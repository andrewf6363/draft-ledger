# The Draft Ledger — Build Checklist

Plan: `~/.claude/plans/i-d-like-to-build-effervescent-dawn.md`
**Live:** https://andrewf6363.github.io/draft-ledger/ · Repo: andrewf6363/draft-ledger (public)

## Scaffold & data
- [x] Directory structure, owners/tickers/config, seed machine files

## Core scripts
- [x] `lib.py` pure scoring + `test_lib.py` (7 tests pass) — tiebreaker left for Andrew
- [x] `fetch_prices.py` — Yahoo (fail-fast) → yfinance → cache; freezes Jul-1 open
- [x] `fetch_news.py` — Google News RSS (keyless), Yahoo fallback
- [x] `build.py` — orchestrator → index.html (pre / live / final states)
- [x] `template.html` — Modern Club design, drawer, race chart, board, sectors, countdown
- [x] `make_cards.py` — Pillow per-owner PNG cards + og/icon (brand fonts)
- [x] `update.sh` + `.github/workflows/update.yml` — 3×/trading-day cron, no supervisor

## Test locally
- [x] Unit tests pass (7/7)
- [x] Pre-state build renders countdown + roster (verified in browser, 0 console errors)
- [x] Live-state build verified via mock fixture — standings, tiles, drawer (3M/6M/YTD/1Y/5Y), race, movers, sectors
- [x] Data reset to honest-empty before deploy

## Deploy
- [x] `git init` isolated repo (separate from home repo)
- [x] Pushed to andrewf6363/draft-ledger
- [x] Repo public (free plan can't serve Pages from private — World Cup is public too)
- [x] GitHub Pages live (main / root) — URL returns 200, content correct
- [x] Smoke test: Action runs green; **yfinance resolves all 11 tickers on GitHub's IP** (keyless works)

## Launch (Jul 1) — for Andrew
- [ ] **Tonight:** add the remaining 8 owners to `data/owners.json` (+ new tickers to `data/tickers.json`), commit
- [ ] Jul 1: confirm the workflow is enabled in the Actions tab; baselines freeze; board flips to live
- [ ] (Optional) write your own tiebreaker rule in `lib.py` `break_tie()`

## Review
- Both states render cleanly; no JS errors. Drawer wiring uses direct binding (robust on touch).
- Data is legitimate simulated-2026 (AI-infrastructure melt-up); absolute prices are high but
  **% returns are computed consistently from one source, so standings are correct.**
- yfinance leaves volume/day-range null; 52-wk range is derived from history as a fallback.
- News now pulls real headlines via Google News RSS (validated locally).
