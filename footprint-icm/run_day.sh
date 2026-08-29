#!/usr/bin/env bash
# run_day.sh — the audit lane's only entry point. [st-h0xx]
#
# Usage: bash footprint-icm/run_day.sh <YYYY-MM-DD> [--no-publish]
#
# Runs the stages that exist, in order, and stops at the first refusal:
#   00  inputs.py     replay the day, check it against the live log, snapshot
#                     the anchor set, regenerate the log body
#   00  live_lane.py  what the live analyst was shown and said, from the
#                     transcript; asserts the wake set against the rule
#   40  compare.py    the page (number check; classes once the model stages
#                     exist)
# Every stage writes its record into /var/moo/state/footprint-icm/<day>/run.json.
# Exit 0 on a full run; 2 on a refusal (the stage names the check); 1 on a
# crash. Prints one line per stage and a final verdict line.
set -uo pipefail

DAY="${1:?usage: run_day.sh <YYYY-MM-DD> [--no-publish]}"
shift || true
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(dirname "$HERE")"
PY="$ROOT/.venv/bin/python"
RUN="/var/moo/state/footprint-icm/$DAY"
LOGF="$RUN/run.log"
mkdir -p "$RUN"

stage() {
    local name="$1"; shift
    echo "== $name" | tee -a "$LOGF"
    if ! "$@" 2>>"$LOGF" | tee -a "$LOGF"; then
        local rc=${PIPESTATUS[0]}
        echo "STOPPED at $name (rc=$rc) — see $LOGF" | tee -a "$LOGF"
        tail -3 "$LOGF" | command grep -E '^\[REFUSED\]' >&2 || true
        exit "$rc"
    fi
}

echo "footprint-icm run $DAY $(TZ=America/Chicago date '+%Y-%m-%d %H:%M CT')" >> "$LOGF"
stage 00-inputs   "$PY" "$HERE/bin/inputs.py" "$DAY"
stage 00-live     "$PY" "$HERE/bin/live_lane.py" "$DAY"
stage 40-compare  "$PY" "$HERE/bin/compare.py" "$DAY" "$@"
echo "done $DAY — run.json: $RUN/run.json; page: /var/moo/desk/desk-footprint-icm-$DAY.html" | tee -a "$LOGF"
