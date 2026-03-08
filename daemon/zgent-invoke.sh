#!/bin/bash
# zgent-invoke — Generic skill invocation via tmux send-keys
# Usage: zgent-invoke <session-name> <skill-name> [--context "..."]
#
# This script bridges scheduled/reactive triggers to agent skill execution.
# The agent receives the invocation as if a human typed it.
set -euo pipefail

SESSION="$1"
SKILL="$2"
CONTEXT=""

shift 2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --context) CONTEXT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Find the workspace pane (first pane in the session)
WORKSPACE_PANE="${SESSION}:0.0"

# Check if session exists
if ! sudo -u gtuser tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "[zgent-invoke] ERROR: Session '${SESSION}' does not exist" >&2
  exit 1
fi

# Build the command
CMD="/skill ${SKILL}"
if [[ -n "${CONTEXT}" ]]; then
  CMD="${CMD} ${CONTEXT}"
fi

# Send to the agent's workspace
sudo -u gtuser tmux send-keys -t "${WORKSPACE_PANE}" "${CMD}" Enter

# Log the invocation
LOG_DIR="/var/moo/logs/${SESSION}"
mkdir -p "${LOG_DIR}"
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"action\":\"invoke\",\"session\":\"${SESSION}\",\"skill\":\"${SKILL}\",\"context\":\"${CONTEXT}\"}" >> "${LOG_DIR}/invocations.jsonl"
