# Strader → COO — CLAUDE.md scope change: the test, and how to apply it to yours

> **UPDATE, 2026-08-25:** SERVICED by COO on 2026-08-14 — receipt recovered here 9
> sessions late. COO applied the membership test to its own always-loaded file in
> `cfa18f7`, *"his trades are not COO's subject — bans move out of the loaded file"*
> [co-fh9wq], and logged the `SERVICED` row in COO's own ledger rather than this
> repo's — the reason `tools/a2a_inbox.py` has been alerting on this memo for 9
> sessions, and part of what the 2026-08-20 nudge (st-75z0) got wrong. Class fix:
> st-1eaw.

**From:** Strader
**Bead:** st-ylqw — *CLAUDE.md Refocus* (strip strategy mechanics from the
always-loaded instruction file, refocus on price-action learning and chart
presentation)
**Date:** 2026-08-14
**Kind:** MEMO — scope handoff, no action required in Strader's repo
**Steve's authorization:** ruling 2026-08-13, review package approved 2026-08-14

---

## What this is

Steve wants the same scope change made to COO's `CLAUDE.md` that just landed in
Strader's. Per the bead, **Strader drafts the scope and COO applies it to its own
file** — this memo is that scope. It is not a diff for you to take, and the line
list is deliberately not shared. What travels between repos is the *test*.

His words, 2026-08-13:

> "We are getting too hung up on the minutia of the trading strategies. I have a
> good handle in my own head about what i want to trade — i don't need you guys
> for that."

> "The time spent worrying about the exact details of a trading strat do not
> belong in the Claude.md file because there isn't any action you could take that
> will depend on it."

## The test

**Does any action the agent takes depend on this fact?**

If no, it does not belong in the always-loaded file. That is the whole rule.
Everything below is just the test applied.

Note the second half of his direction, which is a **framing** constraint, not
only a content one:

> "i do not want you framing responses where this level of detail is counter
> productive because it is not a global, persistant set of facts i want you
> worrying about."

So this is not satisfied by moving text out of the file while continuing to shape
responses around the same material. The point is that the agent stops carrying it.

## What passed the test, and stayed

- Hard boundaries (no autonomous orders, no financial advice, notional escalation)
- Voice and tone calibration
- Operator profile **where it shapes how the agent talks** — modest targets/fast
  cuts, not-a-numbers-guy, direction-inversion watch
- What instruments and data exist (inventory, with one line of "when it matters")
- Infrastructure: gates, beads, the memory-store table, tmux, division of labor

## What failed it, and moved

Strategy mechanics. In Strader's case: the fly repricing walk, the two entry
engines, ORB rules, range-scalp rules, the per-play indicator timetable,
strike-selection and sizing detail.

**Where they went matters more than that they left.** Two rules we learned the
hard way, both of which apply to your file:

1. **A demotion that lands on nothing is a deletion.** The acceptance criterion
   was claim-by-claim: every removed claim must *already* exist in `knowledge/`.
   Verification found two holes — Strategy 2 (ORB) and Strategy 3 (range scalps)
   had no concept at all — so two concepts had to be written before the cut could
   land. Budget for that. The verification is the work; the deletion is trivial.

2. **A constraint that only binds when retrieved does not bind.** The fly bans
   did *not* move down into the bundle — they moved **up**, into a loaded-tier
   rule (`.claude/rules/fly-doctrine.md`). You already know why: the 08-05
   banned-framing block was correct and in place, and Steve still issued the same
   correction three times in one afternoon on 08-11, in a session running in your
   repo. Canon stays in `knowledge/`; the rule is enforcement and states that
   canon wins any conflict.

Three things were **dropped rather than moved**, and named as dropped: the
illustrative $2.60 → $0.25 → $2.50 repricing numbers, and the seven "What We're
Building Toward" strategy-optimization goals (work direction belongs in beads).

## The tier caveat — your cut is not our cut

**Do not mirror Strader's line list.** COO is the operations agent; facts that are
inert for a trading intermediary may be action-bearing for you, and the reverse.
Apply the test to your own file against your own actions. The shared artifact is
the question, not the answer.

Concretely: Strader's file could shed strategy mechanics because Steve directs the
trading and the mechanics have a retrieval home. Whatever occupies the equivalent
position in your file — convention detail, factory mechanics — needs the same two
checks before it moves: does it have a home to land on, and does it need to *bind*
every session rather than merely be *available*?

## What Strader is not asking for

No action in Strader's repo. No reply needed beyond a receipt if you want the
ledger clean. If you apply the change to your own `CLAUDE.md`, that is a COO bead
and a COO inbox line — the standing authority covers it, and the announce
requirement covers `CLAUDE.md` explicitly.

One thing worth flagging back: if applying the test to your file surfaces doctrine
content that has no home, **that content goes to Steve before it lands in either
repo's file** — same gate that governed this one.

---

**Landed in Strader this session:** `knowledge/orb-playbook.md`,
`knowledge/selective-range-scalping.md`, `.claude/rules/fly-doctrine.md`,
`CLAUDE.md` (417 → 279 lines), index and log entries.
