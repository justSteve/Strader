#!/usr/bin/env bash
# health_assessors.sh — write the three collector health verdicts. [co-03ojd.7 J-F1]
#
# Runs scripts/capture_health.py once per collector so the three state files the
# live-monitoring registry names AUTHORITATIVE keep moving:
#
#     data/corpus/_capture_health.json      ES trades + MBP-1 (strader-capture.service)
#     data/corpus/_gexbot_health.json       GexBot 60 s poll   (strader-gexbot.service)
#     data/corpus/_gexbot_of1s_health.json  GexBot 1 Hz leg    (strader-gexbot-orderflow-1s.service)
#
# WHY THIS EXISTS. Until 2026-08-13 the */2 cron supervisors
# (scripts/cron/*-supervisor*.sh, pruned 2026-09-06 — tag pre-prune-2026-09-05) both relaunched
# the collectors and ran the assessor. st-pgfe moved the collectors into systemd
# units, which relaunch on failure by themselves — but nothing took over the
# assessor half, so all three files froze at 2026-08-13 and every reader
# (surface_liveness.sh, drill_bridge.py, the 08:25 pre-open heartbeat) saw a
# permanently stale file. A stale file looks the same as a healthy one that
# stopped being written; that is the failure the audit (COO enterprise audit
# 2026-08-15, sweep J, F1) found. This script is the assessor half, on its own
# clock: strader-health-assessors.timer fires it every 2 minutes, the cadence the
# readers were built for (they treat >180 s as stale).
#
# The arguments per collector are the ones the retired supervisors passed —
# ported verbatim from capture-supervisor-session.sh, gexbot-supervisor-session.sh
# and gexbot-orderflow-1s-supervisor.sh, all four pruned 2026-09-06 (tag pre-prune-2026-09-05)
# once this script had carried their arguments for three weeks — so the verdict
# semantics (window, venue calendar, stale threshold) are unchanged. THIS FILE is
# now where those arguments live; there is no second copy to drift against.
#
# Exit code: 0 unless an assessor itself broke (its rc=2). A DEAD/STALE verdict
# is the assessor's finding, written to the state file and the health log where
# the readers look; it is NOT this unit's failure. A failed unit therefore means
# exactly one thing — the health writer is broken — which is what
# `systemctl status strader-health-assessors` should tell you.
#
#     bash scripts/health_assessors.sh          # run all three, print each verdict line
#     bash scripts/health_assessors.sh --json   # print each verdict as JSON
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
CHECK="$REPO/scripts/capture_health.py"
CORPUS="$REPO/data/corpus"
FMT=()
[[ "${1:-}" == "--json" ]] && FMT=(--json)

worst=0
run_one() {  # run_one <label> <capture_health args...>
    local label="$1"; shift
    local out rc
    out="$(cd "$REPO" && PYTHONPATH="$REPO" "$PY" "$CHECK" "${FMT[@]}" "$@" 2>&1)"; rc=$?
    printf '[%s] rc=%d\n%s\n' "$label" "$rc" "$out"
    if (( rc == 2 )); then worst=2; fi
}

# ES capture runs the Globex day since 2026-08-18 [st-9olq] (early 00:00-02:50,
# session 02:50-15:05, evening 15:06-end of day / Fri 16:05); the clock window is
# the whole day and --venue globex supplies the pause, the maintenance halt, the
# Friday close and the Sunday reopen.
run_one "es capture" \
    --streams es,es-mbp1 --stale-secs 600 --grace-secs 180 --venue globex \
    --window-start 00:00 --window-end 23:59 \
    --match corpus_stream_databento.py \
    --state "$CORPUS/_capture_health.json"

run_one "gexbot 60s" \
    --streams gexbot --stale-secs 300 --grace-secs 180 --venue cash \
    --window-start 08:30 --window-end 15:05 \
    --match corpus_poll_gexbot.py \
    --state "$CORPUS/_gexbot_health.json"

run_one "gexbot 1Hz orderflow" \
    --streams gexbot_orderflow_1s --stale-secs 300 --grace-secs 180 --venue cash \
    --window-start 08:30 --window-end 15:05 \
    --match corpus_poll_gexbot_orderflow_1s.py \
    --state "$CORPUS/_gexbot_of1s_health.json"

exit "$worst"
