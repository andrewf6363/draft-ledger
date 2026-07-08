"""Pure, deterministic scoring for The Draft Ledger.

No file I/O, no network, no clock reads here — every input is passed in, so the
same inputs always produce the same output. That is what makes the whole site
self-healing: each run recomputes standings from scratch, so a corrected price
or a late baseline fixes everything downstream automatically.

The game: each owner picks 3 stocks. Score = average percent return across the 3,
measured from each stock's July-1 OPEN. Highest average earns the No. 1 draft pick.
"""

import functools

ROUND_DP = 2  # decimals shown for percentages everywhere on the site


def pct_return(latest, open_):
    """Percent return of one stock since its frozen July-1 open.

    Returns None when it can't be computed yet (no baseline frozen, or no price),
    so a not-yet-started or missing pick never divides by zero or fabricates a 0%.
    """
    if latest is None or open_ is None or open_ == 0:
        return None
    return (latest - open_) / open_ * 100.0


def owner_returns(picks, latest_by_sym, open_by_sym):
    """Per-pick returns for one owner, in pick order. Each item: {sym, pct|None}."""
    return [
        {"sym": sym, "pct": pct_return(latest_by_sym.get(sym), open_by_sym.get(sym))}
        for sym in picks
    ]


def owner_average(returns):
    """Average percent return across an owner's picks.

    Returns None if ANY pick is still pending — we only rank fully-priced owners,
    so a partial denominator can never mis-rank someone. Sum is in fixed pick
    order for determinism.
    """
    vals = [r["pct"] for r in returns]
    if not vals or any(v is None for v in vals):
        return None
    return sum(vals) / len(vals)


def contribution(pct, n_picks):
    """Points this single pick adds to the owner's average (pct / number_of_picks).

    Lets the site show which of someone's three picks is actually carrying them.
    """
    if pct is None or n_picks == 0:
        return None
    return pct / n_picks


def break_tie(a, b):
    """Order two owners who have the SAME rounded average return.

    Return a NEGATIVE number if `a` should display above `b`, POSITIVE if `b`
    should display above `a`, and 0 if they are genuinely indistinguishable
    (they then share a rank number). Each owner dict has keys: `name` (str),
    `avg` (float), and `returns` (list of {sym, pct}).

    --- ANDREW: THIS ONE IS YOURS. ---
    The league rules don't define a tiebreaker, and with returns measured to two
    decimals an exact tie is unlikely but possible. The default below breaks ties
    by whoever's single best-performing stock is higher, then alphabetically.
    Swap in whatever feels fair to your league (e.g. lowest spread between their
    three picks = "most consistent wins", or earliest submission, or a coin-flip
    seeded by name). Keep it a pure function of the two dicts.
    """
    best_a = max((r["pct"] for r in a["returns"] if r["pct"] is not None), default=0.0)
    best_b = max((r["pct"] for r in b["returns"] if r["pct"] is not None), default=0.0)
    if best_a != best_b:
        return -1 if best_a > best_b else 1
    if a["name"] != b["name"]:
        return -1 if a["name"] < b["name"] else 1
    return 0


def compute_standings(owners, latest_by_sym, open_by_sym):
    """Rank owners best-first. `owners` is a list of {name, picks:[3 syms]}.

    Returns a list of result dicts: name, picks, returns, avg, pending, rank,
    points_behind. Owners whose picks aren't all priced yet are marked pending
    and sorted to the end without a rank.
    """
    rows = []
    for o in owners:
        rets = owner_returns(o["picks"], latest_by_sym, open_by_sym)
        avg = owner_average(rets)
        rows.append({
            "name": o["name"],
            "picks": list(o["picks"]),
            "returns": rets,
            "avg": avg,
            "pending": avg is None,
        })

    ranked = [r for r in rows if r["avg"] is not None]
    pending = [r for r in rows if r["avg"] is None]

    def cmp(a, b):
        da, db = round(a["avg"], ROUND_DP), round(b["avg"], ROUND_DP)
        if da != db:
            return -1 if da > db else 1
        return break_tie(a, b)

    ranked.sort(key=functools.cmp_to_key(cmp))

    out = []
    leader_avg = round(ranked[0]["avg"], ROUND_DP) if ranked else None
    last_avg = None
    last_rank = 0
    for i, r in enumerate(ranked):
        ravg = round(r["avg"], ROUND_DP)
        if last_avg is None or ravg != last_avg:
            rank = i + 1            # standard competition ranking: ties share, next skips
            last_rank, last_avg = rank, ravg
        else:
            rank = last_rank        # equal rounded average -> shared rank
        row = dict(r)
        row["rank"] = rank
        row["points_behind"] = round(leader_avg - ravg, ROUND_DP)
        out.append(row)

    for r in pending:
        row = dict(r)
        row["rank"] = None
        row["points_behind"] = None
        out.append(row)
    return out


def split_factor(events, after_date, as_of_date):
    """Cumulative split ratio for the splits in `events` that fall strictly after
    `after_date` AND on-or-before `as_of_date` — i.e. splits that have actually
    happened yet. `ratio` is new shares per old share (a 4-for-1 split is 4; a
    1-for-10 reverse split is 0.1). Returns 1.0 when nothing applies.

    Gating on `as_of_date` is what keeps a *future* split (announced but not yet
    effective) from retro-adjusting today's price before it actually happens.
    """
    f = 1.0
    for ev in events or []:
        d = ev.get("date", "")
        if d and after_date < d <= as_of_date:
            try:
                r = float(ev.get("ratio", 1) or 1)
                if r > 0:
                    f *= r
            except (TypeError, ValueError):
                pass
    return f or 1.0


def split_adjust(price, events, ref_date, as_of_date):
    """Restate a price observed on `ref_date` onto the share basis in effect as of
    `as_of_date`, accounting for any splits in between. A split is not a gain or a
    loss, so dividing the pre-split price by the split ratio keeps returns honest.
    """
    if price is None:
        return None
    f = split_factor(events, ref_date, as_of_date)
    return price / f if f else price


def apply_movement(standings, prev_ranks):
    """Add rank movement vs the previous snapshot.

    `prev_ranks` maps name -> rank from the last saved snapshot. Sets `movement`
    (prev_rank - rank; positive = climbed) and `is_new` on each row.
    """
    for r in standings:
        pr = prev_ranks.get(r["name"])
        if pr is None or r["rank"] is None:
            r["movement"] = 0
            r["is_new"] = pr is None and r["rank"] is not None
        else:
            r["movement"] = pr - r["rank"]
            r["is_new"] = False
    return standings
