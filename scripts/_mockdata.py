"""DEV-ONLY: write a realistic mid-July fixture into data/ so the live view can be
QA'd locally (the real feed is throttled from this IP). NOT part of the pipeline.
Run `python3 scripts/_mockdata.py` then `python3 scripts/build.py`. Reset afterward
with the seed files (or git checkout) before deploying — the live site must start
in honest pre-launch.
"""
import random
from datetime import date, timedelta

import store

random.seed(42)

# symbol -> (Jul-1 open baseline, total % return so far, today's % move)
SPEC = {
    "RKLB": (28.00, 14.2, 1.1), "OKLO": (56.00, 9.6, 0.8), "HOOD": (23.50, 6.1, 0.5),
    "NNE": (32.00, 18.4, 2.2),  "LUNR": (12.30, -3.2, -0.6),
    "MU": (110.00, 11.3, 1.6),  "STX": (95.00, 7.8, 1.1),  "SNDK": (47.00, 2.4, 0.5),
    "GEV": (175.00, 5.2, 1.2),  "VRT": (110.00, 3.1, 0.6), "CEG": (215.00, -1.4, -0.4),
}
NOW = {s: round(b * (1 + p / 100), 2) for s, (b, p, _) in SPEC.items()}


def july_recent(s):
    b, _, _ = SPEC[s]
    end, out = NOW[s], []
    days = [date(2026, 7, 1) + timedelta(days=i) for i in range(20)]
    days = [d for d in days if d.weekday() < 5]
    for i, d in enumerate(days):
        frac = i / (len(days) - 1)
        val = b + (end - b) * frac + random.uniform(-1, 1) * b * 0.008
        out.append({"d": d.isoformat(), "c": round(val, 2)})
    out[-1]["c"] = end
    return out


def long_series(s):
    vals, v = [], NOW[s]
    for _ in range(160):
        vals.append(v)
        v = v / (1 + random.uniform(-0.04, 0.045))
    vals = vals[::-1]
    start = date(2023, 7, 3)
    return [{"d": (start + timedelta(weeks=i)).isoformat(), "c": round(max(x, 0.5), 2)} for i, x in enumerate(vals)]


# baseline (all frozen)
baseline = {"frozen_utc": "2026-07-01T13:31:00Z", "open_session_date": "2026-07-01",
            "opens": {s: {"open": round(b, 4), "source": "mock", "captured_utc": "2026-07-01T13:31:00Z"}
                      for s, (b, _, _) in SPEC.items()}}

# prices
prices = {"updated_utc": "2026-07-18T16:05:00Z", "tickers": {}}
for s, (b, p, day) in SPEC.items():
    series = [c["c"] for c in long_series(s)]
    prices["tickers"][s] = {
        "latest": {"price": NOW[s], "asof_utc": "2026-07-18T16:05:00Z", "source": "mock"},
        "prev_close": round(NOW[s] / (1 + day / 100), 2),
        "day_change_pct": day,
        "day_high": round(NOW[s] * 1.012, 2), "day_low": round(NOW[s] * 0.987, 2),
        "week52_high": round(max(series) * 1.02, 2), "week52_low": round(min(series) * 0.98, 2),
        "volume": random.randint(2, 40) * 100000,
        "recent": july_recent(s),
    }

longh = {"updated_utc": "2026-07-18T16:05:00Z", "tickers": {s: {"series": long_series(s)} for s in SPEC}}

news = {"updated_utc": "2026-07-18T16:05:00Z", "tickers": {}}
HL = {"RKLB": "Rocket Lab lands new Neutron launch contract",
      "NNE": "Nano Nuclear advances microreactor licensing milestone",
      "OKLO": "Oklo signs power-purchase agreement with data-center operator",
      "MU": "Micron HBM demand outpaces supply on AI buildout"}
for s in SPEC:
    t = store.load("tickers.json", {}).get(s, {}).get("name", s)
    news["tickers"][s] = {"items": [
        {"title": HL.get(s, f"{t} extends July rally as sector momentum builds"),
         "link": f"https://finance.yahoo.com/quote/{s}", "pub": "Fri, 17 Jul 2026 18:30:00 GMT"},
        {"title": f"Analysts weigh in on {t} after strong month", "link": f"https://finance.yahoo.com/quote/{s}",
         "pub": "Thu, 16 Jul 2026 14:05:00 GMT"},
    ]}

# standings history: 4 prior days, with a rank swap on the last so movement shows
def ranks_from(avgs):
    order = sorted(avgs, key=lambda k: -avgs[k])
    return {n: i + 1 for i, n in enumerate(order)}

snaps = []
days = [("2026-06-25", {"John Atkins": 9.1, "Andrew Fahey": 7.0, "Keegan Ball": 6.8, "Kyle Williams": 2.0}),
        ("2026-06-26", {"John Atkins": 9.4, "Andrew Fahey": 7.3, "Keegan Ball": 7.1, "Kyle Williams": 2.1}),
        ("2026-06-27", {"John Atkins": 9.6, "Andrew Fahey": 7.6, "Keegan Ball": 7.4, "Kyle Williams": 2.2}),
        ("2026-06-28", {"John Atkins": 9.8, "Andrew Fahey": 7.9, "Keegan Ball": 7.7, "Kyle Williams": 2.25})]
for d, avgs in days:
    snaps.append({"date": d, "avgs": avgs, "ranks": ranks_from(avgs)})
histj = {"snapshots": snaps}

for name, obj in [("baseline.json", baseline), ("prices.json", prices),
                  ("history_long.json", longh), ("news.json", news),
                  ("standings_history.json", histj)]:
    store.save_if_changed(name, obj)
print("mock fixture written (mid-July live state).")
