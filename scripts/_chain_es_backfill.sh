#!/bin/bash
# Waits for the currently-running OPRA backfill driver to finish, then
# kicks off the ES backfill. Launched with nohup in the background.
#
# Match pattern is specifically the .py file of the BACKFILL driver, not
# the per-day pull scripts (corpus_pull_*.py) which only run as transient
# subprocesses inside the driver.
set -euo pipefail

LOG=/root/projects/Strader/data/corpus/_backfill.log
PATTERN='python.*corpus_backfill_databento\.py'

# Initial wait: the OPRA driver should already be running when we start.
# Poll every 60s until it exits.
while pgrep -f "$PATTERN" > /dev/null; do
    sleep 60
done

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  === chain: OPRA driver exited, starting ES backfill ===" >> "$LOG"

cd /root/projects/Strader
exec .venv/bin/python scripts/corpus_backfill_databento.py --dataset es >> "$LOG" 2>&1
