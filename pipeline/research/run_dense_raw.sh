#!/usr/bin/env bash
# Runs the dense backtest with raw quantiles for the price and then the demand, on the local SQLite file.
# Start:   cd pipeline && bash research/run_dense_raw.sh      (about 20 to 50 minutes in all)
# Alive:   tail -f research/results/dense_raw.log
# Done:    research/results/dense_raw_price.json and dense_raw_demand.json exist (each is skipped if it does).
# Resumes: a finished target is not run again; delete its json to repeat it.
set -euo pipefail
cd "$(dirname "$0")/.."
export DATABASE_URL="sqlite:///data/voltia.sqlite"
LOG="research/results/dense_raw.log"
for target in price demand; do
  if [ -f "research/results/dense_raw_${target}.json" ]; then
    echo "$(date -u +%FT%TZ) ${target}: already done" | tee -a "$LOG"
    continue
  fi
  echo "$(date -u +%FT%TZ) ${target}: start" | tee -a "$LOG"
  uv run --frozen python research/run_dense_raw.py "$target" 2>&1 | tee -a "$LOG"
  echo "$(date -u +%FT%TZ) ${target}: done" | tee -a "$LOG"
done
