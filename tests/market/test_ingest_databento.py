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

from market.entities.quote import Quote
from market.entities.trade import Trade
from market.ingest.databento import quote_from_databento, trade_from_databento

CENTRAL = ZoneInfo("America/Chicago")


@dataclass
class FakeTradeMsg:
    """Stand-in for databento_dbn.TradeMsg with only the fields we use."""
    instrument_id: int
    pretty_ts_event: datetime
    pretty_price: float
    size: int
    side: str


@dataclass
class FakeMBP1Msg:
    """Stand-in for databento_dbn.MBP1Msg with only the fields we use."""
    instrument_id: int
    pretty_ts_event: datetime
    pretty_bid_px_00: float
    bid_sz_00: int
    pretty_ask_px_00: float
    ask_sz_00: int


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


def test_quote_from_databento_resolves_symbol_and_fields():
    record = FakeMBP1Msg(
        instrument_id=42,
        pretty_ts_event=datetime(2026, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
        pretty_bid_px_00=298.50,
        bid_sz_00=100,
        pretty_ask_px_00=298.55,
        ask_sz_00=200,
    )
    quote = quote_from_databento(record, {42: "AAPL"})

    assert isinstance(quote, Quote)
    assert quote.symbol == "AAPL"
    assert quote.bid_price == 298.50
    assert quote.bid_size == 100
    assert quote.ask_price == 298.55
    assert quote.ask_size == 200
    assert quote.mid == pytest.approx(298.525)
    assert quote.spread == pytest.approx(0.05)


def test_quote_from_databento_normalizes_to_central():
    record = FakeMBP1Msg(
        instrument_id=1,
        pretty_ts_event=datetime(2026, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
        pretty_bid_px_00=200.0,
        bid_sz_00=10,
        pretty_ask_px_00=200.05,
        ask_sz_00=20,
    )
    quote = quote_from_databento(record, {1: "AAPL"})
    assert quote.ts.tzinfo == CENTRAL
    assert quote.ts.hour == 9
    assert quote.ts.minute == 30


def test_quote_from_databento_unknown_instrument_id_yields_empty_symbol():
    record = FakeMBP1Msg(
        instrument_id=999,
        pretty_ts_event=datetime(2026, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
        pretty_bid_px_00=100.0,
        bid_sz_00=1,
        pretty_ask_px_00=100.05,
        ask_sz_00=1,
    )
    quote = quote_from_databento(record, {})
    assert quote.symbol == ""
    assert quote.instrument_id == 999


def test_live_client_symbol_map_uses_stype_out(monkeypatch):
    """LiveClient must resolve a parent/continuous input to the per-contract
    instrument symbol via stype_out_symbol — NOT collapse every contract to
    the parent (stype_in_symbol). Regression for a live-feed bug that tagged
    every SPXW option trade as 'SPXW.OPT'.
    """
    import market.ingest.databento as ing

    class FakeSymbolMapping:
        def __init__(self, instrument_id, stype_in_symbol, stype_out_symbol):
            self.instrument_id = instrument_id
            self.stype_in_symbol = stype_in_symbol
            self.stype_out_symbol = stype_out_symbol

    class FakeTradeMsg2:
        def __init__(self, instrument_id, ts, price, size, side):
            self.instrument_id = instrument_id
            self.pretty_ts_event = ts
            self.pretty_price = price
            self.size = size
            self.side = side

    class FakeLive:
        def __init__(self, *a, **k):
            self.records = []

        def subscribe(self, **kwargs):
            pass

        def __iter__(self):
            return iter(self.records)

        def stop(self):
            pass

    fake = FakeLive()
    fake.records = [
        FakeSymbolMapping(7, "SPXW.OPT", "SPXW  260608C05500000"),
        FakeTradeMsg2(7, datetime(2026, 6, 8, 18, 30, 0, tzinfo=timezone.utc),
                      2.35, 4, "B"),
    ]
    monkeypatch.setattr(ing, "Live", lambda key=None: fake)
    monkeypatch.setattr(ing, "SymbolMappingMsg", FakeSymbolMapping)
    monkeypatch.setattr(ing, "TradeMsg", FakeTradeMsg2)

    client = ing.LiveClient(key="dummy")
    trades = list(client.trades())
    assert len(trades) == 1
    assert trades[0].symbol == "SPXW  260608C05500000"  # not "SPXW.OPT"
