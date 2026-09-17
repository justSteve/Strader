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
        assert events == ["unlock", "request", "preview", "sending", "placed", "filled",
                          "stop_placed", "target_placed"]

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
        here, STOP cleared — is not locked out by its id. (Used to wait for
        the open; the window no longer gates SPX, Steve 2026-09-14.)"""
        armed.stop()
        assert armed.place(entry(intent_id="retry-1"))["refused"]["bound"] == "stop"
        armed.resume()
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

    def test_a_quote_with_no_price_in_it_is_no_mark(self, armed, broker):
        """``last or mid`` used to hand back 0.0 for an empty quote, and every
        caller then compared a stop to the index at zero (finding 32)."""
        broker.set_quote("$SPX", bid=0.0, ask=0.0, last=0.0)
        with pytest.raises(BrokerError, match="no usable"):
            armed.spx_mark()
        out = armed.place(entry())
        assert out["refused"]["bound"] == "protective_stop"
        assert sent_orders(broker) == []

    def test_an_entry_whose_cut_is_crossed_while_it_is_priced_is_refused_at_the_send(
            self, armed, broker, monkeypatch):
        """Finding 32 (st-xv5e): cycle 1 on 2026-09-14 passed the consistency
        check on one mark, the broker previewed, and the send read a fresh
        mark already through the cut — the position was born past it. The
        cut is checked again on the mark the send is journaled with."""
        real_preview = broker.preview

        def preview(intent):
            out = real_preview(intent)
            # the index moves through the cut during the preview round trip
            broker.set_quote("$SPX", bid=SPX_NOW - 12.75, ask=SPX_NOW - 12.25,
                             last=SPX_NOW - 12.5)
            return out

        monkeypatch.setattr(broker, "preview", preview)
        out = armed.place(entry(stop_spx=SPX_NOW - 12))
        assert out["refused"]["bound"] == "protective_stop"
        assert "moved through the cut" in out["refused"]["reason"]
        assert sent_orders(broker) == []
        assert armed.status()["positions"] == []
        line = armed.journal.events("refused")[-1]
        assert line["kind"] == "place" and "moved through the cut" in line["refused"]["reason"]

    def test_a_mark_lost_during_the_preview_refuses_the_send(self, armed, broker, monkeypatch):
        real_preview = broker.preview

        def preview(intent):
            out = real_preview(intent)
            broker._quotes.pop("$SPX")
            return out

        monkeypatch.setattr(broker, "preview", preview)
        out = armed.place(entry())
        assert out["refused"]["bound"] == "protective_stop"
        assert "at the send" in out["refused"]["reason"]
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
        resting = [o for o in broker.working_orders(CALL) if o.order_type is OrderType.STOP]
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
        resting = [o for o in broker.working_orders(CALL) if o.order_type is OrderType.STOP]
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

    def test_a_zero_mark_fires_nothing(self, armed, broker):
        """Finding 32 (st-xv5e): at spx == 0 every long call is past its cut,
        and observe() used to market-sell each one for nothing."""
        armed.place(entry(stop_spx=SPX_NOW - 12))
        before = len(sent_orders(broker))
        out = armed.observe(0.0)
        assert out["fired"] == [] and "not a price" in out["refused"]
        assert len(sent_orders(broker)) == before
        assert len(armed.status()["positions"]) == 1
        line = armed.journal.events("mark_refused")[0]
        assert line["spx"] == 0.0 and "not a price" in line["detail"]

    @pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "seven"])
    def test_a_mark_that_is_not_a_price_fires_nothing(self, armed, broker, bad):
        armed.place(entry(stop_spx=SPX_NOW - 12))
        out = armed.observe(bad)
        assert out["fired"] == [] and out["refused"]
        assert len(armed.status()["positions"]) == 1

    def test_a_mark_far_from_the_last_is_refused_until_the_window_passes(
            self, armed, broker, clock):
        """A quote that is wrong rather than moved fires the same way a real
        move does. Inside the window the resting bracket is the exit; a
        genuine gap is accepted once the window has passed."""
        from execd.service import MARK_BAND_WINDOW_S
        armed.place(entry(stop_spx=SPX_NOW - 12))
        assert armed.observe(SPX_NOW)["refused"] is None
        clock.advance(seconds=5)
        out = armed.observe(SPX_NOW * 0.98)         # 2 % in five seconds
        assert out["fired"] == [] and "from the last mark accepted" in out["refused"]
        assert len(armed.status()["positions"]) == 1
        assert len(armed.journal.events("mark_refused")) == 1
        clock.advance(seconds=5)
        assert armed.observe(SPX_NOW * 0.98)["refused"]   # still inside the window
        assert len(armed.journal.events("mark_refused")) == 1   # one line per streak
        clock.advance(seconds=MARK_BAND_WINDOW_S)
        out = armed.observe(SPX_NOW * 0.98)
        assert out["refused"] is None and out["fired"][0]["closed"] is True
        assert armed.journal.events("mark_accepted")[0]["refused"] == 2

    def test_a_mark_inside_the_band_is_acted_on(self, armed, broker, clock):
        armed.place(entry(stop_spx=SPX_NOW - 12))
        assert armed.observe(SPX_NOW)["refused"] is None
        clock.advance(seconds=5)
        out = armed.observe(SPX_NOW - 12.5)          # ~0.2 %: a move, not a bad quote
        assert out["refused"] is None and out["fired"][0]["closed"] is True

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
        armed.journal.record("closed", symbol=PUT, pnl_usd=-500.0)
        out = armed.place(entry(intent_id="after-loss"))
        assert out["refused"]["bound"] == "ceiling"
        assert "$500.00" in out["refused"]["reason"]

    def test_the_ceiling_survives_a_restart(self, broker, clock, tmp_path):
        """A restart that reset the budget would hand Steve a fresh $500 of
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

    def test_an_entry_that_can_lose_more_than_the_day_has_left_never_sends(
            self, armed, broker):
        """Finding 6, and it is checked while refusing is still free — the
        broker sees nothing. A $2.10 limit down to its $0.05 stop is $205, and
        the day has $150 left."""
        armed.journal.record("filled", kind="entry", symbol=PUT, qty=1, price=2.0)
        armed.journal.record("closed", symbol=PUT, pnl_usd=-350.0)
        out = armed.place(entry(intent_id="over-budget"))
        assert out["refused"]["bound"] == "ceiling"
        assert "$205.00" in out["refused"]["reason"]
        assert sent_orders(broker) == []

    def test_the_same_entry_passes_with_the_day_untouched(self, armed):
        assert armed.place(entry(intent_id="in-budget"))["refused"] is None

    def test_a_fill_too_cheap_to_leave_room_for_a_stop_is_refused_before_it_sends(
            self, armed, broker):
        """Finding 12. The stop price was derived only after the fill, so a
        contract this cheap became a live position with no stop under it and a
        journal line about it. It is now refused while nothing is at risk."""
        cheap = "SPXW  260826C06500000"
        broker.set_quote(cheap, bid=0.05, ask=0.05)
        out = armed.place(entry(intent_id="too-cheap", symbol=cheap, limit=0.05,
                                stop_spx=SPX_NOW - 12, delta=0.30))
        assert out["refused"]["bound"] == "protective_stop"
        assert "no resting stop can be derived" in out["refused"]["reason"]
        assert sent_orders(broker) == []

    def test_status_reports_the_headroom(self, armed):
        armed.journal.record("filled", kind="entry", symbol=PUT, qty=1, price=2.0)
        armed.journal.record("closed", symbol=PUT, pnl_usd=-35.0)
        day = armed.status()["day"]
        assert day["realized_loss_usd"] == 35.0
        assert day["loss_headroom_usd"] == 465.0


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
        # The bracket's cancels precede the close's placement since st-97z1
        # (the stop) and st-fn5y (the take-profit): the legs are designed to
        # fire at the same prices the close is sent at, so none may be live at
        # the broker beside it.
        assert events == [
            "unlock", "request", "preview", "sending", "placed", "filled", "stop_placed",
            "target_placed", "exit_triggered", "canceled", "canceled", "placed",
            "closed", "stand_down",
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


class TestTheCeilingCountsWhatIsHeld:
    """Audit finding 40 (st-s2jj): check_risk_budget and adjust subtracted
    realized loss only, so the 'sum of the day's worst cases' claim held by
    max_open_positions being 1. Pinned here at 2."""

    def svc(self, broker, clock, tmp_path, ceiling: float):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha",
                               bounds=Bounds(daily_loss_ceiling_usd=ceiling, max_open_positions=2))
        svc = ExecService(broker, config, clock=clock)
        svc.unlock({"token": "x"})
        # the call: 2.10 in, stop 1.50 → $60 at risk
        svc.place(entry(intent_id="held-call", stop_spx=SPX_NOW - 2.0, delta=0.30))
        assert svc.journal.events("stop_placed")[0]["risk_usd"] == 60.0
        return svc

    @staticmethod
    def put():
        # 1.90 in, stop 1.35 (on the grid) → $55 at risk
        return entry(intent_id="held-put", symbol=PUT, limit=1.90, stop_spx=SPX_NOW + 2.0, delta=0.28)

    def test_a_second_entry_must_fit_beside_the_first(self, broker, clock, tmp_path):
        svc = self.svc(broker, clock, tmp_path, ceiling=100.0)
        out = svc.place(self.put())
        assert out["refused"]["bound"] == "ceiling"
        assert "$55.00" in out["refused"]["reason"] and "$40.00" in out["refused"]["reason"]
        assert "$60.00 at risk on what is held" in out["refused"]["reason"]
        assert len(svc.status()["positions"]) == 1

    def test_a_second_entry_that_fits_beside_the_first_opens(self, broker, clock, tmp_path):
        svc = self.svc(broker, clock, tmp_path, ceiling=120.0)
        assert svc.place(self.put())["refused"] is None
        assert len(svc.status()["positions"]) == 2

    def test_widening_one_stop_counts_the_other_position(self, broker, clock, tmp_path):
        svc = self.svc(broker, clock, tmp_path, ceiling=200.0)
        assert svc.place(self.put())["refused"] is None       # $60 + $55 held
        out = svc.adjust(CALL, stop_price=0.10)               # $200 on the call alone
        assert out["refused"]["bound"] == "ceiling"
        assert "$55.00 at risk on the other positions held" in out["refused"]["reason"]
        assert "$145.00" in out["refused"]["reason"]
        assert svc.adjust(CALL, stop_price=1.00)["refused"] is None   # $110 ≤ $145

    def test_a_held_position_with_no_stop_shuts_the_entry_door(self, broker, clock, tmp_path):
        svc = self.svc(broker, clock, tmp_path, ceiling=500.0)
        svc._open[CALL].stop_price = None          # a stop that would not rest, or adopted
        out = svc.place(self.put())
        assert out["refused"]["bound"] == "ceiling"
        assert "held with no stop" in out["refused"]["reason"] and "unbounded" in out["refused"]["reason"]
