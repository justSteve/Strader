#!/usr/bin/env bash
# Start (or verify) the Orderflow Doctrine Monitor [st-2n69] in the
# gexbot-pipeline tmux session, window "of-monitor". Idempotent.
set -euo pipefail

SOCK="moocity"
SESSION="${OF_MONITOR_SESSION:-steves-desk}"   # collector lives in steves-desk:gex
WINDOW="of-monitor"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! tmux -L "$SOCK" has-session -t "$SESSION" 2>/dev/null; then
    echo "ERROR: tmux session '$SESSION' (socket $SOCK) not found." >&2
    echo "Set OF_MONITOR_SESSION if the desk session is named differently." >&2
    exit 1
fi

if tmux -L "$SOCK" list-windows -t "$SESSION" -F '#{window_name}' | grep -qx "$WINDOW"; then
    # window name alone proves nothing: python exits leave the shell (and
    # the window) behind. Only a live monitor process counts as running.
    if pgrep -f 'orderflow_monitor\.py --follow' >/dev/null; then
        echo "Monitor already running in $SESSION:$WINDOW; not restarting."
        echo "Attach: tmux -L $SOCK attach -t $SESSION"
        exit 0
    fi
    echo "Window $SESSION:$WINDOW exists but the monitor is dead; recycling it."
    tmux -L "$SOCK" kill-window -t "$SESSION:$WINDOW"
fi

tmux -L "$SOCK" new-window -d -t "$SESSION" -n "$WINDOW" -c "$REPO"
# Two send-keys calls, per .claude/rules/two-send-keys.md
tmux -L "$SOCK" send-keys -t "$SESSION:$WINDOW" '.venv/bin/python3 scripts/orderflow_monitor.py --follow'
tmux -L "$SOCK" send-keys -t "$SESSION:$WINDOW" Enter

# verify the process came up and heartbeat is moving before claiming success
sleep 6
if ! pgrep -f 'orderflow_monitor\.py --follow' >/dev/null; then
    echo "ERROR: monitor process did not survive startup; last pane output:" >&2
    tmux -L "$SOCK" capture-pane -t "$SESSION:$WINDOW" -p | grep -v '^$' | tail -5 >&2
    exit 1
fi
HB=/var/moo/state/orderflow-monitor.json
echo "Monitor started in $SESSION:$WINDOW."
echo "Heartbeat: $(cat "$HB" 2>/dev/null || echo "not yet written ($HB)")"
echo "Feed:      tmux -L $SOCK attach -t $SESSION  (window $WINDOW)"
