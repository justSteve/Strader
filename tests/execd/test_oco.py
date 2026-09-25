"""The stop and the target as ONE one-cancels-other order, and the broker's
raw order body as evidence. [co-8mb1z]

2026-09-25 12:15 CT, live on Schwab: the stop rested at 7.10 as its own
order and the 10x take-profit, sent as a second SELL_TO_CLOSE for the same
one contract, was rejected — "not enough available cash/buying power … may
result in an oversold/overbought position". The stop then filled at 7.30,
the entry price, and the normalised order said nothing of why.

What is asserted:
- the OCO body is the shape schwab-py documents (spec-derived, NOT yet
  live-verified — the first live bracket after the install is the first
  recording), with the stop's trigger basis still MARK;
- the transport reads the children back and tracks each leg by its own id,
  and lists an OCO's children as orders;
- the raw read scrubs account numbers and is on the loopback API;
- the service rests the pair as one order at the fill, on an add, after a
  partial exit and on an adjust, never as two; FLATTEN takes it off;
- a leg that fills cancels the other at the broker and in the paper book,
  and the close is booked once;
- every leg placed and every fill booked carries the broker's raw body.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import pytest

from execd import schwab as S
from execd.api import create_app
from execd.broker import MockBroker, OrderStatus
from execd.intent import OrderIntent, OrderType, Side
from execd.paper import PaperBroker
from execd.schwab import SchwabBroker, build_oco
from execd.service import ExecService, ServiceConfig

from .conftest import CALL, SPX_NOW, Clock, entry
from .test_schwab import (ACCT_HASH, ACCT_NUMBER, NOW, FakeSchwab, assert_no_secret, payload,
                          spec_order)

STOP = OrderIntent(intent_id="t:stop:1", symbol=CALL, side=Side.SELL_TO_CLOSE, qty=1,
                   order_type=OrderType.STOP, stop_price=1.90)
TARGET = OrderIntent(intent_id="t:target:1", symbol=CALL, side=Side.SELL_TO_CLOSE, qty=1,
                     order_type=OrderType.LIMIT, limit=21.00)


# ── the wire shape ───────────────────────────────────────────────────────

class TestTheShape:
    def test_the_oco_is_the_documented_shape(self):
        """lib/schwab-py/docs/order-builder.rst 99-114 and
        schwab.orders.common.one_cancels_other: a parent carrying only
        orderStrategyType OCO, the legs as complete SINGLE children."""
        body = build_oco(STOP, TARGET)
        assert set(body) == {"orderStrategyType", "childOrderStrategies"}
        assert body["orderStrategyType"] == "OCO"
        target, stop = body["childOrderStrategies"]
        for child in (target, stop):
            assert child["orderStrategyType"] == "SINGLE"
            assert child["session"] == "NORMAL" and child["duration"] == "DAY"
            leg, = child["orderLegCollection"]
            assert leg["instruction"] == "SELL_TO_CLOSE" and leg["quantity"] == 1
            assert leg["instrument"] == {"symbol": CALL, "assetType": "OPTION"}
        assert target["orderType"] == "LIMIT" and target["price"] == "21.00"
        assert stop["orderType"] == "STOP" and stop["stopPrice"] == "1.90"

    def test_the_trigger_basis_is_still_his_mark(self):
        """Steve's 2026-09-19 ruling; not this change's to touch."""
        assert S.STOP_TRIGGER == "MARK"
        assert build_oco(STOP, TARGET)["childOrderStrategies"][1]["stopType"] == "MARK"

    def test_the_20_dollar_default_is_untouched(self):
        from execd.orderform import DEFAULT_STOP_LOSS_USD
        assert DEFAULT_STOP_LOSS_USD == 20.0


# ── the transport ────────────────────────────────────────────────────────

class OcoSchwab(FakeSchwab):
    """FakeSchwab that answers an OCO the way the spec describes: a parent
    with its own id, the children inside it with theirs."""

    def _placed(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("orderStrategyType") != "OCO":
            return super()._placed(body)
        children = [super(OcoSchwab, self)._placed(c) for c in body["childOrderStrategies"]]
        pid = self.next_order_id
        self.next_order_id += 1
        parent = {"orderStrategyType": "OCO", "orderId": pid, "status": "WORKING",
                  "accountNumber": int(ACCT_NUMBER), "childOrderStrategies": children}
        self.orders[pid] = parent
        return parent


@pytest.fixture
def ocofake() -> OcoSchwab:
    return OcoSchwab()


@pytest.fixture
def sb(ocofake) -> SchwabBroker:
    cred = payload()
    return SchwabBroker(lambda: cred, clock=lambda: NOW,
                        transport=httpx.MockTransport(ocofake.handler))


class TestTheTransport:
    def test_one_post_two_legs_each_under_its_own_id(self, sb, ocofake):
        stop, target = sb.place_oco(STOP, TARGET)
        posts = [c for c in ocofake.calls if c[0] == "POST" and c[1].endswith("/orders")]
        assert len(posts) == 1 and posts[0][3]["orderStrategyType"] == "OCO"
        assert stop.order_type is OrderType.STOP and stop.price == 1.90 and stop.is_working
        assert target.order_type is OrderType.LIMIT and target.price == 21.00
        assert stop.order_id != target.order_id

    def test_a_400_is_both_legs_rejected_in_schwabs_words(self, sb, ocofake):
        ocofake.place_status = 400
        ocofake.place_detail = "may result in an oversold/overbought position"
        stop, target = sb.place_oco(STOP, TARGET)
        assert stop.status is target.status is OrderStatus.REJECTED
        assert "oversold" in stop.message

    def test_a_parent_that_cannot_be_read_back_is_loud(self, sb, ocofake):
        ocofake.fail_get_order_once = True
        stop, target = sb.place_oco(STOP, TARGET)
        assert stop.is_working and stop.order_id.startswith("oco:")
        assert "could not be read back" in stop.message

    def test_the_listing_carries_the_children_as_orders(self, sb, ocofake):
        ocofake.orders = {
            1: {"orderStrategyType": "OCO", "orderId": 1, "status": "WORKING",
                "childOrderStrategies": [
                    spec_order(2, status="WORKING", instruction="SELL_TO_CLOSE",
                               order_type="LIMIT", price=21.0),
                    spec_order(3, status="FILLED", instruction="SELL_TO_CLOSE",
                               order_type="STOP", price=None, stop_price=1.9,
                               fills=[(1.0, 1.85, "2026-09-04T14:40:00+0000")])]}}
        ids = sorted(o.order_id for o in sb.orders())
        assert ids == ["2", "3"]
        fills = sb.fills_since(NOW.replace(hour=0))
        assert [(f.order_id, f.price) for f in fills] == [("3", 1.85)]

    def test_the_raw_read_scrubs_the_account(self, sb, ocofake):
        stop, _target = sb.place_oco(STOP, TARGET)
        parent_id = max(ocofake.orders)
        raw = sb.raw_order(str(parent_id))
        assert raw["orderStrategyType"] == "OCO"
        assert raw["accountNumber"] == "<account>"
        assert all(c["accountNumber"] == "<account>" for c in raw["childOrderStrategies"])
        assert_no_secret(json.dumps(raw))


# ── the service ──────────────────────────────────────────────────────────

@pytest.fixture
def oco_broker(broker: MockBroker) -> MockBroker:
    broker.oco_enabled = True
    return broker


@pytest.fixture
def svc(oco_broker, clock, tmp_path) -> ExecService:
    s = ExecService(oco_broker, ServiceConfig(state_dir=tmp_path / "execd", sha="t"), clock=clock)
    s.unlock({"token": "x"})
    return s


def legs(broker, symbol=CALL):
    return sorted((o.order_type.value, o.qty) for o in broker.working_orders(symbol)
                  if o.side is Side.SELL_TO_CLOSE)


class TestTheService:
    def test_the_fill_rests_one_oco_never_two_orders(self, svc, oco_broker):
        out = svc.place(entry(intent_id="o-1"))
        assert len(oco_broker.calls_to("place_oco")) == 1
        assert [c["order_type"] for c in oco_broker.calls_to("place")] == ["LIMIT"]  # the entry only
        assert out["stop_order"]["order_type"] == "STOP"
        assert out["target_order"]["order_type"] == "LIMIT"
        assert legs(oco_broker) == [("LIMIT", 1), ("STOP", 1)]
        placed = svc.journal.events("stop_placed", "target_placed")
        assert all(e["oco"] for e in placed)

    def test_the_stop_filling_takes_the_target_off_and_books_once(self, svc, oco_broker):
        svc.place(entry(intent_id="o-2"))
        pos = svc.status()["positions"][0]
        oco_broker.fill_resting(pos["stop_order_id"])
        assert oco_broker._orders[pos["target_order_id"]].status is OrderStatus.CANCELED
        svc.reconcile()
        svc.poll_fills()
        assert svc.status()["positions"] == []
        assert len(svc.journal.events("closed")) == 1
        assert svc.journal.events("oversold") == []

    def test_an_add_replaces_the_pair_at_the_combined_size(self, svc, oco_broker):
        svc.place(entry(intent_id="o-3"))
        before = svc.status()["positions"][0]
        svc.place(entry(intent_id="o-4"))
        after = svc.status()["positions"][0]
        assert after["qty"] == 2
        assert oco_broker._orders[before["stop_order_id"]].status is OrderStatus.CANCELED
        assert oco_broker._orders[before["target_order_id"]].status is OrderStatus.CANCELED
        assert legs(oco_broker) == [("LIMIT", 2), ("STOP", 2)]
        assert len(oco_broker.calls_to("place_oco")) == 2

    def test_moving_the_stop_replaces_the_pair_and_keeps_the_target(self, svc, oco_broker):
        svc.place(entry(intent_id="o-5"))
        target_price = svc.status()["positions"][0]["target_price"]
        assert svc.adjust(CALL, stop_price=1.20)["refused"] is None
        pos = svc.status()["positions"][0]
        assert (pos["stop_price"], pos["target_price"]) == (1.20, target_price)
        assert legs(oco_broker) == [("LIMIT", 1), ("STOP", 1)]
        partners = oco_broker._oco
        assert partners.get(pos["stop_order_id"]) == pos["target_order_id"]

    def test_flatten_takes_the_pair_off_and_leaves_nothing(self, svc, oco_broker):
        svc.place(entry(intent_id="o-6"))
        svc.flatten()
        assert svc.status()["positions"] == [] and oco_broker.working_orders(CALL) == []

    def test_every_leg_and_every_fill_carries_the_raw_body(self, svc, oco_broker):
        svc.place(entry(intent_id="o-7"))
        svc.flatten()
        why = [e["why"] for e in svc.journal.events("order_raw")]
        assert "stop_placed" in why and "target_placed" in why
        assert any(w.startswith("fill:") for w in why)
        assert all("body" in e for e in svc.journal.events("order_raw"))

    def test_the_raw_read_is_on_the_loopback_api(self, svc, oco_broker):
        svc.place(entry(intent_id="o-8"))
        oid = svc.status()["positions"][0]["stop_order_id"]
        r = create_app(svc).test_client().get(f"/orders/{oid}/raw")
        assert r.status_code == 200 and r.json["raw"]["order_type"] == "STOP"
        bad = create_app(svc).test_client().get("/orders/a%20b/raw")
        assert bad.status_code == 400

    def test_a_broker_without_oco_still_rests_two_legs(self, broker, clock, tmp_path):
        s = ExecService(broker, ServiceConfig(state_dir=tmp_path / "x", sha="t"), clock=clock)
        s.unlock({"token": "x"})
        s.place(entry(intent_id="n-1"))
        assert broker.calls_to("place_oco") == []
        assert legs(broker) == [("LIMIT", 1), ("STOP", 1)]


class TestPaperIsTheSame:
    def svc(self, broker, clock, tmp_path):
        paper = PaperBroker(broker, book_path=tmp_path / "book.json", clock=clock)
        s = ExecService(paper, ServiceConfig(state_dir=tmp_path / "p", sha="t", mode="paper"),
                        clock=clock)
        s.unlock({"token": "x"})
        return s, paper

    def test_the_paper_book_holds_the_pair_as_oco(self, broker, clock, tmp_path):
        s, paper = self.svc(broker, clock, tmp_path)
        s.place(entry(intent_id="p-1", stop_spx=SPX_NOW - 2.0))
        pos = s.status()["positions"][0]
        assert paper._oco[pos["stop_order_id"]] == pos["target_order_id"]
        assert broker.calls_to("place") == [] and broker.calls_to("place_oco") == []

    def test_a_paper_stop_that_triggers_cancels_the_target(self, broker, clock, tmp_path):
        s, paper = self.svc(broker, clock, tmp_path)
        s.place(entry(intent_id="p-2", stop_spx=SPX_NOW - 2.0))
        pos = s.status()["positions"][0]
        clock.advance(seconds=5)
        broker.set_quote(CALL, bid=1.40, ask=1.50)       # mid 1.45, under the stop
        s.poll_fills()
        book = {o.order_id: o.status for o in paper.orders()}
        assert book[pos["stop_order_id"]] is OrderStatus.FILLED
        assert book[pos["target_order_id"]] is OrderStatus.CANCELED
        assert s.status()["positions"] == []

    def test_the_links_survive_a_restart(self, broker, clock, tmp_path):
        s, paper = self.svc(broker, clock, tmp_path)
        s.place(entry(intent_id="p-3", stop_spx=SPX_NOW - 2.0))
        again = PaperBroker(broker, book_path=tmp_path / "book.json", clock=clock)
        assert again._oco == paper._oco and again._oco
