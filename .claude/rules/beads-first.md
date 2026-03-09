# Rule: Beads-First

You are a beads-first entity. Substantive work requires bead authorization. Always reference the bead ID in your commit messages when performing substantive work.

## Gate Check

1. Is there an open bead in `.beads/` that covers this work?
2. If yes, proceed. Reference the bead ID in your commit messages.
3. If no, decide: does this work need a bead?
   - **Create one yourself** if the work is non-trivial (multi-file changes, new features, architectural decisions, anything you'd want to track).
   - **Proceed without one** if the work is minor housekeeping (fixing a typo, updating a status field, small config tweak).
   - When in doubt, create the bead. It's cheap and the audit trail is valuable.

## What Counts as Substantive Work

- Creating, modifying, or deleting files
- Running commands that change system or project state
- Installing dependencies
- Modifying configuration

## What Does NOT Require a Bead

- Reading files to understand context
- Answering questions about the codebase
- Discussing approach or planning (though planning should lead to a bead)
- Running read-only diagnostic commands

## Bead Creation

When you create a bead yourself, append it to `.beads/issues.jsonl` following the standard format. Use your judgment on `type` (epic vs task) and write a clear `description`. You own this decision — don't defer to the operator on bead creation, sub-task breakdown, or ID assignment.
