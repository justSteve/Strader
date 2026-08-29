# Final-Hour Base Rates — what the last hour pays

**Bead:** st-g0jo (*Final-Hour Acuity*) · **Measured:** 2026-08-28 evening ·
**Data:** 288 ES tape days (2025-05-27 → 2026-08-28), 286 usable ·
**Script:** `scripts/measurement/final_hour_base.py` · **Rows:**
`data/measurement/final-hour-base-2026-08-28.jsonl`

All numbers are ES points, RTH, Central time. "14:00" is the last print at or
before 14:00 CT; "close" is the last print before 15:00 CT.

## The prize (valid on all 286 days)

| | 14:00 → close | 14:30 → close |
|---|---|---|
| median net move (absolute) | **7.50** | 6.00 |
| net move ≥ 5 | 65% | 57% |
| net move ≥ 10 | **38%** | 29% |
| net move ≥ 15 | 23% | — |
| net move ≥ 20 | 13% | — |
| max excursion from the 14:00 print ≥ 10 (either side) | **69%** | — |
| down-excursion ≥ 10 / up-excursion ≥ 10 | 40% / 36% | — |
| close inside the 13:00–14:00 box (median box 15 pts) | **49%** | — |
| close above the 14:00 print | 53% | — |

Read: seven final hours in ten travel 10+ points from the 14:00 print at some
point; four in ten *finish* 10+ away. Direction is a coin flip on the base
rate. Half the time the close never leaves the box price was already in at
14:00. So the whole edge is direction and timing — exactly the "delta call"
Steve named.

## Coverage caveat — the one that shapes the plan

247 of the 288 days hold only the **13:00–15:00 CT window** (the 2025
backfill pulled the late-day window, and the OPRA pull matches it). Only the
40 live-collection days from 2026-07-03 onward hold the full session. So any
feature that looks back before 13:00 — position in the day's range, cum
delta, volume profile / value area, "is volume drying vs. late morning" — is
measurable on ~40 days, not 286. The cross-tabs on those features were run
and are **not reported**: n is too small to say anything, and the partial
days silently answer a different question.

What *is* measurable on every day at 14:00 with no lookahead: the 13:00–14:00
box (range, delta, delta-vs-price absorption), the last-30-minute drift, and
the distance from price to the day's Mancini levels.

## Today's row (2026-08-28), for calibration

14:00 print 7716.00 · box 7712.25–7727.25 (15 pts, +995 delta on −8.25 of
price — buying absorbed) · close **7723.00** (+7.00) · up-excursion 12.25,
down-excursion 2.25 · close inside the box. The 14:15 read said pinned close
in 7712–7730; it closed 7723.
