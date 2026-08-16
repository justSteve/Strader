#!/usr/bin/env bash
# live-footprint-up.sh — bring up the live footprint stack in tmux. [st-re1o]
#
#   bash scripts/live-footprint-up.sh              # today, RTH window
#   bash scripts/live-footprint-up.sh --now        # start capture immediately
#   bash scripts/live-footprint-up.sh --with-mbp1  # also capture the book
#
# Three processes, one tmux window, in dependency order:
#   pane 0  drill_bridge.py            the channel the page polls
#   pane 1  corpus_stream_databento.py CAPTURE — writes the corpus
#   pane 2  live_footprint_feed.py     tails the corpus, pushes bars
#
# CAPTURE IS THE PANE THAT MATTERS. Live trades and MBP-1 are never backfilled,
# so a session missed is missed at any price. The other two only render. If you
# are short on time or something is misbehaving, keep pane 1 alive and let the
# rest go — the day stays fully replayable through the ordinary drill after the
# close, because the feeder reads the same corpus file the drill does.
#
# The page is written to /tmp/desk-live-footprint.html, a stable address. Park a
# browser tab on it and refresh; it does not change per day.
set -uo pipefail

REPO="${STRADER_REPO:-/root/projects/Strader}"
PY="${STRADER_PY:-$REPO/.venv/bin/python}"
SOCK="${TMUX_SOCKET:-moocity}"
SESSION="${STRADER_DESK_SESSION:-steves-desk}"
WINDOW="footprint"

START_NOW=0
STREAMS="es"
UNTIL_CT="${STRADER_FP_UNTIL:-15:05}"
START_CT="${STRADER_FP_START:-08:30}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --now)        START_NOW=1 ;;
        --with-mbp1)  STREAMS="es,es-mbp1" ;;
        --until)      UNTIL_CT="$2"; shift ;;
        --start)      START_CT="$2"; shift ;;
        --tmux)       STRADER_FP_FORCE_TMUX=1 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done

command -v tmux >/dev/null || { echo "FATAL: tmux not found" >&2; exit 2; }
[[ -x "$PY" ]] || { echo "FATAL: venv python missing: $PY" >&2; exit 2; }

# Unit-aware [st-n0qm.3]. Since 2026-08-16 the bridge and feeder run under
# systemd (deploy/systemd/strader-drill-bridge.service + strader-footprint-feed.service,
# installed by deploy/install.sh) and come back on their own after a reboot.
# When they are up, this script must not start a second bridge on :7788 or a
# second feeder posting the same day twice — it becomes the viewer: say where
# the page is and how to watch the processes, and exit. Pass --tmux to force
# the old hand-launched stack (only sensible with the units stopped).
FORCE_TMUX="${STRADER_FP_FORCE_TMUX:-0}"
if [[ "$FORCE_TMUX" != "1" ]] && systemctl is-active --quiet strader-drill-bridge.service 2>/dev/null; then
    FEED_STATE="$(systemctl is-active strader-footprint-feed.service 2>/dev/null || echo unknown)"
    cat <<EOT
live footprint stack runs under systemd — nothing to launch.
  bridge  strader-drill-bridge.service    active
  feeder  strader-footprint-feed.service  $FEED_STATE
  page    http://127.0.0.1:7788/            (desktop)
          https://mydesk-1.tail89f676.ts.net/footprint/   (tailnet — iPad/phone)
          file://wsl.localhost/Zgent/tmp/desk-live-footprint.html  (bookmark, still rendered)
  watch   journalctl -fu strader-footprint-feed      journalctl -fu strader-drill-bridge
  control systemctl restart strader-drill-bridge     (PartOf= restarts the feeder too)
EOT
    exit 0
fi

TM="tmux -L $SOCK"

# The page first: it is harmless to regenerate and it fails loudly if the
# template or the day's Mancini parse is wrong, before any process starts.
PYTHONPATH="$REPO" "$PY" "$REPO/scripts/live_footprint_page.py" || exit $?

$TM has-session -t "$SESSION" 2>/dev/null || $TM new-session -d -s "$SESSION" -n System

if $TM list-windows -t "$SESSION" -F '#W' 2>/dev/null | grep -qx "$WINDOW"; then
    # "The window exists" is not "the stack is healthy". [st-h510]
    #
    # On 2026-08-13 this branch exited 0 against a stack that had been pinned to
    # the PREVIOUS day for 21 hours — a green report over a dead renderer. The
    # bridge is the honest witness: it serves the feeder's own day on /bars, so
    # ask it what day it thinks it is rather than trusting the window name.
    BRIDGE_DAY="$(curl -s --max-time 3 'http://127.0.0.1:7788/bars?since=0' 2>/dev/null \
        | "$PY" -c 'import json,sys
try: print(json.load(sys.stdin).get("meta",{}).get("day","") or "")
except Exception: print("")' 2>/dev/null)"
    TODAY_CT="$(TZ=America/Chicago date +%F)"
    if [[ -n "$BRIDGE_DAY" && "$BRIDGE_DAY" != "$TODAY_CT" ]]; then
        echo "STALE STACK — window '$WINDOW' exists but the bridge is serving" >&2
        echo "  $BRIDGE_DAY, and today is $TODAY_CT." >&2
        echo "The renderer is following a file that can no longer grow. Kill the" >&2
        echo "render panes and re-run this script. Do NOT touch the capture pane." >&2
        echo "  tmux -L $SOCK attach -t $SESSION:$WINDOW" >&2
        exit 3
    fi
    echo "window '$WINDOW' already exists${BRIDGE_DAY:+ (bridge day $BRIDGE_DAY, current)}"
    echo "— attach and check it rather than starting a second capture against"
    echo "the same corpus file:"
    echo "  tmux -L $SOCK attach -t $SESSION:$WINDOW"
    exit 0
fi

# Guard on the PROCESS, not the window name. [st-sgr1]
#
# The window check above is necessary but not sufficient: it only catches a
# stack this script started. Capture is routinely running somewhere else — a
# window named 'capture', a bare shell, a systemd unit — and on 2026-08-06 and
# 2026-08-07 it was, so the name check passed and this script would have
# launched a SECOND corpus_stream_databento.py writing the same JSONL. Two
# writers on one corpus file is the failure the header warns about: live trades
# and MBP-1 are never backfilled, so a corrupted session is corrupted forever.
#
# When capture is already up, the answer is NOT to refuse the whole stack —
# that leaves the operator with no chart on a day the data is fine. Start the
# render-only panes and leave the running capture strictly alone.
CAPTURE_PID="$(pgrep -f 'corpus_stream_databento\.py' | head -1 || true)"
if [[ -n "$CAPTURE_PID" ]]; then
    echo "capture already running (pid $CAPTURE_PID) — NOT starting a second one."
    echo "bringing up the render panes only (bridge + feeder)."
    RENDER_ONLY=1
else
    RENDER_ONLY=0
fi

STREAM_ARGS=(--streams "$STREAMS" --until-ct "$UNTIL_CT")
if [[ $START_NOW -eq 1 ]]; then
    STREAM_ARGS+=(--now)
else
    STREAM_ARGS+=(--start-ct "$START_CT")
fi

$TM new-window -d -t "$SESSION" -n "$WINDOW" -c "$REPO"
# Two send-keys calls per pane — content, then Enter — per the tmux convention.
$TM send-keys -t "$SESSION:$WINDOW" \
    "PYTHONPATH=$REPO $PY $REPO/scripts/drill_bridge.py"
$TM send-keys -t "$SESSION:$WINDOW" Enter

if [[ $RENDER_ONLY -eq 0 ]]; then
    $TM split-window -t "$SESSION:$WINDOW" -v -c "$REPO"
    $TM send-keys -t "$SESSION:$WINDOW" \
        "PYTHONPATH=$REPO $PY $REPO/scripts/corpus_stream_databento.py ${STREAM_ARGS[*]}"
    $TM send-keys -t "$SESSION:$WINDOW" Enter
fi

$TM split-window -t "$SESSION:$WINDOW" -v -c "$REPO"
$TM send-keys -t "$SESSION:$WINDOW" \
    "PYTHONPATH=$REPO $PY $REPO/scripts/live_footprint_feed.py"
$TM send-keys -t "$SESSION:$WINDOW" Enter

$TM select-layout -t "$SESSION:$WINDOW" even-vertical

cat <<EOF

live footprint stack up — tmux -L $SOCK attach -t $SESSION:$WINDOW
  pane 0  bridge    127.0.0.1:7788
$( [[ $RENDER_ONLY -eq 1 ]] \
    && echo "  (no capture pane — pid $CAPTURE_PID was already streaming and was left alone)" \
    || echo "  pane 1  CAPTURE   streams=$STREAMS  $( [[ $START_NOW -eq 1 ]] && echo "starting now" || echo "waits until $START_CT CT" ) until $UNTIL_CT CT" )
  feeder            tails the corpus, pushes bars

  page    file://wsl.localhost/Zgent/tmp/desk-live-footprint.html
EOF
