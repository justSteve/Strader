#!/usr/bin/env bash
# Update a tmux pane with presenter output.
# Usage: driver.sh <presenter> <pane_target>
#   presenter:   regime | signals
#   pane_target: tmux address, e.g. "strader:Dashboard.1"
#
# Uses load-buffer + paste-buffer. NOT send-keys.
# send-keys injects keystrokes; paste-buffer outputs content to the pane display.

set -euo pipefail

PRESENTER="${1:?Usage: driver.sh <presenter> <pane_target>}"
PANE="${2:?Usage: driver.sh <presenter> <pane_target>}"
shift 2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
source .venv/bin/activate

case "$PRESENTER" in
  regime)
    python -m present.cli regime "$@" | tmux load-buffer - && tmux paste-buffer -t "$PANE"
    ;;
  signals)
    python -m present.cli signals "$@" | tmux load-buffer - && tmux paste-buffer -t "$PANE"
    ;;
  *)
    echo "Unknown presenter: $PRESENTER" >&2
    exit 1
    ;;
esac
