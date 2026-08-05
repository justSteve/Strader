# Mancini Parse — Process Review

**Bead:** Mancini Parse Revisit (st-pjp8) · 2026-08-05
**Input:** Steve's three rulings this session + the pipeline as it actually runs.

## Steve's rulings (the fixed points this review works around)

1. **He triggers the parse by prompting a Strader session.** No API dependency,
   no scheduled parse.
2. **Strader owns the role.** It was interchangeable — COO ran parses too. It
   is now Strader's job, singular.
3. **Keep as much processing in code as possible.** The LLM does judgment;
   everything else is a script.

## What actually runs today

| Step | Who does it | Judgment? |
|---|---|---|
| Fetch letter from Azure blob | `fetch.py`, called by the 08:15 CT cron | no |
| Strip Substack HTML to ~30k prose | `clean.py` | no |
| Scrape `Supports are:` / `Resistances are:` | `listlevels.py` regex | no |
| **Read the prose for conditional guidance** | **an agent, in-session** | **yes** |
| Validate every price appears verbatim | `validate.py` | no |
| Sanity-band out-of-range levels | `validate.split_out_of_band` (new today) | no |
| Overnight interaction brief | `overnight.py` | no |
| Payload + Pine emit | `payload_emitter.py`, `chart.py` | no |
| Desk publication, clipboard push | `run.py` | no |

One line of judgment, nine lines of code. The shape Steve wants is already
mostly the shape it has — which is why this is a refinement, not a rebuild.

## Finding 1 — the cron is now doing the wrong job

The 08:15 CT cron runs **hybrid mode**: deterministic levels only, commentary
flagged pending. It skips when an in-session parse already exists. Under the
old world (parse might or might not happen) that was a sensible floor.

Under Steve's ruling it is actively wrong: if he hasn't parsed yet, the cron
**publishes a lesser plan** — regex levels, no conditional guidance — to the
desk fifteen minutes before the open, and that is what he'd read.

**Recommendation: split fetch from parse.** The cron keeps every no-judgment
step it can do without the letter being read — fetch, clean, deterministic
levels, and the overnight brief — and then **stops and alerts** ("letter
fetched, N levels scraped, ready to parse") instead of publishing. Publication
happens only from a real parse. Code keeps doing everything code can do; the
plan document stops existing in a half-form.

## Finding 2 — the procedure should be a Skill (yes)

The extraction contract is already a fixed three-step sequence with a strict
JSON shape and a validation gate. Today it lives in a document an agent must
remember to read. That is exactly what a Skill is for.

Concrete benefits, not theoretical:
- Steve types `/mancini-parse` instead of reconstructing a prompt each morning.
- The contract *loads itself* into context rather than depending on the agent
  choosing to open it. The failure mode it removes is a session parsing from a
  half-remembered shape.
- It is version-controlled and reviewable; changes to the procedure become
  commits, not habits.
- It pins the role: the skill lives in Strader's `.claude/skills/`, so
  "Strader owns the parse" is enforced by where the capability exists.

**Housekeeping found in passing:** `.claude/skills/` holds **14 `gc-*` skills**
for Gas City, which was deprecated and deleted 2026-07-29. They are dead weight
in every Strader session's skill listing and should go.

## Finding 3 — "track the letter against real-time PA" is code, not a subagent

Steve asked whether a subagent should own tracking how the letter's details play
out against live price action. The honest answer is **no — and the reason is
instructive**.

Tracking implies **continuity**: what has happened to each level, since the
letter, up to now. A subagent has no memory between invocations. Give the job to
an agent and it must re-derive the whole day from raw tape every single time it
is asked — slowly, and with no guarantee two answers agree. Continuity belongs
in a file.

And the state machine already exists. `overnight.py` computes, per level, the
same four states the Pine renderer draws, using identical close-based
definitions so the brief and the chart can never disagree:

- **touched** — traded within tolerance
- **held** — touched, and closed on the correct side
- **broken** — closed beyond it by more than tolerance (close, not wick)
- **reclaimed** — after a break, closed back on the original side — the Failed
  Breakdown, in place

What is missing is only its **scope**: it runs once, at parse time, over the
overnight window.

**Recommendation: a level-state tracker.** Take that machine, run it
continuously through the session against our own ES tape, and write the state
out where anything can read it — a small JSON refreshed every minute:

```
per level: price, tier, key?, state, first_touch, n_touches, n_defenses,
           last_event_ts, distance_from_price
plus:      levels broken today, levels reclaimed, untested levels above/below
```

Then Steve's three wants resolve without an agent in the loop:

- **Faster answers about letter details** — a file read beats an agent spawn by
  an order of magnitude. The session answers "what happened to 7549?" instantly
  because the answer is a lookup, not an investigation.
- **Overnight implications** — already built; it becomes the tracker's first
  window rather than a special case.
- **Post-open implications** — the same machine, same definitions, live window.
  No second implementation to drift.

## Where a subagent *does* earn a seat

Once the tracker exists: **periodic interpretation.** Every N minutes during the
session, a subagent reads the tracker state plus the letter's conditional
guidance and writes a short narrative — *"7567 broke at 09:12 and the bounce is
stalling underneath it; that is the letter's bear case, not its base case."*
That is judgment over a small, pre-computed input, which is what LLMs are for
and what code cannot do.

Doing this **before** the tracker exists is the mistake: the agent would spend
its context re-deriving state, produce inconsistent readings, and cost seconds
Steve does not have at the open.

## Proposed order of work

1. **Skill** (`/mancini-parse` in Strader) — smallest, removes daily friction now.
2. **Cron split** — fetch/prepare/alert; never publish a hybrid plan.
3. **Level-state tracker** — generalize `overnight.py`'s machine to a live,
   queryable state file.
4. **Interpretation subagent** — only after 3, and only if 3 leaves a real gap.
5. **Delete the 14 dead `gc-*` skills.**

Nothing here gets built until Steve rules on the order.

## The audit lesson, applied in advance

Anything the tracker asserts must be checkable: its state file carries the
timestamps and the tape rows behind each transition, so a claim like "7549 held
three times" can be verified rather than believed. A tracker nobody has scored
against the tape is exactly the artifact the continuation audit warned about.
