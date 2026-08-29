# Final-Hour Lens Calls — the three lenses at 14:00 / 14:30 / 14:45, scored on 286 days

**Bead:** st-g0jo (*Final-Hour Acuity*, Stages 2–3) · **Measured:** 2026-08-29 ·
**Data:** 286 ES tape days (2025-05-27 → 2026-08-28); Mancini levels on 261 of
them; GexBot on 17–18 · **Scripts:** `scripts/measurement/final_hour_lens.py`
(extract + rule), `final_hour_lens_summary.py` (score) · **Rows:**
`data/measurement/final-hour-lens-2026-08-29.jsonl` (one per day per T)

## What was done

For every corpus day, at T = 14:00, 14:30 and 14:45 CT, each lens was rebuilt
from data stamped before T and made its call — **pin / down / up** — by a rule
written into the script header *before the first run* and not tuned since.
"Realized" is the close 5+ ES points from the T print (up / down) or inside 5
(pin). A directional call is a **hit** if the close went 5+ its way, a **miss**
if 5+ against, **flat** otherwise; edge = hit − miss. Heat is the adverse
excursion before the first +5 print on the hits.

The rules, in one line each (full text in the script):

- **Footprint** — down if price is in the bottom fifth of the 13:00→T box with
  the last 30 minutes falling on negative delta; up mirrored; else pin.
- **Mancini** — replay each letter level on the tape over 13:00→T (touched
  within 1.0, broke 2.0 through, reclaimed 1.0 back). Floor = held support
  within 10 below, lid = held resistance within 10 above. Lost support above
  → down; taken resistance below → up; floor and lid → pin; floor only → up;
  lid only → down; else pin.
- **GEX** — classic `gex_zero` majors. Spot above zero gamma and within 10 of
  the positive major → pin; below zero gamma → toward the negative major;
  above zero gamma with the positive major 10+ away → toward it; else pin.

The 08-28 calibration row reproduces the hand read on the footprint side:
box 7712.25–7727.25, buying absorbed (+995 delta on −8.25 of price), volume
at 0.31 of late morning, at the low edge of value → **pin**. Mancini: 7714
major held (41 print touches) with no lid inside 10 → **up**. GEX by the
classic majors: spot 7705 under zero gamma 7722 with the negative major at
7700 → **down**. It closed +7. The hand read's GEX leg used the state-tier
strike list (7705/7720 as the two long-gamma strikes), which is a different
reading of the same feed — see "GEX lens" below.

## The result — no lens turns 14:00 into a direction call

**14:00 CT.** 286 days; realized up 36% / down 29% / pin 35%.

| lens | calls (down / up / pin) | down: hit / miss | up: hit / miss | pooled edge | pin: close within 5 |
|---|---|---|---|---|---|
| footprint | 34 / 49 / 203 | 38% / 47% | 35% / 29% | **+0** | 38% (base 35%) |
| Mancini | 99 / 120 / 42 | 26% / 35% | 41% / 31% | **+1** | 40% |
| GEX (17 d) | 8 / 3 / 6 | 25% / 38% | 0% / 0% | −9 | 83% (5 of 6) |

The directional calls are a coin flip, and the coin is biased the wrong way on
the down side: both lenses' **down** calls missed more than they hit. Median
net move the call's way: footprint −0.25, Mancini +0.75.

**2025 vs 2026, 14:00 directional calls:** footprint +7 → −7; Mancini −6 →
+8. Both flip sign. By the standard set in the plan (the day-type gate,
st-gno7), neither is reported as an edge.

**In premium** (Stage 1 ITM single on the called side, 14:00 entry): footprint
calls, 77 OPRA days, median **−24%** at the close, positive on 44%; Mancini,
204 days, median **−5%**, positive on 45%; where the two agreed, 40 days,
median **−40%**. The −10% cut fired on ~90% of these trades.

**14:30 and 14:45** move the pin calls up with the base rate (pin base 42%
→ 47%; footprint pin 43% → 48%, Mancini pin 53% → 52%, close in box 64–78%)
and leave the down calls flat or negative at every T.

## What survived the split — one rule, small

**Footprint up at 14:45** (price in the top fifth of the box, last 30 minutes
rising on positive delta, 15 minutes to the bell): 2025 n=25, hit 36% / miss
16% (+20); 2026 n=15, hit 40% / miss 13% (+27). Median net the call's way
**+2.75**, heat before +5 on the hits 3.00. The base rate at 14:45 is already
up 30% / down 20–25%, so roughly half of that edge is the sample's own upward
lean into the close. Mancini up at 14:45 is +8 / +23 on the halves (n=117)
with a +2.00 median — same shape, same caveat. Nothing on the down side
survived: footprint down at 14:45 was +22 in 2025 and −19 in 2026.

What that is worth in Steve's units: a 3-point median with 15 minutes left,
which through the Stage 1 curve is the 0-to-+5 bin — the ITM single finishes
about +7% at the median. It is a lean, not the 10-point flush.

## The 10-point flush specifically

Base rate of a 10+ excursion from the 14:00 print: up 36%, down 40%. Among
the lenses' **down** calls at 14:00, the 10-point down excursion came on
54% (footprint, 2025), 57% (footprint, 2026), 25% and 36% (Mancini). The
footprint down call does raise the chance of a 10-point dip — from 40% to
~55% — but the close does not stay there (the call's hit rate on the close
is 33–46%, miss 43–54%). That is the shape of a dip that gets bought, and
the heat number says the same: on the footprint down calls that did hit at
14:00, the median adverse excursion before the first −5 was **5.75 points**,
the largest of any cell.

## GEX lens

17–18 days is not a measurement; it is recorded so the rows accrue. Two
things to fix before it is scored: (1) the rule reads the classic majors
(`mpos_vol` / `mneg_vol` / `zero_gamma`), while the 08-28 hand read used the
state-tier 0DTE strike list — the two disagreed on 08-28 (down vs pin), so
the lens as coded is not the lens on his screen; (2) 5–6 of the 23 GexBot
days have no row within 10 minutes of T. Both are a Stage 4 decision, when
the 14:00 page is generated live and the GEX leg can be read the way he
reads it.

## Cross-tabs recorded, not ruled on (14:00)

- Box position: bottom fifth → up 43% / down 31% / pin 26% (n=65); top → 31 /
  27 / 42 (n=81). The bottom of the box gets bought more than it breaks.
- Absorption (box delta against price): buy-absorbed n=42 → up 38 / down 29 /
  pin 33; sell-absorbed n=58 → 33 / 29 / 38. No signal.
- Energy (last-30 volume vs box average): dried (<0.8) n=25, hot (>1.2) n=27 —
  neither moves the split.
- A held Mancini major within 10 below (n=60): up 38 / down 35 / pin 27 —
  *more* two-sided than the rest, not a floor.
- Full-session days (n=53) — price vs value area and volume-drying vs late
  morning: n too small in every cell to say anything; kept for the accrual.

## What it settles for the program

- **Stage 2's answer is negative and it is the useful kind.** The three lenses
  as pre-registered rules do not carry a 14:00 direction call across 286 days;
  the 08-28 read was right on the day and the rule that reproduces it is at
  the base rate over the corpus. The plan's Stage 3 standard (both halves or
  nothing) was applied and nothing on the down side passed.
- **The rows are the asset.** 858 rows with every lens' state and the outcome
  including heat are the input to Stage 4's page (each lens' call beside its
  measured rate — those rates are now real numbers, mostly near the base) and
  to the drill (replay the T state, Steve calls it, score in premium).
- **Next measurable things, in order:** (a) rules that use the *combination*
  the hand read actually used — box position × energy × Mancini floor — as a
  single pre-registered rule, scored the same way; (b) the GEX lens read from
  the state-tier strikes on the accruing days; (c) T-15 features from st-9i7a
  (sell burst then limp drift) and st-vl3c, which this stage was meant to
  absorb and has not yet.
