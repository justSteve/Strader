# Strader Worker Context

> **Context Recovery**: Run `bd ready` to see available work after compaction or new session.

## Startup Protocol

1. Check for available work: `bd ready`
2. If work is available → claim it with `bd update <id> --status in_progress` and execute
3. If nothing available → wait for user instructions

## Key Commands

- `bd ready` - Find available work (no blockers)
- `bd create -t "title"` - Create a new bead for untracked work
- `bd update <id> --status in_progress` - Claim work
- `bd close <id>` - Mark work complete

## Session Close Protocol

Before signaling completion:
1. `git status` (check what changed)
2. `git add <files>` (stage code changes)
3. `git commit -m "..."` (commit code)
4. `git push` (push to remote)

## What This Is NOT

This is an independent zgent, not a Gas City managed agent. Do not use `gt` commands (`gt mol`, `gt mail`, `gt feed`, `gt done`, `gt prime`). Those are for Gas City polecats/workers. Use `bd` for all beads operations.
