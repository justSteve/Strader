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
# BOOTSTRAP (Steve-authorized 2026-07-23). If the tmux session is down this
# wrapper creates a MINIMAL session to host the gauge — it does NOT rebuild
# COO's full desk. If COO later re-bootstraps the desk the two may need
# reconciling; that tradeoff is accepted for gauge reliability.
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

TMUX=(tmux -L "$SOCKET")

: "${HOME:=/root}"
export HOME

LOG_DIR="${STRADER_GAUGE_LOGDIR:-/var/moo/logs/gauge-preopen}"
mkdir -p "$LOG_DIR" 2>/dev/null
DATE="$(date +%Y-%m-%d)"
LOG="$LOG_DIR/$DATE.log"

log() { echo "[$(date +%H:%M:%S)] $*"; }

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
        log "OK: live gauge already running (pid ${LIVE_PIDS%% })— nothing to do."
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

    WID=""
    if ! "${TMUX[@]}" has-session -t "$SESSION" 2>/dev/null; then
        # --- BOOTSTRAP: session down → create a minimal one (Steve-authorized) ---
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

    # remain-on-exit: a CLEAN exit closes the window (the gauge loops forever,
    # so it only exits on crash); a CRASH instead freezes the error in-pane
    # until the next heartbeat reaps it — crashes stay diagnosable, not silent.
    "${TMUX[@]}" set-option -t "$WID" remain-on-exit on 2>/dev/null || true

    sleep 1
    NEWPID="$(live_gauge_pids | tr '\n' ' ')"
    if [[ -n "${NEWPID// }" ]]; then
        log "OK: launched live gauge (pid ${NEWPID%% }) in $SESSION window '$WIN_NAME' ($WID)."
        exit 0
    fi
    log "ERROR: window $WID created but no live gauge process after 1s — the gauge likely crashed on startup; check pane $WID (remain-on-exit is on, so the error is frozen there)."
    exit 4

} >> "$LOG" 2>&1
