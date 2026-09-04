#!/usr/bin/env bash
# gexbot_hist_nightly.sh — nightly gexbot /hist harvest [st-mx42]
# Idempotent: backfill skips files already present locally or on Z:.
# --days 3 self-heals evenings where the vendor hasn't published yet.
#
# Heartbeat [co-8b60y]: /var/moo/state/strader-gexbot-hist-nightly.json —
# running at start, ok/failed on exit by the trap scripts/cron/heartbeat-lib.sh
# arms. STRADER_REPO / STRADER_PY / STRADER_GEXBOT_HIST_LOG are test seams.
set -uo pipefail
REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
LOG="${STRADER_GEXBOT_HIST_LOG:-/var/moo/logs/gexbot-hist-nightly.log}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null
# shellcheck source=cron/heartbeat-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/cron/heartbeat-lib.sh"
hb_init "$(hb_path strader-gexbot-hist-nightly)" "hist harvest"
cd "$REPO" || { HB_DETAIL="repo missing at $REPO"; exit 2; }
{
  echo "=== $(date -Is) gexbot-hist nightly start"
  "$PY" scripts/gexbot_hist_backfill.py --ticker SPX --days 3
  rc=$?
  echo "=== $(date -Is) exit ${rc}"
} >> "$LOG" 2>&1
if (( ${rc:-1} == 0 )); then HB_DETAIL="SPX hist harvest complete (3 days, idempotent)"
else HB_DETAIL="backfill rc=${rc:-1} — $LOG"; fi
exit "${rc:-1}"
