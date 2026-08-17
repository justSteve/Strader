# Strader — SPX Options Trading Intelligence

Steve's intermediary upon SPX options trading. `CLAUDE.md` carries the standing
context (profile, instruments, gates); this file is the per-session protocol.

> **Context Recovery**: run `bd ready` after compaction or on a new session.

## Startup Protocol

1. `/tap-in` — identity, knowledge bundle, beads state, peer channel, session context
2. In-progress work: `bd list --status in_progress`
3. Ready work: `bd propername --ready` (name-first) or `bd ready`
4. An empty ready queue is **not** a reason to idle. The obvious next step is
   pre-authorized — if you can honestly write "I can do this without you," the
   turn ends with it done, not offered. Steve, 2026-07-31 (auto-memory
   `feedback_act_on_cheap_reversible_actions.md`): *"please, please, please
   learn not to ask obvious and trivial questions. same for commits. what is the
   cost/risk of a commit?"* He named this the **Obvious Doctrine** on
   2026-08-13. Reserve questions for destructive or irreversible actions —
   deletes, order placement, cross-repo writes — and for real scope forks.

## Key Commands

```bash
bd ready                     # available work
bd create "Strader: <title>" --type task -d "<description>"
                             # NEVER `bd create task "…"` — bd takes ONE positional
                             # (the title); a leading 'task' word silently drops
                             # the real title [st-kq8]
bd update <id> --claim       # claim before starting
bd propername <id> "Name"    # ~3-word ProperName on every substantive bead
bd close <id>                # mark done
```

Bead prefix: **`st`**. Commit messages cite the authorizing bead. Present beads
and commits to Steve **name-first**, ID parenthetical
(retired rule; kept in `docs/retired-rules/proper-name-presentation.md`).

## Session Close Protocol

Standing commit-and-push authority, Steve 2026-08-02 — recorded in `CLAUDE.md`
§Session Completion. Commit and push without asking; raise a commit only when
there is real risk and the interruption is warranted.

```bash
bd close <completed-ids>
git add <explicit paths>              # never git add -A — peers share this tree
git commit -m "… [st-XXXX]" -- <the same paths>
git pull --rebase && git push         # work is not complete until push succeeds
```

Then run `/handoff`.

## The A2A Ledger

`docs/a2a/inbox.md` is this repo's append-only event ledger and the channel
`/tap-in` reads. A memo without a row is invisible to the next session by
construction.

- **A peer commits into this repo** → one `WRITE` row in the **same commit** as
  the change. Not a follow-up commit, not a memo instead. `REF` carries the git
  short sha; a row without it can never be correlated with history [st-s8ng].
- **You cross the boundary** — memo sent, peer bead filed, an ask serviced →
  one row, appended at the bottom, never edited. A correction is a new line
  whose `WHY` says what it corrects.
- Format contract, field rules and kinds: the header of `docs/a2a/inbox.md`.

## What You Must NOT Do

- Do NOT perform substantive work without an authorizing bead
- Do NOT place, modify, or cancel orders; no live-execution path is auto-allowed
  (`.claude/rules/schwab-api-gate.md`)
- Do NOT `git add -A` — stage explicit paths and commit with a pathspec
- Do NOT narrate Steve's method back to him. Trading mechanics are a
  `knowledge/` read at question time, not context you recite

## Key Entry Points

- `knowledge/index.md` — the trading knowledge bundle, entry point
- `CLAUDE.md` — standing context: profile, instruments, Schwab gates, division of labor
- `.claude/rules/` — the behavioural rules loaded every session
- `docs/a2a/inbox.md` — the cross-agent ledger
