# Cumulative delta at session scale — what it is and is not worth

**Measured 2026-08-05. 21 full corpus days (2026-07-07 .. 2026-08-04), ES front
month, aggressor-tagged trades from GLBX.MDP3.**

Written because on 2026-08-04 Strader told Steve, twice, that the day's 129-point
rally was "bought by nobody" on the strength of a negative cumulative delta. That
claim did not survive being checked, and the way it failed is worth keeping.

## The aggressor convention is correct — verified, not assumed

Before anything else, the obvious suspect was a sign inversion. It is not.

`market/entities/trade.py` documents Databento's `side` as `'A'` = sell aggressor
(hit the bid), `'B'` = buy aggressor (lifted the ask), and `market/orderflow/bars.py`
implements exactly that. Tested against our own MBP-1 top-of-book by matching each
trade to the last quote strictly before it:

| window (UTC) | trades | `'A'` printed | `'B'` printed |
|---|---|---|---|
| 2026-08-04 14:00–14:10 | 16,362 | at/below bid **100.0%** | at/above ask **100.0%** |
| 2026-08-04 19:30–19:40 | 7,597 | at/below bid **100.0%** | at/above ask **100.0%** |

Zero ambiguous prints. The convention, the docstring and the implementation agree.
**Delta is not inverted.** Any future suspicion on this point should re-run the
book test rather than re-reason about it.

## The baseline

`delta%` is net aggressor imbalance as a fraction of that period's volume — the
normalisation the 2026-08-04 reading lacked.

| statistic | value |
|---|---|
| days with **positive** session delta | **17 of 21** |
| median session delta% | **+1.11%** |
| mean session delta% | +0.90% |
| median of \|session delta%\| | 1.35% |
| median worst-single-hour \|delta%\| | 2.94% |

**ES carries a persistent positive aggressor tilt.** Roughly +1.1% of session
volume, on four days out of five. That is the reference point against which any
day's delta has to be read, and it is nowhere in the codebase or the charts.

## What that makes of 2026-08-04

| | |
|---|---|
| session delta | −6,948 on 1,385,446 = **−0.50%** |
| rank | **2nd lowest of 21 days** |
| buy-aggressor share | 49.75% |
| most extreme single hour | **+7.51%** — a *buying* hour, near the top of the sample |
| price | **+129.00**, the largest gain in the sample |

So the day was genuinely unusual — but as a *level*, not a direction. The normal
positive tilt was absent. Nearly half of all aggressive volume was still buyers,
the single most lopsided hour of the day was buyers, and the late session ran
**+4,365** from 14:46 to the close. "Bought by nobody" was wrong by every measure
available.

## The load-bearing result: session delta does not predict direction

    corr(session delta%, day's price change) = -0.22   (n=21)

Slightly *inverse*, and small enough to be noise. Counter-examples are not rare —
they are most of the tail:

| day | session delta% | price change |
|---|---|---|
| 2026-07-27 | +1.53% | **−58.50** |
| 2026-07-29 | +0.82% | **−106.00** |
| 2026-08-03 | +0.17% | **+82.25** |
| 2026-08-04 | −0.50% | **+129.00** |

Two heavy-buying days closed sharply lower; the two flattest/negative days closed
sharply higher. **A session-scale delta reading carries no directional edge in our
own data.** Narrating one as conviction — "nobody is buying this rally", "a rally
with nothing underneath it" — is telling a story the data does not support.

Mechanically this should not be surprising. Every trade has a buyer and a seller;
`side` records only which party crossed the spread. Price rises when passive
offers withdraw, which need not involve aggressive buyers at all.

## How to use delta after this

- **Do not** read session or multi-hour cumulative delta as directional conviction,
  and do not quote a raw contract count (`−7,856`) without its denominator. Against
  230,670 contracts that is −3.4%; against the day it is −0.50%.
- **Do** quote delta as a percentage of the period's volume, against the +1.11%
  median, so "unusual" has a referent.
- **Untouched by this study:** delta at *bar and level scale*, which is where
  `SetupRecognizer` actually uses it (flush / stall / flip / confirm) and where
  absorption reads live. Those are different claims on a different time scale and
  this result neither supports nor undermines them. Do not generalise it into
  "delta is useless."

## Reproducing

Aggressor-convention test and the baseline sweep were run ad hoc from
`market.orderflow.replay.read_corpus_day` plus MBP-1 rows. Both are cheap to redo;
the baseline should be re-run as the corpus grows, since 21 days is a single
regime and every one of them sits inside a strong uptrend.
