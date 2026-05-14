#!/bin/bash
# run.sh — Steve's entry point for running reviewed Schwab code
# Usage: ./scripts/run.sh <script.py> [args...]
#
# This is the ONLY way to run live Schwab API code.
# The agent cannot execute this (blocked by PreToolUse hook).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <script.py> [args...]"
  echo ""
  echo "Available scripts:"
  ls "$SCRIPT_DIR"/*.py 2>/dev/null | xargs -I{} basename {}
  exit 1
fi

SCRIPT="$1"
shift

# Ensure gate key exists
if [ ! -f "$HOME/.schwab_gate_key" ]; then
  echo "Creating gate key at ~/.schwab_gate_key ..."
  touch "$HOME/.schwab_gate_key"
fi

# Activate venv
source "$REPO_DIR/.venv/bin/activate"

# Load environment
set -a
source "$REPO_DIR/.env"
set +a

# Run
cd "$REPO_DIR"
python3 "$SCRIPT_DIR/$SCRIPT" "$@"
