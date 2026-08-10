#!/usr/bin/env bash
# capture-supervisor-wrapper.sh — keep the live Databento capture alive. [st-6qx4]
#
#   */2 * * * * /usr/bin/bash /root/projects/Strader/scripts/cron/capture-supervisor-wrapper.sh
#
# Cron here runs local America/Chicago time (no TZ override), so every window
# below tracks the session clock and rides DST automatically.
#
# WHY THIS EXISTS. scripts/corpus_stream_databento.py is the first long-lived
# process in a repo whose automation is otherwise entirely cron ticks. A cron job
# that fails leaves an rc and a log; a streamer that dies at 02:00 leaves nothing
# until someone looks at a pane at 08:30. Live trades and MBP-1 quotes are NEVER
# backfilled — a night lost cannot be bought later at any price. That asymmetry,
# not tidiness, is the whole justification for this script.
#
# EVERY TWO MINUTES, NOT FIVE. The gauge heartbeat is */5 because a gauge that
# respawns five minutes late replays its own state file and loses nothing. This
# one cannot replay anything: the tick that arrived while it was down is gone.
# The check is a /proc scan and one small JSON read, so the extra fires are free.
#
# IDEMPOTENT BY PROCESS, NOT BY WINDOW [st-cm5]. On 2026-07-23 three tmux windows
# were named `gauge` with exactly one live process behind them. A window named
# `capture` proves nothing. scripts/capture_health.py finds the real processes by
# scanning /proc for a python whose command line carries the streamer path.
#
# A LIVE PID IS NOT A LIVE FEED. The harder failure is a process that is alive
# and receiving nothing — the pane looks busy and the tape stops. That is caught
# by watching manifest `streams.<name>.cycles` advance between runs, gated on the
# GLBX calendar so the daily 15:15 pause and 16:00 halt are not mistaken for
# death. See strader/capture_health.py.
#
# RESTART IS SAFE — verified in the streamer, not assumed:
#   * JSONL is opened "a" (StreamWorker.run), so a relaunch appends.
#   * the raw DBN tee picks the lowest FREE segment index (_next_raw_path), so
#     no segment is ever clobbered.
#   * the manifest is read-modify-written with increments (update_manifest).
# What is NOT safe is TWO captures at once — they double-append the same file.
# Hence the process guard before every launch, and the `duplicate` verdict.
#
# WHAT IT WILL NOT DO. It does not kill. A stale capture is reported and left
# running unless STRADER_CAPTURE_RESTART_STALE=1 is set, matching the gauge's
# rule that killing someone's process from cron stays a human call. Flip the knob
# once the stale verdict has been observed clean for a week.
#
# WHERE THE ALERT GOES. data/corpus/_health.jsonl (shared with corpus_daily and
# the pre-open heartbeat), a log under /var/moo/logs/capture-supervisor/, and —
# the one surface actually read every morning — the 08:25 CT pre-open heartbeat,
# which reports the watcher's state file as a soft check. An alert nobody reads
# is not a guard; the Mancini interpretive leg died silently for three sessions
# at rc=0 because its only witness was a log file.
#
# PATH IS SET EXPLICITLY [st-i68]. Cron's minimal PATH is why the 2026-07-24
# Mancini batch died on a bare FileNotFoundError.
#
# Manual smoke (safe — a no-op when a capture is already live):
#   bash scripts/cron/capture-supervisor-wrapper.sh
#
# Test knobs (drive every path against a stub process on a scratch socket, with
# no real streamer, no moocity desk and no Databento connection):
#   STRADER_CAPTURE_MATCH  STRADER_CAPTURE_LAUNCH  STRADER_CAPTURE_PROC_ROOT
#   STRADER_CAPTURE_CORPUS_ROOT  STRADER_CAPTURE_STATE  STRADER_CAPTURE_HEALTH_LOG
#   STRADER_CAPTURE_NOW  STRADER_TMUX_SOCKET  STRADER_TMUX_SESSION
#   STRADER_CAPTURE_WIN  STRADER_CAPTURE_LOGDIR  STRADER_CAPTURE_GRACE_SECS
set -uo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
CHECK="$REPO/scripts/capture_health.py"
STREAMER="$REPO/scripts/corpus_stream_databento.py"

: "${HOME:=/root}"
export HOME

# --- what a healthy day looks like ----------------------------------------
# Round-the-clock is Phase B's own answer (st-d5f §2d): it moots st-btu's
# pre-market question and captures the Globex session that nothing else covers.
# The streamer fixes its corpus day at startup, so it cannot span midnight —
# 23:59 + a relaunch on the next tick IS the day rollover.
STREAMS="${STRADER_CAPTURE_STREAMS:-es,es-mbp1}"
UNTIL_CT="${STRADER_CAPTURE_UNTIL_CT:-23:59}"
START_CT="${STRADER_CAPTURE_START_CT:-00:00}"
STALE_SECS="${STRADER_CAPTURE_STALE_SECS:-600}"
GRACE_SECS="${STRADER_CAPTURE_GRACE_SECS:-180}"
RESTART_STALE="${STRADER_CAPTURE_RESTART_STALE:-0}"

# --- where it lives --------------------------------------------------------
SOCKET="${STRADER_TMUX_SOCKET:-moocity}"
SESSION="${STRADER_TMUX_SESSION:-steves-desk}"
WIN_NAME="${STRADER_CAPTURE_WIN:-capture}"
# A dedicated window, deliberately NOT the `footprint` window that
# scripts/live-footprint-up.sh builds: that script guards on the window name, so
# reusing it would make a supervisor relaunch look like a running stack and
# suppress the manual bring-up. The feeder tails the corpus file, not the pane,
# so it does not care which window the capture lives in.
LAUNCH_CMD="${STRADER_CAPTURE_LAUNCH:-exec env PYTHONPATH=$REPO $PY $STREAMER --streams $STREAMS --until-ct $UNTIL_CT --now}"

LOG_DIR="${STRADER_CAPTURE_LOGDIR:-/var/moo/logs/capture-supervisor}"
mkdir -p "$LOG_DIR" 2>/dev/null
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

TMUX=(tmux -L "$SOCKET")

# Flags shared by the check and the restart record, so both touch the same
# state file and the same health log.
CHECK_ARGS=(--streams "$STREAMS" --stale-secs "$STALE_SECS"
            --grace-secs "$GRACE_SECS"
            --window-start "$START_CT" --window-end "$UNTIL_CT")
[[ -n "${STRADER_CAPTURE_MATCH:-}" ]]       && CHECK_ARGS+=(--match "$STRADER_CAPTURE_MATCH")
[[ -n "${STRADER_CAPTURE_PROC_ROOT:-}" ]]   && CHECK_ARGS+=(--proc-root "$STRADER_CAPTURE_PROC_ROOT")
[[ -n "${STRADER_CAPTURE_CORPUS_ROOT:-}" ]] && CHECK_ARGS+=(--corpus-root "$STRADER_CAPTURE_CORPUS_ROOT")
[[ -n "${STRADER_CAPTURE_STATE:-}" ]]       && CHECK_ARGS+=(--state "$STRADER_CAPTURE_STATE")
[[ -n "${STRADER_CAPTURE_HEALTH_LOG:-}" ]]  && CHECK_ARGS+=(--health-log "$STRADER_CAPTURE_HEALTH_LOG")
[[ -n "${STRADER_CAPTURE_NOW:-}" ]]         && CHECK_ARGS+=(--now "$STRADER_CAPTURE_NOW")

log() { echo "[$(date +%H:%M:%S)] $*"; }

live_pids() {
    "$PY" "$CHECK" "${CHECK_ARGS[@]}" --porcelain --no-alert 2>/dev/null \
        | sed -n 's/^pids=//p'
}

{
    log "=== capture-supervisor start $(date +%Y-%m-%dT%H:%M:%S%z) socket=$SOCKET ==="

    # --- preflight --------------------------------------------------------
    if [[ ! -x "$PY" ]]; then
        log "FATAL: venv python not executable: $PY"; exit 2
    fi
    if [[ ! -f "$CHECK" ]]; then
        log "FATAL: checker missing: $CHECK"; exit 2
    fi
    if [[ ! -f "$STREAMER" ]]; then
        log "FATAL: streamer missing: $STREAMER"; exit 2
    fi

    # --- the verdict ------------------------------------------------------
    # The checker owns assessment, the state file and the alert. This wrapper
    # owns only the decision to relaunch — one brain, not two.
    OUT="$("$PY" "$CHECK" "${CHECK_ARGS[@]}" --porcelain 2>&1)"
    CHECK_RC=$?
    STATUS=""; ALL_STALE=0; PIDS=""
    while IFS='=' read -r k v; do
        case "$k" in
            status)    STATUS="$v" ;;
            all_stale) ALL_STALE="$v" ;;
            pids)      PIDS="$v" ;;
        esac
    done <<< "$OUT"
    log "check rc=$CHECK_RC status=${STATUS:-?} pids=[${PIDS}] all_stale=$ALL_STALE"
    printf '%s\n' "$OUT" | sed 's/^/    /'

    if [[ -z "$STATUS" ]]; then
        log "FATAL: checker produced no verdict (rc=$CHECK_RC) — capture liveness is UNKNOWN."
        exit 2
    fi

    # --- act --------------------------------------------------------------
    case "$STATUS" in
        ok|starting|quiet|idle)
            log "no action: $STATUS"
            exit 0
            ;;
        duplicate)
            # Two captures double-append the same JSONL. Picking which to kill
            # needs a human eye on what each one is writing; killing the wrong
            # one loses the good stream. Report loudly, touch nothing.
            log "ALERT: duplicate captures [$PIDS] — both appending the same corpus files. NOT killing from cron; stop all but one by hand."
            exit 1
            ;;
        stale)
            if [[ "$RESTART_STALE" != "1" ]]; then
                log "ALERT: capture is alive but not receiving. Leaving it running (STRADER_CAPTURE_RESTART_STALE unset) — killing from cron stays a human call. Alert is on the health log and the pre-open heartbeat."
                exit 1
            fi
            if [[ "$ALL_STALE" != "1" ]]; then
                log "ALERT: partial staleness (some streams still advancing) — restart-on-stale only fires when EVERY watched stream is frozen. Left running."
                exit 1
            fi
            log "restart-on-stale enabled and every stream frozen — terminating [$PIDS] before relaunch."
            for p in $PIDS; do kill -TERM "$p" 2>/dev/null; done
            for _ in 1 2 3 4 5 6 7 8 9 10; do
                sleep 1
                [[ -z "$(live_pids)" ]] && break
            done
            for p in $(live_pids); do
                log "pid $p ignored SIGTERM — SIGKILL"
                kill -KILL "$p" 2>/dev/null
            done
            sleep 1
            if [[ -n "$(live_pids)" ]]; then
                log "FATAL: stale capture would not die — refusing to launch a second one."
                exit 2
            fi
            ;;
        dead)
            # Don't relaunch into the last breath of the window: the streamer
            # refuses to start once --until-ct has passed ("until-ct already
            # passed. Nothing to do."), so a launch here would exit instantly,
            # bank a spurious restart record, and repeat. The day-rollover
            # relaunch on the next tick is the one that matters.
            NOW_HM="$(TZ=America/Chicago date +%H:%M)"
            [[ -n "${STRADER_CAPTURE_NOW:-}" ]] && NOW_HM="${STRADER_CAPTURE_NOW#*T}"
            NOW_MIN=$(( 10#${NOW_HM%%:*} * 60 + 10#${NOW_HM##*:} ))
            END_MIN=$(( 10#${UNTIL_CT%%:*} * 60 + 10#${UNTIL_CT##*:} ))
            if (( NOW_MIN >= END_MIN - 2 )); then
                log "capture is down at $NOW_HM CT, inside the final 2 minutes of the $START_CT-$UNTIL_CT window — not relaunching; the next tick starts the new day's capture."
                exit 0
            fi
            log "capture is DOWN inside the expected window — relaunching."
            ;;
        *)
            log "FATAL: unrecognised status '$STATUS'"; exit 2
            ;;
    esac

    # --- relaunch ---------------------------------------------------------
    if ! "${TMUX[@]}" has-session -t "$SESSION" 2>/dev/null; then
        log "session '$SESSION' on socket '$SOCKET' is DOWN — bootstrapping a minimal one to host the capture. NOTE: not COO's full desk; reconcile if COO rebuilds."
        WID="$("${TMUX[@]}" new-session -d -s "$SESSION" -n "$WIN_NAME" \
                 -c "$REPO" -P -F '#{window_id}' "$LAUNCH_CMD" 2>/dev/null)"
        if [[ -z "$WID" ]]; then
            log "FATAL: could not bootstrap session '$SESSION' on socket '$SOCKET'."; exit 2
        fi
    else
        # Create first, reap after [st-cm5]: if every window in the session were
        # a stale `capture` window, reaping first would empty and DESTROY the
        # session and the launch would then fail. The guard above already proved
        # no live capture exists behind any of them.
        STALE_IDS="$("${TMUX[@]}" list-windows -t "$SESSION" -F '#{window_id} #{window_name}' 2>/dev/null \
                    | awk -v n="$WIN_NAME" '$2==n {print $1}')"
        WID="$("${TMUX[@]}" new-window -d -t "$SESSION" -n "$WIN_NAME" -c "$REPO" \
                 -P -F '#{window_id}' "$LAUNCH_CMD" 2>/dev/null)"
        if [[ -z "$WID" ]]; then
            log "FATAL: tmux new-window failed."; exit 2
        fi
        for wid in $STALE_IDS; do
            log "reaping stale window $wid (name=$WIN_NAME, no live capture behind it)"
            "${TMUX[@]}" kill-window -t "$wid" 2>/dev/null || true
        done
    fi

    # remain-on-exit=failed: a crash freezes the pane so the traceback is still
    # legible next time someone attaches; a clean exit at --until-ct closes it.
    "${TMUX[@]}" set-option -t "$WID" remain-on-exit failed 2>/dev/null || true

    sleep 3
    NEWPIDS="$(live_pids)"
    if [[ -n "${NEWPIDS// }" ]]; then
        log "OK: capture relaunched (pid $NEWPIDS) in $SESSION window '$WIN_NAME' ($WID), streams=$STREAMS until $UNTIL_CT CT."
        "$PY" "$CHECK" "${CHECK_ARGS[@]}" \
            --record-restart "was $STATUS; relaunched pid $NEWPIDS in $SESSION:$WIN_NAME (streams=$STREAMS until $UNTIL_CT CT)" \
            || log "WARN: restart record failed"
        exit 0
    fi
    log "FATAL: window $WID created but no capture process after 3s — the streamer crashed on startup (bad credentials? entitlement?). Pane is frozen (remain-on-exit=failed); attach and read it: tmux -L $SOCKET attach -t $SESSION:$WIN_NAME"
    exit 2
} >> "$LOG" 2>&1
