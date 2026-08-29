# Final-Hour Combination Calls — the lenses read together, scored on 286 days

**Bead:** st-g0jo (*Final-Hour Acuity*, Stage 3 continued) · **Measured:**
2026-08-29 · **Data:** the Stage 2 rows (286 days × 14:00 / 14:30 / 14:45 CT,
Mancini leg on 261) · **Scripts:** `scripts/measurement/final_hour_combo.py`;
premium re-priced at each T by `final_hour_premium.py <base> <out> HH:MM` ·
**Rows:** `data/measurement/final-hour-premium-{1430,1445}-2026-08-29.jsonl`

Stage 2 had each lens call on every day and none carried a 14:00 direction.
The 08-28 hand read was not one lens — it was a footprint state read against
a Mancini level, and it called only because they agreed. This scores that
shape: seven rules that fire only when their parts line up and say nothing
otherwise, written before the run and not tuned. Coverage (how often a rule
speaks) sits beside its hit rate throughout, because a rule that speaks on
eight days is a story, not a measurement.

## The rules (first to fire wins; else no call)

| | shape | call |
|---|---|---|
| R1 flush | bottom quarter of the 13:00→T box, last 30 min falling on negative delta, **no Mancini support held within 10 below** | down |
| R2 launch | top quarter, last 30 rising on positive delta, **no Mancini resistance held within 10 above** | up |
| R3 pinned | a held Mancini level within 10 on *both* sides, tape quieter than its box | pin |
| R4 bought | bottom quarter, sitting on a held Mancini support within 5 (the failed-breakdown shape) | up |
| R5 sold | top quarter, under a held Mancini resistance within 5 | down |
| R6 lost | under a support that broke this window and was not reclaimed, nothing held below, still falling | down |
| R7 taken | above a resistance that broke this window, nothing held above, still rising | up |
| A1 / A2 | R1 / R2 **without** the Mancini clause — the ablations | down / up |

Scoring is Stage 3's: realized = close 5+ ES points from the T print; hit /
miss / flat; edge = hit − miss; both halves (2025 · 2026) reported for every
directional rule.

## 14:45 CT — where the combinations mean something

286 days · base up 30% / down 23% / pin 47%.

| rule | call | fires | hit | miss | edge | median net, call's way | heat before +5 on hits | edge 2025 · 2026 |
|---|---|---|---|---|---|---|---|---|
| **R2 launch** | up | 26 (9%) | **46%** | **8%** | **+38** | **+3.25** | 3.00 | **+33 (n15) · +45 (n11)** |
| A2 launch, no Mancini | up | 44 (15%) | 36% | 18% | +18 | +2.75 | 2.88 | +14 · +25 |
| R5 sold | down | 26 (9%) | 31% | 15% | +15 | +1.62 | 2.00 | +6 (n16) · +30 (n10) |
| R1 flush | down | 27 (9%) | 30% | 26% | +4 | +0.25 | 2.50 | +31 · −21 |
| A1 flush, no Mancini | down | 43 (15%) | 30% | 33% | −2 | −0.50 | 2.00 | +26 · −25 |
| R4 bought | up | 22 (8%) | 36% | 36% | +0 | +0.38 | 1.25 | −25 · +14 |
| R3 pinned | pin | 5 (2%) | 20% | — | — | — | — | — |
| R6 / R7 | | 2 / 4 | | | | | | too rare to read |

The combined caller speaks on 107 of 286 days (37%) and is silent on the
rest; on the days it speaks, hit 35% / miss 21%, edge +14.

**R2 is the one combination that holds.** Positive on both halves at every T
(14:00: +7 · +11; 14:30: +18 · +18; 14:45: +33 · +45), growing as the bell
approaches, spread across twelve of the thirteen months it fired in (one miss
in May 2025, one in November 2025). The Mancini clause is load-bearing: the
same footprint shape *with* a held resistance inside 10 above is what A2
adds, and it halves the edge at 14:45 (+38 → +18) and at 14:00 (+9 → +4).
That is the plain reading of "no lid" — a launch into nothing of Mancini's
runs; a launch into a level he named stalls.

What it catches is small: a median 3.25 ES points with fifteen minutes left,
heat of 3.00 before the first +5 on the hits. In premium, the ITM call bought
at 14:45 on those days (23 with OPRA): entry median 10.90, **at the close
median +43%, mean +38%, finished above entry on 65%, printed +25% on 87%**;
the −10% cut (about a point of premium) fired on 87% of them — the 3-point
heat again sits outside a 1-point cut, as it did in Stage 1.

Read the premium column with a caveat that does not apply at 14:00: over the
last fifteen minutes the SPX cash close and the ES print diverge by a few
points either way (MOC), which is the size of the move being scored. The
per-day pairing of ES net move to option return is still +0.94 for R2 and
+0.97 for R1, so the direction is faithful; the magnitudes are noisier.

## 14:00 CT — the flush shape is inverse

286 days · base up 36% / down 29% / pin 35%.

| rule | call | fires | hit | miss | edge | median net, call's way | edge 2025 · 2026 |
|---|---|---|---|---|---|---|---|
| **R1 flush** | down | 30 (10%) | 30% | **47%** | **−17** | −3.25 | **−23 (n13) · −12 (n17)** |
| A1 flush, no Mancini | down | 44 (15%) | 34% | 43% | −9 | −1.88 | −6 · −12 |
| R2 launch | up | 45 (16%) | 36% | 27% | +9 | +1.00 | +7 · +11 |
| A2 launch, no Mancini | up | 56 (20%) | 34% | 30% | +4 | +0.88 | +9 · −4 |
| R4 bought | up | 18 (6%) | 33% | 39% | −6 | −2.50 | −25 · +10 |
| R5 sold | down | 14 (5%) | 36% | 21% | +14 | +0.25 | −17 · +38 |
| R7 taken | up | 11 (4%) | 36% | 27% | +9 | +0.75 | +0 · +25 |
| R3 pinned | pin | 9 (3%) | 22% | — | — | — | — |

At 14:00 the combined caller speaks on 42% of days with edge +0 — as blank as
the single lenses. The one number that is not blank is R1, and it points the
other way: **price pressing the bottom of the box on selling, with nothing of
Mancini's held beneath it, closed 5+ higher on 47% of days and 5+ lower on
30%**, on both halves. Removing the Mancini clause (A1) softens it to −9, so
"no floor below" is part of the shape that gets bought, not a filter that
finds the flush. The same rule at 14:30 is −16 (−14 · −18). In premium the
14:00 put on R1 days closed at a median −29%; the 14:30 put −8%.

The 10-point excursion tells the rest of that story: on R1 days at 14:00 the
10-point *dip* does come more often than base (about 55% vs 40%, Stage 3), and
the close does not stay there. That is the measured shape of the final-hour
flush from this starting state — a dip that gets bought — and it is a number
about the *state*, not about any day Steve reads live.

## What did not fire, or did not hold

- **R3 pinned** (held Mancini level on both sides, quiet tape): 9 / 7 / 5
  days. The 08-28 configuration is rare in the corpus and cannot be scored.
- **R4 bought** (the failed-breakdown shape into the close): −6 / −10 / +0,
  sign-flipping across halves at every T. Sitting on a defended Mancini
  support at the bottom of the box does not produce the bounce by the bell.
- **R5 sold**: +15 at 14:45 on both halves (+6 · +30, n=26) but −17 · +38 at
  14:00 — the mirror of R2 without R2's consistency. Watch, not a finding.
- **R6 / R7** (level broke this window): 1–11 days. Mancini's levels are
  rarely lost or taken inside the 13:00→T window; the recognizer's own
  break-and-reclaim events (st-9i7a, st-vl3c) are the right source for that
  shape, which is item (c) in the bead.

## What it settles

- **One combination survives the standard: launch into no lid (R2), late.**
  It is a lean of ~3 points into the bell, worth about +40% on a 14:45 ITM
  call at the median, and it fires on one day in eleven. The Mancini clause
  earns its place in it.
- **The flush shape from the bottom of the box is inverse at 14:00 and
  14:30.** That is now measured on both halves, with and without the Mancini
  clause, and in premium.
- **The rows and both premium entry files are the inputs to Stage 4** — the
  page that shows each call beside its measured rate, and the drill.
