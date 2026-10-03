"""The entry carries its stop alone; the target goes on after the fill.
[st-zv1l]

Steve, 2026-10-03: "I'm fine with leaving the take profit clause until after a
fill but i'd prefer having that stop loss on right away." ``Bounds.stop_with_entry``
sends the entry as a TRIGGER whose one child is the SELL STOP — no OCO — and
once the fill is read the stop comes off and goes back on with the target as
one OCO pair (Schwab refuses a target beside a lone stop as an oversell).

Spec-derived: schwab-py's ``first_triggers_second``. Whether Schwab rests this
child or fills it at activation, as it did the OCO bracket's MARK stop at
11:02:21 CT 2026-10-02 (st-jdk7), is measured by the first live 1-lot.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from execd.bounds import Bounds
from execd.broker import MockBroker, OrderStatus
from execd.paper import PaperBroker
from execd.schwab import SchwabBroker, build_triggered
from execd.service import ExecService, ServiceConfig

from .conftest import CALL
from .test_oco import STOP, OcoSchwab
from .test_schwab import NOW, payload
from .test_triggered import ENTRY, entry, legs


def make(broker, clock, tmp_path, *, on: bool = True, **cfg):
    s = ExecService(broker, ServiceConfig(state_dir=tmp_path / "execd", sha="t",
                                          bounds=Bounds(stop_with_entry=on), **cfg),
                    clock=clock)
    s.unlock({"token": "x"})
    return s


@pytest.fixture
def mb(broker: MockBroker) -> MockBroker:
    broker.oco_enabled = True
    return broker


@pytest.fixture
def svc(mb, clock, tmp_path) -> ExecService:
    return make(mb, clock, tmp_path)


class TestTheShape:
    def test_the_entrys_one_child_is_the_stop_itself(self):
        body = build_triggered(ENTRY, STOP, None)
        assert body["orderStrategyType"] == "TRIGGER" and body["orderType"] == "LIMIT"
        child, = body["childOrderStrategies"]
        assert child["orderStrategyType"] == "SINGLE"
        assert child["orderType"] == "STOP" and child["stopType"] == "MARK"
        assert child["orderLegCollection"][0]["instruction"] == "SELL_TO_CLOSE"
        assert "childOrderStrategies" not in child

    def test_off_by_default(self):
        assert Bounds().stop_with_entry is False

    def test_a_non_boolean_switch_is_refused(self):
        with pytest.raises(ValueError, match="stop_with_entry"):
            Bounds.from_dict({"stop_with_entry": "yes please"})


class TestTheStopGoesWithTheEntry:
    def test_off_the_entry_goes_alone(self, mb, clock, tmp_path):
        s = make(mb, clock, tmp_path, on=False)
        s.place(entry(intent_id="o-1"))
        assert mb.calls_to("place_triggered") == []
        assert s.status()["positions"][0]["stop_order_id"]

    def test_the_stop_is_carried_and_the_target_follows_as_a_pair(self, svc, mb):
        out = svc.place(entry(intent_id="s-1"))
        assert len(mb.calls_to("place_triggered")) == 1
        sending = svc.journal.events("sending")[-1]
        assert sending["carried"] == "stop" and sending["target_price"] is None
        assert sending["stop_price"] == 1.90                 # the 2.10 limit less $20
        # the carried stop was booked as the position's, then swapped for the pair
        placed = svc.journal.events("stop_placed")
        assert [(e["kind"], e["oco"]) for e in placed] == [("triggered", False), ("entry", True)]
        cancelled, = [e for e in svc.journal.events("canceled") if e["kind"] == "protective-stop"]
        assert cancelled["order_id"] == placed[0]["order_id"]
        assert len(mb.calls_to("place_oco")) == 1
        pos = svc.status()["positions"][0]
        assert pos["stop_order_id"] and pos["target_order_id"]
        assert legs(mb) == sorted([("STOP", 1, pos["stop_price"]),
                                   ("LIMIT", 1, pos["target_price"])])
        assert out["target_order"] is not None
        assert svc.journal.events("bracket_fallback") == []
        assert svc.journal.events("stop_unprotected") == []

    def test_a_resting_entry_carries_its_stop_when_it_fills(self, svc, mb):
        mb.rest_limits = True
        out = svc.place(entry(intent_id="s-2"))
        assert out["working"]["triggered"] is True and legs(mb) == []
        mb.fill_resting(out["order"]["order_id"])
        assert [o.order_type.value for o in mb.working_orders(CALL)] == ["STOP"]
        svc.reconcile()
        pos = svc.status()["positions"][0]
        assert pos["stop_order_id"] and pos["target_order_id"]
        assert svc.journal.events("bracket_fallback") == []

    def test_a_stop_that_fired_at_activation_is_booked_as_the_stop(self, svc, mb):
        """The st-jdk7 shape, now with the stop alone: filled before the
        service first read it. One close, no second stop, nothing short."""
        orig = mb.place_triggered

        def fire(entry_, stop, target=None):
            order = orig(entry_, stop, target)
            mb.fill_resting(mb._children[order.order_id][0])
            return order
        mb.place_triggered = fire
        svc.place(entry(intent_id="s-3"))
        closed, = svc.journal.events("closed")
        assert (closed["kind"], closed["reason"]) == ("protective-stop", "resting-stop")
        assert svc.journal.events("bracket_fired")[0]["leg"] == "stop"
        assert svc.journal.events("oversold") == []
        assert CALL not in svc._open and legs(mb) == []
        assert mb.calls_to("place_oco") == []

    def test_a_carried_stop_that_will_not_come_off_stays_and_no_target_rests(self, svc, mb):
        mb.cancel_pending = True
        svc.place(entry(intent_id="s-4"))
        pos = svc.status()["positions"][0]
        assert pos["stop_order_id"] and not pos["target_order_id"]
        assert [o.order_type.value for o in mb.working_orders(CALL)] == ["STOP"]
        warn, = svc.journal.events("target_unprotected")
        assert "would not come off" in warn["detail"]
        assert mb.calls_to("place_oco") == []

    def test_a_missing_carried_stop_is_read_again_then_replaced(self, svc, mb, monkeypatch,
                                                                clock):
        from execd.service import LEG_SETTLE_S
        monkeypatch.setattr(mb, "children_of", lambda oid: (None, None))
        out = svc.place(entry(intent_id="s-5"))
        assert out["bracket_unread"] is True
        clock.advance(seconds=LEG_SETTLE_S + 1)
        svc.reconcile()
        assert svc.journal.events("bracket_fallback")
        pos = svc.status()["positions"][0]
        assert pos["stop_order_id"] and pos["target_order_id"]

    def test_an_add_goes_out_alone(self, svc, mb):
        svc.place(entry(intent_id="s-6"))
        svc.place(entry(intent_id="s-7"))
        assert len(mb.calls_to("place_triggered")) == 1


class TestPaper:
    def test_the_book_carries_the_stop_alone_across_a_restart(self, broker, clock, tmp_path):
        paper = PaperBroker(broker, book_path=tmp_path / "book.json", clock=clock)
        s = make(paper, clock, tmp_path, mode="paper")
        broker.set_quote(CALL, bid=2.20, ask=2.30)         # the 2.10 limit rests
        out = s.place(entry(intent_id="p-1", limit=2.10))
        assert out["working"]["triggered"] is True
        again = PaperBroker(broker, book_path=tmp_path / "book.json", clock=clock)
        (stop, target), = again._pending_children.values()
        assert stop["order_type"] == "STOP" and target is None
        clock.advance(seconds=5)
        broker.set_quote(CALL, bid=2.00, ask=2.10)
        s.reconcile()
        pos = s.status()["positions"][0]
        assert paper._oco[pos["stop_order_id"]] == pos["target_order_id"]
        assert broker.calls_to("place") == []
        reread = PaperBroker(broker, book_path=tmp_path / "book.json", clock=clock)
        assert all(v[1] is None for v in reread._children.values())


class StopChildSchwab(OcoSchwab):
    """A TRIGGER parent whose one child is a SINGLE stop."""

    def _placed(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("orderStrategyType") != "TRIGGER":
            return super()._placed(body)
        child = body.pop("childOrderStrategies")[0]
        parent = super()._placed({k: v for k, v in body.items() if k != "orderStrategyType"})
        parent["orderStrategyType"] = "TRIGGER"
        kid = super()._placed(child)
        kid["status"] = "AWAITING_PARENT_ORDER"
        parent["childOrderStrategies"] = [kid]
        return parent


class TestTheSchwabTransport:
    def test_one_post_and_the_child_reads_back_as_the_stop(self):
        fake = StopChildSchwab()
        cred = payload()
        sb = SchwabBroker(lambda: cred, clock=lambda: NOW,
                          transport=httpx.MockTransport(fake.handler))
        order = sb.place_triggered(ENTRY, STOP)
        posts = [c for c in fake.calls if c[0] == "POST" and c[1].endswith("/orders")]
        assert len(posts) == 1
        assert posts[0][3]["orderStrategyType"] == "TRIGGER"
        assert order.is_working
        stop, target = sb.children_of(order.order_id)
        assert stop.price == 1.90 and target is None
        assert stop.status is not OrderStatus.FILLED
