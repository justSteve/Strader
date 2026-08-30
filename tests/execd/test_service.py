"""ExecService end to end against the mock broker. [st-eznu]

Stage 1 is done when this file passes: the whole service runs, every bound
refuses, the protective stop is placed on every fill, the day's ceiling holds
across a restart, and the two ways out — Steve's flatten and the SPX-mark
exit — work in the states that block everything else.

Nothing here reaches a network. ``MockBroker`` fills deterministically and
records every call, so "the service did not transmit" is asserted against the
call log rather than inferred from an absent exception.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from execd.arming import ArmState
from execd.bounds import Bounds
from execd.broker import BrokerError, MockBroker
from execd.intent import OrderIntent, OrderType, Side
from execd.service import ExecService, OpenPosition, Refused, ServiceConfig

from .conftest import CALL, PUT, SPX_NOW, entry, exit_intent


def sent_orders(broker: MockBroker) -> list[dict]:
    return broker.calls_to("place")


class TestTheEntryPath:
    def test_a_good_entry_fills_and_is_journaled(self, armed, broker):
        out = armed.place(entry())
        assert out["refused"] is None
        assert out["order"]["status"] == "FILLED"
        assert out["order"]["fill_price"] == 2.10
        events = [e["event"] for e in armed.journal.read()]
        assert events == ["unlock", "request", "preview", "placed", "filled",
                          "stop_placed"]

    def test_the_fill_becomes_a_tracked_position(self, armed):
        armed.place(entry())
        assert armed.status()["positions"][0]["symbol"] == CALL
        assert armed.day_state().open_positions == 1

    def test_a_refused_entry_transmits_nothing(self, armed, broker):
        out = armed.place(entry(qty=99))
        assert out["refused"]["bound"] == "qty"
        assert sent_orders(broker) == []

    def test_a_locked_service_refuses_and_transmits_nothing(self, service, broker):
        out = service.place(entry())
        assert out["refused"]["bound"] == "armed"
        assert sent_orders(broker) == []

    def test_a_stood_down_service_refuses_an_entry(self, armed, broker):
        armed.stand_down()
        assert armed.place(entry())["refused"]["bound"] == "armed"
        assert sent_orders(broker) == []

    def test_the_kill_file_refuses_an_entry(self, armed, broker):
        armed.stop()
        assert armed.place(entry())["refused"]["bound"] == "stop"
        assert sent_orders(broker) == []

    def test_a_second_position_is_refused_while_one_is_open(self, armed):
        armed.place(entry(intent_id="t-1"))
        out = armed.place(entry(intent_id="t-2", symbol=PUT, limit=1.90,
                                stop_spx=SPX_NOW + 12, delta=0.28))
        assert out["refused"]["bound"] == "positions"

    def test_a_broker_rejection_is_recorded_and_leaves_no_position(self, armed, broker):
        broker.reject_next = "buying power"
        out = armed.place(entry())
        assert out["order"]["status"] == "REJECTED"
        assert armed.status()["positions"] == []
        assert [e["event"] for e in armed.journal.read()][-1] == "rejected"

    def test_an_unfilled_limit_places_no_protective_stop_yet(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry())
        assert out["order"]["status"] == "WORKING"
        assert out["stop_order"] is None
        assert armed.status()["positions"] == []


class TestThePreviewGate:
    def test_a_preview_that_costs_more_than_the_intent_stops_the_send(self, armed, broker, monkeypatch):
        from execd.broker import Preview

        def dear(intent):
            return Preview(intent.symbol, intent.side, intent.qty, intent.order_type,
                           price=3.50, cost_usd=350.0, commission_usd=0.65)

        monkeypatch.setattr(broker, "preview", dear)
        out = armed.place(entry(limit=2.10))
        assert out["refused"]["bound"] == "preview_cost"
        assert sent_orders(broker) == []

    def test_a_preview_the_broker_will_not_accept_stops_the_send(self, armed, broker, monkeypatch):
        from execd.broker import Preview

        def refused(intent):
            return Preview(intent.symbol, intent.side, intent.qty, intent.order_type,
                           price=2.10, cost_usd=210.0, accepted=False,
                           messages=("market closed",))

        monkeypatch.setattr(broker, "preview", refused)
        out = armed.place(entry())
        assert out["refused"]["bound"] == "preview_cost"
        assert "market closed" in out["refused"]["reason"]
        assert sent_orders(broker) == []

    def test_preview_prices_without_transmitting(self, armed, broker):
        out = armed.preview(entry())
        assert out["refused"] is None
        assert out["preview"]["cost_usd"] == 210.0
        assert sent_orders(broker) == []

    def test_preview_reports_a_refusal_without_pricing_it(self, armed, broker):
        out = armed.preview(entry(qty=99))
        assert out["refused"]["bound"] == "qty"
        assert broker.calls_to("preview") == []


class TestIdempotency:
    def test_a_repeated_intent_id_is_answered_from_the_journal(self, armed, broker):
        first = armed.place(entry(intent_id="dup-1"))
        second = armed.place(entry(intent_id="dup-1"))
        assert second["replayed"] is True
        assert second["order"]["order_id"] == first["order"]["order_id"]

    def test_a_repeat_sends_nothing_to_the_broker(self, armed, broker):
        armed.place(entry(intent_id="dup-1"))
        before = len(sent_orders(broker))
        armed.place(entry(intent_id="dup-1"))
        assert len(sent_orders(broker)) == before

    def test_the_replay_is_journaled_so_the_duplicate_is_visible(self, armed):
        armed.place(entry(intent_id="dup-1"))
        armed.place(entry(intent_id="dup-1"))
        assert armed.journal.read()[-1]["event"] == "replayed"

    def test_a_refused_intent_id_may_be_retried(self, armed, clock):
        """A refusal has no side effect, so a caller that fixes the reason —
        here, waiting for the session to open — is not locked out by its id."""
        clock.set_ct(7, 0)
        assert armed.place(entry(intent_id="retry-1"))["refused"]["bound"] == "window"
        clock.set_ct(10, 0)
        assert armed.place(entry(intent_id="retry-1"))["refused"] is None

    def test_a_different_id_for_the_same_contract_is_a_second_order(self, armed, broker):
        armed.place(entry(intent_id="a-1"))
        armed.flatten()
        armed.place(entry(intent_id="a-2"))
        assert len(sent_orders(broker)) >= 3


class TestTheProtectiveStop:
    def test_a_resting_stop_is_placed_on_every_fill(self, armed, broker):
        out = armed.place(entry())
        assert out["stop_order"]["status"] == "WORKING"
        assert out["stop_order"]["order_type"] == "STOP"
        assert broker.working_orders(CALL)

    def test_its_price_is_the_spx_stop_walked_through_delta(self, armed):
        # 6380 - 6368 = 12 SPX points at 0.30 delta = 3.60; a 2.10 fill floors at one tick.
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        line = armed.journal.events("stop_placed")[0]
        assert line["stop_price"] == 1.50      # 2.10 - (2 × 0.30)

    def test_the_stop_is_journaled_with_the_risk_it_caps(self, armed):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        line = armed.journal.events("stop_placed")[0]
        assert line["risk_usd"] == 60.0
        assert line["stop_spx"] == SPX_NOW - 2.0 and line["delta"] == 0.30

    def test_an_entry_whose_stop_sign_is_transposed_is_refused_before_the_send(self, armed, broker):
        # a CALL stop ABOVE spot is already triggered
        out = armed.place(entry(stop_spx=SPX_NOW + 12))
        assert out["refused"]["bound"] == "protective_stop"
        assert "transposed" in out["refused"]["reason"]
        assert sent_orders(broker) == []

    def test_an_entry_is_refused_when_the_index_mark_is_missing(self, armed, broker):
        broker._quotes.pop("$SPX")
        out = armed.place(entry())
        assert out["refused"]["bound"] == "protective_stop"
        assert sent_orders(broker) == []

    def test_a_broker_that_refuses_the_resting_stop_is_loud(self, armed, broker, monkeypatch):
        """The position is live and unprotected. That must be in the journal
        under its own event, not swallowed as a warning."""
        real_place = broker.place
        calls = {"n": 0}

        def place(intent):
            calls["n"] += 1
            if intent.order_type is OrderType.STOP:
                raise BrokerError("stop rejected")
            return real_place(intent)

        monkeypatch.setattr(broker, "place", place)
        out = armed.place(entry())
        assert out["order"]["status"] == "FILLED"
        assert out["stop_order"] is None
        assert armed.journal.events("stop_unprotected")[0]["symbol"] == CALL

    def test_the_resting_stop_is_cancelled_when_the_position_closes(self, armed, broker):
        armed.place(entry())
        stop_id = armed.status()["positions"][0]["stop_order_id"]
        armed.flatten()
        assert not broker.working_orders(CALL)
        assert any(c["order_id"] == stop_id for c in broker.calls_to("cancel"))


class TestTheExitPath:
    def test_a_close_books_the_pnl(self, armed):
        armed.place(entry(limit=2.10))
        out = armed.place(exit_intent())
        # bought at 2.10, market sell hits the 2.00 bid
        assert out["closed"]["pnl_usd"] == -10.0
        assert armed.status()["positions"] == []

    def test_a_winning_close_is_booked_too(self, armed, broker):
        armed.place(entry(limit=2.10))
        broker.set_quote(CALL, bid=4.00, ask=4.10)
        out = armed.place(exit_intent())
        assert out["closed"]["pnl_usd"] == 190.0

    def test_an_exit_works_while_the_kill_file_is_on(self, armed, broker):
        armed.place(entry())
        armed.stop()
        assert armed.place(exit_intent())["closed"]["closed"] is True

    def test_an_exit_works_while_stood_down(self, armed):
        armed.place(entry())
        armed.stand_down()
        assert armed.place(exit_intent())["closed"]["closed"] is True

    def test_an_exit_works_outside_the_session_window(self, armed, clock):
        armed.place(entry())
        clock.set_ct(17, 30)
        assert armed.place(exit_intent())["closed"]["closed"] is True

    def test_an_exit_works_with_the_daily_ceiling_breached(self, armed):
        armed.place(entry())
        armed.journal.record("closed", symbol="other", pnl_usd=-500.0)
        assert armed.place(exit_intent())["closed"]["closed"] is True

    def test_a_locked_service_cannot_exit_because_it_has_nothing_to_send_with(self, armed, broker):
        armed.place(entry())
        armed.lock()
        out = armed.place(exit_intent())
        assert out["refused"]["bound"] == "armed"

    def test_an_exit_that_would_open_risk_is_refused(self, armed):
        armed.place(entry())
        opening = OrderIntent("x-1", CALL, Side.BUY_TO_OPEN, 1,
                              order_type=OrderType.MARKET, source="test")
        # arrives on the entry path and is refused for its order type
        assert armed.place(opening)["refused"]["bound"] == "order_type"


class TestPartialExits:
    """A real broker fills part of an order; the mock does it on request. The
    hazard is the resting stop, which was sized for the whole position and
    would sell contracts Steve no longer owns if it triggered on the rest."""

    @pytest.fixture
    def two_lot(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha",
                               bounds=Bounds(qty_cap=2))
        svc = ExecService(broker, config, clock=clock)
        svc.unlock({"token": "x"})
        svc.place(entry(intent_id="two-1", qty=2, stop_spx=SPX_NOW - 2.0, delta=0.30))
        return svc

    def test_the_entry_stop_is_sized_to_the_position(self, two_lot):
        assert two_lot.journal.events("stop_placed")[0]["qty"] == 2

    def test_a_partial_exit_leaves_the_position_open(self, two_lot, broker):
        broker.partial_fill_qty = 1
        out = two_lot.place(exit_intent(intent_id="two-1-x", qty=2))
        assert out["closed"]["closed"] is False
        assert out["closed"]["remaining_qty"] == 1
        assert two_lot.status()["positions"][0]["qty"] == 1

    def test_a_partial_exit_replaces_the_stop_at_the_smaller_size(self, two_lot, broker):
        broker.partial_fill_qty = 1
        two_lot.place(exit_intent(intent_id="two-1-x", qty=2))
        resting = broker.working_orders(CALL)
        assert len(resting) == 1 and resting[0].qty == 1
        assert two_lot.journal.events("stop_placed")[-1]["kind"] == "resized"

    def test_the_oversized_stop_is_cancelled_not_left_behind(self, two_lot, broker):
        broker.partial_fill_qty = 1
        first_stop = two_lot.status()["positions"][0]["stop_order_id"]
        two_lot.place(exit_intent(intent_id="two-1-x", qty=2))
        assert any(c["order_id"] == first_stop for c in broker.calls_to("cancel"))

    def test_the_partial_loss_debits_the_ceiling_immediately(self, two_lot, broker):
        broker.partial_fill_qty = 1
        two_lot.place(exit_intent(intent_id="two-1-x", qty=2))
        # one lot bought at 2.10, sold at the 2.00 bid
        assert two_lot.day_state().realized_loss_usd == 10.0

    def test_the_position_slot_is_not_freed_until_nothing_is_left(self, two_lot, broker):
        broker.partial_fill_qty = 1
        two_lot.place(exit_intent(intent_id="two-1-x", qty=2))
        assert two_lot.day_state().open_positions == 1
        two_lot.place(exit_intent(intent_id="two-1-y", qty=1))
        assert two_lot.day_state().open_positions == 0

    def test_the_rest_closes_normally(self, two_lot, broker):
        broker.partial_fill_qty = 1
        two_lot.place(exit_intent(intent_id="two-1-x", qty=2))
        out = two_lot.place(exit_intent(intent_id="two-1-y", qty=1))
        assert out["closed"]["closed"] is True
        assert two_lot.status()["positions"] == []
        assert broker.working_orders(CALL) == []

    def test_selling_more_than_is_held_is_refused(self, armed, broker):
        armed.place(entry(intent_id="one-1"))
        out = armed.place(exit_intent(intent_id="one-1-x", qty=5))
        assert out["refused"]["bound"] == "qty"
        assert "short" in out["refused"]["reason"]

    def test_a_partially_filled_resting_stop_gets_a_new_one_for_the_rest(
            self, two_lot, broker, clock):
        """The stop itself can fill partly. What is left is then running with
        no stop at all unless the service notices."""
        stop_id = two_lot.status()["positions"][0]["stop_order_id"]
        clock.advance(minutes=5)
        broker._orders[stop_id] = replace(broker._orders[stop_id], qty=1)
        broker.trigger_stop(stop_id)

        out = two_lot.poll_fills()
        assert out["picked_up"][0]["remaining_qty"] == 1
        resting = broker.working_orders(CALL)
        assert len(resting) == 1 and resting[0].qty == 1
        assert two_lot.status()["positions"][0]["qty"] == 1


class TestFlatten:
    def test_flatten_closes_every_position_at_market(self, armed, broker):
        armed.place(entry())
        out = armed.flatten()
        assert out["closed"][0]["closed"] is True
        assert armed.status()["positions"] == []
        assert broker.positions() == []

    def test_flatten_works_while_killed(self, armed):
        armed.place(entry())
        armed.stop()
        assert armed.flatten()["closed"][0]["closed"] is True

    def test_flatten_works_while_stood_down(self, armed):
        armed.place(entry())
        armed.stand_down()
        assert armed.flatten()["closed"][0]["closed"] is True

    def test_flatten_works_after_the_bell(self, armed, clock):
        armed.place(entry())
        clock.set_ct(16, 0)
        assert armed.flatten()["closed"][0]["closed"] is True

    def test_flatten_with_nothing_open_is_a_no_op_not_an_error(self, armed):
        assert armed.flatten() == {"refused": None, "closed": [], "errors": []}

    def test_flatten_on_a_locked_service_raises_rather_than_pretending(self, service):
        with pytest.raises(Refused) as exc:
            service.flatten()
        assert exc.value.refusal.bound == "armed"

    def test_a_broker_failure_on_one_position_does_not_abandon_the_rest(
            self, armed, broker, monkeypatch):
        armed.place(entry())
        armed._open["EXTRA"] = OpenPosition(
            symbol=PUT, qty=1, entry_price=1.90, intent_id="ghost", right="P")
        real_place = broker.place

        def place(intent):
            if intent.symbol == PUT:
                raise BrokerError("no route")
            return real_place(intent)

        monkeypatch.setattr(broker, "place", place)
        out = armed.flatten()
        assert len(out["closed"]) == 1 and len(out["errors"]) == 1
        assert out["errors"][0]["symbol"] == PUT


class TestTheSpxExitLoop:
    def test_observe_fires_the_exit_when_the_index_reaches_the_stop(self, armed):
        armed.place(entry(stop_spx=SPX_NOW - 12))
        out = armed.observe(SPX_NOW - 12.5)
        assert out["fired"][0]["closed"] is True
        assert armed.status()["positions"] == []

    def test_observe_does_nothing_short_of_the_level(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 12))
        before = len(sent_orders(broker))
        assert armed.observe(SPX_NOW - 11.0)["fired"] == []
        assert len(sent_orders(broker)) == before

    def test_a_put_fires_on_the_way_up(self, armed, broker):
        armed.place(entry(symbol=PUT, limit=1.90, stop_spx=SPX_NOW + 12, delta=0.28))
        assert armed.observe(SPX_NOW + 12.5)["fired"][0]["closed"] is True

    def test_firing_cancels_the_resting_stop(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 12))
        armed.observe(SPX_NOW - 12.5)
        assert not broker.working_orders(CALL)

    def test_the_exit_is_journaled_with_the_level_that_fired_it(self, armed):
        armed.place(entry(stop_spx=SPX_NOW - 12))
        armed.observe(SPX_NOW - 12.5)
        line = armed.journal.events("exit_triggered")[0]
        assert line["spx"] == SPX_NOW - 12.5 and line["stop_spx"] == SPX_NOW - 12


class TestPollFills:
    def test_a_resting_stop_that_triggers_is_picked_up(self, armed, broker, clock):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        stop_id = armed.status()["positions"][0]["stop_order_id"]
        clock.advance(minutes=5)
        broker.trigger_stop(stop_id)
        out = armed.poll_fills()
        assert out["picked_up"][0]["order_id"] == stop_id
        assert out["picked_up"][0]["exit_price"] == 1.50
        assert armed.status()["positions"] == []

    def test_the_loss_debits_the_days_ceiling(self, armed, broker, clock):
        armed.place(entry(limit=2.10, stop_spx=SPX_NOW - 2.0, delta=0.30))
        stop_id = armed.status()["positions"][0]["stop_order_id"]
        clock.advance(minutes=5)
        broker.trigger_stop(stop_id)
        armed.poll_fills()
        assert armed.day_state().realized_loss_usd == 60.0

    def test_nothing_to_pick_up_is_quiet(self, armed, clock):
        armed.place(entry())
        clock.advance(minutes=5)
        assert armed.poll_fills() == {"picked_up": []}

    def test_a_broker_outage_is_reported_not_raised(self, armed, broker, clock):
        armed.place(entry())
        clock.advance(minutes=5)
        broker.fail_next = "connection reset"
        out = armed.poll_fills()
        assert "connection reset" in out["error"]
        assert armed.journal.events("error")


class TestTheDailyCeiling:
    def test_two_losses_spend_the_attempts(self, armed, broker):
        for i in range(2):
            armed.place(entry(intent_id=f"a-{i}"))
            armed.flatten()
        out = armed.place(entry(intent_id="a-2"))
        assert out["refused"]["bound"] == "ceiling"
        assert "attempts" in out["refused"]["reason"]

    def test_the_loss_ceiling_refuses_before_the_attempts_run_out(self, armed):
        armed.journal.record("filled", kind="entry", symbol=PUT, qty=1, price=2.0)
        armed.journal.record("closed", symbol=PUT, pnl_usd=-100.0)
        out = armed.place(entry(intent_id="after-loss"))
        assert out["refused"]["bound"] == "ceiling"
        assert "$100.00" in out["refused"]["reason"]

    def test_the_ceiling_survives_a_restart(self, broker, clock, tmp_path):
        """A restart that reset the budget would hand Steve a fresh $100 of
        loss and two fresh attempts. This box restarts."""
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="pre-restart"))
        first.flatten()

        second = ExecService(broker, config, clock=clock)
        second.unlock({"token": "x"})
        assert second.day_state().attempts_used == 1
        assert second.status()["day"]["attempts_left"] == 1

    def test_status_reports_the_headroom(self, armed):
        armed.journal.record("filled", kind="entry", symbol=PUT, qty=1, price=2.0)
        armed.journal.record("closed", symbol=PUT, pnl_usd=-35.0)
        day = armed.status()["day"]
        assert day["realized_loss_usd"] == 35.0
        assert day["loss_headroom_usd"] == 65.0


class TestRecoveryAfterRestart:
    def test_an_open_position_is_recovered_so_flatten_can_still_reach_it(
            self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="live-1"))

        second = ExecService(broker, config, clock=clock)
        assert second.status()["positions"][0]["symbol"] == CALL
        second.unlock({"token": "x"})
        assert second.flatten()["closed"][0]["closed"] is True

    def test_the_recovered_position_keeps_its_stop_level_so_observe_still_works(
            self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="live-1", stop_spx=SPX_NOW - 12))

        second = ExecService(broker, config, clock=clock)
        second.unlock({"token": "x"})
        assert second.observe(SPX_NOW - 12.5)["fired"][0]["closed"] is True

    def test_a_service_comes_back_locked(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        second = ExecService(broker, config, clock=clock)
        assert second.arming.state is ArmState.LOCKED

    def test_a_position_whose_stop_never_rested_is_still_recovered_watchable(
            self, broker, clock, tmp_path, monkeypatch):
        """If the resting stop failed to place, the SPX-mark loop is the only
        protection left — so a restart must recover the level to watch, not
        just the position."""
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        real_place = broker.place

        def place(intent):
            if intent.order_type is OrderType.STOP:
                raise BrokerError("stop rejected")
            return real_place(intent)

        monkeypatch.setattr(broker, "place", place)
        first.place(entry(intent_id="live-1", stop_spx=SPX_NOW - 12))
        assert first.journal.events("stop_unprotected")

        monkeypatch.setattr(broker, "place", real_place)
        second = ExecService(broker, config, clock=clock)
        second.unlock({"token": "x"})
        assert second.status()["positions"][0]["stop_spx"] == SPX_NOW - 12
        assert second.observe(SPX_NOW - 12.5)["fired"][0]["closed"] is True

    def test_a_partially_closed_position_recovers_at_its_remaining_size(
            self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha",
                               bounds=Bounds(qty_cap=2))
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="two-1", qty=2, stop_spx=SPX_NOW - 2.0, delta=0.30))
        broker.partial_fill_qty = 1
        first.place(exit_intent(intent_id="two-1-x", qty=2))

        second = ExecService(broker, config, clock=clock)
        assert second.status()["positions"][0]["qty"] == 1

    def test_a_closed_position_is_not_resurrected(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="live-1"))
        first.flatten()
        second = ExecService(broker, config, clock=clock)
        assert second.status()["positions"] == []


class TestTheJournalReproducesTheDay:
    def test_a_full_round_trip_reads_back_in_order(self, armed, broker):
        armed.place(entry(intent_id="day-1"))
        armed.observe(SPX_NOW - 12.5)
        armed.stand_down()
        events = [e["event"] for e in armed.journal.read()]
        assert events == [
            "unlock", "request", "preview", "placed", "filled", "stop_placed",
            "exit_triggered", "placed", "closed", "canceled", "stand_down",
        ]

    def test_every_line_carries_the_installed_sha(self, armed):
        armed.place(entry())
        assert {e["sha"] for e in armed.journal.read()} == {"testsha"}

    def test_a_refusal_names_its_bound_in_the_journal(self, armed):
        armed.place(entry(qty=99))
        refused = armed.journal.events("refused")[0]
        assert refused["refused"] == {"bound": "qty",
                                      "reason": "99 contracts is over the 1-contract cap"}

    def test_the_journal_never_carries_the_credential(self, armed):
        armed.unlock({"refresh_token": "sekrit-value"})
        armed.place(entry())
        assert "sekrit" not in armed.journal.path_for().read_text()


class TestCancel:
    def test_cancel_pulls_a_working_order(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry())
        result = armed.cancel(out["order"]["order_id"])
        assert result["order"]["status"] == "CANCELED"

    def test_cancel_is_legal_while_killed(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry())
        armed.stop()
        assert armed.cancel(out["order"]["order_id"])["order"]["status"] == "CANCELED"

    def test_cancel_on_a_locked_service_raises(self, service):
        with pytest.raises(Refused):
            service.cancel("mock-0001")

    def test_cancelling_an_unknown_order_reaches_the_broker_and_fails_loudly(self, armed):
        with pytest.raises(BrokerError):
            armed.cancel("no-such-order")
