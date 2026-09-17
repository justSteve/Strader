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

* a working entry occupies a position slot while it is alive, because it can
  become a position at any moment (not an attempt — since 2026-09-14 an
  attempt is a filled position, st-fn5y);
* it survives a restart, because the journal records it;
* when it fills, the service notices and rests the protective stop it owes;
* when it is cancelled or rejected, the slot comes back;
* a position the service does not know about is adopted rather than ignored,
  and an exit is sized against the broker rather than sent unbounded.
"""

from __future__ import annotations

import pytest

from execd.bounds import Bounds
from execd.broker import BrokerError, MockBroker, OrderStatus, Position
from execd.service import POSITION_SETTLE_S, ExecService, ServiceConfig

from .conftest import CALL, PUT, SPX_NOW, entry, exit_intent


def working_buys(broker: MockBroker) -> list:
    return [o for o in broker.working_orders() if o.side.value == "BUY_TO_OPEN"]


class TestAWorkingEntryIsNotForgotten:
    def test_it_occupies_a_position_slot_but_no_attempt(self, armed, broker):
        """The slot is what closes the entry door. The attempt is Steve's
        counter of filled positions (2026-09-14), and nothing has filled."""
        broker.rest_limits = True
        out = armed.place(entry())
        assert out["order"]["status"] == "WORKING"
        assert out["stop_order"] is None          # nothing filled, nothing to protect
        assert out["target_order"] is None
        day = armed.status()["day"]
        assert day["open_positions"] == 1
        assert day["attempts_used"] == 0

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
    def test_a_position_the_service_never_opened_is_shown_not_adopted(self, armed, broker):
        """Until 2026-09-15 this was adopted. Finding 30 (st-isx3): the account
        holds Steve's own spreads, and adopting a leg of one meant FLATTEN
        would sell it. Now only a contract this service tried to open is
        adopted; the rest is shown."""
        broker.set_position(PUT, qty=3, avg_price=1.85)
        armed.reconcile()
        armed.reconcile()
        assert [p for p in armed.status()["positions"] if p["symbol"] == PUT] == []
        assert armed.status()["foreign_positions"] == [{"symbol": PUT, "qty": 3, "avg_price": 1.85}]
        assert len(armed.journal.events("position_foreign")) == 1        # once, not per sweep
        assert not armed.journal.events("position_adopted")

    def test_a_position_this_service_opened_and_lost_is_adopted(self, armed, broker, clock):
        """Adoption is for THIS service's position — the journal says which.
        Here the send was acknowledged and the service then forgot the working
        entry (a crash between the `working` line and the fill)."""
        broker.rest_limits = True
        armed.place(entry(intent_id="mine-1", symbol=PUT, limit=1.90, stop_spx=SPX_NOW + 12.0))
        oid = broker.working_orders(PUT)[0].order_id
        armed._working.clear()                    # the crash
        broker._orders.pop(oid)                   # the listing no longer carries it either
        broker.set_position(PUT, qty=1, avg_price=1.90)
        armed.reconcile()
        adopted = [p for p in armed.status()["positions"] if p["symbol"] == PUT]
        assert adopted and adopted[0]["intent_id"] == f"adopted:{PUT}"
        assert armed.journal.events("position_adopted")
        assert armed.journal.events("stop_unprotected")
        assert armed.status()["foreign_positions"] == []

    def test_his_butterfly_wings_are_neither_slotted_nor_flattened(self, armed, broker):
        """The sequence the audit wrote out: +1/-2/+1 by hand, unlock, price
        the first ticket, tap FLATTEN. The entry door stays open and FLATTEN
        sells nothing of his."""
        wing_lo, body, wing_hi = ("SPXW  260826C06390000", "SPXW  260826C06400000",
                                  "SPXW  260826C06410000")
        broker.set_position(wing_lo, qty=1, avg_price=5.0)
        broker.set_position(body, qty=-2, avg_price=2.1)
        broker.set_position(wing_hi, qty=1, avg_price=0.8)
        armed.reconcile()
        st = armed.status()
        assert st["positions"] == [] and st["day"]["open_positions"] == 0
        assert {p["symbol"] for p in st["foreign_positions"]} == {wing_lo, wing_hi}
        assert st["shorts"] == [{"symbol": body, "qty": -2}]
        # his entry is not refused on positions
        out = armed.place(entry(intent_id="mine-1"))
        assert out["refused"] is None and out["order"]["status"] == "FILLED"
        # FLATTEN sells the service's own contract and nothing of his
        out = armed.flatten(reason="test")
        assert [c["symbol"] for c in out["closed"]] == [CALL]
        assert broker.positions() and {p.symbol for p in broker.positions()} == {wing_lo, body, wing_hi}

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

    def test_flatten_leaves_a_position_the_service_never_opened(self, armed, broker):
        """'Close everything' means everything THIS service holds. What Steve
        holds by hand in the same account is his (finding 30, st-isx3)."""
        broker.set_position(PUT, qty=2, avg_price=1.85)
        out = armed.flatten(reason="test")
        assert out["closed"] == []
        assert broker.positions()[0].symbol == PUT
        assert armed.status()["foreign_positions"][0]["symbol"] == PUT

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
    def test_two_working_entries_fill_the_slots_and_spend_no_attempt(self, armed, broker):
        """Working entries close the entry door by the position count, not
        the attempt count: nothing has filled, so no attempt is spent
        (Steve, 2026-09-14)."""
        armed.bounds = armed.config.bounds = Bounds(max_open_positions=2)
        broker.rest_limits = True
        armed.place(entry(intent_id="a-1"))
        armed.place(entry(intent_id="a-2", symbol=PUT,
                          stop_spx=SPX_NOW + 12.0, delta=0.28, limit=1.90))
        out = armed.place(entry(intent_id="a-3"))
        assert out["refused"]["bound"] == "positions"
        assert armed.status()["day"]["attempts_used"] == 0
        assert armed.status()["day"]["open_positions"] == 2

    def test_a_working_entry_that_fills_is_counted_once(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry(intent_id="once-1"))
        broker.fill_resting(out["order"]["order_id"])
        armed.reconcile()
        assert armed.status()["day"]["attempts_used"] == 1
        assert armed.status()["day"]["open_positions"] == 1


class TestStartUpReconcileWaitsForTheCredential:
    """A real service comes back LOCKED, and its transport is bound to the
    arming state only after the constructor returns. The first installed start
    (2026-09-14 06:50 CT) journaled one spurious 'no trading credential source
    is bound' error for exactly that reason. With no credential there is
    nothing to ask the broker with, so the start-up reconcile runs at the
    unlock instead. The mock needs no credential and keeps reconciling at
    construction. [st-p8k8]"""

    class CredentialBroker(MockBroker):
        """A mock that declares it needs the arming credential, like Schwab."""

        credential_source = None

        def bind(self, arming):
            self.credential_source = arming.credential
            return self

    def test_a_locked_start_does_not_ask_the_broker_or_journal_an_error(self, clock, tmp_path):
        broker = self.CredentialBroker(clock=clock)
        service = ExecService(broker, ServiceConfig(state_dir=tmp_path, sha="t"), clock=clock)
        assert not [c for c in broker.calls if c[0] == "positions"]
        assert not [e for e in service.journal.read() if e["event"] == "error"]

    def test_the_unlock_runs_the_reconcile_it_deferred(self, clock, tmp_path):
        broker = self.CredentialBroker(clock=clock)
        service = ExecService(broker, ServiceConfig(state_dir=tmp_path, sha="t"), clock=clock)
        broker.bind(service.arming)
        service.unlock({"token": {"creation_timestamp": 1_757_000_000}})
        assert [c for c in broker.calls if c[0] == "positions"], "unlock must reconcile"

    def test_the_mock_still_reconciles_at_construction(self, broker, clock, tmp_path):
        ExecService(broker, ServiceConfig(state_dir=tmp_path, sha="t"), clock=clock)
        assert [c for c in broker.calls if c[0] == "positions"]


# ── a send with no answer (2026-09-15 audit, finding 25; st-xlz9) ─────────

class TestASendWithNoAnswer:
    """The broker took the order; the socket died before the answer. There
    was no `placed` line, so a retry of the same intent sent it again, and
    reconcile — a lookup on ids the service already held — never found the
    first. Now the intent is `sending` before the send, `send_unknown` after
    the error, held as unconfirmed, and the orphan sweep matches it to the
    broker's listing by contract, side, size, limit and time."""

    def test_the_timed_out_send_is_journaled_and_holds_the_door(self, armed, broker):
        broker.accept_then_fail_next = "read timed out"
        with pytest.raises(BrokerError, match="timed out"):
            armed.place(entry(intent_id="lost-1"))
        events = [e["event"] for e in armed.journal.find("lost-1")]
        assert events[-2:] == ["sending", "send_unknown"]
        assert [s["intent_id"] for s in armed.status()["unconfirmed_sends"]] == ["lost-1"]
        # While the listing cannot be read, nothing goes out — the same
        # intent again least of all (no `placed` line, so _replay is blind).
        broker.fail_next = "listing unavailable"
        again = armed.place(entry(intent_id="lost-1"))
        assert again["refused"]["bound"] == "send_unconfirmed"
        broker.fail_next = "listing unavailable"
        other = armed.place(entry(intent_id="lost-2", symbol=PUT))
        assert other["refused"]["bound"] == "send_unconfirmed"
        assert len(broker.calls_to("place")) == 1
        # Once the listing answers, the reconcile every place() runs first
        # finds the resting order, so the door is now shut by the slot.
        assert armed.place(entry(intent_id="lost-1"))["refused"]["bound"] == "positions"
        assert len(broker.calls_to("place")) == 1

    def test_reconcile_finds_the_resting_order_and_it_becomes_the_working_entry(
            self, armed, broker, clock):
        broker.accept_then_fail_next = "read timed out"
        with pytest.raises(BrokerError):
            armed.place(entry(intent_id="lost-1"))
        resting = broker.working_orders(CALL)[0]
        out = armed.reconcile()
        assert out["found"] == [{"intent_id": "lost-1", "outcome": "found",
                                 "order_id": resting.order_id, "status": "WORKING"}]
        assert armed.status()["unconfirmed_sends"] == []
        work = armed.status()["working"]
        assert [w["order_id"] for w in work] == [resting.order_id]
        assert work[0]["intent_id"] == "lost-1" and work[0]["stop_spx"] == SPX_NOW - 12.0
        resolved = armed.journal.events("send_resolved")
        assert resolved[0]["outcome"] == "found" and resolved[0]["order_id"] == resting.order_id
        # the slot is held: a new entry is refused on positions, not on the send
        assert armed.place(entry(intent_id="next", symbol=PUT))["refused"]["bound"] == "positions"
        # and when it fills, the usual promotion rests the bracket
        clock.advance(seconds=1)
        broker.fill_resting(resting.order_id)
        armed.reconcile()
        pos = armed.status()["positions"]
        assert pos and pos[0]["intent_id"] == "lost-1" and pos[0]["stop_order_id"]

    def test_a_send_the_broker_already_filled_becomes_the_position(self, armed, broker, clock):
        broker.accept_then_fail_next = "read timed out"
        with pytest.raises(BrokerError):
            armed.place(entry(intent_id="lost-1"))
        resting = broker.working_orders(CALL)[0]
        clock.advance(seconds=1)
        broker.fill_resting(resting.order_id)
        armed.reconcile()
        pos = armed.status()["positions"]
        assert [p["intent_id"] for p in pos] == ["lost-1"]
        assert pos[0]["stop_order_id"] and pos[0]["target_order_id"]
        assert armed.status()["unconfirmed_sends"] == [] and armed.status()["working"] == []

    def test_nothing_in_the_listing_after_the_settle_window_releases_the_intent(
            self, armed, broker, clock):
        real_place = broker.place

        def refuse_after_taking_nothing(intent):
            raise BrokerError("connect timed out")          # never reached the broker

        broker.place = refuse_after_taking_nothing
        with pytest.raises(BrokerError):
            armed.place(entry(intent_id="lost-1"))
        broker.place = real_place
        armed.reconcile()
        assert armed.status()["unconfirmed_sends"]            # too soon to say
        clock.advance(seconds=61)
        out = armed.reconcile()
        assert out["found"] == [{"intent_id": "lost-1", "outcome": "not-found", "order_id": None}]
        assert armed.journal.events("send_resolved")[0]["outcome"] == "not-found"
        # the intent may now be re-sent, and _replay does not answer it from the sending line
        broker.set_quote(CALL, bid=2.00, ask=2.10)          # a fresh quote after the clock moved
        broker.set_quote("$SPX", bid=SPX_NOW - 0.25, ask=SPX_NOW + 0.25, last=SPX_NOW)
        sent = armed.place(entry(intent_id="lost-1"))
        assert sent["order"]["status"] == "FILLED"

    def test_an_unconfirmed_send_survives_a_restart(self, armed, broker, clock, tmp_path):
        broker.accept_then_fail_next = "read timed out"
        with pytest.raises(BrokerError):
            armed.place(entry(intent_id="lost-1"))
        again = ExecService(broker, armed.config, clock=clock)
        # The mock needs no credential, so the start-up reconcile ran in the
        # constructor: the recovered send was swept and found at once. The
        # journal shows the recovery happened, not a fresh guess.
        assert again.status()["unconfirmed_sends"] == []
        assert [w["intent_id"] for w in again.status()["working"]] == ["lost-1"]
        assert again.journal.events("send_resolved")[-1]["outcome"] == "found"
        assert again.journal.events("recovered") == []      # it was not a position yet

    def test_a_working_buy_the_service_did_not_send_is_shown_not_adopted(self, armed, broker):
        from execd.intent import OrderIntent, OrderType, Side
        broker.rest_limits = True
        foreign = broker.place(OrderIntent(intent_id="hand-1", symbol=PUT, side=Side.BUY_TO_OPEN,
                                           qty=2, order_type=OrderType.LIMIT, limit=1.85,
                                           source="tos"))
        broker.calls.clear()
        armed.reconcile()
        armed.reconcile()
        shown = armed.status()["foreign_orders"]
        assert [o["order_id"] for o in shown] == [foreign.order_id]
        assert len(armed.journal.events("foreign_order")) == 1     # once, not per sweep
        assert armed.status()["working"] == [] and armed.status()["positions"] == []

    def test_an_unnamed_working_entry_is_identified_from_the_listing(self, armed, broker):
        """The transport names an order ``unnamed:<intent>`` when the 201
        carried no Location. Reconcile used to look that id up in a listing
        that could never contain it and hold the slot forever."""
        from dataclasses import replace as _replace
        broker.rest_limits = True
        armed.place(entry(intent_id="noloc-1"))
        real_id = broker.working_orders(CALL)[0].order_id
        # re-key what the service holds to the transport's synthetic id
        work = armed._working.pop(real_id)
        armed._working["unnamed:noloc-1"] = _replace(work, order_id="unnamed:noloc-1")
        out = armed.reconcile()
        assert out["found"] == [{"intent_id": "noloc-1", "outcome": "identified", "order_id": real_id}]
        assert [w["order_id"] for w in armed.status()["working"]] == [real_id]
        assert armed.journal.events("working_identified")[0]["old_order_id"] == "unnamed:noloc-1"


class TestACloseIsBookedOnce:
    """2026-09-16 10:19:29 CT (st-4b0p): the put's stop filled inside the
    fill sweep that reconcile runs, a second after reconcile had read the
    broker's positions. The stale snapshot still held the contract, so the
    position was adopted the moment it had been closed, and the next poll —
    whose window still covered the fill — booked the same order id against
    the adopted position. Three closes for two orders, the day's realized
    debited twice. Four minutes earlier the flatten's own market fill had
    come back through the sweep as ``unattributed_sell``. Same cause."""

    @staticmethod
    def stop_id(svc: ExecService) -> str:
        return svc.status()["positions"][0]["stop_order_id"]

    def test_a_stop_that_fills_inside_reconciles_own_sweep_is_not_adopted(
            self, armed, broker, clock, monkeypatch):
        armed.place(entry(intent_id="race-1", stop_spx=SPX_NOW - 2.0, delta=0.30))
        sid = self.stop_id(armed)
        clock.advance(seconds=5)
        real_fills_since = broker.fills_since
        crossed = {"done": False}

        def fills_since(since):
            # the paper book's sweep fills the stop while the fill window is
            # being read — after orders() and any positions() read before it
            if not crossed["done"]:
                crossed["done"] = True
                broker.fill_resting(sid)
            return real_fills_since(since)

        monkeypatch.setattr(broker, "fills_since", fills_since)
        out = armed.reconcile()
        assert out["adopted"] == []
        assert armed.status()["positions"] == []
        closed = armed.journal.events("closed")
        assert len(closed) == 1 and closed[0]["order_id"] == sid and closed[0]["pnl_usd"] == -60.0
        assert not armed.journal.events("position_adopted")
        assert armed.day_state().realized_loss_usd == 60.0

    def test_a_fill_the_broker_reports_twice_is_booked_once(self, armed, broker, clock):
        armed.place(entry(intent_id="twice-1", stop_spx=SPX_NOW - 2.0, delta=0.30))
        sid = self.stop_id(armed)
        clock.advance(seconds=5)
        broker.fill_resting(sid)
        first = armed.poll_fills()
        assert first["picked_up"][0]["order_id"] == sid
        armed._last_fill_poll = clock() - __import__("datetime").timedelta(minutes=5)   # the window re-covers it
        again = armed.poll_fills()
        assert again["picked_up"] == []
        assert len(armed.journal.events("closed")) == 1
        assert not armed.journal.events("unattributed_sell")

    def test_the_services_own_market_close_is_never_unattributed(self, armed, broker, clock):
        armed.place(entry(intent_id="flat-1", stop_spx=SPX_NOW - 2.0, delta=0.30))
        clock.advance(seconds=5)
        armed.flatten()
        exit_id = armed.journal.events("closed")[-1]["order_id"]
        armed._last_fill_poll = clock() - __import__("datetime").timedelta(minutes=5)
        armed.poll_fills()
        armed.reconcile()
        assert not armed.journal.events("unattributed_sell")
        assert len(armed.journal.events("closed")) == 1
        assert exit_id in armed._booked_exits

    def test_a_restart_remembers_what_was_booked(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="rec-once", stop_spx=SPX_NOW - 2.0, delta=0.30))
        sid = self.stop_id(first)
        clock.advance(seconds=5)
        broker.fill_resting(sid)
        first.poll_fills()
        assert len(first.journal.events("closed")) == 1

        second = ExecService(broker, config, clock=clock)
        second.unlock({"token": "x"})
        second._last_fill_poll = clock() - __import__("datetime").timedelta(minutes=5)
        second.poll_fills()
        assert len(second.journal.events("closed")) == 1
        assert not second.journal.events("unattributed_sell")


class TestTheLegsAreReconciled:
    """Audit finding 39 (st-vqmr): the leg ids were believed, never reconciled.
    A stop the broker cancelled, expired, rejected after acceptance, or Steve
    cancelled by hand in the Schwab app was reported resting until the next
    cancel, and a restart restored the id from the journal unchecked."""

    @staticmethod
    def pos(svc):
        return svc.status()["positions"][0]

    @staticmethod
    def kill(broker, order_id, status="CANCELED", word=None):
        from dataclasses import replace
        from execd.broker import OrderStatus
        broker._orders[order_id] = replace(broker._orders[order_id],
                                           status=OrderStatus[status], message=word or status)

    def test_a_stop_cancelled_by_hand_is_re_rested_loud(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        p = self.pos(armed)
        sid = p["stop_order_id"]
        self.kill(broker, sid)                       # by hand in the Schwab app
        out = armed.reconcile()
        assert out["legs"][0]["outcome"] == "canceled" and out["legs"][0]["rerested"]
        p2 = self.pos(armed)
        assert p2["stop_order_id"] and p2["stop_order_id"] != sid
        assert broker._orders[p2["stop_order_id"]].is_working
        assert p2["stop_price"] == p["stop_price"] and p2["stop_state"] == "resting"
        lost = armed.journal.events("leg_lost")[0]
        assert lost["order_id"] == sid and lost["kind"] == "protective-stop"
        assert lost["outcome"] == "canceled" and "re-resting" in lost["detail"]
        assert armed.journal.events("stop_placed")[-1]["kind"] == "re-rested"

    def test_an_expired_target_is_re_rested(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        p = self.pos(armed)
        tid = p["target_order_id"]
        self.kill(broker, tid, word="EXPIRED")       # the transport maps EXPIRED to CANCELED
        armed.reconcile()
        p2 = self.pos(armed)
        assert p2["target_order_id"] and p2["target_order_id"] != tid
        assert p2["target_price"] == p["target_price"] and p2["target_state"] == "resting"
        lost = armed.journal.events("leg_lost")[0]
        assert lost["kind"] == "take-profit" and lost["broker_status"] == "EXPIRED"
        assert armed.journal.events("target_placed")[-1]["kind"] == "re-rested"

    def test_a_leg_the_broker_kills_twice_is_left_off_loud(self, armed, broker, clock):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        self.kill(broker, self.pos(armed)["stop_order_id"])
        armed.reconcile()
        clock.advance(seconds=5)
        self.kill(broker, self.pos(armed)["stop_order_id"])
        armed.reconcile()
        p = self.pos(armed)
        assert p["stop_order_id"] is None and p["stop_state"] is None
        assert len(armed.journal.events("stop_placed")) == 2          # no third
        line = armed.journal.events("stop_unprotected")[-1]
        assert "again" in line["detail"] and "SPX-mark loop" in line["detail"]
        assert len(armed.status()["positions"]) == 1                  # still held, still watched

    def test_a_leg_found_filled_by_the_sweep_is_booked_as_the_close(self, armed, broker):
        """The fill sweep's window can miss a fill; the listing cannot."""
        from execd.broker import OrderStatus
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        p = self.pos(armed)
        sid, tid = p["stop_order_id"], p["target_order_id"]
        broker.fill_resting(sid)
        broker._fills.clear()                          # the sweep's window will not see it
        out = armed.reconcile()
        assert out["legs"][0]["outcome"] == "filled"
        assert armed.status()["positions"] == []
        closed = armed.journal.events("closed")[-1]
        assert closed["order_id"] == sid and closed["kind"] == "protective-stop"
        assert closed["exit_price"] == broker._orders[sid].fill_price
        assert broker._orders[tid].status is OrderStatus.CANCELED   # the other leg came off

    def test_a_leg_missing_from_the_listing_is_kept_and_said_after_the_window(
            self, armed, broker, clock):
        from execd.service import LEG_SETTLE_S
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        p = self.pos(armed)
        sid = p["stop_order_id"]
        saved = broker._orders.pop(sid)                # the listing lags, or the leg is gone
        assert armed.reconcile()["legs"] == []
        assert self.pos(armed)["stop_state"] == "resting"
        assert not armed.journal.events("leg_unaccounted")
        clock.advance(seconds=LEG_SETTLE_S + 1)
        out = armed.reconcile()
        assert out["legs"] == [{"symbol": CALL, "leg": "protective-stop",
                                "order_id": sid, "outcome": "unaccounted"}]
        p2 = self.pos(armed)
        assert p2["stop_order_id"] == sid and p2["stop_state"] == "unaccounted"
        assert len(armed.journal.events("stop_placed")) == 1          # not re-rested
        armed.reconcile()
        assert len(armed.journal.events("leg_unaccounted")) == 1      # said once
        assert "UPDATE the stop" in armed.journal.events("leg_unaccounted")[0]["detail"]
        broker._orders[sid] = saved                    # back in the listing
        armed.reconcile()
        assert self.pos(armed)["stop_state"] == "resting"
        assert armed.journal.events("leg_listed")[0]["order_id"] == sid

    def test_a_terminal_leg_is_not_re_rested_while_a_close_is_in_flight(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        pos = armed._open[CALL]
        broker.rest_market = True
        close = broker.place(exit_intent())            # a market sell working at the broker
        pos.exit_order_id, pos.exit_reason = close.order_id, "spx-stop"
        self.kill(broker, pos.stop_order_id)
        out = armed.reconcile()
        row = [r for r in out["legs"] if r["leg"] == "protective-stop"][0]
        assert row["outcome"] == "canceled" and row["rerested"] is None
        assert pos.stop_order_id is None
        assert len(armed.journal.events("stop_placed")) == 1
        assert "close is in flight" in armed.journal.events("leg_lost")[0]["detail"]

    def test_a_restart_checks_the_leg_ids_it_recovered(self, broker, clock, tmp_path):
        """_recover restored stop_order_id from the last stop_placed line with
        no check (04 §5, second bullet). The reconcile the unlock runs now
        looks it up."""
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="rec-leg", stop_spx=SPX_NOW - 2.0, delta=0.30))
        sid = self.pos(first)["stop_order_id"]
        self.kill(broker, sid)                         # cancelled by hand while the box was down
        second = ExecService(broker, config, clock=clock)   # recovers the id, then reconciles
        second.unlock({"token": "x"})
        p = self.pos(second)
        assert p["stop_order_id"] and p["stop_order_id"] != sid
        assert broker._orders[p["stop_order_id"]].is_working
        assert second.journal.events("leg_lost")[0]["order_id"] == sid
