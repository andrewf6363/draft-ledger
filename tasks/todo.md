# The Draft Ledger — Build Checklist

Plan: `~/.claude/plans/i-d-like-to-build-effervescent-dawn.md`

## Scaffold & data
- [x] Directory structure (`data/`, `scripts/`, `assets/fonts/`, `.github/workflows/`)
- [x] `data/owners.json` (4 known owners; 8 more arrive tonight)
- [x] `data/tickers.json` (11 symbols, name + sector)
- [x] `data/config.json` (title, dates, commissioner)
- [x] Seed machine files (baseline, prices, history_long, news, standings_history, overrides)

## Core scripts
- [ ] `scripts/lib.py` — pure deterministic scoring (+ tiebreaker: Andrew's contribution)
- [ ] `scripts/test_lib.py` — unit tests, zero network
- [ ] `scripts/fetch_prices.py` — Yahoo v8 + yfinance fallback, cache-first, baseline freeze
- [ ] `scripts/fetch_news.py` — Yahoo RSS, best-effort
- [ ] `scripts/build.py` — orchestrator → render `index.html`
- [ ] `scripts/template.html` — Modern Club design + render JS + drawer + charts
- [ ] `scripts/make_cards.py` — Pillow per-owner PNG cards
- [ ] `scripts/update.sh` — pull → fetch → build → cards → commit-if-changed → push
- [ ] `.github/workflows/update.yml` — 3×/trading-day cron, no supervisor

## Test locally
- [ ] Unit tests pass
- [ ] `fetch_prices.py` dry-run resolves all 12 tickers (incl. GEV/SNDK/NNE/OKLO/LUNR)
- [ ] `build.py` renders countdown state (pre-July) and live state (mocked baseline)
- [ ] Preview `index.html` — tape, drawer, timeframe toggle, sparklines, responsive

## Deploy
- [ ] `git init` in THIS folder (isolated from home repo)
- [ ] `gh repo create andrewf6363/draft-ledger --private`, push
- [ ] Enable GitHub Pages (main / root)
- [ ] `workflow_dispatch` smoke test; confirm live URL updates

## Launch (Jul 1)
- [ ] Add remaining 8 owners to `owners.json` (tonight)
- [ ] Confirm Action enabled in Actions tab
- [ ] Verify baselines froze; all tickers resolve

## Review
_(filled in after build)_
