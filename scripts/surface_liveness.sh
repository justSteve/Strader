#!/usr/bin/env bash
# surface_liveness.sh — what is ACTUALLY running right now. [st-42mn]
#
#   bash scripts/surface_liveness.sh
#
# WHY THIS EXISTS. On 2026-08-05 Steve resubscribed GEXBot mid-afternoon. The
# agent spent the rest of the session telling him "we have no GEX" while the
# collector was writing to the corpus in the next tmux window. Nothing was
# broken and nobody was careless: the belief came from a memory file and a
# CurrentStatus line that were true when written.
#
# That is the SAME failure the tap-in skill already warns about for the beads
# export (co-vf9q): "plausible, well-formed, wrong data, which is worse than
# returning nothing." CurrentStatus.md is a CLAIM about the world. This is an
# OBSERVATION of it. Session rituals should open with the observation, and the
# operator should never have to remember to circle the agent in.
#
# Deliberately dependency-free (ps, ls, date) so it cannot itself be the thing
# that is down, and read-only so it is safe to run at any point in a session.

set -uo pipefail

REPO="${STRADER_REPO:-/root/projects/Strader}"
TODAY="$(TZ=America/Chicago date +%F)"
NOW="$(TZ=America/Chicago date '+%H:%M:%S %Z')"
DAY_DIR="$REPO/data/corpus/$TODAY"

printf 'SURFACE LIVENESS — observed %s (corpus day %s)\n\n' "$NOW" "$TODAY"
printf '%-22s %-8s %-10s %s\n' "SURFACE" "STATE" "UPTIME" "DETAIL"
printf '%s\n' "----------------------------------------------------------------------------"

probe() {           # probe <label> <pgrep-pattern> <detail>
    local label="$1" pat="$2" detail="${3:-}"
    local line pid et
    line="$(ps -eo pid=,etime=,args= | grep -F -- "$pat" | grep -v grep | head -1)"
    if [[ -n "$line" ]]; then
        pid="$(awk '{print $1}' <<<"$line")"
        et="$(awk '{print $2}' <<<"$line")"
        printf '%-22s %-8s %-10s %s\n' "$label" "UP" "$et" "pid $pid${detail:+ · $detail}"
    else
        printf '%-22s %-8s %-10s %s\n' "$label" "DOWN" "-" "${detail:-no process}"
    fi
}

fsize() {           # fsize <label> <path> [why-absent-is-normal]
    local label="$1" path="$2" note="${3:-}"
    if [[ -f "$path" ]]; then
        printf '%-22s %-8s %-10s %s\n' "$label" "present" \
            "$(date -r "$path" +%H:%M 2>/dev/null || echo -)" \
            "$(du -h "$path" 2>/dev/null | cut -f1) — $(basename "$path")"
    else
        printf '%-22s %-8s %-10s %s\n' "$label" "ABSENT" "-" \
            "$(basename "$path")${note:+ · $note}"
    fi
}

# The tmux server itself, FIRST — every surface below is hosted in it, so one
# server death reads as five independent failures unless this row is present.
# Observed 2026-08-05 ~19:56 CT: the moocity server died and took the GEX
# collector and the 90-day backfill with it. The script reported five DOWN
# rows and gave no hint they shared one cause. [st-p3lv]
if tmux -L moocity ls >/dev/null 2>&1; then
    printf '%-22s %-8s %-10s %s\n' "tmux moocity" "UP" "-" \
        "$(tmux -L moocity ls 2>/dev/null | wc -l) session(s) — hosts the surfaces below"
else
    printf '%-22s %-8s %-10s %s\n' "tmux moocity" "DOWN" "-" \
        "SOCKET ABSENT — every DOWN below is explained by this, not by 5 faults"
fi

probe "ES capture"        "corpus_stream_databento.py"  "trades + MBP-1"
probe "drill bridge"      "drill_bridge.py"             "127.0.0.1:7788"
probe "footprint feeder"  "live_footprint_feed.py"      "tails today's ES JSONL"
probe "GEX collector"     "corpus_poll_gexbot.py"       "SPX GEX -> corpus · the FEED is RTH-only (measured: first tick 08:30:02, last 15:00:33), so the collector is gated 08:30-15:05 CT weekdays, NYSE holidays off. DOWN outside that is NORMAL. Cron */2 restarts it — DOWN *inside* the window means the supervisor is failing too [st-p3lv]"
probe "MI gauge"          "mi_gauge"                    "cron-driven, usually DOWN between ticks"
probe "GEX hist backfill" "gexbot_hist_backfill.py"     "90-day harvest — only matters during the paid window (st-ox9x); delete this row when it completes"

printf '\n'
fsize "ES tape"      "$DAY_DIR/databento_glbx_es.jsonl"
fsize "MBP-1 quotes" "$DAY_DIR/databento_glbx_es_mbp1.jsonl"
fsize "GEX polls"    "$DAY_DIR/gexbot.jsonl"
fsize "MI gauge ticks"   "$DAY_DIR/mi_gauge_live.jsonl"
# internals.jsonl is written by the 06:30 T+1 corpus_daily cron, NOT during the
# session — so ABSENT is the NORMAL same-day state and was being read as an
# alarm at tap-in. The live intraday surface is mi_gauge_live.jsonl above.
fsize "internals (T+1)"  "$DAY_DIR/internals.jsonl" \
      "normal until tomorrow's 06:30 corpus_daily — not an alarm today"

printf '\n'
printf 'Read this OVER CurrentStatus.md where the two disagree: that file records\n'
printf 'what was true when someone last wrote it, this records what is true now.\n'
printf 'A surface can change mid-session without the agent being told.\n'
