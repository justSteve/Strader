"""The exit path under a broker that acknowledges before it fills. [st-97z1]

Findings 2 and 3 of the 2026-08-30 independent audit (case st-5qjq,
`01-unintended-order-paths.md` §2–§3). Both live in the same place: the
service's own exits assumed a market order fills in the same breath it is sent.

**Finding 2.** `observe()` fired `_market_close` for a position whose SPX level
had traded, and if that close came back WORKING the position stayed in the
book with its trigger still armed — so the next tick fired it again. Against a
broker that acknowledges and fills later, a one-second observe loop sent a new
market sell every second until one filled. Five ticks, five sells, one
contract.

**Finding 3.** The close was transmitted *before* the resting protective stop
was cancelled, and the two are designed to fire at the same price — the stop
is derived from the very SPX level the loop watches. Both live at the broker
at once means both can fill: a one-contract short on a long-premium-only
account.

The discipline now: one close in flight per position, remembered on the
position, in the journal, and across a restart; and the resting stop comes off
before the close goes on, with every failure branch putting it back. The tests
below are those two sentences, branch by branch.
"""

from __future__ import annotations

import pytest

from execd.broker import MockBroker, OrderStatus
from execd.service import ExecService, Refused, ServiceConfig

from .conftest import CALL, SPX_NOW, entry, exit_intent

TRIGGER = SPX_NOW - 12.5      # below the conftest entry's stop_spx of SPX_NOW - 12


def sells(broker: MockBroker) -> list[dict]:
    return [kw for kw in broker.calls_to("place")
            if kw.get("side") == "SELL_TO_CLOSE" and kw.get("order_type") == "MARKET"]


@pytest.fixture
def holding(armed, broker):
    """An armed service holding one filled position with its stop resting."""
    armed.place(entry(intent_id="hold-1"))
    return armed


class TestOneCloseAtATime:
    def test_five_ticks_send_one_close_not_five(self, holding, broker):
        """The audit's finding 2, as a test."""
        broker.rest_market = True
        for _ in range(5):
            holding.observe(TRIGGER)
        assert len(sells(broker)) == 1

    def test_the_waiting_ticks_report_the_close_as_pending(self, holding, broker):
        broker.rest_market = True
        first = holding.observe(TRIGGER)
        assert first["fired"][0]["status"] == "WORKING"
        second = holding.observe(TRIGGER)
        assert second["fired"] == []
        assert second["pending"][0]["symbol"] == CALL
        assert second["pending"][0]["reason"] == "spx-stop"

    def test_a_second_manual_exit_is_refused_while_one_is_in_flight(
            self, holding, broker):
        broker.rest_market = True
        holding.observe(TRIGGER)
        out = holding.place(exit_intent(intent_id="stacked"))
        assert out["refused"]["bound"] == "exit_in_flight"
        assert len(sells(broker)) == 1

    def test_the_in_flight_close_survives_a_restart(self, broker, clock, tmp_path):
        """A restart that forgot the in-flight close would re-fire into it —
        the same oversell, resurrected."""
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="restart-1"))
        broker.rest_market = True
        first.observe(TRIGGER)

        second = ExecService(broker, config, clock=clock)
        second.unlock({"token": "x"})
        second.observe(TRIGGER)
        assert len(sells(broker)) == 1

    def test_the_filled_close_is_booked_with_the_reason_that_sent_it(
            self, holding, broker, clock):
        broker.rest_market = True
        out = holding.observe(TRIGGER)
        clock.advance(seconds=1)     # the fill must postdate the last poll
        broker.fill_resting(out["fired"][0]["order_id"])
        picked = holding.poll_fills()["picked_up"]
        assert picked and picked[0]["symbol"] == CALL
        closed = holding.journal.events("closed")[-1]
        assert closed["kind"] == "spx-stop"
        assert holding.status()["positions"] == []

    def test_a_close_the_broker_cancelled_frees_the_loop_to_fire_again(
            self, holding, broker):
        broker.rest_market = True
        out = holding.observe(TRIGGER)
        broker.reject_resting(out["fired"][0]["order_id"], "killed at the exchange")
        holding.reconcile()
        assert holding.journal.events("exit_resolved")
        # the position is live again, so the protection went back on...
        assert holding.status()["positions"][0]["stop_order_id"] is not None
        # ...and the next tick may close it.
        broker.rest_market = False
        assert holding.observe(TRIGGER)["fired"][0]["closed"] is True


class TestTheStopComesOffFirst:
    def test_the_cancel_is_transmitted_before_the_close(self, holding, broker):
        """The audit's finding 3, as a test: at no moment are the stop and the
        close both live at the broker."""
        holding.observe(TRIGGER)
        methods = [name for name, _ in broker.calls]
        assert "cancel" in methods and "place" in methods
        last_cancel_free = len(methods) - 1 - methods[::-1].index("cancel")
        first_close = max(i for i, (name, kw) in enumerate(broker.calls)
                          if name == "place" and kw.get("side") == "SELL_TO_CLOSE")
        assert last_cancel_free < first_close

    def test_when_the_stop_wins_the_race_no_close_is_sent(self, holding, broker):
        """cancel() answering FILLED means price got there first. The position
        is already closed at the broker; selling it again would be the short."""
        stop_id = holding.status()["positions"][0]["stop_order_id"]
        broker.fill_resting(stop_id)
        result = holding.observe(TRIGGER)
        assert result["fired"][0]["reason"] == "resting-stop"
        assert result["fired"][0]["closed"] is True
        assert sells(broker) == []          # the service transmitted nothing
        assert holding.status()["positions"] == []

    def test_a_rejected_close_puts_the_stop_back(self, holding, broker):
        old_stop_price = holding.status()["positions"][0]["stop_price"]
        broker.reject_next = "market closed"
        holding.observe(TRIGGER)
        pos = holding.status()["positions"][0]
        assert pos["stop_order_id"] is not None
        assert pos["stop_price"] == old_stop_price
        assert broker._orders[pos["stop_order_id"]].is_working

    def test_a_broker_down_at_the_cancel_sends_nothing_and_keeps_the_stop(
            self, holding, broker):
        stop_id = holding.status()["positions"][0]["stop_order_id"]
        broker.fail_next = "connection reset"
        result = holding.observe(TRIGGER)
        assert result["fired"][0]["status"] == "DEFERRED"
        assert sells(broker) == []
        assert broker._orders[stop_id].is_working   # the protection still stands

    def test_a_manual_full_size_exit_also_pulls_the_stop_first(
            self, holding, broker):
        stop_id = holding.status()["positions"][0]["stop_order_id"]
        out = holding.place(exit_intent(intent_id="manual-x"))
        assert out["closed"]["closed"] is True
        assert broker._orders[stop_id].status is OrderStatus.CANCELED
        methods = [name for name, _ in broker.calls]
        assert methods.index("cancel") < len(methods) - 1 - methods[::-1].index("place")

    def test_a_manual_exit_finding_the_stop_already_filled_sends_nothing(
            self, holding, broker):
        stop_id = holding.status()["positions"][0]["stop_order_id"]
        broker.fill_resting(stop_id)
        out = holding.place(exit_intent(intent_id="manual-late"))
        assert out["order"] is None
        assert out["closed"]["reason"] == "resting-stop"
        assert sells(broker) == []


class TestFlattenDoesNotQueue:
    def test_flatten_replaces_an_in_flight_close_instead_of_waiting(
            self, holding, broker):
        broker.rest_market = True
        out = holding.observe(TRIGGER)
        stuck_id = out["fired"][0]["order_id"]
        broker.rest_market = False
        result = holding.flatten(reason="get-me-out")
        assert result["closed"][0]["closed"] is True
        assert broker._orders[stuck_id].status is OrderStatus.CANCELED
        assert holding.status()["positions"] == []

    def test_flatten_books_an_in_flight_close_that_already_filled(
            self, holding, broker):
        """flatten's own reconcile finds the fill first, books it, and leaves
        flatten nothing to close — which is the point: one close, one fill,
        nothing re-sold."""
        broker.rest_market = True
        out = holding.observe(TRIGGER)
        broker.fill_resting(out["fired"][0]["order_id"])
        result = holding.flatten(reason="get-me-out")
        assert result["errors"] == []
        assert holding.status()["positions"] == []
        assert len(sells(broker)) == 1      # the original close, nothing more
        closed = holding.journal.events("closed")
        assert closed and closed[-1]["kind"] == "spx-stop"
