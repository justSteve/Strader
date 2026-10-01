"""The order screen, end to end: pricing → edit → SEND → fills → closes. [st-ug1h]

The screen is driven as the browser drives it (``screen.OrderScreen``): a
side, a strike tapped, the stop steppers or the close-at box, the padlock,
SEND. Then the question Steve asked on 2026-09-30 is asked of every send:
did the service receive what the ticket on the screen showed? And after
the fills and the closes, does what the poll paints — the card, the
caption, the closed cards, the day's total — agree with the service?
"""

from __future__ import annotations

import pytest

from .screen import OrderScreen
from .tape import ramp


def flat(seconds=120.0, spx=6380.0):
    return ramp((0, spx), (seconds, spx))


def received_matches_shown(answer, shown):
    got = answer["_received"]
    assert got is not None, answer
    assert got["symbol"] == shown["contract"]["symbol"]
    assert got["qty"] == shown["lots"]
    assert got["limit"] == shown["limit"]
    if shown["stop_set_by"] == "spx":
        assert got.get("stop_price") is None and got["stop_spx"] == shown["stop_spx"]
    else:
        assert got["stop_price"] == shown["stop_price"]
        assert got["stop_spx"] == shown["stop_spx"]
    return got


class TestTheTicketIsWhatIsSent:
    def test_strike_tapped_stop_stepped_wider_send(self, make):
        scn = make(flat())
        screen = OrderScreen(scn)
        first = screen.pick("call", delta=0.5)
        screen.tap(first["contract"]["strike"] + 5)
        shown = screen.step_stop(+1)                       # 0.20 → 0.30
        assert round(shown["limit"] - shown["stop_price"], 2) == 0.30
        answer = screen.send()
        assert answer["ok"] is True and answer["msg_stage"] == "filled", answer.get("bad")
        received_matches_shown(answer, shown)
        sym = shown["contract"]["symbol"]
        assert scn.resting(sym)["stop"] == [shown["stop_price"]]     # filled at the limit

    def test_steppers_narrow_too(self, make):
        scn = make(flat())
        screen = OrderScreen(scn)
        screen.pick("put", delta=0.5)
        screen.step_stop(+3)
        shown = screen.step_stop(-1)                       # 0.20 → 0.50 → 0.40
        assert round(shown["limit"] - shown["stop_price"], 2) == 0.40
        received_matches_shown(screen.send(), shown)

    def test_a_stale_close_at_box_is_refused_at_send(self, make):
        """The close-at-SPX box is gone from the entry (Steve, 2026-10-01,
        st-a54y: "At entry, only permit a $$ SL"). A page painted before the
        install still has it: what it types is refused in words on the
        ticket, SEND is off, and a SEND that goes anyway reaches no
        service."""
        scn = make(flat())
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        body = screen.client.get("/exec/order?side=call&delta=0.5").get_data(as_text=True)
        assert "id=exitbox" not in body and "close at SPX" not in body
        shown = screen.type_exit(6376)
        assert "dollars only" in shown["error"] and shown["sendable"] is False
        answer = screen.send()
        assert answer["ok"] is False and "dollars only" in answer["bad"]
        assert answer["_received"] is None and scn.events("sending") == []

    def test_the_default_stop_on_two_lots_in_a_dime_market_is_refused_and_widened_goes(self, make):
        """st-yeph, the case that raised it: the flat $20 over two lots is
        0.10 a contract, at the bid of a 0.10-wide market. The screen says
        why and SEND is off; a SEND that goes anyway is refused at the page
        and nothing reaches the service. A stepper tap widens it past the
        spread and the same ticket goes."""
        scn = make(ramp((0, 6380.0), (120, 6380.0), spread=0.10))
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        shown = screen.lots(2)
        assert "would rest at or above" in shown["error"] and shown["sendable"] is False
        answer = screen.send()
        assert answer["ok"] is False and "widen the stop" in answer["bad"]
        assert answer["_received"] is None and scn.events("sending") == []
        shown = screen.step_stop(+1)                       # wider than the dime spread
        assert shown["error"] is None and shown["sendable"] is True
        answer = screen.send()
        assert answer["ok"] is True and answer["msg_stage"] == "filled", answer.get("bad")
        received_matches_shown(answer, shown)

    def test_the_padlock_and_three_lots(self, make):
        scn = make(ramp((0, 6380), (30, 6380), (60, 6379.7), (120, 6379.7)))
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        screen.lots(3)
        screen.type_stop("0.50")
        live = screen.shown["limit"]
        shown = screen.lock(round(live - 0.10, 2))
        answer = screen.send()
        assert answer["msg_stage"] == "working", answer.get("msg")
        got = received_matches_shown(answer, shown)
        assert got["limit"] == round(live - 0.10, 2)
        scn.run(120, until=lambda s: bool(s.held()))
        sym = shown["contract"]["symbol"]
        assert scn.held() == {sym: 3}
        assert [o.qty for o in scn.working(sym)] == [3, 3]

    @pytest.mark.parametrize("locked", [False, True], ids=["unlocked", "locked"])
    def test_the_market_moves_between_the_paint_and_the_tap(self, make, locked):
        """SEND prices again at the send. Unlocked, the limit is the ask at
        that moment — by design (the padlock exists for the other case); the
        strike stays the one on the screen and the stop keeps its distance.
        Locked, the limit is the one shown."""
        scn = make(ramp((0, 6380), (3, 6380), (4, 6381.5), (60, 6381.5)))
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        shown = screen.lock() if locked else screen.shown
        scn.wait_until(5)                                  # the market moved; no repaint
        got = screen.send()["_received"]
        assert got["symbol"] == shown["contract"]["symbol"]
        if locked:
            assert got["limit"] == shown["limit"]
        else:
            assert got["limit"] > shown["limit"]
        assert round(got["limit"] - got["stop_price"], 2) == \
            round(shown["limit"] - shown["stop_price"], 2)


class TestTheScreenAgreesWithTheService:
    def test_the_card_the_caption_the_closed_cards_and_the_day(self, make):
        scn = make(ramp((0, 6380), (15, 6380), (75, 6372), (120, 6372),
                        (150, 6372), (210, 6366), (260, 6366)))
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        answer = screen.send()
        assert answer["msg_stage"] == "filled" and answer["panel_stage"] == "filled"
        state = screen.poll()
        assert state["panel_stage"] == "filled"
        svc_pos = scn.service.status()["positions"][0]
        assert state["positions"][0]["stop_price"] == svc_pos["stop_price"]
        assert state["positions"][0]["target_price"] == svc_pos["target_price"]
        assert screen.closed_cards(state) == []

        scn.run(120, until=lambda s: not s.held())
        state = screen.poll()
        assert state["panel_stage"] == "none"               # the caption goes with the card
        # each card net of both commissions, as the open card's figures are
        assert screen.closed_cards(state) == [c["net_pnl_usd"] for c in scn.closes()]
        assert screen.today(state) == scn.service.status()["pnl"]["day_usd"] == scn.realized()

        # a second trade, closed the same way: two cards, newest on top
        scn.wait_until(150)
        screen.pick("call", delta=0.5)
        screen.send()
        scn.run(110, until=lambda s: not s.held())
        state = screen.poll()
        closes = scn.closes()
        assert len(closes) == 2
        assert screen.closed_cards(state) == [c["net_pnl_usd"] for c in reversed(closes)]
        assert screen.today(state) == scn.realized()

    def test_an_open_position_is_on_the_day_at_its_net(self, make):
        scn = make(flat())
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        screen.send()
        state = screen.poll()
        net = state["positions"][0]["valuation"]["net_if_closed_usd"]
        assert screen.today(state) == state["pnl"]["day_usd"] == net


class TestTheTrafficPane:
    """The SEND traffic buffer (st-qnbg; Steve, 2026-10-01): one line a hop,
    CT-stamped, a block per SEND, no JSON — on the paper book under the
    real service, as the screen drives it."""

    @staticmethod
    def lines(state):
        import html
        import re
        return [html.unescape(t) for t in
                re.findall(r"<div class='tl [a-z-]+'>([^<]*)</div>", state["traffic_html"])]

    def test_an_accepted_send_rests_then_fills_inside_its_block_and_a_refused_send_follows(self, make):
        scn = make(ramp((0, 6380), (30, 6380), (90, 6378), (150, 6378)))
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        live = screen.shown["limit"]
        screen.type_stop("0.50")
        shown = screen.lock(round(live - 0.10, 2))           # rests under the offer
        sym = shown["contract"]["symbol"]
        answer = screen.send()
        assert answer["msg_stage"] == "working", answer.get("bad")
        lines = self.lines(answer)
        strike = f"{shown['contract']['strike']:g}C"
        assert lines[0].startswith("── ") and lines[0].endswith(f" BUY 1 SPX {strike} ──")
        assert f"→ execd: BUY 1 SPX {strike} LMT {shown['limit']:.2f}, stop $50" in lines[1]
        assert any("→ paper: preview" in ln for ln in lines)
        assert any(f"→ paper: BUY 1 SPX {strike} LMT {shown['limit']:.2f} + STOP" in ln for ln in lines)
        assert "WORKING" in lines[-1] and "← paper: accepted, order" in lines[-1]
        assert "FILLED" not in " ".join(lines)
        scn.run(150, until=lambda s: bool(s.held()))
        state = screen.poll()
        lines = self.lines(state)
        fill = scn.position(sym).entry_price
        assert lines[-1].endswith(f"← FILLED 1 @ {fill:.2f}")
        assert sum(ln.startswith("── ") for ln in lines) == 1   # inside its own block
        # a second SEND the page refuses: its own block, the refusal last
        screen.sel.update(limit="", stopoff="", exitspx="6370")
        screen.reprice()
        answer = screen.send()
        lines = self.lines(answer)
        assert sum(ln.startswith("── ") for ln in lines) == 2
        assert "→ SEND BUY 1 SPX " in lines[-2]
        assert "← REFUSED at the page: the entry's stop is dollars only" in lines[-1]
        assert "{" not in answer["traffic_html"]
        assert all(ln[:2].isdigit() or ln.startswith("── ") for ln in lines)   # CT-stamped
