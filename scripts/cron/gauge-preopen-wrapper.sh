#!/usr/bin/env bash
# gauge-preopen-wrapper.sh — Keep the live MI gauge alive in tmux. [st-cm5]
#
# Fired on a 5-minute heartbeat cron across the session, this both LAUNCHES the
# gauge pre-open and RESPAWNS it if it dies mid-session. One idempotent script
# does both jobs: it launches only when no live gauge exists, and no-ops when
# one does.
#
#   */5 8-15 * * 1-5 /usr/bin/bash /root/projects/Strader/scripts/cron/gauge-preopen-wrapper.sh
#
# Cron here runs local America/Chicago time (no TZ override), so the window
# tracks the 08:30 open and rides DST automatically. First fire ≥08:00 brings
# the pane up pre-open (full-session cum-TICK spine); every later fire is a
# cheap no-op unless the gauge has died, in which case it respawns within 5 min.
#
# WHY A PANE THAT DIES IS NOT ENOUGH — STATE CONTINUITY. mi_gauge.py --live
# captures every synthetic minute to data/corpus/<date>/mi_gauge_live.jsonl and
# REPLAYS it on (re)launch, so a respawn continues the spine instead of
# resetting to cum=0 (which would run hot and be useless). The gauge is a
# deterministic pure function of its tick stream, so replay reconstructs the
# exact state; only minutes elapsed while the process was DOWN are lost
# (same-day $TICK is clamped and cannot backfill), and the gauge names that gap.
#
# IDEMPOTENT BY PROCESS, NOT BY WINDOW. On 2026-07-23 three windows were named
# `gauge` with only one live — the others had died down to a bash shell. A
# window named `gauge` is not proof of a live gauge. The guard is a python-comm
# filtered pgrep; when no live process exists, every stale `gauge` window is
# reaped before a fresh launch.
#
# SESSION WINDOW [st-5n8]. The gauge is a SESSION daemon, not a service. It
# self-exits at STRADER_GAUGE_SESSION_END (default 15:15 CT) and on a day
# rollover; this wrapper exports that same value so both agree on one number.
# Outside 08:00–15:15 CT Mon–Fri, "no gauge running" is the CORRECT state and
# this script exits 0 without launching. Before st-5n8 neither side had a stop
# condition, so the 7/24 launch ran 26h into Saturday and wrote 1269 dead rows.
# A gauge still alive outside the window is logged as a WARN — it is not killed
# from cron; that stays a human call.
#
# BOOTSTRAP (Steve-authorized 2026-07-23; upgraded under st-r3f). If the tmux
# session is down, bring up the REAL desk by invoking COO's own idempotent
# bootstrap (/root/projects/COO/tmuxMOO/bin/steves-desk-session.sh, honours
# TMUX_SOCKET, no-ops when the session exists) — cross-repo READ+invoke by
# absolute path is what COO's shared-executable-space convention prescribes. The
# gauge then lands in the actual working surface and nothing needs reconciling
# later. Only when that script is unavailable (or the session name is not
# steves-desk, the sole name it creates) do we fall back to the 7/23 behaviour:
# a MINIMAL session hosting just the gauge.
#
# Placement: a dedicated full-width window (the ~102-col render does not fit
# COO's 62/94 NAV/CONTENT split), inserted right after the Trading window when
# it exists, appended otherwise.
#
# Manual smoke (safe — idempotent no-op if a gauge is already live):
#   scripts/cron/gauge-preopen-wrapper.sh
#
# Test knobs (point bootstrap/reap/respawn at a scratch socket + stub process,
# exercising every path WITHOUT the moocity desk or the gated live Schwab API):
#   STRADER_TMUX_SOCKET  STRADER_TMUX_SESSION  STRADER_GAUGE_WIN
#   STRADER_ANCHOR_WIN   STRADER_GAUGE_MATCH   STRADER_GAUGE_LAUNCH
#   STRADER_DESK_BOOTSTRAP  STRADER_GAUGE_SESSION_START/_END
#   STRADER_GAUGE_NOW   (pretend it is 'YYYY-MM-DDTHH:MM' CT)

set -uo pipefail

STRADER_REPO="${STRADER_REPO:-/root/projects/Strader}"
STRADER_VENV="${STRADER_VENV:-$STRADER_REPO/.venv}"
PY="$STRADER_VENV/bin/python"
GAUGE_SCRIPT="scripts/mi_gauge.py"          # relative to repo root

# Overridable knobs (defaults = production).
SOCKET="${STRADER_TMUX_SOCKET:-moocity}"
SESSION="${STRADER_TMUX_SESSION:-steves-desk}"
WIN_NAME="${STRADER_GAUGE_WIN:-gauge}"
ANCHOR_WIN="${STRADER_ANCHOR_WIN:-Trading}"
GAUGE_MATCH="${STRADER_GAUGE_MATCH:-mi_gauge.py --live}"
GAUGE_LAUNCH_CMD="${STRADER_GAUGE_LAUNCH:-exec $PY $STRADER_REPO/$GAUGE_SCRIPT --live}"

# Session window (CT). Exported so the launched gauge self-exits on the same
# number this wrapper stops respawning on — one source of truth, no drift.
SESSION_START="${STRADER_GAUGE_SESSION_START:-08:00}"
SESSION_END="${STRADER_GAUGE_SESSION_END:-15:15}"
export STRADER_GAUGE_SESSION_END="$SESSION_END"

# COO's real desk bootstrap [st-r3f]; idempotent, honours TMUX_SOCKET.
DESK_BOOTSTRAP="${STRADER_DESK_BOOTSTRAP:-/root/projects/COO/tmuxMOO/bin/steves-desk-session.sh}"
DESK_SESSION_NAME="steves-desk"   # the only session name that script creates

TMUX=(tmux -L "$SOCKET")

: "${HOME:=/root}"
export HOME

LOG_DIR="${STRADER_GAUGE_LOGDIR:-/var/moo/logs/gauge-preopen}"
mkdir -p "$LOG_DIR" 2>/dev/null
DATE="$(date +%Y-%m-%d)"
LOG="$LOG_DIR/$DATE.log"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# Heartbeat [co-8b60y]: /var/moo/state/strader-gauge-preopen.json — one per
# 5-minute tick, ok/failed on exit by the trap heartbeat-lib.sh arms. The
# cadence check knows the 8-15 Mon-Fri window, so a quiet weekend is not stale.
# shellcheck source=heartbeat-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/heartbeat-lib.sh"
hb_init "$(hb_path strader-gauge-preopen)" "supervision tick"

hm_to_min() { local h=${1%%:*} m=${1##*:}; echo $(( 10#$h * 60 + 10#$m )); }

# Session clock. Cron runs local America/Chicago, but the zone is forced so the
# guard is still right when invoked from a differently-zoned shell. Tests set
# STRADER_GAUGE_NOW='YYYY-MM-DDTHH:MM' to pin a moment (weekend, post-close…).
if [[ -n "${STRADER_GAUGE_NOW:-}" ]]; then
    NOW_HM="$(TZ=America/Chicago date -d "$STRADER_GAUGE_NOW" +%H:%M 2>/dev/null)"
    NOW_DOW="$(TZ=America/Chicago date -d "$STRADER_GAUGE_NOW" +%u 2>/dev/null)"
    [[ -z "$NOW_HM" ]] && { echo "FATAL: unparseable STRADER_GAUGE_NOW='$STRADER_GAUGE_NOW'" >&2; exit 2; }
else
    NOW_HM="$(TZ=America/Chicago date +%H:%M)"
    NOW_DOW="$(TZ=America/Chicago date +%u)"
fi
IN_SESSION=0
if (( NOW_DOW <= 5 )) \
   && (( $(hm_to_min "$NOW_HM") >= $(hm_to_min "$SESSION_START") )) \
   && (( $(hm_to_min "$NOW_HM") <  $(hm_to_min "$SESSION_END") )); then
    IN_SESSION=1
fi

# Live-gauge PIDs, restricted to actual python processes. A bare `pgrep -f
# 'mi_gauge.py --live'` also matches any shell/grep/editor whose command line
# merely mentions the string — a false positive there makes the guard skip the
# launch and lose the session, the very failure this wrapper exists to prevent.
# Filtering on comm=python* excludes those. (Tests override GAUGE_MATCH and
# launch a python stub so this filter still applies.)
live_gauge_pids() {
    local p comm
    for p in $(pgrep -f "$GAUGE_MATCH" 2>/dev/null); do
        comm="$(ps -o comm= -p "$p" 2>/dev/null)"
        case "$comm" in python*|*/python*) echo "$p" ;; esac
    done
}

{
    log "=== gauge-preopen start $(date +%Y-%m-%dT%H:%M:%S%z) socket=$SOCKET session=$SESSION ==="

    # --- preflight -------------------------------------------------------
    if [[ ! -x "$PY" ]]; then
        log "FATAL: venv python not executable: $PY"; exit 2
    fi
    if [[ ! -f "$STRADER_REPO/$GAUGE_SCRIPT" ]]; then
        log "FATAL: gauge script missing: $STRADER_REPO/$GAUGE_SCRIPT"; exit 2
    fi

    # --- idempotency guard: PROCESS, not window --------------------------
    LIVE_PIDS="$(live_gauge_pids | tr '\n' ' ')"
    if [[ -n "${LIVE_PIDS// }" ]]; then
        if (( IN_SESSION )); then
            log "OK: live gauge already running (pid ${LIVE_PIDS%% })— nothing to do."
            HB_DETAIL="live gauge running (pid ${LIVE_PIDS%% })"
        else
            HB_DETAIL="gauge still running (pid ${LIVE_PIDS%% }) outside the window — not killed from cron"
            log "WARN: gauge still running (pid ${LIVE_PIDS%% }) at $NOW_HM CT (dow $NOW_DOW), OUTSIDE the $SESSION_START–$SESSION_END window — it should have self-exited at $SESSION_END. Not killing from cron; that is Steve's call. A pre-st-5n8 process has no stop condition and will run until killed."
        fi
        exit 0
    fi

    # --- outside the session window, NOT running is CORRECT [st-5n8] -----
    # The cron line fires on a dumb heartbeat; the judgement lives here. No
    # gauge outside 08:00–15:15 CT Mon–Fri is the desired state, not a fault to
    # respawn away — there is nothing to measure on a closed tape, and a launch
    # here is what produced the 26-hour 7/24 run.
    if (( ! IN_SESSION )); then
        log "OK: $NOW_HM CT (dow $NOW_DOW) is outside the session window $SESSION_START–$SESSION_END Mon–Fri — no gauge expected, not launching."
        HB_DETAIL="outside the session window — no gauge expected"
        exit 0
    fi

    # We are going to launch. Surface gate deps now (informational — the gauge
    # stays alive through a dead token, printing poll errors in-pane).
    if [[ ! -f "$HOME/.schwab_gate_key" ]]; then
        log "WARN: ~/.schwab_gate_key ABSENT — live gauge cannot authenticate; launching anyway so the failure shows in-pane, not silently from cron."
    fi
    HEALTH="$STRADER_REPO/data/corpus/_schwab_token_health.json"
    if [[ -f "$HEALTH" ]]; then
        STATUS="$(grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' "$HEALTH" \
                    | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')"
        log "token health: ${STATUS:-unknown}"
    fi

    # --- desk down → bring up the REAL desk first [st-r3f] ---------------
    # Steve's ask: the code that starts the gauge should detect a down desk and
    # start it. COO's script is the authority on what the desk IS, and it is
    # idempotent (clean exit 0 when the session exists), so calling it here can
    # only ever help. Only its failure or absence falls through to the minimal
    # bootstrap below.
    if ! "${TMUX[@]}" has-session -t "$SESSION" 2>/dev/null; then
        if [[ "$SESSION" == "$DESK_SESSION_NAME" && -x "$DESK_BOOTSTRAP" ]]; then
            log "session '$SESSION' is DOWN — invoking COO desk bootstrap: $DESK_BOOTSTRAP"
            TMUX_SOCKET="$SOCKET" timeout 60 bash "$DESK_BOOTSTRAP"
            DESK_RC=$?
            if "${TMUX[@]}" has-session -t "$SESSION" 2>/dev/null; then
                log "real desk is up (bootstrap rc=$DESK_RC) — placing the gauge window in it."
            else
                log "WARN: desk bootstrap produced no session '$SESSION' (rc=$DESK_RC) — falling back to the minimal bootstrap."
            fi
        else
            log "note: real desk bootstrap not usable (session='$SESSION' script='$DESK_BOOTSTRAP') — minimal bootstrap."
        fi
    fi

    WID=""
    if ! "${TMUX[@]}" has-session -t "$SESSION" 2>/dev/null; then
        # --- FALLBACK BOOTSTRAP: still down → create a minimal session -----
        log "session '$SESSION' on socket '$SOCKET' is DOWN — bootstrapping a minimal session (Steve-authorized 2026-07-23). NOTE: not COO's full desk; reconcile if COO rebuilds."
        WID="$("${TMUX[@]}" new-session -d -s "$SESSION" -n "$WIN_NAME" \
                 -c "$STRADER_REPO" -P -F '#{window_id}' "$GAUGE_LAUNCH_CMD" 2>/dev/null)"
        if [[ -z "$WID" ]]; then
            log "FATAL: could not bootstrap session '$SESSION' on socket '$SOCKET'."; exit 2
        fi
        log "bootstrapped session '$SESSION' with gauge window $WID."
    else
        # --- session up: launch fresh FIRST, then reap the stale ones -----
        # Order matters: if we reaped first and every window in the session
        # happened to be a stale gauge window, killing them all would empty and
        # DESTROY the session, and the launch would then fail. So snapshot the
        # pre-existing stale windows (guard already proved none are live),
        # create the fresh window, and only then reap the snapshot — the new
        # window keeps the session non-empty throughout.
        STALE_IDS="$("${TMUX[@]}" list-windows -t "$SESSION" -F '#{window_id} #{window_name}' 2>/dev/null \
                    | awk -v n="$WIN_NAME" '$2==n {print $1}')"

        # Insert after the Trading anchor when present; append otherwise.
        NEWARGS=(-d -t "$SESSION" -n "$WIN_NAME" -c "$STRADER_REPO" -P -F '#{window_id}')
        if "${TMUX[@]}" list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null \
                | grep -qx "$ANCHOR_WIN"; then
            NEWARGS=(-d -a -t "$SESSION:$ANCHOR_WIN" -n "$WIN_NAME" \
                     -c "$STRADER_REPO" -P -F '#{window_id}')
        else
            log "note: anchor window '$ANCHOR_WIN' not present — appending gauge window."
        fi
        WID="$("${TMUX[@]}" new-window "${NEWARGS[@]}" "$GAUGE_LAUNCH_CMD" 2>/dev/null)"
        if [[ -z "$WID" ]]; then
            log "FATAL: tmux new-window failed."; exit 2
        fi

        for wid in $STALE_IDS; do
            log "reaping stale window $wid (name=$WIN_NAME, no live gauge process)"
            "${TMUX[@]}" kill-window -t "$wid" 2>/dev/null || true
        done
    fi

    # remain-on-exit=failed: freeze the pane on a CRASH (traceback stays legible
    # until the next launch reaps it), close it on a clean exit. Steve's call
    # 2026-07-25 — before st-5n8 the gauge never exited cleanly, so `on` and
    # `failed` behaved identically; now that 15:15 is a clean exit, `on` would
    # park a dead pane on the desk every evening until the next morning's first
    # in-window fire. The day's final read is already durable in
    # data/corpus/<date>/mi_gauge_live.jsonl, so closing the window loses
    # nothing. (The pre-st-5n8 comment here claimed `on` closed the window on a
    # clean exit; it does not — that was never exercised.)
    "${TMUX[@]}" set-option -t "$WID" remain-on-exit failed 2>/dev/null || true

    sleep 1
    NEWPID="$(live_gauge_pids | tr '\n' ' ')"
    if [[ -n "${NEWPID// }" ]]; then
        log "OK: launched live gauge (pid ${NEWPID%% }) in $SESSION window '$WIN_NAME' ($WID)."
        HB_DETAIL="launched live gauge (pid ${NEWPID%% })"
        exit 0
    fi
    log "ERROR: window $WID created but no live gauge process after 1s — the gauge likely crashed on startup; check pane $WID (remain-on-exit is 'failed', so a crash stays frozen there)."
    HB_DETAIL="gauge crashed on launch; pane $WID frozen — $LOG"
    exit 4

} >> "$LOG" 2>&1
