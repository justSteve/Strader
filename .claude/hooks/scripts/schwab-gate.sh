#!/bin/bash
# schwab-gate.sh — PreToolUse hook for Bash
# Hard gate: prevents agent from executing Schwab API code or modifying credentials
#
# Exit 0 = allow, Exit 2 = block (message on stderr)

set -uo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.command // empty')

if [ -z "$COMMAND" ]; then
  exit 0
fi

# Gate 1: Block python execution of any file that imports schwab
# Exempt: schwab/readers/ — pre-approved read-only market data scripts
# Only check when command actually runs python (not grep, cat, etc.)
if echo "$COMMAND" | grep -qE '(python3?|\./) '; then
  for PY_FILE in $(echo "$COMMAND" | grep -oE '[^ ;|&"'\'']+\.py' || true); do
    case "$PY_FILE" in
      schwab/readers/*.py|*/schwab/readers/*.py) continue ;;
    esac
    if [ -f "$PY_FILE" ] && grep -qlE '^[[:space:]]*(import schwab|from schwab)' "$PY_FILE" 2>/dev/null; then
      echo "SCHWAB GATE: '$PY_FILE' imports schwab. Write code → Steve reviews → Steve runs." >&2
      exit 2
    fi
  done
fi

# Gate 2: Block inline python that references schwab
if echo "$COMMAND" | grep -qE 'python3?\s+.*-c.*schwab'; then
  echo "SCHWAB GATE: Inline schwab import blocked." >&2
  exit 2
fi

# Gate 3: Block execution from scripts/ directory
if echo "$COMMAND" | grep -qE '(python3?|bash|sh|\./).*scripts/'; then
  echo "SCHWAB GATE: scripts/ is Steve-only. Write code → Steve reviews → Steve runs." >&2
  exit 2
fi

# Gate 4: Block token file modification
if echo "$COMMAND" | grep -qE '(>|>>|cp |mv |rm |chmod ).*tokens/'; then
  echo "SCHWAB GATE: Cannot modify token files." >&2
  exit 2
fi

# Gate 5: Block schwab module execution
if echo "$COMMAND" | grep -qE 'python3?\s+-m\s+schwab'; then
  echo "SCHWAB GATE: Cannot run schwab as module." >&2
  exit 2
fi

exit 0
