"""Deterministic volume-bar / footprint builder (st-uqf, design spec §4, §6).

Consumes an iterator of ``Trade`` in canonical stream order and yields
``FootprintBar`` every ``n`` contracts. Pure function of its input: no clock,
no randomness, no global state — the golden-replay tests depend on that.

Rules encoded here (spec §4 "determinism rules"):
  - Bar boundary: cumulative contract count. The whole crossing trade lands in
    the bar it completes (STRADDLE_RULE) — a bar may overshoot ``n`` by at most
    one print's size, and the next bar starts empty.
  - Ordering is the *caller's* contract (``replay.read_corpus_day`` provides
    it for corpus data; the live adapter must do the same). The builder guards
    against regressions: a trade with ``ts`` earlier than its predecessor
    raises immediately rather than silently producing unstable bars.
  - Aggressor-less prints (side "N"): counted in ``volume`` and ``none_vol``,
    never in cells or delta (NONE_SIDE_POLICY = "separate").
  - Cell prices are tick-bucketed via integer tick counts (no float drift).
"""
from __future__ import annotations

import logging
from typing import Iterable, Iterator

from market.entities.footprint import FootprintBar, FootprintCell
from market.entities.trade import Trade
from market.signals.orderflow_config import TICK, VOLUME_BAR_N

logger = logging.getLogger(__name__)


class _BarAccumulator:
    """Mutable working state for one in-progress bar."""

    __slots__ = ("symbol", "start_ts", "end_ts", "open", "high", "low", "close",
                 "volume", "none_vol", "buy_vol", "sell_vol", "cells")

    def __init__(self, first: Trade):
        self.symbol = first.symbol
        self.start_ts = first.ts
        self.end_ts = first.ts
        self.open = first.price
        self.high = first.price
        self.low = first.price
        self.close = first.price
        self.volume = 0
        self.none_vol = 0
        self.buy_vol = 0
        self.sell_vol = 0
        self.cells: dict[int, list[int]] = {}  # tick_count -> [bid_vol, ask_vol]
        self.add(first)

    def add(self, t: Trade) -> None:
        self.end_ts = t.ts
        self.close = t.price
        if t.price > self.high:
            self.high = t.price
        if t.price < self.low:
            self.low = t.price
        self.volume += t.size
        if t.side == "N":
            self.none_vol += t.size
            return
        ticks = round(t.price / TICK)
        cell = self.cells.setdefault(ticks, [0, 0])
        if t.side == "A":       # sell-aggressor hit the bid
            cell[0] += t.size
            self.sell_vol += t.size
        else:                   # "B": buy-aggressor lifted the offer
            cell[1] += t.size
            self.buy_vol += t.size

    def freeze(self) -> FootprintBar:
        cells = tuple(
            FootprintCell(price=ticks * TICK, bid_vol=bv, ask_vol=av)
            for ticks, (bv, av) in sorted(self.cells.items())
        )
        return FootprintBar(
            symbol=self.symbol,
            start_ts=self.start_ts, end_ts=self.end_ts,
            open=self.open, high=self.high, low=self.low, close=self.close,
            volume=self.volume, delta=self.buy_vol - self.sell_vol,
            none_vol=self.none_vol, cells=cells,
        )


def build_bars(
    trades: Iterable[Trade],
    n: int = VOLUME_BAR_N,
    include_partial: bool = False,
) -> Iterator[FootprintBar]:
    """Yield ``FootprintBar`` every ``n`` contracts from an ordered trade stream.

    Args:
        trades: trades in canonical stream order (ts ascending; equal-ts runs
            already sequence-ordered by the caller). Out-of-order input raises
            ``ValueError`` — determinism over convenience.
        n: contracts per bar (default VOLUME_BAR_N from orderflow_config).
        include_partial: yield the trailing under-``n`` bar at stream end
            (useful for display/drills; golden fixtures pin it explicitly).
    """
    if n <= 0:
        raise ValueError(f"bar size must be positive, got {n}")

    acc: _BarAccumulator | None = None
    last_ts = None
    bars = 0
    for t in trades:
        if last_ts is not None and t.ts < last_ts:
            raise ValueError(
                f"out-of-order trade at {t.ts.isoformat()} (prev {last_ts.isoformat()}); "
                "caller must provide canonical (ts_event, sequence) order"
            )
        last_ts = t.ts
        if acc is None:
            acc = _BarAccumulator(t)
        else:
            acc.add(t)
        if acc.volume >= n:
            yield acc.freeze()
            bars += 1
            acc = None
    if acc is not None and include_partial:
        yield acc.freeze()
        bars += 1
    logger.debug("build_bars: emitted %d bars (n=%d, include_partial=%s)",
                 bars, n, include_partial)
