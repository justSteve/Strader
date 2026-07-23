"""Market-internals gauge seed constants — the single source. [st-3fr]

Same contract as orderflow_config.py: every threshold the MI gauge uses lives
here as a named constant with provenance. No inline magic numbers.

[calibrated] 2026-07-22 from 31 sessions of $TICK minute candles
(2026-06-05 .. 2026-07-21, scripts/measurement/internals_calibrate.py over the
schwab_internals corpus stream). Key findings baked into the shape of this
table:
  - The folklore +/-1000 threshold is a SESSION-extreme marker, not a
    per-minute signal: only ~10% of sessions print +1000 at all (daily-max
    p90 = 923); -1000 prints slightly more often (daily-min p90 = -1059).
  - Extremes are bucket-dependent: the open drive is positively skewed
    (opening bid programs; high p50 +165 vs low p50 -10) and a +500 print
    means far less there than at 2pm. Afternoon negative tails run deepest.
  - Negative tails are fatter than positive in every bucket after the open.

CLIMAX = bucket p95 of the per-minute wick distribution on that side;
EXTREME = bucket p99. The gauge treats a wick beyond CLIMAX as a climax
print (sell-into-it exit signal when holding with the flush) and beyond
EXTREME as a capitulation-grade print.
"""
from __future__ import annotations

from datetime import time as _time

# Time buckets, US/Central — shared session vocabulary (drills, stage plan).
TICK_BUCKETS = (
    ("open-drive", _time(8, 30), _time(9, 15)),
    ("morning", _time(9, 15), _time(11, 0)),
    ("midday", _time(11, 0), _time(13, 0)),
    ("afternoon", _time(13, 0), _time(15, 0)),
)

# bucket -> (positive CLIMAX, positive EXTREME, negative CLIMAX, negative EXTREME)
TICK_THRESHOLDS: dict[str, tuple[int, int, int, int]] = {
    "open-drive": (591, 727, -403, -554),
    "morning": (442, 616, -530, -706),
    "midday": (421, 610, -567, -771),
    "afternoon": (510, 687, -594, -892),
}

# Session-extreme context (31-session distribution of daily max/min TICK):
# median daily max +683 / p90 +923 / best +1095;
# median daily min -768 / p90 -1059 / worst -1362.
TICK_SESSION_MAX_MEDIAN = 683
TICK_SESSION_MIN_MEDIAN = -768

# Cumulative TICK, time-normalized (sum of minute closes since 08:30 divided
# by minutes elapsed). [calibrated] 2026-07-23, same 31 sessions: intraday
# max |cum| p50=25.7k p90=47k; EOD |cum| p50=24.9k p90=46.8k. Per-minute pace:
# ~64/min median session one-sidedness, ~120/min at p90. The cum component
# saturates at p90 pace — a session running that one-sided IS the spine.
TICK_CUM_PER_MIN_SCALE = 120
TICK_CUM_PER_MIN_MEDIAN = 64

# Component weights by bucket [seeded, not calibrated]: instant extremes are
# cheap in the open drive (positively-skewed program prints), so the day-spine
# carries more weight there; after 09:15 the instant wick leads.
GAUGE_WEIGHTS: dict[str, dict[str, float]] = {
    "open-drive": {"instant": 0.4, "cum": 0.6},
    "morning": {"instant": 0.6, "cum": 0.4},
    "midday": {"instant": 0.6, "cum": 0.4},
    "afternoon": {"instant": 0.6, "cum": 0.4},
}

# Score bands (|score|): >= CLIMAX_BAND = climax zone (exit-into-it when
# holding with the flush; no counter-entries); >= LEAN_BAND = directional
# lean; below = neutral tape.
GAUGE_CLIMAX_BAND = 75
GAUGE_LEAN_BAND = 40

# Recalibration cadence: weekly, alongside the corpus_pull_internals.py
# snapshot (Schwab minute history is a rolling ~47-day window).
