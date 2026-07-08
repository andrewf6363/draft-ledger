"""Unit tests for lib.py scoring. Zero network. Run: python3 scripts/test_lib.py"""

import lib


def approx(a, b, eps=1e-9):
    return a is not None and b is not None and abs(a - b) < eps


def test_pct_return():
    assert approx(lib.pct_return(110, 100), 10.0)
    assert approx(lib.pct_return(90, 100), -10.0)
    assert lib.pct_return(None, 100) is None      # no price yet
    assert lib.pct_return(110, None) is None       # no baseline yet
    assert lib.pct_return(110, 0) is None          # never divide by zero


def test_owner_average():
    rets = [{"sym": "A", "pct": 10.0}, {"sym": "B", "pct": 0.0}, {"sym": "C", "pct": -1.0}]
    assert approx(lib.owner_average(rets), 3.0)
    rets_pending = [{"sym": "A", "pct": 10.0}, {"sym": "B", "pct": None}, {"sym": "C", "pct": 5.0}]
    assert lib.owner_average(rets_pending) is None  # any pending -> whole owner pending


def test_contribution():
    assert approx(lib.contribution(9.0, 3), 3.0)
    assert lib.contribution(None, 3) is None


def test_standings_order_and_points_behind():
    owners = [
        {"name": "Kyle Williams", "picks": ["GEV", "VRT", "CEG"]},
        {"name": "John Atkins", "picks": ["RKLB", "OKLO", "HOOD"]},
        {"name": "Keegan Ball", "picks": ["NNE", "OKLO", "LUNR"]},
        {"name": "Andrew Fahey", "picks": ["MU", "STX", "SNDK"]},
    ]
    opens = {s: 100.0 for s in ["GEV", "VRT", "CEG", "RKLB", "OKLO", "HOOD", "NNE", "LUNR", "MU", "STX", "SNDK"]}
    latest = {
        "RKLB": 114.2, "OKLO": 109.6, "HOOD": 106.1,   # John  -> 9.97
        "NNE": 118.4, "LUNR": 96.8,                     # Keegan-> 8.27 (OKLO shared)
        "MU": 111.3, "STX": 107.8, "SNDK": 102.4,       # Andrew-> 7.17
        "GEV": 105.2, "VRT": 103.1, "CEG": 98.6,        # Kyle  -> 2.30
    }
    s = lib.compute_standings(owners, latest, opens)
    names = [r["name"] for r in s]
    assert names == ["John Atkins", "Keegan Ball", "Andrew Fahey", "Kyle Williams"], names
    assert [r["rank"] for r in s] == [1, 2, 3, 4]
    assert approx(round(s[0]["avg"], 2), 9.97)
    assert s[0]["points_behind"] == 0.0
    assert s[1]["points_behind"] == 1.70    # 9.97 - 8.27
    assert s[3]["points_behind"] == 7.67    # 9.97 - 2.30
    # OKLO shared by John & Keegan resolves to the same return for both
    john_oklo = next(x["pct"] for x in s[0]["returns"] if x["sym"] == "OKLO")
    keegan_oklo = next(x["pct"] for x in s[1]["returns"] if x["sym"] == "OKLO")
    assert approx(john_oklo, keegan_oklo)


def test_shared_rank_ties():
    owners = [
        {"name": "Pat", "picks": ["A", "B", "C"]},   # +10,0,-10 -> 0.00, best 10
        {"name": "Quinn", "picks": ["D", "E", "F"]}, # +5,0,-5   -> 0.00, best 5
        {"name": "Rory", "picks": ["G", "H", "I"]},  # -5,-5,-5  -> -5.00
    ]
    opens = {s: 100.0 for s in "ABCDEFGHI"}
    latest = {"A": 110, "B": 100, "C": 90, "D": 105, "E": 100, "F": 95, "G": 95, "H": 95, "I": 95}
    s = lib.compute_standings(owners, latest, opens)
    by = {r["name"]: r for r in s}
    assert by["Pat"]["rank"] == 1 and by["Quinn"]["rank"] == 1, "tie shares rank 1"
    assert by["Rory"]["rank"] == 3, "next distinct skips to 3"
    # break_tie default: higher single best pick displays first
    assert [r["name"] for r in s][:2] == ["Pat", "Quinn"]


def test_pending_owner_sorts_last_without_rank():
    owners = [
        {"name": "Full", "picks": ["A", "B", "C"]},
        {"name": "Half", "picks": ["A", "B", "Z"]},  # Z has no price -> pending
    ]
    opens = {"A": 100.0, "B": 100.0, "C": 100.0, "Z": 100.0}
    latest = {"A": 110, "B": 110, "C": 110}           # Z missing
    s = lib.compute_standings(owners, latest, opens)
    assert s[0]["name"] == "Full" and s[0]["rank"] == 1
    assert s[1]["name"] == "Half" and s[1]["rank"] is None and s[1]["pending"] is True


def test_apply_movement():
    s = [{"name": "John", "rank": 1}, {"name": "Keegan", "rank": 2}, {"name": "New", "rank": 3}]
    lib.apply_movement(s, {"John": 2, "Keegan": 1})
    assert s[0]["movement"] == 1 and s[0]["is_new"] is False   # John climbed 2->1
    assert s[1]["movement"] == -1                               # Keegan slipped 1->2
    assert s[2]["is_new"] is True                               # New owner, no prior rank


def test_split_adjustment_crwd():
    ev = [{"date": "2026-07-02", "ratio": 4}]   # CrowdStrike 4-for-1, effective Jul 2
    # Before the split is effective, nothing is adjusted (Jun 30 view).
    assert lib.split_factor(ev, "2026-07-01", "2026-06-30") == 1.0
    assert approx(lib.split_adjust(760.0, ev, "2026-07-01", "2026-06-30"), 760.0)
    # Once effective, the Jul-1 baseline is restated onto the post-split basis.
    assert lib.split_factor(ev, "2026-07-01", "2026-07-15") == 4.0
    assert approx(lib.split_adjust(760.0, ev, "2026-07-01", "2026-07-15"), 190.0)
    # A price already observed post-split has no later split to adjust for.
    assert approx(lib.split_adjust(190.0, ev, "2026-07-10", "2026-07-15"), 190.0)
    # End to end: $760 open, 4-for-1 split, $200 now -> a real +5.26%, not -74%.
    adj_open = lib.split_adjust(760.0, ev, "2026-07-01", "2026-07-15")
    assert approx(round(lib.pct_return(200.0, adj_open), 2), 5.26)
    # Without the fix it would be catastrophic:
    assert round(lib.pct_return(200.0, 760.0), 1) == -73.7
    # Reverse split (1-for-10) scales the other way.
    rev = [{"date": "2026-07-10", "ratio": 0.1}]
    assert approx(lib.split_adjust(5.0, rev, "2026-07-01", "2026-07-15"), 50.0)
    # A stock with no splits is completely untouched.
    assert lib.split_factor([], "2026-07-01", "2026-07-15") == 1.0


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run()
