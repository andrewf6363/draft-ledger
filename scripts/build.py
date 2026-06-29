"""Orchestrator: load every data file, compute standings + presentation extras,
inject one DATA blob into template.html, and write index.html.

Deterministic and self-healing — it recomputes everything from scratch each run.
Renders a pre-launch roster+countdown until all July-1 baselines are frozen, then
flips to the live board, then locks to a final state after the July-31 close.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import lib
import store

ET = timezone(timedelta(hours=-4))            # EDT — valid for the whole July window
HOLIDAYS = {"2026-07-03"}                       # Independence Day observed (Jul 4 is a Sat)


def now_utc():
    return datetime.now(timezone.utc)


def et_now():
    return now_utc().astimezone(ET)


def iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rnd(x, dp=2):
    return None if x is None else round(x, dp)


def market_status():
    n = et_now()
    if n.weekday() >= 5:
        return "Market closed · weekend", False
    if n.date().isoformat() in HOLIDAYS:
        return "Market closed · holiday", False
    mins = n.hour * 60 + n.minute
    if mins < 9 * 60 + 30:
        return "Pre-market", False
    if mins < 16 * 60:
        return "Market open", True
    return "After hours", False


def trading_days_left(start_date, end_date):
    """Weekdays (minus known holidays) from max(today, start) through end, inclusive."""
    today = et_now().date()
    cur = max(today, date.fromisoformat(start_date))
    end = date.fromisoformat(end_date)
    n = 0
    while cur <= end:
        if cur.weekday() < 5 and cur.isoformat() not in HOLIDAYS:
            n += 1
        cur += timedelta(days=1)
    return n


def spark(july_closes, baseline_open, w=64, h=20, pad=2):
    """Inline-SVG polyline points for the standings sparkline, anchored at the
    July-1 open so the slope literally is the return. None until there's data."""
    if baseline_open is None or not july_closes:
        return None
    series = [baseline_open] + list(july_closes)
    if len(series) < 2:
        return None
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1.0
    n = len(series)
    pts = []
    for i, v in enumerate(series):
        x = pad + (w - 2 * pad) * (i / (n - 1))
        y = pad + (h - 2 * pad) * (1 - (v - lo) / span)
        pts.append(f"{x:.1f},{y:.1f}")
    return {"points": " ".join(pts), "up": series[-1] >= baseline_open}


def main():
    cfg = store.load("config.json", {})
    owners = store.load("owners.json", {"owners": []}).get("owners", [])
    tickers = store.load("tickers.json", {})
    baseline = store.load("baseline.json", {"opens": {}})
    prices = store.load("prices.json", {"tickers": {}})
    longh = store.load("history_long.json", {"tickers": {}})
    news = store.load("news.json", {"tickers": {}})
    hist = store.load("standings_history.json", {"snapshots": []})
    ov = store.load("overrides.json", {"latest": {}, "baseline": {}})

    start_date = cfg.get("start_session_date", "2026-07-01")
    end_date = cfg.get("end_session_date", "2026-07-31")

    opens_raw = baseline.get("opens", {})
    pt = prices.get("tickers", {})

    # Resolve maps (overrides win).
    open_by_sym, latest_by_sym = {}, {}
    for sym in tickers:
        op = ov.get("baseline", {}).get(sym)
        if op is None and sym in opens_raw:
            op = opens_raw[sym].get("open")
        open_by_sym[sym] = op
        lp = ov.get("latest", {}).get(sym)
        if lp is None:
            lp = (pt.get(sym, {}).get("latest") or {}).get("price")
        latest_by_sym[sym] = lp

    picked = []
    for o in owners:
        for s in o.get("picks", []):
            if s not in picked:
                picked.append(s)

    have_all_baseline = bool(picked) and all(open_by_sym.get(s) is not None for s in picked)

    def last_close_date(sym):
        rec = pt.get(sym, {}).get("recent") or []
        return rec[-1]["d"] if rec else None

    is_final = have_all_baseline and all(
        (last_close_date(s) or "") >= end_date for s in picked
    )
    state = "live" if have_all_baseline else "pre"
    if is_final:
        state = "final"

    # --- standings (live/final) ---
    standings = lib.compute_standings(owners, latest_by_sym, open_by_sym)

    # movement vs the most recent snapshot from a PRIOR day (before upserting today)
    today = et_now().date().isoformat()
    snaps = sorted(hist.get("snapshots", []), key=lambda s: s.get("date", ""))
    prev_ranks = {}
    for s in snaps:
        if s.get("date", "") < today:
            prev_ranks = s.get("ranks", {})
    lib.apply_movement(standings, prev_ranks)

    # attach presentation detail to each row
    name_to_picks = {o["name"]: o["picks"] for o in owners}
    rows = []
    for r in standings:
        picks_detail = []
        for item in r["returns"]:
            sym = item["sym"]
            op = open_by_sym.get(sym)
            tp = pt.get(sym, {})
            rec = [c for c in ((tp.get("recent") or [])) if c["d"] >= start_date]
            picks_detail.append({
                "sym": sym,
                "name": tickers.get(sym, {}).get("name", sym),
                "sector": tickers.get(sym, {}).get("sector", ""),
                "pct": rnd(item["pct"]),
                "contribution": rnd(lib.contribution(item["pct"], len(r["picks"]))),
                "price": latest_by_sym.get(sym),
                "day_change_pct": tp.get("day_change_pct"),
                "baseline": rnd(op, 4) if op is not None else None,
                "spark": spark([c["c"] for c in rec], op),
            })
        rows.append({
            "name": r["name"], "rank": r["rank"], "avg": rnd(r["avg"]),
            "points_behind": r["points_behind"], "movement": r.get("movement", 0),
            "is_new": r.get("is_new", False), "pending": r["pending"], "picks": picks_detail,
        })

    draft_order = [{"rank": r["rank"], "name": r["name"], "avg": r["avg"]}
                   for r in rows if r["rank"] is not None]

    # --- daily movers ---
    movers = None
    if state in ("live", "final"):
        owners_of = {}
        for o in owners:
            for s in o["picks"]:
                owners_of.setdefault(s, []).append(o["name"])
        moved = [(s, pt.get(s, {}).get("day_change_pct")) for s in picked]
        moved = [(s, d) for s, d in moved if d is not None]
        if moved:
            g = max(moved, key=lambda x: x[1])
            d = min(moved, key=lambda x: x[1])
            movers = {
                "gainer": {"sym": g[0], "name": tickers.get(g[0], {}).get("name", g[0]),
                           "pct": g[1], "owners": owners_of.get(g[0], [])},
                "drag": {"sym": d[0], "name": tickers.get(d[0], {}).get("name", d[0]),
                         "pct": d[1], "owners": owners_of.get(d[0], [])},
            }

    # --- sector tally (by pick instance) ---
    sec_counts = {}
    total_picks = 0
    for o in owners:
        for s in o["picks"]:
            total_picks += 1
            sec = tickers.get(s, {}).get("sector", "Other")
            sec_counts[sec] = sec_counts.get(sec, 0) + 1
    sectors = [{"sector": k, "count": v, "pct": round(v / total_picks * 100)}
               for k, v in sorted(sec_counts.items(), key=lambda x: -x[1])] if total_picks else []

    # --- per-ticker detail for the drawer ---
    tick_detail = {}
    for sym in picked:
        op = open_by_sym.get(sym)
        lp = latest_by_sym.get(sym)
        tp = pt.get(sym, {})
        tick_detail[sym] = {
            "name": tickers.get(sym, {}).get("name", sym),
            "sector": tickers.get(sym, {}).get("sector", ""),
            "price": lp,
            "day_change_pct": tp.get("day_change_pct"),
            "baseline": rnd(op, 4) if op is not None else None,
            "return_pct": rnd(lib.pct_return(lp, op)),
            "week52_high": tp.get("week52_high"), "week52_low": tp.get("week52_low"),
            "day_high": tp.get("day_high"), "day_low": tp.get("day_low"),
            "volume": tp.get("volume"),
            "history": (longh.get("tickers", {}).get(sym, {}) or {}).get("series", []),
            "news": (news.get("tickers", {}).get(sym, {}) or {}).get("items", []),
        }

    # --- roster (pre state) ---
    roster = [{"name": o["name"],
               "picks": [{"sym": s, "name": tickers.get(s, {}).get("name", s),
                          "sector": tickers.get(s, {}).get("sector", "")} for s in o["picks"]]}
              for o in owners]

    # --- upsert today's snapshot + build race series ---
    if state in ("live", "final"):
        cur_avgs = {r["name"]: r["avg"] for r in rows if r["avg"] is not None}
        cur_ranks = {r["name"]: r["rank"] for r in rows if r["rank"] is not None}
        snaps = [s for s in snaps if s.get("date") != today]
        snaps.append({"date": today, "avgs": cur_avgs, "ranks": cur_ranks})
        snaps.sort(key=lambda s: s["date"])
        hist["snapshots"] = snaps
        store.save_if_changed("standings_history.json", hist)

    race_dates = [s["date"] for s in snaps]
    race_series = [{"name": o["name"],
                    "points": [s.get("avgs", {}).get(o["name"]) for s in snaps]}
                   for o in owners]

    status_label, is_open = market_status()
    data = {
        "meta": {
            "title": cfg.get("title", "The Draft Ledger"),
            "subtitle": cfg.get("subtitle", ""),
            "edition": cfg.get("edition", ""),
            "commissioner": cfg.get("commissioner", ""),
            "prize_line": cfg.get("prize_line", ""),
            "state": state,
            "generated_utc": iso_z(now_utc()),
            "start_utc": cfg.get("start_utc"), "end_utc": cfg.get("end_utc"),
            "open_label": cfg.get("open_label", ""), "close_label": cfg.get("close_label", ""),
            "market_status": status_label, "market_open": is_open,
            "baseline_count": sum(1 for s in picked if open_by_sym.get(s) is not None),
            "picked_count": len(picked),
            "owner_count": len(owners),
            "days_left": trading_days_left(start_date, end_date),
        },
        "roster": roster,
        "standings": rows,
        "draft_order": draft_order,
        "movers": movers,
        "sectors": sectors,
        "race": {"dates": race_dates, "series": race_series},
        "tickers": tick_detail,
    }

    tpl_path = os.path.join(store.HERE, "template.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    with open(os.path.join(store.ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    store.save_if_changed("standings.json", {"generated_utc": data["meta"]["generated_utc"],
                                             "state": state, "standings": rows})

    print(f"build: state={state} owners={len(owners)} priced={data['meta']['baseline_count']}/{len(picked)} "
          f"-> index.html ({len(html)//1024}kb)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
