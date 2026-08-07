#!/usr/bin/env bash
# gexbot_hist_nightly.sh — nightly gexbot /hist harvest [st-mx42]
# Idempotent: backfill skips files already present locally or on Z:.
# --days 3 self-heals evenings where the vendor hasn't published yet.
set -uo pipefail
LOG=/var/moo/logs/gexbot-hist-nightly.log
cd /root/projects/Strader
{
  echo "=== $(date -Is) gexbot-hist nightly start"
  .venv/bin/python scripts/gexbot_hist_backfill.py --ticker SPX --days 3
  rc=$?
  echo "=== $(date -Is) exit ${rc}"
} >> "$LOG" 2>&1
exit ${rc:-1}
