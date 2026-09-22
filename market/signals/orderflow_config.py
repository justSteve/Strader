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
# ── what makes a run ONE ORDER rather than a crowd [2026-08-27] ─────────────
# Steve, seeing a 3-level 129-contract callout: "sweep implies a substantial
# move by a high funded entity just crashing thru the book." The four gates
# above cannot express that, and the measurement says why.
#
# ES print sizes, 1.69M prints over 5 sessions: the MEDIAN PRINT IS 1 CONTRACT,
# 54% of prints are size 1, and prints of 100+ number 34 in five days carrying
# under 1% of volume. So 129 contracts is essentially never one order. Measured
# on the runs themselves:
#
#     run size          prints/run   largest print   duration
#     100-250              13             54          56 ms
#     250+                 14            140           1 ms
#
# A 100-250 run is thirteen prints averaging ten lots leaning the same way for
# 56ms — a crowd of small aggressors, which is a real phenomenon but is not
# what the word means. The 250+ population completes in ONE MILLISECOND with a
# single print carrying half of it: one order filled across several resting
# levels. The practitioner literature agrees — a sweep is large orders hitting
# multiple price levels *simultaneously*, not aggregate pressure summed over a
# burst.
#
# So the discriminator is not a bigger size floor (which still admits thirteen
# small aggressors totalling 400). It is evidence of single-order origin:
# SPAN, because one order's fills are reported in one instant, and
# CONCENTRATION, because one order leaves one dominant print.
#
# Rate at each candidate, same 5 sessions (today's rule yields 42.2/day):
#     span<=50ms                        21.4/day
#     span<=5ms                         15.4/day
#     one print >= 50%                  13.2/day
#     span<=5ms AND one print >= 50%     6.0/day   <- adopted, median 256 lots
#     one print >= 80%                   3.8/day
SWEEP_MAX_SPAN_MS = 5           # first print to last; "simultaneously"
SWEEP_MIN_CONCENTRATION = 0.5   # largest single print / total run size

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
# [calibrated] st-3vu 2026-07-06 against 12 Mancini-labeled textbook days:
# the original seeds (12 bars / 16 ticks = 4 pts) invalidated exactly his best
# setups — textbook flushes run 10-15 pts below the level before reclaiming
# (that depth IS the trap). Loosening to 40 bars / 60 ticks flipped 4 labeled
# misses (2025-10-03, 2025-10-06, 2026-02-13, 2026-04-23) into confirmations
# within 0-3 minutes of Mancini's own timestamps while losing zero prior hits.
ENGAGEMENT_WINDOW_BARS = 40     # beats must complete within this many bars of beat 1
INVALIDATE_TICKS = 60           # 15 pts beyond the level without reclaim kills the setup

# ── absorption (spec §2 demoted tier; research doc Q4; st-9vl) ──────────────
# A level episode = the span where a side's defended price P stays alive at
# top-of-book: open while best bid ∈ [P, P + BAND ticks] (better bids stacking
# in front keep P's defense alive), closed the moment it trades through
# (bid < P = broke) or price leaves the band (defense won). Ask-side mirror.
# Within it, a REFILL = resting size at P depleted by ≥ REFILL_DEPLETION_MIN
# then recovered by ≥ REFILL_RECOVERY_MIN (observable only while P is at top —
# MBP-1 sees one level). An AbsorptionRead emits at episode end when
# aggressive volume into P and refill count both clear their floors.
# [calibrated] st-9vl 2026-07-22 on the purchased 2026-07-02 MBP-1 day (9.06M
# book events): strict single-price episodes only ever completed refill cycles
# in the closing-auction churn (all 14 hits inside 14:58-15:00) — the band is
# what makes mid-session defense visible. Floors chosen from the emission
# grid for the ~10-40/session rarity band (the st-wnc large-lot/sweep lesson).
ABSORPTION_BAND_TICKS = 2       # defended price survives ≤ this far behind top
ABSORPTION_VOL_MIN = 100        # aggressive contracts into the level, ES scale
ABSORPTION_REFILL_MIN = 2       # distinct refill events to call it defended
REFILL_DEPLETION_MIN = 25       # contracts consumed before a recovery counts
REFILL_RECOVERY_MIN = 25        # contracts replenished to count one refill
ABSORPTION_VOL_SCALE = 500      # volume at which the vol component saturates
ABSORPTION_REFILL_SCALE = 4     # refills at which the refill component saturates

# ── absorption, impact-scaled floor (co-qp8cn, 2026-09-22) ──────────────────
# The fixed ABSORPTION_VOL_MIN above is worth two ticks of expected move at
# noon and one tick in the last fifteen minutes, which is why the reads pile
# into the end of the day. [measured] scripts/measurement/impact_by_interval.py
# over 50 recorded days: the trades-only impact slope (mid change per signed
# contract, 10-s bins, OLS through the origin) runs ~0.022 ticks/contract at
# 08:30, ~0.020 midday, 0.0094 in 14:45-15:00; the book-side law β·depth = 0.29
# holds in every interval (0.284-0.297, R² 0.91-0.94) except the last (0.228).
# The impact tracker therefore sets its floor as "enough contracts that the
# trailing rate says price should have moved EXPECTED_TICKS_MIN ticks", and
# emits with the held/broke outcome as part of the read.
IMPACT_BIN_S = 10                       # bin for the trailing regression
IMPACT_WINDOW_S = 900                   # trailing window the slope is fit over
IMPACT_MIN_BINS = 30                    # bins before the fit replaces the seed
IMPACT_SEED_TICKS_PER_CONTRACT = 0.02   # the cross-day midday median, used until warm
IMPACT_FLOOR_TICKS_PER_CONTRACT = 0.002 # a flat, dead window cannot make any volume "enough"
ABSORPTION_EXPECTED_TICKS_MIN = 3.0     # the aggression should have moved price this far
ABSORPTION_HOLD_MIN_S = 0.0             # the defended price must stand at least this long
ABSORPTION_IMPACT_REFILL_MIN = 0        # refills stay evidence, not a gate
# Print-size evidence (Steve, 2026-09-22): the activity he trades happens at a
# level of interest, in under a minute, as larger-than-average prints. The
# tracker carries the trailing mean print size (same bins and window as the
# impact fit) and counts the episode's prints at or above BIG_PRINT_MULT
# times that norm. Evidence on the read, not a gate. [measured 2026-09-18
# RTH: 209,724 prints, mean 4.0, p50 1, p90 10, p99 36.] [measured 2026-09-22,
# scripts/measurement/absorption_scalp_survey.py, 50 sessions: 99% of held
# reads already carry a print at 4× the norm (largest print / norm p50 11×),
# and requiring 20× or 40× makes the held level break MORE often within five
# minutes, not less — so the multiple stays evidence and is not a gate.]
ABSORPTION_BIG_PRINT_MULT = 4.0         # a print this many times the trailing mean is "big"
ABSORPTION_BIG_PRINTS_MIN = 0           # big prints stay evidence, not a gate
PRINT_NORM_SEED = 4.0                   # cross-day RTH mean print size, used until warm

# ── consumer wiring (spec §6) ───────────────────────────────────────────────
CONFLUENCE_TOLERANCE_PTS = 2.0  # Mancini level ∩ anchor proximity

# Calibration note (st-su4, 2026-07-05, 7/2 full RTH): at VOLUME_BAR_N=2000
# the FLOOR=100 diagonal test flags ~333 levels/session (≈1 per 2 bars — sane
# recognizer evidence), but 3-consecutive STACKS are structurally rare at this
# bar size (0-6/session across floors 30-100): cells average ~130 contracts.
# Do NOT lower the floor to manufacture stacks; if the recognizer needs
# stacked confirmation it should aggregate coarser (st-2kf design decision).
