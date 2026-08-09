#!/usr/bin/env bash
# live-parity-wrapper.sh — did yesterday's live session emit what a replay of
# its tape recomputes? [st-x2mp, closes st-d5f AC#4]
#
#   10 16 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/live-parity-wrapper.sh
#
# NOT YET INSTALLED IN CRON. Add the line above by hand — a new scheduled job on
# a box running live capture is something a human should have seen arrive.
#
# WHY 16:10 CT. The cash close is 15:00 and the feeder keeps running past it;
# waiting until the tape has stopped and the feeder has written its `end` marker
# means the day's LAST run is complete, which is the run the checker prefers. It
# is deliberately NOT after the 07:30 compaction — the checker reads a packed
# day fine (resolve_existing), but running the same evening means a divergence
# is reported while the capture log for that session is still fresh.
#
# WHAT A FAILURE MEANS. Not "the engine is wrong": the live feeder and the
# replay drive the SAME StackDriver through the SAME live_drive loop, so a
# difference is never a difference of logic. It means the two sides did not see
# the same trades in the same order — the live path holds rows for
# --reorder-lag seconds and releases them in order, the replay sorts the whole
# file by (ts, sequence), and a reconnect redelivering rows staler than the lag
# is the known way for those to part company. The report names the first
# divergent bar; its timestamp is where to look in the capture log.
#
# WHAT AN [ALERT]-WORTHY RESULT LOOKS LIKE. rc=1. rc=2 is "could not check"
# (no run log, no tape) and is a gap in evidence rather than a divergence —
# still worth knowing, because a session run with --no-run-log can never be
# checked afterwards.
#
# PATH IS SET EXPLICITLY [st-i68]. Cron's minimal PATH is why the 2026-07-24
# Mancini batch died on a bare `FileNotFoundError`.
set -uo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
LOG_DIR="${STRADER_PARITY_LOGDIR:-/var/moo/logs/live-parity}"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

{
    echo "=== live-parity start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

    if [[ ! -x "$PY" ]]; then
        echo "FATAL: venv python not executable: $PY"
        exit 2
    fi
    cd "$REPO" || { echo "FATAL: repo dir missing: $REPO"; exit 2; }

    # No --date: the checker resolves the most recent session day itself, the
    # same helper corpus-daily and corpus-compact target, so the three jobs
    # cannot drift onto different days.
    PYTHONPATH="$REPO" "$PY" "$REPO/scripts/live_parity_check.py"
    rc=$?

    case $rc in
        0) echo "PASS — the replay reproduced the live run" ;;
        1) echo "ALERT: live/replay DIVERGED — see the first divergent bar above" ;;
        2) echo "could not check — no run log or no tape for the day" ;;
        *) echo "unexpected rc=$rc" ;;
    esac

    echo "=== live-parity end $(date -u +%Y-%m-%dT%H:%M:%SZ) (rc=$rc) ==="
    exit $rc
} >>"$LOG" 2>&1
