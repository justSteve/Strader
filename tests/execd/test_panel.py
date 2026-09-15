"""The order status panel — one card, seven stages. [st-4ezg]

What the design (docs/design/order-status-panel, Steve's 2026-09-14 review)
has to mean in code: every stage is read off the service and the day's
journal; the names are ``C6400``; every time but the header clock is *x ago*;
one net number, commissions included; the filled stage is the bracket's live
editor; a working entry has CANCEL AND RE-PRICE and no STOP; a refusal or a
preview never hides money that is live; the state JSON carries the stage and
the body the script polls.
"""

from __future__ import annotations

import datetime as dt

import pytest

from execd.panel import ago, contract_name, journal_facts, stage_of
from execd.service import ExecService

from .conftest import CALL, PUT, SPX_NOW, entry
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
        assert stage_of(st, facts, previewed=True) == "previewed"
        assert stage_of(st, facts, refused=True) == "refused"
        assert stage_of(st, facts, previewed=True, refused=True) == "refused"


# ── the card on the page ─────────────────────────────────────────────────

class TestTheCard:
    def test_none_shows_no_card_and_the_strip_carries_the_mode(self, page):
        """With nothing held, nothing working and no preview the page opens on
        the side buttons: no stage card at all (design docs/design/order-page,
        st-shhi). The strip carries the mode and the day line the attempts."""
        body = text(page.get("/exec/order"))
        assert "<div id=panel " not in body
        assert "0 of 2 attempts" in body
        assert "badge live'>LIVE" in body and "badge paper" not in body
        assert "BULLISH" in body and "BEARISH" in body

    def test_the_header_has_one_clock_and_the_rest_is_ago(self, page, holding, clock):
        body = text(page.get("/exec/order"))
        card = panel_of(body)
        assert body.count("id=clock") == 1                     # one clock on the page — in the strip
        assert "10:00:00" in body                              # the clock, CT
        assert "id=clock" not in card                          # the card no longer repeats it
        assert "class=ago data-at=" in card                    # the fill, ticking
        assert "id=updated class=ago" in card
        assert ">pause<" in card and ">less<" in card and "id=refresh" in card

    def test_previewed_carries_the_cost_line_send_and_re_price(self, page):
        body = text(page.post("/exec/order/preview", data={"side": "call", "delta": "0.3"}))
        card = panel_of(body)
        assert stage_word(body) == "PREVIEWED"
        assert "C6400 × 1 · buy limit 2.10 = $210.00" in card
        assert "broker's cost line" in card and "$210.65" in card
        assert "on fill</td><td>stop" in card and "target 21.00" in card
        assert "action='/exec/order/send'" in card and ">SEND<" in card
        assert "name=nonce value='" in card
        assert ">RE-PRICE</a>" in card and "href='/exec/order?side=call" in card
        assert "SEND good for 60 s" in card

    def test_working_names_the_gap_to_the_ask_and_offers_only_cancel(self, page, armed, broker, clock):
        broker.rest_limits = True
        r = page.post("/exec/order/preview", data={"side": "call", "delta": "0.3"})
        nonce = text(r).split("name=nonce value='")[1].split("'")[0]
        page.post("/exec/order/send", data={"nonce": nonce})
        clock.advance(seconds=12)
        broker.set_quote(CALL, bid=2.00, ask=2.15)
        body = text(page.get("/exec/order"))
        card = panel_of(body)
        assert stage_word(body) == "WORKING"
        assert "buy limit 2.10 · sent <span class=ago" in card and "12 s ago" in card
        assert "ask above the limit" in card and ">+0.05<" in card
        assert "bid 2.00 / ask 2.15" in card
        assert "cut if SPX reaches" in card and "target 10× the fill" in card
        assert "CANCEL AND RE-PRICE" in card and ">STOP<" not in card and ">FLATTEN<" not in card

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
        assert "name=stop_price inputmode=decimal value='1.50'" in card
        assert "name=target_price inputmode=decimal value='21.00'" in card
        assert f"{v['at_stop_usd']:+,.2f}".replace("+", "+$").replace("-", "-$") in card
        assert ">UPDATE<" in card
        assert "action='/exec/flatten'" in card and ">FLATTEN<" in card
        assert "action='/exec/stop'" in card and ">STOP<" in card
        # no footer, no explanatory line under the controls
        assert "tailnet only" not in card

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
        assert "FLATTEN AGAIN" in card and ">UPDATE<" not in card and ">STOP<" not in card

    def test_closed_shows_the_last_close_and_offers_a_new_order(self, page, holding, broker, clock):
        clock.advance(seconds=99)
        broker.set_quote(CALL, bid=2.30, ask=2.40)
        holding.flatten()
        clock.advance(seconds=40)
        body = text(page.get("/exec/order"))
        card = panel_of(body)
        assert stage_word(body) == "CLOSED"
        assert "C6400 × 1 · closed <span class=ago" in card and "40 s ago" in card
        assert "P&amp;L" in card and "+$20.00" in card
        assert "2.10 → 2.30 · held 1 m 39 s" in card
        assert "reason</td><td>flatten" in card
        assert "realized +$20.00 over 1 close(s)" in card
        assert ">NEW ORDER</a>" in card and "href='/exec/order'" in card

    def test_a_refusal_with_nothing_live_is_the_refused_stage(self, page, armed):
        armed.stop()
        body = text(page.post("/exec/order/preview", data={"side": "call", "delta": "0.3"}))
        card = panel_of(body)
        assert stage_word(body) == "REFUSED"
        assert "Refused (" in card and ">RE-PRICE</a>" in card
        assert body.count("Refused (") == 1, "the refusal is the card, not a box above it too"

    def test_a_refusal_with_money_live_keeps_the_editor_in_reach(self, page, holding):
        r = page.post("/exec/order/adjust", data={"symbol": CALL, "stop_price": "abc"})
        body = text(page.get(r.headers["Location"]))
        assert stage_word(body) == "FILLED" and ">UPDATE<" in body
        assert "<div class=bad>Not updated:" in body
        assert "data-stage=refused" not in body

    def test_a_preview_while_holding_renders_the_ticket_above_the_live_part(self, holding):
        from execd.panel import panel_body
        actions = {n: f"/exec/{n.replace('_', '/')}" for n in (
            "index", "stop", "flatten", "order", "order_send", "order_adjust", "order_cancel")}
        preview = {"preview": {"symbol": PUT, "qty": 1, "price": 1.90, "cost_usd": 190.0,
                               "total_usd": 190.65, "accepted": True}}
        stage, body = panel_body(holding, holding.status(), actions, now=holding.clock(),
                                 order_path="/exec/order", sel_query={"side": "put"},
                                 preview=preview, nonce="n-1")
        assert stage == "previewed"
        assert body.index(">SEND<") < body.index(">UPDATE<")
        assert "P6300 × 1 · buy limit 1.90" in body and "NET NOW" in body and ">FLATTEN<" in body

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
        assert ">UPDATE<" in s["panel_body_html"] and "NET NOW" in s["panel_body_html"]

    def test_the_polled_body_never_carries_a_request_owned_stage(self, page, armed):
        page.post("/exec/order/preview", data={"side": "call", "delta": "0.3"})
        s = page.get("/exec/order/state").get_json()
        assert s["panel_stage"] == "none"

    def test_every_action_on_the_card_is_an_absolute_exec_path(self, page, holding):
        for body in (text(page.get("/exec/order")),
                     text(page.post("/exec/order/preview", data={"side": "put", "delta": "0.3"}))):
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
    return app.test_client()
