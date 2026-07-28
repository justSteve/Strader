# Fundamental Units of Orderflow — NotebookLM Source Bundle

This bundle teaches a measured vocabulary for ES/SPX price action, built for a
trader learning to read footprint charts. It contains: (1) a narrative of one
real trading day told in the vocabulary, (2) five short teaching essays, and
(3) the full glossary. Everything is derived from 263 measured trading days.
Good audio-overview angles: the story of the 7/22 trading day; why every label
carries a confidence grade ("grades not gates"); the fencing metaphor (thrust,
parry — does the parry hold?); what a trader can know live versus only in
hindsight.

---

# The Day in Fundamental Units — Wednesday 2026-07-22

**Bead:** st-g9y · **Form:** measured narrative — every number below is pulled from
`data/measurement/moves/{atoms,moves}.jsonl` (run `20260728T123632Z`), the replay
record, or the verified pre-market pull; nothing is remembered or embellished.
**Vocabulary:** terms appear **bold** on first use; every label carries its
grade-band, per the lexicon (`docs/lexicon/lexicon.yaml`). Companion: the PA
Lexicon desk page for lookup.

---

## Prologue — before the tape

The trap was sprung before our recording begins. At 07:56:53 CT, thirty-four
minutes ahead of the bell, ES flushed to 7504.0 — two points through the 7506
low Mancini had flagged — 123 prints in four seconds, then a ~23-point recovery
into the open. Verified by a one-off pre-market pull; invisible to everything
below, which starts at 08:30. Keep it in mind: the day's story is the
*aftermath* of a trap we never filmed.

## Act I — the open drive (08:30 → 09:06)

The first minute of tape is an **atom** — one clock minute, the smallest unit
we grade. It arrives loud: 9,196 contracts (**effort** in the 99.7th
percentile of the day) pushing +2.75 net (**effect**, 94.6th) — graded
**F1 conviction** in the **strong grade-band** (0.892). The movement is being
paid for. The next atom is nearly a corner case of the whole corpus: F1 at
grade 0.984, effort 99.2 / effect 99.7. Two minutes in, and the recognizer —
working a tier below, on 2,000-trade bars — has already run
**flush-stage → flip-stage** at the 7533 plan-level; its first
**confirmation-event** stamps 08:32.

Watch what the atoms do at 08:35: 3,923 contracts — 96th percentile effort —
and *zero* net movement. Travel-ratio 0.0: a full round trip inside the
minute. That is **F2 absorption** in the strong grade-band (0.836), and in the
leg's cell string it prints the **micro-stall** motif — conviction, absorption,
conviction resuming — the pause that refreshes rather than reverses. The
morning is thick with **probe-atoms** (high-effort round-trip minutes):
23 today against a corpus norm of ~7, most of them packed into
08:34–09:02 — the tape digesting the overnight trap in public.

By 09:06 the whole run is one **leg** — the zigzag's unit — and here the
vocabulary earns its honesty clause. The leg: +28.25 points in 36 minutes,
**pace** 0.792 against the flush-leg **cutpoint** of 0.75, **giveback** 0.009 — it kept
essentially everything it took. Is it a **flush-leg**? By the cutpoint, yes — but at
pace 0.792 the **archetype-grade** is ~0.01: a **coin-flip grade-band**
call, honestly reported as the *flush-leg/steady-leg pair*. The label is not
embarrassed; it is telling you exactly how much to lean on it. Its **force**
(+4,183, signed delta — never confuse with unsigned effort) agrees with its
direction, as it does for every leg today.

## Act II — the give-back (09:05 → 09:45)

Legs die hot. The **pivot-atom** — the shared border minute where one leg ends
and the next begins — is 09:05: F1 at grade 0.948, effort 97.4th percentile.
Nothing faded here; the up-leg was *killed by opposition*, which is how 63% of
corpus legs end. The down-leg it births is remarkable for one number:
giveback 0.000. It closed at its exact extreme — −22.50 of −22.50 — a
**steady-leg** (mid-pace, force-aligned) that never surrendered a tick of what
it took.

## Act III — the escalator (09:44 → 11:20)

The recovery is the slowest big leg of the day: +31.50 points across 96
minutes at pace 0.336 — under the 0.38 cutpoint, effect in the 76th percentile —
a **leg-grind**, the trend-day crawl that never offers a clean entry. Its
force is enormous and aligned (+9,757): patient, paid-for buying. The 09:46
confirmation-event at 7533 (the recognizer's fourth and final of the day)
fires two minutes into this leg — in hindsight, a textbook **leg-boundary-trap**:
the prior down-leg dying, conviction opening the new one.

## Act IV — the long fade (11:19 → 15:00)

The top at 11:19 is the honest exception: this pivot-atom grades **F4 dead**
(0.276) — effort 36th percentile, a *quiet* turn. Sixty-three percent of
pivots are loud; this one belongs to the other thirty-seven. No opposition
killed the escalator; it simply stopped being paid for.

What follows occupies more than half the session: −26.00 points over 221
minutes at pace 0.121. Read its atom string and it is wall-to-wall **F4 dead**
and **F3 hollow** — price drifting on air, minute by minute. Yet at leg scale
it grades F1 (effort 89.7th percentile), and that apparent contradiction is a
lesson, not a bug: 221 minutes of small efforts *sum* to a large one.
Atom grades are day-relative texture; leg grades are corpus-wide mass. Both
are true; the tiers measure different things — say which tier you mean.

The fade ends in a fight. 14:58 is a probe-atom (7,538 contracts, travel
0.2), and 14:59 is the single loudest atom of the day — 39,694 contracts,
100th percentile on both axes, F1 at grade 1.000, ten points of range —
while the book-level **absorption-reads** show sellers throwing 200–300
contracts at the bid and getting refilled 3–5×. A contested close, graded at
maximum confidence. The sequel is not in this day's file: the next session
gapped down eighty points.

## The day in one line

**Day-sequence:** flush-leg *(coin-flip, pair with steady-leg)* → steady-leg →
leg-grind → steady-leg *(off-pace)* — a balanced-rotation story told in four
words, which is what a **D-day** looks like from the inside.

---

## Epilogue — creatures not seen today

Four archetypes never appear on 7/22. So that you still meet them, here is
each one's best sighting from *other* days in the 263-day corpus — real
dates, real numbers, nothing staged:

- **counterforce-leg** — price moving *through* opposing force. The corpus
  specimen is 2026-07-27, 08:30: **−81.75 points on net BUYING (+3,033)** —
  trapped buyers all the way down. When you see falling price with blue
  footers, you are watching this — and it is Direction Inversion Watch
  territory by construction.
- **probe-fade** — out, nothing there, back. 2026-07-13 at 08:30: 22.0 points
  of extreme, −10.25 kept, giveback 0.53. (That one is already armed in your
  replay drill queue.)
- **absorption-stall** — the wall. 2025-06-25, 14:54: **70,825 contracts in
  six minutes for +3.5 points.** Effort without effect, at leg scale.
- **hollow-glide** — distance on air. 2025-06-18, 13:42: −38.25 points in 19
  minutes on under 15,000 contracts — nobody paid for that trip, and it
  traveled anyway.

## Coda — what was LIVE in this story

Everything narrated from atoms' raw fields (volumes, nets, travel), every
stage, every confirmation-event, every absorption-read: **LIVE** — knowable in
the minute. Every percentile, cell, grade-band, leg boundary, archetype, and
the day-sequence itself: **HINDSIGHT** — the grading of the tape after the
fact, which is exactly the authority hindsight holds in this system. The
narrative you just read is the hindsight layer teaching the live layer's
vocabulary; your seat only ever gets asked about the live half.


---

# 09 · Fundamental Units — Naming What the Tape Does

*Foundation series, document 9. Rests on: [02 · Volume](02-volume.md) (effort vs
effect), [05 · Order Flow](05-order-flow.md) (aggression, delta, absorption),
[06 · Bars and the Footprint](06-bars-and-the-footprint.md) (cells, footers),
[07 · Levels and Traps](07-levels-and-traps.md) (the four stages).*

*This document is five short essays, read in order. Ground truth for every term
is `docs/lexicon/lexicon.yaml`; every number is a measurement from 263 trading
days (39,482 minutes, 1,649 price swings), adversarially verified. First
contact with this vocabulary should be the companion narrative,*
The Day in Fundamental Units — 2026-07-22*; these essays explain the machinery
the narrative showed in motion.*

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


---

## The Vocabulary, term by term


### Axes

**effort** (live): Unsigned volume traded in a unit — how much fuel was spent. On the chart: Cell brightness and the size of the footer volume number.

**effect** (live): Price movement produced. Two faces: displacement (close minus open, signed) and travel (high minus low). A unit can travel far and displace nothing — that is a fight, not stillness. On the chart: How far the column's cells span (travel) vs where it closes relative to where it opened (displacement).

**force** (live): Signed delta — buy-aggression minus sell-aggression. NOT the same as effort (unsigned). The two axes are never interchangeable. On the chart: The footer delta number and its color.

**travel-ratio** (live): Displacement divided by travel, 0-1. 1 = one-way traffic; near 0 = full round trip inside the unit. Marks structure the unit's net hides. On the chart: A tall column that closes where it opened has travel-ratio near 0 — the wick-heavy silhouette.

**pace** (hindsight): Leg extreme-points per minute; corpus tercile cutpoints 0.38 / 0.75. On the chart: How steep the leg looks on the candle companion chart.

**giveback** (hindsight): Fraction of a leg's extreme surrendered by its end. Measured fact: big legs keep what they take (flush-leg median giveback 0.05); giveback concentrates in small legs. On the chart: The pullback from the leg's furthest point before the next leg starts.


### Grade bands

**cutpoint** (n/a (a property of definitions, not of tape)): A dividing line in a classification — pace 0.75 is the flush-leg cutpoint; the archetype-grade measures distance from it. Distinct from a threshold, which TRIGGERS an event when crossed (the reversal threshold ends a leg; the 150-contract delta threshold fires the flip-stage). Cutpoints sort; thresholds act. Bare "cut" is banned in definitions — in speech it keeps its trading sense: cutting a position. On the chart: Nothing — cutpoints live in the grading, not on the tape.

**coin-flip band** (hindsight): Grade <= 0.1 — within a whisker of the cell-boundary. 20.4% of atoms, 19.3% of legs. Unreportable as a cell claim; report the straddled pair ("F3/F4 coin-flip"). Banned as a bare command token in the CLI grammar. On the chart: A column you could argue either way about — the honest label admits it.

**lean band** (hindsight): Grade 0.1-0.3 (32.5% atoms / 28.7% legs). Reportable with the grade-band attached. On the chart: Readable but not shout-it-across-the-room.

**solid band** (hindsight): Grade 0.3-0.6 (31.3% / 29.0%). Reliable. On the chart: You would call it the same way twice.

**strong band** (hindsight): Grade > 0.6 (15.8% / 23.0%). Survives any reasonable reclassification. On the chart: Unmistakable — the textbook example you would screenshot.


### Atom tier

**atom** (live (raw) / hindsight (graded)): One clock minute of tape: net, range, travel-ratio, effort, force — live at minute close. Its percentile grades and F-cell are day-relative, hence hindsight. On the chart: Roughly 2-4 footprint columns' worth of tape at typical pace (columns are volume-bars, not minutes).

**F1 conviction** (hindsight): High effort AND high effect — the movement is being paid for. 34.7% of atoms. On the chart: Bright cells, wide span, big footer delta agreeing with direction.

**F2 absorption** (hindsight): High effort, low effect — someone is standing there. 16.0% of atoms. 82.5% of all range-travel the 1-minute lens discards hides inside F2 cells: absorption minutes are internally violent. On the chart: Bright cells piled at the same prices, column going nowhere — the pile-up without the march.

**F3 hollow** (hindsight): Effect without effort — price drifting on air. 22.4% of atoms. On the chart: Dim cells but the column spans far; nobody paid for the trip.

**F4 dead** (hindsight): Neither effort nor effect. 26.9% of atoms. On the chart: Dim, short, forgettable.

**doji-atom** (live): Travel-ratio exactly 0 (open = close). 8.0% of atoms — the pure-rotation marker. On the chart: The column that ends where it began.

**probe-atom** (hindsight): High-effort round-trip minute (effort_pct > 80, travel < 0.3). ~6.7/day, 75.3% graded F2. Confirmation events co-locate with them at 37.1% vs a 16.2% base — but no better than high-effort one-way minutes: effort is the signal, the round trip is texture. On the chart: A violent column that slams back to where it started — the sub-minute fight compressed.

**pivot-atom** (hindsight): The shared border minute between consecutive legs (leg k's last = leg k+1's first). 63% graded F1 — legs die hot, by opposition, not exhaustion. On the chart: The loud column at the turn — NOT a quiet fade.

**micro-stall** (hindsight): The interior "1-2-1" cell motif — conviction, absorption, conviction resuming — a sub-leg pause. Partner word micro- distinguishes it from stall-stage (episode tier). The parry FAILS here: the leg continues. If the parry holds and force turns, you were watching a stall-stage instead — indistinguishable in the moment, named only in hindsight. On the chart: A thrust, a parry that fails, the thrust resumes (Steve's fencing frame, 2026-07-28). Bright / pinned / bright again, leg unbroken.


### Leg tier

**zigzag decomposition** (hindsight): The drawing rule that produces legs: redraw the day with the fewest alternating strokes that capture every swing bigger than the reversal threshold (20% of the day's final high-low range, floor 1.5 pts). A stroke extends while price makes new extremes its way; a beyond-threshold retracement ends it at its furthest point and starts the opposite stroke. Sub-threshold wiggle is absorbed into the stroke it happened during. Doubly hindsight: the threshold needs the final range, and a stroke's end is knowable only after the retracement. (Charting platforms ship the same idea as the ZigZag indicator, usually fixed-percent; ours is day-relative.) On the chart: The day traced with the fewest pen strokes — on 7/22 the threshold was 7.65 pts and the day compressed to four strokes.

**leg** (hindsight): One element of the day's zigzag (reversal threshold 20% of final day range, floor 1.5 pts). Median 15 min, 7.25 pts. The unit the archetypes name. ("Move" is retired as a unit word; option-structure legs must compound as option-leg / spread-leg.) On the chart: One directional swing on the candle companion — the thing you'd draw with one pen stroke.

**flush-leg** (hindsight): Fast and big — pace >= 0.75, effect >= 70. 13.7% of legs; median 16.75 pts in 16 min, giveback 0.05. 76% occur on D-days. The tradeable V-dump leg. On the chart: The steep cliff. On candlesticks — the elevator-down (or up) you already recognize.

**steady-leg** (hindsight): Mid-pace pure-conviction residual; the most force-confirmed class (alignment 0.95). ~18% of legs. The "trust the tape" reference. On the chart: A clean staircase — direction, pace, and delta all agreeing.

**leg-grind** (hindsight): Slow but big — pace < 0.38, effect >= 70. 6.0% of legs, median 66 min. Over-indexes P-days (trend-day crawl). On the chart: The all-afternoon escalator that never gives an entry.

**counterforce-leg** (hindsight): Big leg whose delta disagrees with its direction (effect >= 60, force misaligned). 4.2%; skews DOWN 41/28 — price falling through net buying: trapped-buyer drops. (Renamed from "squeeze-leg" — squeeze is an up-cloud word; the bare name would have baked in a direction inversion.) On the chart: Falling prices with blue (buy) footers — the tape arguing with itself. Direction Inversion Watch territory.

**absorption-stall** (hindsight): Leg-scale F2 — heavy effort, little net progress. 9.6% of legs. On the chart: A fat sideways smear of bright columns.

**hollow-glide** (hindsight): Leg-scale F3 — distance covered on thin participation. ~8% of legs. On the chart: A drift you could wave your hand through.

**probe-fade** (hindsight): Small leg that pokes out and surrenders it — giveback >= 0.30 with effect < 50. 7.8% of legs. On the chart: The failed little excursion — out, nothing there, back.

**dead-drift** (hindsight): The residual majority — 32.4% of legs. Nothing happening, honestly labeled. On the chart: The chop between the stories.


### Day tier

**day-sequence** (hindsight): The session's ordered archetype string — a day-type read from the inside. 2026-07-22 reads flush-leg, steady-leg, leg-grind, steady-leg. On the chart: The day's story told in four to eight words.


### Episode tier

**episode** (live): The recognizer's unit of work at 2,000-trade bar resolution — one engagement of one anchor through the four stages. LIVE — this is the tier that emits in real time and the tier your yea/nay rides on. On the chart: The Anatomy row in the drill; the thing the coach arms and walks.


### The four stages

**flush-stage** (live): Stage 1 — aggressive break through a price-level. Sub-minute; invisible to atoms. Leg-scale correlate: the flush-leg. On the chart: The spike through the armed plan-level — often inside a single column.

**stall-stage** (live): Stage 2 — aggression continues, extreme stops extending. Atom-scale correlate: F2-in-tail (absorption-death), which lifts the confirm-conditional from 0.46 to 0.60. On the chart: The parry that HOLDS — sellers still thrusting, lows shrinking, nothing given (7/22 footers 1-3).

**flip-stage** (live): Stage 3 — delta turns against the break (threshold 150 contracts, ~7% of bar volume: machine-legible, not eye-legible). Its 1-minute shadow is the pivot-atom. On the chart: You will NOT see it in cells; the coach calls it. Footer sign change is the after-the-fact trace.

**confirm-stage** (live): Stage 4 — a close back across the price-level with opposite evidence. The recognizer emission is a confirmation-event. Atom correlate: the conviction head ("11"/"111" leg openings). On the chart: The retake candle/column closing back through the price-level.


### Orderflow primitives

**sweep-print** (live): One aggressive order eating multiple book price-levels (>= 3 ticks). Your candlestick-hindsight "sweep" — it kept its name, compounded. On the chart: The long single-print tail; on candles, the wick you already spot.

**absorption-read** (live): Book-level verdict — aggressor threw size, passive side refilled (from MBP-1 quotes). Outcome word (held/broke/lifted-away) is currently prose-only; enum field is queued code work. On the chart: Price pinned while the footer volume climbs; needs book data to grade.

**delta-divergence** (live): New price extreme on weaker aggression than the prior extreme — the exhaustion tell. On the chart: New low, smaller red footer than the last low made.

**imbalance-stack** (live): >= 3 consecutive diagonal bid/ask dominances (3:1) — one side owning a price ladder. On the chart: A diagonal run of lopsided cells.


### Level states

**level-state** (live): The renderer's per-plan-level state machine, close-based: untouched -> tested/held -> broken -> reclaimed. RECLAIMED is the failed-breakdown pattern rendered in place — the same market event the episode tier confirms from orderflow, on a slower clock. On the chart: The plan-level line's color/style and state word in the HUD on the /ES chart.


### Cross-tier signatures

**V-signature** (hindsight): Prior down flush-leg <= -8 pts, confirmation-event within 3 min of the new up-leg. 77.5% wins vs 46.9% base (31/40, hindsight attribution). The measured V-dump fly entry. On the chart: The cliff, the turn, the immediate retake — your butterfly setup in taxonomy words.

**host-leg** (hindsight): The leg containing a confirmation-event. Direction agreement splits win rate 66% vs 19% — the strongest single hindsight separator. Stays a diagnostic until a live proxy exists. On the chart: Is the setup swimming with or against the swing it lives inside.

**leg-boundary-trap** (hindsight): Down-leg dying by absorption (F2 tail) then an up-leg opening on conviction — the four-stage sequence at leg scale. 27.6% of down-up pairs; stall-conditional 0.60 vs 0.46. On the chart: Pile-up at the low, loud turn, bright staircase out.
