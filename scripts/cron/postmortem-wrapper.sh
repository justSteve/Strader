#!/usr/bin/env bash
# postmortem-wrapper.sh — the day post-mortem, two passes. [co-7kgte]
#
#   30 15 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/postmortem-wrapper.sh same-day
#   27 8  * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/postmortem-wrapper.sh next-morning
#
# WHY TWO PASSES. At 15:30 the feeder is still writing the evening session into
# the same day file; the same-day page measures what is there and says so. At
# 08:27 the previous session is complete and that evening's Mancini letter has
# been parsed (08:15), so the morning pass re-measures the whole day and adds
# his recap. 08:27 keeps its own minute: 08:15 parse, 08:20 tracker, 08:25 risk.
#
# MORNING SMOKE. Before the next-morning pass, the previous session's
# <day>.json from its 15:30 pass must exist and parse; if not, that is an
# alert in its own right (the same-day cron did not run or died), and the pass
# still runs so the day is not lost.
#
# FAILURE. Non-zero exit → corpus_daily.emit_alert("postmortem", …) so it
# lands in the health log the morning heartbeat reads. rc=2 (no record) and
# rc=3 (renderer missing; ledger written) are distinguishable there.
#
# PATH IS SET EXPLICITLY — cron's minimal PATH [st-i68]. The desk renderer
# (COO desk-html.sh) needs `marked` (the Windows npm install) and `node`
# (nvm), and the plain-words gate inside it needs `claude` (~/.local/bin);
# each is appended only when its directory exists, so a missing one degrades
# to rc=3 / an untranslated page, never a bash error.
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
: "${HOME:=/root}"
export HOME
for extra in "$HOME/.local/bin" "$HOME"/.nvm/versions/node/*/bin /mnt/c/Users/steve/AppData/Roaming/npm; do
    [[ -d "$extra" ]] && PATH="$PATH:$extra"
done
export PATH

PASS="${1:-same-day}"
REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
LOG="${STRADER_LOG_DIR:-$REPO/logs}/postmortem.log"
mkdir -p "$(dirname "$LOG")"

alert() {  # $1 message, $2 pass, $3 rc
    PM_MSG="$1" PM_PASS="$2" PM_RC="$3" PYTHONPATH="$REPO" "$PY" - <<'PYEOF' || echo "WARN: alert emission failed"
import os, sys
sys.path.insert(0, os.path.join(os.environ["PYTHONPATH"], "scripts"))
from corpus_daily import emit_alert
emit_alert("postmortem", os.environ["PM_MSG"],
           {"pass": os.environ["PM_PASS"], "returncode": int(os.environ["PM_RC"])})
PYEOF
}

{
    echo "=== postmortem $PASS start $(date +%Y-%m-%dT%H:%M:%S%z) ==="
    if [[ ! -x "$PY" ]]; then echo "FATAL: venv python not executable: $PY"; exit 1; fi
    cd "$REPO" || { echo "FATAL: repo dir missing: $REPO"; exit 1; }

    if [[ "$PASS" == "next-morning" ]]; then
        PREV=$(PYTHONPATH="$REPO" "$PY" -c 'from market.corpus.paths import most_recent_session_day; print(most_recent_session_day())')
        if ! PYTHONPATH="$REPO" "$PY" -c "import json; json.load(open('data/measurement/postmortem/$PREV.json'))" 2>/dev/null; then
            echo "SMOKE: data/measurement/postmortem/$PREV.json missing or unreadable — the 15:30 pass did not land"
            alert "same-day post-mortem for $PREV never landed (no <day>.json); the morning pass is running anyway" smoke 0
        fi
    fi

    PYTHONPATH="$REPO" "$PY" "$REPO/scripts/postmortem_day.py" --pass "$PASS"
    rc=$?
    echo "=== postmortem $PASS end $(date +%Y-%m-%dT%H:%M:%S%z) (rc=$rc) ==="
    if (( rc != 0 )); then
        case $rc in
            2) why="no feeder record for the day (page written saying so)" ;;
            3) why="desk renderer missing or failed — ledger written, page not rendered" ;;
            *) why="unexpected failure; see logs/postmortem.log" ;;
        esac
        alert "day post-mortem $PASS pass rc=$rc: $why" "$PASS" "$rc"
    fi
    exit $rc
} >> "$LOG" 2>&1
