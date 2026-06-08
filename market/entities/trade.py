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
    symbol: str           # resolved instrument symbol (e.g. "SPXW  260608C05500000")
    instrument_id: int    # Databento internal id (for joining across records)
    price: float
    size: int
    side: TradeSide = "N"
