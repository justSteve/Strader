"""OrderIntent — the wire form the service will accept from the engine. [st-eznu]"""

from __future__ import annotations

from datetime import date

import pytest

from execd.intent import (SENDABLE_ORDER_TYPES, Occ, OrderIntent, OrderType, Side,
                          parse_occ)

from .conftest import CALL, PUT, entry


class TestOcc:
    def test_parses_the_21_character_form(self):
        occ = parse_occ(CALL)
        assert occ == Occ("SPXW", date(2026, 8, 26), "C", 6400.0)
        assert occ.right_word == "CALL"

    def test_parses_a_put_and_a_fractional_strike(self):
        occ = parse_occ("SPXW  260826P06312500")
        assert (occ.right, occ.strike, occ.right_word) == ("P", 6312.5, "PUT")

    def test_parses_an_unpadded_root(self):
        assert parse_occ("SPX260826C06400000").root == "SPX"

    @pytest.mark.parametrize("symbol", [
        "", "SPXW", "SPXW  260826X06400000", "SPXW  261326C06400000",
        "spxw  260826c06400000", "SPXW  260826C640000",
    ])
    def test_refuses_malformations_by_naming_the_symbol(self, symbol):
        with pytest.raises(ValueError, match="OCC"):
            parse_occ(symbol)


class TestValidation:
    def test_a_well_formed_entry_has_no_problems(self):
        assert entry().problems() == []
        assert entry().validated() is not None

    def test_intent_id_must_be_a_usable_idempotency_key(self):
        assert any("intent_id" in p for p in entry(intent_id="").problems())
        assert any("intent_id" in p for p in entry(intent_id="ab").problems())
        assert entry(intent_id="desk:2026-08-26:001").problems() == []

    def test_quantity_must_be_a_positive_integer(self):
        assert any("qty" in p for p in entry(qty=0).problems())
        assert any("qty" in p for p in entry(qty=-1).problems())
        # bool is an int in Python; a True quantity is a bug, not one contract.
        assert any("qty" in p for p in entry(qty=True).problems())

    def test_a_limit_order_needs_a_limit(self):
        assert any("LIMIT" in p for p in entry(limit=None).problems())
        assert any("LIMIT" in p for p in entry(limit=0.0).problems())

    def test_a_market_order_carries_no_limit(self):
        bad = OrderIntent("t-1", CALL, Side.SELL_TO_CLOSE, 1,
                          order_type=OrderType.MARKET, limit=1.0)
        assert any("MARKET" in p for p in bad.problems())

    def test_a_stop_order_needs_a_stop_price(self):
        bad = OrderIntent("t-1", CALL, Side.SELL_TO_CLOSE, 1, order_type=OrderType.STOP)
        assert any("STOP" in p for p in bad.problems())

    @pytest.mark.parametrize("order_type", [OrderType.NET_CREDIT, OrderType.NET_DEBIT])
    def test_the_service_names_spread_orders_but_will_not_send_one(self, order_type):
        """The transport has to report the three-leg spreads the account holds,
        so the type vocabulary knows them; that must not become permission to
        place one. Everything in bounds.py reasons about single-leg long
        premium [st-ilp9]."""
        bad = OrderIntent("t-1", CALL, Side.BUY_TO_OPEN, 1, order_type=order_type, limit=2.0)
        assert any("does not send" in p for p in bad.problems())
        with pytest.raises(ValueError):
            bad.validated()

    def test_every_sendable_type_is_accepted(self):
        assert SENDABLE_ORDER_TYPES == {OrderType.LIMIT, OrderType.MARKET, OrderType.STOP}
        assert entry().problems() == []

    def test_delta_outside_zero_to_one_is_refused(self):
        assert any("delta" in p for p in entry(delta=0.0).problems())
        assert any("delta" in p for p in entry(delta=1.5).problems())
        assert entry(delta=-0.30).problems() == []   # sign lives in the right, not the delta

    def test_validated_raises_naming_the_intent_and_every_problem(self):
        with pytest.raises(ValueError) as exc:
            OrderIntent("", "nope", Side.BUY_TO_OPEN, 0).validated()
        message = str(exc.value)
        assert "intent_id" in message and "OCC" in message and "qty" in message


class TestDerived:
    def test_is_entry_follows_the_side(self):
        assert entry().is_entry
        assert not OrderIntent("t", CALL, Side.SELL_TO_CLOSE, 1,
                               order_type=OrderType.MARKET).is_entry

    def test_max_cost_is_the_limit_times_the_multiplier(self):
        assert entry(limit=2.10, qty=1).max_cost_usd == 210.0
        assert entry(limit=2.10, qty=3).max_cost_usd == 630.0

    def test_a_market_order_has_no_stated_maximum(self):
        assert OrderIntent("t", CALL, Side.SELL_TO_CLOSE, 1,
                           order_type=OrderType.MARKET).max_cost_usd is None


class TestWireForm:
    def test_round_trips_through_a_dict(self):
        original = entry(intent_id="rt-1", symbol=PUT, limit=1.85, delta=-0.28)
        assert OrderIntent.from_dict(original.to_dict()) == original

    def test_enums_serialise_as_their_strings(self):
        d = entry().to_dict()
        assert d["side"] == "BUY_TO_OPEN" and d["order_type"] == "LIMIT"

    def test_from_dict_accepts_numbers_as_strings(self):
        got = OrderIntent.from_dict({
            "intent_id": "s-1", "symbol": CALL, "side": "BUY_TO_OPEN",
            "qty": "1", "limit": "2.10", "stop_spx": "6368", "delta": "0.3",
        })
        assert (got.qty, got.limit, got.stop_spx, got.delta) == (1, 2.10, 6368.0, 0.3)
        assert got.problems() == []

    def test_an_unknown_side_is_a_value_error_not_a_default(self):
        with pytest.raises(ValueError, match="bad intent"):
            OrderIntent.from_dict({"intent_id": "s-1", "symbol": CALL, "side": "SELL_SHORT"})

    def test_a_missing_side_is_refused_rather_than_guessed(self):
        with pytest.raises(ValueError, match="bad intent"):
            OrderIntent.from_dict({"intent_id": "s-1", "symbol": CALL})
