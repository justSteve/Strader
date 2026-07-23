"""AbsorptionTracker — MBP-1-evidenced absorption reads (st-9vl, spec §2).

Absorption is the defender's fingerprint: aggressive volume slams a level,
resting size at top-of-book keeps refilling, and price refuses to move —
force without effect (research doc Q4, Q1.5 force/effect matrix). The
research verdict is binding here: this emits a *scored read* with exposed
component evidence, never a boolean gate.

Mechanics — per book side, a **level episode** anchors at the defended price
P and stays open while P remains alive at top-of-book: for a bid defense,
best bid ∈ [P, P + ABSORPTION_BAND_TICKS] (better bids stacking in front of P
keep its defense alive). It closes the moment the level trades through
(bid < P = broke) or price leaves the band (defense won). Ask-side mirror.
The band is not a nicety: calibration on the purchased 7/2 day showed strict
single-price episodes only complete deplete→recover cycles in closing-auction
churn — mid-session, top-of-book flickers faster than passive size refills.
While open:

  - action='T' events whose aggressor attacks this side at exactly P
    accumulate ``aggr_vol`` (sell aggressors hit the bid, buy aggressors lift
    the ask — Trade side convention).
  - Resting size at P is tracked as a deplete→recover cycle: consumed by
    ≥ REFILL_DEPLETION_MIN then replenished by ≥ REFILL_RECOVERY_MIN counts
    one **refill event** — passive size stepping back in front of the attack.
    Observable only while P is at top (MBP-1 sees one level); the cycle
    pauses while better prices hold the top and resumes when P returns.

On close, if both ``aggr_vol`` and ``refill_events`` clear their floors, an
``AbsorptionRead`` emits with the episode's evidence. ``displacement_ticks``
is where top-of-book went at close, signed from the defender's perspective
(bid defense: negative = level broke, positive = price lifted away). An
episode interrupted by end-of-stream (``flush``) closes with displacement 0.

Determinism: pure function of the event stream — no wall-clock, no
randomness. Same live/replay contract as OrderflowEngine; the parity
harness extension replays a committed MBP-1 fixture through ``run``.

Each event is one atomic step: the trade (if any) is attributed to the
episodes that were standing BEFORE the event, then the post-event book state
rolls the episodes — a trade that wipes the level both credits the episode
and closes it, on the same event.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal

from market.entities.book import BookEvent
from market.signals.orderflow import AbsorptionRead
from market.signals.types import Signal
from market.signals.orderflow_config import (
    ABSORPTION_BAND_TICKS,
    ABSORPTION_REFILL_MIN,
    ABSORPTION_REFILL_SCALE,
    ABSORPTION_VOL_MIN,
    ABSORPTION_VOL_SCALE,
    REFILL_DEPLETION_MIN,
    REFILL_RECOVERY_MIN,
    TICK,
)

logger = logging.getLogger(__name__)

Side = Literal["bid", "ask"]


@dataclass
class _Episode:
    side: Side
    price: float
    start_ts: datetime
    last_ts: datetime
    aggr_vol: int = 0
    refill_events: int = 0
    # deplete→recover cycle state
    peak_sz: int = 0     # max resting size since episode start / last refill
    trough_sz: int = 0   # min resting size since peak_sz was set
    events: int = 0

    def observe_size(self, sz: int) -> None:
        """Advance the deplete→recover cycle with the current resting size."""
        self.events += 1
        if sz > self.peak_sz and self.peak_sz - self.trough_sz < REFILL_DEPLETION_MIN:
            # still building the pre-depletion peak
            self.peak_sz = sz
            self.trough_sz = sz
            return
        if sz < self.trough_sz:
            self.trough_sz = sz
            return
        if (self.peak_sz - self.trough_sz >= REFILL_DEPLETION_MIN
                and sz - self.trough_sz >= REFILL_RECOVERY_MIN):
            self.refill_events += 1
            self.peak_sz = sz
            self.trough_sz = sz


class AbsorptionTracker:
    """Consume MBP-1 book events in stream order; emit AbsorptionReads."""

    def __init__(self):
        self._episodes: dict[Side, _Episode | None] = {"bid": None, "ask": None}
        self._last_ts: datetime | None = None

    # ── public API ──────────────────────────────────────────────────────────
    def process(self, e: BookEvent) -> list[Signal]:
        if self._last_ts is not None and e.ts < self._last_ts:
            raise ValueError(
                f"out-of-order book event at {e.ts.isoformat()} (prev {self._last_ts.isoformat()})"
            )
        self._last_ts = e.ts
        out: list[Signal] = []
        self._attribute_trade(e)
        out.extend(self._roll_side("bid", e.bid_px, e.bid_sz, e))
        out.extend(self._roll_side("ask", e.ask_px, e.ask_sz, e))
        return out

    def flush(self) -> list[Signal]:
        """End-of-stream: close both open episodes with zero displacement."""
        out: list[Signal] = []
        for side in ("bid", "ask"):
            ep = self._episodes[side]
            if ep is not None:
                out.extend(self._close(ep, next_px=None))
            self._episodes[side] = None  # type: ignore[index]
        return out

    def run(self, events: Iterable[BookEvent]) -> list[Signal]:
        signals: list[Signal] = []
        for e in events:
            signals.extend(self.process(e))
        signals.extend(self.flush())
        return signals

    # ── internals ───────────────────────────────────────────────────────────
    def _attribute_trade(self, e: BookEvent) -> None:
        if e.action != "T" or e.price is None or not e.size:
            return
        # sell aggressor attacks the standing bid; buy aggressor the ask
        side: Side | None = "bid" if e.side == "A" else "ask" if e.side == "B" else None
        if side is None:
            return
        ep = self._episodes[side]
        if ep is not None and e.price == ep.price:
            ep.aggr_vol += e.size
            ep.last_ts = e.ts

    def _roll_side(self, side: Side, px: float | None, sz: int | None,
                   e: BookEvent) -> list[Signal]:
        out: list[Signal] = []
        ep = self._episodes[side]
        if ep is not None and px is not None and not self._alive(ep, px):
            out.extend(self._close(ep, next_px=px))
            ep = None
        if ep is not None and px is None:
            out.extend(self._close(ep, next_px=None))
            ep = None
        if ep is None:
            if px is not None:
                ep = _Episode(side=side, price=px, start_ts=e.ts, last_ts=e.ts,
                              peak_sz=sz or 0, trough_sz=sz or 0)
            self._episodes[side] = ep
            return out
        ep.last_ts = e.ts
        # the deplete→recover cycle is only observable while the anchor price
        # itself holds the top — a better price in front hides P's size
        if sz is not None and px == ep.price:
            ep.observe_size(sz)
        return out

    @staticmethod
    def _alive(ep: _Episode, px: float) -> bool:
        band = ABSORPTION_BAND_TICKS * TICK
        if ep.side == "bid":
            return ep.price <= px <= ep.price + band + 1e-9
        return ep.price - band - 1e-9 <= px <= ep.price

    def _close(self, ep: _Episode, next_px: float | None) -> list[Signal]:
        if ep.aggr_vol < ABSORPTION_VOL_MIN or ep.refill_events < ABSORPTION_REFILL_MIN:
            return []
        # signed from the defender's perspective: for a bid defense a lower
        # next bid = broke (negative); for an ask defense a higher next ask
        # = broke (negative)
        if next_px is None:
            disp = 0
        else:
            raw = round((next_px - ep.price) / TICK)
            disp = raw if ep.side == "bid" else -raw
        vol_score = min(1.0, ep.aggr_vol / ABSORPTION_VOL_SCALE)
        refill_score = min(1.0, ep.refill_events / ABSORPTION_REFILL_SCALE)
        confidence = round(0.5 * vol_score + 0.5 * refill_score, 4)
        attacker = "sellers" if ep.side == "bid" else "buyers"
        away = "lifted away" if ep.side == "bid" else "fell away"
        outcome = ("held (end of stream)" if next_px is None
                   else "broke" if disp < 0 else away)
        dur_s = (ep.last_ts - ep.start_ts).total_seconds()
        return [AbsorptionRead(
            timestamp=ep.last_ts, source="orderflow.absorption",
            confidence=confidence,
            reason=(f"{attacker} threw {ep.aggr_vol} contracts at {ep.price:.2f} "
                    f"{ep.side}; size refilled {ep.refill_events}x over {dur_s:.1f}s "
                    f"— absorbed, level {outcome}"),
            side=ep.side, price=ep.price, aggressive_vol=ep.aggr_vol,
            displacement_ticks=disp, refill_events=ep.refill_events,
        )]
