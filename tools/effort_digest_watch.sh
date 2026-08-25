#!/usr/bin/env bash
# SUPERSEDED 2026-08-25 by tools/effort_event_watch.sh [st-85dv] — do not arm this.
# It wakes on a 300-second clock (~276 wakes/day, almost all of them "nothing");
# the replacement wakes only on sig=alert EVENT lines the scorer detects itself.
# Kept as the record of what the clock tier was, and for a log with no EVENT lines
# (a scorer older than st-dgwj). Contract: docs/playbooks/emitter-two-tier.md.
#
# Digest watch for scripts/live_effort_effect.py [st-2nyb].
#
# Emits one compact digest line per interval summarising the new scorer bars,
# plus an immediate line for any error/reconnect signature and for scorer death.
# Each stdout line is a Monitor event, so the filter is deliberately narrow.
#
# Usage: bash tools/effort_digest_watch.sh <logfile> [interval_seconds]
set -u

LOG="${1:?usage: effort_digest_watch.sh <logfile> [interval]}"
INTERVAL="${2:-300}"
PATTERN='Traceback|Error|error:|gave up|reconnect|DayRolledOver|Killed|OOM'

offset=$(wc -c < "$LOG" 2>/dev/null || echo 0)
echo "digest watch armed on $(basename "$LOG") at byte $offset, ${INTERVAL}s cadence"

while true; do
    sleep "$INTERVAL"

    # --- liveness first: a dead scorer looks exactly like a quiet tape ---
    pid=$(pgrep -f 'live_effort_effect.py' | head -1)
    if [ -z "$pid" ]; then
        echo "[ALERT] $(TZ=America/Chicago date +'%H:%M CT') live_effort_effect.py NOT RUNNING — no pid matches"
        continue
    fi

    if [ ! -f "$LOG" ]; then
        echo "[ALERT] $(TZ=America/Chicago date +'%H:%M CT') log $LOG disappeared (scorer pid $pid alive)"
        continue
    fi

    size=$(wc -c < "$LOG")
    if [ "$size" -lt "$offset" ]; then offset=0; fi   # log rotated/truncated
    chunk=$(tail -c +$((offset + 1)) "$LOG")
    offset=$size

    if [ -z "$chunk" ]; then
        echo "[ALERT] $(TZ=America/Chicago date +'%H:%M CT') scorer pid $pid alive but log SILENT for ${INTERVAL}s"
        continue
    fi

    # --- anything that smells like a fault goes out verbatim ---
    printf '%s\n' "$chunk" | command grep -E "$PATTERN" | while IFS= read -r line; do
        echo "[ALERT] scorer: $line"
    done

    # --- the digest itself ---
    printf '%s\n' "$chunk" | command grep -E '^[0-9]{2}:[0-9]{2} CT +F[1-4] ' | awk -v now="$(TZ=America/Chicago date +'%H:%M CT')" '
    {
        n++
        t = $1
        if (first == "") first = t
        last = t
        if (match($0, /F[1-4]/))            f = substr($0, RSTART, RLENGTH)
        cnt[f]++
        if (match($0, /h[0-9.]+/))          { h = substr($0, RSTART+1, RLENGTH-1) + 0; if (hi == "" || h > hi) hi = h }
        if (match($0, /l[0-9.]+/))          { l = substr($0, RSTART+1, RLENGTH-1) + 0; if (lo == "" || l < lo) lo = l }
        if (match($0, /c[0-9.]+ /))         c = substr($0, RSTART+1, RLENGTH-2) + 0
        if (match($0, / vol [0-9]+/))       v += substr($0, RSTART+5, RLENGTH-5) + 0
        if (match($0, / d[+-][0-9]+/))      d += substr($0, RSTART+2, RLENGTH-2) + 0
        if (match($0, /grade [0-9.]+/))     { g = substr($0, RSTART+6, RLENGTH-6) + 0
                                              if (g > topg) { topg = g; topt = t; topf = f } }
    }
    END {
        if (n == 0) exit
        printf "%s digest n=%d (%s-%s)", now, n, first, last
        for (i = 1; i <= 4; i++) printf " F%d:%d", i, cnt["F" i] + 0
        printf " | ES %.2f-%.2f c%.2f | vol %d d%+d | max grade %.2f %s@%s\n", lo, hi, c, v, d, topg, topf, topt
    }'
done
