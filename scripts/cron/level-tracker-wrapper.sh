#!/usr/bin/env bash
# level-tracker-wrapper.sh — run the Mancini level-state tracker for the session. [st-qih1]
#
#   20 8 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/level-tracker-wrapper.sh
#
# Starts five minutes after the 08:15 prepare job and ten before the cash open.
# The tracker loop re-fetches the letter-window /ES candles once a minute,
# recomputes every level's touched/held/broken/reclaimed state (the same
# machine the overnight brief and Pine markers use), and atomically rewrites
# data/level_state/current.json. It exits on its own at 15:15 CT.
#
# LIFECYCLE GUARANTEES
# - No parse yet (Steve hasn't run /mancini-parse): the loop waits and logs;
#   the state file appears within a minute of the parse landing.
# - Double start (cron retry, manual run): the pidfile under data/level_state/
#   refuses a second loop; this wrapper exits 1 loudly instead of forking a twin.
# - Repeated fetch failures (Schwab token dead, etc.): one non-urgent alert per
#   streak via strader.alerts, keeps retrying; the state file simply goes stale.
# - Host slept through 15:15: the first tick after wake sees session end and
#   exits cleanly.
#
# Manual smoke (single tick, no loop, no clipboard/desk side effects):
#   PYTHONPATH=/root/projects/Strader /root/projects/Strader/.venv/bin/python \
#       -m runbook.mancini.tracker --once
# Replay a frozen day (the regression fixture):
#   ... -m runbook.mancini.tracker --replay runbook/mancini/tests/fixtures/candles-2026-08-05.json --day 2026-08-05

set -uo pipefail

STRADER_REPO="${STRADER_REPO:-/root/projects/Strader}"
STRADER_VENV="${STRADER_VENV:-$STRADER_REPO/.venv}"
PY="$STRADER_VENV/bin/python"

: "${HOME:=/root}"
export HOME

LOG_DIR="${STRADER_TRACKER_LOGDIR:-/var/moo/logs/level-tracker}"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

# Heartbeat [co-8b60y]: /var/moo/state/strader-level-tracker.json — `running`
# for the whole session loop (SCHEDULE.md max_run_min 480), ok/failed on exit
# by the trap heartbeat-lib.sh arms. Read by COO's heartbeat-check.sh.
# shellcheck source=heartbeat-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/heartbeat-lib.sh"
hb_init "$(hb_path strader-level-tracker)" "session loop"

{
    echo "[$(date +%H:%M:%S)] === level-tracker start $(date +%Y-%m-%dT%H:%M:%S%z) ==="
    if [[ ! -x "$PY" ]]; then
        echo "[$(date +%H:%M:%S)] FATAL: venv python not executable: $PY"; exit 2
    fi
    cd "$STRADER_REPO" || { echo "FATAL: repo dir missing: $STRADER_REPO"; exit 2; }

    PYTHONPATH="$STRADER_REPO" "$PY" -m runbook.mancini.tracker --loop "$@"
    rc=$?
    echo "[$(date +%H:%M:%S)] === level-tracker end (rc=$rc) ==="
    if (( rc == 0 )); then HB_DETAIL="session loop ended cleanly"
    else HB_DETAIL="tracker loop rc=$rc (1 = a second loop was refused, or the loop failed) — $LOG"; fi
    exit $rc
} >> "$LOG" 2>&1
