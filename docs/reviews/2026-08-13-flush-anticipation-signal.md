# Anticipating the Late-Day Flush — a Trade-Tape Candidate

Bead: st-z96i · built 2026-08-13 from the ES trade tape (Databento) for
2026-08-11 and 2026-08-12

**Scope Steve set:** find footprint data that *anticipates* the 10-point flush in
the last 30 minutes. Recovery explicitly out of scope. The instrument is a 0DTE
long put single, not a fly — so the read has to fire *before* the break.

> **Superseded framing (Steve, 2026-08-13).** This page originally said the read
> also had to "survive being wrong for a minute." Steve's answer — *or just take
> profit at an arbitrary point* — is correct and is measured in **Fixed-target
> exit** below. Surviving the drawdown is only required if you are reaching for
> the whole flush. At a 2-point target the drawdown has not happened yet.

> **Read this first.** Three fires across two days. The thresholds *and* the time
> filter were chosen after seeing which fires worked. That is fitting a curve to
> two points, and it is not tradeable evidence. What follows is a hypothesis
> precise enough to be killed — see the last section.

---

## What both days actually did before the break

Not one tell. A two-part sequence.

**Part 1 — a concentrated sell burst.** One 30-second bucket where sell
aggression is a large share of that bucket's volume *and* the average print size
is above the day's median. A real seller shows up and is visible.

**Part 2 — a limp drift back.** The next few buckets carry price back toward the
high on near-zero delta concentration. Nobody bought it back — it floated back
on nothing.

Then it breaks. The burst is the test; the limp recovery is the confirmation
that the test found no defence. **Price returning to the high on no volume is
the setup, not a rejection of it** — that is the counter-intuitive half.

| | 8/11 | 8/12 |
|---|---|---|
| burst bucket | 14:42:30 | 14:40:00 |
| volume | 1,544 | 1,441 |
| delta | **−724** | **−515** |
| \|delta\|/vol | **46.9%** | **35.7%** |
| avg print (day median) | 5.22 (3.52) | 4.69 (3.48) |
| next 6 buckets under 15% concentration | 4 | 4 |

---

## Scored as a long put would actually trade it

Signal: 30s bucket, delta < 0, |delta|/vol ≥ 28%, avg print > day median,
confirmed by ≥4 of the next 6 buckets under 15% concentration, firing only from
14:25 CT. Scored 20 minutes forward in ES points from the signal bucket's close.

| day | fired | ES | vol | delta | d% | **MAE (heat)** | **MFE (down)** | net @ +20m | R:R |
|---|---|---|---|---|---|---|---|---|---|
| 8/11 | 14:39:00 | 7755.50 | 1,740 | −508 | 29.2% | **+1.00** | **−12.00** | −9.00 | 12.0× |
| 8/11 | 14:42:30 | 7753.50 | 1,544 | −724 | 46.9% | **+1.00** | **−10.25** | −3.75 | 10.3× |
| 8/12 | 14:40:00 | 7772.25 | 1,441 | −515 | 35.7% | **+2.50** | **−7.75** | −2.75 | 3.1× |

**Every fire reached at least −7.75 ES points within 20 minutes. Worst heat
before it paid: +2.50.**

Stop sensitivity — the number that decides whether this is tradeable by someone
who cuts fast:

| stop | fires surviving to work |
|---|---|
| 1.0 ES pts | 2 / 3 |
| 2.0 ES pts | 2 / 3 |
| **2.5 ES pts** | **3 / 3** |
| 3.0 ES pts | 3 / 3 |

A 2-point stop — which is a natural instinct — kills the 8/12 trade before it
pays. That single fact is the most useful thing on this page, because it is the
one that would have cost real money.

---

## Fixed-target exit — the drawdown is a function of how greedy you are

MAE over 20 minutes is the wrong number if you are out in three. The number that
matters is **heat before target**: the worst adverse move between entry and the
moment the target prints. Measured at 5-second resolution off the tick tape:

| target | fires hit | median time to hit | **worst heat before it printed** |
|---|---|---|---|
| 1.5 pts | **3 / 3** | **2m 04s** | **+1.00** |
| 2.0 pts | **3 / 3** | **2m 45s** | **+1.00** |
| 3.0 pts | 3 / 3 | 5m 05s | +2.50 |
| 4.0 pts | 3 / 3 | 5m 36s | +2.50 |
| 5.0 pts | 3 / 3 | 5m 47s | +2.50 |
| 7.0 pts | 3 / 3 | 9m 17s | +2.50 |

**The break is between 2 and 3 points.** The +2.50 heat that drove the whole stop
discussion is entirely an 8/12 phenomenon, and on 8/12 it happens *after* the
2-point target has already filled — that trade was out in 2m 45s having never
been more than a point offside. Reaching for the third point is what buys the
drawdown:

| 8/12, fired 14:40:00 | time to hit | heat before target |
|---|---|---|
| 2.0 pts | **2m 45s** | **+1.00** |
| 3.0 pts | 10m 37s | +2.50 |

Same signal, same day. One point of extra greed costs eight minutes of holding
and 1.5 points of additional drawdown.

### What that is worth as a put, using real quotes

The 14:45 chain snapshot exists on both days, so this does not have to be
assumed. On 8/12 at 14:45:03, SPX 7751.26:

| | strike | bid / ask | mark | delta | spread |
|---|---|---|---|---|---|
| 8/12 | 7750P | 1.45 / 1.55 | 1.50 | −0.410 | **0.10** |
| 8/11 | 7730P | 3.60 / 3.80 | 3.70 | −0.498 | 0.20 |

A 2-point SPX move on a 0.41-delta put is ~0.82 of option value before gamma,
which rises as price falls. Call it 1.50 → roughly 2.3, so **~+0.70/contract
(~$70)** on a three-minute hold, before slippage.

**And note the friction difference.** That put quotes 0.10 wide on a 1.50 mark —
about 3% of premium. The 8/11 butterfly at the same hour quoted **1.60 wide on a
1.90 mark**, 42% below mid to exit. At the close, singles win the friction fight
against flies by an order of magnitude. That is a structural argument for the
instrument, independent of whether this particular signal survives testing.

---

## Rarity, and where the duds live

Across 12:30–14:59, the burst filter fires **6 times in 300 buckets (2.0%)** on
each day. Selective. But the *outcomes* split hard by time of day:

| fires | 8/11 | 8/12 |
|---|---|---|
| before 14:25 | 2, both followed by ≥5.25 pts down | 5, followed by −0.50 to −3.25 — **all duds** |
| after 14:25 | 4, followed by −6.50 to −10.75 | 1, followed by −7.75 |

The early-session fires on 8/12 are exactly the false positives you would expect
from a pattern this simple. The 14:25 filter removes them — but the filter was
chosen *because* it removed them, so it earns nothing until it holds out of
sample.

---

## What would kill it or confirm it

The signal uses **only the trade tape** — delta, volume, print size. No book, no
GEX, no options. That matters, because it means the whole corpus is eligible:

- **275 days of ES trade tape on disk, 2025-05-27 → 2026-08-12.**
- MBP-1 exists on only 23 days, but the signal does not use it.

So this is testable on ~273 unseen days without pulling a single new byte. The
test to run:

1. Sweep the burst threshold (20–40%), the confirmation window, and the fire-time
   cutoff across all 275 days — not to find the best combination, but to see
   whether *any* plateau exists or whether the 8/11 result is a spike in noise.
2. Report MAE and MFE distributions, not hit rate. Hit rate hides the heat.
3. Score against a real fill assumption — one bucket of lag, not the signal
   bucket's close, which is what this page optimistically assumed.
4. Condition on day type. 8/11 and 8/12 both had a late flush; the question that
   matters is how often it fires on days that *don't* flush.

Point 4 is the one that decides it. Two flush days cannot tell you the false
positive rate on non-flush days, and that rate is the entire economics of the
trade.
