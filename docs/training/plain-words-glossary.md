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
conviction / absorption / hollow / dead. The **F is for "frame"** — the codes
come from the drill catalog's single-bar *frame scenarios* (its siblings are
S1–S6 level-engagement scenarios and T1–T3 tempo scenarios), and the taxonomy
inherited those ratified names rather than minting new ones.
**Grade, grade-band** — how far a label sits from the dividing line: coin-flip
(too close to call — always spoken as a pair, "F3/F4"), lean, solid, strong.
**Leg** — one stroke of the day's zigzag; the unit swings are measured in.
**Archetype** — which of eight recurring characters a leg is (flush-leg,
steady-leg, leg-grind, counterforce-leg, absorption-stall, hollow-glide,
probe-fade, dead-drift).
**Pivot-atom** — the shared minute where one leg dies and the next is born.
**Stages** — the recognizer's four-part sequence at a level: flush-stage →
stall-stage → flip-stage → confirm-stage.
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
