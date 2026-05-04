#!/usr/bin/env bash
# Session start hook — directs zgent to run /tap-in before responding.
# Part of the session-rituals convention. See conventions/session-rituals.md.
#
# The /tap-in skill handles all session initialization: identity loading,
# beads state, DaysActivity archival, warm-start snapshot. This hook's
# only job is to make that invocation non-optional.

set -euo pipefail

ZGENT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
ZGENT_NAME=$(basename "$ZGENT_DIR")
SESSION_LOG="/var/moo/logs/sessions.jsonl"
SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"

# Detect warm vs cold start
START_TYPE="cold"
if [ -f "$ZGENT_DIR/.claude/state/snapshot.json" ]; then
    START_TYPE="warm"
fi

# Log session start
jq -n -c \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" \
    --arg sid "$SESSION_ID" \
    --arg zgent "$ZGENT_NAME" \
    --arg event "session_start" \
    --arg start_type "$START_TYPE" \
    --arg harness "${AUTOMUX_HARNESS:-0}" \
    '{ts:$ts, session_id:$sid, zgent:$zgent, event:$event, start_type:$start_type, harness:$harness}' \
    >> "$SESSION_LOG" 2>/dev/null || true

# Harness bypass: when AUTOMUX_HARNESS=1, skip the mandatory /tap-in injection
# so harness-driven scenarios get the agent's natural cold-start behavior with
# CLAUDE.md and .claude/rules/* loaded, not a 30-second tap-in detour.
# See bead co-6li.
if [[ "${AUTOMUX_HARNESS:-0}" == "1" ]]; then
    exit 0
fi

cat <<EOF
# Session Ritual — MANDATORY

You MUST run /tap-in before responding to the user's first message.
Do not skip this. Do not summarize beads or context from memory instead.
Invoke the /tap-in skill now.

After /tap-in completes and you have responded to the user's first message,
start the checkpoint loop: /loop 30m /checkpoint
This auto-saves session state every 30 minutes as a safety net.
Do not ask the user whether to start it — just start it.

Start type: ${START_TYPE}
Zgent: ${ZGENT_NAME}
EOF
