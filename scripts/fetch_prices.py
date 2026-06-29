"""Fetch prices for every picked ticker — the ONLY module that touches the network.

Strategy (keyless, cache-first):
  1. Yahoo v8 chart JSON via urllib (one call/ticker gives 5y daily history, the
     live price, and the dated July-1 bar we freeze as the baseline).
  2. yfinance fallback when Yahoo rate-limits a symbol.
  3. If both fail for a ticker, KEEP its cached values — never blank the board.

Writes: data/baseline.json (write-once per ticker), data/prices.json (latest +
recent series for sparklines + headline stats), data/history_long.json
(downsampled 5y for the click-to-expand drawer charts).
"""

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

import store

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CHART = "https://query{h}.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1d&includePrePost=false"
RECENT_N = 45          # daily closes kept for the standings sparklines
LONG_DAILY_DAYS = 380  # keep daily detail within ~1y; weekly before that


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(x):
    """Coerce to float or None (also rejects NaN)."""
    try:
        if x is None:
            return None
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_yahoo(sym):
    """Yahoo v8 chart -> normalized {bars, meta, source} or None. Retries hosts/backs off on 429."""
    for attempt, host in enumerate(["1", "2", "1"]):
        try:
            data = _http_json(CHART.format(h=host, sym=sym))
            res = (data.get("chart") or {}).get("result")
            if not res:
                return None
            return parse_yahoo(res[0])
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503):
                time.sleep([2, 5, 12][min(attempt, 2)])
                continue
            return None
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, ValueError, OSError):
            time.sleep(2)
    return None


def parse_yahoo(res):
    meta = res.get("meta") or {}
    ts = res.get("timestamp") or []
    q = (((res.get("indicators") or {}).get("quote") or [{}])[0]) or {}
    opens, closes = q.get("open") or [], q.get("close") or []
    bars = []
    for i, t in enumerate(ts):
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        o = opens[i] if i < len(opens) else None
        c = closes[i] if i < len(closes) else None
        bars.append({"d": d, "o": _f(o), "c": _f(c)})
    return {
        "bars": bars,
        "meta": {
            "price": _f(meta.get("regularMarketPrice")),
            "prev_close": _f(meta.get("chartPreviousClose") or meta.get("previousClose")),
            "day_high": _f(meta.get("regularMarketDayHigh")),
            "day_low": _f(meta.get("regularMarketDayLow")),
            "week52_high": _f(meta.get("fiftyTwoWeekHigh")),
            "week52_low": _f(meta.get("fiftyTwoWeekLow")),
            "volume": _f(meta.get("regularMarketVolume")),
        },
        "source": "yahoo",
    }


def fetch_yfinance(sym):
    """Fallback via yfinance (different crumb/cookie handling). Returns same shape or None."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        t = yf.Ticker(sym)
        hist = t.history(period="5y", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        bars = [{"d": idx.strftime("%Y-%m-%d"), "o": _f(row.get("Open")), "c": _f(row.get("Close"))}
                for idx, row in hist.iterrows()]
        fi = dict(getattr(t, "fast_info", {}) or {})
        price = _f(fi.get("last_price")) or (bars[-1]["c"] if bars else None)
        return {
            "bars": bars,
            "meta": {
                "price": price,
                "prev_close": _f(fi.get("previous_close")),
                "day_high": _f(fi.get("day_high")),
                "day_low": _f(fi.get("day_low")),
                "week52_high": _f(fi.get("year_high")),
                "week52_low": _f(fi.get("year_low")),
                "volume": _f(fi.get("last_volume")),
            },
            "source": "yfinance",
        }
    except Exception:
        return None


def get_quote(sym):
    return fetch_yahoo(sym) or fetch_yfinance(sym)


def _iso_week(d):
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-{w:02d}"


def downsample(bars):
    """Daily within ~1y, one point per ISO week before that. Chronological out."""
    closed = [b for b in bars if b["c"] is not None]
    if not closed:
        return []
    cutoff = (date.fromisoformat(closed[-1]["d"]) - timedelta(days=LONG_DAILY_DAYS)).isoformat()
    out, weeks = [], set()
    for b in closed:
        if b["d"] >= cutoff:
            out.append({"d": b["d"], "c": round(b["c"], 4)})
        else:
            wk = _iso_week(b["d"])
            if wk not in weeks:
                weeks.add(wk)
                out.append({"d": b["d"], "c": round(b["c"], 4)})
    return out


def update_ticker(sym, parsed, prices, longh, baseline, start_date):
    bars = parsed["bars"]
    closed = [b for b in bars if b["c"] is not None]
    meta = parsed["meta"]

    # Freeze the July-1 OPEN once, read from the dated bar (robust to late runs).
    if sym not in baseline["opens"]:
        jul1 = next((b for b in bars if b["d"] == start_date and b["o"] is not None), None)
        if jul1:
            baseline["opens"][sym] = {
                "open": round(jul1["o"], 4), "source": parsed["source"], "captured_utc": now_iso(),
            }

    price = meta["price"] if meta["price"] is not None else (closed[-1]["c"] if closed else None)
    prev = meta["prev_close"]
    if prev is None and len(closed) >= 2:
        prev = closed[-2]["c"]
    day_pct = ((price - prev) / prev * 100.0) if (price is not None and prev) else None

    prices["tickers"][sym] = {
        "latest": {"price": round(price, 4) if price is not None else None,
                   "asof_utc": now_iso(), "source": parsed["source"]},
        "prev_close": round(prev, 4) if prev else None,
        "day_change_pct": round(day_pct, 2) if day_pct is not None else None,
        "day_high": round(meta["day_high"], 4) if meta["day_high"] else None,
        "day_low": round(meta["day_low"], 4) if meta["day_low"] else None,
        "week52_high": round(meta["week52_high"], 4) if meta["week52_high"] else None,
        "week52_low": round(meta["week52_low"], 4) if meta["week52_low"] else None,
        "volume": int(meta["volume"]) if meta["volume"] else None,
        "recent": [{"d": b["d"], "c": round(b["c"], 4)} for b in closed[-RECENT_N:]],
    }
    longh["tickers"][sym] = {"series": downsample(bars)}


def main():
    owners = store.load("owners.json", {"owners": []}).get("owners", [])
    cfg = store.load("config.json", {})
    start_date = cfg.get("start_session_date", "2026-07-01")

    syms = []
    for o in owners:
        for s in o.get("picks", []):
            if s not in syms:
                syms.append(s)

    prices = store.load("prices.json", {"updated_utc": None, "tickers": {}})
    longh = store.load("history_long.json", {"updated_utc": None, "tickers": {}})
    baseline = store.load("baseline.json", {"frozen_utc": None, "open_session_date": start_date, "opens": {}})
    prices.setdefault("tickers", {})
    longh.setdefault("tickers", {})
    baseline.setdefault("opens", {})

    print(f"Fetching {len(syms)} tickers: {', '.join(syms)}")
    unresolved = []
    for sym in syms:
        parsed = get_quote(sym)
        if not parsed or not parsed["bars"]:
            if sym in prices["tickers"]:
                print(f"  keep-cache  {sym}  (fetch failed; kept last good)")
            else:
                print(f"  UNRESOLVED  {sym}  (no data and no cache)")
                unresolved.append(sym)
            continue
        update_ticker(sym, parsed, prices, longh, baseline, start_date)
        latest = prices["tickers"][sym]["latest"]["price"]
        frozen = "frozen" if sym in baseline["opens"] else "no-Jul1-bar-yet"
        print(f"  ok  {sym:5s} ${latest}  via {parsed['source']:9s} baseline:{frozen}")
        time.sleep(0.4)

    prices["updated_utc"] = now_iso()
    longh["updated_utc"] = now_iso()
    if baseline["opens"] and not baseline.get("frozen_utc"):
        baseline["frozen_utc"] = now_iso()

    wrote = [n for n, ok in [
        ("prices", store.save_if_changed("prices.json", prices)),
        ("history_long", store.save_if_changed("history_long.json", longh)),
        ("baseline", store.save_if_changed("baseline.json", baseline)),
    ] if ok]
    print(f"wrote: {', '.join(wrote) if wrote else 'nothing (no material change)'}")
    if unresolved:
        print(f"!! UNRESOLVED: {unresolved} — check the symbol or add a remap in tickers.json")
        return 0  # non-fatal; build still renders the rest
    return 0


if __name__ == "__main__":
    sys.exit(main())
