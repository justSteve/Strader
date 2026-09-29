"""TOS beside the form (st-5n3s).

Steve, 2026-09-29: "I'm going to be using TOS native alongside the form …
You'll need to take steps to ensure the form is synched in as close to
real-time as possible." Schwab's listing tells a leg he *moved* in TOS
(REPLACED, a new order in its place) from one he *cancelled* (CANCELED) —
the transport folds both to CANCELED, so the raw word is carried on the
result and these tests set it the way the Schwab transport does.

Before this, both read as "cancelled by hand" and the leg was re-rested at
its old price: a moved stop came back beside his new one (two sells for one
contract), and a cancelled one came straight back.
"""
from __future__ import annotations

from dataclasses import replace

from execd.broker import MockBroker, OrderStatus, Side
from execd.service import ExecService, ServiceConfig

from .conftest import CALL, SPX_NOW, entry, exit_intent


def pos(svc):
    return svc.status()["positions"][0]


def tos_cancel(broker: MockBroker, order_id: str) -> None:
    o = broker._orders[order_id]
    broker._orders[order_id] = replace(o, status=OrderStatus.CANCELED, raw_status="CANCELED",
                                       closed_at=broker.clock())


def tos_move(broker: MockBroker, order_id: str, new_id: str, price: float) -> None:
    """What Schwab lists after a leg is modified in TOS: the old order
    REPLACED, a new one working at the new price, entered as the old closed."""
    now = broker.clock()
    o = broker._orders[order_id]
    broker._orders[order_id] = replace(o, status=OrderStatus.CANCELED, raw_status="REPLACED",
                                       closed_at=now)
    broker._orders[new_id] = replace(o, order_id=new_id, status=OrderStatus.WORKING,
                                     raw_status="WORKING", price=price, submitted_at=now,
                                     closed_at=None)


def working_sells(broker: MockBroker) -> list:
    return [o for o in broker.orders() if o.is_working and o.side is Side.SELL_TO_CLOSE]


class TestALegMovedInTOS:
    def test_the_form_follows_the_new_stop_and_rests_nothing_beside_it(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        p = pos(armed)
        before = len(broker.calls_to("place")) + len(broker.calls_to("place_oco"))
        new_px = round(p["stop_price"] - 0.30, 2)
        tos_move(broker, p["stop_order_id"], "tos-1", new_px)
        out = armed.reconcile()
        assert out["legs"][0]["outcome"] == "replaced"
        p2 = pos(armed)
        assert p2["stop_order_id"] == "tos-1" and p2["stop_price"] == new_px
        assert p2["stop_state"] == "resting"
        # nothing re-rested: his order is the only stop
        assert len(broker.calls_to("place")) + len(broker.calls_to("place_oco")) == before
        assert not armed.journal.events("leg_lost")
        line = armed.journal.events("leg_replaced")[0]
        assert line["old_order_id"] == p["stop_order_id"] and line["order_id"] == "tos-1"
        # the SPX level the loop watches moved with the price (lower stop, lower level)
        assert p2["stop_spx"] < p["stop_spx"]

    def test_a_moved_target_is_followed_as_a_premium_limit(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        tos_move(broker, pos(armed)["target_order_id"], "tos-t", 3.40)
        armed.reconcile()
        p = pos(armed)
        assert p["target_order_id"] == "tos-t" and p["target_price"] == 3.40
        assert p["target_spx"] is None

    def test_a_replacement_not_yet_listed_is_waited_for_not_re_rested(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        sid = pos(armed)["stop_order_id"]
        o = broker._orders[sid]
        broker._orders[sid] = replace(o, status=OrderStatus.CANCELED, raw_status="REPLACED",
                                      closed_at=broker.clock())
        armed.reconcile()
        assert pos(armed)["stop_order_id"] == sid
        assert not armed.journal.events("leg_lost")
        assert not armed.journal.events("leg_cancelled_outside")

    def test_the_move_survives_a_restart(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="tos-mv", stop_spx=SPX_NOW - 2.0, delta=0.30))
        tos_move(broker, pos(first)["stop_order_id"], "tos-2", 1.60)
        first.reconcile()
        second = ExecService(broker, config, clock=clock)
        second.unlock({"token": "x"})
        p = pos(second)
        assert p["stop_order_id"] == "tos-2" and p["stop_price"] == 1.60


class TestALegCancelledInTOS:
    def test_it_stays_off_and_the_card_says_so(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        sid = pos(armed)["stop_order_id"]
        tos_cancel(broker, sid)
        out = armed.reconcile()
        assert out["legs"][0]["outcome"] == "cancelled_outside"
        p = pos(armed)
        assert p["stop_order_id"] is None and p["stop_state"] is None
        assert p["stop_off_by_hand"] and p["stop_spx"] is None
        assert not armed.journal.events("leg_lost")
        assert armed.journal.events("leg_cancelled_outside")[0]["order_id"] == sid
        # a second pass does not put it back either
        armed.reconcile()
        assert pos(armed)["stop_order_id"] is None

    def test_the_spx_loop_does_not_close_on_a_stop_he_cancelled(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        tos_cancel(broker, pos(armed)["stop_order_id"])
        armed.reconcile()
        out = armed.observe(SPX_NOW - 5.0)
        assert not out["fired"]

    def test_setting_it_on_the_form_puts_it_back(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        tos_cancel(broker, pos(armed)["stop_order_id"])
        armed.reconcile()
        armed.adjust(CALL, stop_price=1.70)
        p = pos(armed)
        assert p["stop_order_id"] and p["stop_state"] == "resting"
        assert p["stop_price"] == 1.70 and not p["stop_off_by_hand"]

    def test_a_close_in_tos_after_cancelling_both_legs_is_booked_as_his(self, armed, broker):
        armed.place(entry(stop_spx=SPX_NOW - 2.0, delta=0.30))
        p = pos(armed)
        tos_cancel(broker, p["stop_order_id"])
        tos_cancel(broker, p["target_order_id"])
        armed.reconcile()
        broker.place(exit_intent(intent_id="tos-sell"))
        armed.reconcile()
        closed = armed.journal.events("closed")[-1]
        assert closed["kind"] == "external"
        assert not armed.status()["positions"]

    def test_the_cancelled_state_survives_a_restart(self, broker, clock, tmp_path):
        config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha")
        first = ExecService(broker, config, clock=clock)
        first.unlock({"token": "x"})
        first.place(entry(intent_id="tos-cx", stop_spx=SPX_NOW - 2.0, delta=0.30))
        tos_cancel(broker, pos(first)["stop_order_id"])
        first.reconcile()
        second = ExecService(broker, config, clock=clock)
        second.unlock({"token": "x"})
        p = pos(second)
        assert p["stop_order_id"] is None and p["stop_off_by_hand"]
        assert not second.journal.events("leg_lost")


class TestAWorkingEntryRepricedInTOS:
    def test_the_form_follows_the_new_entry(self, armed, broker):
        broker.rest_limits = True
        out = armed.place(entry())
        wid = out["order"]["order_id"]
        tos_move(broker, wid, "tos-e", 2.05)
        armed.reconcile()
        work = armed.status()["working"]
        assert [x["order_id"] for x in work] == ["tos-e"] and work[0]["limit"] == 2.05
        assert armed.journal.events("entry_resolved")[-1]["outcome"] == "replaced"
