# Rule: `grep` and `find` in the Bash Tool Are Shims — Three Bans

In Bash tool calls, `grep`, `find` and `rg` are shell functions wrapping the
Claude Code binary (`ugrep` / `bfs`), not GNU tools. On 2026-08-15 two of them
took the whole distro down twice in four minutes (18 GB grep, OOM).

1. **No `-o` with bounded-repetition context** (`grep -oE '.{0,120}X.{0,120}'`)
   under the shim — it allocates without bound. Use `command grep …`, or drop
   `-o` and read the line.
2. **Never `find /`** — it walks every 9p mount (a 4 TB archive included).
   Root every find at or below `/root/projects`, `/root/.claude`, `/var/moo`,
   `/etc`, or a named `/mnt/c/...` path.
3. **A "moved to background after 120s" grep/find is still running and still
   allocating.** Kill it (`pgrep -x 2.1.233`), then rewrite the command.

Also: shimmed `grep -r` skips gitignored files, so for "is anything left?"
sweeps use `command grep -r`. Full post-mortem:
`docs/retired-rules/shell-shim-hazards.md`.
