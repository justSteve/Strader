from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TradeSide = Literal["B", "A", "N"]


@dataclass(frozen=True)
class Trade:
    """A single executed trade tick.

    `side` is the aggressor side using Databento's convention:
      - 'B' = buy aggressor (lifted the ask)
      - 'A' = sell aggressor (hit the bid)
      - 'N' = unknown / not reported
    """
    ts: datetime          # event timestamp, US/Central
    symbol: str           # raw symbol as subscribed (e.g. "ES.c.0", "AAPL")
    instrument_id: int    # Databento internal id (for joining across records)
    price: float
    size: int
    side: TradeSide = "N"
