# Clock Family Traversal — Hour-of-Day Baseline

**Bead:** st-1bv1 · **Measured:** 2026-08-20 · **Archive:** gexbot-hist 1-second
orderflow, 63 days, 2026-05-07 → 2026-08-06 (63/63 loaded) · **Script:**
`scripts/measurement/clock_family_traversal.py` · **Raw:**
`data/measurement/clock_family_traversal.json`

---

## Why this exists

The bundle concept *Channel Family Taxonomy* (st-a3yh) records **CLOCK** as the
strongest single predictor the continuation audit found — day-median AUC **.875**
against the deliverable's **.607** — and simultaneously as `NEVER-TRAVERSED`. The
concept's procedure is binding: a study design opens by traversing the family
list and writing a verdict per family *before* measuring. Orderflow edge-test
rounds 1–4 (st-yirc, st-mvvf, st-gkbo, st-a2cj) did not do that.

**The bundle named the answer and nobody read it.** This document exists so the
traversal is recorded rather than rediscovered a third time.

## The table

Rolling 15-minute windows over minute-sampled closes, stepped one minute,
labelled by the hour the window starts. Excursion is `max − min` inside the
window, **absolute, either direction**. Final two minutes of RTH excluded, as
rounds 2–3 did.

| CT hour | P(≥10pt move) | median excursion | n windows | fix2000 `gex_of` | fix2000 `cvr_of` |
|---|---|---|---|---|---|
| 08 (from 08:30) | **81%** | 15.30 | 1,806 | 1 | 1 |
| 09 | 66% | 12.13 | 3,773 | 2 | 2 |
| 10 | 45% | 9.38 | 3,780 | 2 | 3 |
| 11 | 33% | 7.67 | 3,780 | 7 | 1 |
| 12 | 26% | 6.92 | 3,780 | 9 | 3 |
| 13 | **25%** | 6.51 | 3,780 | 32 | 6 |
| 14 | 27% | 6.87 | 2,772 | **2,211** | **872** |

**97.7% of giant flow prints (2,211 / 2,264) land in the 14:00 hour — where
displacement sits at its daily floor.** Notional moves; price does not. That is
expiry mechanics — 0DTE settlement, closing-auction hedging, vanna/charm unwind
— and absolute excursion either direction is *opportunity, not directional edge*.

## What this retires

Round 4 scored candidates against a **pooled baseline of "≥10pt move in ~40% of
15-minute windows."** That flat number averages across an 81%-to-25% gradient.

> **Every orderflow candidate scored against the pooled ~40% was scored against
> the wrong comparator, and hour-of-day outperforms every signal four rounds
> produced.**

The pooled figure is retired as a comparator. Future candidates score against
**their own hour**.

## Reproduction is partial, and that is the finding

The 2026-08-09 result recorded its table but **not the code that produced it**.
Three candidate window measures were tried against the recorded numbers:

| measure | P(≥10pt) by CT hour, 08→14 |
|---|---|
| raw 1 Hz max−min | 94 83 62 47 38 36 39 |
| \|last − first\| (net, not excursion) | 45 31 21 18 13 15 15 |
| **minute-sampled closes, max−min** | **81 66 45 33 26 25 27** |
| *the recorded finding* | *77 62 42 32 26 25 27* |

Minute-sampled closes is the measure — **exact at hours 12, 13 and 14**, within
four points everywhere else.

**Not recovered:** the window-inclusion rule. This script keeps ~6% more windows
than the original (3,780/hour against ~3,545). Per-minute coverage filters were
swept (≥30, ≥45, ≥55 samples) and none closes the gap — they drop *n* far faster
than they move *P*. The flow-print counts are likewise close in ratio but not in
level: the original totals 4,808 prints against this script's 2,264 (`gex_of`) /
888 (`cvr_of`), while the hour-14 concentration reproduces at 97.7% against 98.6%.

The residual is a window-count and print-definition difference. **It changes no
conclusion, and it was not tuned away** — matching a target by fitting an
unrecorded filter manufactures agreement rather than reproducing a result.

That gap is the lesson the traversal procedure exists to prevent: *a finding
without its script is not reproducible, only re-derivable.* Hence the script is
committed alongside this table.

## Read-through to st-v5a8

The proposed **10:00–13:00 no-trade window** gains evidence here: P(≥10pt) falls
**45 → 33 → 26** across that span, the three lowest morning hours. But excursion
is not tradeability — **the directional and cost sides are still owed**, and this
measurement says nothing about either.

## Reproduce

```bash
.venv/bin/python scripts/measurement/clock_family_traversal.py --report
```

## Verdict for the taxonomy

**Clock family: `NEVER-TRAVERSED` → `MEASURED` (2026-08-20, st-1bv1).**
