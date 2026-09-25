"""The bracket — a take-profit beside the stop, one-cancels-the-other by the
service's own hand, a live editor for both, and cancel-and-re-price. [st-fn5y]

Steve, 2026-09-14: *"Future filled orders will result in resting 'take profit'
orders in addition to stoplosses. The screen should be a live editor allowing
an update to both trigger conditions."* And: *"Upon fill, api should create a
resting order at a 10x profit target."* The 10x here is on the PREMIUM basis
(fill × 10) — the standing assumption until he rules on premium-vs-risk.

What has to be true, and is asserted below, branch by branch:

* a fill rests both legs; a target that cannot be derived or rested is a
  warning (``target_unprotected``), never a fault, because the stop stands;
* when either leg fills the other comes off at once, and a cancel that finds
  the other leg already filled books it and journals the short as
  ``oversold``;
* every close the service sends takes both legs off first and puts both back
  on every failure branch; a partial exit resizes both; flatten pulls both;
* ``adjust`` moves either leg by cancel-then-rest, refuses off-grid prices,
  a stop not below the bid, a target not above it, a stop wider than the
  day's headroom, and a leg that filled before it could move;
* a restart rebuilds the target from the journal like the stop;
* the paper book fills a resting sell limit at the bid once the bid reaches
  it, attributable to that order;
* the page carries the target row, the UPDATE form, and CANCEL AND RE-PRICE
  that brings the form back priced from the selection the entry came from.
"""

from __future__ import annotations

import json

import httpx
import pytest

from execd.api import create_app
from execd.bounds import Bounds
from execd.broker import BrokerError, MockBroker, OrderResult, OrderStatus
from execd.intent import OrderIntent, OrderType, Side
from execd.paper import PaperBroker
from execd.service import ExecService, Refused, ServiceConfig
from execd.stops import take_profit_price

from .conftest import CALL, PUT, SPX_NOW, entry, exit_intent, page_send, schwab_chain_maps
from .conftest import same_origin  # noqa: E402

#: the conftest entry with a two-point SPX stop at 0.30 delta: fill 2.10,
#: stop 1.50, target 21.00 on the premium basis
NEAR_STOP = SPX_NOW - 2.0
TRIGGER = NEAR_STOP - 0.5


def sells(broker: MockBroker) -> list[dict]:
    return [kw for kw in broker.calls_to("place")
            if kw.get("side") == "SELL_TO_CLOSE" and kw.get("order_type") == "MARKET"]


def legs(broker: MockBroker, symbol: str = CALL) -> dict[str, list[OrderResult]]:
    working = broker.working_orders(symbol)
    return {"stop": [o for o in working if o.order_type is OrderType.STOP],
            "target": [o for o in working if o.order_type is OrderType.LIMIT
                       and o.side is Side.SELL_TO_CLOSE]}


@pytest.fixture
def holding(armed: ExecService):
    """An armed service holding one fill at 2.10 with a 1.50 stop and a
    21.00 target resting."""
    out = armed.place(entry(intent_id="br-1", stop_spx=NEAR_STOP, delta=0.30))
    assert out["order"]["status"] == "FILLED"
    return armed


def pos_of(svc: ExecService) -> dict:
    return svc.status()["positions"][0]


# ── the arithmetic ───────────────────────────────────────────────────────

class TestTakeProfitPrice:
    def test_premium_basis_is_fill_times_the_multiple_on_the_tick(self):
        assert take_profit_price(2.10, 10.0) == 21.00
        assert take_profit_price(0.35, 10.0) == 3.50
        assert take_profit_price(0.27, 10.0) == 2.70

    def test_it_rounds_up_onto_the_grid_in_force_at_the_target(self):
        assert take_profit_price(0.283, 10.0) == 2.85       # 2.83 → 0.05 grid below $3
        assert take_profit_price(0.301, 10.0) == 3.10       # 3.01 → 0.10 grid at $3+
        assert take_profit_price(2.10, 1.5) == 3.20         # 3.15 → 3.20

    def test_risk_basis_is_fill_plus_the_multiple_times_the_distance_to_the_stop(self):
        assert take_profit_price(2.10, 10.0, "risk", stop_price=1.50) == 8.10
        assert take_profit_price(2.10, 1.0, "risk", stop_price=1.50) == 2.70

    @pytest.mark.parametrize("kwargs, match", [
        (dict(fill_px=0, multiple=10), "positive"),
        (dict(fill_px=2.10, multiple=0), "multiple"),
        (dict(fill_px=2.10, multiple=10, basis="risk"), "needs a resting stop"),
        (dict(fill_px=2.10, multiple=10, basis="risk", stop_price=2.10), "not below"),
        (dict(fill_px=2.10, multiple=10, basis="mid"), "basis"),
        (dict(fill_px=2.10, multiple=1.0), "not above"),
    ])
    def test_inputs_that_cannot_make_a_target_raise(self, kwargs, match):
        with pytest.raises(ValueError, match=match):
            take_profit_price(**kwargs)


# ── A. the target on the fill ────────────────────────────────────────────

class TestTheTargetRestsOnTheFill:
    def test_a_fill_rests_a_stop_and_a_target(self, holding, broker):
        out = holding.journal.find("br-1")
        assert [e["event"] for e in out][-3:] == ["filled", "stop_placed", "target_placed"]
        p = pos_of(holding)
        assert (p["stop_price"], p["target_price"]) == (1.50, 21.00)
        assert p["stop_order_id"] and p["target_order_id"]
        assert p["stop_order_id"] != p["target_order_id"]
        resting = legs(broker)
        assert len(resting["stop"]) == 1 and len(resting["target"]) == 1
        assert resting["target"][0].price == 21.00 and resting["target"][0].qty == 1

    def test_the_target_line_carries_the_basis_and_the_multiple(self, holding):
        line = holding.journal.events("target_placed")[0]
        assert line["target_price"] == 21.00 and line["basis"] == "premium"
        assert line["multiple"] == 10.0 and line["kind"] == "entry"
        assert line["reward_usd"] == 1890.0 and line["order_id"]

    def test_the_place_answer_carries_the_target_order(self, armed):
        out = armed.place(entry(intent_id="br-2", stop_spx=NEAR_STOP, delta=0.30))
        assert out["target_order"]["order_type"] == "LIMIT"
        assert out["target_order"]["side"] == "SELL_TO_CLOSE"
        assert out["target_order"]["price"] == 21.00
        assert out["target_order"]["status"] == "WORKING"

    def test_the_risk_basis_multiplies_the_distance_to_the_stop(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha",
                               bounds=Bounds(take_profit_basis="risk", take_profit_multiple=10.0))
        svc = ExecService(broker, config, clock=clock)
        svc.unlock({"token": "x"})
        svc.place(entry(intent_id="br-3", stop_spx=NEAR_STOP, delta=0.30))
        assert pos_of(svc)["target_price"] == 8.10                # 2.10 + 10 × 0.60
        assert svc.journal.events("target_placed")[0]["basis"] == "risk"

    def test_a_broker_that_refuses_the_target_is_a_warning_not_a_fault(
            self, armed, broker, monkeypatch):
        real_place = broker.place

        def place(intent):
            if intent.order_type is OrderType.LIMIT and intent.side is Side.SELL_TO_CLOSE:
                raise BrokerError("no sell limits today")
            return real_place(intent)

        monkeypatch.setattr(broker, "place", place)
        out = armed.place(entry(intent_id="br-4", stop_spx=NEAR_STOP, delta=0.30))
        assert out["order"]["status"] == "FILLED"
        assert out["stop_order"]["status"] == "WORKING"          # the protection stands
        assert out["target_order"] is None
        p = pos_of(armed)
        assert p["stop_order_id"] and p["target_order_id"] is None and p["target_price"] is None
        line = armed.journal.events("target_unprotected")[0]
        assert "no sell limits today" in line["detail"] and line["target_price"] == 21.00
        assert not armed.journal.events("stop_unprotected")

    def test_a_target_the_broker_rejects_is_journaled_with_its_order(
            self, armed, broker, monkeypatch):
        real_place = broker.place

        def place(intent):
            if intent.order_type is OrderType.LIMIT and intent.side is Side.SELL_TO_CLOSE:
                broker.reject_next = "price too far from the market"
            return real_place(intent)

        monkeypatch.setattr(broker, "place", place)
        armed.place(entry(intent_id="br-5", stop_spx=NEAR_STOP, delta=0.30))
        line = armed.journal.events("target_unprotected")[0]
        assert "rejected" in line["detail"] and line["order_id"]
        assert pos_of(armed)["target_order_id"] is None

    def test_a_working_entry_that_fills_later_gets_its_target_at_reconcile(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry(intent_id="br-6", stop_spx=NEAR_STOP, delta=0.30))
        broker.rest_limits = False
        broker.fill_resting(out["order"]["order_id"])
        armed.reconcile()
        p = pos_of(armed)
        assert p["stop_order_id"] and p["target_order_id"]
        assert p["target_price"] == 21.00

    def test_the_status_and_the_valuation_carry_the_target(self, holding):
        p = pos_of(holding)
        v = p["valuation"]
        assert v["at_target_usd"] == pytest.approx((21.00 - 2.10) * 100 - 1.30)
        assert v["at_stop_usd"] == pytest.approx((1.50 - 2.10) * 100 - 1.30)
        assert p["entry_spx"] == SPX_NOW

    def test_a_target_already_through_when_it_lands_is_the_exit(self, armed, broker):
        """The bid is above the target the moment the sell limit lands (a
        ten-cent option whose bid jumps to 0.30 as the 0.15 target lands). That fill is the close,
        booked as the target, and the stop comes off."""
        cheap = "SPXW  260826C06450000"
        broker.set_quote(cheap, bid=0.05, ask=0.10)
        armed.bounds = armed.config.bounds = Bounds(take_profit_multiple=1.2)
        real_place = broker.place

        def place(intent):
            if intent.order_type is OrderType.LIMIT and intent.side is Side.SELL_TO_CLOSE:
                broker.set_quote(cheap, bid=0.30, ask=0.32)      # the bid ran up
            return real_place(intent)

        broker.place = place
        out = armed.place(entry(intent_id="br-7", symbol=cheap, limit=0.10,
                                stop_spx=NEAR_STOP, delta=0.30))
        assert out["order"]["status"] == "FILLED"
        assert out["target_order"]["closed"]["reason"] == "target"
        assert armed.status()["positions"] == []
        assert armed.journal.events("target_placed")[0]["filled_at_once"] is True
        assert not broker.working_orders(cheap)                 # the stop came off


# ── B. one cancels the other ─────────────────────────────────────────────

class TestOneCancelsTheOther:
    def test_the_stop_filling_cancels_the_target(self, holding, broker, clock):
        p = pos_of(holding)
        clock.advance(minutes=1)
        broker.fill_resting(p["stop_order_id"])
        out = holding.poll_fills()
        assert out["picked_up"][0]["reason"] == "protective-stop"
        assert out["picked_up"][0]["pnl_usd"] == -60.0
        assert broker._orders[p["target_order_id"]].status is OrderStatus.CANCELED
        assert holding.status()["positions"] == []
        closed = holding.journal.events("closed")[-1]
        assert closed["kind"] == "protective-stop" and closed["reason"] == "resting-stop"

    def test_the_target_filling_cancels_the_stop_and_books_the_win(self, holding, broker, clock):
        p = pos_of(holding)
        clock.advance(minutes=1)
        broker.fill_resting(p["target_order_id"])
        out = holding.poll_fills()
        assert out["picked_up"][0]["reason"] == "target"
        assert out["picked_up"][0]["exit_price"] == 21.00
        assert out["picked_up"][0]["pnl_usd"] == 1890.0
        assert broker._orders[p["stop_order_id"]].status is OrderStatus.CANCELED
        assert holding.status()["positions"] == []
        closed = holding.journal.events("closed")[-1]
        assert closed["kind"] == "target" and closed["reason"] == "resting-target"
        assert closed["pnl_usd"] == 1890.0

    def test_the_other_leg_comes_off_before_the_close_is_booked(self, holding, broker, clock):
        p = pos_of(holding)
        clock.advance(minutes=1)
        broker.fill_resting(p["target_order_id"])
        holding.poll_fills()
        events = [e["event"] for e in holding.journal.read()]
        assert events.index("canceled") < events.index("closed")

    def test_both_legs_filled_is_booked_once_and_the_short_is_loud(self, holding, broker, clock):
        """The race lost on both sides: the stop filled, and before the cancel
        reached the target it filled too. One close is booked against what
        was held; the extra contract sold is ``oversold`` in the journal."""
        p = pos_of(holding)
        clock.advance(minutes=1)
        broker.fill_resting(p["stop_order_id"])
        broker.fill_resting(p["target_order_id"])
        out = holding.poll_fills()
        assert len(out["picked_up"]) == 1
        closed = holding.journal.events("closed")
        assert len(closed) == 1 and closed[0]["kind"] == "protective-stop"
        over = holding.journal.events("oversold")
        assert len(over) == 1 and over[0]["qty"] == 1 and over[0]["leg"] == "target"
        assert "bought back by hand" in over[0]["detail"]
        assert holding.status()["positions"] == []


class TestTheCloseTakesBothLegsOff:
    def test_both_cancels_precede_the_close(self, holding, broker):
        p = pos_of(holding)
        holding.observe(TRIGGER)
        names = [(n, kw) for n, kw in broker.calls]
        cancel_ids = [kw["order_id"] for n, kw in names if n == "cancel"]
        assert set(cancel_ids) >= {p["stop_order_id"], p["target_order_id"]}
        last_cancel = max(i for i, (n, _) in enumerate(names) if n == "cancel")
        close = min(i for i, (n, kw) in enumerate(names)
                    if n == "place" and kw.get("side") == "SELL_TO_CLOSE"
                    and kw.get("order_type") == "MARKET")
        assert last_cancel < close
        assert holding.status()["positions"] == []
        assert not broker.working_orders(CALL)

    def test_when_the_target_wins_the_race_no_close_is_sent(self, holding, broker):
        p = pos_of(holding)
        broker.fill_resting(p["target_order_id"])
        result = holding.observe(TRIGGER)
        assert result["fired"][0]["reason"] == "target"
        assert result["fired"][0]["closed"] is True
        assert result["fired"][0]["pnl_usd"] == 1890.0
        assert sells(broker) == []
        assert broker._orders[p["stop_order_id"]].status is OrderStatus.CANCELED
        assert holding.status()["positions"] == []

    def test_when_the_stop_wins_the_race_the_target_comes_off(self, holding, broker):
        p = pos_of(holding)
        broker.fill_resting(p["stop_order_id"])
        result = holding.observe(TRIGGER)
        assert result["fired"][0]["reason"] == "resting-stop"
        assert broker._orders[p["target_order_id"]].status is OrderStatus.CANCELED
        assert sells(broker) == []

    def test_a_rejected_close_puts_both_legs_back(self, holding, broker):
        before = pos_of(holding)
        broker.reject_next = "market closed"
        holding.observe(TRIGGER)
        after = pos_of(holding)
        assert after["stop_order_id"] and after["stop_order_id"] != before["stop_order_id"]
        assert after["target_order_id"] and after["target_order_id"] != before["target_order_id"]
        assert (after["stop_price"], after["target_price"]) == (1.50, 21.00)
        resting = legs(broker)
        assert len(resting["stop"]) == 1 and len(resting["target"]) == 1

    def test_a_broker_down_at_the_close_puts_both_legs_back(self, holding, broker, monkeypatch):
        real_place = broker.place

        def place(intent):
            if intent.order_type is OrderType.MARKET:
                raise BrokerError("connection reset")
            return real_place(intent)

        monkeypatch.setattr(broker, "place", place)
        result = holding.observe(TRIGGER)
        assert result["fired"][0]["closed"] is False
        resting = legs(broker)
        assert len(resting["stop"]) == 1 and len(resting["target"]) == 1

    def test_a_broker_down_at_the_target_cancel_sends_nothing_and_restores_the_stop(
            self, holding, broker, monkeypatch):
        p = pos_of(holding)
        real_cancel = broker.cancel

        def cancel(order_id):
            if order_id == p["target_order_id"]:
                raise BrokerError("connection reset")
            return real_cancel(order_id)

        monkeypatch.setattr(broker, "cancel", cancel)
        result = holding.observe(TRIGGER)
        assert result["fired"][0]["status"] == "DEFERRED"
        assert sells(broker) == []
        after = pos_of(holding)
        assert after["stop_order_id"] and after["stop_order_id"] != p["stop_order_id"]
        assert after["target_order_id"] == p["target_order_id"]     # still resting
        assert broker._orders[p["target_order_id"]].is_working
        assert broker._orders[after["stop_order_id"]].is_working

    def test_a_manual_full_exit_pulls_both_legs_first(self, holding, broker):
        p = pos_of(holding)
        out = holding.place(exit_intent(intent_id="br-x"))
        assert out["closed"]["closed"] is True
        assert broker._orders[p["stop_order_id"]].status is OrderStatus.CANCELED
        assert broker._orders[p["target_order_id"]].status is OrderStatus.CANCELED

    def test_a_manual_exit_finding_the_target_filled_sends_nothing(self, holding, broker, monkeypatch):
        """The fill lands between the reconcile that opens every place and
        the cancel: the cancel finds it. (The reconcile is stubbed here so
        the race is the cancel's to find — the reconcile's own path is the
        next test.)"""
        monkeypatch.setattr(holding, "reconcile", lambda: {})
        broker.fill_resting(pos_of(holding)["target_order_id"])
        out = holding.place(exit_intent(intent_id="br-late"))
        assert out["order"] is None
        assert out["closed"]["reason"] == "target"
        assert "take-profit had already filled" in out["note"]
        assert sells(broker) == []

    def test_a_manual_exit_after_the_target_filled_finds_it_already_booked(self, holding, broker):
        """The reconcile that opens every place reads the listing, finds the
        take-profit FILLED and books the close (st-vqmr); the exit then has
        nothing to close and is refused rather than sent."""
        broker.fill_resting(pos_of(holding)["target_order_id"])
        out = holding.place(exit_intent(intent_id="br-late"))
        assert out["order"] is None
        assert out["refused"]["bound"] == "qty" and "position of 0" in out["refused"]["reason"]
        closed = holding.journal.events("closed")[-1]
        assert closed["kind"] == "target" and closed["qty"] == 1
        assert holding.status()["positions"] == []
        assert sells(broker) == []

    def test_flatten_takes_both_legs_off(self, holding, broker):
        p = pos_of(holding)
        out = holding.flatten(reason="test")
        assert out["closed"][0]["closed"] is True
        # both legs came off BEFORE the close went on, so the settle found
        # nothing left to cancel — the cancels are in the broker's call log
        assert out["closed"][0]["stop_canceled"] is None
        assert out["closed"][0]["target_canceled"] is None
        assert not broker.working_orders(CALL)
        cancelled = {kw["order_id"] for kw in broker.calls_to("cancel")}
        assert {p["stop_order_id"], p["target_order_id"]} <= cancelled

    def test_a_cancelled_in_flight_close_puts_both_legs_back(self, holding, broker):
        broker.rest_market = True
        out = holding.observe(TRIGGER)
        assert legs(broker) == {"stop": [], "target": []}          # both off while it works
        holding.cancel(out["fired"][0]["order_id"])
        resting = legs(broker)
        assert len(resting["stop"]) == 1 and len(resting["target"]) == 1

    def test_a_close_the_broker_killed_puts_both_legs_back(self, holding, broker):
        broker.rest_market = True
        out = holding.observe(TRIGGER)
        broker.reject_resting(out["fired"][0]["order_id"], "killed at the exchange")
        holding.reconcile()
        resting = legs(broker)
        assert len(resting["stop"]) == 1 and len(resting["target"]) == 1


class TestPartialExitsResizeBoth:
    @pytest.fixture
    def two_lot(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha",
                               bounds=Bounds(qty_cap=2))
        svc = ExecService(broker, config, clock=clock)
        svc.unlock({"token": "x"})
        svc.place(entry(intent_id="two-1", qty=2, stop_spx=NEAR_STOP, delta=0.30))
        return svc

    def test_both_legs_are_sized_to_the_position(self, two_lot, broker):
        resting = legs(broker)
        assert resting["stop"][0].qty == 2 and resting["target"][0].qty == 2

    def test_a_partial_exit_replaces_both_at_the_smaller_size(self, two_lot, broker):
        broker.partial_fill_qty = 1
        out = two_lot.place(exit_intent(intent_id="two-1-x", qty=2))
        assert out["closed"]["remaining_qty"] == 1
        assert out["closed"]["stop_replaced"] and out["closed"]["target_replaced"]
        resting = legs(broker)
        assert len(resting["stop"]) == 1 and resting["stop"][0].qty == 1
        assert len(resting["target"]) == 1 and resting["target"][0].qty == 1
        assert resting["target"][0].price == 21.00
        assert two_lot.journal.events("target_placed")[-1]["kind"] == "resized"

    def test_a_partially_filled_target_leaves_a_resized_bracket_for_the_rest(
            self, two_lot, broker, clock):
        from dataclasses import replace
        p = pos_of(two_lot)
        clock.advance(minutes=1)
        broker._orders[p["target_order_id"]] = replace(broker._orders[p["target_order_id"]], qty=1)
        broker.fill_resting(p["target_order_id"])
        out = two_lot.poll_fills()
        assert out["picked_up"][0]["remaining_qty"] == 1
        resting = legs(broker)
        assert len(resting["stop"]) == 1 and resting["stop"][0].qty == 1
        assert len(resting["target"]) == 1 and resting["target"][0].qty == 1

    def test_a_size_the_broker_corrects_resizes_both(self, two_lot, broker):
        broker.set_position(CALL, qty=1, avg_price=2.10)
        two_lot.reconcile()
        assert two_lot.journal.events("position_corrected")
        resting = legs(broker)
        assert resting["stop"][0].qty == 1 and resting["target"][0].qty == 1


class TestCancelGuardsTheTarget:
    def test_cancelling_the_target_alone_is_refused(self, holding, broker):
        target_id = pos_of(holding)["target_order_id"]
        with pytest.raises(Refused) as exc:
            holding.cancel(target_id)
        assert exc.value.refusal.bound == "take_profit"
        assert broker._orders[target_id].is_working
        assert holding.journal.events("refused")[-1]["order_id"] == target_id

    def test_a_position_gone_elsewhere_pulls_both_legs(self, holding, broker, clock):
        from execd.service import POSITION_SETTLE_S
        p = pos_of(holding)
        broker._positions.clear()
        holding.reconcile()
        clock.advance(seconds=POSITION_SETTLE_S + 1)
        holding.reconcile()
        assert broker._orders[p["stop_order_id"]].status is OrderStatus.CANCELED
        assert broker._orders[p["target_order_id"]].status is OrderStatus.CANCELED


# ── C. the live editor ───────────────────────────────────────────────────

class TestAdjust:
    def test_both_legs_move_by_cancel_then_rest(self, holding, broker):
        before = pos_of(holding)
        out = holding.adjust(CALL, stop_price=1.80, target_price=25.00)
        assert out["refused"] is None
        assert out["stop"]["moved"] and out["target"]["moved"]
        assert (out["stop"]["old_price"], out["stop"]["new_price"]) == (1.50, 1.80)
        assert (out["target"]["old_price"], out["target"]["new_price"]) == (21.00, 25.00)
        after = pos_of(holding)
        assert (after["stop_price"], after["target_price"]) == (1.80, 25.00)
        assert after["stop_order_id"] != before["stop_order_id"]
        assert after["target_order_id"] != before["target_order_id"]
        assert broker._orders[before["stop_order_id"]].status is OrderStatus.CANCELED
        assert broker._orders[before["target_order_id"]].status is OrderStatus.CANCELED
        resting = legs(broker)
        assert resting["stop"][0].price == 1.80 and resting["target"][0].price == 25.00

    def test_the_moves_are_journaled_with_old_and_new(self, holding):
        holding.adjust(CALL, stop_price=1.80, target_price=25.00)
        s = holding.journal.events("stop_adjusted")[0]
        t = holding.journal.events("target_adjusted")[0]
        assert (s["old_price"], s["new_price"]) == (1.50, 1.80)
        assert (t["old_price"], t["new_price"]) == (21.00, 25.00)
        assert s["old_order_id"] != s["new_order_id"] and t["old_order_id"] != t["new_order_id"]
        assert s["bid"] == 2.00
        assert holding.journal.events("stop_placed")[-1]["kind"] == "adjusted"
        assert holding.journal.events("target_placed")[-1]["kind"] == "adjusted"

    def test_one_leg_alone_leaves_the_other_untouched(self, holding, broker):
        before = pos_of(holding)
        out = holding.adjust(CALL, target_price=30.00)
        assert out["stop"] is None and out["target"]["moved"]
        after = pos_of(holding)
        assert after["stop_order_id"] == before["stop_order_id"] and after["stop_price"] == 1.50
        assert after["target_price"] == 30.00

    def test_moving_the_stop_moves_the_spx_trigger_with_it(self, holding, broker):
        """The two stops stay one stop: the SPX level the loop watches is
        re-derived from the new option price through the entry's delta."""
        assert pos_of(holding)["stop_spx"] == NEAR_STOP
        out = holding.adjust(CALL, stop_price=1.80)
        # (2.10 − 1.80) / 0.30 = 1.0 point below the entry's SPX mark
        assert out["stop"]["stop_spx"] == SPX_NOW - 1.0
        assert pos_of(holding)["stop_spx"] == SPX_NOW - 1.0
        line = holding.journal.events("stop_adjusted")[0]
        assert (line["old_stop_spx"], line["new_stop_spx"]) == (NEAR_STOP, SPX_NOW - 1.0)
        assert holding.observe(SPX_NOW - 0.5)["fired"] == []
        assert holding.observe(SPX_NOW - 1.0)["fired"][0]["closed"] is True

    def test_a_put_stop_moves_the_trigger_the_other_way(self, armed):
        armed.place(entry(intent_id="br-p", symbol=PUT, limit=1.90,
                          stop_spx=SPX_NOW + 2.0, delta=0.30))
        assert pos_of(armed)["stop_price"] == 1.30                # 1.90 − 2 × 0.30
        out = armed.adjust(PUT, stop_price=1.60)              # (1.90 − 1.60)/0.30 = 1.0
        assert out["refused"] is None
        assert out["stop"]["stop_spx"] == SPX_NOW + 1.0
        assert armed.observe(SPX_NOW + 1.0)["fired"][0]["closed"] is True

    @pytest.mark.parametrize("kwargs, bound, words", [
        (dict(stop_price=1.83), "tick", "not on the 0.05 grid"),
        (dict(target_price=3.05), "tick", "not on the 0.10 grid"),
        (dict(stop_price=2.05), "bracket", "not below the 2.00 bid"),
        (dict(stop_price=2.00), "bracket", "not below the 2.00 bid"),
        (dict(target_price=1.95), "bracket", "not above the 2.00 bid"),
        (dict(target_price=2.00), "bracket", "not above the 2.00 bid"),
        (dict(stop_price=-1.0), "bracket", "positive"),
    ])
    def test_a_price_that_cannot_be_a_trigger_is_refused(self, holding, broker, kwargs, bound, words):
        before = pos_of(holding)
        out = holding.adjust(CALL, **kwargs)
        assert out["refused"]["bound"] == bound and words in out["refused"]["reason"]
        after = pos_of(holding)
        assert (after["stop_order_id"], after["target_order_id"]) == \
            (before["stop_order_id"], before["target_order_id"])
        assert broker.calls_to("cancel") == []
        assert holding.journal.events("refused")[-1]["kind"] == "adjust"

    def test_a_stop_moved_wide_is_his_to_move(self, holding):
        """No daily ceiling on an adjusted stop (co-8mb1z): a stop at 0.05
        after a $350 loss today is allowed."""
        holding.journal.record("closed", symbol="other", pnl_usd=-350.0)
        assert holding.adjust(CALL, stop_price=0.05)["refused"] is None
        assert pos_of(holding)["stop_price"] == 0.05

    def test_tightening_the_stop_after_a_loss_is_allowed(self, holding):
        holding.journal.record("closed", symbol="other", pnl_usd=-480.0)
        assert holding.adjust(CALL, stop_price=1.95)["refused"] is None

    def test_no_position_is_a_refusal(self, holding):
        out = holding.adjust(PUT, stop_price=1.00)
        assert out["refused"]["bound"] == "position"

    def test_nothing_to_adjust_is_a_value_error(self, holding):
        with pytest.raises(ValueError, match="stop_price, a target_price, or both"):
            holding.adjust(CALL)

    def test_a_close_in_flight_refuses_the_adjust(self, holding, broker):
        broker.rest_market = True
        holding.observe(TRIGGER)
        out = holding.adjust(CALL, stop_price=1.80)
        assert out["refused"]["bound"] == "exit_in_flight"

    def test_a_locked_service_refuses(self, holding):
        holding.lock()
        out = holding.adjust(CALL, stop_price=1.80)
        assert out["refused"]["bound"] == "armed"

    def test_adjust_is_legal_while_stopped(self, holding):
        holding.stop()
        assert holding.adjust(CALL, target_price=25.00)["refused"] is None

    def test_a_stop_that_filled_before_it_could_move_is_booked_and_refused(self, holding, broker):
        p = pos_of(holding)
        broker.fill_resting(p["stop_order_id"])
        out = holding.adjust(CALL, stop_price=1.80, target_price=25.00)
        assert out["refused"]["bound"] == "filled"
        assert "stop filled at 1.50" in out["refused"]["reason"]
        assert out["closed"]["reason"] == "resting-stop" and out["closed"]["closed"] is True
        assert out["target"] is None                                # never reached
        assert holding.status()["positions"] == []
        assert broker._orders[p["target_order_id"]].status is OrderStatus.CANCELED
        assert holding.journal.events("closed")[-1]["kind"] == "resting-stop"

    def test_a_target_that_filled_before_it_could_move_is_booked_and_refused(self, holding, broker):
        p = pos_of(holding)
        broker.fill_resting(p["target_order_id"])
        out = holding.adjust(CALL, target_price=25.00)
        assert out["refused"]["bound"] == "filled"
        assert "take-profit filled at 21.00" in out["refused"]["reason"]
        assert out["closed"]["reason"] == "target" and out["closed"]["pnl_usd"] == 1890.0
        assert holding.status()["positions"] == []
        assert broker._orders[p["stop_order_id"]].status is OrderStatus.CANCELED

    def test_a_broker_down_at_the_cancel_changes_nothing_and_raises(self, holding, broker):
        before = pos_of(holding)
        broker.fail_next = "connection reset"        # the quote read fails first
        with pytest.raises(BrokerError):
            holding.adjust(CALL, stop_price=1.80)
        after = pos_of(holding)
        assert after["stop_order_id"] == before["stop_order_id"]

    def test_a_new_stop_the_broker_will_not_rest_brings_the_old_one_back(
            self, holding, broker, monkeypatch):
        before = pos_of(holding)
        real_place = broker.place

        def place(intent):
            if intent.order_type is OrderType.STOP and intent.stop_price == 1.80:
                raise BrokerError("no")
            return real_place(intent)

        monkeypatch.setattr(broker, "place", place)
        out = holding.adjust(CALL, stop_price=1.80)
        assert out["refused"] is None and out["stop"]["moved"] is False
        assert "old stop is back" in out["stop"]["error"]
        after = pos_of(holding)
        assert after["stop_price"] == 1.50 and after["stop_spx"] == NEAR_STOP
        assert after["stop_order_id"] and after["stop_order_id"] != before["stop_order_id"]
        assert broker._orders[after["stop_order_id"]].is_working
        assert not holding.journal.events("stop_adjusted")
        assert holding.journal.events("stop_placed")[-1]["kind"] == "restored"


class TestAdjustOverTheApi:
    @pytest.fixture
    def client(self, holding):
        return create_app(holding).test_client()

    @staticmethod
    def post(client, payload):
        return client.post("/adjust", data=json.dumps(payload), content_type="application/json")

    def test_a_good_adjust_is_a_200(self, client, holding):
        r = self.post(client, {"symbol": CALL, "stop_price": 1.80, "target_price": "25.0"})
        assert r.status_code == 200
        assert r.json["stop"]["moved"] and r.json["target"]["new_price"] == 25.0
        assert pos_of(holding)["stop_price"] == 1.80

    def test_a_refusal_is_a_409_naming_the_bound(self, client):
        r = self.post(client, {"symbol": CALL, "stop_price": 2.50})
        assert r.status_code == 409 and r.json["refused"]["bound"] == "bracket"

    @pytest.mark.parametrize("payload", [
        {}, {"stop_price": 1.80}, {"symbol": CALL, "stop_price": "one eighty"},
        {"symbol": CALL, "target_price": True},
    ])
    def test_a_malformed_request_is_a_400(self, client, payload):
        r = self.post(client, payload)
        assert r.status_code == 400 and r.json["error"] == "bad_request"

    def test_nothing_to_adjust_is_a_400(self, client):
        assert self.post(client, {"symbol": CALL}).status_code == 400

    def test_a_broker_failure_is_a_502(self, client, broker):
        broker.fail_next = "down"
        r = self.post(client, {"symbol": CALL, "stop_price": 1.80})
        assert r.status_code == 502 and r.json["error"] == "broker"

    def test_a_locked_service_is_a_409(self, holding):
        holding.lock()
        client = create_app(holding).test_client()
        r = self.post(client, {"symbol": CALL, "stop_price": 1.80})
        assert r.status_code == 409 and r.json["refused"]["bound"] == "armed"

    def test_adjust_refuses_a_get(self, client):
        assert client.get("/adjust").status_code == 405


# ── recovery ─────────────────────────────────────────────────────────────

class TestRecovery:
    def test_a_restart_rebuilds_the_target_like_the_stop(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="rec-1", stop_spx=NEAR_STOP, delta=0.30))
        before = pos_of(first)

        second = ExecService(broker, config, clock=clock)
        after = pos_of(second)
        assert after["target_order_id"] == before["target_order_id"]
        assert after["target_price"] == 21.00
        assert after["stop_order_id"] == before["stop_order_id"]
        assert after["entry_spx"] == SPX_NOW

    def test_a_restart_after_an_adjust_carries_the_new_legs(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="rec-2", stop_spx=NEAR_STOP, delta=0.30))
        first.adjust(CALL, stop_price=1.80, target_price=25.00)
        moved = pos_of(first)

        second = ExecService(broker, config, clock=clock)
        after = pos_of(second)
        assert (after["stop_order_id"], after["target_order_id"]) == \
            (moved["stop_order_id"], moved["target_order_id"])
        assert (after["stop_price"], after["target_price"]) == (1.80, 25.00)
        assert after["stop_spx"] == SPX_NOW - 1.0
        second.unlock({"token": "x"})
        assert second.observe(SPX_NOW - 1.0)["fired"][0]["closed"] is True

    def test_legs_that_were_off_for_a_close_in_flight_do_not_come_back_as_ids(
            self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="rec-3", stop_spx=NEAR_STOP, delta=0.30))
        broker.rest_market = True
        first.observe(TRIGGER)

        second = ExecService(broker, config, clock=clock)
        p = pos_of(second)
        assert p["exit_order_id"] and p["stop_order_id"] is None and p["target_order_id"] is None
        assert (p["stop_price"], p["target_price"]) == (1.50, 21.00)   # the prices survive

    def test_a_target_that_filled_as_it_landed_is_not_resurrected(self, armed, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        cheap = "SPXW  260826C06450000"
        broker.set_quote(cheap, bid=0.05, ask=0.10)
        first = ExecService(broker, config, clock=clock)
        first.bounds = first.config.bounds = Bounds(take_profit_multiple=1.2)
        first.unlock({"token": "x"})
        real_place = broker.place

        def place(intent):
            if intent.order_type is OrderType.LIMIT and intent.side is Side.SELL_TO_CLOSE:
                broker.set_quote(cheap, bid=0.30, ask=0.32)
            return real_place(intent)

        broker.place = place
        first.place(entry(intent_id="rec-4", symbol=cheap, limit=0.10,
                          stop_spx=NEAR_STOP, delta=0.30))
        broker.place = real_place
        second = ExecService(broker, config, clock=clock)
        assert second.status()["positions"] == []


# ── D. no attempts rule (removed 2026-09-24, co-8mb1z) ────────────────────

class TestNoAttemptsRule:
    def test_losses_never_run_out(self, armed, broker):
        for i in range(12):                                     # twelve losers
            assert armed.place(entry(intent_id=f"l-{i}", stop_spx=NEAR_STOP,
                                     delta=0.30))["refused"] is None
            armed.flatten(reason="test")
        assert "attempts_left" not in armed.status()["day"]


# ── E. cancel and re-price ───────────────────────────────────────────────

class TestCancelAndRePrice:
    def test_a_working_entry_from_the_api_carries_no_page_query(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry(intent_id="cq-1"))
        assert out["working"]["page_query"] is None

    def test_place_records_the_page_query_on_the_working_line_and_recovers_it(
            self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        broker.rest_limits = True
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        query = {"side": "call", "expiry": "2026-08-26", "delta": "0.3", "budget": "150"}
        out = first.place(entry(intent_id="cq-2"), page_query=query)
        assert out["working"]["page_query"] == query
        assert first.journal.events("working")[0]["page_query"] == query
        second = ExecService(broker, config, clock=clock)
        assert second.status()["working"][0]["page_query"] == query

    def test_the_query_never_reaches_the_broker_or_the_intent(self, armed, broker):
        broker.rest_limits = True
        armed.place(entry(intent_id="cq-3"), page_query={"side": "call"})
        assert "page_query" not in armed.journal.find("cq-3")[0]["intent"]
        assert all("page_query" not in kw for kw in broker.calls_to("place"))


# ── F. the paper book ────────────────────────────────────────────────────

class TestPaperTarget:
    @pytest.fixture
    def live(self, clock):
        b = MockBroker(clock=clock)
        b.set_quote(CALL, bid=2.00, ask=2.10)
        b.set_quote("$SPX", bid=SPX_NOW - 0.25, ask=SPX_NOW + 0.25, last=SPX_NOW)
        return b

    @pytest.fixture
    def paper(self, live, clock, tmp_path):
        return PaperBroker(live, book_path=tmp_path / "paper-book.json", clock=clock)

    def test_a_resting_sell_limit_fills_at_the_bid_once_the_bid_reaches_it(self, paper, live, clock):
        paper.place(entry("pt-1"))
        target = paper.place(OrderIntent("pt-1-t", CALL, Side.SELL_TO_CLOSE, 1,
                                         order_type=OrderType.LIMIT, limit=2.50))
        assert target.status is OrderStatus.WORKING and target.price == 2.50
        since = clock()
        clock.advance(seconds=5)
        live.set_quote(CALL, bid=2.45, ask=2.55)
        assert paper.fills_since(since) == []                   # not there yet
        live.set_quote(CALL, bid=2.55, ask=2.65)
        fills = paper.fills_since(since)
        assert len(fills) == 1
        assert fills[0].order_id == target.order_id and fills[0].price == 2.55
        assert fills[0].side is Side.SELL_TO_CLOSE
        assert paper.positions() == []
        assert paper.orders()[-1].status is OrderStatus.FILLED

    def test_a_marketable_sell_limit_fills_at_once_at_the_bid(self, paper):
        paper.place(entry("pt-2"))
        o = paper.place(OrderIntent("pt-2-t", CALL, Side.SELL_TO_CLOSE, 1,
                                    order_type=OrderType.LIMIT, limit=1.90))
        assert o.status is OrderStatus.FILLED and o.fill_price == 2.00

    def test_the_target_fills_in_the_book_and_the_sweep_books_it_as_the_target(
            self, paper, live, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha", mode="paper")
        svc = ExecService(paper, config, clock=clock)
        svc.unlock({"token": "x"})
        out = svc.place(entry("pt-3", stop_spx=NEAR_STOP, delta=0.30))
        assert out["stop_order"]["order_id"] == "paper-0002"
        assert out["target_order"]["order_id"] == "paper-0003"
        assert out["target_order"]["price"] == 21.00
        clock.advance(seconds=5)
        live.set_quote(CALL, bid=21.50, ask=21.70)
        r = svc.poll_fills()
        assert len(r["picked_up"]) == 1
        assert r["picked_up"][0]["order_id"] == "paper-0003"
        assert r["picked_up"][0]["reason"] == "target"
        assert r["picked_up"][0]["pnl_usd"] == 1940.0             # (21.50 − 2.10) × 100
        assert svc.status()["positions"] == []
        book = {o.order_id: o.status for o in paper.orders()}
        assert book["paper-0002"] is OrderStatus.CANCELED         # the stop came off
        assert [c[0] for c in live.calls if c[0] in ("place", "cancel")] == []

    def test_the_stop_fills_in_the_book_and_the_target_comes_off(self, paper, live, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha", mode="paper")
        svc = ExecService(paper, config, clock=clock)
        svc.unlock({"token": "x"})
        svc.place(entry("pt-4", stop_spx=NEAR_STOP, delta=0.30))
        clock.advance(seconds=5)
        live.set_quote(CALL, bid=1.45, ask=1.55)
        r = svc.poll_fills()
        assert r["picked_up"][0]["reason"] == "protective-stop"
        book = {o.order_id: o.status for o in paper.orders()}
        assert book["paper-0003"] is OrderStatus.CANCELED


# ── the page ─────────────────────────────────────────────────────────────

@pytest.fixture
def page(armed: ExecService, broker, clock, tmp_path):
    from execd.page import CredentialFile, create_page
    from execd.vault import Vault
    from .test_page import CALLBACK, PASS, Schwab, market_payload, vault_payload

    broker.set_chain("SPXW", schwab_chain_maps())
    vault = Vault(tmp_path / "vault.json")
    vault.store(vault_payload(), PASS)
    mfile = tmp_path / "market.json"
    mfile.write_text(json.dumps(market_payload()))
    market = CredentialFile(mfile)
    market.load()
    app = create_page(armed, vault=vault, market=market, callback_url=CALLBACK,
                      http_client=httpx.Client(base_url="https://api.schwabapi.com",
                                               transport=httpx.MockTransport(Schwab())),
                      clock=clock)
    app.config["TESTING"] = True
    return same_origin(app.test_client())


def text(r) -> str:
    return r.get_data(as_text=True)


class TestThePage:
    def test_the_position_card_shows_the_target_and_the_editor(self, page, holding):
        body = text(page.get("/exec/order"))
        assert "FILLED" in body and "NET NOW" in body
        assert "value='21.00'" in body and "value='1.50'" in body
        assert "action='/exec/order/adjust'" in body and ">SET<" in body
        assert "name=stop inputmode=decimal enterkeyhint=go autocomplete=off value='1.50'" in body
        assert "name=target inputmode=decimal enterkeyhint=go autocomplete=off value='21.00'" in body
        assert f"name=symbol value='{CALL}'" in body

    def test_the_state_json_carries_the_target_and_the_editor_fragment(self, page, holding):
        s = page.get(f"/exec/order/state?symbol={CALL}").json
        p = s["positions"][0]
        assert p["target_price"] == 21.00 and p["target_order_id"]
        assert p["valuation"]["at_target_usd"] == pytest.approx((21.00 - 2.10) * 100 - 1.30)
        assert ">UPDATE<" in s["position_html"] and s["working"] == []

    def test_update_moves_both_and_says_so(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "1.80",
                                                  "target_price": "25"})
        assert r.status_code == 303
        landing = text(page.get(r.headers["Location"]))
        assert "Stop moved from 1.50 to 1.80" in landing
        assert "Target moved from 21.00 to 25.00" in landing
        assert "value='1.80'" in landing and "value='25.00'" in landing
        assert (pos_of(holding)["stop_price"], pos_of(holding)["target_price"]) == (1.80, 25.00)

    def test_update_with_one_field_blank_moves_only_the_other(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "",
                                                  "target_price": "30.00"})
        landing = text(page.get(r.headers["Location"]))
        assert "Target moved" in landing and "Stop moved" not in landing
        assert pos_of(holding)["stop_price"] == 1.50

    def test_a_refused_update_says_why_and_changes_nothing(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "2.50"})
        landing = text(page.get(r.headers["Location"]))
        assert "Refused (bracket)" in landing and "not below the 2.00 bid" in landing
        assert pos_of(holding)["stop_price"] == 1.50

    def test_a_number_that_is_not_one_is_refused_in_words(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "one"})
        assert "Not updated" in text(page.get(r.headers["Location"]))

    def test_nothing_entered_is_nothing_updated(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL})
        assert "Nothing to update" in text(page.get(r.headers["Location"]))

    def test_the_editor_is_absent_while_a_close_is_in_flight(self, page, holding, broker):
        broker.rest_market = True
        holding.observe(TRIGGER)
        body = text(page.get("/exec/order"))
        assert "SELLING" in body and "FLATTEN AGAIN" in body and ">SET<" not in body

    def test_cancel_and_re_price_brings_the_form_back_priced_from_the_selection(
            self, page, armed, broker):
        broker.rest_limits = True
        r = page_send(page, {"side": "call", "delta": "0.3", "lots": "1"})
        landing = text(page.get(r.headers["Location"]))
        assert "not filled yet" in landing and "the bracket rests when it fills" in landing
        assert "WORKING" in landing and "CANCEL AND RE-PRICE" in landing
        assert "action='/exec/order/cancel'" in landing
        w = armed.status()["working"][0]
        assert w["page_query"] == {"side": "call", "expiry": "2026-08-26", "delta": "0.3"}
        assert armed.journal.events("working")[0]["page_query"] == w["page_query"]

        r = page.post("/exec/order/cancel", data={"order_id": w["order_id"]})
        assert r.status_code == 303
        where = r.headers["Location"]
        assert "side=call" in where and "delta=0.3" in where and "budget" not in where
        assert "expiry=2026-08-26" in where
        landing = text(page.get(where))
        assert f"Cancelled {w['order_id']}" in landing
        assert "data-stage=working" not in landing
        assert ">SEND<" in landing and ">6400<" in landing.split("<tr class='chosen'>")[1].split("</tr>")[0]
        assert armed.status()["working"] == []
        assert armed.journal.events("entry_resolved")[-1]["outcome"] == "canceled"
        assert armed.status()["day"]["open_positions"] == 0

    def test_cancelling_an_entry_the_desk_sent_lands_on_the_bare_form(self, page, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry(intent_id="desk-1"))
        r = page.post("/exec/order/cancel", data={"order_id": out["order"]["order_id"]})
        where = r.headers["Location"]
        assert where.startswith("/exec/order?") and "side=" not in where
        assert armed.status()["working"] == []

    def test_the_working_screen_asks_the_broker_rather_than_believing_itself(
            self, page, armed, broker):
        """Steve, 2026-09-18, on reading the first ticket back: "that would
        mean i was looking at 'waiting for a fill' after the fill had
        executed". In paper it could not happen — the book has no clock and
        only fills when read — but live it can, because the watcher
        reconciles every 5 s and this poll paints every 3 s. A screen that
        says "not filled yet" about an order that is gone is a CANCEL aimed
        at nothing, so the poll reconciles while anything is working. [st-jdg5]"""
        broker.rest_limits = True
        page_send(page, {"side": "call", "delta": "0.3"})
        w = armed.status()["working"][0]
        # the broker fills it and tells nobody, the way Schwab does
        broker.fill_resting(w["order_id"])
        assert armed.status()["working"], "the service has not noticed yet"

        j = page.get(f"/exec/order/state?symbol={CALL}&side=call&delta=0.3").json
        assert j["working"] == [], "the poll still believed its own stale state"
        assert j["positions"] and j["positions"][0]["stop_order_id"]
        assert j["panel_stage"] == "filled"

    def test_an_unconfirmed_cancel_does_not_re_prime_the_form(self, page, armed, broker):
        """A cancel the broker has taken but not finished (PENDING_CANCEL at
        Schwab) leaves an order that can still fill. The page must not say
        "Cancelled" and must not come back priced for another send, because
        re-priming the form beside a live order is how one order becomes two.
        The working card stays, so he can ask again. [st-jdg5]"""
        broker.rest_limits = True
        r = page_send(page, {"side": "call", "delta": "0.3"})
        w = armed.status()["working"][0]
        broker.cancel_pending = True

        r = page.post("/exec/order/cancel", data={"order_id": w["order_id"]})
        where = r.headers["Location"]
        assert "side=call" not in where, "the form was re-primed beside a live order"
        landing = text(page.get(where))
        assert "Not confirmed" in landing and "can still fill" in landing
        assert "Cancelled" not in landing
        assert "data-stage=working" in landing and "CANCEL AND RE-PRICE" in landing
        assert [x["order_id"] for x in armed.status()["working"]] == [w["order_id"]]

    def test_a_cancel_that_lost_the_race_says_the_position_is_open(
            self, page, armed, broker):
        broker.rest_limits = True
        page_send(page, {"side": "call", "delta": "0.3"})
        w = armed.status()["working"][0]
        broker.fill_resting(w["order_id"])

        r = page.post("/exec/order/cancel", data={"order_id": w["order_id"]})
        landing = text(page.get(r.headers["Location"]))
        assert "Too late" in landing and "filled before the cancel" in landing
        assert "Cancelled" not in landing
        # and it is a proper position: the bracket rested, nothing adopted
        pos = armed.status()["positions"]
        assert len(pos) == 1 and pos[0]["stop_order_id"] and pos[0]["target_order_id"]

    def test_cancelling_a_bracket_leg_from_the_page_is_refused(self, page, holding):
        target_id = pos_of(holding)["target_order_id"]
        r = page.post("/exec/order/cancel", data={"order_id": target_id})
        assert "Refused (take_profit)" in text(page.get(r.headers["Location"]))
        assert pos_of(holding)["target_order_id"] == target_id

    def test_the_page_has_no_explanatory_text_under_the_bracket_controls(self, page, holding):
        body = text(page.get("/exec/order"))
        form = body.split("action='/exec/order/adjust'")[1].split("</form>")[0]
        assert "<div class=k>" not in form

    def test_the_landing_message_names_the_bracket_after_a_fill(self, page, armed):
        r = page_send(page, {"side": "call", "delta": "0.3"})
        landing = text(page.get(r.headers["Location"]))
        assert "Protective stop resting" in landing and "Take-profit resting" in landing
        assert "at 21.00" in landing


# ── a cancel is an ask (2026-09-15 audit, findings 24, 28, 29; st-7ah8) ──

class TestCancelIsAnAsk:
    """The transport's cancel is a DELETE the broker acknowledges and works;
    the read that follows can say PENDING_CANCEL, which is an order the
    exchange still holds. Until 2026-09-15 ``_pull_leg`` booked every
    non-FILLED answer as "the leg is off", so the market close went out
    beside a live stop, both sold, and the short was invisible."""

    def test_a_pending_cancel_defers_the_close_and_keeps_the_stop(self, holding, broker):
        broker.cancel_pending = True
        out = holding.observe(NEAR_STOP - 1)
        fired = out["fired"][0]
        assert fired["status"] == "DEFERRED" and fired["closed"] is False
        assert sells(broker) == []                         # nothing sent beside a live stop
        assert pos_of(holding)["stop_order_id"] is not None
        assert holding.journal.events("cancel_pending")
        assert legs(broker)["stop"]                        # still resting at the broker

    def test_once_the_cancel_is_done_the_close_goes_out(self, holding, broker):
        broker.cancel_pending = True
        holding.observe(NEAR_STOP - 1)
        stop_id = pos_of(holding)["stop_order_id"]
        broker.cancel_pending = False
        broker.resolve_pending_cancel(stop_id)
        out = holding.observe(NEAR_STOP - 1)
        assert out["fired"][0]["closed"] is True
        assert len(sells(broker)) == 1
        assert holding.status()["positions"] == []

    def test_a_leg_left_behind_by_a_close_is_carried_as_loose_until_reconcile_sees_it_off(
            self, holding, broker, clock):
        """The stop fills at the broker; the target's cancel is only
        acknowledged. The close is booked, the position dropped — and the
        target is NOT forgotten: it is loose, on /status and in the journal,
        and reconcile keeps asking after it until it is terminal."""
        stop_id = pos_of(holding)["stop_order_id"]
        target_id = pos_of(holding)["target_order_id"]
        broker.cancel_pending = True
        clock.advance(seconds=1)
        broker.trigger_stop(stop_id)
        holding.poll_fills()
        assert holding.status()["positions"] == []
        loose = holding.status()["loose_legs"]
        assert [l["order_id"] for l in loose] == [target_id]
        assert loose[0]["leg"] == "take-profit"
        assert holding.journal.events("leg_unconfirmed")
        # a second sweep, still pending: still loose
        holding.reconcile()
        assert holding.status()["loose_legs"]
        # the exchange finishes the cancel
        broker.cancel_pending = False
        broker.resolve_pending_cancel(target_id)
        out = holding.reconcile()
        assert out["loose"] == [{"symbol": CALL, "order_id": target_id,
                                 "leg": "take-profit", "outcome": "canceled"}]
        assert holding.status()["loose_legs"] == []
        assert holding.journal.events("leg_resolved")

    def test_a_loose_leg_that_fills_is_a_short_and_is_never_silent(self, holding, broker, clock):
        stop_id = pos_of(holding)["stop_order_id"]
        target_id = pos_of(holding)["target_order_id"]
        broker.cancel_pending = True
        clock.advance(seconds=1)
        broker.trigger_stop(stop_id)
        holding.poll_fills()
        assert holding.status()["loose_legs"]
        # the pending cancel loses the race: the target fills after the close
        broker.cancel_pending = False
        broker.set_quote(CALL, bid=21.50, ask=21.60)
        broker.fill_resting(target_id)
        holding.reconcile()
        over = holding.journal.events("oversold")
        assert over and over[0]["order_id"] == target_id and over[0]["leg"] == "take-profit"
        assert holding.status()["loose_legs"] == []
        # the broker now holds a short, and the page can see it
        assert holding.status()["shorts"] == [{"symbol": CALL, "qty": -1}]
        assert holding.journal.events("short_held")
        # it is not adopted, not flattened, and the slot count is honest
        assert holding.status()["positions"] == []

    def test_a_loose_leg_survives_a_restart(self, holding, broker, clock, tmp_path):
        stop_id = pos_of(holding)["stop_order_id"]
        target_id = pos_of(holding)["target_order_id"]
        broker.cancel_pending = True
        clock.advance(seconds=1)
        broker.trigger_stop(stop_id)
        holding.poll_fills()
        again = ExecService(broker, holding.config, clock=clock)
        assert [l["order_id"] for l in again.status()["loose_legs"]] == [target_id]
        broker.cancel_pending = False
        broker.resolve_pending_cancel(target_id)
        again.reconcile()
        assert again.status()["loose_legs"] == []

    def test_a_sell_on_a_symbol_not_held_is_journaled_once_not_dropped(self, armed, broker):
        """Finding 29: a SELL_TO_CLOSE the sweep could attribute to no
        position was ``continue``d. It is the last chance to see a short."""
        from execd.broker import Fill
        broker._fills.append(Fill("foreign-9", PUT, Side.SELL_TO_CLOSE, 1, 1.85,
                                  armed.clock() + __import__("datetime").timedelta(seconds=1)))
        armed.poll_fills()
        armed.poll_fills()
        lines = armed.journal.events("unattributed_sell")
        assert len(lines) == 1 and lines[0]["order_id"] == "foreign-9" and lines[0]["symbol"] == PUT

    def test_a_cancel_that_errors_keeps_the_leg_id_so_no_second_stop_is_rested(
            self, holding, broker, clock):
        """Finding 39's mirror: ``_cancel_leg_quietly`` cleared the id on a
        BrokerError, so a cancel that timed out but succeeded was forgotten
        and the next re-rest put a second stop beside the first."""
        stop_id = pos_of(holding)["stop_order_id"]
        # the target fills at the broker; the fill sweep books it and
        # _book_close then cancels the stop — and that cancel errors
        target_id = pos_of(holding)["target_order_id"]
        broker.set_quote(CALL, bid=21.50, ask=21.60)
        clock.advance(seconds=1)
        broker.fill_resting(target_id)
        real_cancel = broker.cancel
        errored: list[str] = []

        def cancel_once_erroring(order_id):
            if not errored:
                errored.append(order_id)
                raise BrokerError("socket closed")
            return real_cancel(order_id)

        broker.cancel = cancel_once_erroring
        holding.poll_fills()
        assert errored == [stop_id]
        # the position is closed (target filled the whole size) and the stop,
        # whose cancel errored, is loose — not forgotten
        assert holding.status()["positions"] == []
        assert [l["order_id"] for l in holding.status()["loose_legs"]] == [stop_id]
        assert len(legs(broker)["stop"]) == 1              # one stop at the broker, not two
        holding.reconcile()                                # the retry cancels it
        assert holding.status()["loose_legs"] == [] and legs(broker)["stop"] == []


class TestFilledQuantityFallback:
    """01 §6 of the 2026-08-30 audit, never closed: ``filled_qty or pos.qty``
    booked a full close for a FILLED order whose body carried no quantity.
    The fallback is the order's own size, never the position's."""

    def test_a_filled_order_with_no_quantity_books_its_own_size(self):
        from execd.service import _filled_qty_of
        o = OrderResult(order_id="x", status=OrderStatus.FILLED, symbol=CALL,
                        side=Side.SELL_TO_CLOSE, qty=1, order_type=OrderType.MARKET,
                        filled_qty=0, fill_price=2.0)
        assert _filled_qty_of(o) == 1
        assert _filled_qty_of(OrderResult(order_id="y", status=OrderStatus.FILLED, symbol=CALL,
                                          side=Side.SELL_TO_CLOSE, qty=3, order_type=OrderType.MARKET,
                                          filled_qty=2, fill_price=2.0)) == 2


class TestUnchangedLegsAndWaterMarks:
    """Steve, 2026-09-15 14:07 CT: "Stop moved from 10.30 to 10.30 … the
    running total showed price at +70 but market order not fired … what's
    journal show?" The stop was pulled and re-rested twice at the same
    price, and the journal held no trace of the +70. [st-ff5j]"""

    def test_an_unchanged_stop_is_left_resting_and_said_so(self, page, holding, broker):
        before = pos_of(holding)
        adjusted_before = len(holding.journal.events("stop_adjusted"))
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "1.50",
                                                  "target_price": "25"})
        landing = text(page.get(r.headers["Location"]))
        assert "Stop unchanged at 1.50." in landing and "Target moved from 21.00 to 25.00" in landing
        after = pos_of(holding)
        assert after["stop_order_id"] == before["stop_order_id"]
        assert broker._orders[before["stop_order_id"]].status is OrderStatus.WORKING
        assert len(holding.journal.events("stop_adjusted")) == adjusted_before
        ev = holding.journal.events("adjust_unchanged")[-1]
        assert ev["leg"] == "stop" and ev["price"] == 1.50 and ev["order_id"] == before["stop_order_id"]

    def test_both_unchanged_touches_nothing(self, page, holding, broker):
        before = pos_of(holding)
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "1.50",
                                                  "target_price": "21.00"})
        landing = text(page.get(r.headers["Location"]))
        assert "Stop unchanged at 1.50. Target unchanged at 21.00." in landing
        after = pos_of(holding)
        assert (after["stop_order_id"], after["target_order_id"]) == (before["stop_order_id"], before["target_order_id"])

    def test_the_water_marks_follow_the_bid_and_land_in_the_closed_line(self, holding, broker, clock):
        broker.set_quote(CALL, bid=2.80, ask=2.90)
        clock.advance(seconds=10)
        holding.status()
        p = pos_of(holding)
        assert p["best_net_usd"] == pytest.approx((2.80 - 2.10) * 100 - 1.30)
        assert p["worst_net_usd"] == p["best_net_usd"] or p["worst_net_usd"] < p["best_net_usd"]
        best_at = p["best_at"]
        broker.set_quote(CALL, bid=1.90, ask=2.00)
        clock.advance(seconds=10)
        holding.status()
        p = pos_of(holding)
        assert p["best_net_usd"] == pytest.approx(68.70) and p["best_at"] == best_at
        assert p["worst_net_usd"] == pytest.approx((1.90 - 2.10) * 100 - 1.30)
        holding.flatten()
        closed = holding.journal.events("closed")[-1]
        assert closed["best_net_usd"] == pytest.approx(68.70) and closed["best_at"] == best_at
        assert closed["worst_net_usd"] == pytest.approx(-21.30) and closed["worst_at"]

    def test_the_card_shows_best_and_worst_and_update_goes_dead_on_submit(self, page, holding, broker):
        broker.set_quote(CALL, bid=2.80, ask=2.90)
        body = text(page.get("/exec/order"))
        assert "best <span class='pos'>+$68.70</span> at " in body
        assert "b.textContent = '…'" in body and "classList.contains('adjust')" in body
        holding.flatten()
        after = text(page.get("/exec/order"))
        assert "best · worst" in after and "+$68.70" in after


class TestAReplayedAdjustTouchesNothing:
    """Steve, 2026-09-15 14:07 CT: the browser (or the tailnet proxy) re-sent
    an UPDATE the instant the first one's 303 went out; the service ran it
    again. And the poll repainted the editor with the old values while the
    new ones were in flight — "the screen blink and the 104 displayed
    again". [st-gw5m]"""

    def test_the_same_adjust_inside_the_window_is_answered_from_the_first(self, holding, broker, clock):
        first = holding.adjust(CALL, stop_price=1.80, target_price=25.0)
        assert first["stop"]["moved"] and first["target"]["moved"]
        ids = (pos_of(holding)["stop_order_id"], pos_of(holding)["target_order_id"])
        calls_before = len(broker.calls)
        clock.advance(seconds=4)
        again = holding.adjust(CALL, stop_price=1.80, target_price=25.0)
        assert again.get("replayed") is True
        assert again["stop"]["moved"] and again["target"]["moved"]      # the first answer, verbatim
        assert len(broker.calls) == calls_before                          # nothing at the broker
        assert (pos_of(holding)["stop_order_id"], pos_of(holding)["target_order_id"]) == ids
        ev = holding.journal.events("adjust_replayed")[-1]
        assert ev["stop_price"] == 1.80 and ev["first_at"]

    def test_outside_the_window_it_is_a_new_adjust(self, holding, broker, clock):
        from execd.service import ADJUST_REPLAY_S
        holding.adjust(CALL, stop_price=1.80, target_price=25.0)
        clock.advance(seconds=ADJUST_REPLAY_S + 1)
        again = holding.adjust(CALL, stop_price=1.80, target_price=25.0)
        assert not again.get("replayed") and again["stop"]["unchanged"] and again["target"]["unchanged"]

    def test_a_different_adjust_is_never_a_replay(self, holding, broker, clock):
        holding.adjust(CALL, stop_price=1.80)
        clock.advance(seconds=2)
        again = holding.adjust(CALL, stop_price=1.85)
        assert not again.get("replayed") and again["stop"]["moved"] and again["stop"]["new_price"] == 1.85

    def test_a_refused_adjust_is_not_remembered(self, holding, broker, clock):
        r = holding.adjust(CALL, stop_price=2.50)          # not below the bid: refused
        assert r["refused"]
        broker.set_quote(CALL, bid=2.60, ask=2.70)
        again = holding.adjust(CALL, stop_price=2.50)
        assert not again.get("replayed") and again["stop"]["moved"]

    def test_the_script_freezes_the_body_while_an_update_is_in_flight(self, page, holding):
        body = text(page.get("/exec/order"))
        assert "var inflight = false;" in body and "inflight = true;" in body
        assert "!inflight && (changed || !editing())" in body


class TestOneLegEnterToSend:
    """Steve, 2026-09-15: "there isn't going to be a scenario where i want
    to change both take profit and stop loss. It'll be one or the other.
    I'd like to be able to enter the value in either and just hit enter to
    submit … make this as instant as possible." [st-bmaz]"""

    def test_the_card_has_one_form_per_leg_and_no_update_button(self, page, holding):
        body = text(page.get("/exec/order"))
        card = body.split("<div id=panel ")[1].split("<div class=side>")[0]
        forms = card.split("class='adjust leg'")
        assert len(forms) == 3 and ">UPDATE<" not in card
        assert "data-leg=stop" in card and "data-leg=target" in card
        assert card.count("enterkeyhint=go") == 2 and card.count(">SET<") == 2
        assert "id=adjustnote" in card
        stop_form = card.split("data-leg=stop")[1].split("</form>")[0]
        assert "name=stop inputmode" in stop_form and "name=target inputmode" not in stop_form

    def test_an_ajax_set_answers_in_place_with_the_repainted_card(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "target_price": "25", "ajax": "1"})
        assert r.status_code == 200
        j = r.json
        assert j["ok"] is True and j["msg"] == "Target moved from 21.00 to 25.00." and j["bad"] is None
        assert j["panel_stage"] == "filled" and "value='25.00'" in j["panel_body_html"]
        assert "value='1.50'" in j["panel_body_html"]              # the stop untouched
        assert pos_of(holding)["target_price"] == 25.0 and pos_of(holding)["stop_price"] == 1.50

    def test_an_ajax_refusal_is_words_not_a_redirect(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "2.50"},
                      headers={"Accept": "application/json"})
        assert r.status_code == 200
        j = r.json
        assert j["ok"] is False and "Refused (bracket)" in j["bad"] and "not below the 2.00 bid" in j["bad"]
        assert j["panel_stage"] == "filled" and pos_of(holding)["stop_price"] == 1.50

    def test_the_plain_form_still_redirects(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "1.80"})
        assert r.status_code == 303 and "msg=Stop+moved" in r.headers["Location"]

    def test_the_script_sends_a_leg_by_fetch_and_paints_the_answer(self, page, holding):
        body = text(page.get("/exec/order"))
        assert "fd.set('ajax', '1')" in body and "headers: {'Accept': 'application/json'}" in body
        assert "note(j.bad || j.msg || '', !!j.bad)" in body


# ── E. either leg as an SPX level (st-2j3m) ──────────────────────────────

class TestSpxLevelBracket:
    """Steve, 2026-09-16: "i'd like to have a path to define a SPX target
    strike for both stop loss and take profit … the operator will include a
    '.' in the form submission when asking for dollar amt." A level is
    walked into the price that rests; the level is what the loop watches.
    The ``holding`` fixture: fill 2.10 at SPX 6380, delta 0.30, bid 2.00 /
    ask 2.10 (a 0.33-point noise floor), stop 1.50 at 6378, target 21.00.
    [st-2j3m]"""

    def test_a_stop_given_as_a_level_rests_the_walked_price_and_watches_the_level(
            self, holding, broker):
        before = pos_of(holding)
        out = holding.adjust(CALL, stop_spx=SPX_NOW - 4)
        assert out["refused"] is None
        s = out["stop"]
        assert s["moved"] and s["given"] == "spx"
        assert (s["old_price"], s["new_price"]) == (1.50, 0.90)      # 2.10 − 4 × 0.30
        assert (s["old_stop_spx"], s["stop_spx"]) == (NEAR_STOP, SPX_NOW - 4)
        after = pos_of(holding)
        assert after["stop_price"] == 0.90 and after["stop_spx"] == SPX_NOW - 4
        assert after["stop_order_id"] != before["stop_order_id"]
        assert legs(broker)["stop"][0].price == 0.90
        line = holding.journal.events("stop_adjusted")[-1]
        assert line["given"] == "spx" and line["new_stop_spx"] == SPX_NOW - 4
        assert line["new_price"] == 0.90
        assert holding.journal.events("stop_placed")[-1]["stop_spx"] == SPX_NOW - 4
        # the loop fires at the level, not before
        assert holding.observe(SPX_NOW - 3.9)["fired"] == []
        fired = holding.observe(SPX_NOW - 4)["fired"][0]
        assert fired["closed"] is True and fired["reason"] == "spx-stop"

    def test_a_put_stop_level_sits_above_the_market(self, armed, broker):
        armed.place(entry(intent_id="lv-p", symbol=PUT, limit=1.90,
                          stop_spx=SPX_NOW + 2.0, delta=0.30))
        out = armed.adjust(PUT, stop_spx=SPX_NOW + 4)
        assert out["refused"] is None
        assert out["stop"]["new_price"] == 0.70                        # 1.90 − 4 × 0.30
        assert pos_of(armed)["stop_spx"] == SPX_NOW + 4
        assert armed.observe(SPX_NOW + 3.9)["fired"] == []
        assert armed.observe(SPX_NOW + 4)["fired"][0]["closed"] is True

    def test_a_target_given_as_a_level_rests_the_walked_limit_and_the_loop_fires_at_it(
            self, holding, broker):
        out = holding.adjust(CALL, target_spx=SPX_NOW + 20)
        assert out["refused"] is None
        t = out["target"]
        assert t["moved"] and t["given"] == "spx"
        assert (t["old_price"], t["new_price"]) == (21.00, 8.10)     # 2.10 + 20 × 0.30
        assert (t["old_target_spx"], t["target_spx"]) == (None, SPX_NOW + 20)
        p = pos_of(holding)
        assert p["target_price"] == 8.10 and p["target_spx"] == SPX_NOW + 20
        assert legs(broker)["target"][0].price == 8.10
        placed = holding.journal.events("target_placed")[-1]
        assert placed["target_spx"] == SPX_NOW + 20 and placed["kind"] == "adjusted"
        adjusted = holding.journal.events("target_adjusted")[-1]
        assert adjusted["given"] == "spx" and adjusted["new_target_spx"] == SPX_NOW + 20
        # the mark reaches the level: both legs off, a market close, named
        stop_id, target_id = p["stop_order_id"], p["target_order_id"]
        assert holding.observe(SPX_NOW + 19.9)["fired"] == []
        fired = holding.observe(SPX_NOW + 20)["fired"][0]
        assert fired["closed"] is True and fired["reason"] == "spx-target"
        assert holding.journal.events("target_triggered")[-1]["target_spx"] == SPX_NOW + 20
        assert holding.journal.events("closed")[-1]["kind"] == "spx-target"
        assert broker._orders[stop_id].status is OrderStatus.CANCELED
        assert broker._orders[target_id].status is OrderStatus.CANCELED
        assert holding.status()["positions"] == []

    def test_the_resting_limit_is_the_target_s_floor_when_the_bid_gets_there_first(
            self, holding, broker, clock):
        holding.adjust(CALL, target_spx=SPX_NOW + 20)
        p = pos_of(holding)
        clock.advance(minutes=1)
        broker.fill_resting(p["target_order_id"])
        holding.poll_fills()
        assert holding.journal.events("closed")[-1]["kind"] == "target"
        assert holding.status()["positions"] == []
        assert holding.observe(SPX_NOW + 20)["fired"] == []

    def test_a_target_given_in_dollars_after_a_level_clears_the_level(self, holding, broker):
        holding.adjust(CALL, target_spx=SPX_NOW + 20)
        out = holding.adjust(CALL, target_price=25.0)
        t = out["target"]
        assert t["moved"] and t["given"] == "price"
        assert t["old_target_spx"] == SPX_NOW + 20 and t["target_spx"] is None
        assert pos_of(holding)["target_spx"] is None
        assert holding.observe(SPX_NOW + 20)["fired"] == []          # nothing fires on a price
        assert holding.journal.events("target_adjusted")[-1]["new_target_spx"] is None

    def test_a_level_whose_price_already_rests_moves_the_level_alone(self, holding, broker):
        holding.adjust(CALL, stop_spx=SPX_NOW - 4)                  # rests 0.90
        p = pos_of(holding)
        cancels = len(broker.calls_to("cancel"))
        out = holding.adjust(CALL, stop_spx=SPX_NOW - 4.01)         # 0.897 → 0.90: the same tick
        s = out["stop"]
        assert s["moved"] and s["level_only"] and s["new_price"] == 0.90
        assert s["stop_spx"] == SPX_NOW - 4.01 and s["old_stop_spx"] == SPX_NOW - 4
        assert len(broker.calls_to("cancel")) == cancels
        assert pos_of(holding)["stop_order_id"] == p["stop_order_id"]
        assert pos_of(holding)["stop_spx"] == SPX_NOW - 4.01
        line = holding.journal.events("stop_adjusted")[-1]
        assert line["level_only"] is True and line["new_order_id"] == p["stop_order_id"]
        assert holding.observe(SPX_NOW - 4.0)["fired"] == []
        assert holding.observe(SPX_NOW - 4.01)["fired"][0]["closed"] is True

    def test_a_dollar_target_at_the_resting_price_clears_the_level_without_the_broker(
            self, holding, broker):
        holding.adjust(CALL, target_spx=SPX_NOW + 20)                # rests 8.10
        cancels = len(broker.calls_to("cancel"))
        out = holding.adjust(CALL, target_price=8.10)
        t = out["target"]
        assert t["level_only"] and t["target_spx"] is None and t["given"] == "price"
        assert len(broker.calls_to("cancel")) == cancels
        assert pos_of(holding)["target_spx"] is None
        assert holding.observe(SPX_NOW + 20)["fired"] == []

    def test_the_same_level_again_is_unchanged(self, holding, broker):
        holding.adjust(CALL, stop_spx=SPX_NOW - 4)
        holding.adjust(CALL, target_spx=SPX_NOW + 20)
        cancels = len(broker.calls_to("cancel"))
        out = holding.adjust(CALL, stop_spx=SPX_NOW - 4, target_spx=SPX_NOW + 20)
        assert out["stop"]["unchanged"] and out["stop"]["stop_spx"] == SPX_NOW - 4
        assert out["target"]["unchanged"] and out["target"]["target_spx"] == SPX_NOW + 20
        assert out["stop"]["given"] == "spx"
        assert len(broker.calls_to("cancel")) == cancels
        assert holding.journal.events("adjust_unchanged")[-1]["level"] == SPX_NOW + 20

    def test_a_dollar_stop_still_walks_its_level_back_and_a_raised_stop_walks_above_the_entry(
            self, holding, broker):
        broker.set_quote(CALL, bid=5.00, ask=5.10)
        out = holding.adjust(CALL, stop_price=3.00)                  # 0.90 above the fill
        assert out["stop"]["given"] == "price"
        assert out["stop"]["stop_spx"] == SPX_NOW + 3.0              # (2.10 − 3.00)/0.30 = −3
        assert holding.observe(SPX_NOW + 3.1)["fired"] == []
        assert holding.observe(SPX_NOW + 3.0)["fired"][0]["closed"] is True

    @pytest.mark.parametrize("kwargs, words", [
        (dict(stop_spx=SPX_NOW + 5), "a call's stop sits below the market"),
        (dict(stop_spx=SPX_NOW), "not below the 6380.00 mark"),
        (dict(target_spx=SPX_NOW - 5), "a call's target sits above the market"),
        (dict(target_spx=SPX_NOW), "not above the 6380.00 mark"),
        (dict(stop_spx=SPX_NOW - 0.2), "inside the 0.33-point noise floor"),
        (dict(target_spx=SPX_NOW + 0.3), "inside the 0.33-point noise floor"),
        (dict(stop_spx=SPX_NOW - 10), "walks to no price this stop can rest at"),
    ])
    def test_a_level_that_cannot_be_a_trigger_is_refused_in_words(
            self, holding, broker, kwargs, words):
        before = pos_of(holding)
        out = holding.adjust(CALL, **kwargs)
        assert out["refused"]["bound"] == "level" and words in out["refused"]["reason"]
        after = pos_of(holding)
        assert (after["stop_order_id"], after["target_order_id"]) == \
            (before["stop_order_id"], before["target_order_id"])
        assert (after["stop_spx"], after["target_spx"]) == (NEAR_STOP, None)
        assert broker.calls_to("cancel") == []
        assert holding.journal.events("refused")[-1]["kind"] == "adjust"

    def test_a_put_level_on_the_wrong_side_is_refused_the_other_way(self, armed):
        armed.place(entry(intent_id="lv-p2", symbol=PUT, limit=1.90,
                          stop_spx=SPX_NOW + 2.0, delta=0.30))
        out = armed.adjust(PUT, stop_spx=SPX_NOW - 5)
        assert out["refused"]["bound"] == "level"
        assert "a put's stop sits above the market" in out["refused"]["reason"]
        out = armed.adjust(PUT, target_spx=SPX_NOW + 5)
        assert "a put's target sits below the market" in out["refused"]["reason"]

    def test_the_walked_price_meets_the_bid_refusal_worded_with_the_level(self, holding, broker):
        broker.set_quote("$SPX", bid=SPX_NOW + 9.75, ask=SPX_NOW + 10.25, last=SPX_NOW + 10)
        out = holding.adjust(CALL, stop_spx=SPX_NOW + 9)             # walks to 4.80, bid 2.00
        assert out["refused"]["bound"] == "bracket"
        assert "a stop at SPX 6389 (which walks to 4.80) is not below the 2.00 bid" \
            in out["refused"]["reason"]

    def test_a_position_with_no_delta_cannot_take_a_level(self, holding):
        holding._open[CALL].delta = None
        out = holding.adjust(CALL, stop_spx=SPX_NOW - 4)
        assert out["refused"]["bound"] == "level"
        assert "give the stop in dollars" in out["refused"]["reason"]
        assert holding.adjust(CALL, stop_price=1.80)["refused"] is None   # dollars still work

    def test_a_leg_is_a_price_or_a_level_never_both(self, holding):
        with pytest.raises(ValueError, match="a price or an SPX level, not both"):
            holding.adjust(CALL, stop_price=1.80, stop_spx=SPX_NOW - 4)
        with pytest.raises(ValueError, match="a price or an SPX level, not both"):
            holding.adjust(CALL, target_price=25.0, target_spx=SPX_NOW + 20)

    def test_a_level_adjust_replays_like_a_price_one(self, holding, broker, clock):
        first = holding.adjust(CALL, stop_spx=SPX_NOW - 4)
        calls = len(broker.calls)
        clock.advance(seconds=3)
        again = holding.adjust(CALL, stop_spx=SPX_NOW - 4)
        assert again.get("replayed") is True and again["stop"]["new_price"] == first["stop"]["new_price"]
        assert len(broker.calls) == calls
        assert holding.journal.events("adjust_replayed")[-1]["stop_spx"] == SPX_NOW - 4

    def test_the_status_carries_the_target_level(self, holding):
        holding.adjust(CALL, target_spx=SPX_NOW + 20)
        p = pos_of(holding)
        assert p["target_spx"] == SPX_NOW + 20
        assert holding.valuation(holding._open[CALL])["at_target_usd"] == pytest.approx(
            (8.10 - 2.10) * 100 - 1.30)

    def test_a_restart_rebuilds_both_levels(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="lv-rec", stop_spx=NEAR_STOP, delta=0.30))
        first.adjust(CALL, stop_spx=SPX_NOW - 4, target_spx=SPX_NOW + 20)
        first.adjust(CALL, stop_spx=SPX_NOW - 4.01)                 # level only, no re-rest
        moved = pos_of(first)

        second = ExecService(broker, config, clock=clock)
        after = pos_of(second)
        assert (after["stop_order_id"], after["target_order_id"]) == \
            (moved["stop_order_id"], moved["target_order_id"])
        assert (after["stop_price"], after["target_price"]) == (0.90, 8.10)
        assert after["stop_spx"] == SPX_NOW - 4.01 and after["target_spx"] == SPX_NOW + 20
        second.unlock({"token": "x"})
        assert second.observe(SPX_NOW + 20)["fired"][0]["reason"] == "spx-target"

    def test_a_restart_after_the_level_was_cleared_carries_no_level(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="lv-rec2", stop_spx=NEAR_STOP, delta=0.30))
        first.adjust(CALL, target_spx=SPX_NOW + 20)
        first.adjust(CALL, target_price=8.10)                         # clears the level in place
        second = ExecService(broker, config, clock=clock)
        assert pos_of(second)["target_spx"] is None
        second.unlock({"token": "x"})
        assert second.observe(SPX_NOW + 20)["fired"] == []


class TestSpxLevelOverTheApi:
    @pytest.fixture
    def client(self, holding):
        return create_app(holding).test_client()

    @staticmethod
    def post(client, payload):
        return client.post("/adjust", data=json.dumps(payload), content_type="application/json")

    def test_a_level_for_either_leg_is_accepted(self, client, holding):
        r = self.post(client, {"symbol": CALL, "stop_spx": SPX_NOW - 4, "target_spx": "6400"})
        assert r.status_code == 200
        assert r.json["stop"]["new_price"] == 0.90 and r.json["stop"]["stop_spx"] == SPX_NOW - 4
        assert r.json["target"]["new_price"] == 8.10 and r.json["target"]["target_spx"] == 6400.0
        assert pos_of(holding)["target_spx"] == 6400.0

    def test_a_level_refusal_is_a_409_naming_the_bound(self, client):
        r = self.post(client, {"symbol": CALL, "stop_spx": SPX_NOW + 5})
        assert r.status_code == 409 and r.json["refused"]["bound"] == "level"

    def test_both_forms_for_one_leg_is_a_400(self, client):
        r = self.post(client, {"symbol": CALL, "stop_price": 1.80, "stop_spx": SPX_NOW - 4})
        assert r.status_code == 400 and r.json["error"] == "bad_request"


class TestSpxLevelOnThePage:
    """The box takes either form, told apart by the '.' (Steve's rule); the
    answer says which was set; the card shows both forms of each leg."""

    def test_a_number_without_a_point_is_an_spx_level(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop": "6376", "ajax": "1"})
        j = r.json
        assert j["ok"] is True
        assert j["msg"] == "Stop set by SPX 6376.00 → rests at 0.90 (was 1.50)."
        p = pos_of(holding)
        assert p["stop_price"] == 0.90 and p["stop_spx"] == 6376.0

    def test_a_number_with_a_point_is_dollars(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop": "1.80", "ajax": "1"})
        assert r.json["msg"] == "Stop moved from 1.50 to 1.80 (SPX cut level now 6379.00)."
        assert pos_of(holding)["stop_price"] == 1.80

    def test_a_target_level_and_then_a_dollar_target_say_which_fires(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "target": "6400", "ajax": "1"})
        assert r.json["msg"] == "Target set by SPX 6400.00 → rests at 8.10 (was 21.00)."
        card = r.json["panel_body_html"]
        assert "value='8.10'" in card and "<span class=level>SPX 6400.00</span>" in card
        assert "<span class=level>SPX 6378.00</span>" in card            # the stop's, beside it
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "target": "25.0", "ajax": "1"})
        assert r.json["msg"] == ("Target moved from 8.10 to 25.00 (a price: nothing fires on "
                                 "the SPX mark for it now).")
        assert "SPX 6400.00" not in r.json["panel_body_html"]

    def test_a_level_that_only_moves_the_level_says_so(self, page, holding):
        page.post("/exec/order/adjust", data={"symbol": CALL, "stop": "6376", "ajax": "1"})
        holding._last_adjust = None
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "target": "8.10", "ajax": "1"})
        # 8.10 in dollars where 21.00 rests: a real move; then a level that walks to 8.10
        assert r.json["msg"] == "Target moved from 21.00 to 8.10."
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "target": "6400", "ajax": "1"})
        assert r.json["msg"] == "Target SPX level set to 6400.00; the resting 8.10 target is unchanged."

    def test_a_level_refusal_is_words(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop": "6385", "ajax": "1"})
        assert r.json["ok"] is False
        assert "Refused (level): a call's stop sits below the market" in r.json["bad"]

    def test_a_point_in_a_level_sized_number_is_read_as_dollars_and_refused_in_words(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop": "6376.5", "ajax": "1"})
        assert r.json["ok"] is False and "a stop at 6376.50 is not below the 2.00 bid" in r.json["bad"]

    @pytest.mark.parametrize("raw, words", [
        ("abc", "stop must be a number"),
        ("1e-1", "not a whole SPX level"),
    ])
    def test_a_value_that_is_neither_is_said_back(self, page, holding, raw, words):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop": raw, "ajax": "1"})
        assert r.json["ok"] is False and words in r.json["bad"]

    def test_the_named_dollar_fields_still_work(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "1.80", "ajax": "1"})
        assert r.json["ok"] is True and pos_of(holding)["stop_price"] == 1.80

    def test_the_card_states_the_rule_and_shows_the_stop_level(self, page, holding):
        body = text(page.get("/exec/order"))
        card = body.split("<div id=panel ")[1].split("<div class=side>")[0]
        assert "a number with a '.' is a price (10.30); without one it is an SPX level (7585)" in card
        assert "<span class=level>SPX 6378.00</span>" in card
        assert "name=stop inputmode=decimal" in card and "name=target inputmode=decimal" in card
