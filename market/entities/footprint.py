"""Footprint bar entities — per-price aggressor-split volume within a volume bar.

The footprint is the data substrate for the orderflow layer (st-l5o design,
docs/superpowers/specs/2026-07-03-orderflow-signal-layer-design.md §6): each
bar spans a fixed number of contracts (VOLUME_BAR_N, not clock time), and each
cell records how much volume traded at one price on each aggressor side.

Data only, mirroring the ``market/entities`` convention: these classes
represent and measure; the builder that produces them lives in
``market/orderflow/bars.py`` and the signals that interpret them live in
``market/signals/``.

Side vocabulary (Databento/CME convention, carried from ``Trade.side``):
  - ask_vol — volume from buy-aggressors (lifted the offer; ``side == "B"``)
  - bid_vol — volume from sell-aggressors (hit the bid; ``side == "A"``)
Aggressor-less prints (``side == "N"``) are tracked on the bar as ``none_vol``
and never enter cells or delta (spec §9 NONE_SIDE_POLICY).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FootprintCell:
    """Aggressor-split volume at one price within one bar."""

    price: float   # tick-bucketed (ES 0.25)
    bid_vol: int   # sell-aggressor volume (hit the bid)
    ask_vol: int   # buy-aggressor volume (lifted the offer)

    @property
    def total(self) -> int:
        return self.bid_vol + self.ask_vol

    @property
    def delta(self) -> int:
        return self.ask_vol - self.bid_vol


@dataclass(frozen=True)
class FootprintBar:
    """One volume bar: OHLC plus the per-price aggressor-split cells.

    ``volume`` counts every contract in the bar including ``none_vol``;
    ``delta`` counts only exchange-tagged aggressor volume. ``cells`` are
    ascending by price and cover only prices that traded in this bar.
    """

    symbol: str
    start_ts: datetime  # ts_event of first print, US/Central
    end_ts: datetime    # ts_event of last print, US/Central
    open: float
    high: float
    low: float
    close: float
    volume: int         # all contracts (>= VOLUME_BAR_N except a trailing partial)
    delta: int          # buy-aggressor volume − sell-aggressor volume
    none_vol: int       # aggressor-less contracts; in volume, never in delta
    cells: tuple[FootprintCell, ...]

    def __post_init__(self) -> None:
        prices = [c.price for c in self.cells]
        if prices != sorted(prices):
            raise ValueError("FootprintBar.cells must be ascending by price")
        if self.volume < 0 or self.none_vol < 0:
            raise ValueError("volume/none_vol must be non-negative")

    @property
    def duration_seconds(self) -> float:
        """Wall time the bar took to fill — an urgency read, not an input."""
        return (self.end_ts - self.start_ts).total_seconds()

    @property
    def poc_price(self) -> float:
        """Point of control: the price with the most traded volume in this bar.
        Deterministic tie-break: the lower price wins."""
        if not self.cells:
            raise ValueError("bar has no cells")
        best = max(self.cells, key=lambda c: (c.total, -c.price))
        return best.price
