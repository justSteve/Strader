# $TICK percentile seed — 31 sessions (2026-06-05 → 2026-07-21) [st-3fr]

First calibration of the MI gauge's climax thresholds, from Schwab minute
candles backfilled into the `schwab_internals` corpus stream
(`scripts/corpus_pull_internals.py`, computed by
`scripts/measurement/internals_calibrate.py`). Seeds live in
`market/signals/internals_config.py`.

## Per-minute wick percentiles by time bucket (CT)

| Bucket | Side | p50 | p75 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|
| open-drive 8:30–9:15 | high | 165 | 329 | 513 | **591** | **727** |
| | low | −10 | −190 | −325 | **−403** | **−554** |
| morning 9:15–11:00 | high | 73 | 221 | 363 | **442** | **616** |
| | low | −119 | −286 | −434 | **−530** | **−706** |
| midday 11:00–13:00 | high | 45 | 200 | 348 | **421** | **610** |
| | low | −114 | −299 | −466 | **−567** | **−771** |
| afternoon 13:00–15:00 | high | 78 | 247 | 406 | **510** | **687** |
| | low | −156 | −322 | −479 | **−594** | **−892** |

Bold = the CLIMAX (p95) and EXTREME (p99) seeds.

## Session extremes (daily max/min TICK, 31 sessions)

- Daily max: median +683, p90 +923, best +1095
- Daily min: median −768, p90 −1059, worst −1362

## What the numbers say

1. **The folklore ±1000 is a session-extreme marker, not a trade signal.**
   Only ~1 session in 10 prints +1000 at all. Waiting for ±1000 to exit means
   the signal almost never fires. The tape's real climax line sits at roughly
   ±450–600 depending on bucket and side.
2. **Buckets are not optional.** The open drive is positively skewed (opening
   bid programs — high p50 +165 vs low p50 −10). A +500 in the open drive is
   p90 noise; a +500 at 2pm is a climax. Same number, different meaning.
3. **Negative tails are fatter after the open, deepest in the afternoon**
   (p99 −892) — flush climaxes into the close are the strongest single
   reading this instrument produces, which is exactly the butterfly window.
4. **Caveats:** 31 sessions from one regime (July range-trade, VIX teens).
   These seeds will drift with regime; recalibration is weekly, riding the
   corpus snapshot. A vol-regime shift (VIX 20+) invalidates them until
   re-run.
