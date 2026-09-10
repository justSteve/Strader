#!/usr/bin/env bash
# enforcement-common.sh — shared functions for enforcement hooks
# Sourced by each enforcement hook, not executed directly.
#
# STRADER COPY [st-fsf3, 2026-09-10]: verbatim from COO/.claude/hooks/lib/
# enforcement-common.sh so the two zgents' guards share one dialect — the same
# deny JSON, the same audit row shape, the same /var/moo/audit/enforcement.jsonl
# (rows carry zgent: Strader). If COO changes its library, re-copy; do not fork.
#
# Fail-closed pattern and threat taxonomy adapted from
# Delanoe Pirard's claude-code-blueprint (Apache 2.0)
# https://github.com/Aedelon/claude-code-blueprint

# --- Fail-Closed Trap --------------------------------------------------------
enforcement_trap() {
    trap '__enforcement_deny "Hook error - fail-closed"' ERR
}

__enforcement_deny() {
    local reason="${1:-unknown error}"
    # HOOK_EVENT_NAME may not be set if the trap fires before enforcement_read_input;
    # fall back to PreToolUse (every current enforcement hook is registered there).
    local event="${HOOK_EVENT_NAME:-PreToolUse}"
    jq -n -c --arg r "$reason" --arg e "$event" \
        '{hookSpecificOutput:{hookEventName:$e,permissionDecision:"deny",permissionDecisionReason:$r}}'
    exit 1
}

# --- Input Parsing ------------------------------------------------------------
enforcement_read_input() {
    INPUT=$(cat)
    if [[ -z "$INPUT" ]]; then
        exit 0
    fi

    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
    TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}')
    SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')
    # Claude Code passes the hook event name on stdin; keep it for deny output.
    HOOK_EVENT_NAME=$(echo "$INPUT" | jq -r '.hook_event_name // "PreToolUse"')
}

# --- Tool Name Filter ---------------------------------------------------------
enforcement_require_tool() {
    local match=false
    for expected in "$@"; do
        if [[ "$TOOL_NAME" == "$expected" ]]; then
            match=true
            break
        fi
    done
    if [[ "$match" == "false" ]]; then
        exit 0
    fi
}

# --- Project Root Detection ---------------------------------------------------
enforcement_detect_repo_root() {
    REPO_ROOT="${CLAUDE_PROJECT_DIR:-}"
    if [[ -z "$REPO_ROOT" ]]; then
        REPO_ROOT=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
    fi
    if [[ -z "$REPO_ROOT" ]]; then
        REPO_ROOT="$PWD"
    fi
    ZGENT_NAME=$(basename "$REPO_ROOT")
}

# --- Bypass Check -------------------------------------------------------------
ENFORCEMENT_BYPASS="${GT_ENFORCEMENT_BYPASS:-0}"

# --- Logging ------------------------------------------------------------------
# Overridable by env so test suites can redirect their fixtures out of the live
# audit trail. While this was a bare assignment, 34% of enforcement.jsonl was
# test fixtures (772 of 2,281 rows measured 2026-08-16), the file auto-rotates
# at 1 MB, and every nightly run of the hook suites discarded that much real
# enforcement history to make room for synthetic rows [co-03ojd.4, sweep D-F9].
ENFORCEMENT_LOG="${ENFORCEMENT_LOG:-/var/moo/audit/enforcement.jsonl}"

enforcement_log() {
    local hook="$1"
    local action="$2"
    local tool="$3"
    local trigger="$4"
    local detail="$5"
    local preview="$6"

    mkdir -p "$(dirname "$ENFORCEMENT_LOG")" 2>/dev/null || true

    # Auto-rotate at 1MB
    if [[ -f "$ENFORCEMENT_LOG" ]]; then
        local size
        size=$(stat -c%s "$ENFORCEMENT_LOG" 2>/dev/null || echo "0")
        if [[ "$size" -gt 1048576 ]]; then
            mv "$ENFORCEMENT_LOG" "${ENFORCEMENT_LOG}.old" 2>/dev/null || true
        fi
    fi

    jq -n -c \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" \
        --arg sid "$SESSION_ID" \
        --arg zgent "${ZGENT_NAME:-unknown}" \
        --arg hook "$hook" \
        --arg action "$action" \
        --arg tool "$tool" \
        --arg trigger "$trigger" \
        --arg detail "$detail" \
        --arg preview "${preview:0:200}" \
        '{ts:$ts,session_id:$sid,zgent:$zgent,hook:$hook,action:$action,tool:$tool,trigger:$trigger,detail:$detail,input_preview:$preview}' \
        >> "$ENFORCEMENT_LOG" 2>/dev/null || true
}

# --- Deny + Log helper --------------------------------------------------------
enforcement_deny() {
    local hook="$1"
    local trigger="$2"
    local detail="$3"
    local preview="${4:-}"

    if [[ "$ENFORCEMENT_BYPASS" == "1" ]]; then
        enforcement_log "$hook" "BYPASS" "$TOOL_NAME" "$trigger" "$detail" "$preview"
        exit 0
    fi

    enforcement_log "$hook" "deny" "$TOOL_NAME" "$trigger" "$detail" "$preview"
    local event="${HOOK_EVENT_NAME:-PreToolUse}"
    jq -n -c --arg r "$detail" --arg e "$event" \
        '{hookSpecificOutput:{hookEventName:$e,permissionDecision:"deny",permissionDecisionReason:$r}}'
    exit 1
}

# --- Allow + Log helper -------------------------------------------------------
# Emits a terminal PreToolUse allow, which settles the permission decision
# without a prompt. Measured against the 2.1.232 binary: a hook returning
# permissionDecision "allow" yields hookPermissionResult {behavior:"allow"},
# and the aggregation order is deny > defer > ask > allow — so any guard that
# denies still wins over this. Use only where a prompt cannot be answered.
enforcement_allow() {
    local hook="$1"
    local trigger="$2"
    local detail="$3"
    local preview="${4:-}"

    enforcement_log "$hook" "allow" "$TOOL_NAME" "$trigger" "$detail" "$preview"
    local event="${HOOK_EVENT_NAME:-PreToolUse}"
    jq -n -c --arg r "$detail" --arg e "$event" \
        '{hookSpecificOutput:{hookEventName:$e,permissionDecision:"allow",permissionDecisionReason:$r}}'
    exit 0
}

# --- Warn (systemMessage, exit 0) helper --------------------------------------
enforcement_warn() {
    local hook="$1"
    local trigger="$2"
    local detail="$3"
    local preview="${4:-}"

    enforcement_log "$hook" "warn" "$TOOL_NAME" "$trigger" "$detail" "$preview"
    jq -n -c --arg h "$hook" --arg d "$detail" \
        '{systemMessage:("[\($h)] \($d)")}'
    exit 0
}
