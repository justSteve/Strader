#!/usr/bin/env bash
# footprint-icm-wrapper.sh — the audit lane's daily run, 15:40 CT Mon-Fri. [st-l3z8]
#
#   40 15 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/footprint-icm-wrapper.sh
#
# The line above is rendered from COO/SCHEDULE.md (entry strader-footprint-icm)
# by schedule-generate.sh --install — never a hand crontab line (finding
# ops-cost-2 of the ICM trial). Steve's Go: recommended in the trial reply of
# 2026-08-29; silence took it 2026-08-30.
#
# WHAT IT DOES. Runs footprint-icm/run_day.sh for today's session (regular
# hours 08:30-15:00 CT are fully captured by 15:05; the 15:06 evening capture
# is the entry this one is declared after). run_day.sh stops at the first
# failed check and exits 2 on a refusal, 1 on a crash; every stage writes its
# record into /var/moo/state/footprint-icm/<day>/run.json and the page lands
# at /var/moo/desk/desk-footprint-icm-<day>.html.
#
# FAILURE. Non-zero exit -> corpus_daily.emit_alert("footprint-icm", ...) so it
# lands in data/corpus/_health.jsonl, which the morning heartbeat reads. A
# holiday produces rc=2 (no live record for the day) and one alert line — the
# same honest failure the postmortem wrapper reports.
#
# HEARTBEAT. Every exit writes /var/moo/state/strader-footprint-icm.json
# ({ts, status, detail, day, rc}) so /tap-in's HEARTBEATS check sees a stale or
# failed run without anyone reading a log. Two hazards this covers, both on the
# record from the trial: the no-screen `claude -p` buffers its output until it
# exits, and the retired Drive sync saw mid-run deaths — so a run that never
# reaches the end still leaves a "started" heartbeat with status "running",
# which the check reports as not ok.
#
# TIMEOUT. The two model stages run once per delivered wake plus once for the
# window; a hung call would hold the cron slot forever. `timeout` bounds the
# whole run (default 60 min, ICM_TIMEOUT_SECS) and rc=124 is alerted as such.
#
# NO MARGINAL CHARGE. The model calls go through `claude -p` on Steve's Pro
# plan (plan quota, not a bill); usage.json's dollar figure is a list-price
# equivalent, a size-of-run number only.
#
# PATH IS SET EXPLICITLY — cron's minimal PATH [st-i68]: `claude` lives in
# ~/.local/bin and the desk renderer needs node; each is appended only when
# its directory exists.
#
# Env overrides (tests): STRADER_REPO, STRADER_PY, ICM_RUN_DAY (the run_day
# script), ICM_DAY (YYYY-MM-DD), ICM_HEARTBEAT, ICM_LOG_DIR, ICM_TIMEOUT_SECS.
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
: "${HOME:=/root}"
export HOME
for extra in "$HOME/.local/bin" "$HOME"/.nvm/versions/node/*/bin /mnt/c/Users/steve/AppData/Roaming/npm; do
    [[ -d "$extra" ]] && PATH="$PATH:$extra"
done
export PATH

REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
RUN_DAY="${ICM_RUN_DAY:-$REPO/footprint-icm/run_day.sh}"
DAY="${ICM_DAY:-$(TZ=America/Chicago date +%Y-%m-%d)}"
HB="${ICM_HEARTBEAT:-/var/moo/state/strader-footprint-icm.json}"
LOG_DIR="${ICM_LOG_DIR:-$REPO/logs/footprint-icm}"
TIMEOUT_SECS="${ICM_TIMEOUT_SECS:-3600}"
LOG="$LOG_DIR/$DAY.log"
mkdir -p "$LOG_DIR" "$(dirname "$HB")"

write_hb() {  # status, detail, rc
    printf '{"ts": "%s", "status": "%s", "detail": "%s", "day": "%s", "rc": %s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${2//\"/\\\"}" "$DAY" "$3" > "$HB.tmp" && mv -f "$HB.tmp" "$HB"
}

alert() {  # message, rc
    ICM_MSG="$1" ICM_RC="$2" ICM_DAY_="$DAY" PYTHONPATH="$REPO" "$PY" - <<'PYEOF' || echo "WARN: alert emission failed"
import os, sys
sys.path.insert(0, os.path.join(os.environ["PYTHONPATH"], "scripts"))
from corpus_daily import emit_alert
emit_alert("footprint-icm", os.environ["ICM_MSG"],
           {"day": os.environ["ICM_DAY_"], "returncode": int(os.environ["ICM_RC"])})
PYEOF
}

{
    echo "=== footprint-icm $DAY start $(date +%Y-%m-%dT%H:%M:%S%z) ==="
    if [[ ! -x "$PY" ]]; then
        echo "FATAL: venv python not executable: $PY"; write_hb failed "venv python missing at $PY" 1; exit 1
    fi
    if [[ ! -f "$RUN_DAY" ]]; then
        echo "FATAL: run_day script missing: $RUN_DAY"; write_hb failed "run_day.sh missing at $RUN_DAY" 1
        alert "audit lane entry point missing at $RUN_DAY" 1; exit 1
    fi
    cd "$REPO" || { echo "FATAL: repo dir missing: $REPO"; write_hb failed "repo missing at $REPO" 1; exit 1; }

    write_hb running "started $(date -u +%H:%MZ); no end record yet" 0
    timeout "$TIMEOUT_SECS" /usr/bin/bash "$RUN_DAY" "$DAY"
    rc=$?
    echo "=== footprint-icm $DAY end $(date +%Y-%m-%dT%H:%M:%S%z) (rc=$rc) ==="
    if (( rc == 0 )); then
        write_hb ok "run complete; page desk-footprint-icm-$DAY.html" 0
    else
        case $rc in
            2)   why="a stage refused (no live record for the day, or a check failed) — see run.log" ;;
            124) why="timed out after ${TIMEOUT_SECS}s — a model stage hung" ;;
            *)   why="unexpected failure; see $LOG" ;;
        esac
        write_hb failed "rc=$rc: $why" "$rc"
        alert "footprint-icm run for $DAY rc=$rc: $why" "$rc"
    fi
    exit $rc
} >> "$LOG" 2>&1
