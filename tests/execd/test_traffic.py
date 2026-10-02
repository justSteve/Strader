"""The SEND traffic pane: one plain line a hop, a block per SEND. [st-qnbg]

Steve, 2026-10-01: "I don't want raw json - i want that payload (in both
directions) reduced to just the essential info of the result - something was
sent - something was returned that validated or errored."
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone

import pytest

from execd.orderpage import PANE_LOGIC
from execd.traffic import (TRAFFIC_CAP, Line, TrafficBuffer, contract_words, lines_for_send,
                           newest_first, render_html, ticket_words)

from .conftest import CALL, page_send
from .test_orderform import chain, mono, order_page, text  # noqa: F401 — fixtures

AT = datetime(2026, 10, 1, 17, 4, 31, tzinfo=timezone.utc)          # 12:04:31 CT
SYM = "SPXW  261001C07720000"
INTENT = {"intent_id": "page-1", "symbol": SYM, "side": "BUY_TO_OPEN", "qty": 2,
          "limit": 10.40, "stop_price": 10.30, "stop_spx": 7700.0}


def j(event, sec, **kw):
    return {"ts": AT.replace(second=sec).isoformat(), "event": event, "intent_id": "page-1",
            "mode": "live", "broker": "schwab", **kw}


class TestTheWords:
    def test_contract_and_ticket(self):
        assert contract_words(SYM) == "SPX 7720C"
        assert ticket_words(INTENT) == "BUY 2 SPX 7720C LMT 10.40, stop $20"

    def test_an_accepted_send_that_fills_reads_as_hops(self):
        journal = [
            j("preview", 31, preview={"side": "BUY_TO_OPEN", "qty": 2, "symbol": SYM, "price": 10.40,
                                      "accepted": True, "total_usd": 2081.30, "messages": []}),
            j("sending", 31, kind="entry", symbol=SYM, qty=2, limit=10.40, stop_price=10.30,
              target_price=52.00),
            j("placed", 32, kind="entry", order={"order_id": "1234567", "status": "FILLED",
                                                  "filled_qty": 2, "fill_price": 10.35}),
            j("filled", 33, kind="entry", qty=2, price=10.35),
            {"ts": AT.isoformat(), "event": "placed", "intent_id": "someone-else"},
        ]
        got = [ln.plain() for ln in lines_for_send(at=AT, title="BUY 2 SPX 7720C",
                                                   intent=INTENT, journal=journal)]
        assert got == [
            "── 12:04:31 BUY 2 SPX 7720C ──",
            "12:04:31 → execd: BUY 2 SPX 7720C LMT 10.40, stop $20",
            "12:04:31 → Schwab: preview BUY 2 SPX 7720C LMT 10.40",
            "12:04:31 ← Schwab: preview ok, $2,081.30 with fees",
            "12:04:31 → Schwab: BUY 2 SPX 7720C LMT 10.40 + STOP 10.30 + TARGET 52.00",
            "12:04:32 ← Schwab: accepted, order 1234567",
            "12:04:33 ← FILLED 2 @ 10.35",
        ]

    def test_a_refusal_by_the_service_is_a_failure_line(self):
        journal = [j("refused", 31, kind="place",
                     refused={"bound": "stop_over_bid",
                              "reason": "the stop 10.30 would rest at or above the 10.30 bid "
                                        "and sell on the fill — widen the stop"})]
        lines = lines_for_send(at=AT, title="BUY 2 SPX 7720C", intent=INTENT, journal=journal)
        last = lines[-1]
        assert last.kind == "in" and last.ok is False
        assert last.plain() == ("12:04:31 ← REFUSED by execd (stop_over_bid): the stop 10.30 would "
                                "rest at or above the 10.30 bid and sell on the fill — widen the stop")

    def test_a_ticket_the_page_refused_never_reached_execd(self):
        lines = lines_for_send(at=AT, title="BUY 2 SPX 7720C", intent=None,
                               page_refusal="the entry's stop is dollars only")
        assert [ln.plain() for ln in lines] == [
            "── 12:04:31 BUY 2 SPX 7720C ──",
            "12:04:31 → SEND BUY 2 SPX 7720C",
            "12:04:31 ← REFUSED at the page: the entry's stop is dollars only"]
        assert lines[-1].ok is False

    def test_a_broker_error_and_a_rejection(self):
        err = lines_for_send(at=AT, title="t", intent=INTENT,
                             journal=[j("send_unknown", 31, detail="read timed out")])
        assert err[-1].plain() == "12:04:31 ← Schwab: no answer: read timed out" and not err[-1].ok
        rej = lines_for_send(at=AT, title="t", intent=INTENT, journal=[
            j("placed", 31, order={"order_id": "9", "status": "REJECTED", "message": "no buying power"})])
        assert rej[-1].plain() == "12:04:31 ← Schwab: REJECTED, order 9: no buying power"
        bare = lines_for_send(at=AT, title="t", intent=INTENT, error="HTTP 400: bad symbol")
        assert bare[-1].plain() == "12:04:31 ← error: HTTP 400: bad symbol"

    def test_paper_says_paper(self):
        e = j("sending", 31, symbol=SYM, qty=1, limit=10.40)
        e["mode"] = "paper"
        assert lines_for_send(at=AT, title="t", intent=INTENT, journal=[e])[2].text.startswith("paper: ")


class TestTheBuffer:
    def test_a_later_fill_lands_inside_its_own_block_and_a_part_shows_a_count(self):
        buf = TrafficBuffer()
        buf.add(lines_for_send(at=AT, title="BUY 2 SPX 7720C", intent=INTENT, journal=[
            j("placed", 32, order={"order_id": "1", "status": "WORKING"})]),
            key="page-1", pending_qty=2)
        buf.add([Line("12:05:00", "head", "BUY 1 SPX 7700C")], key="page-2")
        assert buf.pending == {"page-1"}
        assert buf.note_fills([j("filled", 40, kind="entry", qty=1, price=10.35)]) == 1
        assert buf.pending == {"page-1"}
        buf.note_fills([j("filled", 40, kind="entry", qty=1, price=10.35),
                        j("filled", 45, kind="entry", qty=1, price=10.30)])
        plain = [ln.plain() for ln in buf.lines()]
        assert plain[-1] == "── 12:05:00 BUY 1 SPX 7700C ──"         # the later block stays last
        assert plain[-3:-1] == ["12:04:40 ← FILLED 1/2 @ 10.35", "12:04:45 ← FILLED 2 @ 10.30"]
        assert buf.pending == set()

    def test_the_cap_drops_the_oldest_lines_and_is_said(self):
        buf = TrafficBuffer(cap=5)
        for i in range(4):
            buf.add([Line(f"12:00:0{i}", "head", f"t{i}"), Line(f"12:00:0{i}", "out", "x")])
        assert len(buf) == 5 and buf.dropped == 3
        assert buf.lines()[-1].text == "x" and buf.lines()[1].text == "t2"
        assert render_html(buf).startswith("<div class=k id=traffic-cap>5 of the last 5 lines kept")
        assert TRAFFIC_CAP == 200

    def test_the_html_is_words_escaped_and_coloured_by_direction(self):
        buf = TrafficBuffer()
        buf.add([Line("12:00:00", "head", "BUY 1 SPX 7720C"),
                 Line("12:00:00", "out", "execd: <b>x</b>"),
                 Line("12:00:01", "in", "accepted"),
                 Line("12:00:01", "in", "REFUSED: {\"a\": 1}", ok=False)])
        h = render_html(buf)
        assert "&lt;b&gt;" in h and "<b>" not in h
        assert "class='tl tl-head'>── 12:00:00 BUY 1 SPX 7720C ──" in h
        assert "class='tl tl-out'>12:00:00 → execd" in h
        assert "class='tl tl-in'>12:00:01 ← accepted" in h
        assert "class='tl tl-fail'>12:00:01 ← REFUSED" in h


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on this box")
def test_the_pane_rule_under_node():
    """A SEND shows the traffic; it stays through anything but a tap inside
    it or the toggle; the toggle flips either way."""
    cases = [["strikes", "send", "traffic"], ["traffic", "send", "traffic"],
             ["traffic", "poll", "traffic"], ["traffic", "tap-traffic", "strikes"],
             ["traffic", "toggle", "strikes"], ["strikes", "toggle", "traffic"],
             ["strikes", "poll", "strikes"]]
    js = ("var window = {};" + PANE_LOGIC
          + f"var cases = {json.dumps(cases)};"
          + "var bad = cases.filter(function(c){ return window.__paneNext(c[0], c[1]) !== c[2]; });"
          + "console.log(JSON.stringify(bad));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == []


class TestThePage:
    def test_the_pane_holds_the_strikes_the_toggle_and_the_buffer(self, order_page):
        body = text(order_page.get("/exec/order?side=call"))
        pane = body.split("<div class=card id=pane data-view=strikes>")[1]
        assert "id=panetoggle" in pane and "<div id=strikes>" in pane
        assert "<div id=traffic hidden>" in pane and "no SEND yet" in pane
        assert "window.__paneNext" in body and "__paneShow('send')" in body

    def test_a_send_and_a_refused_send_land_in_the_buffer_as_words(self, order_page, armed, chain):
        page_send(order_page, {"side": "call", "strike": "6400"})
        page_send(order_page, {"side": "call", "strike": "6400", "stop": "2.05"})
        h = order_page.get("/exec/order/state?side=call").json["traffic_html"]
        assert "{" not in h and "&quot;" not in h                     # no JSON, anywhere
        assert "→ execd: BUY 1 SPX 6400C LMT 2.10, stop $30" in h
        assert "← FILLED 1 @ 2.10" in h
        assert "← REFUSED at the page: the stop 2.05 would rest at or above the 2.00 bid" in h
        assert h.count("tl-head") == 2
        assert armed.status()["positions"][0]["symbol"] == CALL


def test_the_newest_transaction_renders_at_the_top_with_its_hops_in_order():
    """Steve, 2026-10-02 (st-d7cm): newest at the top — the block, not the
    line: a SEND's hops still read down in the order they happened."""
    buf = TrafficBuffer()
    buf.add([Line("11:00:00", "head", "old"), Line("11:00:00", "out", "o1"),
             Line("11:00:01", "in", "o2")])
    buf.add([Line("11:02:00", "head", "new"), Line("11:02:00", "out", "n1"),
             Line("11:02:01", "in", "n2")])
    h = render_html(buf)
    order = [h.index(w) for w in ("── 11:02:00 new", "n1", "n2", "── 11:00:00 old", "o1", "o2")]
    assert order == sorted(order)
    assert "newest at the top" in h
    # a block the cap cut below its header stays together, oldest last
    assert [ln.text for ln in newest_first([Line("1", "in", "tail"), Line("2", "head", "h"),
                                            Line("2", "out", "x")])] == ["h", "x", "tail"]
