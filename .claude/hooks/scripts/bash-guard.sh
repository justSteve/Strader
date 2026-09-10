#!/usr/bin/env bash
# bash-guard.sh — PreToolUse enforcement hook for Bash commands. [st-fsf3]
#
# Strader had no destructive-command guard at all: .claude/settings.json
# auto-allows `rm *` and `mv *`, and the only Bash hook was schwab-gate.sh,
# which gates what code REACHES, not what a command DELETES. A backup bounds
# the loss; it does not prevent it, and the Databento live legs under
# data/corpus/ can never be re-pulled at any price (verified 2026-08-13).
#
# Dialect: COO's bash-guard.sh (gt-enforce, co-n4o3r), through a verbatim copy
# of its enforcement library — same regexes for the shared cases, same deny
# JSON, same audit log. Two guards that disagree about what "destructive"
# means would be worse than one. Strader adds three rules of its own, marked
# STRADER below: the corpus tree, the zgent bridge, and `git clean -x`.
#
# Payload: reads `.tool_input.command` ONLY and fails closed on a command that
# sits at the top level instead — the shape that left schwab-gate.sh dormant
# from May to August 2026 [st-ad6p]. tests/test_bash_guard_hook.py asserts
# every deny twice (nested → deny, flat → not seen) for that reason.
#
# Fail-closed pattern and threat taxonomy adapted from
# Delanoe Pirard's claude-code-blueprint (Apache 2.0)
# https://github.com/Aedelon/claude-code-blueprint

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/../lib/enforcement-common.sh"
enforcement_trap

HOOK_NAME="bash-guard"

# --- Read and filter ----------------------------------------------------------
enforcement_read_input
enforcement_require_tool "Bash"

COMMAND=$(echo "$TOOL_INPUT" | jq -r '.command // empty')
if [[ -z "$COMMAND" ]]; then
    STRAY=$(echo "$INPUT" | jq -r '.command // empty')
    if [[ -n "$STRAY" ]]; then
        enforcement_deny "$HOOK_NAME" "payload_shape" \
            "Unrecognised payload: a command at the top level, none at .tool_input.command — refusing to guess [st-ad6p]" \
            "$STRAY"
    fi
    exit 0
fi

enforcement_detect_repo_root

# --- Privilege Escalation -----------------------------------------------------
if echo "$COMMAND" | grep -qE '(^|;|&&|\|)\s*(sudo|su|doas|pkexec)\b'; then
    enforcement_deny "$HOOK_NAME" "privilege_escalation" \
        "Privilege escalation blocked: $(echo "$COMMAND" | grep -oE '(sudo|su |doas |pkexec)[^ ]*')" \
        "$COMMAND"
fi

# --- Destructive Patterns (shared with COO) -----------------------------------
if echo "$COMMAND" | grep -qE 'rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force\s+)*-[a-zA-Z]*r[a-zA-Z]*\s+(/\s*$|/\s*;|~\s*$|~\s*;|\.\s*$|\.\s*;)'; then
    enforcement_deny "$HOOK_NAME" "destructive_pattern" \
        "Destructive rm blocked: targets /, ~, or ." "$COMMAND"
fi
if echo "$COMMAND" | grep -qE 'rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+|--recursive\s+)*-[a-zA-Z]*f[a-zA-Z]*\s+(/\s*$|/\s*;|~\s*$|~\s*;|\.\s*$|\.\s*;)'; then
    enforcement_deny "$HOOK_NAME" "destructive_pattern" \
        "Destructive rm blocked: targets /, ~, or ." "$COMMAND"
fi

if echo "$COMMAND" | grep -qE ':\(\)\s*\{.*\|.*&.*\}'; then
    enforcement_deny "$HOOK_NAME" "destructive_pattern" "Fork bomb detected" "$COMMAND"
fi
if echo "$COMMAND" | grep -qE '(^|;|&&|\|)\s*(mkfs\.[a-z0-9]+|mkfs)\s'; then
    enforcement_deny "$HOOK_NAME" "destructive_pattern" "Filesystem format command blocked" "$COMMAND"
fi
if echo "$COMMAND" | grep -qE 'dd\s+.*(if=/dev/|of=/dev/)'; then
    enforcement_deny "$HOOK_NAME" "destructive_pattern" "dd device operation blocked" "$COMMAND"
fi

# --- Per-segment rules --------------------------------------------------------
# The command is split on ; && || | and newlines and each segment is judged
# on its own arguments, so `cp -r /root/projects/COO/x $S && rm -rf $S` is not
# a false positive (co-n4o3r). A segment is the words after any leading
# `cd … &&`-style chaining has been split off.
while IFS= read -r seg; do
    seg="${seg#"${seg%%[![:space:]]*}"}"   # ltrim
    [[ -z "$seg" ]] && continue
    verb="${seg%% *}"

    # Recursive rm aimed at another repo's tree, or at /root/projects itself
    # [co-n4o3r]. Our own repo (by basename), /tmp and scratchpads are untouched.
    if [[ "$verb" == "rm" ]] && echo "$seg" | grep -qE '(^|\s)(-[a-zA-Z]*r[a-zA-Z]*|--recursive)(\s|$)'; then
        for tgt in $(echo "$seg" | grep -oE '(/root|~)/projects(/[^ /;&|"'"'"']+)?' | sort -u); do
            rel="${tgt#*/projects}"; rel="${rel#/}"
            if [[ -z "$rel" || "$rel" == "*" || "$rel" != "$ZGENT_NAME" ]]; then
                enforcement_deny "$HOOK_NAME" "destructive_pattern" \
                    "Recursive rm into another repo blocked: $tgt (this repo is $ZGENT_NAME)" \
                    "$COMMAND"
            fi
        done
        # STRADER: the sanctioned bridge is a shared dropbox, not ours to clear.
        if echo "$seg" | grep -qE '/mnt/c/Users/steve/zgent-bridge(/|\s|$)'; then
            enforcement_deny "$HOOK_NAME" "destructive_pattern" \
                "Recursive rm into the zgent bridge blocked" "$COMMAND"
        fi
    fi

    # STRADER: the corpus tree. data/corpus/ holds the Databento live legs,
    # which cannot be re-pulled (OPRA has a date wall; the plan is lapsed).
    # Any rm, mv-away, find -delete / -exec rm, shred or truncate whose target
    # names data/corpus is denied — except the writer's own residue
    # (*.tmp, *.repair-tmp, manifest.json.corrupt-*, manifest.lock), which is
    # not data. Relative or absolute, in this repo or a peer's copy of it.
    case "$verb" in
        rm|mv|shred|truncate|find)
            if echo "$seg" | grep -qE '(^|[ =/"'"'"'])(data/corpus|/root/projects/[^ /]+/data/corpus)(/|\s|$)'; then
                hit=true
                if [[ "$verb" == "rm" || "$verb" == "mv" ]]; then
                    hit=false
                    for tgt in $(echo "$seg" | grep -oE '[^ "'"'"']*data/corpus[^ "'"'"']*'); do
                        case "$tgt" in
                            *.tmp|*.repair-tmp|*/manifest.json.corrupt-*|*/manifest.lock) ;;
                            *) hit=true ;;
                        esac
                    done
                elif [[ "$verb" == "find" ]]; then
                    echo "$seg" | grep -qE '(\s-delete(\s|$)|-exec\s+rm\b|-execdir\s+rm\b)' || hit=false
                fi
                if [[ "$hit" == "true" ]]; then
                    enforcement_deny "$HOOK_NAME" "corpus_tree" \
                        "Destructive $verb on data/corpus blocked — the live tape is not re-pullable; a corpus delete is Steve's action [st-fsf3]" \
                        "$COMMAND"
                fi
            fi
            ;;
    esac

    # STRADER: `git clean -x` / `-X` removes IGNORED files — data/corpus is
    # ignored, so this is a corpus delete wearing git's clothes.
    if [[ "$verb" == "git" ]] && echo "$seg" | grep -qE '^git\s+clean\b' \
        && echo "$seg" | grep -qE '(\s-[a-zA-Z]*[xX][a-zA-Z]*(\s|$))'; then
        enforcement_deny "$HOOK_NAME" "corpus_tree" \
            "git clean -x/-X blocked: it removes ignored files, and data/corpus is ignored [st-fsf3]" \
            "$COMMAND"
    fi
done < <(printf '%s\n' "$COMMAND" | sed -E 's/(&&|\|\||;|\|)/\n/g')

# --- Pipe-to-Shell ------------------------------------------------------------
if echo "$COMMAND" | grep -qE '(curl|wget)\s.*\|\s*(bash|sh|zsh|dash)'; then
    enforcement_deny "$HOOK_NAME" "pipe_to_shell" \
        "Pipe-to-shell blocked: remote code execution risk" "$COMMAND"
fi

# --- Obfuscation --------------------------------------------------------------
if echo "$COMMAND" | grep -qE 'eval\s+\$'; then
    enforcement_deny "$HOOK_NAME" "obfuscation" \
        "eval with variable blocked: indirect execution risk" "$COMMAND"
fi
if echo "$COMMAND" | grep -qE 'base64\s+(-d|--decode).*\|\s*(bash|sh)'; then
    enforcement_deny "$HOOK_NAME" "obfuscation" "base64 decode to shell blocked" "$COMMAND"
fi

# --- All checks passed --------------------------------------------------------
exit 0
