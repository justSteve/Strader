"""MIGauge — the market-internals composite gauge engine (st-3fr, phase B).

Consumes $TICK minute candles in session order and emits one ``InternalsRead``
per minute: a signed −100..+100 score plus the named driver. Deterministic —
pure function of the candle stream, no wall-clock — so live and replay produce
identical reads (the orderflow-engine parity discipline applied here).

v1 components (weights in internals_config.GAUGE_WEIGHTS, seeded not fitted):

  INSTANT — the minute's wick measured against its time-bucket's calibrated
  climax scale (p95/p99 of the 31-session distribution, per side). Maps
  0 → bucket climax → bucket extreme onto 0 → 75 → 100, signed by which side
  of the tape produced the bigger relative print. This is the climax meter.

  CUM — cumulative TICK (sum of minute closes since the 08:30 open) divided
  by minutes elapsed, against the calibrated per-minute pace scale. This is
  the day's spine: has the tape had a lean all session.

The driver label is the component with the larger weighted contribution,
upgraded to "TICK climax" / "TICK capitulation" whenever the instant wick
actually crossed its bucket's p95/p99 line — those prints name themselves
regardless of weights.

CVD divergence from the orderflow engine joins as a third leg in a later
phase; the v1 gauge stands on internals alone so it can run from the Schwab
minute feed with no Databento dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from market.signals.internals import InternalsRead
from market.signals.internals_config import (
    GAUGE_CLIMAX_BAND,
    GAUGE_LEAN_BAND,
    GAUGE_WEIGHTS,
    TICK_BUCKETS,
    TICK_CUM_PER_MIN_SCALE,
    TICK_THRESHOLDS,
)


@dataclass(frozen=True)
class TickMinute:
    """One $TICK minute candle. high/low are the wick extremes — the wick IS
    the climax; closes understate it. close feeds the cumulative spine."""
    ts: datetime          # minute start, US/Central
    high: int
    low: int
    close: int


def bucket_of(ts: datetime) -> str | None:
    t = ts.time()
    for name, lo, hi in TICK_BUCKETS:
        if lo <= t < hi:
            return name
    return None


def _instant_score(high: int, low: int, bucket: str) -> tuple[int, bool, bool]:
    """Map the minute wick to a signed 0..100 against the bucket's scale.
    Returns (score, crossed_climax, crossed_extreme)."""
    pos_climax, pos_extreme, neg_climax, neg_extreme = TICK_THRESHOLDS[bucket]
    pos_ratio = max(0.0, high / pos_climax)
    neg_ratio = max(0.0, low / neg_climax)  # both negative -> positive ratio
    if pos_ratio >= neg_ratio:
        ratio, sign = pos_ratio, 1
        ext_ratio = pos_extreme / pos_climax
    else:
        ratio, sign = neg_ratio, -1
        ext_ratio = neg_extreme / neg_climax
    if ratio <= 1.0:
        score = 75.0 * ratio
    elif ratio >= ext_ratio:
        score = 100.0
    else:
        score = 75.0 + 25.0 * (ratio - 1.0) / (ext_ratio - 1.0)
    return int(round(sign * score)), ratio >= 1.0, ratio >= ext_ratio


class MIGauge:
    """Process $TICK minutes in session order; emit one read per minute."""

    def __init__(self):
        self.cum_tick = 0
        self.minutes = 0
        self._last_ts: datetime | None = None
        self._session_day = None

    def process(self, m: TickMinute) -> InternalsRead | None:
        """Returns None for minutes outside the session buckets."""
        if self._last_ts is not None and m.ts < self._last_ts:
            raise ValueError(
                f"out-of-order minute at {m.ts.isoformat()} (prev {self._last_ts.isoformat()})"
            )
        self._last_ts = m.ts
        if self._session_day != m.ts.date():
            self._session_day = m.ts.date()
            self.cum_tick = 0
            self.minutes = 0
        bucket = bucket_of(m.ts)
        if bucket is None:
            return None
        self.cum_tick += m.close
        self.minutes += 1

        instant, hit_climax, hit_extreme = _instant_score(m.high, m.low, bucket)
        pace = self.cum_tick / (self.minutes * TICK_CUM_PER_MIN_SCALE)
        cum = int(round(max(-1.0, min(1.0, pace)) * 100))

        w = GAUGE_WEIGHTS[bucket]
        score = int(round(w["instant"] * instant + w["cum"] * cum))

        if hit_extreme:
            driver = "TICK capitulation" if instant < 0 else "TICK climax+"
        elif hit_climax:
            driver = "TICK flush climax" if instant < 0 else "TICK climax"
        elif abs(w["cum"] * cum) >= abs(w["instant"] * instant):
            driver = "cum TICK spine" if abs(cum) >= 25 else "quiet tape"
        else:
            driver = "TICK pressure" if abs(instant) >= 25 else "quiet tape"

        band = ("climax" if abs(score) >= GAUGE_CLIMAX_BAND
                else "lean" if abs(score) >= GAUGE_LEAN_BAND else "neutral")
        return InternalsRead(
            timestamp=m.ts, source="internals.gauge",
            confidence=round(abs(score) / 100, 4),
            reason=(f"{score:+d} · {driver} — wick {m.high:+d}/{m.low:+d} "
                    f"({bucket}), cum {self.cum_tick:+d} over {self.minutes}m"),
            score=score, driver=driver, band=band, bucket=bucket,
            instant=instant, cum=cum,
            tick_high=m.high, tick_low=m.low, cum_tick=self.cum_tick,
        )

    def run(self, minutes: Iterable[TickMinute]) -> list[InternalsRead]:
        out = []
        for m in minutes:
            r = self.process(m)
            if r is not None:
                out.append(r)
        return out
