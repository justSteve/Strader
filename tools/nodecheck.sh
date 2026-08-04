#!/usr/bin/env bash
# nodecheck.sh — run a checked-in node script without env-assignment prefixes. [st-df6f]
#
# Usage:
#   bash tools/nodecheck.sh <script.mjs> <target-file> [extra args...]
#   bash tools/nodecheck.sh tools/drill_page_check.mjs "$SCRATCH/drill-0731.html"
#
# Why this exists: Claude Code permission rules prefix-match the literal
# command string. `Bash(node *)` is in the allow-list, but a command written as
# `SCRATCH=... && NODE_PATH=... node ...` starts with an assignment, matches no
# rule, and prompts every time (Steve ruled the prompt intrusive, 2026-08-04).
# This wrapper is invoked as `bash tools/...`, which the checked-in allow-list
# already covers, and it derives NODE_PATH itself so callers never need the
# assignment prefix.
#
# NODE_PATH resolution, in order:
#   1. a NODE_PATH already exported by the caller wins;
#   2. else <target-file's directory>/node_modules, if it exists (the page
#      checks keep their deps beside the page in the session scratchpad);
#   3. else unset — plain node resolution.
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: bash tools/nodecheck.sh <script.mjs> <target-file> [args...]" >&2
    exit 2
fi
script="$1"; target="$2"; shift 2

[[ -f "$script" ]] || { echo "nodecheck: no such script: $script" >&2; exit 2; }
[[ -e "$target" ]] || { echo "nodecheck: no such target: $target" >&2; exit 2; }

if [[ -z "${NODE_PATH:-}" ]]; then
    tdir="$(cd "$(dirname "$target")" && pwd)"
    if [[ -d "$tdir/node_modules" ]]; then
        export NODE_PATH="$tdir/node_modules"
    fi
fi

exec node "$script" "$target" "$@"
