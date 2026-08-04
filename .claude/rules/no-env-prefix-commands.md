# Rule: No Env-Assignment Prefixes in Bash Commands

Claude Code permission rules prefix-match the **literal command string**. A
command written as

```bash
SCRATCH=/tmp/... && NODE_PATH=$SCRATCH/node_modules node tools/drill_page_check.mjs ...
```

starts with `SCRATCH=`, matches no `Bash(...)` allow rule — not even
`Bash(node *)`, which is allowed — and prompts Steve every time. He has ruled
the prompt intrusive (2026-08-04, st-df6f).

## Do

- Run node page checks through the wrapper, which the existing `Bash(bash *)`
  allow already covers and which derives `NODE_PATH` from the target's
  directory:

  ```bash
  bash tools/nodecheck.sh tools/drill_page_check.mjs "$SCRATCH/drill-0731.html"
  ```

- In general: start commands with the program name the allow-list knows.
  If an env var is genuinely needed, prefer a checked-in wrapper script that
  sets it internally.

## Don't

- Don't lead a Bash command with `VAR=value` assignments (inline or `&& `-chained).
- Don't ask for `Bash(SCRATCH=*)`-style allow rules — an assignment prefix can
  hide *any* command behind it, so such a rule is an open hole, and it was
  deliberately not added.
