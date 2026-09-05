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

# The identity comes off STDIN, not the environment. CLAUDE_SESSION_ID is not
# exported into a SessionStart hook, so `${CLAUDE_SESSION_ID:-unknown}` wrote
# the literal "unknown" on every row this log has ever held — measured
# 2026-09-05, 12 of 12 Strader rows — and no session was individually
# identifiable. This is the schwab-gate failure again: read the wrong field,
# find nothing, carry on silently. `-t 0` so an interactive run without a
# payload cannot hang here, and every fallback is still "unknown".
PAYLOAD=""
if [ ! -t 0 ]; then
    PAYLOAD="$(timeout 2 cat || true)"
fi
SESSION_ID="unknown"
if [ -n "$PAYLOAD" ]; then
    SESSION_ID="$(printf '%s' "$PAYLOAD" | jq -r '.session_id // "unknown"' 2>/dev/null || echo unknown)"
fi
[ -z "$SESSION_ID" ] && SESSION_ID="unknown"

# Cold vs warm. The warm branch tested for .claude/state/snapshot.json, which
# the checkpoint loop used to write — and that loop is DISCONTINUED
# (knowledge/checkpoint-loop-discontinued.md). The file has never existed since,
# so start_type was "cold" on 12 of 12 rows and the field carried no
# information. It now reports the harness's own `source` (startup / resume /
# clear / compact), which is the distinction the field was reaching for.
START_TYPE="cold"
if [ -n "$PAYLOAD" ]; then
    HOOK_SOURCE="$(printf '%s' "$PAYLOAD" | jq -r '.source // ""' 2>/dev/null || echo "")"
    case "$HOOK_SOURCE" in
        resume|clear|compact) START_TYPE="$HOOK_SOURCE" ;;
        startup|"")           START_TYPE="cold" ;;
        *)                    START_TYPE="$HOOK_SOURCE" ;;
    esac
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

Start type: ${START_TYPE}
Zgent: ${ZGENT_NAME}
EOF
