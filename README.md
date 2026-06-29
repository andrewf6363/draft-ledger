# The Draft Ledger

A live, auto-updating scoreboard for the league's July stock challenge. Each owner
picks 3 stocks; the **highest average percent return** across the three (measured from
the **July 1 market open** to the **July 31 close**) earns the **No. 1 draft pick**.

Built as a static GitHub Pages site that a GitHub Action refreshes 3× per trading day.

---

## How it works

1. A GitHub Action runs `scripts/update.sh` at market open, midday, and after close (weekdays).
2. `fetch_prices.py` pulls each ticker's price + history (Yahoo, no API key; `yfinance` fallback; last-good cache).
   - The **July 1 opening price** is frozen once into `data/baseline.json` and never changes — it's the denominator for every return.
3. `build.py` recomputes standings from scratch and regenerates `index.html`.
4. It commits **only if something changed**, and GitHub Pages serves the new page.

Before July 1 the site shows the **roster + a countdown**. Once all opening prices are
frozen it flips to the **live board**; after the July 31 close it locks to **final**.

## Adding owners (the one edit that matters)

Open `data/owners.json` and add a line per owner:

```json
{ "name": "First Last", "picks": ["AAA", "BBB", "CCC"] }
```

Then, for any **new** ticker, add a row to `data/tickers.json`:

```json
"AAA": { "name": "Company Name", "sector": "Sector" }
```

Commit. The next run (or `bash scripts/update.sh`, or the **Run workflow** button in the
Actions tab) picks them up automatically. No code changes.

## Fixing a bad price

Edit `data/overrides.json` — commissioner always wins:

```json
{ "latest": { "SNDK": 49.88 }, "baseline": { "SNDK": 47.10 } }
```

## Local commands

```bash
python3 scripts/test_lib.py      # scoring unit tests
python3 scripts/fetch_prices.py  # pull live data (needs an un-throttled IP)
python3 scripts/build.py         # regenerate index.html
python3 scripts/_mockdata.py     # DEV: write a fake mid-July fixture to preview the live view
```

## Launch-day checklist (July 1)

- [ ] Open the **Actions** tab and confirm the workflow is enabled (GitHub disables idle schedules after 60 days).
- [ ] Hit **Run workflow** once as a smoke test.
- [ ] Confirm `data/baseline.json` froze all opening prices and the board went live.
- [ ] If the run logs `UNRESOLVED` tickers or Yahoo rate-limits GitHub's runners, add a free
      API key fallback (Finnhub/Alpha Vantage) — `fetch_prices.py` is built to chain in another source.
