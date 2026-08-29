#!/usr/bin/env bash
# run_day.sh — the audit lane's only entry point. [st-h0xx]
#
# Usage: bash footprint-icm/run_day.sh <YYYY-MM-DD> [--no-publish] [--no-model]
#
# Runs the stages in order and stops at the first refusal:
#   00  inputs.py         replay the day, check it against the live log,
#                         snapshot the anchor set, regenerate the log body
#   00  live_lane.py      what the live analyst was shown and said, from the
#                         transcript; asserts the wake set against the rule
#   10  render_events.py  the events in plain words, per-wake slices (code)
#   20  excerpts.py       the classify stage's context folder from the source
#                         list, pinned to commits; then verified untouched
#   20  classify.py       the model labels each wake's slice and the window;
#                         the checker fails the run on any bad cite   [model]
#   40  claims.py         the model transcribes the live replies into CLAIM
#                         lines, and the planted fixture                [model]
#   40  compare.py        the classes and the page (code)
# --no-model skips the two model stages; the page then carries the live side
# and the number check only. Every stage writes its record into
# /var/moo/state/footprint-icm/<day>/run.json. Exit 0 on a full run; 2 on a
# refusal (the stage names the check); 1 on a crash.
set -uo pipefail

DAY="${1:?usage: run_day.sh <YYYY-MM-DD> [--no-publish] [--no-model]}"
shift || true
PUBLISH_ARGS=()
MODEL=1
for a in "$@"; do
    case "$a" in
        --no-publish) PUBLISH_ARGS+=("--no-publish") ;;
        --no-model)   MODEL=0 ;;
        *) echo "unknown flag $a" >&2; exit 1 ;;
    esac
done
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

echo "footprint-icm run $DAY $(TZ=America/Chicago date '+%Y-%m-%d %H:%M CT') model=$MODEL" >> "$LOGF"
stage 00-inputs      "$PY" "$HERE/bin/inputs.py" "$DAY"
stage 00-live        "$PY" "$HERE/bin/live_lane.py" "$DAY"
stage 10-transcribe  "$PY" "$HERE/bin/render_events.py" "$DAY"
stage 20-context     "$PY" "$HERE/bin/excerpts.py" "$DAY"
stage 20-verify      "$PY" "$HERE/bin/excerpts.py" --verify "$RUN"
if [ "$MODEL" = 1 ]; then
    stage 20-classify "$PY" "$HERE/bin/classify.py" "$DAY"
    stage 40-claims   "$PY" "$HERE/bin/claims.py" "$DAY"
fi
stage 40-compare     "$PY" "$HERE/bin/compare.py" "$DAY" "${PUBLISH_ARGS[@]}"
echo "done $DAY — run.json: $RUN/run.json; page: /var/moo/desk/desk-footprint-icm-$DAY.html" | tee -a "$LOGF"
