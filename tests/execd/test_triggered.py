"""Entry, stop and target as ONE order; the stop and target moved by replace.
[co-8mb1z]

Steve, 2026-09-25: "My intent is to ensure that Stop Loss is in place as soon
as the order is filled -- confirm yes to create all 3 at once. We can lower
the take profit % to 5X. In practice I'll be sitting on a ready order to
change that according to conditions at the time."

Spec-derived and not yet live-verified: the TRIGGER-with-OCO shape, reading
the children back, and the replace (PUT). What Schwab does to the OCO sibling
of a replaced leg is NOT measured; the service reads it back and journals it.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import pytest

from execd.bounds import Bounds
from execd.broker import MockBroker, OrderStatus
from execd.intent import OrderIntent, OrderType, Side
from execd.paper import PaperBroker
from execd.schwab import SchwabBroker, build_triggered
from execd.service import ExecService, ServiceConfig

from .conftest import CALL, SPX_NOW
from .test_oco import STOP, TARGET, OcoSchwab
from .test_schwab import ACCT_HASH, NOW, payload, schwab_error, spec_order

ENTRY = OrderIntent(intent_id="t", symbol=CALL, side=Side.BUY_TO_OPEN, qty=1,
                    order_type=OrderType.LIMIT, limit=2.10)


def entry(**kw):
    """An entry the way the order form sends it: the SPX level that walks to
    $20 under the 2.10 limit at 0.30 delta (6380 - 0.667, rounded away from
    spot, as ``orderform._level_for`` does)."""
    from .conftest import entry as base
    kw.setdefault("stop_spx", 6379.33)
    return base(**kw)


def make(broker, clock, tmp_path, **cfg):
    s = ExecService(broker, ServiceConfig(state_dir=tmp_path / "execd", sha="t", **cfg),
                    clock=clock)
    s.unlock({"token": "x"})
    return s


@pytest.fixture
def mb(broker: MockBroker) -> MockBroker:
    broker.oco_enabled = True
    return broker


@pytest.fixture
def svc(mb, clock, tmp_path) -> ExecService:
    return make(mb, clock, tmp_path)       # the default bounds: 5x


def legs(broker, symbol=CALL):
    return sorted((o.order_type.value, o.qty, o.price) for o in broker.working_orders(symbol)
                  if o.side is Side.SELL_TO_CLOSE)


class TestTheShape:
    def test_the_entry_carries_the_oco_as_its_trigger_child(self):
        """schwab-py's first-triggers-OCO (docs/order-builder.rst 81-155)."""
        body = build_triggered(ENTRY, STOP, TARGET)
        assert body["orderStrategyType"] == "TRIGGER" and body["orderType"] == "LIMIT"
        assert body["orderLegCollection"][0]["instruction"] == "BUY_TO_OPEN"
        child, = body["childOrderStrategies"]
        assert child["orderStrategyType"] == "OCO"
        types = sorted(c["orderType"] for c in child["childOrderStrategies"])
        assert types == ["LIMIT", "STOP"]
        stop = next(c for c in child["childOrderStrategies"] if c["orderType"] == "STOP")
        assert stop["stopType"] == "MARK"


class TestAllThreeAtOnce:
    def test_the_fill_finds_its_bracket_already_resting(self, svc, mb):
        out = svc.place(entry(intent_id="a-1"))
        assert len(mb.calls_to("place_triggered")) == 1
        assert mb.calls_to("place_oco") == [] or len(mb.calls_to("place_oco")) == 1
        # the service placed nothing of its own after the fill: every OCO
        # came from the broker bringing the triggered child to life
        assert [c["order_type"] for c in mb.calls_to("place")] == ["LIMIT"]
        assert out["stop_order"]["price"] == 1.90          # the 2.10 limit less $20
        assert out["target_order"]["price"] == 10.50       # 5x the 2.10 limit
        assert legs(mb) == [("LIMIT", 1, 10.50), ("STOP", 1, 1.90)]
        kinds = {e["kind"] for e in svc.journal.events("stop_placed", "target_placed")}
        assert kinds == {"triggered"}
        assert svc.journal.events("sending")[-1]["triggered"] is True

    def test_a_resting_entry_brings_its_bracket_when_it_fills(self, svc, mb):
        mb.rest_limits = True
        out = svc.place(entry(intent_id="a-2"))
        assert out["working"]["triggered"] is True and legs(mb) == []
        mb.fill_resting(out["order"]["order_id"])
        svc.reconcile()
        pos = svc.status()["positions"][0]
        assert (pos["stop_price"], pos["target_price"]) == (1.90, 10.50)
        assert legs(mb) == [("LIMIT", 1, 10.50), ("STOP", 1, 1.90)]
        assert svc.journal.events("bracket_fallback") == []

    def test_his_typed_stop_wins(self, svc, mb, armed=None):
        from execd.stops import protective_stop_price
        level = SPX_NOW - 30.0                      # a wider stop of his own
        out = svc.place(entry(intent_id="a-3", stop_spx=level))
        want = protective_stop_price(2.10, 0.30, SPX_NOW, level)
        assert out["stop_order"]["price"] == want and want < 1.90

    def test_a_missing_child_falls_back_and_says_so(self, svc, mb, monkeypatch):
        monkeypatch.setattr(mb, "children_of", lambda oid: (None, None))
        svc.place(entry(intent_id="a-4"))
        assert svc.journal.events("bracket_fallback")
        pos = svc.status()["positions"][0]
        assert pos["stop_order_id"] and pos["target_order_id"]

    def test_a_child_sized_for_more_than_filled_is_replaced(self, svc, mb, clock, tmp_path):
        s = make(mb, clock, tmp_path / "two", bounds=Bounds(qty_cap=2))
        mb.partial_fill_qty = 1
        s.place(entry(intent_id="a-5", qty=2))
        fb = s.journal.events("bracket_fallback")
        assert fb and fb[-1]["qty"] == 1
        assert legs(mb) == [("LIMIT", 1, 10.50), ("STOP", 1, 1.90)]

    def test_an_add_goes_out_alone_and_the_pair_is_resized(self, svc, mb):
        svc.place(entry(intent_id="a-6"))
        svc.place(entry(intent_id="a-7"))
        assert len(mb.calls_to("place_triggered")) == 1   # the add is a plain entry
        assert legs(mb) == [("LIMIT", 2, 10.50), ("STOP", 2, 1.90)]

    def test_re_pricing_a_working_triggered_entry_leaves_one_bracket(self, svc, mb):
        mb.rest_limits = True
        first = svc.place(entry(intent_id="a-8"))
        svc.cancel(first["order"]["order_id"])
        second = svc.place(entry(intent_id="a-9", limit=2.05))
        mb.fill_resting(second["order"]["order_id"])
        svc.reconcile()
        # 5x 2.05 is 10.25, up to the 0.10 grid above $3; $20 under 2.05
        assert legs(mb) == [("LIMIT", 1, 10.30), ("STOP", 1, 1.85)]

    def test_alpaca_style_brokers_send_the_entry_alone(self, broker, clock, tmp_path):
        s = make(broker, clock, tmp_path / "x")            # no OCO, no trigger
        s.place(entry(intent_id="a-10"))
        assert broker.calls_to("place_triggered") == []
        assert len(legs(broker)) == 2


class TestReplace:
    def test_moving_the_stop_is_a_replace_and_the_sibling_is_read_back(self, svc, mb):
        svc.place(entry(intent_id="r-1"))
        target_id = svc.status()["positions"][0]["target_order_id"]
        n_cancel = len(mb.calls_to("cancel"))
        assert svc.adjust(CALL, stop_price=1.50)["refused"] is None
        assert len(mb.calls_to("replace_order")) == 1
        assert len(mb.calls_to("cancel")) == n_cancel      # no cancel-and-new
        pos = svc.status()["positions"][0]
        assert pos["stop_price"] == 1.50 and pos["target_order_id"] == target_id
        moved = svc.journal.events("stop_adjusted")[-1]
        assert moved["replaced"] is True
        why = [e["why"] for e in svc.journal.events("order_raw")]
        assert "replace:stop" in why and "replace:stop:sibling" in why

    def test_a_replace_that_takes_the_sibling_off_puts_the_pair_back(self, svc, mb):
        svc.place(entry(intent_id="r-2"))
        mb.replace_breaks_oco = True
        svc.adjust(CALL, target_price=12.00)
        assert svc.journal.events("replace_broke_oco")
        assert legs(mb) == [("LIMIT", 1, 12.00), ("STOP", 1, 1.90)]
        pos = svc.status()["positions"][0]
        assert mb._oco.get(pos["stop_order_id"]) == pos["target_order_id"]


class TestPaper:
    def test_the_book_brings_the_bracket_when_the_entry_fills_and_keeps_it(self, broker, clock,
                                                                           tmp_path):
        paper = PaperBroker(broker, book_path=tmp_path / "book.json", clock=clock)
        s = make(paper, clock, tmp_path, mode="paper")
        broker.set_quote(CALL, bid=2.20, ask=2.30)         # the 2.10 limit rests
        out = s.place(entry(intent_id="p-1", limit=2.10))
        assert out["working"]["triggered"] is True
        assert PaperBroker(broker, book_path=tmp_path / "book.json", clock=clock
                           )._pending_children                      # survives a restart
        clock.advance(seconds=5)
        broker.set_quote(CALL, bid=2.00, ask=2.10)
        s.reconcile()
        pos = s.status()["positions"][0]
        assert (pos["stop_price"], pos["target_price"]) == (1.90, 10.50)
        assert paper._oco[pos["stop_order_id"]] == pos["target_order_id"]
        assert broker.calls_to("place") == []                        # nothing reached the broker


class TriggerSchwab(OcoSchwab):
    """The fake with a TRIGGER parent holding the OCO, and a PUT replace."""

    def _placed(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("orderStrategyType") != "TRIGGER":
            return super()._placed(body)
        child = body.pop("childOrderStrategies")[0]
        entry_body = {k: v for k, v in body.items() if k != "orderStrategyType"}
        parent = super()._placed(entry_body)
        parent["orderStrategyType"] = "TRIGGER"
        oco = super()._placed(child)
        for c in oco["childOrderStrategies"]:
            c["status"] = "AWAITING_PARENT_ORDER"
        parent["childOrderStrategies"] = [oco]
        return parent

    def handler(self, request: httpx.Request) -> httpx.Response:
        m = re.fullmatch(rf"/trader/v1/accounts/{ACCT_HASH}/orders/(\d+)", request.url.path)
        if request.method == "PUT" and m:
            self.calls.append(("PUT", request.url.path, {}, json.loads(request.content), ""))
            old = self.orders.get(int(m.group(1)))
            if old is None:
                return schwab_error(404, "order not found")
            old["status"] = "REPLACED"
            new = super()._placed(json.loads(request.content))
            return httpx.Response(201, headers={
                "Location": f"https://api.schwabapi.com/trader/v1/accounts/{ACCT_HASH}/orders/{new['orderId']}"})
        return super().handler(request)


@pytest.fixture
def tfake() -> TriggerSchwab:
    return TriggerSchwab()


@pytest.fixture
def tsb(tfake) -> SchwabBroker:
    cred = payload()
    return SchwabBroker(lambda: cred, clock=lambda: NOW,
                        transport=httpx.MockTransport(tfake.handler))


class TestTheSchwabTransport:
    def test_one_post_carries_all_three(self, tsb, tfake):
        order = tsb.place_triggered(ENTRY, STOP, TARGET)
        posts = [c for c in tfake.calls if c[0] == "POST" and c[1].endswith("/orders")]
        assert len(posts) == 1 and posts[0][3]["orderStrategyType"] == "TRIGGER"
        assert order.side is Side.BUY_TO_OPEN and order.is_working
        stop, target = tsb.children_of(order.order_id)
        assert stop.order_type is OrderType.STOP and stop.price == 1.90 and stop.is_working
        assert target.order_type is OrderType.LIMIT and target.price == 21.00

    def test_replace_is_a_put_and_answers_the_new_order(self, tsb, tfake):
        stop, _t = tsb.place_oco(STOP, TARGET)
        moved = OrderIntent(intent_id="t:stop:1b", symbol=CALL, side=Side.SELL_TO_CLOSE, qty=1,
                            order_type=OrderType.STOP, stop_price=1.50)
        new = tsb.replace_order(stop.order_id, moved)
        puts = [c for c in tfake.calls if c[0] == "PUT"]
        assert len(puts) == 1 and puts[0][3]["stopPrice"] == "1.50"
        assert new.order_id != stop.order_id and new.price == 1.50

    def test_a_rejected_replace_is_a_rejection(self, tsb, tfake):
        stop, _t = tsb.place_oco(STOP, TARGET)

        def refuse(request):
            if request.method == "PUT":
                return schwab_error(400, "cannot replace")
            return TriggerSchwab.handler(tfake, request)
        tsb._client._transport = httpx.MockTransport(refuse)
        moved = OrderIntent(intent_id="x", symbol=CALL, side=Side.SELL_TO_CLOSE, qty=1,
                            order_type=OrderType.STOP, stop_price=1.50)
        assert tsb.replace_order(stop.order_id, moved).status is OrderStatus.REJECTED
