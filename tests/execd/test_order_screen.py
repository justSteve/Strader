"""The order screen, iPad pass 4. [st-qqxj]

Steve, 2026-09-30: *"more refinements to order screen - date should be
positioned to left of time - use same font. move the stop and close at line
to above the send button. why is 'reason' now showing 'external'? The SENT
AND FILLED caption box is still not updating if a close occurs. you can
remove the 'update [n] and pause and 'less' buttons. after a position has
closed for whatever reason, collapse it's details - let's consider each
position to be a card unto itself - stack them at the bottom of the screen -
most recent at the top. permit each order to be expanded again. The card i'm
currently looking at shows a $20 loss but I had changed the SL to .3 -- did
that change register? The 'open position' screen should display both SL and
TP controls the same way they are rendered on the pre-order screen. Offer
both strike and amount triggers."*

The date's place and font are pinned in test_panel's money-row test; the
rest is here, item by item, over the real routes and the mock broker. The
13:38 CT ticket is replayed at the bottom with its own numbers.
"""

from __future__ import annotations

import datetime as dt

import pytest

from execd.compose import Contract
from execd.intent import OrderIntent
from execd.orderform import Priced, Selection, _apply_flat_loss_stop, intent_for, price
from execd.panel import closed_html, closed_positions, journal_facts, reason_words

from .conftest import CALL, SPX_NOW, page_send
from .test_bracket import box, holding, page, pos_of, text  # noqa: F401 — fixtures
from .test_orderform import chain, mono, order_page  # noqa: F401 — fixtures
from .test_triggered import mb, svc  # noqa: F401 — fixtures

DAY = dt.date(2026, 8, 26)


# ── 2. the stop and close-at row sits above SEND ─────────────────────────

class TestTheStopRowIsAboveSend:
    def test_ticket_then_the_stop_row_then_send_then_the_strikes(self, order_page):
        """Steve: "move the stop and close at line to above the send button"."""
        body = text(order_page.get("/exec/order?side=call&delta=0.3"))
        at = [body.index(s) for s in ("<div id=fd0>", "<form id=sel ", "id=stopbox", "id=exitbox",
                                      "class=sendform", "<div id=strikes>")]
        assert at == sorted(at)


# ── 3. no 'updated', pause or less ───────────────────────────────────────

class TestNoUpdatedPauseOrLess:
    def test_the_controls_and_their_code_are_gone(self, page, holding):
        """Steve: "you can remove the 'update [n] and pause and 'less'
        buttons". The fold they drove, the pause flag and the stored
        preference go with them; a failed poll is said in #pollnote."""
        body = text(page.get("/exec/order"))
        for gone in ("id=updated", "id=pause", "id=more", ">pause<", ">less<", "paused",
                     "execd.panel.compact", "setCompact", ".compact", "class=full"):
            assert gone not in body, gone
        assert "<div id=pollnote class=pollnote hidden></div>" in body
        assert "pollNote('poll failed: '" in body and "id=refresh" in body


# ── 4. the SENT AND FILLED caption follows a close ───────────────────────

class TestTheFilledCaptionGoesWithTheFill:
    def test_the_answer_is_tied_to_filled_and_a_close_moves_the_card_on(
            self, order_page, armed, chain, clock):
        """paper-0061 (st-5n3s) tied "not filled yet" to the working stage.
        "SENT AND FILLED" said nothing of its stage, so a stop out under it
        left it standing. It is tied to filled now, and every close — stop,
        target, FLATTEN, a sale in TOS — takes the card to no order."""
        r = order_page.post("/exec/order/send", data={
            "side": "call", "delta": "0.3", "ajax": "1",
            "nonce": text(order_page.get("/exec/order?side=call&delta=0.3"))
            .split("name=nonce value='")[1].split("'")[0]})
        j = r.json
        assert "SENT AND FILLED" in j["msg"] and j["msg_stage"] == "filled"
        assert j["panel_stage"] == "filled"
        p = armed.status()["positions"][0]
        clock.advance(seconds=5)
        chain.fill_resting(p["stop_order_id"])
        armed.poll_fills()
        s = order_page.get("/exec/order/state").json
        assert s["panel_stage"] == "none"                     # ≠ filled: the caption goes
        script = text(order_page.get("/exec/order")).split("var STATE = ")[1]
        assert "tied.getAttribute('data-for-stage') !== stageNow()" in script

    def test_a_working_answer_is_still_tied_to_working(self, page, armed, broker):
        broker.rest_limits = True
        r = page_send(page, {"side": "call", "delta": "0.3", "ajax": "1"})
        assert r.json["msg_stage"] == "working" and "not filled yet" in r.json["msg"]


# ── 5. a closed position is a folded card of its own ─────────────────────

def _close(svc, clock, intent_id, *, pnl, exit_px=2.00, qty=1, remaining=0, kind="protective-stop",
           order_id=None, symbol=CALL):
    clock.advance(seconds=30)
    svc.journal.record("closed", symbol=symbol, qty=qty, remaining_qty=remaining,
                       intent_id=intent_id, kind=kind, entry_price=2.10, exit_price=exit_px,
                       pnl_usd=pnl, order_id=order_id or f"{intent_id}-x{remaining}",
                       reason="resting-stop")


class TestClosedCards:
    def test_newest_on_top_one_card_per_position_and_a_partial_is_not_closed(self, armed, clock):
        _close(armed, clock, "a", pnl=-10.0)
        _close(armed, clock, "b", pnl=+20.0, qty=1, remaining=1, exit_px=2.30)   # half out
        _close(armed, clock, "c", pnl=-5.0)
        _close(armed, clock, "b", pnl=+40.0, qty=1, remaining=0, exit_px=2.50)   # the rest
        _close(armed, clock, "d", pnl=+1.0, remaining=2)                          # still held
        cards = closed_positions(journal_facts(armed))
        assert [g["key"] for g in cards] == ["b", "c", "a"]
        b = cards[0]
        assert (b["qty"], b["pnl_usd"], b["exit_price"]) == (2, 60.0, 2.40)
        html = closed_html(journal_facts(armed), clock())
        assert html.index("data-key='b'") < html.index("data-key='c'") < html.index("data-key='a'")
        assert "<details class='card closedcard' " in html and " open" not in html
        assert "b-x1, b-x0" in html                           # both parts' orders

    def test_the_line_is_contract_time_in_ct_money_and_why(self, armed, clock):
        _close(armed, clock, "a", pnl=-20.0)
        head = closed_html(journal_facts(armed), clock()).split("<summary>")[1].split("</summary>")[0]
        assert "C6400 × 1" in head and "10:00:30" in head      # 15:00:30 UTC is 10:00:30 CT
        assert "<span class='cpnl neg'>-$20.00</span>" in head and ">stop<" in head

    def test_the_stop_it_rested_at_is_on_the_card(self, armed, clock):
        """"I had changed the SL to .3 -- did that change register?" — the
        card says what rested, and how far under the limit."""
        armed.journal.record("sending", intent_id="a", symbol=CALL, limit=11.80, stop_price=11.50)
        armed.journal.record("stop_placed", intent_id="a", symbol=CALL, stop_price=11.50)
        _close(armed, clock, "a", pnl=-30.0)
        html = closed_html(journal_facts(armed), clock())
        assert "<tr><td>stop rested</td><td>11.50 (0.30 under the 11.80 limit)</td></tr>" in html

    @pytest.mark.parametrize("kind, order_type, words", [
        ("external", "STOP", "stop (an order the service was not tracking)"),
        ("external", "LIMIT", "target (an order the service was not tracking)"),
        ("external", None, "closed outside this form"),
        ("protective-stop", None, "stop"), ("resting-stop", None, "stop"),
        ("target", None, "target"), ("flatten", None, "FLATTEN"),
        ("spx-stop", None, "stop at its SPX level"), ("spx-exit", None, "close-at SPX level"),
    ])
    def test_why_in_words_and_external_named_by_its_order(self, kind, order_type, words):
        """"why is 'reason' now showing 'external'?" — 13:38 CT: the stop sent
        with the entry (paper-0078, a STOP) filled while the service was
        resting a second pair, and was booked as a sale made outside it."""
        types = {"paper-0078": order_type} if order_type else {}
        assert reason_words({"kind": kind, "order_id": "paper-0078"}, types) == words

    def test_the_1338_close_reads_as_a_stop(self, armed, clock):
        armed.journal.record("order_raw", order_id="paper-0078", why="fill:external",
                             body={"order_id": "paper-0078", "order_type": "STOP"})
        _close(armed, clock, "page-1338", pnl=-20.0, kind="external", order_id="paper-0078")
        assert "stop (an order the service was not tracking)" in closed_html(journal_facts(armed), clock())

    def test_the_page_script_keeps_an_opened_card_open(self, page, holding):
        script = text(page.get("/exec/order")).split("var STATE = ")[1]
        assert "open[ds[i].getAttribute('data-key')] = true" in script


# ── 6. the open position: both legs, both ways ───────────────────────────

class TestTheOpenPositionEditor:
    """Fill 2.10, stop 1.50 at SPX 6378, target 21.00 (the ``holding``
    fixture). Each leg: a dollar box — its distance from the fill — and an
    SPX box; ``live`` names the one he typed in."""

    def post(self, page, **data):
        return page.post("/exec/order/adjust", data={"symbol": CALL, "ajax": "1", **data}).json

    def test_a_stop_in_dollars_is_that_far_under_the_fill(self, page, holding):
        j = self.post(page, stopoff=".3", stopspx="NA", live="off")
        assert j["ok"] is True and j["msg"].startswith("Stop moved from 1.50 to 1.80")
        assert pos_of(holding)["stop_price"] == 1.80
        assert box(j["panel_body_html"], "stopoff") == ".3"

    def test_a_target_in_dollars_is_that_far_over_the_fill(self, page, holding):
        j = self.post(page, targetoff="5", targetspx="NA", live="off")
        assert j["ok"] is True and pos_of(holding)["target_price"] == 7.10

    def test_a_stop_as_an_spx_level(self, page, holding):
        j = self.post(page, stopoff="NA", stopspx="6376", live="spx")
        assert j["msg"] == "Stop set by SPX 6376.00 → rests at 0.90 (was 1.50)."
        assert box(j["panel_body_html"], "stopspx") == "6376"

    def test_live_picks_between_two_filled_boxes(self, page, holding):
        """Without the script both boxes post their numbers; ``live`` says
        which one he typed in, and with no ``live`` the dollar box wins."""
        assert self.post(page, stopoff=".6", stopspx="6376", live="spx")["msg"].startswith("Stop set by SPX 6376")
        holding._last_adjust = None
        assert self.post(page, stopoff=".4", stopspx="6376")["msg"].startswith("Stop moved from 0.90 to 1.70")

    def test_an_off_grid_distance_lands_on_the_grid_no_further_than_asked(self, page, holding):
        self.post(page, stopoff=".33", live="off")
        assert pos_of(holding)["stop_price"] == 1.80          # 1.77 → up to 1.80

    @pytest.mark.parametrize("data, words", [
        (dict(stopoff="abc", live="off"), "stop $ must be a dollar distance"),
        (dict(stopoff="0", live="off"), "stop $ must be more than nothing"),
        (dict(stopoff="3", live="off"), "below nothing"),
        (dict(targetspx="x", live="spx"), "target at SPX must be a level"),
        (dict(stopoff="NA", stopspx="NA"), "Nothing to update"),
    ])
    def test_what_cannot_be_a_leg_is_said(self, page, holding, data, words):
        j = self.post(page, **data)
        assert j["ok"] is False and words in j["bad"]
        assert pos_of(holding)["stop_price"] == 1.50

    def test_no_position_no_dollar_leg(self, page, holding):
        holding.flatten()
        j = self.post(page, stopoff=".3", live="off")
        assert j["ok"] is False and "no open position" in j["bad"]

    def test_the_script_steps_the_dollar_box_and_marks_one_box_live(self, page, holding):
        script = text(page.get("/exec/order")).split("var STATE = ")[1]
        assert "b.getAttribute('data-for') !== 'off'" in script
        assert "legLive(f, 'off')" in script and "legLive(f, 'spx')" in script
        # SET, not the first button in the form (a stepper), goes dead while it sends
        assert "f.querySelector('button.set') || f.querySelector('button')" in script


# ── 7. the .3 stop and the 13:38 CT ticket ───────────────────────────────

class TestTheThirtyCentStop:
    """2026-09-30 13:38 CT, paper: the stop box read .3; the journal's
    ``sending`` line carries ``page_query.stopoff = 0.30`` and a level struck
    for 0.30 (7693.28, from SPX 7693.71 at pricing) — the page carried it.
    The installed service (6734ac9) walked that level at SPX 7693.68, 0.03
    nearer, to 11.52, and rounded it UP to the 0.10 grid: 11.60, 0.20 under
    the 11.80 limit. 87ced9c (master, not yet installed) carries the stop's
    price with the intent and re-strikes the level from the mark at the
    send; this replays the ticket through both halves."""

    def test_the_1338_ticket_rests_its_stop_thirty_under_the_limit(self, svc, mb):
        c = Contract(symbol=CALL, strike=6400, bid_pts=11.70, ask_pts=11.80, delta=0.70,
                     expiration=DAY.isoformat(), dte=0, right="CALL")
        mb.set_quote(CALL, bid=11.70, ask=11.80)
        ticket = Priced(selection=Selection(side="call", expiry=DAY, stopoff=0.30),
                        spx=SPX_NOW, contract=c, limit=11.80)
        _apply_flat_loss_stop(ticket, c, SPX_NOW, per_contract=0.30)
        assert ticket.stop_price == 11.50 and ticket.stop_spx == 6379.57
        intent = intent_for(ticket, intent_id="page-1338", engine_sha="t")
        moved = SPX_NOW - 0.03                  # 0.03 toward the level before the send
        mb.set_quote("$SPX", bid=moved - 0.25, ask=moved + 0.25, last=moved)
        out = svc.place(OrderIntent.from_dict(intent))
        assert out["stop_order"]["price"] == 11.50           # 6734ac9 rested 11.60

    def test_a_close_at_level_is_a_level_and_sends_no_stop_price(self, armed, chain):
        """87ced9c meant a level to stay a level, but compared ``stop_set_by``
        with "level", which it never is — the close-at box sets "spx" — so a
        close-at ticket carried a price too and the service re-struck his
        level from it at the send."""
        p = price(armed, Selection.from_args({"side": "call", "strike": "6400", "exitspx": "6376"},
                                             today=DAY))
        assert p.stop_set_by == "spx" and p.stop_spx == 6376.0
        d = intent_for(p, intent_id="lvl", engine_sha="t")
        assert "stop_price" not in d and d["stop_spx"] == 6376.0 and d["exit_spx"] == 6376.0

    def test_send_carries_the_strike_on_the_ticket(self, order_page):
        """The 13:38 SEND went out as ``delta=0.8`` with no strike: SEND chose
        again at the send. It carries the strike the ticket shows now; the
        form itself keeps following δ."""
        body = text(order_page.get("/exec/order?side=call&delta=0.3"))
        fields = body.split("<span id=sendfields>")[1].split("</span>")[0]
        assert "name='strike' value='6400'" in fields and "name='delta'" not in fields
        form = body.split("<form id=sel ")[1].split("</form>")[0]
        assert "name=strike value=''" in form and "name=delta value='0.3'" in form
        j = order_page.get("/exec/order/price?side=call&delta=0.3").json
        assert "name='strike' value='6400'" in j["send_fields_html"]

    def test_send_carries_what_the_boxes_say_before_the_reprice_is_back(self, order_page):
        """The stop box writes ``stopoff`` (and the close-at box ``exitspx``)
        600 ms before its reprice goes out; SEND read only ``stop`` from the
        form, so a .3 typed and sent inside that window went as the old stop."""
        script = text(order_page.get("/exec/order?side=call")).split("var STATE = ")[1]
        assert "['stop', 'stopoff', 'exitspx', 'limit', 'lots'].forEach" in script
        assert "fd.set('strike', sk.value); fd.delete('delta');" in script


def test_the_poll_carries_the_days_total_with_the_closed_cards():
    """The closed cards repainted after a close while the 'today' line under
    them kept the old total until a reload (seen in the 2026-09-30 shots:
    three cards summing −$80 over 'today −$10'). The poll now carries it."""
    import inspect
    from execd import page, panel
    assert "today_text" in inspect.getsource(page)
    assert "getElementById('today')" in panel.PANEL_SCRIPT
