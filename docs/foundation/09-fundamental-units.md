# 09 · Fundamental Units — Naming What the Tape Does

*Foundation series, document 9. Rests on: [02 · Volume](02-volume.md) (effort vs
effect), [05 · Order Flow](05-order-flow.md) (aggression, delta, absorption),
[06 · Bars and the Footprint](06-bars-and-the-footprint.md) (cells, footers),
[07 · Levels and Traps](07-levels-and-traps.md) (the four stages).*

*This document is five short essays, read in order. Ground truth for every term
is `docs/lexicon/lexicon.yaml`; every number is a measurement from 263 trading
days (39,482 minutes, 1,649 price swings), adversarially verified. First
contact with this vocabulary should be the companion narratives,*
The Day in Fundamental Units *(2026-07-22 and 2026-07-24)*; these essays
explain the machinery the narratives showed in motion. For the measurement
vocabulary the accuracy numbers are spoken in — anchor, fire, the scoring
rule — read `docs/training/plain-words-glossary.md` first; no essay assumes
it.*

---

## Essay I — The atom and the four cells

**The one idea:** one minute of tape, scored on two axes, lands in one of four
cells — and the cells already have names you know.

The **atom** is one clock minute. It gets two scores. **Effort** — how many
contracts changed hands (document 02's participation, unsigned). **Effect** —
how far price moved. Score each against the rest of the day (a percentile:
busier or quieter than the day's other minutes?) and cross them:

| | High effect | Low effect |
|---|---|---|
| **High effort** | **F1 conviction** — the movement is being paid for (34.7% of minutes) | **F2 absorption** — someone is standing there (16.0%) |
| **Low effort** | **F3 hollow** — price drifting on air (22.4%) | **F4 dead** — nothing happening (26.9%) |

Two refinements make the atom honest. First, effect has two faces:
**displacement** (where the minute closed vs opened) and **travel** (its full
high-low span). A minute can travel five points and close where it opened — a
round trip. The **travel-ratio** (displacement ÷ travel) catches this: near 1
is one-way traffic, near 0 is a fight. This matters because the measured
corpus shows **half of all travel hides inside minutes whose displacement is
small** — and 82.5% of that hidden violence lives in F2 absorption cells.
Absorption minutes are not quiet; they are wars that ended where they started.

Second, **force** — signed delta, document 05's aggression balance — is
recorded on every atom but is *not* one of the matrix axes. Effort answers
"how much business"; force answers "which side pressed." Keeping them separate
is not pedantry: one of the eight swing types exists precisely because force
and direction *disagree*.

## Essay II — Grades, not gates

**The one idea:** the four cells are lines we drew on a smooth surface, so
every label must say how far it sits from the line.

We tested whether the tape naturally clusters into the four cells. It does
not: the distribution of minutes over the effort/effect surface is smooth —
no valleys, no gaps. The 2×2 grid is *imposed*. The honest consequence:
**one classification in five is a literal coin flip** — 20.4% of atoms sit
within a whisker of a cell-boundary.

So every label carries a **grade**: distance from the nearest cell-boundary,
0 to 1. And grades are spoken in **grade-bands**: **coin-flip** (≤0.1 — never
report the cell alone; say the straddled pair, "F3/F4 coin-flip"), **lean**,
**solid**, and **strong** (>0.6 — survives any reasonable redrawing of the
lines). Speak them like this: *"graded F1 at 0.62"* — never *"is F1."*

This is not hedging; it is calibration. When the 7/22 opening swing scored
pace 0.792 against a 0.75 cutpoint, the vocabulary reported
"flush-leg/steady-leg, coin-flip" — telling you *exactly* how much weight the
label can bear. A vocabulary that admits its coin flips earns trust for its
strong calls. (A **cutpoint**, while we are here, is a dividing line that
*sorts*; a **threshold** is a value that *triggers* — the reversal threshold
ends a swing, the 150-contract delta threshold fires the flip-stage. Bare
"cut" stays reserved for what you do to a losing position.)

## Essay III — The zigzag and the eight archetypes

**The one idea:** redraw the day with the fewest pen strokes, and the strokes
themselves sort into eight recurring characters.

The **zigzag decomposition** is the drawing rule: trace the day with
alternating strokes, ending a stroke only when price retraces more than a
threshold (20% of the day's range) from the stroke's furthest point. Each
stroke is a **leg** — median 15 minutes, 7.25 points. Everything smaller than
the threshold is absorbed into the leg as texture.

Across 1,649 legs, four measured axes — pace, effect, giveback, force
alignment — sort the population into eight **archetypes**: **flush-leg**
(fast and big; the tradeable V-dump cliff, 13.7%), **steady-leg** (mid-pace,
force agreeing 95% — the trust-the-tape reference), **leg-grind** (slow and
big; the trend-day escalator), **counterforce-leg** (price moving *through*
opposing force — falling prices on net buying; direction-inversion territory),
**absorption-stall** (the wall: 70,825 contracts for 3.5 points, once),
**hollow-glide** (distance on air), **probe-fade** (out, nothing there,
back), and **dead-drift** (the honest majority: 32.4% of legs are nothing
happening).

Two corpus facts to carry: **big legs keep what they take** (flush-legs give
back a median 5% of their extreme — the reason a fly entered at a V-dump
extreme isn't fighting the leg that made it), and **legs die hot** — the
**pivot-atom** where one leg ends and the next begins grades F1 conviction
63% of the time. Swings end by opposition, not exhaustion. The exceptions —
quiet pivots like 7/22's 11:19 top — are real, at 37%, and worth knowing by
that number.

## Essay IV — The tiers, and where your words live

**The one idea:** every vocabulary you already have keeps working; each word
now has an address.

The units nest: **axes** score → **atoms** (minutes) → **legs** (swings) →
the **day-sequence** (the session's archetype string — a D-day *reads* as
rotation from the inside). Beside that stack sits the tier you already knew:
the **episode** tier, where the recognizer runs the four **stages**
(flush-stage → stall-stage → flip-stage → confirm-stage) on 2,000-contract
bars, and where the **primitives** live — **sweep-print**, **absorption-read**,
**delta-divergence**, **imbalance-stack**. Nothing you learned in documents
01–08 was replaced; it was given a floor in the building.

The tiers also resolve an apparent paradox worth meeting head-on: 7/22's
afternoon leg is wall-to-wall F4-dead *atoms*, yet grades F1 at *leg* scale —
because 221 minutes of small efforts sum to a large one. Atom grades are the
day's texture; leg grades are corpus-scale mass. Both true. When you speak a
grade, say which tier you mean.

One discrimination from this stack matters more than any other, and it has a
fencing name: at a contested price, a thrust meets a parry. If the **parry
fails** — conviction resumes through it — you watched a **micro-stall**, a
pause inside a living leg. If the **parry holds** and force turns, you
watched a **stall-stage**, and the leg is dying into a possible trap. *In the
moment the two are indistinguishable.* The next atoms decide. Sitting with
that ambiguity — rather than resolving it prematurely — is the discipline the
whole grade-band system exists to train.

## Essay V — LIVE and HINDSIGHT: your seat

**The one idea:** every measurement in this document is stamped LIVE or
HINDSIGHT, and the stamp defines your job.

**LIVE** — knowable in the minute: raw atom fields, the four stages, every
primitive, every confirmation-event. **HINDSIGHT** — computable only after:
all percentiles (they rank against the *completed* day), all cells and
grade-bands, all leg boundaries (a pivot exists only after the retracement
proves it), all archetypes, the day-sequence.

The system's two strongest discoveries are both hindsight, and honestly
labeled: confirmations *with* their host-leg win 66% versus 19% against it,
and the **V-signature** — a deep flush-leg answered by a confirmation-event
within minutes — wins 77.5% versus a 46.9% base. Neither is a live entry
rule yet; turning them live (developing percentiles, provisional pivots) is
open engineering, and until it ships, they are how the tape gets *graded*,
not how it gets *traded*.

Which is the seat, stated one last time: deterministic code watches every
minute; an agent switches on where it counts; **hindsight is the authority on
what was correct; you are the authority on risk** — the final call on every
trade and every size. This vocabulary's whole purpose is to make what the
watchers tell you *unambiguous* at the moment that call is yours.
