# Drill Skill Ladder — What to Concentrate On, In What Order

*st-5ov · 2026-07-13 · The ordered concentration list the drill dropdown reflects.
Companion to [scenario-catalog.md](scenario-catalog.md); machine-readable deck in
[scenario-deck.json](scenario-deck.json).*

> **Prerequisite (st-8j8):** this ladder assumes the background built in
> [`docs/foundation/`](../foundation/00-READ-ME-FIRST.md) — auction mechanics,
> volume, the two profiles, order flow, the footprint, and trap mechanics. Read
> that series first; it defines every term this page uses in shorthand.

---

## Why an order exists at all — three structural facts

### 1. The six scenarios are one pattern with six exits

S1–S6 are not six independent patterns to memorize. They are the **same four-stage
sequence** (flush → stall → flip → confirm) observed at different termination points:

```
price meets level
├─ no force either direction ·································· S6 chop straddle
├─ force punished at once, level never trades through ········· S1 clean rejection
└─ force breaks through ··········· STAGE 1 flush
   ├─ aggression keeps getting paid ··························· S4 clean break
   └─ aggression stops paying ····· STAGE 2 stall
      └─ footers change sides ····· STAGE 3 flip
         ├─ retake never holds ································ S5 sprung trap fails
         └─ retake holds ·········· STAGE 4 confirm
            ├─ flush was violent ······························ S2 failed breakdown
            └─ flush was quiet ································ S3 level reclaim
```

So the curriculum is not "learn six things." It is **learn ONE sequence deeply, then
learn where each lookalike departs from it.** Every discrimination drill is a question
of the form "which stage went missing?"

### 2. Tempo and frame reads are the stage detectors, not side material

Each stage of the sequence IS a frame/tempo read applied in context:

| Stage | Is this read |
|-------|--------------|
| flush | F1 conviction (bright cell, big number) arriving at T3 burst pace |
| stall | F2 absorption — effort without effect, the matrix's money quadrant |
| flip | column-level footer color change |
| confirm | F1 conviction the other way, WITH effect |

You cannot call a stall if you cannot see absorption in one cell; you cannot weight a
flush if you cannot feel pace. Units 0–1 are load-bearing, not warm-up.

### 3. Carmine's set is the anchor axis, not a second list of strats

The recognizer derives the CarmineSetup name from **where the level came from**, not
from a different pattern (`market/orderflow/recognizer.py`):

| Carmine setup | = the sequence at |
|---------------|-------------------|
| failed_breakdown | a support level, violent flush |
| level_reclaim | a support level, quiet flush |
| range_trap | a session range edge |
| return_to_lvn | a low-volume node |

Carmine's four strats = **(one sequence) × (three anchor types)**. You do not study
four strats in parallel; you master the sequence at one anchor type, then re-meet it
at the others. Anchor generalization is the LAST unit, not four separate curricula.

---

## Ordering principles

1. **Prototype first.** Internalize the complete archetype (S2 — the marquee, most
   verified references) before any boundary case. You can't notice a missing stage
   until the full rhythm is automatic.
2. **Departures in stage order, weighted by cost.** After the archetype, drill the
   lookalikes by where they depart AND what the confusion costs. S2-vs-S4 confusion =
   fading force that is being paid = direct loss (doctrine: never fade paid force) —
   first. S2-vs-S3 confusion = same-direction trade at slightly lower conviction,
   Mancini himself relabels between them — nearly free, so late.
3. **The confirm gate is behavioral, not perceptual.** S5 is indistinguishable from
   S2-in-progress until stage 4 *by construction* — the drill's job is patience and
   the fast cut, not a sharper eye. It gets its own unit right after the money
   discrimination, because it justifies the doctrine emotionally.
4. **Passive exposure covers the commons.** S1 and S6 occur constantly in ordinary
   guess-then-reveal reps; they accumulate reps for free. Concentrated study waits
   until the sequence reads exist — S1's tell ("never trades through") is meaningless
   before you know what through-then-trapped looks like.

## The ladder

| Unit | Concentrate on | The skill | Why here |
|------|---------------|-----------|----------|
| 0 | T1–T3 tempo | Feel pace before reading anything; time is an output | Substrate for everything |
| 1 | F1–F4 frames | Effort-vs-effect matrix on one cell/column | These ARE the stage detectors |
| 2 | **S2 archetype** | Walk complete sequences (narrated → prompted → cold) until the four-stage rhythm is automatic | Prototype first; 3 verified refs |
| 3 | **S2 vs S4** | The trap vs the anti-trap. Tell lives in stage 2: is the aggression still getting paid? | Costliest confusion in the deck |
| 4 | **S5** | The confirm gate — no call before stage 4; fast cut if early | Doctrine, proven on tape |
| 5 | **S3 vs S2** | Family refinement: flush violence separates the siblings | Low-stakes; family agreement = success |
| 6 | **S1 + S6** | The no-sequence pair: level holds vs level is noise | Needs sequence reads first; refs [to tag] |
| 7 | Anchor generalization | The same ladder re-met at range edges (range_trap) and LVNs (return_to_lvn) | Completes Carmine's set |

The drill page's **Ladder dropdown** presents scenarios in exactly this order. Lesson
specs (st-5ov deliverable 2) attach scaffold level, deck mix, and pass bar per unit.
