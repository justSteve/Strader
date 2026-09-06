#!/bin/bash
# schwab-gate.sh — PreToolUse hook for Bash
# Hard gate: prevents the agent from executing Schwab API code or touching credentials
#
# Exit 0 = allow, Exit 2 = block (message on stderr)
#
# ============================================================================
# REWRITTEN AND INSTALLED 2026-08-13 — st-ad6p, approved by Steve.
# Prior version is in git history under tag pre-prune-2026-09-05 (the .bak file
# was removed 2026-09-06).
# Behaviour is pinned by tests/test_schwab_gate_hook.py — run it before editing.
#
# TWO CHANGES. The first is the bug; the second is what makes the fix safe to
# turn on.
#
# 1. PAYLOAD KEY. The live hook reads `.command` from the PreToolUse JSON. Claude
#    Code nests it at `.tool_input.command`, so the variable was always empty and
#    every gate below has been returning "allow" without inspecting anything
#    since May 2026. One character of jq path. Falls back to the bare key so the
#    hook also works if invoked with a flat payload (tests, other harnesses).
#
# 2. GATE 3 REWRITTEN — this is the part that needs your eye. The old gate 3
#    blocked ANY command matching `(python3?|bash|sh|\./).*scripts/`. When it was
#    written, scripts/ was Schwab code. It is not any more: 65 .py files live
#    there and only 11 reach Schwab. Turning the old gate 3 on today would block
#    surface_liveness.sh, gex_now.py, level_interaction_read.py, the replay and
#    drill tooling, and the entitlements probe the new tap-in step calls — on a
#    trading day. It also matched `sh` unanchored, so `git show HEAD:scripts/x`
#    tripped it.
#
#    Replaced with reachability: block a .py if it imports schwab directly OR
#    imports broker_schwab (whose client.py is the single module that reaches the
#    API), except the two pre-approved readers. Location stops mattering; what
#    the code touches is what matters. The 2026-08-13 list of 11 files under
#    scripts/ is retired — three were deleted in the 2026-09-06 prune (st-rfjg).
#    Coverage is now proven by tests/test_schwab_gate_hook.py::
#    test_every_reaching_file_in_the_tree_blocks, which sweeps every tracked .py
#    (16 reaching files as of 2026-09-06).
#
# KNOWN LIMIT, stated rather than papered over: this checks the named file's own
# imports, not a full transitive closure. A script importing a local module that
# in turn imports broker_schwab is not caught. The structural layer — the hobbled
# lib/schwab-py fork with order/account methods physically removed — remains the
# real backstop for order placement, and this hook does not pretend otherwise.
# ============================================================================

set -uo pipefail

INPUT=$(cat)

# THE FIX — read the NESTED key only, and fail CLOSED on an unexpected shape.
#
# A first draft read `.tool_input.command // .command` — nested with the bare key
# as a fallback. The control test killed it, correctly: with a fallback the hook
# reads both shapes, so nothing can prove it reads the right one, and a later
# regression to bare-only would sail past a green suite. That is the defect this
# rewrite exists to fix, reintroduced as a convenience.
#
# So: nested only. If the payload carries no nested command but DOES carry one at
# the top level, that is a harness shape this hook was not written for — block
# loudly rather than allow silently. Silent allow on an unrecognised payload is
# exactly how five gates sat dormant from May to August without a single symptom.
# jq is this hook's parser. Without it every gate below would see an empty
# command and allow — the May–August dormancy, again. Fail closed.
# [finding 14, case st-5qjq; approved by Steve 2026-09-01, st-kh0l]
if ! command -v jq >/dev/null 2>&1; then
  echo "SCHWAB GATE: jq is not on PATH — blocking rather than failing open." >&2
  echo "             Install jq or fix PATH; nothing runs through this hook" >&2
  echo "             until its parser is back. [finding 14, case st-5qjq]" >&2
  exit 2
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

if [ -z "$COMMAND" ]; then
  STRAY=$(echo "$INPUT" | jq -r '.command // empty' 2>/dev/null)
  if [ -n "$STRAY" ]; then
    echo "SCHWAB GATE: unrecognised payload shape — a command was present at the" >&2
    echo "             top level but not at .tool_input.command. Refusing to guess." >&2
    echo "             Fix the hook's payload parsing before running this. [st-ad6p]" >&2
    exit 2
  fi
  exit 0
fi

# Gate 1: block executing any .py that REACHES schwab — directly, or via
# broker_schwab. Exempt: the two pre-approved read-only market data readers.
if echo "$COMMAND" | grep -qE '(python3?|\./) '; then
  for PY_FILE in $(echo "$COMMAND" | grep -oE '[^ ;|&"'\'']+\.py' || true); do
    case "$PY_FILE" in
      broker_schwab/readers/*.py|*/broker_schwab/readers/*.py) continue ;;
    esac
    [ -f "$PY_FILE" ] || continue
    if grep -qE '^[[:space:]]*(import[[:space:]]+schwab|from[[:space:]]+schwab)' "$PY_FILE" 2>/dev/null; then
      echo "SCHWAB GATE: '$PY_FILE' imports schwab. Write code -> Steve reviews -> Steve runs." >&2
      exit 2
    fi
    if grep -qE '^[[:space:]]*(import[[:space:]]+broker_schwab|from[[:space:]]+broker_schwab)' "$PY_FILE" 2>/dev/null; then
      echo "SCHWAB GATE: '$PY_FILE' imports broker_schwab, which reaches the live API." >&2
      echo "             Pre-approved readers only: broker_schwab/readers/{quote,chain}.py" >&2
      exit 2
    fi
  done
fi

# Gate 2: block inline python that references schwab
if echo "$COMMAND" | grep -qE 'python3?[[:space:]]+.*-c.*schwab'; then
  echo "SCHWAB GATE: Inline schwab import blocked." >&2
  exit 2
fi

# Gate 3 (REWRITTEN): block Steve's runner. run.sh is the sanctioned human path
# for live Schwab code; the agent invoking it would defeat the whole review step.
# The old blanket ban on scripts/ is gone — gate 1 now blocks by reachability.
#
# MATCHES AN INVOCATION, NOT A MENTION. The first cut matched the path after any
# whitespace, which blocked `git commit -m "...rewrote scripts/run.sh..."` — it
# fired twice within five minutes of install, on this file's own commit. A gate
# that blocks writing *about* the runner trains everyone to work around it, and
# a worked-around gate is worse than none. So: command position (start, or after
# a shell separator), or explicitly interpreter-invoked.
RUNNER_AT_CMD_POS='(^|[;|&(]|&&|\|\|)[[:space:]]*(\./)?([^[:space:]"'\'']*/)?scripts/run\.sh([[:space:]]|$)'
RUNNER_VIA_INTERP='(^|[[:space:];|&(])(bash|sh|source|\.)[[:space:]]+(\./)?([^[:space:]"'\'']*/)?scripts/run\.sh([[:space:]]|$)'
if echo "$COMMAND" | grep -qE "$RUNNER_AT_CMD_POS" || echo "$COMMAND" | grep -qE "$RUNNER_VIA_INTERP"; then
  echo "SCHWAB GATE: scripts/run.sh is Steve's runner. The agent does not invoke it." >&2
  exit 2
fi

# Gate 4: block token file modification
if echo "$COMMAND" | grep -qE '(>|>>|cp |mv |rm |chmod ).*tokens/'; then
  echo "SCHWAB GATE: Cannot modify token files." >&2
  exit 2
fi

# Gate 5: block schwab module execution
if echo "$COMMAND" | grep -qE 'python3?[[:space:]]+-m[[:space:]]+schwab'; then
  echo "SCHWAB GATE: Cannot run schwab as module." >&2
  exit 2
fi

exit 0
