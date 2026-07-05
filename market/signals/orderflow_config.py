"""Orderflow layer config constants — the single source (design spec §9).

Every threshold the orderflow layer uses lives here as a named constant.
Replay divergence almost always traces to an implicit constant; keeping them
in one module makes every change a reviewable config commit, never a silent
inline edit (docs/superpowers/specs/2026-07-03-orderflow-signal-layer-design.md).

Provenance markers:
  [calibrated]   — measured from corpus data; date and bead noted.
  [literature]   — practitioner-literature seed (research doc Q1); expected to
                   be re-calibrated once enough full-RTH corpus days exist.
"""
from __future__ import annotations

# ── instrument ──────────────────────────────────────────────────────────────
TICK = 0.25  # ES minimum price increment

# ── unit model (spec §4) ────────────────────────────────────────────────────
# [calibrated] st-f05 2026-07-04 on 2026-07-02 full RTH (1.335M contracts):
# median bar ≈ 43s over the session, ≈ 26s during the open hour. Provisional
# until ~5 widened full-RTH days confirm; 7/2 was a holiday-eve session.
VOLUME_BAR_N = 2_000

# Straddle rule (spec §4): the whole crossing trade lands in the bar it
# completes — bars may overshoot N by at most one print's size. Encoded in
# market/orderflow/bars.py; named here so the rule has one citable home.
STRADDLE_RULE = "whole-trade-into-crossing-bar"

# ── CVD (spec §2) ───────────────────────────────────────────────────────────
CVD_RESET_CT = "08:30"          # cash-session open, US/Central
NONE_SIDE_POLICY = "separate"   # aggressor-less prints: own bucket, never in delta

# ── footprint imbalance (spec §2; research doc Q1.3) [literature] ──────────
IMBALANCE_RATIO = 3.0           # diagonal dominance multiple
IMBALANCE_FLOOR = 100           # contracts on the dominant side, ES scale
STACK_MIN = 3                   # consecutive same-direction imbalances = stacked

# ── large-lot / sweep (spec §2) [calibrated st-wnc 2026-07-05 on 7/2 RTH] ───
# Relative-only thresholds were hopelessly chatty on ES (10x median ≈ 10-20
# contracts -> 15,467 "large lots"/day; 3-level runs -> 3,658 "sweeps"/day).
# A 100-contract floor yields ~33 large lots and ~39 sweeps per session —
# rare enough to mean urgency. Both tests are AND-ed with the floor.
LARGE_LOT_K = 10.0              # multiple of rolling median print size
LARGE_LOT_MIN_SIZE = 100        # absolute contract floor (AND with the above)
LARGE_LOT_MEDIAN_WINDOW = 500   # prints in the rolling-median warm-up window
SWEEP_MIN_TICKS = 3             # distinct price levels walked by one aggressor
SWEEP_MIN_SIZE = 100            # total contracts in the run (AND with above)
SWEEP_WINDOW_MS = 250           # event-time window; never wall-clock

# ── divergence pivots (spec §2) [literature seed; calibrate st-wnc] ─────────
PIVOT_FILTER_TICKS = 8          # swing high/low confirmation filter (2.0 pts)

# ── consumer wiring (spec §6) ───────────────────────────────────────────────
CONFLUENCE_TOLERANCE_PTS = 2.0  # Mancini level ∩ anchor proximity
