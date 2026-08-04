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
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done

command -v tmux >/dev/null || { echo "FATAL: tmux not found" >&2; exit 2; }
[[ -x "$PY" ]] || { echo "FATAL: venv python missing: $PY" >&2; exit 2; }

TM="tmux -L $SOCK"

# The page first: it is harmless to regenerate and it fails loudly if the
# template or the day's Mancini parse is wrong, before any process starts.
PYTHONPATH="$REPO" "$PY" "$REPO/scripts/live_footprint_page.py" || exit $?

$TM has-session -t "$SESSION" 2>/dev/null || $TM new-session -d -s "$SESSION" -n System

if $TM list-windows -t "$SESSION" -F '#W' 2>/dev/null | grep -qx "$WINDOW"; then
    echo "window '$WINDOW' already exists — attach and check it rather than"
    echo "starting a second capture against the same corpus file:"
    echo "  tmux -L $SOCK attach -t $SESSION:$WINDOW"
    exit 0
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

$TM split-window -t "$SESSION:$WINDOW" -v -c "$REPO"
$TM send-keys -t "$SESSION:$WINDOW" \
    "PYTHONPATH=$REPO $PY $REPO/scripts/corpus_stream_databento.py ${STREAM_ARGS[*]}"
$TM send-keys -t "$SESSION:$WINDOW" Enter

$TM split-window -t "$SESSION:$WINDOW" -v -c "$REPO"
$TM send-keys -t "$SESSION:$WINDOW" \
    "PYTHONPATH=$REPO $PY $REPO/scripts/live_footprint_feed.py"
$TM send-keys -t "$SESSION:$WINDOW" Enter

$TM select-layout -t "$SESSION:$WINDOW" even-vertical

cat <<EOF

live footprint stack up — tmux -L $SOCK attach -t $SESSION:$WINDOW
  pane 0  bridge    127.0.0.1:7788
  pane 1  CAPTURE   streams=$STREAMS  $( [[ $START_NOW -eq 1 ]] && echo "starting now" || echo "waits until $START_CT CT" ) until $UNTIL_CT CT
  pane 2  feeder    tails the corpus, pushes bars

  page    file://wsl.localhost/Zgent/tmp/desk-live-footprint.html
EOF
