#!/usr/bin/env bash
# Event watch for scripts/live_effort_effect.py — the wake tier of the two-tier
# emitter. [st-85dv, st-dgwj]
#
# WHAT CHANGED, AND WHY. This replaces tools/effort_digest_watch.sh, which woke
# a model every 300 seconds whether or not anything had happened — about 276
# wakes a day, almost all of them on minutes where the honest report was
# "nothing". The 2026-08-24 audit showed what that bought: routine minutes
# consumed the budget while the events that mattered went unremarked, because
# noticing depended on model attention rather than on the instrument.
#
# So the scorer now detects events itself (market/orderflow/tape_events.py) and
# marks each one sig=alert or sig=note. This watch wakes on ALERTS ONLY.
# Measured over two real sessions: 17 and 10 alert-grade events inside RTH,
# against 276 clock wakes. A quiet tape now costs nothing at all.
#
# EVERY STDOUT LINE IS A MODEL WAKE. That is the whole economics of this file,
# so the filter is deliberately narrow and everything here is about not emitting:
#
#   - only sig=alert events wake anyone; sig=note lines stay in the log as
#     context for whoever is already awake;
#   - alerts arriving together are BATCHED into one wake, because a climax and
#     the level acceptance it caused are one situation, not two;
#   - each wake carries the graded bar that produced it, so the analyst does not
#     have to go and read the log to know what the tape was doing.
#
# SILENCE IS NOT SUCCESS. A dead scorer looks exactly like a quiet tape, and a
# watch that only ever reports good news would stay silent through a crash. So
# liveness is checked on its own timer regardless of event flow, and fault
# signatures in the log go out verbatim and immediately.
#
# Usage: bash tools/effort_event_watch.sh <logfile> [liveness_interval_s] [batch_gap_s]
set -u

LOG="${1:?usage: effort_event_watch.sh <logfile> [liveness_interval] [batch_gap]}"
LIVENESS="${2:-600}"      # how often to assert the scorer is alive and writing
BATCH_GAP="${3:-20}"      # alerts within this gap of each other are one wake
FAULT='Traceback|Error|error:|gave up|reconnect|DayRolledOver|Killed|OOM'

now_ct() { TZ=America/Chicago date +'%H:%M CT'; }

# The last graded bar seen, so a wake can carry its own context.
last_bar=""
# Pending alert batch.
batch=()
last_alert_epoch=0

flush_batch() {
    [ ${#batch[@]} -eq 0 ] && return
    if [ ${#batch[@]} -eq 1 ]; then
        echo "[TAPE] ${batch[0]}"
    else
        echo "[TAPE] ${#batch[@]} events: ${batch[0]}"
        local i
        for ((i = 1; i < ${#batch[@]}; i++)); do echo "        + ${batch[$i]}"; done
    fi
    [ -n "$last_bar" ] && echo "        bar: $last_bar"
    batch=()
}

echo "event watch armed on $(basename "$LOG") — waking on sig=alert only" \
     "(liveness ${LIVENESS}s, batch gap ${BATCH_GAP}s)"

# -n0: start at the END of the file. A cutover replays the morning through the
# scorer, and those events are history — re-emitting them would wake the analyst
# once per past event the moment it arms.
# -F: survive rotation at the midnight roll.
tail -n0 -F "$LOG" 2>/dev/null | {
    idle_ticks=0
    while true; do
        # A short read timeout is the batch clock AND the liveness clock: it
        # ticks whether or not the tape is moving.
        if IFS= read -t 5 -r line; then
            # Faults go out immediately and alone — they are not tape events.
            if printf '%s' "$line" | command grep -qE "$FAULT"; then
                flush_batch
                echo "[ALERT] scorer: $line"
                continue
            fi
            # Remember the most recent graded bar as context for the next wake.
            case "$line" in
                [0-9][0-9]:[0-9][0-9]" CT  F"[1-4]*) last_bar="$line" ;;
            esac
            # The only thing that wakes anybody.
            case "$line" in
                *" EVENT "*"sig=alert"*)
                    batch+=("$line")
                    last_alert_epoch=$(date +%s)
                    ;;
            esac
        else
            # read timed out: nothing arrived in the last 5s.
            idle_ticks=$((idle_ticks + 1))

            if [ ${#batch[@]} -gt 0 ]; then
                gap=$(( $(date +%s) - last_alert_epoch ))
                [ "$gap" -ge "$BATCH_GAP" ] && flush_batch
            fi

            if [ $((idle_ticks * 5)) -ge "$LIVENESS" ]; then
                idle_ticks=0
                pid=$(pgrep -f 'live_effort_effect.py' | head -1)
                if [ -z "$pid" ]; then
                    echo "[ALERT] $(now_ct) live_effort_effect.py NOT RUNNING — no pid matches"
                elif [ ! -f "$LOG" ]; then
                    echo "[ALERT] $(now_ct) log $LOG disappeared (scorer pid $pid alive)"
                else
                    age=$(( $(date +%s) - $(stat -c %Y "$LOG" 2>/dev/null || echo 0) ))
                    if [ "$age" -gt "$LIVENESS" ]; then
                        echo "[ALERT] $(now_ct) scorer pid $pid alive but log has not been written for ${age}s"
                    fi
                fi
            fi
        fi
    done
}
