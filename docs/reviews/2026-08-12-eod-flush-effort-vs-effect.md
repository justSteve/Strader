# EOD Flush X-Ray — Effort vs Effect, 8/12 vs 8/11

Bead: st-z96i · built 2026-08-13 from the corpus (Databento ES trades + MBP-1
top-of-book, GEXBot 1s SPX)

**Effect** is SPX cash points. **Effort** is measured two ways on the ES tape,
because they answer different questions: *volume* (how much trading it took) and
*|delta|* (how one-sided it was). Aggressor convention pinned in
`market/orderflow/anchored_profile.py` [st-6gs3] — `B` = lifted the ask,
`A` = hit the bid.

---

## The two closes are geometric twins

| | 8/11 | 8/12 |
|---|---|---|
| SPX high (14:45–14:59) | 7730.22 | 7752.69 |
| SPX low | 7720.73 | 7742.92 |
| **peak → trough** | **−9.49** | **−9.77** |
| recovery off the low | +7.06 | +6.49 |
| net over the window | −2.43 | −1.52 |

Both dropped ~10 points and bought back two-thirds of it before the bell.

## They cost wildly different amounts

| | 8/11 | 8/12 |
|---|---|---|
| ES volume, 14:45–14:59 | 207,758 | **78,862** |
| net delta | −6,614 | **−1,632** |
| delta as share of volume | 3.18% | 2.07% |
| **SPX pts per 10k contracts** | **−0.46** | **−1.24** |

**8/12 travelled the same distance on 38% of the volume and 25% of the
aggression — 2.7× the price per contract.**

### The sharpest single minute is 14:50, on both days

| | volume | delta | \|d\|/vol | SPX pts |
|---|---|---|---|---|
| 8/11 14:50 | 12,690 | −1,730 | 13.6% | **−0.90** |
| 8/12 14:50 | 4,888 | **−280** | 5.7% | **−4.24** |

8/11 spent 1,730 net sellers to lose nine tenths of a point. 8/12 spent 280 to
lose 4.24. That is roughly **29× the price impact per unit of aggression**, one
day to the next, at the same clock minute.

---

## The book says why — and it inverts the obvious story

The intuition is "8/12's book was empty." It wasn't. Median top-of-book size,
14:45–14:59, against each day's own 11:00–11:14 midday baseline:

| | midday bid | EOD bid | ratio |
|---|---|---|---|
| 8/11 | 30 | **54** | **1.80×** |
| 8/12 | 36 | 44 | 1.22× |

**8/12's book was normal. 8/11's was unusually full.** The gap in effort/effect
is 8/11 being a wall, not 8/12 being a vacuum.

Two more things the book shows:

**The flush minute looks identical on both days.** Median bid size collapses to
28–29 at 14:50 on 8/11 *and* 8/12, from 42–51 in the minutes before. Roughly 40%
of the resting bid steps away right at the move. That withdrawal is the flush
signature and it is not what distinguishes the two days.

**The difference is the rebuild into the bell** (mean total top-of-book size):

| | 14:56 | 14:57 | 14:58 | 14:59 |
|---|---|---|---|---|
| 8/11 | 97.6 | 112.5 | 147.7 | **193.0** |
| 8/12 | 68.5 | 76.4 | 99.7 | 157.9 |

8/11 stacked liquidity into the close and made sellers chew through it. 8/12
didn't, so the same net selling went much further.

---

## Where 8/12 stopped, and why it came back

GEXBot through the flush — the long-gamma magnet walked *down* to meet price:

| CT | spot | major long gamma | major short gamma |
|---|---|---|---|
| 14:47 | 7750.10 | 7750.00 | 7735.96 |
| 14:51 | 7747.31 | 7749.24 | 7735.99 |
| 14:54 | 7746.09 | **7745.18** | 7738.76 |
| 14:55 | **7743.42** | 7745.18 | 7738.76 |
| 14:59 | 7748.61 | 7744.47 | 7750.30 |
| 15:00 | 7748.71 | 7743.94 | 7750.30 |

The low of 7742.92 undershot the long-gamma magnet by **2.3 points** and stopped
**4.2 points above** the short-gamma level at ~7738.76 — which was never
touched. Price was still inside the positive-gamma cushion the whole way down,
so the dip got bought mechanically and closed at 7748.71, back at the magnet.

That is the whole reason the flush was a V and not a slide.

---

## The caveat: the metric breaks in the final minute

| | volume | delta | SPX pts | scores as |
|---|---|---|---|---|
| 8/11 14:59 | 99,942 | −3,966 | +1.15 | extreme absorption |
| 8/12 14:59 | 34,939 | −759 | +2.58 | mild absorption |

Neither is absorption. That is the closing auction — MOC imbalance crossing, not
a directional fight, and the effort/effect ratio has no meaning against it.
**Score the window 14:45–14:58 and drop 14:59.**

---

## What to take from it

1. **Identical-looking flushes can have opposite mechanics.** Same 10 points,
   same V, and one cost 2.7× more per contract than the other. The chart cannot
   tell you which you are in; the delta-per-point can.
2. **Cheap travel means absent bids, not heavy selling.** 8/12's −4.24 point
   minute on −280 delta is the tell. When price moves that far on that little
   aggression, there is nothing underneath — and nothing underneath cuts both
   ways, which is why it snapped back just as cheaply.
3. **Read book rebuild, not just book depth.** The withdrawal at the flush
   minute was identical on both days. What differed was whether liquidity came
   back before the bell, and that is what set how far the selling travelled.
4. **This is diagnostic, not a setup.** A 10-point V inside the last 15 minutes
   is not tradeable as a fly — five minutes of life and closing-hour spreads
   eat it. Value here is in calibrating the read, not in a missed entry.
