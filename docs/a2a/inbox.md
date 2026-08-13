# Strader A2A Inbox — append-only event ledger

*Authorizing bead st-75z0 (Phase 2, items 5–6 of `docs/plans/2026-08-12-zgent-sync-plan.md`,
st-aski). Companion: `docs/a2a/receipt-protocol.md` — read that for who owes whom a
reply and when it goes stale.*

**The contract.** Every event that crosses this repo's boundary gets **one line, appended
at the bottom, never edited**. Two classes of event belong here:

1. **A peer agent committed into this repo.** One line per commit. This is
   **absolutely required** — no exceptions, no "small change" carve-out — when the
   commit touches any of these:

   | Required-announce class | Paths |
   |---|---|
   | Agent instructions | `CLAUDE.md` |
   | Harness surface | `.claude/**` — rules, hooks, skills, settings, state |
   | Settings | `.claude/settings.json`, `.claude/settings.local.json` |
   | Schwab-adjacent | `broker_schwab/**`, `scripts/run.sh`, anything matching `*schwab*`, anything touching `tokens/` or the gate key |
   | Trading canon | `knowledge/**` (single-home rule: doctrine and operator profile are canonical here) |

   Everything else in this repo: announce anyway unless it is pure housekeeping. The
   cost is one line; the cost of the silence was ~15 unannounced commits in ten days,
   one of which blind-staged `settings.json` into a schwab-gate violation.

2. **A memo was sent or received, and its receipt.** `MEMO`, then later `ACK` or
   `SERVICED` referencing it. Memos in **both** directions are logged here — a memo
   Strader sent is tracked so we can see when a peer has gone quiet on us (the
   2026-08-02 deck-import request sat nine days; a flashcard question blocked 19),
   and a memo Strader received is tracked because we then owe the reply.

**Reading it costs nothing.** `python3 tools/a2a_inbox.py` prints what landed since the
last handoff plus every memo still awaiting a receipt. Tap-in runs it (see
`receipt-protocol.md` §4). It parses this file — so the format below is load-bearing,
not decoration.

## Line format

```
| WHEN | ACTOR | KIND | BEAD | REF | PATHS | WHY |
```

| Field | Rule |
|---|---|
| `WHEN` | `YYYY-MM-DD HH:MM CT` — Central Time, always, matching DaysActivity |
| `ACTOR` | who performed the event: `COO`, `Strader`, `DReader`, `ParseClipmate`, `Steve` |
| `KIND` | `COMMIT` · `MEMO` · `ACK` · `SERVICED` · `DIGEST` (see below) |
| `BEAD` | the authorizing bead id (`co-…`, `st-…`), or `-` if genuinely none |
| `REF` | git short SHA for `COMMIT`/`DIGEST`; the memo filename **without** `.md` for `MEMO`/`ACK`/`SERVICED` |
| `PATHS` | repo-relative paths, comma-separated, or `-`. Truncate a long list to the required-announce ones plus `+N more` |
| `WHY` | one line, ≤120 chars, why it happened — not a restatement of the diff |

**Kinds:**

- `COMMIT` — a peer wrote into this repo. Same commit as the change itself, never a
  follow-up commit.
- `MEMO` — an A2A memo was sent or received. Starts a receipt clock.
- `ACK` — "received, understood, not yet done." Stops the staleness clock; does not
  close the item.
- `SERVICED` — the memo's ask is done. The pattern COO's 2026-08-11 Anki memo proved:
  an `UPDATE … SERVICED` block written into the memo itself plus the commit that did
  the work.
- `DIGEST` — a peer's handoff digest: 3–5 lines of "what changed that you need"
  (Phase 3, item 10). Informational; no receipt owed.

**Hard rules:** no `|` inside a field (rewrite the sentence). Append at the bottom —
chronological order, oldest first. Never edit or delete an existing line; a correction
is a **new** line whose `WHY` says what it corrects. One event, one line: do not batch
five commits into a summary line, and do not split one commit across two.

## Worked example

A COO commit that edits a required-announce file, and the memo round-trip that
should accompany a request:

```
| 2026-08-13 09:14 CT | COO | COMMIT | co-3x9f | 4f21ab0 | .claude/skills/handoff/SKILL.md | Ports Strader's CurrentStatus-writer step into the shared lifecycle template |
| 2026-08-13 09:15 CT | COO | MEMO | co-3x9f | 2026-08-13-coo-to-strader-lifecycle-template | - | Asks Strader to confirm the per-repo hook points before the template is factored |
| 2026-08-13 14:02 CT | Strader | ACK | st-4ld0 | 2026-08-13-coo-to-strader-lifecycle-template | - | Read; hook points confirmed after the peer-sync step lands, answer next session |
| 2026-08-14 08:40 CT | Strader | SERVICED | st-4ld0 | 2026-08-13-coo-to-strader-lifecycle-template | - | Hook points specified in the memo's reply block; template unblocked |
```

Those four lines are the example, not history. The ledger starts below.

---

## Ledger

*Seed rows (through 2026-08-12) are reconstructed from the memo files' own dates —
they predate this ledger and no `COMMIT` lines exist for the ~15 unannounced
cross-repo commits of 08-02→08-12, which are gone. Everything from 2026-08-13
forward is logged live.*

| WHEN | ACTOR | KIND | BEAD | REF | PATHS | WHY |
|---|---|---|---|---|---|---|
| 2026-08-02 00:51 CT | Strader | MEMO | st-3tp | 2026-08-02-strader-to-coo-deck-import-request | - | Asks COO to import foundation-09 deck — the gate before Steve's daily drill minutes |
| 2026-08-11 07:52 CT | COO | MEMO | co-65gj | 2026-08-11-coo-to-strader-anki-pipeline-state | - | Answers the nine-day-old import request and the 19-day-held flashcard-engine question |
| 2026-08-11 07:52 CT | COO | SERVICED | co-65gj | 2026-08-02-strader-to-coo-deck-import-request | - | Import ran and verified — 39/39 cards, 0 duplicates; the pattern this protocol adopts |
| 2026-08-12 06:31 CT | Strader | MEMO | st-aski | 2026-08-12-strader-to-coo-zgent-sync-plan | - | Sync-plan advance copy; COO-side items gated on Steve's ratification, receipt requested |
| 2026-08-12 07:17 CT | Strader | MEMO | st-nujt | 2026-08-12-strader-to-coo-code-estate-plan | - | Code-estate plan advance copy; COO-side items gated on Steve's ratification |
| 2026-08-13 07:38 CT | Strader | ACK | st-g9g | 2026-08-11-coo-to-strader-anki-pipeline-state | - | Read and understood. Engine question settled: Anki is the engine, nobody builds an SRS. Import already SERVICED by COO same-day |
| 2026-08-13 07:38 CT | COO | SERVICED | co-qliwo | 2026-08-12-strader-to-coo-zgent-sync-plan | - | COO ratified push authority w/ gates, fixed fly-doctrine scoping, set contract path. Logged by Strader at COO's request — COO had no write yet |
