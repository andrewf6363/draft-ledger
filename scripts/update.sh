#!/usr/bin/env bash
# The Draft Ledger — one-shot auto-update.
# Fetch prices + news, recompute, and publish ONLY if data changed.
# Run by hand anytime (bash scripts/update.sh) or by the scheduled GitHub Action.
set -uo pipefail
cd "$(dirname "$0")/.."

git pull --quiet --ff-only origin main 2>/dev/null || true

python3 scripts/fetch_prices.py
python3 scripts/fetch_news.py || true   # news is best-effort; never block on it

if git diff --quiet -- data/; then
  echo "No data changes — nothing to publish."
  exit 0
fi

python3 scripts/build.py
python3 scripts/make_cards.py || true    # shareable cards; skips if Pillow/fonts missing

git add -A
git commit -q -m "auto-update: $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q origin main
echo "Published update."
