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
    echo "Window $SESSION:$WINDOW already exists; not restarting."
    echo "Attach: tmux -L $SOCK attach -t $SESSION"
    exit 0
fi

tmux -L "$SOCK" new-window -d -t "$SESSION" -n "$WINDOW" -c "$REPO"
# Two send-keys calls, per .claude/rules/two-send-keys.md
tmux -L "$SOCK" send-keys -t "$SESSION:$WINDOW" '.venv/bin/python3 scripts/orderflow_monitor.py --follow'
tmux -L "$SOCK" send-keys -t "$SESSION:$WINDOW" Enter

echo "Monitor started in $SESSION:$WINDOW."
echo "Feed:      tmux -L $SOCK attach -t $SESSION  (window $WINDOW)"
echo "Heartbeat: /var/moo/state/orderflow-monitor.json"
