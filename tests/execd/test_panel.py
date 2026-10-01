"""The order status panel — one card, seven stages. [st-4ezg]

What the design (docs/design/order-status-panel, Steve's 2026-09-14 review)
has to mean in code: every stage is read off the service and the day's
journal; the names are ``C6400``; every time but the header clock is *x ago*;
one net number, commissions included; the filled stage is the bracket's live
editor; a working entry has CANCEL AND RE-PRICE and no STOP; a refusal or a
refusal never hides money that is live; the state JSON carries the stage and
the body the script polls.
"""

from __future__ import annotations

import datetime as dt

import pytest

from execd.panel import ago, contract_name, journal_facts, stage_of
from execd.service import ExecService

from .conftest import CALL, PUT, SPX_NOW, entry, page_send
from .conftest import same_origin  # noqa: E402
from .test_bracket import TRIGGER, holding, page, pos_of, text  # noqa: F401 — fixtures


def panel_of(body: str) -> str:
    """The card, header to the end of its body."""
    assert "<div id=panel " in body, "no panel on the page"
    return body.split("<div id=panel ")[1].split("<div class=side>")[0]


def stage_word(body: str) -> str:
    return panel_of(body).split("id=stageword")[1].split(">")[1].split("<")[0]


# ── words for numbers ────────────────────────────────────────────────────

class TestWords:
    def test_a_contract_is_right_and_strike(self):
        assert contract_name(CALL) == "C6400"
        assert contract_name(PUT) == "P6300"
        assert contract_name("SPXW  260826C06412500") == "C6412.5"

    def test_a_name_that_is_not_occ_comes_back_trimmed(self):
        assert contract_name("  $SPX ") == "$SPX"

    def test_ago_uses_the_designs_units(self):
        assert ago(0) == "0 s" and ago(12) == "12 s" and ago(59.9) == "59 s"
        assert ago(95) == "1 m 35 s" and ago(120) == "2 m" and ago(60) == "1 m"
        assert ago(3600) == "1 h 00 m" and ago(7500) == "2 h 05 m"
        assert ago(None) == "—"


# ── the stage, off the service ───────────────────────────────────────────

class TestStage:
    def test_nothing_is_none(self, armed: ExecService):
        assert stage_of(armed.status(), journal_facts(armed)) == "none"

    def test_a_resting_entry_is_working(self, armed: ExecService, broker):
        broker.rest_limits = True
        armed.place(entry())
        assert stage_of(armed.status(), journal_facts(armed)) == "working"

    def test_a_fill_is_filled_and_a_close_in_flight_is_exiting(self, holding: ExecService, broker):
        assert stage_of(holding.status(), journal_facts(holding)) == "filled"
        broker.rest_market = True
        holding.observe(TRIGGER)
        assert stage_of(holding.status(), journal_facts(holding)) == "exiting"

    def test_a_close_leaves_closed_until_the_next_order(self, holding: ExecService):
        holding.flatten()
        assert holding.status()["positions"] == []
        assert stage_of(holding.status(), journal_facts(holding)) == "closed"

    def test_the_request_owned_stages_win_over_a_resting_service(self, armed: ExecService):
        st, facts = armed.status(), journal_facts(armed)
        assert stage_of(st, facts, refused=True) == "refused"


# ── the card on the page ─────────────────────────────────────────────────

class TestTheCard:
    def test_none_shows_no_card_and_the_strip_carries_the_mode(self, page):
        """With nothing held, nothing working and no answer the page opens on
        the side buttons: no stage card at all (design docs/design/order-page,
        st-shhi). The strip carries the mode, and nothing on the page counts
        attempts at him (st-644f)."""
        body = text(page.get("/exec/order"))
        assert "<div id=panel hidden " in body and "<div id=panel class" not in body   # hidden until a stage arrives (st-igw0)
        assert "attempts" not in body and "headroom" not in body
        assert "badge live'>LIVE" in body and "badge paper" not in body
        assert "BULLISH" in body and "BEARISH" in body

    def test_no_clock_beside_the_arming_word_and_the_card_still_ticks(
            self, page, holding, clock):
        """Steve, 2026-09-18: "remove the timestamp the order was armed"
        (st-644f) — not beside the arming word. Steve, 2026-09-30 (iPad): the
        clock comes back on the money row, left, with the buying power
        right-aligned; the strip stays clockless. The card's relative 'ago'
        stamps stay."""
        body = text(page.get("/exec/order"))
        card = panel_of(body)
        strip = body.split("id=strip>")[1].split("</div></div>")[0]
        assert "id=clock" not in strip
        # the date to the LEFT of the clock, in the clock's own font (Steve,
        # 2026-09-30, st-qqxj)
        assert ("<div class=money><span class=when><span id=day class=clock>08-26</span> "
                "<span id=clock class=clock></span></span>") in body
        # the position's own best/worst water marks are labelled and stay
        assert "class=ago data-at=" in card                    # the fill, ticking
        # no 'updated', pause or less (Steve, 2026-09-30, st-qqxj); refresh stays
        assert "id=updated" not in card and ">pause<" not in card and ">less<" not in card
        assert "id=refresh" in card

    def test_working_names_the_gap_to_the_ask_and_offers_only_cancel(self, page, armed, broker, clock):
        broker.rest_limits = True
        page_send(page, {"side": "call", "delta": "0.3"})
        clock.advance(seconds=12)
        broker.set_quote(CALL, bid=2.00, ask=2.15)
        body = text(page.get("/exec/order"))
        card = panel_of(body)
        assert stage_word(body) == "WORKING"
        assert "buy limit 2.10 · sent <span class=ago" in card and "12 s ago" in card
        assert "ask above the limit" in card and ">+0.05<" in card
        assert "bid 2.00 / ask 2.15" in card
        assert "cut if SPX reaches" in card and "target 10× the entry" in card
        assert "CANCEL AND RE-PRICE" in card and ">STOP<" not in card and ">FLATTEN<" not in card

    def test_a_not_filled_yet_caption_goes_when_the_card_moves_on(self, page):
        """2026-09-30, paper-0061: the fill landed inside the SEND answer, the
        card said FILLED and the caption still said WORKING. The caption is
        tied to the working stage and dropped once the card leaves it [st-5n3s]."""
        body = text(page.get("/exec/order"))
        assert "if (forStage && stageNow() && stageNow() !== forStage) return;" in body
        assert "document.querySelector('#answer [data-for-stage]')" in body
        assert "answerBox(j.bad || j.msg || '', !!j.bad, j.msg_stage || null)" in body

    def test_the_cards_stop_and_target_have_steppers(self, page, holding):
        """Steve, 2026-09-30: after a fill, the take-profit updates the same
        way the stop does — + left of the box, − right, then SET [st-5n3s];
        and as the ticket's stop row is, a dollar box between the steppers
        and an SPX box after it (st-qqxj)."""
        card = panel_of(text(page.get("/exec/order")))
        for leg in ("stop", "target"):
            form = card.split(f"data-leg={leg}>")[1].split("</form>")[0]
            plus, box, minus, spx, set_ = (form.index("data-step=1 "), form.index(f"name={leg}off "),
                                           form.index("data-step=-1"), form.index(f"name={leg}spx "),
                                           form.index(">SET<"))
            assert plus < box < minus < spx < set_
            assert "class='dl stopl'" in form and "class='dl exitl'" in form

    def test_filled_is_the_live_editor_with_one_net_number(self, page, holding, broker, clock):
        clock.advance(seconds=95)
        broker.set_quote(CALL, bid=2.30, ask=2.40)
        body = text(page.get("/exec/order"))
        card = panel_of(body)
        assert stage_word(body) == "FILLED"
        assert "C6400 × 1 · in 2.10 · <span class=ago" in card and "1 m 35 s ago" in card
        v = pos_of(holding)["valuation"]
        assert "NET NOW" in card and f"+${v['net_if_closed_usd']:.2f}" in card
        assert "SPX 6380.00, cut " in card
        assert "aria-label='stop in dollars' value='.6'" in card
        assert "aria-label='target in dollars' value='18.9'" in card
        assert f"{v['at_stop_usd']:+,.2f}".replace("+", "+$").replace("-", "-$") in card
        assert ">SET<" in card
        assert "action='/exec/flatten'" in card and ">FLATTEN<" in card
        assert "action='/exec/stop'" not in card and ">STOP<" not in card     # no STOP (2026-09-30)
        # no footer, no explanatory line under the controls
        assert "tailnet only" not in card

    def test_the_stop_note_is_the_brokers_answer_not_the_id(self, page, holding, broker, clock):
        """Findings 39 and 41 (st-vqmr): the card keyed NO STOP RESTING on the
        price, so a stop the broker had cancelled still showed its money."""
        from execd.service import LEG_SETTLE_S
        p = pos_of(holding)
        sid = p["stop_order_id"]
        saved = broker._orders.pop(sid)
        holding.reconcile()                            # first seen missing
        clock.advance(seconds=LEG_SETTLE_S + 1)
        holding.reconcile()                            # still missing past the window
        card = panel_of(text(page.get("/exec/order")))
        assert "NOT IN THE BROKER'S LISTING" in card and "NO STOP RESTING" not in card
        broker._orders[sid] = saved
        holding.reconcile()
        card = panel_of(text(page.get("/exec/order")))
        assert "NOT IN THE BROKER'S LISTING" not in card
        holding._open[CALL].stop_order_id = None      # no order behind the price
        card = panel_of(text(page.get("/exec/order")))
        assert "NO STOP RESTING" in card

    def test_exiting_shows_the_send_time_and_flatten_again(self, page, holding, broker, clock):
        broker.rest_market = True
        holding.observe(TRIGGER)
        clock.advance(seconds=4)
        body = text(page.get("/exec/order"))
        card = panel_of(body)
        assert stage_word(body) == "SELLING"
        assert "C6400 × 1 · in 2.10 · selling" in card
        assert "market sell sent" in card and "4 s ago" in card
        assert "reason</td><td>spx-stop" in card and "stop · target</td><td>cancelled" in card
        assert "FLATTEN AGAIN" in card and ">SET<" not in card and ">STOP<" not in card

    def test_a_close_folds_into_its_own_card_at_the_foot(self, page, holding, broker, clock):
        """Steve, 2026-09-30: "after a position has closed for whatever
        reason, collapse it's details - let's consider each position to be a
        card unto itself - stack them at the bottom of the screen" [st-qqxj].
        The card goes back to no order, hidden; the close is a folded card
        under the strikes, its line the contract, the CT time, the money and
        why, its details one tap away."""
        clock.advance(seconds=99)
        broker.set_quote(CALL, bid=2.30, ask=2.40)
        holding.flatten()
        clock.advance(seconds=40)
        body = text(page.get("/exec/order"))
        assert "<div id=panel hidden class='card panel'>" in body and "data-stage=none" in body
        assert ">NEW ORDER</a>" not in body and "data-stage=closed" not in body
        stack = body.split("<div id=closed>")[1].split("<div class=foot>")[0]
        assert body.index("class=side") < body.index("<div id=closed>") < body.index("class=foot")
        assert "<details class='card closedcard' data-key='br-1'>" in stack   # folded: no open
        head = stack.split("<summary>")[1].split("</summary>")[0]
        # the money net of both commissions, as the open card's is (st-ocnp)
        assert "C6400 × 1" in head and "10:01:39" in head and "+$18.70" in head and "FLATTEN" in head
        assert "<tr><td>before fees</td><td>+$20.00 ($1.30 in commissions)</td></tr>" in stack
        assert "2.10 → 2.30 · held 1 m 39 s" in stack
        assert "<tr><td>reason</td><td>FLATTEN</td></tr>" in stack

    def test_a_refusal_with_nothing_live_is_the_refused_stage(self, page, armed):
        armed.stop()
        r = page_send(page, {"side": "call", "delta": "0.3"})
        body = text(page.get(r.headers["Location"]))
        card = panel_of(body)
        assert stage_word(body) == "REFUSED"
        assert "Refused (" in card and ">RE-PRICE</a>" in card
        assert body.count("Refused (") == 1, "the refusal is the card, not a box above it too"

    def test_a_refusal_with_money_live_keeps_the_editor_in_reach(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "abc"})
        body = text(page.get(r.headers["Location"]))
        assert stage_word(body) == "FILLED" and ">SET<" in body
        assert "<div class=bad>Not updated:" in body
        assert "data-stage=refused" not in body

    def test_stop_on_is_said_and_stop_is_not_offered_again(self, page, holding):
        holding.stop()
        card = panel_of(text(page.get("/exec/order")))
        assert "STOP IS ON" in card and ">STOP<" not in card and ">FLATTEN<" in card

    def test_paper_mode_is_the_badge(self, service, chain_page_paper):
        body = text(chain_page_paper.get("/exec/order"))
        assert "<span class='badge paper'>PAPER</span>" in body.split("<div class=side>")[0]   # the strip
        assert "badge live" not in body


# ── the state JSON the script polls ──────────────────────────────────────

class TestTheStateJson:
    def test_it_carries_the_stage_and_the_body(self, page, holding):
        s = page.get("/exec/order/state").get_json()
        assert s["panel_stage"] == "filled"
        assert s["panel_body_html"].startswith("<div class=body data-stage=filled>")
        assert ">SET<" in s["panel_body_html"] and "NET NOW" in s["panel_body_html"]

    def test_the_polled_body_never_carries_a_request_owned_stage(self, page, armed):
        armed.stop()
        page_send(page, {"side": "call", "delta": "0.3"})       # refused: a request-owned stage
        s = page.get("/exec/order/state").get_json()
        assert s["panel_stage"] == "none"

    def test_every_action_on_the_card_is_an_absolute_exec_path(self, page, holding):
        for body in (text(page.get("/exec/order")),
                     text(page.get("/exec/order?side=put&delta=0.3"))):
            card = panel_of(body)
            actions = [a.split("'")[0] for a in card.split("action='")[1:]]
            hrefs = [a.split("'")[0] for a in card.split("href='")[1:]]
            assert actions and all(a.startswith("/exec/") for a in actions), actions
            assert all(h.startswith("/exec/") for h in hrefs), hrefs

    def test_no_secret_on_the_card(self, page, holding):
        body = text(page.get("/exec/order"))
        assert "not-a-real-credential" not in body


@pytest.fixture
def chain_page_paper(broker, clock, tmp_path):
    """A paper-mode service behind the page, the chain set."""
    import httpx
    from execd.page import create_page
    from execd.paper import PaperBroker
    from execd.service import ServiceConfig
    from execd.vault import Vault
    from .conftest import schwab_chain_maps
    from .test_page import CALLBACK, PASS, Schwab, vault_payload
    broker.set_chain("SPXW", schwab_chain_maps())
    paper = PaperBroker(broker, clock=clock)
    svc = ExecService(paper, ServiceConfig(state_dir=tmp_path / "p", sha="t", mode="paper"), clock=clock)
    svc.unlock({"token": "x"})
    vault = Vault(tmp_path / "vault.json")
    vault.store(vault_payload(), PASS)
    app = create_page(svc, vault=vault, market=None, callback_url=CALLBACK,
                      http_client=httpx.Client(base_url="https://api.schwabapi.com",
                                               transport=httpx.MockTransport(Schwab())),
                      clock=clock)
    app.config["TESTING"] = True
    return same_origin(app.test_client())


class TestNewOrderClearsTheCard:
    """Steve, 2026-09-15: "New Order button should clear prior order screen
    before all else." A closed or refused card is history the moment the
    next order begins — NEW ORDER, or a side picked."""

    def test_a_closed_card_stays_in_the_stack_whatever_begins_next(self, page, holding, broker, clock):
        """A close is not the card's any more (st-qqxj), so there is nothing
        for NEW ORDER or a side to clear: the day's closes stay folded at the
        foot on every load."""
        stop_id = pos_of(holding)["stop_order_id"]
        clock.advance(seconds=1)
        broker.trigger_stop(stop_id)
        holding.poll_fills()
        for url in ("/exec/order", "/exec/order?new=1", "/exec/order?side=call"):
            body = text(page.get(url))
            assert "data-stage=closed" not in body and "data-key='br-1'" in body, url

    def test_refused_clears_the_same_way(self, page, service, broker):
        from execd.broker import Preview
        service.unlock({"t": 1})
        real = broker.preview
        broker.preview = lambda intent: Preview(symbol=intent.symbol, side=intent.side, qty=intent.qty,
                                                order_type=intent.order_type, price=2.10, cost_usd=210.0,
                                                commission_usd=0.65, accepted=False,
                                                messages=("reject: not enough buying power",))
        page_send(page, {"side": "call", "delta": "0.3"})       # refused by the broker's preview
        broker.preview = real
        assert "data-stage=refused" in text(page.get("/exec/order"))
        assert "data-stage=refused" not in text(page.get("/exec/order?new=1"))
        assert "data-stage=refused" not in text(page.get("/exec/order?side=put"))


class TestTheAccountsMoney:
    """Steve, 2026-09-15: "display account's option buying power". One
    figure, in Schwab's words (2026-09-17: "option buying power and
    available is redundant", st-bafu); the ticket speaks of the account only
    when it cannot pay — the 09:54 refusal was this arithmetic."""

    def test_one_money_figure_and_the_ticket_warns_only_when_it_is_short(
            self, page, service, broker):
        broker.set_balances(available_funds=150.0, option_buying_power=150.0, buying_power=300.0)
        service.unlock({"t": 1})
        service._balances_cache = None            # the unlock's status read came before the money
        # the opening strike is one the account can pay for (Steve,
        # 2026-09-30: "the highest delta that creates a legal order"); a
        # tapped one it cannot is still said
        body = text(page.get("/exec/order?side=call&delta=0.3"))
        assert "<span id=balances><b>$150.00</b></span>" in body and "available $150.00" not in body
        assert "option buying power" not in body and "this needs" not in body
        body = text(page.get("/exec/order?side=call&strike=6400"))
        assert "this needs $210.00 and the account has $150.00 available" in body
        broker.set_balances(available_funds=1607.24, option_buying_power=1607.24)
        service._balances_cache = None
        body = text(page.get("/exec/order?side=call&delta=0.3"))
        assert "available" not in body and "after this" not in body
        j = page.get("/exec/order/state").get_json()
        assert j["balances_html"] == "<b>$1,607.24</b>"

    def test_a_broker_that_cannot_say_is_said_not_hidden(self, page, service, broker):
        service.unlock({"t": 1})
        body = text(page.get("/exec/order"))
        assert "account: no balances set on the mock" in body


class TestTheClosedStackUnderThePoll:
    """The poll carries the day's closed cards and the card's own stage; the
    script hides the card when it goes back to no order and repaints the
    stack only when it changed, keeping a card he opened open (st-qqxj)."""

    def test_the_poll_carries_the_stack_and_the_script_keeps_what_is_open(self, page, holding, broker, clock):
        stop_id = pos_of(holding)["stop_order_id"]
        clock.advance(seconds=1)
        broker.trigger_stop(stop_id)
        holding.poll_fills()
        s = page.get("/exec/order/state").get_json()
        assert s["panel_stage"] == "none" and "last_close_ts" not in s
        assert "data-key='br-1'" in s["closed_html"]
        script = text(page.get("/exec/order")).split("var STATE = ")[1]
        assert "pn.hidden = (j.panel_stage === 'none')" in script
        assert "cs.__html !== j.closed_html" in script and "details[open]" in script
        assert "data-dismissed" not in script and "last_close_ts" not in script


class TestATypedNumberOutlivesTheRepaint:
    """2026-09-16 10:19 CT (st-4b0p): a target strike typed into the SET box,
    Enter, and "the dollar amount stayed in the input" — no adjust request
    in the journal. Focus had left the box, so the 3 s repaint put the
    resting price back before the Enter. Typed and unsent is now carried
    across the repaint, name by name, with focus and caret."""

    def test_the_script_keeps_typed_values_across_a_repaint(self, page, armed):
        body = text(page.get("/exec/order"))
        assert "function keepTyped(root)" in body and "function restoreTyped(root, kept)" in body
        assert "a.value === a.defaultValue" in body
        assert "var kept = keepTyped(body); body.innerHTML = j.panel_body_html; restoreTyped(body, kept);" in body
        assert "var keptp = keepTyped(pc); pc.innerHTML = j.position_html || ''; restoreTyped(pc, keptp);" in body
