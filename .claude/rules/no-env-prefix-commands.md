# Rule: Don't Lead a Bash Command With an Assignment

Claude Code permission rules prefix-match the **literal command string**. A
command that begins with `VAR=value` matches no `Bash(...)` allow rule — not
even when the program that follows is fully allowed — so it prompts Steve every
single time.

Measured 2026-08-05 across the six most recent Strader sessions: **106 prompting
Bash calls, 60 of them this one shape** (`SCRATCH=`, `TZ=`, `F=$(...)`). It is by
far the biggest source of interruption in this repo (st-cmfc, generalizing
st-df6f which fixed only the `node` case).

## Do — inline the path, don't assign it

```bash
# Prompts (leads with an assignment):
SCRATCH=/tmp/claude-0/.../scratchpad && timeout 600 .venv/bin/python scripts/orderflow_drill.py --out $SCRATCH/drill.html

# Runs clean (leads with `timeout`, which is allowed):
timeout 600 .venv/bin/python scripts/orderflow_drill.py --out /tmp/claude-0/.../scratchpad/drill.html
```

Yes, the literal path is long. Type it anyway — it costs you characters and
costs Steve nothing. Every allowed leading program works this way:
`timeout`, `.venv/bin/python`, `.venv/bin/python3`, `node`, `python3`, `bash`,
`git`, `bd`, `curl`, `ps`, `jq`.

For node scripts needing `NODE_PATH`, use the wrapper, which derives it itself:

```bash
bash tools/nodecheck.sh tools/drill_page_check.mjs /tmp/claude-0/.../scratchpad/page.html
```

For a command substitution you were going to assign, inline it or pipe it:

```bash
# Prompts:  F=$(find . -name x); grep foo "$F"
# Clean:    find . -name x -exec grep foo {} +
```

## Allowed exceptions (already in settings.json)

- `TZ=America/Chicago date ...` — pinned to `date`, so it is not a general
  assignment door. Use it freely for CT timestamps.

## Deliberately NOT allowed — do not request these

- **Blanket assignment prefixes** (`Bash(SCRATCH=*)`, `Bash(VAR=*)`) — an
  assignment prefix can hide *any* command behind it. That rule is a hole, not
  a convenience.
- **`kill` / `pkill`** — this box runs live capture feeds; a human should see
  a process being killed. They are rare enough that prompting costs little.
- **`gc ...`** — Gas City is deprecated and deleted. A `gc` call is a bug, and
  the prompt is the signal. Fix the caller instead of silencing the prompt.

## Shapes that still prompt, and that is fine

Shell loops and conditionals (`for ...`, `while ...`, `if ...`) lead with a
keyword, not a program, so they prompt. They are uncommon; prefer a small
checked-in script under `tools/` when you find yourself writing the same loop
twice.
