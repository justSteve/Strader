from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from market.entities.trade import TradeSide

# Databento MBP event actions we consume: A=add, C=cancel, M=modify,
# T=trade, F=fill, R=clear/reset, N=none. The tracker only branches on "T";
# every action still updates the post-event book state.
BookAction = Literal["A", "C", "M", "T", "F", "R", "N"]


@dataclass(frozen=True)
class BookEvent:
    """One MBP-1 (top-of-book) update: the triggering event plus the book
    state AFTER it. Trades (action='T') interleave with quote updates in the
    same stream — that pairing is what absorption logic consumes. [st-9vl]

    `side` follows the Trade convention for action='T' rows:
      'B' = buy aggressor (lifted the ask), 'A' = sell aggressor (hit the bid).
    Bid/ask fields may be None when a side of the book is empty.
    """
    ts: datetime            # event timestamp, US/Central
    symbol: str
    instrument_id: int
    action: BookAction
    side: TradeSide = "N"
    price: float | None = None    # event price (trade price for action='T')
    size: int | None = None       # event size
    bid_px: float | None = None   # best bid after the event
    ask_px: float | None = None
    bid_sz: int | None = None
    ask_sz: int | None = None
    bid_ct: int | None = None     # resting order count at best bid
    ask_ct: int | None = None
    sequence: int | None = None
