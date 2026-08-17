# Rule: Present Artifacts Name-First

When you present a bead or a git artifact to the operator, **lead with its
ProperName** — a short (~3-word) human handle — not the machine ID. The ID
(bead `<prefix>-XXXX`, commit hash) is secondary: parenthetical, or omitted
when the name is enough. Operators read by name, not by "nonsense hash."

Enterprise-standard rule (certification catalog: `rule:proper-name-presentation`).
Origin: COO `co-wf5u` / `co-oajk`, 2026-07-06. Canonical convention:
`conventions/bead-propername.md` in COO.

## Beads

- Refer to a bead as **Settings Template Drift** (`co-ur7l`), name first.
- When listing the queue, prefer `bd propername --ready` (name-first) over raw
  `bd ready`.
- Give every substantive bead a ProperName on creation:
  `bd propername <id> "Three Word Name"`.

## Git artifacts (commits, branches, PRs)

- Refer to a commit as **Bead Proper Names** (`fef40eb`) — name first, hash
  parenthetical or omitted.
- A commit's ProperName is *derived*: from the `[<prefix>-XXXX]` bead it
  references (`bd propername <id>`), else a ~3-word gist of the subject.
- Use `git namedlog` when showing commit history — it renders
  `ProperName · shorthash · subject`.

## Tooling and graceful degradation

The `bd propername` and `git namedlog` helpers ship in the standard runtime
image (installed by the factory). Where they are present, use them. Where they
are **not** yet installed, still honor the principle: lead with the best
available human handle — a bead's title compressed to a phrase, a commit's
subject gist — and demote the ID. The behavior is name-first presentation; the
helpers only make it ergonomic.

A zgent's own bead store carries ProperNames once backfilled for that repo
(`factory/scripts/backfill-propernames.sh` pattern). Until then, `--ready`
shows `(unset)`; that is expected, not a failure — new beads still get names on
creation.

## What this is not

- Do not rewrite commit messages, add git notes, or fork the beads schema to
  store names. ProperNames are a *layer on top* — metadata for beads, derived
  for git. The underlying systems stay untouched.
- Do not drop the ID when it is needed for an action (checkout, `bd show`,
  cherry-pick). Name-first means the name *leads*, not that the ID vanishes.
