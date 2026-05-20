from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Quote:
    """A top-of-book snapshot: best bid and best ask at event time.

    Derived from Databento MBP-1 / TBBO records. Sizes are aggregate
    visible quantity at each level.
    """
    ts: datetime          # event timestamp, US/Central
    symbol: str
    instrument_id: int
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int

    @property
    def mid(self) -> float:
        return (self.bid_price + self.ask_price) / 2.0

    @property
    def spread(self) -> float:
        return self.ask_price - self.bid_price
