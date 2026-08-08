# Orderflow edge tests, round 3 — Freddy-faithful — 2026-08-08 [st-gkbo]

63 hist days at 1s. Wall = nearest of 0DTE zero_mcall/zero_mput at event time. Aligned delta = -sign(30-min trend) x forward move (positive = reversal happened). Control uses the same alignment rule.

## 1. Level-conditioned two-signal

Events within 30 min of the close have no +30m outcome — n15/n30 columns give the actually-measurable counts; judge each cell by its own n, not the event count.

| definition | band | events | n15 | n30/days | al +15m med | %pos | al +30m med | %pos |
|---|---|---|---|---|---|---|---|---|
| p95x6 | all | 236 | 177 | 165/52d | 0.59 | 55% | 1.58 | 59% |
| p95x6 | wall <= 3 | 78 | 38 | 36/27d | 1.25 | 58% | 3.03 | 75% |
| p95x6 | wall <= 5 | 105 | 56 | 52/33d | 1.67 | 61% | 2.41 | 71% |
| p95x6 | wall <= 10 | 153 | 95 | 83/43d | 1.41 | 61% | 2.31 | 64% |
| p95x6 | wall > 10 | 83 | 82 | 82/41d | -0.12 | 49% | 1.41 | 54% |
| fix2000 | all | 137 | 46 | 23/15d | 1.03 | 63% | 1.13 | 65% |
| fix2000 | wall <= 3 | 88 | 21 | 9/6d | 1.92 | 76% | 1.13 | 89% |
| fix2000 | wall <= 5 | 107 | 29 | 13/8d | 1.1 | 69% | 1.21 | 85% |
| fix2000 | wall <= 10 | 131 | 41 | 18/13d | 1.1 | 63% | 1.17 | 72% |
| fix2000 | wall > 10 | 6 | 5 | 5/5d | 0.59 | 60% | -1.08 | 40% |
| — | **random control** | 378 | 378 | 378/63d | -0.78 | 43% | -1.18 | 46% |

## 2. Post-entry momentum rule (fuel = convexity DOWN-spike within 10 min of entry)

| definition | group | n | al +30m med | %pos |
|---|---|---|---|---|
| p95x6 | fuel present | 65 | 1.13 | 52% |
| p95x6 | no fuel | 100 | 1.75 | 63% |
| fix2000 | fuel present | 12 | 3.93 | 75% |
| fix2000 | no fuel | 11 | 0.79 | 55% |

Raw: `data/derived/acuity-sweep/edge-tests-r3-raw.json`. Measurement only [st-gkbo].

## Verdicts

1. **Level-first conditioning: SURVIVES CONTROL, monotone in proximity**
   (on the measurable p95x6 sample). Aligned +30m: wall<=3 +3.03 / 75%
   pos (n=36, 27 days) -> wall<=5 +2.41 / 71% -> wall<=10 +2.31 / 64%
   -> wall>10 +1.41 / 54% -> control -1.18 / 46%. Freddy's "level
   first, flow as the confirm" discipline concentrates the effect
   exactly as taught; far-from-wall events decay toward the control.
   fix2000 bands are unusable at +30m (n<=9) — see structural note.
2. **Post-entry momentum rule: NOT SUPPORTED as operationalized**
   (and underpowered). p95x6 runs opposite to the claim (fuel 52% vs
   no-fuel 63%); fix2000 agrees with it but at n=12 vs 11. The
   operationalization also drops Freddy's "in your new direction"
   qualifier (convexity spikes carry no direction; a directional
   variant would need the gex pane or price motion at spike time).
   Unresolved — revisit with forward data and a directional definition.
3. **Structural finding: giant absolute prints are a late-session
   phenomenon.** 83% of fix2000 events (prints >= $2000MM) occur within
   30 min of the close — no +30m horizon exists for them. Judging
   late-day two-signals needs an into-close outcome metric, not a fixed
   +30m window. This is also where the doctrine's last-10-minutes
   window and the late-day fly lane live — the join point for the
   trade-history study.
