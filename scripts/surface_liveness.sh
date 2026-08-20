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

# A LAUNCHER MENTIONS A SCRIPT WITHOUT RUNNING IT. [st-cc5k]
#
# Found 2026-08-14: this row read "ES capture UP · pid 133436 · uptime
# 1-23:03:08" for two days. 133436 was a leftover tmux CLIENT from 08-12 whose
# argv still carried the capture command line; it had outlived the window it
# created. The real capture was a different pid under systemd. Because the
# match was on script NAME and `head -1` takes the lowest pid, the stale client
# won — so if the systemd capture had died, this row would have stayed GREEN
# indefinitely. That day it was right by accident, which is exactly the
# "plausible, well-formed, wrong data" this file exists to end (header, above).
#
# Two defences, in order:
#   1. systemd is asked which pid IT started, wherever a unit exists. No argv
#      pattern can know that; the supervisor does.
#   2. The argv scan (for cron-driven surfaces with no unit) now drops anything
#      that spawns rather than runs.
# Every row reports which of the two answered, so a wrong green is diagnosable
# on sight rather than requiring a ps archaeology session.
LAUNCHER_RE='tmux|new-session|send-keys|surface_liveness\.sh'

ps_table() {        # indirected so the control case can inject a canned table
    if [[ -n "${LIVENESS_PS_FIXTURE:-}" ]]; then
        cat -- "$LIVENESS_PS_FIXTURE"
    else
        ps -eo pid=,etime=,args=
    fi
}

scan_argv() {       # scan_argv <pattern> -> "pid etime ..." or empty
    ps_table | grep -F -- "$1" | grep -Ev -- "$LAUNCHER_RE" | grep -v grep | head -1
}

unit_pid() {        # unit_pid <unit>... -> "pid unit" for the first active one
    command -v systemctl >/dev/null 2>&1 || return 0
    [[ -n "${LIVENESS_NO_SYSTEMD:-}" ]] && return 0
    local u state pid
    for u in "$@"; do
        state="$(systemctl show "$u" -p ActiveState --value 2>/dev/null || true)"
        [[ "$state" == "active" ]] || continue
        pid="$(systemctl show "$u" -p MainPID --value 2>/dev/null || true)"
        [[ -n "$pid" && "$pid" != "0" ]] || continue
        printf '%s %s\n' "$pid" "$u"
        return 0
    done
}

probe() {           # probe <label> <pattern> <detail> [unit...]
    local label="$1" pat="$2" detail="${3:-}"
    shift 3 2>/dev/null || shift $#
    local pid="" et="" src="" line u
    if (( $# > 0 )); then
        read -r pid u <<<"$(unit_pid "$@")"
        [[ -n "$pid" ]] && { et="$(ps -p "$pid" -o etime= 2>/dev/null | tr -d " ")"; src="$u"; }
    fi
    if [[ -z "$pid" ]]; then
        line="$(scan_argv "$pat")"
        if [[ -n "$line" ]]; then
            pid="$(awk '{print $1}' <<<"$line")"
            et="$(awk '{print $2}' <<<"$line")"
            src="argv scan"
        fi
    fi
    if [[ -n "$pid" ]]; then
        printf '%-22s %-8s %-10s %s\n' "$label" "UP" "${et:--}" \
            "pid $pid via $src${detail:+ · $detail}"
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

probe "ES capture"        "corpus_stream_databento.py"  "trades + MBP-1" \
      strader-capture.service strader-capture-early.service strader-capture-evening.service
probe "drill bridge"      "drill_bridge.py"             "127.0.0.1:7788 · systemd strader-drill-bridge.service since 2026-08-16 (st-n0qm.3); serves the page + /health/producers + /alerts" \
      strader-drill-bridge.service
probe "footprint feeder"  "live_footprint_feed.py"      "tails today's ES JSONL · systemd strader-footprint-feed.service, PartOf the bridge (st-n0qm.3); DayRolledOver = restart into the new day" \
      strader-footprint-feed.service
probe "GEX collector"     "corpus_poll_gexbot.py"       "SPX GEX -> corpus · the FEED is RTH-only (measured: first tick 08:30:02, last 15:00:33), so the collector is gated 08:30-15:05 CT weekdays, NYSE holidays off. DOWN outside that is NORMAL. systemd strader-gexbot.timer starts it 08:30 CT (st-pgfe, 2026-08-13; the */2 cron shim is gone) — DOWN *inside* the window means the unit is failing [st-p3lv]" \
      strader-gexbot.service
# The 1 Hz leg is a SEPARATE process from the collector above on purpose (own
# cadence, own quota economics, own supervisor) — and it had no row here for its
# first three live days. It was up, and this script could not have said so either
# way, which is the 2026-08-05 GEXBot blindness this file exists to end. [st-pfrz]
probe "GEX 1Hz orderflow" "corpus_poll_gexbot_orderflow_1s.py" "SPX orderflow at ~1 Hz -> corpus · same measured RTH gate as the collector above (08:30-15:05 CT weekdays, NYSE holidays off), so DOWN outside that is NORMAL. systemd strader-gexbot-orderflow-1s.timer starts it 08:30 CT (st-pgfe, 2026-08-13; the */2 cron shim is gone) — DOWN *inside* the window means the unit is failing [st-ipn0]" \
      strader-gexbot-orderflow-1s.service
# Supervised since 2026-08-16 06:20 CT (strader-orderflow-sentinel.service,
# st-2yuw / co-03ojd.7). Before that it was the only unsupervised live surface
# here: it died with the 08-11 reboot and again in the 08-15 OOM reset and stayed
# down until a human noticed. Still: no window explains a DOWN — it runs all day.
probe "OF sentinel"       "orderflow_sentinel.py"       "level-proximity alerts off the 1 Hz feed -> orderflow_alerts.jsonl + bridge /alerts (st-n0qm.9) · systemd strader-orderflow-sentinel.service; DOWN is ALWAYS actionable [st-igim]" \
      strader-orderflow-sentinel.service
probe "MI gauge"          "mi_gauge"                    "cron-driven, usually DOWN between ticks"
probe "GEX hist backfill" "gexbot_hist_backfill.py"     "nightly /hist harvest, cron 21:00 CT weekdays (st-mx42) — it runs for a few minutes after the close, so DOWN is NORMAL almost all day and this row is a permanent fixture, not a temporary one. The 'delete when the paid window completes' instruction this row used to carry pointed at st-ox9x, CANCELLED 2026-08-10; the surviving loose end is st-kr4a (files named .json.gz are plain JSON)"

# Producer HEALTH FILES [st-n0qm.3, Phase 2b/4]: each live producer writes its
# own heartbeat JSON; the bridge's /health/producers and the page's HUD dots
# read the same files. A process row can say UP while its loop is wedged; the
# health file's AGE is what says the loop is turning. Budgets match the bridge.
printf '\n'
hstat() {           # hstat <label> <path> <fresh_s> [why-absent-is-normal]
    local label="$1" path="$2" fresh="$3" note="${4:-}"
    if [[ ! -f "$path" ]]; then
        printf '%-22s %-8s %-10s %s\n' "$label" "ABSENT" "-" "$(basename "$path")${note:+ · $note}"
        return
    fi
    local age state status
    age=$(( $(date +%s) - $(date -r "$path" +%s) ))
    status="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('status') or d.get('state') or '-')" "$path" 2>/dev/null || echo '-')"
    # idle/quiet is a collector saying "outside my window" — neutral, like the
    # page's dots, not stale: stale is a producer that should be moving and is not.
    if   [[ "$status" == idle || "$status" == quiet ]]; then state="IDLE"
    elif (( age <= fresh ));     then state="FRESH"
    elif (( age <= fresh * 3 )); then state="AGING"
    else                              state="STALE"; fi
    printf '%-22s %-8s %-10s %s\n' "$label" "$state" "${age}s" "$(basename "$path") · status $status · budget ${fresh}s"
}
hstat "tape health"     "$REPO/data/corpus/_capture_health.json"     180 "written every 2 min by strader-health-assessors.timer (co-03ojd.7); STALE here means the health WRITER stopped, not the tape — check systemctl list-timers strader-health-assessors"
hstat "gex health"      "$REPO/data/corpus/_gexbot_health.json"      180 "same writer as tape health; idle outside 08:30-15:05 CT is normal"
hstat "1Hz gex health"  "$REPO/data/corpus/_gexbot_of1s_health.json" 180 "same writer as tape health; idle/quiet outside 08:30-15:05 CT is normal"
hstat "sentinel health" "$DAY_DIR/_sentinel_health.json"             90  "every 60 s while the sentinel runs (Phase 0)"
hstat "feed health"     "$DAY_DIR/_footprint_health.json"            90  "every push and every 30 s while waiting (Phase 2b)"

printf '\n'
fsize "ES tape"      "$DAY_DIR/databento_glbx_es.jsonl"
fsize "MBP-1 quotes" "$DAY_DIR/databento_glbx_es_mbp1.jsonl"
fsize "GEX polls"    "$DAY_DIR/gexbot.jsonl"
fsize "GEX 1Hz rows" "$DAY_DIR/gexbot_orderflow_1s.jsonl"
# Written only when the sentinel actually fires. A quiet market produces no file,
# so ABSENT here is a market state, not a fault — read it against the OF sentinel
# process row above, which is the row that says whether anything is watching.
fsize "OF alerts"    "$DAY_DIR/orderflow_alerts.jsonl" \
      "no alert has fired today — normal on a quiet tape, IF the sentinel row above says UP"
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
