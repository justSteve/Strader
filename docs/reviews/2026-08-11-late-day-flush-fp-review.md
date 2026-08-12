# 8/11 Late-Day Flush — Footprint Review

Bead: st-z96i · reconstructed 2026-08-12 from the corpus (Databento ES trades,
GEXBot 1s SPX, Schwab chain snapshots)

---

## Before anything else — the ticket isn't what you remembered

You described the position as **10-wide centered at SPX 7740**. The ticket reads:

```
BOT +2 BUTTERFLY SPX 100 (Weeklys) 11 AUG 26  7760/7745/7730 PUT @ 1.70
```

That is **15-wide, body at 7745** — five points higher and half again as wide.
$340 debit, and the debit is the whole risk. It matters because the body
location *is* the thesis, and 7745 turns out to be the thing that decided this
trade.

---

## Where the magnet actually was

GEXBot, 8/11 afternoon, SPX terms:

| time CT | spot | major positive | major negative | major long gamma |
|---|---|---|---|---|
| 12:45 | 7735.78 | 7750 | 7725 | 7734.47 |
| 13:05 | 7733.82 | 7750 | 7725 | **7725.55** |
| 13:30 | 7719.77 | 7750 | 7725 | 7724.99 |
| 14:05 | 7722.84 | 7750 | 7725 | 7725.18 |
| 14:15 | 7725.42 | **7740.08** | 7725 | 7725.00 |
| 14:35 | 7730.55 | 7740 | 7725 | 7725.14 |
| 14:55 | 7726.73 | **7730** | 7725 | 7725.00 |
| 15:00 | 7727.79 | 7730 | 7725 | 7725.00 |

**Major long gamma parked on 7725 from 13:05 to the bell and never moved.**
SPX settled **7728.20**. The magnet called the close within 3.2 points, and the
positive-gamma ceiling walked *down* into it — 7750 → 7740 → 7730 — closing the
lid a step at a time.

Your body sat at 7745, **20 points above the magnet**. The other candidate
destination — the 12:45–13:00 consolidation the market dumped out of, SPX
7734–7736 — was also below it. 7745 was above both.

What the same $340 would have done with the body somewhere else, at the actual
7728.20 settle:

| body | structure | payoff at settle |
|---|---|---|
| 7745 (what you took) | 7760/7745/7730 | **0.00** — expired 1.80 pts below the lower wing |
| 7735 (the dumped-from range) | 7750/7735/7720 | **8.20** |
| 7725 (the GEX magnet) | 7740/7725/7710 | **11.80** |

The read was right — price flushed and came back. The destination was set ten to
twenty points too high, and that alone is the trade.

---

## The tape, 12:45 → close

| CT | what happened | SPX | ES delta |
|---|---|---|---|
| 12:45–13:00 | balance, 2-pt range | 7734–7736 | flat |
| 13:01–13:19 | first leg down, grind | 7735 → 7730 | −1,800 cum |
| 13:20–13:29 | **the flush** | 7730 → **7717.25** | 13:28 −1,584 · 13:29 **−2,760** on 13,908 |
| 13:30–13:53 | reversal, recovery | 7717 → **7727.14** | +7,168 spent buying it back |
| 13:53–14:07 | pullback — your stop | 7727 → 7721.20 | 14:00 −698 |
| 14:09–14:39 | steady grind up | 7721 → **7733.79** | +11,000 cum, the day's high water |
| 14:45–15:00 | EOD flush | 7733 → 7720.73 | 14:50 −1,730 · 14:59 −3,966 on 99,942 |

Capitulation minute is 13:29 — 13,908 contracts, −2,760 delta, and the low. The
very next minute flipped to **+986**. That one-bar polarity flip at the low is
the cleanest single print in the day.

---

## Your question: was the 1:55 pivot readable?

**The turn — yes, clearly. The depth — there was no depth to read.**

The swing high is 13:53 at SPX 7727.14 (ES 7750.25). Footprint at ES 7750 ±1.25:

| CT | buy | sell | delta | ES high |
|---|---|---|---|---|
| 13:49 | 806 | 666 | +140 | 7749.00 |
| 13:52 | 582 | 294 | +288 | 7749.25 |
| **13:53** | **1,560** | **1,094** | **+466** | **7750.25** |
| 13:54 | 1,008 | 776 | +232 | 7749.75 |
| 13:55 | 508 | 442 | +66 | 7749.25 |
| 13:57 | 414 | 208 | +206 | 7748.75 |

Every minute positive delta. Every minute a **lower high**. About 1,400 net
contracts of buy aggression spent at one price over nine minutes, and price
finished below where it started. That is absorption — the ask kept refilling,
and lower each time.

Two things sharpen it:

1. **The recovery had spent its fuel.** Cumulative delta went −7,936 at the
   13:29 low to −768 by 13:55. The buyers used **+7,168** of aggression to lift
   SPX 10 points. The sellers had used −2,760 in a *single minute* to drop it
   4.5. Buyers were paying roughly four times as much per point. Effort/result
   that lopsided is absorption, not initiative.
2. **It stalled 2 points above the magnet.** SPX 7727.14 against major long
   gamma at 7725. It wasn't going anywhere; it was on a leash.

So the exit signal existed and was legible in real time: *positive delta, lower
highs, three minutes running, two points above the magnet.*

**But the depth question has a blunt answer — the pullback was only 5.9 points**
(7727.14 → 7721.20). Nothing in the footprint predicted a deep move because
there wasn't one. What made it *feel* deep is that the body was 20 points away,
so the fly was living entirely on far-tail optionality; small SPX moves swung it
hard in percentage terms. **The fragility was in the strike selection, not in
the move.**

The same signature repeats at the actual top, tighter — footprint at ES 7756
(SPX ~7734), 14:36–14:42: `+372, −336, **+1,060**, −256, −38, +28, −58`. The
14:38 push spent 1,060 and 14:39 immediately printed a lower high on negative
delta. It stalled 6 points short of the 7740 positive-gamma level that had just
walked down to meet it.

---

## The fly price at 2:40 CT

**Method.** The corpus holds five Schwab chain snapshots for 8/11, not a
continuous series, so 14:40 is reconstructed. Schwab's per-strike IVs are
unusable here — the 7760P prints 19–21% against a ~11% ATM, and pricing each leg
at its own quoted IV overstates the fly by +1.01 to +1.73 on a structure worth
under 2.00. So per-leg IV is discarded and a single flat vol is solved to
reproduce the **quoted fly mark** at 14:45, then only spot and clock are moved
back five minutes. Every number below is a short local extrapolation off a real
tradeable price.

**Quoted — the only hard prices in the day:**

| CT | SPX | min left | exit (bid) | mark | entry (ask) | spread | fly delta |
|---|---|---|---|---|---|---|---|
| 07:00 | 7753.11 | 480 | 1.40 | 2.15 | 2.90 | 1.50 | −0.021 |
| 08:30 | 7763.38 | 390 | 1.80 | 2.20 | 2.60 | 0.80 | −0.021 |
| 13:00 | 7734.94 | 120 | 4.80 | 5.25 | 5.70 | 0.90 | +0.275 |
| 14:15 | 7725.49 | 44 | 1.20 | 1.55 | 1.90 | 0.70 | +0.227 |
| 14:45 | 7729.09 | 15 | 1.10 | 1.90 | 2.70 | 1.60 | +0.456 |

**14:40 CT — the top before the EOD flush.** SPX tape: 14:38 high 7733.69 ·
14:39 high **7733.79** (session top) · 14:40 open 7733.35, close 7732.33.

| SPX | mid mark | realistic exit | ×2 @ mid | P/L vs 1.70 (mid) | P/L (realistic) | row |
|---|---|---|---|---|---|---|
| 7731.97 | 3.66 | 2.9–3.1 | $733 | **+$393** | +$240–280 | 14:40 low |
| 7732.33 | 3.87 | 3.1–3.3 | $774 | **+$434** | +$280–320 | 14:40 close |
| 7733.35 | 4.47 | 3.7–3.9 | $894 | **+$554** | +$400–440 | 14:40 open/high |
| 7733.79 | 4.73 | 3.9–4.1 | $947 | **+$607** | +$440–480 | 14:39 high — session top |
| 7729.09 | 2.23 | — | $447 | +$107 | — | the 14:45 quoted spot, as a check |

Mid carries roughly **±0.40**; a 30-minute roll of the same method missed by
−0.35, and this is a 5-minute roll. "Realistic exit" is mid minus the 0.6–0.8
fly spread implied by the quoted leg spreads at 14:15 and 14:45 — **SPX fly
spreads into the close are brutal**, 1.60 wide on a 1.90 mark at 14:45, and that
friction is a real part of the answer.

**So: roughly +$400 to +$480 realistically available at the 2:40 top, against a
$340 debit. Better than doubling.**

**Afternoon curve** (same calibrated vol, spot and clock from the tape; rough by
construction away from 14:45 — the shape is the point, not the cents):

| CT | SPX | mid | P/L (2×, mid) | |
|---|---|---|---|---|
| 13:29 | 7717.72 | 1.27 | −$86 | flush low |
| 13:30 | 7720.55 | 1.70 | −$1 | ≈ your fill |
| 13:45 | 7721.66 | 1.70 | $0 | |
| **13:53** | **7726.09** | **2.56** | **+$172** | the pivot you wanted to exit |
| 13:57 | 7726.01 | 2.49 | +$157 | signal still live |
| 14:00 | 7722.66 | 1.65 | −$10 | |
| 14:07 | 7721.46 | 1.26 | −$88 | stop-out zone |
| 14:15 | 7725.36 | 1.95 | +$50 | |
| 14:30 | 7730.15 | 3.15 | +$289 | |
| **14:39** | **7733.54** | **4.61** | **+$582** | session top |
| 14:45 | 7727.80 | 1.40 | −$59 | EOD flush begins |
| 14:53 | 7721.60 | 0.03 | −$247 | |
| 15:00 | **7728.20** | — | **−$340** | settled 1.80 below the wing |

Your 1.70 fill maps to SPX ≈ 7720–7722, which puts the entry at 13:30–13:35 —
one to six minutes off the 13:29 low. **The entry timing was excellent.**

---

## What to take from it

1. **The entry was the best part of the trade.** You bought within minutes of
   the capitulation low, into the flush, at a real discount. That is the play
   working exactly as intended.
2. **The body was the error, and it was knowable at entry.** GEXBot had major
   long gamma on 7725 from 13:05 onward and it never moved. The dumped-from
   range was 7734–7736. 7745 was above both. Body at 7735 pays 8.20; at 7725,
   11.80; at 7745, zero.
3. **The b/e stop wasn't wrong, the structure made it inevitable.** A body 20
   points out means every 5-point wiggle is a large percentage swing. You got
   stopped by a 5.9-point pullback because the position had no cushion, not
   because you managed it badly.
4. **The absorption signature was readable both times** — 13:53 and 14:38, same
   shape: positive delta into a lower high, at or near a gamma level. That is a
   scale-off trigger worth drilling.
5. **You were never wrong about direction or timing — only about distance.**
   Price flushed and it returned. It returned to 7733.79, not 7745. The magnet
   told you where "back" was, six points before the close-lid stepped down to
   meet it.
