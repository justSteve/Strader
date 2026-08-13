#!/bin/bash
# gc-mail-stub.sh — PreToolUse hook for Bash
#
# Gas City was deprecated and deleted 2026-07-29 (co-uugmn). `gc mail` was dead
# in BOTH directions for weeks before anyone noticed, because it failed the two
# worst ways a channel can fail: silently (cwd city resolution — Strader is
# out-of-tree, so every recipient failed identically) and slowly (a cold-start
# subprocess timeout on the very invocation a session-start hook makes). A memo
# sent through it went nowhere and said nothing.
#
# The binary is still installed at /usr/local/bin/gc — 104MB of it — so a `gc`
# call today does NOT fail fast. It resolves. That is the bug this stub exists
# to make loud: reaching for `gc` is now an error with an answer attached, not a
# silent no-op.
#
# Deliberately NOT solved with a permissions allow-rule: per
# .claude/rules/no-env-prefix-commands.md, "a `gc` call is a bug, and the prompt
# is the signal. Fix the caller instead of silencing the prompt." This hook is
# the stronger form of that reasoning — it blocks rather than prompts, because
# there is no longer any correct `gc` invocation.
#
# Exit 0 = allow, Exit 2 = block (message on stderr, shown to the agent).
# Authorizing bead: st-75z0.

set -uo pipefail

INPUT=$(cat)

# Accept either hook payload shape: current Claude Code nests the command under
# .tool_input; older/other shapes put it at the top level. Checking both costs
# nothing and prevents this gate from silently no-opping if the shape changes.
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // .command // empty' 2>/dev/null)

if [ -z "$COMMAND" ]; then
  exit 0
fi

# Match `gc` only where it is the program being run: at the start of the string,
# or immediately after a shell separator ( ; | & ( { newline ), optionally via an
# absolute path or sudo. The trailing boundary keeps `gcc`, `gcloud`, `gc.py`,
# `grep gc` and `git commit -m "gc mail"` from tripping it.
if echo "$COMMAND" | grep -qE '(^|[;&|({]|[[:space:]]&&|[[:space:]]\|\|)[[:space:]]*(sudo[[:space:]]+)?(/usr/local/bin/)?gc([[:space:]]|$)'; then
  cat >&2 <<EOF
GC-MAIL STUB — BLOCKED: \`gc\` is dead. Gas City was deprecated and deleted
2026-07-29 (co-uugmn), and gc mail with it. The binary still resolves, so this
call would have "succeeded" its way into going nowhere, silently — which is
exactly how a desk-migration request sat 6 days and a flashcard question 19.

Blocked command: $COMMAND

Use the A2A file channel instead:
  1. Write the memo:  docs/a2a/YYYY-MM-DD-strader-to-<peer>-<slug>.md
  2. Append one MEMO line to docs/a2a/inbox.md (and to the PEER's inbox — that
     is the bell), in the SAME commit as the memo.
  3. Format contract:  docs/a2a/inbox.md  (header section)
     Receipt rules:    docs/a2a/receipt-protocol.md

If you were only checking for mail, run:  python3 tools/a2a_inbox.py

Do not route around this with an allow-rule. There is no correct \`gc\`
invocation; a caller that still reaches for one is the thing to fix.
EOF
  exit 2
fi

exit 0
