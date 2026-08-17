# Rule: Don't Lead a Bash Command With an Assignment

Permission rules prefix-match the literal command string, so a command that
begins with `VAR=value` matches no allow rule and prompts Steve every time —
60 of 106 prompts across six sessions were this shape (st-cmfc, 2026-08-05).

- Inline the path: `timeout 600 .venv/bin/python scripts/x.py --out /tmp/claude-0/.../scratchpad/x.html`
  — not `SCRATCH=… && timeout …`.
- Inline or pipe a substitution: `find . -name x -exec grep foo {} +` — not
  `F=$(find …); grep foo "$F"`.
- Node scripts needing `NODE_PATH`: `bash tools/nodecheck.sh <script> …`.
- `TZ=America/Chicago date …` is the one allowed exception.
- Do not request blanket assignment prefixes, `kill`/`pkill` (live feeds run
  here — a human should see a kill), or `gc …` (deprecated; the hook blocks
  it). Loops and conditionals prompt; put a repeated loop in `tools/`.
