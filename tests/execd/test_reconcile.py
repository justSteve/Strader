"""The broker is the authority on what is open; the journal is the audit. [st-v7oa]

Every test here exists because of one sentence in the 2026-08-30 independent
audit of this service (case st-5qjq, finding 1):

    The service transmits on what was *requested* and counts on what *filled*,
    and every bound is computed from what filled.

Those are the same event only because ``MockBroker`` used to fill every limit
synchronously. A real broker acknowledges an order and rests it, and a resting
limit is the normal answer rather than an edge case. Before this file, an entry
that came back ``WORKING`` was handed to the caller and forgotten: no tracked
position, no protective stop, no attempt debited, and nothing that ever looked
at it again — so five ``/place`` calls left five live buy orders against a
one-contract, one-position, two-attempt bound.

The fix is not a counter. It is that the service now asks the broker. ``Broker``
has always had ``orders()`` and ``positions()``; nothing on the write path ever
called them. ``ExecService.reconcile`` calls both — at start-up, before every
entry, before an exit is sized, and on the fill poll — and the tests below are
what "asks the broker" has to mean:

* a working entry occupies a position slot and an attempt while it is alive,
  because it can become a position at any moment;
* it survives a restart, because the journal records it;
* when it fills, the service notices and rests the protective stop it owes;
* when it is cancelled or rejected, the slot comes back;
* a position the service does not know about is adopted rather than ignored,
  and an exit is sized against the broker rather than sent unbounded.
"""

from __future__ import annotations

import pytest

from execd.bounds import Bounds
from execd.broker import MockBroker, OrderStatus, Position
from execd.service import POSITION_SETTLE_S, ExecService, ServiceConfig

from .conftest import CALL, PUT, SPX_NOW, entry, exit_intent


def working_buys(broker: MockBroker) -> list:
    return [o for o in broker.working_orders() if o.side.value == "BUY_TO_OPEN"]


class TestAWorkingEntryIsNotForgotten:
    def test_it_occupies_a_position_and_an_attempt(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry())
        assert out["order"]["status"] == "WORKING"
        assert out["stop_order"] is None          # nothing filled, nothing to protect
        day = armed.status()["day"]
        assert day["open_positions"] == 1
        assert day["attempts_used"] == 1

    def test_it_is_visible_as_a_working_order_not_a_position(self, armed, broker):
        broker.rest_limits = True
        armed.place(entry())
        status = armed.status()
        assert status["positions"] == []
        assert status["working"][0]["symbol"] == CALL
        assert status["working"][0]["qty"] == 1

    def test_a_second_entry_is_refused_while_the_first_is_still_working(
            self, armed, broker):
        broker.rest_limits = True
        armed.place(entry(intent_id="w-1"))
        out = armed.place(entry(intent_id="w-2"))
        assert out["refused"]["bound"] == "positions"

    def test_five_places_cannot_leave_five_live_buy_orders(self, armed, broker):
        """The audit's own reproduction, as a test. Five calls, one order."""
        broker.rest_limits = True
        for n in range(1, 6):
            armed.place(entry(intent_id=f"probe-{n}"))
        assert len(working_buys(broker)) == 1

    def test_the_journal_records_it_so_a_restart_recovers_it(
            self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        broker.rest_limits = True
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="survive-1"))

        second = ExecService(broker, config, clock=clock)
        assert second.status()["working"][0]["intent_id"] == "survive-1"
        assert second.day_state().open_positions == 1


class TestReconcileResolvesWhatTheBrokerDid:
    def test_a_working_entry_that_filled_becomes_a_protected_position(
            self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry())
        broker.fill_resting(out["order"]["order_id"])

        result = armed.reconcile()
        assert result["promoted"] == [CALL]
        pos = armed.status()["positions"][0]
        assert pos["symbol"] == CALL
        assert pos["qty"] == 1
        assert pos["stop_order_id"] is not None      # the stop it owed
        assert armed.status()["working"] == []

    def test_the_promoted_fill_is_journaled_as_an_entry_fill(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry())
        broker.fill_resting(out["order"]["order_id"])
        armed.reconcile()
        filled = armed.journal.events("filled")
        assert filled and filled[0]["kind"] == "entry"
        assert filled[0]["symbol"] == CALL
        assert armed.journal.events("stop_placed")

    def test_a_cancelled_working_entry_gives_the_slot_back(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry(intent_id="pull-1"))
        armed.cancel(out["order"]["order_id"])

        armed.reconcile()
        day = armed.status()["day"]
        assert day["open_positions"] == 0
        assert day["attempts_used"] == 0
        assert armed.place(entry(intent_id="pull-2"))["refused"] is None

    def test_a_rejected_working_entry_gives_the_slot_back(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry(intent_id="rej-1"))
        broker.reject_resting(out["order"]["order_id"])
        armed.reconcile()
        assert armed.status()["day"]["attempts_used"] == 0

    def test_an_order_the_broker_has_never_heard_of_keeps_its_slot(
            self, armed, broker):
        """The safe direction. Forgetting it is the bug; holding it refuses new
        risk, which is a thing this service is allowed to do."""
        broker.rest_limits = True
        armed.place(entry(intent_id="ghost-1"))
        broker._orders.clear()

        armed.reconcile()
        assert armed.status()["day"]["open_positions"] == 1
        assert armed.journal.events("reconcile_unknown")

    def test_reconcile_runs_before_an_entry_is_bounded(self, armed, broker):
        """No explicit reconcile() call: place() does it, so a fill that
        happened while nothing was watching is seen before the next send."""
        broker.rest_limits = True
        out = armed.place(entry(intent_id="auto-1"))
        broker.fill_resting(out["order"]["order_id"])

        second = armed.place(entry(intent_id="auto-2"))
        assert second["refused"]["bound"] == "positions"
        assert armed.status()["positions"][0]["stop_order_id"] is not None

    def test_reconcile_is_silent_when_nothing_has_changed(self, armed):
        armed.place(entry())
        before = len(armed.journal.read())
        armed.reconcile()
        assert len(armed.journal.read()) == before


class TestTheBrokerIsTheAuthorityOnPosition:
    def test_a_position_the_service_never_opened_is_adopted(self, armed, broker):
        broker.set_position(PUT, qty=3, avg_price=1.85)
        armed.reconcile()
        adopted = [p for p in armed.status()["positions"] if p["symbol"] == PUT]
        assert adopted and adopted[0]["qty"] == 3
        assert armed.journal.events("position_adopted")

    def test_an_adopted_position_is_flagged_as_unprotected(self, armed, broker):
        broker.set_position(PUT, qty=3, avg_price=1.85)
        armed.reconcile()
        assert armed.journal.events("stop_unprotected")

    def test_a_tracked_size_that_disagrees_with_the_broker_is_corrected(
            self, armed, broker):
        armed.place(entry())
        broker.set_position(CALL, qty=1, avg_price=2.10)
        armed._open[CALL].qty = 7          # the journal's account, gone wrong
        armed.reconcile()
        assert armed.status()["positions"][0]["qty"] == 1
        assert armed.journal.events("position_corrected")

    def test_one_absent_reading_does_not_release_a_position(self, armed, broker):
        """A positions endpoint that has not caught up with a fill it reported
        seconds ago is ordinary. Dropping the position on that would cancel the
        stop under a live trade."""
        armed.place(entry())
        broker._positions.clear()
        armed.reconcile()
        assert armed.status()["positions"][0]["symbol"] == CALL
        assert not armed.journal.events("position_gone")

    def test_a_position_absent_for_the_settle_window_is_released(
            self, armed, broker, clock):
        armed.place(entry())
        broker._positions.clear()          # closed elsewhere, e.g. by the desk
        armed.reconcile()
        clock.advance(seconds=POSITION_SETTLE_S + 1)
        armed.reconcile()
        assert armed.status()["positions"] == []
        assert armed.journal.events("position_gone")

    def test_releasing_a_position_pulls_the_stop_still_resting_under_it(
            self, armed, broker, clock):
        out = armed.place(entry())
        stop_id = out["stop_order"]["order_id"]
        broker._positions.clear()
        armed.reconcile()
        clock.advance(seconds=POSITION_SETTLE_S + 1)
        armed.reconcile()
        assert broker._orders[stop_id].status is OrderStatus.CANCELED

    def test_flatten_closes_a_position_the_service_never_opened(self, armed, broker):
        """'Close everything' means everything the broker holds."""
        broker.set_position(PUT, qty=2, avg_price=1.85)
        out = armed.flatten(reason="test")
        assert [c["symbol"] for c in out["closed"]] == [PUT]
        assert armed.status()["positions"] == []

    def test_reconcile_survives_a_broker_that_cannot_be_reached(self, armed, broker):
        armed.place(entry())
        broker.fail_next = "connection reset"
        result = armed.reconcile()
        assert result["error"] == "connection reset"
        assert armed.status()["positions"][0]["symbol"] == CALL   # nothing dropped
        assert armed.journal.events("error")


class TestAnExitIsSizedAgainstTheBroker:
    def test_an_untracked_exit_is_capped_at_what_the_broker_holds(
            self, armed, broker):
        """Finding 4: ``check_exit`` with ``held_qty=None`` transmitted an
        unbounded SELL_TO_CLOSE. The broker knows the size; ask it."""
        broker.set_position(PUT, qty=2, avg_price=1.85)
        out = armed.place(exit_intent(intent_id="over-1", symbol=PUT, qty=50))
        assert out["refused"]["bound"] == "qty"

    def test_an_exit_within_what_the_broker_holds_still_goes_through(
            self, armed, broker):
        broker.set_position(PUT, qty=2, avg_price=1.85)
        out = armed.place(exit_intent(intent_id="ok-1", symbol=PUT, qty=2))
        assert out["refused"] is None
        assert out["order"]["status"] == "FILLED"

    def test_an_exit_is_not_trapped_when_the_broker_cannot_be_reached(
            self, armed, broker, monkeypatch):
        """Nothing that exists to keep Steve out of risk may keep him in it."""
        def down(*_a, **_kw):
            from execd.broker import BrokerError
            raise BrokerError("connection reset")

        monkeypatch.setattr(broker, "positions", down)
        monkeypatch.setattr(broker, "orders", down)
        out = armed.place(exit_intent(intent_id="blind-1", symbol=PUT, qty=1))
        assert out["refused"] is None
        assert armed.journal.events("exit_unverified")


class TestTheDayCeilingCountsWorkingOrders:
    def test_two_working_entries_exhaust_the_attempts(self, armed, broker):
        armed.bounds = armed.config.bounds = Bounds(max_open_positions=2)
        broker.rest_limits = True
        armed.place(entry(intent_id="a-1"))
        armed.place(entry(intent_id="a-2", symbol=PUT,
                          stop_spx=SPX_NOW + 12.0, delta=0.28, limit=1.90))
        out = armed.place(entry(intent_id="a-3"))
        assert out["refused"]["bound"] in ("positions", "ceiling")
        assert armed.status()["day"]["attempts_used"] == 2

    def test_a_working_entry_that_fills_is_counted_once(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry(intent_id="once-1"))
        broker.fill_resting(out["order"]["order_id"])
        armed.reconcile()
        assert armed.status()["day"]["attempts_used"] == 1
        assert armed.status()["day"]["open_positions"] == 1
