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

# ── volume profile / LVN context (spec §2 Tier B; st-7d6) ──────────────────
# Window convention: the v1 profile window is the PRIOR RTH session — callers
# feed yesterday's trades and consume the levels today. Recomputed on
# completed-session cadence, never per-tick (research doc Q1.6).
PROFILE_WINDOW = "prior-rth-session"
PROFILE_BUCKET_TICKS = 4        # 1.0-pt buckets — 0.25 is too noisy for nodes
LVN_MAX_FRACTION = 0.30         # local minimum below 30% of POC volume = LVN
HVN_MIN_FRACTION = 0.70         # local maximum above 70% of POC volume = HVN

# ── four-beat recognizer (spec §3; st-2kf) ─────────────────────────────────
# Delta thresholds seeded from the 7/2 RTH |bar-delta| distribution
# (p50=111 p75=210 p90=312): flush ≈ p90, quiet ≈ p50, confirm ≈ p75.
ENGAGE_PENETRATION_TICKS = 2    # bar must trade ≥ this beyond the level (beat 1)
FLUSH_DELTA_MIN = 300           # |bar Δ| for a VIOLENT break -> failed_breakdown
QUIET_DELTA_MAX = 110           # |bar Δ| below this = quiet loss -> level_reclaim
STALL_EXTENSION_TICKS = 1       # beat 2: extreme extends ≤ this while aggression continues
FLIP_DELTA_MIN = 150            # beat 3: opposite-direction bar Δ
CONFIRM_DELTA_MIN = 200         # beat 4 fallback when no opposite ImbalanceStack printed
ENGAGEMENT_WINDOW_BARS = 12     # beats must complete within this many bars of beat 1
INVALIDATE_TICKS = 16           # 4.0 pts beyond the level without reclaim kills the setup

# ── consumer wiring (spec §6) ───────────────────────────────────────────────
CONFLUENCE_TOLERANCE_PTS = 2.0  # Mancini level ∩ anchor proximity

# Calibration note (st-su4, 2026-07-05, 7/2 full RTH): at VOLUME_BAR_N=2000
# the FLOOR=100 diagonal test flags ~333 levels/session (≈1 per 2 bars — sane
# recognizer evidence), but 3-consecutive STACKS are structurally rare at this
# bar size (0-6/session across floors 30-100): cells average ~130 contracts.
# Do NOT lower the floor to manufacture stacks; if the recognizer needs
# stacked confirmation it should aggregate coarser (st-2kf design decision).
