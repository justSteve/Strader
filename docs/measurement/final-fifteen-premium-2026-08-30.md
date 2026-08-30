# What a ~$0.20 0DTE single actually paid in the final fifteen

OPRA day-files scored 276 · usable 274 · skipped 2 (Counter({'no-parity': 2}))
span 2025-05-27 -> 2026-08-14

Multiples below are the CLEAN WINDOW, 14:45-14:59. The full window to 15:00 is shown
beside them: the closing seconds carry prints that are not single-leg marks (on
2026-08-05 a put three points in the money printed $84.70 in the last six seconds).

**The spread is not in this measurement and cannot be.** Every OPRA record in this
corpus is `schema: trades`; the estate has never held OPRA NBBO. Entries at the ask
and exits at the bid are not computable from this data at any sample size. A far-OTM
SPX option in the last fifteen minutes is wide — a "$0.20" option may be 0.15 bid /
0.30 ask — so every multiple below is a print-to-print result and an UPPER BOUND on
an achievable one. On a lottery-shaped trade that tax is larger than usual.

## 1. Is a $0.20 strike even there at 14:45?

| side | days with an OTM print 14:40-14:45 | of which no print after 14:45 | usable legs |
|---|---|---|---|
| call | 274 of 274 | 0 | 274 |
| put | 274 of 274 | 0 | 274 |

- **call**: the strike nearest $0.20 was a median $0.20 (|error| from $0.20: median $0.05, p90 $0.08). It sat a median **14.9 points** from spot (p25 11.5, p75 21.3).
- **put**: the strike nearest $0.20 was a median $0.20 (|error| from $0.20: median $0.05, p90 $0.08). It sat a median **17.3 points** from spot (p25 13.5, p75 22.9).

That distance is the whole of the arithmetic: near expiry the option is about its
intrinsic value, so reaching a target premium needs the strike distance PLUS the
target — not the target alone.

## 2. What the leg actually reached (item 4 — peak, not close)

| side | legs | close multiple (median / p90 / max) | PEAK multiple (median / p90 / max) | full-window peak max |
|---|---|---|---|---|
| call | 274 | 0.24x / 0.65x / 38.73x | 1.67x / 5.00x / 49.33x | 49.33x |
| put | 274 | 0.20x / 0.45x / 15.95x | 1.47x / 4.00x / 47.00x | 385.00x |

Pooled, 548 legs. How often the peak reached each multiple of the entry:

| multiple | legs reaching it | rate | what that is in money on a 5-lot ($100 in) |
|---|---|---|---|
| >= 2x | 197 | 35.9% | $200 out |
| >= 3x | 97 | 17.7% | $300 out |
| >= 5x | 52 | 9.5% | $500 out |
| >= 10x | 24 | 4.4% | $1,000 out |
| >= 20x | 10 | 1.8% | $2,000 out |
| >= 50x | 0 | 0.0% | $5,000 out |

Steve's assumption is the **50x** row: $0.20 -> $10.00, $100 -> $5,000.

## 3. What move it actually took

538 legs joined to their day's ES excursion.

| favourable ES excursion in the window | legs | median peak multiple | reached 10x | reached 50x |
|---|---|---|---|---|
| under 5 pts | 245 | 1.33x | 0 (0%) | 0 (0%) |
| 5-10 pts | 171 | 2.00x | 1 (1%) | 0 (0%) |
| 10-15 pts | 63 | 2.27x | 7 (11%) | 0 (0%) |
| 15-20 pts | 42 | 4.83x | 7 (17%) | 0 (0%) |
| 20+ pts | 17 | 12.00x | 9 (53%) | 0 (0%) |

**No leg in the corpus reached 50x.**
The 24 legs that reached 10x needed median **16.9 points** (min 9.5).

## 4. Steve's case, isolated: the days that moved ~10 points the leg's way

49 legs whose day travelled 9-11 points in the leg's favour.
- peak multiple: median **2.08x**, p90 5.00x, max 12.50x
- close multiple: median 0.25x
- entry premium median $0.20, peak premium median $0.35
- reached 50x on **0 of 49**

## 5. When the peak printed (the take-profit number)

Median peak at **1.08 minutes** after 14:45 (p25 0.05, p75 5.02). In the last three minutes of the clean window on 17 of 548 legs (3%).
On the 97 legs that at least tripled, the peak printed at a median **7.12 minutes** after 14:45.

Liquidity caveat: the longest silence between prints on the chosen strike ran a median 22s, p90 64s, max 219s. A gap is a stretch where this measurement cannot see the mark and a live order might not fill.
