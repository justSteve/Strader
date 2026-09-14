"""PaperBroker — everything live except the order. [st-k6gl]

The mock stands in for Schwab underneath the paper broker: what reaches it
is what would reach Schwab. The load-bearing assertions are the absences —
no ``place`` and no ``cancel`` ever arrive at the live transport — and the
presences: every quote, every preview, does.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from execd.api import create_app
from execd.broker import BrokerError, MockBroker, OrderStatus
from execd.paper import PaperBroker, read_mode
from execd.service import ExecService, ServiceConfig
from execd.watch import Watcher

from .conftest import CALL, PUT, SPX_NOW, Clock, entry, exit_intent


@pytest.fixture
def live(clock: Clock) -> MockBroker:
    b = MockBroker(clock=clock)
    b.set_quote(CALL, bid=2.00, ask=2.10)
    b.set_quote(PUT, bid=1.80, ask=1.90)
    b.set_quote("$SPX", bid=SPX_NOW - 0.25, ask=SPX_NOW + 0.25, last=SPX_NOW)
    return b


@pytest.fixture
def paper(live: MockBroker, clock: Clock, tmp_path) -> PaperBroker:
    return PaperBroker(live, book_path=tmp_path / "paper-book.json", clock=clock)


def live_calls(live: MockBroker, *names: str) -> list[str]:
    return [c[0] for c in live.calls if c[0] in names]


# ── reads and the preview go through; orders never do ────────────────────

class TestPassThrough:
    def test_quote_chain_market_read_and_preview_reach_the_live_transport(self, paper, live):
        assert paper.quote(CALL).ask == 2.10
        live.set_chain("SPXW", {"root": "SPXW", "calls": {}, "puts": {}})
        assert paper.chain("SPXW")["root"] == "SPXW"
        assert "$SPX" in paper.market_read("quotes", {"symbols": "$SPX"})
        p = paper.preview(entry("p-1"))
        assert p.total_usd == 210.65
        assert live_calls(live, "quote", "chain", "market_read", "preview") == [
            "quote", "chain", "market_read", "preview"]

    def test_everything_else_the_transport_offers_is_reachable(self, paper, live):
        paper.set_quote(PUT, bid=1.00, ask=1.10)                    # __getattr__ pass-through
        assert live.quote(PUT).ask == 1.10

    def test_place_and_cancel_never_reach_the_live_transport(self, paper, live):
        o = paper.place(entry("p-2"))
        paper.cancel(o.order_id)
        assert live_calls(live, "place", "cancel") == []


# ── the book ─────────────────────────────────────────────────────────────

class TestTheBook:
    def test_a_marketable_limit_fills_at_the_offer_never_above_the_limit(self, paper):
        o = paper.place(entry("p-3", limit=2.15))
        assert o.status is OrderStatus.FILLED and o.fill_price == 2.10 and o.price == 2.15
        assert paper.positions()[0].qty == 1 and paper.positions()[0].avg_price == 2.10
        assert o.order_id == "paper-0001"

    def test_a_limit_under_the_offer_rests_then_fills_when_the_offer_comes_down(self, paper, live):
        o = paper.place(entry("p-4", limit=2.05))
        assert o.status is OrderStatus.WORKING and paper.positions() == []
        live.set_quote(CALL, bid=1.95, ask=2.05)
        assert paper.orders()[0].status is OrderStatus.FILLED
        assert paper.orders()[0].fill_price == 2.05
        assert paper.positions()[0].qty == 1

    def test_a_market_sell_fills_at_the_bid(self, paper):
        paper.place(entry("p-5"))
        o = paper.place(exit_intent("p-5-x"))
        assert o.status is OrderStatus.FILLED and o.fill_price == 2.00
        assert paper.positions() == []

    def test_a_stop_rests_and_fills_at_the_bid_when_the_bid_reaches_it(self, paper, live, clock):
        paper.place(entry("p-6"))
        from execd.intent import OrderIntent, OrderType, Side
        stop = paper.place(OrderIntent("p-6-s", CALL, Side.SELL_TO_CLOSE, 1,
                                       order_type=OrderType.STOP, stop_price=1.60))
        assert stop.status is OrderStatus.WORKING
        since = clock()
        clock.advance(seconds=5)
        assert paper.fills_since(since) == []
        live.set_quote(CALL, bid=1.55, ask=1.65)
        fills = paper.fills_since(since)
        assert len(fills) == 1 and fills[0].order_id == stop.order_id and fills[0].price == 1.55
        assert paper.positions() == []

    def test_cancel_a_resting_order_and_a_filled_one(self, paper, live):
        rest = paper.place(entry("p-7", limit=2.05))
        assert paper.cancel(rest.order_id).status is OrderStatus.CANCELED
        filled = paper.place(entry("p-8"))
        assert paper.cancel(filled.order_id).status is OrderStatus.FILLED   # the race, reported
        with pytest.raises(BrokerError, match="no such order"):
            paper.cancel("paper-9999")

    def test_no_live_quote_means_nothing_is_simulated(self, paper):
        with pytest.raises(BrokerError, match="no live quote"):
            paper.place(entry("p-9", symbol="SPXW  260826C09999000"))

    def test_the_book_survives_a_restart(self, paper, live, clock, tmp_path):
        paper.place(entry("p-10"))
        again = PaperBroker(live, book_path=tmp_path / "paper-book.json", clock=clock)
        assert [p.qty for p in again.positions()] == [1]
        assert again.orders()[0].order_id == "paper-0001"
        assert again.place(entry("p-11")).order_id == "paper-0002"

    def test_a_corrupt_book_is_an_error_not_a_fresh_start(self, live, tmp_path):
        (tmp_path / "paper-book.json").write_text("{not json")
        with pytest.raises(BrokerError, match="cannot be read"):
            PaperBroker(live, book_path=tmp_path / "paper-book.json")


# ── through the service ──────────────────────────────────────────────────

@pytest.fixture
def paper_service(paper: PaperBroker, clock: Clock, tmp_path) -> ExecService:
    config = ServiceConfig(state_dir=tmp_path / "execd", sha="testsha", mode="paper")
    svc = ExecService(paper, config, clock=clock)
    svc.unlock({"token": "not-a-real-credential"})
    return svc


class TestThroughTheService:
    def test_mode_is_on_the_status_the_journal_and_every_answer(self, paper_service):
        assert paper_service.status()["mode"] == "paper"
        prev = paper_service.preview(entry("s-1"))
        assert prev["mode"] == "paper"
        placed = paper_service.place(entry("s-1"))
        assert placed["mode"] == "paper" and placed["order"]["status"] == "FILLED"
        paper_service.stop()
        refused = paper_service.preview(entry("s-2"))
        assert refused["mode"] == "paper" and refused["refused"]
        assert {e["mode"] for e in paper_service.journal.read()} == {"paper"}

    def test_the_life_cycle_in_paper_entry_stop_watch_exit(self, paper_service, paper, live):
        out = paper_service.place(entry("s-3"))
        assert out["order"]["order_id"] == "paper-0001"
        assert out["stop_order"]["order_id"] == "paper-0002"          # the stop rests in the book
        assert live_calls(live, "place", "cancel") == []
        stop_spx = paper_service.status()["positions"][0]["stop_spx"]

        w = Watcher(paper_service)
        assert w.once()["observe"]["fired"] == []
        live.set_quote("$SPX", bid=stop_spx - 1.0, ask=stop_spx - 0.5, last=stop_spx - 0.75)
        r = w.once()
        assert r["observe"]["fired"][0]["symbol"] == CALL
        st = paper_service.status()
        assert st["positions"] == [] and st["day"]["attempts_used"] == 1
        events = [e["event"] for e in paper_service.journal.find("s-3")]
        assert "filled" in events and "exit_triggered" in events
        assert live_calls(live, "place", "cancel") == []             # still nothing live

    def test_the_resting_stop_fills_in_the_book_and_the_sweep_books_it(self, paper_service, paper, live, clock):
        # a three-point SPX stop at 0.30 delta rests the option stop at 1.20;
        # the conftest's twelve-point stop would clamp it to the one-tick floor
        paper_service.place(entry("s-4", stop_spx=SPX_NOW - 3.0))
        stop_price = paper_service.status()["positions"][0]["stop_price"]
        assert stop_price == 1.20
        clock.advance(seconds=5)
        live.set_quote(CALL, bid=stop_price - 0.05, ask=stop_price + 0.05)
        r = paper_service.poll_fills()
        assert len(r["picked_up"]) == 1 and r["picked_up"][0]["remaining_qty"] == 0
        assert paper_service.status()["positions"] == []

    def test_flatten_closes_the_paper_position_at_the_bid(self, paper_service, paper, live):
        paper_service.place(entry("s-5"))
        out = paper_service.flatten(reason="page")
        assert out["closed"][0]["exit_price"] == 2.00 and out["closed"][0]["closed"]
        assert paper_service.status()["positions"] == []
        assert live_calls(live, "place", "cancel") == []

    def test_the_api_carries_the_mode(self, paper_service):
        client = create_app(paper_service).test_client()
        assert client.get("/status").json["mode"] == "paper"
        r = client.post("/preview", data=json.dumps(entry("s-6").to_dict()),
                        content_type="application/json")
        assert r.status_code == 200 and r.json["mode"] == "paper"


# ── the mode file ────────────────────────────────────────────────────────

def test_read_mode(tmp_path):
    assert read_mode(tmp_path / "absent") == "paper"
    (tmp_path / "m").write_text(" LIVE \n")
    assert read_mode(tmp_path / "m") == "live"
    (tmp_path / "m").write_text("paper")
    assert read_mode(tmp_path / "m") == "paper"
    (tmp_path / "m").write_text("yes")
    with pytest.raises(ValueError, match="expected 'paper' or 'live'"):
        read_mode(tmp_path / "m")
