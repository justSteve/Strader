"""Structural Leg Profiler — deterministic reimplementation + hypothesis scoring. [st-bg4]

Reimplements the behavior of LuxAlgo's closed-source "Structural Leg Profiler"
(ATR-thresholded swing legs, per-leg volume profile + POC, naked-POC forward
projection, per-bucket delta, volume-anomaly flags) as pure functions of a
trade list + named config constants, so its claims can be scored against the
tick corpus. Measured-architecture separation: this module COMPARES an
indicator against data; nothing here feeds the live signal chain.

True-delta note: per-bucket delta here is real per-trade aggressor delta from
the corpus ``side`` field — strictly better than the TradingView original's
``request.security_lower_tf`` lower-timeframe approximation.

No-repaint rule: a leg exists only from its confirmation bar (price reversed
from the leg extreme by >= ATR x multiplier). Everything scored forward (naked
POC touches) keys off ``confirm_ts``, never the retrospective pivot time.
``audit_no_repaint`` verifies this on every run (acceptance criterion 5).

Documented deviations from the original (unavoidable — it is closed-source):
  - Bars: fixed 1-minute time bars (LEG_BAR_MINUTES) built from the tape; the
    original runs on whatever chart timeframe is loaded.
  - Naked-POC arming: the level must first get NPOC_ARM_BUCKETS away from the
    POC bucket after confirmation before a return counts as a "touch" —
    otherwise the just-confirmed reversal bar itself trivially touches.
  - A gap across the whole POC bucket (side flip with no print inside it)
    counts as a touch at the flipping trade.
"""
from __future__ import annotations

import random
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt
from typing import Iterable, Sequence

from market.entities.trade import Trade
from market.entities.volume_profile import VolumeProfile
from market.orderflow.profile import build_profile
from market.signals.orderflow_config import PROFILE_BUCKET_TICKS, TICK

# ── config constants (st-bg4 study spec) ────────────────────────────────────
LEG_BAR_MINUTES = 1          # time-bar size the segmenter runs on
ATR_PERIOD = 14              # Wilder ATR period (spec: sweep multipliers, fix period)
SWING_MULTS = (1.5, 2.0, 3.0)  # sensitivity sweep (spec constraint 3)
LEG_BUCKET_TICKS = PROFILE_BUCKET_TICKS  # 1.0-pt buckets, profile.py convention

# H1 — naked POC touch reaction
NPOC_ARM_BUCKETS = 2         # buckets away from POC before a return can "touch"
REACTION_TICKS = 8           # 2.0 pts back away from the level = bounce
PENETRATION_TICKS = 8        # 2.0 pts through the far side = penetration
REACTION_WINDOW_MIN = 15     # minutes after touch before "timeout"
CONTROL_EXCLUDE_BUCKETS = 2  # control level drawn >= this far from the POC

# H2 / H3 — leg-termination window
TERM_WINDOW_BARS = 5         # event within this many bars of the end pivot = "terminal"
EXTREME_ZONE_FRACTION = 0.80  # H3: final 20% of the leg's range = "extreme zone"
ANOMALY_K = 2.0              # bar volume > K x trailing average = anomaly
ANOMALY_WINDOW = 20          # trailing bars in the anomaly average


# ── time bars ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TimeBar:
    start_ts: datetime           # bucket floor (minute boundary, US/Central)
    end_ts: datetime             # last trade ts inside the bar
    open: float
    high: float
    low: float
    close: float
    volume: int
    delta: int                   # buy - sell aggressor volume; side "N" excluded


def build_time_bars(trades: Iterable[Trade], minutes: int = LEG_BAR_MINUTES) -> list[TimeBar]:
    """Fixed-interval OHLCV+delta bars from an ordered trade stream.

    Ordering is the caller's contract (``replay.read_corpus_day``); a
    timestamp regression raises rather than silently mis-bucketing.
    Empty intervals produce no bar (no synthetic fill).
    """
    if minutes <= 0:
        raise ValueError(f"bar minutes must be positive, got {minutes}")
    bars: list[TimeBar] = []
    cur_key = None
    o = h = l = c = 0.0
    start = end = None
    vol = delta = 0
    last_ts = None
    for t in trades:
        if last_ts is not None and t.ts < last_ts:
            raise ValueError(
                f"out-of-order trade at {t.ts.isoformat()} (prev {last_ts.isoformat()})")
        last_ts = t.ts
        floored = t.ts.replace(second=0, microsecond=0)
        key = floored.replace(minute=(floored.minute // minutes) * minutes)
        if key != cur_key:
            if cur_key is not None:
                bars.append(TimeBar(start, end, o, h, l, c, vol, delta))
            cur_key, start = key, key
            o = h = l = t.price
            vol = delta = 0
        end, c = t.ts, t.price
        if t.price > h:
            h = t.price
        if t.price < l:
            l = t.price
        vol += t.size
        if t.side == "B":
            delta += t.size
        elif t.side == "A":
            delta -= t.size
    if cur_key is not None:
        bars.append(TimeBar(start, end, o, h, l, c, vol, delta))
    return bars


def wilder_atr(bars: Sequence[TimeBar], period: int = ATR_PERIOD) -> list[float | None]:
    """Wilder-smoothed ATR, parallel to ``bars``; None during warm-up."""
    out: list[float | None] = [None] * len(bars)
    if len(bars) < period:
        return out
    trs: list[float] = []
    for i, b in enumerate(bars):
        if i == 0:
            trs.append(b.high - b.low)
        else:
            pc = bars[i - 1].close
            trs.append(max(b.high - b.low, abs(b.high - pc), abs(b.low - pc)))
    atr = sum(trs[:period]) / period
    out[period - 1] = atr
    for i in range(period, len(bars)):
        atr = (atr * (period - 1) + trs[i]) / period
        out[i] = atr
    return out


# ── leg segmentation (ZigZag, ATR-thresholded, confirmation-timed) ──────────
@dataclass(frozen=True)
class Leg:
    direction: str               # "up" | "down"
    start_idx: int               # bar index of the starting pivot
    end_idx: int                 # bar index of the ending pivot (the extreme)
    start_price: float           # pivot price (low for up leg, high for down)
    end_price: float
    start_ts: datetime           # bars[start_idx].start_ts
    end_ts: datetime             # bars[end_idx].end_ts
    confirm_idx: int             # bar whose close confirmed the reversal
    confirm_ts: datetime         # bars[confirm_idx].end_ts — scoring epoch

    @property
    def range_pts(self) -> float:
        return abs(self.end_price - self.start_price)


def segment_legs(bars: Sequence[TimeBar], atrs: Sequence[float | None],
                 mult: float) -> list[Leg]:
    """ATR-thresholded ZigZag over closed bars. Deterministic rules:

    - Threshold at bar i is ``atrs[i] * mult`` (the confirming bar's ATR).
    - Within a bar, the extreme is extended FIRST, then the reversal is tested
      against the (possibly updated) extreme using the same bar's other side.
    - At most one confirmation per bar.
    - Bootstrap (no direction yet): both running extremes tracked; the side
      with the larger excursion wins; ties break DOWN (fixed, arbitrary).
    The unconfirmed trailing leg is never emitted — nothing downstream may see
    a leg before its confirmation bar.
    """
    first = next((i for i, a in enumerate(atrs) if a is not None), None)
    if first is None:
        return []
    legs: list[Leg] = []
    hi, hi_idx = bars[first].high, first
    lo, lo_idx = bars[first].low, first
    direction: str | None = None
    ext, ext_idx = 0.0, 0                       # developing extreme of current leg
    pivot_price, pivot_idx = 0.0, 0             # last confirmed pivot

    def _rescan(lo_i: int, hi_i: int, want: str) -> tuple[float, int]:
        """Developing extreme over bars (lo_i, hi_i] after a pivot; seeded at
        hi_i when the range is empty (pivot bar == confirming bar)."""
        rng = range(lo_i + 1, hi_i + 1) if hi_i > lo_i else (hi_i,)
        if want == "high":
            j = max(rng, key=lambda k: (bars[k].high, -k))
            return bars[j].high, j
        j = min(rng, key=lambda k: (bars[k].low, k))
        return bars[j].low, j

    for i in range(first, len(bars)):
        b, thresh = bars[i], atrs[i] * mult  # type: ignore[operator]
        if direction is None:
            if b.high > hi:
                hi, hi_idx = b.high, i
            if b.low < lo:
                lo, lo_idx = b.low, i
            drop, rally = hi - b.low, b.high - lo
            if drop < thresh and rally < thresh:
                continue
            if drop >= rally:                   # ties break down
                direction, pivot_price, pivot_idx = "down", hi, hi_idx
                ext, ext_idx = _rescan(hi_idx, i, "low")
            else:
                direction, pivot_price, pivot_idx = "up", lo, lo_idx
                ext, ext_idx = _rescan(lo_idx, i, "high")
            continue
        if direction == "down":
            if b.low < ext:
                ext, ext_idx = b.low, i
            if b.high - ext >= thresh:
                legs.append(Leg("down", pivot_idx, ext_idx, pivot_price, ext,
                                bars[pivot_idx].start_ts, bars[ext_idx].end_ts,
                                i, bars[i].end_ts))
                pivot_price, pivot_idx = ext, ext_idx
                direction = "up"
                ext, ext_idx = _rescan(pivot_idx, i, "high")
        else:
            if b.high > ext:
                ext, ext_idx = b.high, i
            if ext - b.low >= thresh:
                legs.append(Leg("up", pivot_idx, ext_idx, pivot_price, ext,
                                bars[pivot_idx].start_ts, bars[ext_idx].end_ts,
                                i, bars[i].end_ts))
                pivot_price, pivot_idx = ext, ext_idx
                direction = "down"
                ext, ext_idx = _rescan(pivot_idx, i, "low")
    return legs


# ── per-leg profile with true per-bucket delta ──────────────────────────────
@dataclass(frozen=True)
class LegProfile:
    profile: VolumeProfile
    deltas: tuple[int, ...]      # net aggressor volume per bucket, parallel to prices

    @property
    def poc_price(self) -> float:
        return self.profile.poc_price


def leg_trades(trades: Sequence[Trade], ts_index: Sequence[datetime], leg: Leg) -> list[Trade]:
    """Trades inside the leg's bar span. ``ts_index`` = precomputed [t.ts]."""
    a = bisect_left(ts_index, leg.start_ts)
    z = bisect_left(ts_index, leg.end_ts + timedelta(microseconds=1))
    return list(trades[a:z])


def build_leg_profile(trades_in_leg: Sequence[Trade],
                      bucket_ticks: int = LEG_BUCKET_TICKS) -> LegProfile:
    """Re-anchor profile.py's bucket logic from session window to leg span,
    plus a TRUE per-trade aggressor delta histogram per bucket."""
    prof = build_profile(trades_in_leg, bucket_ticks)
    bucket = bucket_ticks * TICK
    lo_key = int(round(prof.prices[0] / bucket))
    deltas = [0] * len(prof.prices)
    for t in trades_in_leg:
        k = int(t.price // bucket) - lo_key
        if t.side == "B":
            deltas[k] += t.size
        elif t.side == "A":
            deltas[k] -= t.size
    return LegProfile(profile=prof, deltas=tuple(deltas))


# ── H1: naked POC forward projection + touch reaction ───────────────────────
@dataclass(frozen=True)
class TouchEvent:
    leg_index: int
    kind: str                    # "poc" | "control"
    level: float                 # bucket floor
    confirm_ts: datetime
    touch_ts: datetime | None    # None = never armed+touched before data end
    approach: str | None         # "above" | "below"
    outcome: str                 # "bounce" | "penetrate" | "timeout" | "never_touched"


def _score_level(level: float, confirm_ts: datetime, trades: Sequence[Trade],
                 ts_index: Sequence[datetime], leg_index: int, kind: str,
                 bucket_ticks: int = LEG_BUCKET_TICKS) -> TouchEvent:
    bucket = bucket_ticks * TICK
    top = level + bucket                     # bucket is [level, top)
    # armed once price gets NPOC_ARM_BUCKETS-1 full buckets beyond the bucket edge
    arm_margin = (NPOC_ARM_BUCKETS - 1) * bucket
    start = bisect_left(ts_index, confirm_ts)
    armed_side: str | None = None
    touch_i = None
    approach = None
    for i in range(start, len(trades)):
        p = trades[i].price
        in_bucket = level <= p < top
        side = None if in_bucket else ("above" if p >= top else "below")
        if armed_side is None:
            if side == "above" and p >= top + arm_margin:
                armed_side = "above"
            elif side == "below" and p <= level - arm_margin:
                armed_side = "below"
            continue
        if in_bucket or (side is not None and side != armed_side):
            touch_i, approach = i, armed_side
            break
    if touch_i is None:
        return TouchEvent(leg_index, kind, level, confirm_ts, None, None, "never_touched")
    touch_ts = trades[touch_i].ts
    deadline = touch_ts + timedelta(minutes=REACTION_WINDOW_MIN)
    if approach == "above":
        bounce_px = top + REACTION_TICKS * TICK
        pen_px = level - PENETRATION_TICKS * TICK
    else:
        bounce_px = level - REACTION_TICKS * TICK
        pen_px = top + PENETRATION_TICKS * TICK
    outcome = "timeout"
    for i in range(touch_i, len(trades)):
        t = trades[i]
        if t.ts > deadline:
            break
        if (approach == "above" and t.price >= bounce_px) or \
           (approach == "below" and t.price <= bounce_px):
            outcome = "bounce"
            break
        if (approach == "above" and t.price <= pen_px) or \
           (approach == "below" and t.price >= pen_px):
            outcome = "penetrate"
            break
    return TouchEvent(leg_index, kind, level, confirm_ts, touch_ts, approach, outcome)


def score_naked_pocs(legs: Sequence[Leg], profiles: Sequence[LegProfile],
                     trades: Sequence[Trade], ts_index: Sequence[datetime],
                     seed_prefix: str) -> list[TouchEvent]:
    """H1 events: each confirmed leg's POC projected from confirm_ts, plus a
    seeded-random matched control level from the same leg's bucket range
    (>= CONTROL_EXCLUDE_BUCKETS from the POC). Deterministic: the RNG is
    seeded from (seed_prefix, leg index) only."""
    events: list[TouchEvent] = []
    bucket = LEG_BUCKET_TICKS * TICK
    for li, (leg, lp) in enumerate(zip(legs, profiles)):
        poc = lp.poc_price
        events.append(_score_level(poc, leg.confirm_ts, trades, ts_index, li, "poc"))
        candidates = [p for p in lp.profile.prices
                      if abs(p - poc) >= CONTROL_EXCLUDE_BUCKETS * bucket]
        if candidates:
            rng = random.Random(f"{seed_prefix}:{li}")
            ctrl = rng.choice(candidates)
            events.append(_score_level(ctrl, leg.confirm_ts, trades, ts_index, li, "control"))
    return events


# ── H2: delta divergence at leg extensions ──────────────────────────────────
@dataclass(frozen=True)
class ExtensionEvent:
    leg_index: int
    bar_idx: int
    divergent: bool              # extreme extended, leg-cumulative delta did not
    terminal: bool               # within TERM_WINDOW_BARS of the leg's end pivot


def score_delta_divergence(legs: Sequence[Leg], bars: Sequence[TimeBar]) -> list[ExtensionEvent]:
    """Inside each confirmed leg: bars extending the leg extreme, split by
    whether leg-cumulative aggressor delta confirmed the new extreme. The
    first extension has no reference and is skipped."""
    events: list[ExtensionEvent] = []
    for li, leg in enumerate(legs):
        up = leg.direction == "up"
        best_px = bars[leg.start_idx].high if up else bars[leg.start_idx].low
        cum = 0
        best_cum: int | None = None
        for i in range(leg.start_idx + 1, leg.end_idx + 1):
            b = bars[i]
            cum += b.delta
            extended = (b.high > best_px) if up else (b.low < best_px)
            if extended:
                best_px = b.high if up else b.low
                if best_cum is not None:
                    div = (cum <= best_cum) if up else (cum >= best_cum)
                    events.append(ExtensionEvent(
                        li, i, div, leg.end_idx - i <= TERM_WINDOW_BARS))
                best_cum = cum if best_cum is None else (
                    max(best_cum, cum) if up else min(best_cum, cum))
        # (leg's own end pivot is an extension by construction; both arms share it)
    return events


# ── H3: volume anomalies by position in the leg ─────────────────────────────
@dataclass(frozen=True)
class AnomalyEvent:
    leg_index: int
    bar_idx: int
    zone: str                    # "extreme" (final range fraction) | "body"
    terminal: bool


def anomaly_flags(bars: Sequence[TimeBar], k: float = ANOMALY_K,
                  window: int = ANOMALY_WINDOW) -> list[bool]:
    """bar volume > k x trailing ``window``-bar average; False during warm-up."""
    out = [False] * len(bars)
    running = 0
    for i, b in enumerate(bars):
        if i >= window:
            avg = running / window
            out[i] = b.volume > k * avg
            running -= bars[i - window].volume
        running += b.volume
    return out


def score_volume_anomalies(legs: Sequence[Leg], bars: Sequence[TimeBar],
                           flags: Sequence[bool]) -> list[AnomalyEvent]:
    events: list[AnomalyEvent] = []
    for li, leg in enumerate(legs):
        rng_pts = leg.range_pts
        if rng_pts <= 0:
            continue
        up = leg.direction == "up"
        for i in range(leg.start_idx, leg.end_idx + 1):
            if not flags[i]:
                continue
            adv = (bars[i].high - leg.start_price) if up else (leg.start_price - bars[i].low)
            p = min(max(adv / rng_pts, 0.0), 1.0)
            zone = "extreme" if p >= EXTREME_ZONE_FRACTION else "body"
            events.append(AnomalyEvent(li, i, zone, leg.end_idx - i <= TERM_WINDOW_BARS))
    return events


# ── H3b: real-time-scorable variant ─────────────────────────────────────────
# H3 as specified zones anomalies by the leg's EVENTUAL range — unknowable
# live and partly mechanical (legs end at extremes, so late bars sit near the
# final range by construction). H3b removes the lookahead: among bars that
# extend the leg extreme (knowable at bar close), does an anomaly-volume
# extension precede termination more often than a normal-volume extension?
@dataclass(frozen=True)
class ExtensionAnomalyEvent:
    leg_index: int
    bar_idx: int
    anomalous: bool
    terminal: bool


def score_extension_anomalies(legs: Sequence[Leg], bars: Sequence[TimeBar],
                              flags: Sequence[bool]) -> list[ExtensionAnomalyEvent]:
    events: list[ExtensionAnomalyEvent] = []
    for li, leg in enumerate(legs):
        up = leg.direction == "up"
        best = bars[leg.start_idx].high if up else bars[leg.start_idx].low
        for i in range(leg.start_idx + 1, leg.end_idx + 1):
            b = bars[i]
            extended = (b.high > best) if up else (b.low < best)
            if extended:
                best = b.high if up else b.low
                events.append(ExtensionAnomalyEvent(
                    li, i, bool(flags[i]), leg.end_idx - i <= TERM_WINDOW_BARS))
    return events


# ── repaint audit + stats ───────────────────────────────────────────────────
def audit_no_repaint(events: Sequence[TouchEvent], legs: Sequence[Leg]) -> list[str]:
    """Acceptance criterion 5: no level scored before its leg's confirmation."""
    bad = []
    for e in events:
        leg = legs[e.leg_index]
        if e.confirm_ts < leg.confirm_ts:
            bad.append(f"leg {e.leg_index}: event epoch {e.confirm_ts} < confirm {leg.confirm_ts}")
        if e.touch_ts is not None and e.touch_ts < leg.confirm_ts:
            bad.append(f"leg {e.leg_index}: touch {e.touch_ts} < confirm {leg.confirm_ts}")
    return bad


def two_prop_z(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """(rate1, rate2, z) — pooled two-proportion z. z=0.0 when undefined."""
    if n1 == 0 or n2 == 0:
        return (k1 / n1 if n1 else 0.0, k2 / n2 if n2 else 0.0, 0.0)
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return p1, p2, (p1 - p2) / se if se else 0.0
