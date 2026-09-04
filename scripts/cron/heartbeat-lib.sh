#!/usr/bin/env bash
# heartbeat-lib.sh — the one heartbeat writer for scheduled jobs. [co-8b60y]
#
# Source it, then either:
#   hb_write <file> <status> <detail> [extra-json-object]
#       one atomic write of {ts, status, detail, ...extra}
#   hb_init <file> [note]
#       writes status "running" now and arms an EXIT trap: when the script
#       ends without having written a terminal status, the trap writes "ok"
#       (rc 0) or "failed" (rc≠0, detail "exit rc=N"). HB_DETAIL, if set when
#       the script exits, is appended to that detail. A trap already armed is
#       chained, not replaced; a trap armed AFTER hb_init replaces this one, so
#       arm hb_init last or call _hb_exit_trap first in your own trap.
#   hb_done <status> <detail> [extra-json-object]
#       the terminal write for the file hb_init armed.
#   hb_path <job>   ->  $HB_STATE_DIR/<job>.json  (default /var/moo/state)
#
# THE FOUR STATES, read by COO/factory/scripts/heartbeat-check.sh:
#   ok        the job did its work
#   degraded  the job ran and could not do all of it for a stated, expected
#             reason that is not a defect — a mount absent, a token expired,
#             the network away. Reported on its own line; never a bead.
#   failed    the job ran and did not do its work. A bead.
#   running   the job started and has not ended. Older than the catalog's
#             max_run_min (SCHEDULE.md, default 120) it is read as
#             "died mid-run": a kill -9, an OOM, a timeout(1) reaping the
#             wrapper — none of which run an EXIT trap.
# Anything else is not a state and is written as "failed" with the bad word in
# the detail, so a typo cannot read as healthy.
#
# WHY jq AND NOT printf. Five writers used to build the JSON with printf; a
# double quote in the detail — an error message, a path — made the file
# unreadable, which the checker reports as UNHEALTHY on a job that worked.
# jq constructs the document from typed arguments and cannot emit non-JSON.
# The write is tmp+mv in the same directory so a reader never sees half a file.
#
# TWO COPIES ON PURPOSE. COO/factory/scripts/heartbeat-lib.sh and
# Strader/scripts/cron/heartbeat-lib.sh are byte-identical — COO's
# tests/test-heartbeat-lib.sh asserts it. A Strader cron must not depend on the
# COO checkout, and the job whose news is "the venv is broken" cannot need the
# venv, so this is bash and jq only.

[[ -n "${_HB_LIB_LOADED:-}" ]] && return 0
_HB_LIB_LOADED=1

HB_STATE_DIR="${HB_STATE_DIR:-/var/moo/state}"
_HB_FILE=""; _HB_TERMINAL=0; _HB_STARTED=""; _HB_CHAINED=""

hb_path() { printf '%s/%s.json\n' "$HB_STATE_DIR" "$1"; }

_hb_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# hb_write <file> <status> <detail> [extra-json-object]
hb_write() {
    local file="$1" status="$2" detail="${3:-}" extra="${4:-}" tmp dir ts
    case "$status" in
        ok|degraded|failed|running) ;;
        *) detail="not a heartbeat state: '$status' — $detail"; status=failed ;;
    esac
    dir=$(dirname "$file"); mkdir -p "$dir" 2>/dev/null
    tmp="$dir/.$(basename "$file").tmp.$$"
    ts=$(_hb_now)
    if command -v jq >/dev/null 2>&1; then
        if [[ -n "$extra" ]] && ! jq -e 'type == "object"' <<<"$extra" >/dev/null 2>&1; then
            detail="$detail [extra fields dropped: not a JSON object]"; extra=""
        fi
        jq -n --arg ts "$ts" --arg st "$status" --arg d "$detail" --argjson x "${extra:-{\}}" \
              '{ts:$ts, status:$st, detail:$d} + $x' >"$tmp" 2>/dev/null
    else
        # No jq on the box: still leave a file the checker can parse.
        local esc=${detail//\\/\\\\}; esc=${esc//\"/\\\"}; esc=${esc//$'\n'/ }
        printf '{"ts":"%s","status":"%s","detail":"%s"}\n' "$ts" "$status" "$esc" >"$tmp"
    fi
    if ! mv -f "$tmp" "$file" 2>/dev/null; then rm -f "$tmp" 2>/dev/null; return 1; fi
    [[ "$file" == "$_HB_FILE" && "$status" != running ]] && _HB_TERMINAL=1
    return 0
}

# The EXIT trap hb_init arms. Reads the script's exit status, writes the
# terminal heartbeat if none was written, then runs whatever trap was armed
# before hb_init. Never changes the exit status.
_hb_exit_trap() {
    local rc=$?
    if (( ! _HB_TERMINAL )) && [[ -n "$_HB_FILE" ]]; then
        if (( rc == 0 )); then
            hb_write "$_HB_FILE" ok "${HB_DETAIL:-completed}" "{\"rc\":0,\"started\":\"$_HB_STARTED\"}"
        else
            hb_write "$_HB_FILE" failed "exit rc=$rc${HB_DETAIL:+ — $HB_DETAIL}" "{\"rc\":$rc,\"started\":\"$_HB_STARTED\"}"
        fi
    fi
    [[ -n "$_HB_CHAINED" ]] && eval "$_HB_CHAINED"
    return 0
}

# hb_init <file> [note]
hb_init() {
    local prev
    _HB_FILE="$1"; _HB_TERMINAL=0; _HB_STARTED=$(_hb_now)
    prev=$(trap -p EXIT)
    if [[ -n "$prev" ]]; then
        prev=${prev#trap -- }; prev=${prev% EXIT}
        eval "_HB_CHAINED=$prev"
    else
        _HB_CHAINED=""
    fi
    trap '_hb_exit_trap' EXIT
    hb_write "$_HB_FILE" running "started ${_HB_STARTED}${2:+ — $2}" "{\"started\":\"$_HB_STARTED\"}"
}

# hb_done <status> <detail> [extra-json-object]
hb_done() {
    [[ -n "$_HB_FILE" ]] || return 1
    local extra="${3:-}"
    if [[ -z "$extra" ]]; then extra="{\"started\":\"$_HB_STARTED\"}"; fi
    hb_write "$_HB_FILE" "$1" "${2:-}" "$extra"
}
