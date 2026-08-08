# Orderflow edge tests, round 4 — scalp metrics — 2026-08-08 [st-a2cj]

63 hist days at 1s. Target: single-leg SPX scalp-proxy, 15-min hold. MFE/MAE in the fade direction; control scored by the identical rule. Events in the final 15 min excluded.

## 1. Two-signal under scalp metrics (15-min hold)

| sample | n | MFE med | MAE med | P(MFE>=5) | P(MFE>=10) | P(stopped first: MAE>=5 before MFE>=5) |
|---|---|---|---|---|---|---|
| all events | 177 | 4.83 | 3.81 | 49% | 20% | 36% |
| wall <= 5 | 56 | 4.8 | 3.2 | 46% | 12% | 27% |
| **random control** | 378 | 3.78 | 4.72 | 40% | 18% | 40% |

## 2. When do fast moves happen at all? (netcvx regime, 75s sampling, either direction)

| regime | samples | P(>=5 pt move in 15 min) | P(>=10 pt) |
|---|---|---|---|
| DUMP | 5050 | 79% | 37% |
| RAMP | 5730 | 76% | 36% |
| NEUTRAL | 8041 | 78% | 43% |

Raw: `data/derived/acuity-sweep/edge-tests-r4-raw.json`. Spot metrics only; options layer is a future refinement. Measurement only [st-a2cj].

## Verdicts (scalp-proxy lens)

1. **Two-signal: NOT a scalp edge.** +1 pt of median MFE and +9 pts of
   P(MFE>=5) over control, no improvement in the 10-pt tail (20% vs
   18%). Worse: the near-wall cut — the star of round 3 — CUTS the
   10-pt tail to 12%. Coherent picture: near-wall two-signals mark
   *pinning* (price stops and sits), which is why they win on hit-rate
   and drift metrics and lose on follow-through. A containment signal,
   not a launch signal. Retired for the singleton lane.
2. **Netcvx regime does not time fast moves.** P(>=10 pt move in 15
   min) is 36-43% in ALL states, highest in NEUTRAL. Regime state as
   currently defined carries no scalp-timing information.
3. **Structural baseline that reframes the search:** on these 63 days a
   >=5-pt move occurs in ~78% of 15-min windows and a >=10-pt move in
   ~40%. Movement is not scarce — DIRECTION is the entire problem. The
   next candidates must be scored on directional tail shift:
   P(10 pts WITH the signal's direction) vs against. Doctrine's
   momentum side (convexity down-spike moments, dump onsets as events
   rather than states) is the untested lane that maps to this framing.
