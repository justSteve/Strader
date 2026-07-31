# Fundamental Units of Orderflow — NotebookLM Source Bundle

This bundle teaches a measured vocabulary for ES/SPX price action, built for a
trader learning to read footprint charts. It contains: (1) narratives of two
real trading days told in the vocabulary — 2026-07-22 and 2026-07-24, (2) five
short teaching essays, (3) the full glossary, and (4) a plain-words guide to
the measurement layer — how the accuracy of the signals is scored. Everything
is derived from 263 measured trading days.
Good audio-overview angles: the two day-stories compared (7/22's trap sprung
before the open vs 7/24's Failed Breakdown caught entirely on film); why every
label carries a confidence grade ("grades not gates"); the fencing metaphor
(thrust, parry — does the parry hold?); what a trader can know live versus
only in hindsight; and why a signal that fires a fourth time at the same
price is a warning rather than an invitation.

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

---

# The Day in Fundamental Units — Friday 2026-07-24

**Bead:** st-4wd · **Form:** measured narrative, sibling of the 2026-07-22 account —
every number below is pulled from `data/measurement/moves/{atoms,moves}.jsonl`
(run `20260728T123632Z`: 390 atoms, 7 legs, day_type `b`, coverage rth), the
recognizer record `data/measurement/replay/signals_2026-07-24.jsonl` (run
`20260731T042819834897Z-7eb5177`, 193 events), the graded confirmations in
`data/measurement/acuity-run2-confirmations.jsonl` (run `20260727T054148Z`, 9 rows),
or — for the prologue and nothing else — the Mancini letters of 07-23 and 07-24,
clearly attributed. Nothing is remembered or embellished. Corpus norms cite the
taxonomy (`docs/measurement/orderflow-fundamental-units.md`, Draft 2), not the
lexicon's stale figures. **Vocabulary:** terms appear **bold** on first use; every
label carries its grade-band, per `docs/lexicon/lexicon.yaml`.

**Coverage note, before anything:** the 2026-07-24 corpus is exactly RTH,
08:30:00–15:00:00 CT. Unlike 7/22 there is no pre-market tape — and none is
needed. The day's marquee Failed Breakdown printed *inside* coverage. The
overnight story below is letter-attested, not measured, and says so.

---

## Prologue — before the tape (letter-attested, not measured)

Everything in this section is Mancini's account, not ours. The 07-23 plan letter
laid the map for Friday: supports "7438 (major), 7429, 7424, 7418, 7412 (major)";
resistances "7447 (major), 7459, 7464, 7474 (major)" up through "7506 (major)."
The 07-24 recap letter tells the overnight: ES chopped through the evening, ran
to 7464 — his first target up — by 3:45AM ET, and set "a clear shelf of lows
set at 7438 between midnight at 3am" [sic]. Then, in his words: "At 945AM
[ET; 08:45 CT], ES sold off down to 7432... ES flushed and recovered a clear
shelf of lows set at 7438... We recovered this shelf around 10:05AM [09:05 CT]
and ripped." Elsewhere in the same letter the elevator drop is "from 7465 down
to 7434" and the recovery "ripped to 7490+." The letter disagrees with itself
by two points on the low; the measured record (below) says the day's low was
7431.5. Keep the shape in mind — shelf lost, low flushed, shelf recovered,
rip — because this time the whole thing happens on film.

## Act I — the Failed Breakdown, on film this time (08:30 → 10:16)

The first **atom** — one clock minute, the smallest unit we grade — opens loud:
12,590 contracts (**effort**, 99.5th percentile of the day) for +2.25 net
(**effect**, 72.8th) — **F1 conviction** in the **solid grade-band** (0.456). The
second minute is a **probe-atom** and a **doji-atom** at once: 7,987 contracts,
**travel-ratio** 0.00 — a full round trip inside the minute — **F2 absorption**
in the **strong grade-band** (0.872). Two minutes in, the tape is already fighting.

The recognizer — one tier below, on 2,000-trade bars — is working the 7447
plan-level. Its first engagement runs the full four stages: **flush-stage** 08:40:06,
**flip-stage** 08:42:34, **stall-stage** 08:48:07, and a **confirmation-event** at
08:49:23 (confidence 0.8). Sixty-six seconds later the market runs it over. At
08:50:28 a **sweep-print** takes nine book levels at once (7450.00 → 7444.25,
206 contracts), and the elevator arrives: the 08:50 atom prints −8.50 on 7,139
contracts (97.9th / 99.2nd, F1 strong-band 0.958), 08:51 adds −6.75 (F1
strong-band 0.934).
Summing atom nets, the tape drops 23.25 points between the 08:49 local high and
the 08:59 trough. The recognizer opens a second 7447 engagement into the hole
(08:50:28) and later kills it — invalidated 09:00:27, no reclaim.

At the bottom the record shows the fight in book-level detail. The 08:56:52
**absorption-read**: buyers threw 236 contracts at the 7436.50 ask, got refilled
3× — "absorbed, level broke." Three **delta-divergence** reads stamp the lows —
new swing lows 7434.0 (08:57:07) and 7435.0 (08:59:26, 09:05:03) on weaker
aggression each time, the exhaustion tell. The day's low, 7431.5 (RunMeta), is
touched inside 08:58–09:13: the graded 08:58 entry's 15-minute adverse excursion
is exactly 8.0 points from 7439.5. That is the letter's "sold off down to 7432,"
measured. Note the clock, honestly: the letter says 9:45AM ET (08:45 CT); the
measured elevator minutes are 08:50–08:59 CT.

Then the recovery the letter calls the 10:05AM [ET] Failed Breakdown. The 09:00
atom prints +6.50 (F1 strong-band 0.898), 09:08 +7.25 (95.6th / 99.0th, F1
strong-band 0.912). The recognizer confirms the 7447 failed_breakdown twice more — 09:21:23
and 09:55:25, each through all four stages. The graded record (a different run,
anchored at Mancini's 7438 — more on that below) agrees: its 09:08 entry wins
(+15.5 before −4.25), and its 09:55 entry at 7451.75 is near-perfect — adverse
excursion 0.5 points, favorable 37.75 within thirty minutes. "Ripped to 7490+,"
letter and tape in agreement.

The climb to the top of the leg is thick with structure. Twenty probe-atoms
print today against a corpus norm of ~6.7/day (§2.4 slice: effort_pct > 80,
travel < 0.3, range ≥ 2) — seven of them in 08:31–09:03, six more in 10:02–10:30.
The leg's cell string carries fourteen **micro-stall** motifs (the `121` trigram:
conviction, absorption blink, conviction resuming) in 104 trigram slots — 13.5%
against the corpus interior norm of 3.9%. The tape paused constantly and never
broke. At 10:00:54 an absorption-read catches buyers being absorbed at 7466.25;
at 10:11:21 comes the day's highest-confidence read (0.985): sellers threw 485
contracts at the 7474.25 bid and were refilled 5× — "absorbed, level lifted
away" — inside the 10:11 atom, itself a monster probe-atom: 13,676 contracts
(99.7th percentile), 11.25 points of range, travel 0.20. Two F2 atoms follow
(10:12 grade 0.492, 10:13 grade 0.194) — sellers pressing, absorbed — then the
answer: 10:14 prints +10.50 (98.5th / 100th, F1 0.970) and the leg's last atom,
10:15, +9.25 on 10,334 contracts (99.2nd / 99.5th) — F1 at grade 0.984, the
best-graded atom of the day. The leg dies at maximum volume, going up.

Now the whole run as a **leg** — the zigzag's unit: +43.25 points of 45.5
extreme in 106 minutes. **Pace** 0.429 (extreme-points per minute), **giveback**
0.050 — it kept what it took. Its **force** (+5,082, signed delta — never
conflate with unsigned effort) agrees with its direction. At leg scale it grades
F1 in the strong grade-band (0.822; effort 96.7th / effect 91.1st, corpus-wide).
Apply the archetype cascade by hand: not a **flush-leg** (pace under the 0.75
**cutpoint**), not a **leg-grind** (pace above 0.38), force aligned, giveback
small, pure-F1, pace in the 0.38–0.75 window — a **steady-leg** (core), the
"trust the tape" class (11.2% of corpus legs). Its **archetype-grade** — distance
to the nearest reassigning cutpoint, in corpus-percentile units — is 0.114: the
**lean grade-band**, and honestly only a whisker above the coin-flip line, because
its pace percentile (39.8) sits 5.7 points from the leg-grind edge (34.1). Lean
on the label accordingly.

And here the leg lens must confess. The zigzag's reversal threshold today is
13.0 points (20% of the 65.0-point final range), and the entire morning Failed
Breakdown — down 23.25 summed-net points, back up — lives *inside* leg 1. The excursion
happened in the decomposition's seed phase, before any leg direction existed;
the stored record absorbs the day's marquee event into the interior of one
up-leg. This is the documented mega-leg limitation (taxonomy §5.3): on rth days,
leg-boundary-trap resolution lives at the atom tier; the leg tier supplies only
regime. The
atoms and the recognizer filmed the Failed Breakdown; the leg never saw it.

**The record's far-anchor noise, disclosed.** The recognizer's anchor set this
run was Mancini 7412 / 7447 / 7474 / 7506 — and 7506 sat above the day's entire
range (high 7496.5), 7412 below it (low 7431.5). What did they print? At
08:33:05, with the recognizer's neighboring swing prints at 7442.25 (08:31:23)
and 7448.25 (08:34:02), the record shows level_reclaim engagements
*forming* at 7474 **and at 7506** — the latter some sixty points overhead —
both invalidated 31 seconds later. That is the recognizer's known proximity
blind spot (st-98z item 4), the 7/22 account's 7575 analog: "price below
anchor" counts as a flush-stage no matter how far below. 7412 printed nothing
at all — zero events all day, a silent anchor. And the plan-level the letter's whole
story turns on, 7438, is **not in this run's anchor set** — the graded
confirmations run (20260727T054148Z) anchored 7438 and nothing else. The two
records watch the same tape through different keyholes; neither carries the
other's verdicts.

## Act II — the blink at the top (10:15 → 10:20)

Legs die hot, and the **pivot-atom** — the shared border minute where one leg
ends and the next begins — is the 10:15 monster above (F1, 0.984). What follows
barely exists: five minutes, −3.75 net of 5.5 extreme from its origin, pace
1.100, giveback 0.318, force −502 (aligned). At corpus scale it grades **F4
dead** in the strong grade-band (0.756; effort 12.2nd / effect 6.1st
percentile). The cascade lands on **probe-fade** — out,
nothing there, back (giveback ≥ 0.30, effect < 50) — but its giveback percentile
(92.3) sits 1.0 from the cutpoint's (91.3): archetype-grade 0.020, the
**coin-flip grade-band**, unreportable bare. Report the straddled pair:
*probe-fade / dead-drift*. Either way it is the blink between two stories, and
its second-to-last atom (10:18, F2 solid-band 0.348, 4,326 contracts, travel
0.12) is an **absorption-death** marker — the F2-in-tail signature that lifts
the odds the next up-leg opens on conviction (0.46 → 0.60 corpus-wide; the lift
runs 1.85× on b-final days).

## Act III — borrowed conviction (10:19 → 11:11)

It does open on conviction — head cells `111` — and the recognizer is faster
still: a failed_breakdown at 7474 forms at 10:20:07, flip-stage at 10:20:29, and
the confirmation-event lands the same second, 10:20:29 — the only confirmation
of the day that skips the stall-stage. One minute into the new leg, at the
leg-boundary: textbook **leg-boundary-trap** geometry (F2 in the dying leg's
tail, conviction head on the new leg). Honesty clause: this is *not* a
**V-signature** — the prior down-leg's whole extreme was 5.5 points against the
signature's ≥8-point flush-leg requirement. Small leg-boundary-trap, small spring.

The leg itself: +18.75 of 19.0 extreme in 52 minutes, pace 0.365, giveback
0.013, force +2,512 aligned. And it is the day's designated humility lesson —
the case the vow exists for. At leg scale it grades F1 **at 0.004**: effect
percentile 50.2, two-tenths of a point from the cell-boundary. A coin-flip-band
cell label is unreportable bare, so the leg-scale claim is the pair *F1/F2*.
The archetype call inherits the same razor edge: pure-F1 residual, pace 0.365 —
below the steady window, so *steady-leg, off-pace-slow flag*; nudge effect down
two-tenths of a percentile and it reads *absorption-stall*. Report it as the
coin-flip pair — *steady-leg (off-pace-slow) / absorption-stall*, archetype-grade
0.004 — and note the second thin margin: its pace percentile (32.3) is 1.8 from
the window edge (34.1), so even the off-pace flag versus core is nearly a
coin-flip. The label is not embarrassed; it is telling you exactly how much to lean
on it: almost nothing. What is *not* ambiguous: 52 minutes of aligned buying
that kept 98.7% of its extreme.

## Act IV — the trapped-buyer slide (11:10 → 12:10)

On 7/22 the **counterforce-leg** was a creature of the epilogue — an archetype
seen only in other days' tape. Today it walks on stage. The pivot-atom at 11:10
is quiet-ish (F1 lean-band 0.266), and — the record's own wrinkle — the day's
printed high is *not* at the pivot-atom: RunMeta's range high is 7496.5, and the
recognizer's 11:27:52 delta-divergence reads "bearish: new swing high 7495.25"
seventeen minutes *after* the close-based zigzag turned. The down-leg's interior
contains the day's absolute high; the 1-minute-close lens and the bar-level
extremes disagree, and the leg fields cannot show it (§0.1 — leg structure is
doubly hindsight).

The leg: −29.75 of 30.0 extreme in 60 minutes, pace 0.500, giveback 0.008 — it
closed one tick from its extreme. Effect 72.8th percentile. And its
force is **+2,654 — net BUYING, against a falling leg**. The misalignment
percentile is 97.1 against the 75.9 zero-crossing: price fell thirty points
*through* buyers the whole way down. Cascade: **counterforce-leg**
(mis > 0 ∧ effect ≥ 60), archetype-grade 0.256, lean grade-band — the binding
axis is effect (72.8 vs the 60 cutpoint); the misalignment itself is solid. The
corpus says this class skews down 41/28 — trapped-buyer drops — and the
absorption-read at 11:31:25 shows one cohort of them: buyers threw 418 contracts
at the 7485.50 ask, refilled 2×, "absorbed, level broke." When you see falling
price with blue footers, this is what it looks like at leg scale — Direction
Inversion Watch territory by construction.

Inside this leg the recognizer runs a level_reclaim at 7474 through all four
stages — flush-stage 11:47:52, stall-stage 11:51:46, flip-stage 11:54:22,
**confirmation-event 11:59:14** — a bullish confirmation fired inside a falling
**host-leg**. The
corpus grades that context 19.2% (hindsight attribution; the live proxy is
unbuilt). This run carries no ±5 verdict for it — the graded file watches a
different anchor — so the record honestly cannot say how it resolved. What the
tape shows: the leg kept falling for ten more minutes.

## Act V — the hollow bounce (12:09 → 12:35)

The 12:09 pivot-atom is the quiet kind — graded **F3 hollow** at 0.108
(lean grade-band, 0.008 off the coin-flip line), 1,887 contracts, the
turn nobody paid for (63% of corpus pivot-atoms are F1; today's six split three
loud, three quiet — the morning turned loud, the afternoon turns quiet). The
bounce retakes +16.25 of 16.75 in 26 minutes at pace 0.644, force +1,137
aligned — but at corpus scale it grades F4 (effort 17.8th / effect 40.4th):
**dead-drift**, archetype-grade 0.192, lean grade-band, nearest alternative
**hollow-glide** across the effect axis. Sixteen points on air. Its tail is all
F3/F4 — a **quiet-death**, depleted rather than opposed — and the leg it hands
off to is the day's longest.

## Act VI — the long unwind (12:34 → 14:26)

−45.25 points of 46.5 extreme across 112 minutes, pace 0.415, giveback 0.027,
force −2,089 aligned. Read its atom string and it is wall-to-wall F4 dead and
F3 hollow — 55 F4 and 32 F3 of 112 atoms, 78% of the leg drifting down on air —
yet at leg scale it grades F1 in the solid grade-band (0.558; effort 77.9th /
effect 91.5th). Both are true: atom grades are day-relative texture, leg grades
are corpus-wide mass; 112 small efforts sum to a large one. Say which tier you
mean. The cascade: pure-F1, pace inside the window — steady-leg — but its pace
percentile (38.0) sits 3.9 from the leg-grind edge: archetype-grade 0.078,
**coin-flip grade-band**. Report the pair: *steady-leg / leg-grind*. Whichever
word wins, it is the b-day's signature stroke: the letter's morning rip, taken
back a point deeper at nearly the same pace (0.415 against the rip's 0.429).

The recognizer spends the leg trying to catch the falling knife at its two
anchors and failing honestly. The second 7474 level_reclaim (formed 12:39:45)
never confirms — invalidated 13:20:40. A 7447 failed_breakdown forms 13:31:27,
reaches "flush+flip+stall" (the record's own stage string) by 13:36:49, and dies
unconfirmed at 14:04:31. The
graded record at 7438 is blunter: its three mid-leg entries — 13:36, 13:57,
14:12, all bullish, all inside a falling host-leg — all lose at the ±5 bracket
(the 13:57 entry takes 14.0 points of adverse excursion for 2.5 favorable).
Confirmations against the host-leg are the corpus's graveyard, and today they
died on schedule. The absorption-reads frame the bottom: 14:03:31, sellers threw
112 contracts at the 7441.50 bid, refilled 3×, "level lifted away"; 14:04:26,
buyers threw 188 at 7443.00, "level broke" — both sides absorbed within a
minute, six ticks apart. The 13:42:47 delta-divergence stamps the afternoon
low zone: new swing low 7435.5 on weaker aggression — the tape revisiting the
morning's basement (7431.5) and declining to break it. The leg's last atom,
the 14:25 pivot-atom, grades F4 at 0.348 (solid grade-band): 1,850 contracts,
travel 0.10. The day's
biggest leg ends in a whisper.

## Act VII — the last fight (14:25 → 15:00)

The close leg opens dead — head cells `444` — then wakes up. +14.25 of 17.5
extreme in 35 minutes, pace 0.500, giveback 0.186, and an aligned force of
+4,918 net buying on 132,514 contracts — second in size only to leg 1's +5,082,
in a third of the minutes. At corpus scale it grades
F2 (effort 60.1st / effect 35.2nd) → **absorption-stall**, archetype-grade
0.202, lean grade-band — and the honesty clause cuts twice here. First, the
taxonomy's off-diagonal bar (§3.2): an F2 leg claim wants solid-band grade
(> 0.3) minimum, and this one is below it — so report the pair
*absorption-stall / dead-drift* (the nearest alternative, across the effort
axis), with *probe-fade* only 0.224 away across the giveback
axis. A crowded neighborhood; hold the label loosely. Second, the graded record:
its 14:44 and 14:49 bullish entries both lose at ±5 before the 14:53 entry
finally wins (+12.0 against 0.5 adverse) — even the winning side of a rising leg
paid twice for position first.

Then the MOC window, which the corpus says owns the day's densest effort — and
today obliges. The 14:58 atom is a probe-atom *and* doji-atom: 4,597 contracts,
travel 0.00, F2 strong-band (0.820). Twenty-three of the day's 34 absorption-reads
stamp 14:58–15:00, both directions at once: buyers absorbed at the 7443.50–7450.00
asks, sellers absorbed at the 7442.00–7449.25 bids, refill ratios to 6×. And
14:59 is the loudest atom of the day: **38,868 contracts — 100th percentile —
for a force of minus six.** Thirty-nine thousand contracts of effort and the
signed aggression netted to −6, while price ranged 10.75 points and closed +3.75.
F1 at 0.790, and the purest exhibit in the file of why effort and force are
different axes. The final absorption-read, 14:59:59: "absorbed, level held (end
of stream)."

## The day in one line

**Day-sequence:** steady-leg *(lean, 0.114 — a whisker off the leg-grind edge)* →
probe-fade *(coin-flip, pair with dead-drift)* → steady-leg, off-pace-slow
*(coin-flip, pair with absorption-stall — the F1 cell itself grades 0.004)* →
counterforce-leg *(lean)* → dead-drift *(lean)* → steady-leg *(coin-flip, pair
with leg-grind)* → absorption-stall / dead-drift *(lean, below the off-diagonal
solid bar — reported as a pair per §3.2)*.

Three of seven archetype calls land in the coin-flip grade-band; the closest
published baseline is the ~19% coin-flip share for leg *cell* grades (the
taxonomy publishes no grade-band distribution for archetype-grades) — by any
reading,
this day was drawn mostly on the cutlines. The
stored day-type is **b**, and the recognizer's profile read says why: "bulge
sits in the lower range (POC at 26% of range) under a thin upper stem —
one-sided push down, then acceptance below." The b-day median leg is the
corpus's biggest, and today's median leg is 18.75 points against the corpus's
7.25. Summed over 390 atoms: 1,077,442 contracts, day force +12,978, and a
close-to-close sum of nets of **−0.75** — a round trip. The morning rip
(+43.25) and the afternoon unwind (−45.25) are the same stroke drawn twice
with the sign flipped, which is what this b-day looks like from the inside.

## Epilogue — creatures not seen today

Three archetypes never got a bare label today (one lurks as a coin-flip
pair-partner, one as a lean-band nearest alternative; none was assigned). Their best sightings from other days in the
263-day corpus — real dates, real numbers, nothing staged:

- **flush-leg** — fast AND big, the tradeable V-dump leg; today's tape never
  paired its speed with its size (leg 2 had the pace, 1.100, and a 6th-percentile
  effect). The corpus specimen: 2026-03-09, 13:00 — **+109.75 points of 112.5
  extreme in 100 minutes**, pace 1.12, giveback 0.024, effort 99.6th / effect
  100th. Kept essentially all of it.
- **leg-grind** — the trend-day crawl; it haunted today as leg 6's coin-flip
  pair-partner (and leg 1's nearest edge) but never won an assignment. Specimen: 2025-10-29, 08:57 —
  **−62.75 points over 288 minutes**, pace 0.234, effort 99.1st / effect 97.7th.
  Nearly five hours downhill and never a clean entry.
- **hollow-glide** — distance on air, leg-scale F3. Specimen: 2026-03-18,
  13:00 — **−35.0 points in 60 minutes on 23,407 contracts** (effort 40.3rd
  percentile). Nobody paid for that trip, and it traveled anyway.

And one homecoming, with a correction attached: the **counterforce-leg**
printed live today as Act IV. The 7/22 epilogue could only point at a
specimen — 2026-07-27's −81.75 on net buying — but the enforced cascade files
that leg **flush-leg** (pace 1.130, effect 98.6th; flush-leg is checked first
in the priority order), so its genuine misalignment (+3,033 of net buying
against an 81.75-point fall) never gets to name it. No 2026-07-27 leg
classifies counterforce — today's Act IV is the class's first true appearance
in this drill series, not its second. The bestiary rotates.

## Coda — what was LIVE in this story

Everything narrated from atoms' raw fields (volumes, nets, ranges, travel,
force), every stage transition, every confirmation-event, every absorption-read,
sweep-print, and delta-divergence: **LIVE** — knowable in the minute or the
bar. Every percentile, cell, grade-band, leg-boundary, pace, giveback,
archetype, host-leg attribution, the ±5 verdicts (computed after the fact from
excursion records), the day-type letter, and the day-sequence itself:
**HINDSIGHT** — the grading of the tape after the fact, which is exactly the
authority hindsight holds in this system. Two further things this record
structurally cannot see, said plainly: the atoms carry no absolute prices, so
every price in this narrative comes from the recognizer record or the letters;
and the two recognizer runs watched different anchor sets (7412/7447/7474/7506
vs 7438 alone), so the five signals-run confirmations and the nine graded
verdicts describe overlapping but non-identical setups — neither is the other's
scorecard. The narrative you just read is the hindsight layer teaching the live
layer's vocabulary; your seat only ever gets asked about the live half.

---

# Plain-Words Glossary — Read This Before Any Numbers Conversation

**Bead:** st-v95 · **Date:** 2026-07-31 · **Why this exists:** on 2026-07-31 an
accuracy briefing reached Steve in measurement-harness vocabulary — *anchor*,
*fire*, *scoring* — none of which any training channel had defined. This
glossary is **channel zero**: plain trader language first, the term second.
Nothing here assumes you remember any other document.

---

## Part 1 — The measurement layer (the words the accuracy numbers are spoken in)

**Anchor** — a price level we told the software to watch. Almost always a level
from Mancini's letter (7438, 7447…), sometimes a volume shelf from yesterday's
trading. The software does nothing except watch how the tape behaves when price
reaches an anchor.

**Signal / confirmation** — one buy call at an anchor. The pattern is the one
you already trade: price breaks below a support, comes back up through it, the
software says "buy here." In the measurement records this is called a
*confirmation* (the recognizer confirmed the pattern completed).

**Fire, fire-index** — a count of how many signals one anchor has produced
today. The 9am signal at 7438 is fire #1 at that level; the 1pm signal at the
same level is fire #3 or #4. The count matters because quality collapses with
repetition: first signals win about half the time, fourth-and-later signals win
about a third. A level that keeps needing to be re-defended is telling you the
defense is failing.

**The scoring rule (first-touch ±5)** — how every signal is graded. Watch the
next 30 minutes after the signal: if price moves 5 points in the signal's favor
before it moves 5 points against, the signal is a **win**; the reverse is a
**loss**; neither within 30 minutes is **undecided**. Deliberately strict — a
signal that eventually rallied 15 points but dipped 5.5 first grades as a
*loss*. It measures call quality, not profit.

**Favorable / adverse excursion** — after a signal, the furthest price moved
your way (favorable) and against you (adverse) inside the window. The records
abbreviate these MFE and MAE. "Median favorable 10.5 vs adverse 5.75" means the
typical signal in that group ran 10.5 points for you and 5.75 against you.

**Backtest / the corpus** — every accuracy number comes from replaying the
software over *all* stored history (263 days of tape, 182 of them scorable
because we know that day's letter levels), as if it had been watching live.
When a briefing says "423 signals across 182 days," that is the backtest
talking — not any single day.

**Tune half / validate half** — the honesty split. Numbers are checked
separately on older days (before June) and recent days (June onward). A pattern
that only shows up in the old half is treated as suspect. When a briefing says
"held out-of-sample," it means the recent half agrees.

**Win rate is not P&L** — 45% under a strict symmetric race can be very
profitable or very unprofitable depending on size, costs, and what you do after
the first 5 points. The scoring tells you *which calls to trust*; what a trade
earns is a separate question, and sizing is your seat.

## Part 2 — The taxonomy, one line each (full versions: essays 09 + lexicon)

**Atom** — one clock minute of tape, the smallest thing we grade.
**Effort** — how many contracts traded in it (how much business).
**Effect** — how far price moved (what the business bought).
**Force** — which side was pressing (signed; can disagree with direction).
**Cells F1–F4** — the four combinations of high/low effort × effect:
conviction / absorption / hollow / dead.
**Grade, grade-band** — how far a label sits from the dividing line: coin-flip
(too close to call — always spoken as a pair, "F3/F4"), lean, solid, strong.
**Leg** — one stroke of the day's zigzag; the unit swings are measured in.
**Archetype** — which of eight recurring characters a leg is (flush-leg,
steady-leg, leg-grind, counterforce-leg, absorption-stall, hollow-glide,
probe-fade, dead-drift).
**Pivot-atom** — the shared minute where one leg dies and the next is born.
**Stages** — the recognizer's four beats at a level: flush-stage → stall-stage
→ flip-stage → confirm-stage.
**Episode** — one whole engagement of price with a level, start to resolution.
**LIVE / HINDSIGHT** — the stamp on every quantity: knowable in the minute, or
only computable after the day completes. Percentiles, cells, legs, and
archetypes are all HINDSIGHT; stages, primitives, and raw counts are LIVE.

## Part 3 — Two instruments, not one

**The recognition engine** reads only the ES tape and the anchors. It is blind
to everything else.
**The MI gauge** reads market internals (the NYSE TICK) and each minute prints
one signed score, −100 to +100, always naming its driver in plain words
("TICK climax," "quiet tape"). It is a separate instrument built for *you*;
today it does not feed the recognition engine, and whether it should is an open
measured question (bead st-u05).
