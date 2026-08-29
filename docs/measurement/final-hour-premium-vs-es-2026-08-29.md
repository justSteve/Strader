# Final Hour in Premium — what a 14:00 CT single actually paid, against the ES move

**Bead:** st-g0jo (*Final-Hour Acuity*, Stage 1) · **Measured:** 2026-08-29 ·
**Data:** 263 days holding both ES tape and OPRA SPXW prints (2025-05-27 →
2026-07-30; the OPRA pull stops there, so August 2026 has no premium column
yet) · **Scripts:** `scripts/measurement/final_hour_premium.py`,
`final_hour_premium_summary.py` · **Rows:**
`data/measurement/final-hour-premium-2026-08-29.jsonl`

Steve, 2026-08-29: *"process both to see what kind of correlation we can
find."* This is both scoreboards side by side — ES points and the option's own
prints — for the same hour on the same days.

## What was measured

Six hypothetical 0DTE singles bought at the first print after 14:00 CT: put and
call at **~10 ITM** (the futures-proxy single Steve leans to — the 08-26 paper
7685P was ~9 ITM at 10.10), **ATM**, and **~10 OTM**. SPX at 14:00 is inferred
from 0DTE put-call parity on 13:57–14:03 prints. Marks are that strike's own
prints to 15:00 CT. Print gaps are small at these strikes: the longest silence
in the hour is under 100 s on 90% of days for the ITM legs, under 50 s for the
others. Print-to-print noise is 0.10 pts on the ITM legs, a tick or less on the
rest.

"Right direction" below means ES finished the hour 5+ points the option's way.

## 1. Correlation — how faithfully each single follows the ES move

| single | entry (median) | corr: ES net move → option return at close | corr: ES excursion → option best mark |
|---|---|---|---|
| put ~10 ITM | 12.38 | **+0.91** | **+0.95** |
| call ~10 ITM | 11.70 | +0.83 | +0.95 |
| put ATM | 5.30 | +0.82 | +0.82 |
| call ATM | 4.80 | +0.71 | +0.85 |
| put ~10 OTM | 1.98 | +0.67 | +0.68 |
| call ~10 OTM | 1.30 | +0.58 | +0.80 |

The ITM single *is* the futures contract on its last day: nine-tenths of its
close-to-close result is the ES move. Moving out to OTM, the option's result
detaches from the move — it only pays when the move is large, and it does not
pay in proportion.

## 2. The payoff curve — ES points in your favour → premium at the close

ITM put and call pooled (n = 525 single-days), binned by how far ES finished the
hour in the option's favour:

| ES move for you (pts) | n | option at close (median) | finished > 0 | finished ≥ +25% |
|---|---|---|---|---|
| worse than −15 | 57 | −100% | 0% | 0% |
| −15 to −10 | 41 | −97% | 0% | 0% |
| −10 to −5 | 71 | −71% | 0% | 0% |
| −5 to 0 | 91 | −37% | 8% | 1% |
| 0 to +5 | 90 | **+7%** | 59% | 22% |
| +5 to +10 | 72 | **+47%** | 94% | 78% |
| +10 to +15 | 41 | **+72%** | 95% | 95% |
| +15 to +20 | 26 | **+113%** | 100% | 100% |
| +20 and more | 36 | **+199%** | 100% | 100% |

This is the shape Steve described, measured. Get the direction by 5 points and
the ITM single pays about half its cost; by 10, three-quarters; by 15, it
doubles. Miss by 5 and it loses a third; miss by 10, two-thirds; miss by more,
all of it. The curve is nearly linear from −10 to +20 — which is what a
delta-0.7-to-1 instrument should do — with the losses steepening past −10 as
the ITM put goes OTM.

## 3. Right versus wrong, per moneyness

Days where ES finished 5+ points one way (175 of 263 — two-thirds of final
hours pick a side):

| single | right side, close (median) | right ≥ +25% | right ≥ +50% | right ≥ +100% | wrong side, held to close | wrong, cut at −10% |
|---|---|---|---|---|---|---|
| ~10 ITM | **+74%** | 90% | 71% | 38% | −97% | −11% |
| ATM | **+130%** | 78% | 72% | 57% | −99% | −11% |
| ~10 OTM | −33% | 40% | 38% | 35% | −98% | −11% |

ATM pays more per right call but with a wider spread of outcomes; the ~10 OTM
single is *underwater at the close on most right-direction days* — it wins
only in the ≥15-point bin (100% there, +370% median for the put). "Right" for
an OTM single means right by 15 points, which is 23% of final hours.

## 4. The cut — what "not tolerating drawdown" costs in the final hour

Steve's 08-26 yardstick was a 0.30 cut on a 10.10 single. Measured on the
right-direction days only (the ones that pay):

| single | first +25% printed | heat before it (median / p75 / worst) | 0.30 cut fires first | 10% cut fires first | 20% cut fires first | minutes to first +25% (median, p25–p75) |
|---|---|---|---|---|---|---|
| ~10 ITM | 98% of right days | −14% / −4% / −86% | **82%** | 57% | 42% | 10 (2–26) |
| ATM | 98% | −13% / −2% / −94% | 67% | 57% | 42% | 3 (0–15) |
| ~10 OTM | 93% | −12% / −3% / −92% | 46% | 56% | 40% | 2 (0–9) |

On a ~12-point ITM single the winner typically draws down 14% — about 1.7 pts
of premium, two to three ES points against — before it pays. A 0.30 stop sits
inside that, and on the right-direction days it fires before the first +25%
print eight times in ten. The wrong-side rows in §3 show the other half: held
to the close, the wrong single is a total loss; cut at −10% it is an −11% loss.
Both halves of the yardstick are real; the measurement says they are not
available at the same stop distance. That is the number, not a
recommendation about where the stop goes.

## 5. Stability — 2025 half vs 2026 half (ITM single)

| | days | right-days | corr ES → close | right, close (median) | right ≥ +25% | wrong, held |
|---|---|---|---|---|---|---|
| 2025 (05-27 → 12-31) | 146 | 91 | +0.89 | +72% | 91% | −96% |
| 2026 (01-02 → 07-30) | 117 | 84 | +0.86 | +80% | 88% | −97% |

Same picture on both halves. This is an instrument property, not a market
regime.

## What it settles for the program

- **The scoreboard is the ITM single.** It converts an ES call into premium at
  +0.91, so Stages 2–3 can be run and read in ES points and translated through
  the curve in §2 — the OPRA column confirms the translation rather than
  replacing it. That also means August 2026 and every forward day can be
  scored without an OPRA pull.
- **The direction call that matters is ≥ 5 ES points by the close**, which
  two-thirds of final hours provide. The 10-point flush is the big-win bin,
  not the threshold.
- **Heat is the second axis, not an afterthought.** A lens that calls direction
  but not the 2–3-point shake before the move leaves the trade to be stopped
  out of most of its winners at the yardstick stop. Stage 2 records the
  adverse excursion before the favourable one, per day, so the lenses are
  scored on both.
- **Gap to fill, Steve's call:** OPRA stops 2026-07-30. A pull for
  2026-08-03 → today would put the premium column beside the 40 full-session
  footprint days — the only days where all three lenses exist at once.
  Strader will quote the Databento cost before pulling.
