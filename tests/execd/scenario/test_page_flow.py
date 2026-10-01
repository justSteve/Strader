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

    def test_the_close_at_box_sends_a_level_and_no_price(self, make):
        scn = make(flat())
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        shown = screen.type_exit(6376)
        assert shown["stop_set_by"] == "spx" and shown["stop_spx"] == 6376.0
        got = received_matches_shown(screen.send(), shown)
        assert got["exit_spx"] == 6376.0

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
        assert screen.closed_cards(state) == [c["pnl_usd"] for c in scn.closes()]
        assert screen.today(state) == scn.service.status()["pnl"]["day_usd"] == scn.realized()

        # a second trade, closed the same way: two cards, newest on top
        scn.wait_until(150)
        screen.pick("call", delta=0.5)
        screen.send()
        scn.run(110, until=lambda s: not s.held())
        state = screen.poll()
        closes = scn.closes()
        assert len(closes) == 2
        assert screen.closed_cards(state) == [c["pnl_usd"] for c in reversed(closes)]
        assert screen.today(state) == scn.realized()

    def test_an_open_position_is_on_the_day_at_its_net(self, make):
        scn = make(flat())
        screen = OrderScreen(scn)
        screen.pick("call", delta=0.5)
        screen.send()
        state = screen.poll()
        net = state["positions"][0]["valuation"]["net_if_closed_usd"]
        assert screen.today(state) == state["pnl"]["day_usd"] == net
