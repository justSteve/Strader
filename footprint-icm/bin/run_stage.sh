#!/usr/bin/env bash
# run_stage.sh — call the model for one stage, bounded to its folder. [st-h0xx]
#
# Usage: run_stage.sh <run-folder>/<stage-dir> [--smoke]
#
# The stage directory holds prompt.md (the system prompt) and input.txt (the
# whole user turn). The model runs with no tools, no settings files, no
# session persistence, from that directory as its working directory, and
# ONLY after this script has checked that no CLAUDE.md sits in any parent of
# it and that no auto-memory folder exists for it — so nothing enters the
# model's context from outside the folder except the harness's own fixed
# text (about 3,500 tokens, measured 2026-08-28; cached).
#
# Output: output.md (the model's text), usage.json (the harness's full JSON
# reply: tokens, cache reads and writes, list-price cost per model),
# check.json (what this script verified before the call).
#
# --smoke replaces prompt.md/input.txt with a one-word exchange to prove
# login, nesting and the meter before any real prompt exists.
set -euo pipefail

STAGE="${1:?usage: run_stage.sh <stage-dir> [--smoke]}"
MODE="${2:-}"
MODEL="${ICM_MODEL:-claude-opus-5}"
cd "$STAGE"
STAGE="$(pwd -P)"

# 1. no project instructions reachable from here
found=""
d="$STAGE"
while [ "$d" != "/" ]; do
    for f in CLAUDE.md AGENTS.md .claude; do
        [ -e "$d/$f" ] && found="$found $d/$f"
    done
    d="$(dirname "$d")"
done
if [ -n "$found" ]; then
    echo "[REFUSED] run_stage: project instructions reachable from $STAGE:$found" >&2
    exit 2
fi
# 2. no auto-memory for this working directory
mem_key="$(printf '%s' "$STAGE" | sed 's#/#-#g')"
mem_dir="$HOME/.claude/projects/$mem_key"
if [ -d "$mem_dir/memory" ]; then
    echo "[REFUSED] run_stage: auto-memory exists for this folder at $mem_dir/memory" >&2
    exit 2
fi

if [ "$MODE" = "--smoke" ]; then
    PROMPT="You answer with exactly one word."
    INPUT="Reply with the single word OK."
else
    [ -f prompt.md ] || { echo "[REFUSED] run_stage: no prompt.md in $STAGE" >&2; exit 2; }
    [ -f input.txt ] || { echo "[REFUSED] run_stage: no input.txt in $STAGE" >&2; exit 2; }
    PROMPT="$(cat prompt.md)"
    INPUT="$(cat input.txt)"
fi

cat > check.json <<EOF
{"stage": "$STAGE", "model": "$MODEL", "mode": "${MODE:-stage}", "parents_clean": true,
 "auto_memory_absent": true, "checked_at": "$(TZ=America/Chicago date -Iseconds)"}
EOF

# 3. the call. --tools "" disables every tool; --setting-sources "" loads no
#    settings file; the working directory is the stage folder. Not --bare:
#    that skips the login and the call fails "Not logged in" (measured).
printf '%s' "$INPUT" | claude -p \
    --setting-sources "" --tools "" --model "$MODEL" --no-session-persistence \
    --system-prompt "$PROMPT" --output-format json > usage.json
python3 - "$STAGE" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads((p / "usage.json").read_text())
if d.get("is_error"):
    print(f"[REFUSED] run_stage: model call failed: {d.get('result')}", file=sys.stderr)
    sys.exit(2)
(p / "output.md").write_text((d.get("result") or "") + "\n", encoding="utf-8")
u = d.get("usage") or {}
print(f"run_stage {p.name}: ${d.get('total_cost_usd', 0):.4f} list, "
      f"out {u.get('output_tokens')} in {u.get('input_tokens')} "
      f"cache-read {u.get('cache_read_input_tokens')} cache-write {u.get('cache_creation_input_tokens')}, "
      f"{d.get('duration_ms', 0)/1000:.1f}s")
PY
