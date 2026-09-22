"""ImpactAbsorptionTracker — absorption with a floor set by the tape's own
price impact, and the effect half of the definition carried on the read.
[co-qp8cn, 2026-09-22]

Why a second tracker. ``AbsorptionTracker`` (absorption.py) gates on a fixed
contract count and a refill count and records where price went without
requiring anything of it. Measured over 45 recorded sessions that gave a
median of 72 reads a session from August on, half of them in the last ten
minutes, 87% ending with the level traded through. The survey on the COO desk
(absorption-detection-survey-2026-09-22) and our own measurement
(scripts/measurement/impact_by_interval.py) say why: the price move per
contract of flow halves in the last fifteen minutes because the book gets
deeper, so a fixed count clears there almost by default.

What this one does differently, and nothing else:

  1. The volume floor is "enough contracts that price should have moved
     ABSORPTION_EXPECTED_TICKS_MIN ticks", where should-have is the trailing
     IMPACT_WINDOW_S regression of mid change on signed trade volume, refit
     every IMPACT_BIN_S seconds from the stream itself (no clock, no
     look-ahead: the slope in force at an event is the slope of the bins
     that closed before it). Until IMPACT_MIN_BINS have closed the seed
     constant stands in.
  2. The read says whether the level HELD when the episode ended (price left
     the band without trading through) or BROKE, and how long it stood.
     Nothing is filtered on it here; the survey and the page decide.
  3. Refills are evidence on the read, not a gate (ABSORPTION_IMPACT_REFILL_MIN
     defaults to 0).

Episode mechanics are inherited unchanged from AbsorptionTracker: a defended
price at top-of-book, alive within the band, aggression credited per trade,
refills counted while the price holds the top. Same determinism contract.
"""
from __future__ import annotations

import logging
from collections import deque
from market.entities.book import BookEvent
from market.orderflow.absorption import AbsorptionTracker, _Episode
from market.signals.orderflow import ImpactAbsorptionRead
from market.signals.orderflow_config import (
    ABSORPTION_EXPECTED_TICKS_MIN,
    ABSORPTION_HOLD_MIN_S,
    ABSORPTION_IMPACT_REFILL_MIN,
    IMPACT_BIN_S,
    IMPACT_FLOOR_TICKS_PER_CONTRACT,
    IMPACT_MIN_BINS,
    IMPACT_SEED_TICKS_PER_CONTRACT,
    IMPACT_WINDOW_S,
    TICK,
)
from market.signals.types import Signal

logger = logging.getLogger(__name__)


class ImpactEstimator:
    """Trailing slope of mid-price change (ticks) on signed trade volume,
    through the origin, over the last IMPACT_WINDOW_S of IMPACT_BIN_S bins.

    A bin closes when an event arrives with a later bin key; the slope is
    recomputed then, from closed bins only. ``rate`` is the value in force
    for the current event. A window with no signed volume, or a fit at or
    below the floor, reports the floor rather than zero or a negative
    number: a dead tape cannot make any amount of volume "enough".
    """

    def __init__(self, bin_s: int = IMPACT_BIN_S, window_s: int = IMPACT_WINDOW_S,
                 min_bins: int = IMPACT_MIN_BINS, seed: float = IMPACT_SEED_TICKS_PER_CONTRACT,
                 floor: float = IMPACT_FLOOR_TICKS_PER_CONTRACT):
        self.bin_s = bin_s
        self.max_bins = max(1, window_s // bin_s)
        self.min_bins = min_bins
        self.seed = seed
        self.floor = floor
        self._bins: deque[tuple[int, int]] = deque()   # (signed volume, Δmid ticks)
        self._sxy = 0.0
        self._sxx = 0.0
        self._key: int | None = None
        self._ti = 0
        self._mid_open: float | None = None
        self._mid_last: float | None = None
        self.rate = seed
        self.closed_bins = 0

    def _close_bin(self) -> None:
        dp = 0 if self._mid_open is None or self._mid_last is None \
            else round((self._mid_last - self._mid_open) / TICK)
        self._bins.append((self._ti, dp))
        self._sxy += self._ti * dp
        self._sxx += self._ti * self._ti
        if len(self._bins) > self.max_bins:
            x, y = self._bins.popleft()
            self._sxy -= x * y
            self._sxx -= x * x
        self.closed_bins += 1
        if self.closed_bins >= self.min_bins and self._sxx > 0:
            self.rate = max(self.floor, self._sxy / self._sxx)
        self._ti = 0
        self._mid_open = self._mid_last

    def observe(self, e: BookEvent) -> None:
        key = int(e.ts.timestamp()) // self.bin_s
        if self._key is not None and key != self._key:
            self._close_bin()
        self._key = key
        if e.action == "T" and e.size and e.side in ("B", "A"):
            self._ti += e.size if e.side == "B" else -e.size
        if e.bid_px is not None and e.ask_px is not None:
            mid = (e.bid_px + e.ask_px) / 2
            self._mid_last = mid
            if self._mid_open is None:
                self._mid_open = mid

    def expected_ticks(self, contracts: int) -> float:
        return self.rate * contracts


class ImpactAbsorptionTracker(AbsorptionTracker):
    """AbsorptionTracker with the impact-scaled floor and the outcome on the read."""

    def __init__(self, *, expected_ticks_min: float = ABSORPTION_EXPECTED_TICKS_MIN,
                 hold_min_s: float = ABSORPTION_HOLD_MIN_S,
                 refill_min: int = ABSORPTION_IMPACT_REFILL_MIN,
                 estimator: ImpactEstimator | None = None):
        super().__init__()
        self.expected_ticks_min = expected_ticks_min
        self.hold_min_s = hold_min_s
        self.refill_min = refill_min
        self.impact = estimator if estimator is not None else ImpactEstimator()

    def process(self, e: BookEvent) -> list[Signal]:
        # the rate in force for this event is fit on bins that closed before it
        self.impact.observe(e)
        return super().process(e)

    def _close(self, ep: _Episode, next_px: float | None) -> list[Signal]:
        rate = self.impact.rate
        expected = self.impact.expected_ticks(ep.aggr_vol)
        hold_s = (ep.last_ts - ep.start_ts).total_seconds()
        if expected < self.expected_ticks_min or ep.refill_events < self.refill_min \
                or hold_s < self.hold_min_s:
            return []
        if next_px is None:
            disp = 0
            held = False          # end of stream: not a defense that finished
        else:
            raw = round((next_px - ep.price) / TICK)
            disp = raw if ep.side == "bid" else -raw
            held = disp >= 0
        actual = abs(disp)
        confidence = round(max(0.0, 1.0 - actual / expected), 4) if expected > 0 else 0.0
        attacker = "sellers" if ep.side == "bid" else "buyers"
        outcome = ("end of stream" if next_px is None else "held" if held else "broke")
        return [ImpactAbsorptionRead(
            timestamp=ep.last_ts, source="orderflow.absorption_impact",
            confidence=confidence,
            reason=(f"{attacker} threw {ep.aggr_vol} contracts at {ep.price:.2f} {ep.side} "
                    f"over {hold_s:.1f}s; at {rate:.4f} ticks/contract that should have moved "
                    f"price {expected:.1f} ticks, it moved {actual}; refilled {ep.refill_events}x "
                    f"— level {outcome}"),
            side=ep.side, price=ep.price, aggressive_vol=ep.aggr_vol,
            displacement_ticks=disp, refill_events=ep.refill_events,
            expected_ticks=round(expected, 3), impact_ticks_per_contract=round(rate, 6),
            held=held, hold_s=round(hold_s, 3),
        )]


__all__ = ["ImpactEstimator", "ImpactAbsorptionTracker"]
