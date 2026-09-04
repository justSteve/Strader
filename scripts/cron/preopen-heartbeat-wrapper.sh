#!/usr/bin/env bash
# preopen-heartbeat-wrapper.sh — Runbook #11: did pull/parse/gate run before the open. [st-66u]
#
#   25 8 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/preopen-heartbeat-wrapper.sh
#
# Cron runs local America/Chicago time. 08:25 CT is deliberate: after the 08:15
# Mancini parse has had its window and the 07:00 schwab premarket fire is long
# past, five minutes before the 08:30 bell — late enough to judge everything,
# early enough that a FAILED verdict still reaches Steve pre-open.
#
# The check itself (runbook/heartbeat.py) emits the alert on failure — this
# wrapper only hosts it under cron and keeps the log. A wrapper that failed to
# even start the check is its own alert case, handled below the same way.

set -uo pipefail

STRADER_REPO="${STRADER_REPO:-/root/projects/Strader}"
STRADER_VENV="${STRADER_VENV:-$STRADER_REPO/.venv}"
PY="$STRADER_VENV/bin/python"

: "${HOME:=/root}"
export HOME

LOG_DIR="${STRADER_HEARTBEAT_LOGDIR:-/var/moo/logs/preopen-heartbeat}"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# Heartbeat [co-8b60y]: /var/moo/state/strader-preopen-heartbeat.json — this
# job's own liveness, distinct from the pre-open assertion it runs. Written on
# every exit by the trap heartbeat-lib.sh arms; rc 1 (the check ran and found
# a failure) and rc 2 (the check itself broke) both read failed with the reason.
# shellcheck source=heartbeat-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/heartbeat-lib.sh"
hb_init "$(hb_path strader-preopen-heartbeat)" "pre-open assertion"

{
    log "=== preopen-heartbeat start $(date +%Y-%m-%dT%H:%M:%S%z) ==="

    if [[ ! -x "$PY" ]]; then
        log "FATAL: venv python not executable: $PY"; exit 2
    fi

    cd "$STRADER_REPO" || { log "FATAL: repo dir missing: $STRADER_REPO"; exit 2; }

    # Day-start risk reset first [st-958] — idempotent, so a re-fire never
    # clobbers a day that already carries recorded trades. Its failure does not
    # stop the heartbeat below; the heartbeat's risk check is what reports it.
    PYTHONPATH="$STRADER_REPO" "$PY" -m runbook.risk_state reset \
        || log "WARN: risk-state reset failed (heartbeat will flag it)"

    PYTHONPATH="$STRADER_REPO" "$PY" -m runbook.heartbeat
    rc=$?
    log "=== preopen-heartbeat end (rc=$rc) ==="

    if (( rc == 2 )); then
        # rc 1 = check ran and already alerted; rc 2 = the check itself broke.
        HB_RC="$rc" PYTHONPATH="$STRADER_REPO" "$PY" - <<'PYEOF' || log "WARN: alert emission failed"
import os
import sys

sys.path.insert(0, os.path.join(os.environ["PYTHONPATH"], "scripts"))
from corpus_daily import emit_alert

emit_alert(
    "preopen_heartbeat",
    "Pre-open heartbeat could not run (infrastructure failure) — liveness of "
    "this morning's artifacts is UNKNOWN. Verify pull/parse/gate by hand.",
    {"returncode": int(os.environ["HB_RC"]), "source": "preopen-heartbeat-wrapper"},
)
PYEOF
    fi

    case $rc in
        0) HB_DETAIL="pull, parse and gate all present before the bell" ;;
        1) HB_DETAIL="the pre-open check found a failure (alert in data/corpus/_health.jsonl) — $LOG" ;;
        *) HB_DETAIL="the pre-open check itself could not run (rc=$rc) — $LOG" ;;
    esac
    exit $rc
} >> "$LOG" 2>&1
