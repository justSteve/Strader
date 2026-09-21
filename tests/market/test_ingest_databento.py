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


# ── BookEvent conversion (co-qp8cn) — real vendor records, no fakes ──────────
# quote_from_databento drops the triggering event; book_event_from_databento
# keeps it. These build genuine MBP1Msg records so an attribute rename in the
# vendor library fails here and not in the live collector.

_T_NS = 1_789_739_789_123_456_789   # 2026-09-18 13:56:29.123456789 UTC
_PX = 1_000_000_000


def _real_mbp1(action, side, price, size, bid, ask, iid=10252, seq=7):
    import databento_dbn as dbn
    level = dbn.BidAskPair(bid_px=bid[0], ask_px=ask[0], bid_sz=bid[1], ask_sz=ask[1],
                           bid_ct=5, ask_ct=6)
    return dbn.MBP1Msg(publisher_id=1, instrument_id=iid, ts_event=_T_NS, price=price,
                       size=size, action=action, side=side, depth=0, ts_recv=_T_NS + 10,
                       flags=0, ts_in_delta=0, sequence=seq, levels=level)


def test_book_event_keeps_the_trade_a_quote_drops():
    import databento_dbn as dbn
    from market.ingest.databento import book_event_from_databento

    rec = _real_mbp1(dbn.Action.TRADE, dbn.Side.ASK, 7695 * _PX + _PX // 2, 12,
                     bid=(7695 * _PX + _PX // 2, 40), ask=(7695 * _PX + 3 * _PX // 4, 18))
    e = book_event_from_databento(rec, {10252: "ESZ6"})
    assert (e.symbol, e.instrument_id, e.sequence) == ("ESZ6", 10252, 7)
    assert (e.action, e.side, e.price, e.size) == ("T", "A", 7695.5, 12)
    assert (e.bid_px, e.bid_sz, e.bid_ct) == (7695.5, 40, 5)
    assert (e.ask_px, e.ask_sz, e.ask_ct) == (7695.75, 18, 6)


def test_book_event_timestamp_is_central_and_keeps_the_nanoseconds_beside_it():
    import databento_dbn as dbn
    from market.ingest.databento import book_event_from_databento

    rec = _real_mbp1(dbn.Action.MODIFY, dbn.Side.NONE, 7695 * _PX, 1,
                     bid=(7695 * _PX, 5), ask=(7695 * _PX + _PX // 4, 5))
    e = book_event_from_databento(rec, {})
    assert e.ts == datetime(2026, 9, 18, 8, 56, 29, 123456, tzinfo=CENTRAL)
    assert e.ts.utcoffset().total_seconds() == -5 * 3600
    assert e.ts_ns == _T_NS
    assert e.symbol == ""


def test_book_event_ts_ns_is_not_part_of_equality():
    # a row read back from JSONL has no ts_ns and is still the same event
    import dataclasses
    import databento_dbn as dbn
    from market.ingest.databento import book_event_from_databento

    rec = _real_mbp1(dbn.Action.MODIFY, dbn.Side.NONE, 7695 * _PX, 1,
                     bid=(7695 * _PX, 5), ask=(7695 * _PX + _PX // 4, 5))
    e = book_event_from_databento(rec, {})
    assert dataclasses.replace(e, ts_ns=None) == e


def test_book_event_undefined_prices_become_none():
    import databento_dbn as dbn
    from market.ingest.databento import book_event_from_databento

    rec = _real_mbp1(dbn.Action.CLEAR, dbn.Side.NONE, dbn.UNDEF_PRICE, 0,
                     bid=(dbn.UNDEF_PRICE, 0), ask=(7695 * _PX, 5))
    e = book_event_from_databento(rec, {})
    assert e.action == "R"
    assert e.price is None and e.bid_px is None and e.ask_px == 7695.0


def test_live_client_book_events_maps_symbols_and_skips_other_records(monkeypatch):
    import databento_dbn as dbn
    import market.ingest.databento as ing

    mapping = dbn.SymbolMappingMsg(
        publisher_id=1, instrument_id=10252, ts_event=_T_NS,
        stype_in=dbn.SType.CONTINUOUS, stype_in_symbol="ES.c.0",
        stype_out=dbn.SType.RAW_SYMBOL, stype_out_symbol="ESZ6",
        start_ts=_T_NS, end_ts=_T_NS)
    trade = _real_mbp1(dbn.Action.TRADE, dbn.Side.BID, 7695 * _PX, 3,
                       bid=(7694 * _PX, 9), ask=(7695 * _PX, 2))

    class FakeLive:
        def __iter__(self):
            return iter([mapping, object(), trade])

        def stop(self):
            pass

    monkeypatch.setattr(ing, "Live", lambda key=None: FakeLive())
    (e,) = list(ing.LiveClient(key="dummy").book_events())
    assert (e.symbol, e.action, e.side, e.size) == ("ESZ6", "T", "B", 3)
