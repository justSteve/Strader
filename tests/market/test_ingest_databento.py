"""
Offline tests for the Databento ingest boundary.

These tests do not hit the Databento Live API. They construct synthetic
TradeMsg-shaped objects and verify the converter produces the expected
typed Trade entity. Real-stream verification belongs in scripts/, gated
by an API key and intentional metered cost.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from market.entities.trade import Trade
from market.ingest.databento import trade_from_databento

CENTRAL = ZoneInfo("America/Chicago")


@dataclass
class FakeTradeMsg:
    """Stand-in for databento_dbn.TradeMsg with only the fields we use."""
    instrument_id: int
    pretty_ts_event: datetime
    pretty_price: float
    size: int
    side: str


def test_trade_from_databento_resolves_symbol():
    record = FakeTradeMsg(
        instrument_id=42,
        pretty_ts_event=datetime(2026, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
        pretty_price=5820.25,
        size=3,
        side="B",
    )
    trade = trade_from_databento(record, {42: "ES.c.0"})

    assert isinstance(trade, Trade)
    assert trade.symbol == "ES.c.0"
    assert trade.instrument_id == 42
    assert trade.price == 5820.25
    assert trade.size == 3
    assert trade.side == "B"


def test_trade_from_databento_normalizes_to_central():
    record = FakeTradeMsg(
        instrument_id=1,
        pretty_ts_event=datetime(2026, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
        pretty_price=200.0,
        size=100,
        side="A",
    )
    trade = trade_from_databento(record, {1: "AAPL"})
    assert trade.ts.tzinfo == CENTRAL
    # 14:30 UTC = 09:30 CDT (CST during summer DST)
    assert trade.ts.hour == 9
    assert trade.ts.minute == 30


def test_trade_from_databento_unknown_instrument_id_yields_empty_symbol():
    record = FakeTradeMsg(
        instrument_id=999,
        pretty_ts_event=datetime(2026, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
        pretty_price=100.0,
        size=10,
        side="B",
    )
    trade = trade_from_databento(record, {})  # empty map
    assert trade.symbol == ""
    assert trade.instrument_id == 999


def test_trade_from_databento_normalizes_unknown_side():
    record = FakeTradeMsg(
        instrument_id=1,
        pretty_ts_event=datetime(2026, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
        pretty_price=100.0,
        size=1,
        side="X",  # not B/A/N
    )
    trade = trade_from_databento(record, {1: "AAPL"})
    assert trade.side == "N"


def test_trade_from_databento_accepts_int_side():
    record = FakeTradeMsg(
        instrument_id=1,
        pretty_ts_event=datetime(2026, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
        pretty_price=100.0,
        size=1,
        side=ord("B"),  # some SDK versions deliver side as int
    )
    trade = trade_from_databento(record, {1: "AAPL"})
    assert trade.side == "B"
