"""The order form — by code alone. [st-k6gl]

The choice rules (nearest to spot, a delta override, a tapped strike), the
priced ticket (the engine's derivation, the service's tick grid, the resting
stop), and the page: side → strikes → FD0 → send, over the real
routes and the mock broker, with the same journal the live ticket writes.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest

from execd.orderform import Selection, choose, intent_for, load_chain, next_weekday, price
from execd.page import CredentialFile, create_page
from execd.service import ExecService
from execd.vault import Vault

from .conftest import CALL, PUT, SPX_NOW, Clock, page_send, schwab_chain_maps
from .conftest import same_origin  # noqa: E402
from .test_page import CALLBACK, PASS, Schwab, market_payload, vault_payload

DAY = dt.date(2026, 8, 26)


@pytest.fixture
def mono():
    """A monotonic clock a test can move (the page's nonce TTLs)."""
    class Mono:
        t = 1000.0
        def __call__(self):
            return self.t
    return Mono()


@pytest.fixture
def chain(broker):
    broker.set_chain("SPXW", schwab_chain_maps())
    return broker


@pytest.fixture
def order_page(armed: ExecService, chain, clock: Clock, mono, tmp_path):
    vault = Vault(tmp_path / "vault.json")
    vault.store(vault_payload(), PASS)
    mfile = tmp_path / "market.json"
    mfile.write_text(json.dumps(market_payload()))
    market = CredentialFile(mfile)
    market.load()
    app = create_page(armed, vault=vault, market=market, callback_url=CALLBACK,
                      http_client=httpx.Client(base_url="https://api.schwabapi.com",
                                               transport=httpx.MockTransport(Schwab())),
                      clock=clock, monotonic=mono)
    app.config["TESTING"] = True
    return same_origin(app.test_client())


def text(r) -> str:
    return r.get_data(as_text=True)


# ── selection ────────────────────────────────────────────────────────────

class TestSelection:
    def test_from_args_is_tolerant(self):
        s = Selection.from_args({"side": "CALL", "delta": "0.3", "budget": "150", "attempts": "3",
                                 "strike": "6400", "lots": "5"}, today=DAY, lots_cap=1)
        assert (s.side, s.delta, s.budget_usd, s.attempts, s.strike, s.lots) == \
            ("call", 0.3, 150.0, 3, 6400.0, 1)
        assert s.expiry == DAY and s.right == "CALL"
        junk = Selection.from_args({"side": "up", "delta": "9", "budget": "-1", "attempts": "x"},
                                   today=DAY)
        assert junk.side is None and junk.delta is None
        assert junk.budget_usd == 100.0 and junk.attempts == 2

    def test_expiry_words(self):
        assert Selection.from_args({"expiry": "1"}, today=DAY).expiry == dt.date(2026, 8, 27)
        assert Selection.from_args({"expiry": "next"}, today=dt.date(2026, 8, 28)).expiry == dt.date(2026, 8, 31)
        assert Selection.from_args({"expiry": "2026-09-14"}, today=DAY).expiry == dt.date(2026, 9, 14)
        assert next_weekday(dt.date(2026, 9, 11)) == dt.date(2026, 9, 14)

    def test_as_query_drops_defaults_and_honours_overrides(self):
        s = Selection(side="put", expiry=DAY, delta=0.3)
        assert s.as_query() == {"side": "put", "expiry": "2026-08-26", "delta": "0.3"}
        assert s.as_query(strike="6300", delta=None) == {"side": "put", "expiry": "2026-08-26",
                                                         "strike": "6300"}


# ── the choice ───────────────────────────────────────────────────────────

class TestChoice:
    def test_default_is_nearest_to_spot(self, armed, chain):
        contracts, spx = load_chain(armed, DAY, "CALL")
        assert spx == SPX_NOW and [c.strike for c in contracts][:3] == [6350, 6360, 6370]
        assert choose(contracts, spx, strike=None, delta=None).strike == 6380

    def test_delta_override_picks_the_nearest_delta(self, armed, chain):
        contracts, spx = load_chain(armed, DAY, "CALL")
        assert choose(contracts, spx, strike=None, delta=0.30).strike == 6400
        assert choose(contracts, spx, strike=None, delta=0.65).strike == 6360

    def test_a_tapped_strike_wins_and_a_missing_one_says_so(self, armed, chain):
        contracts, spx = load_chain(armed, DAY, "PUT")
        assert choose(contracts, spx, strike=6300, delta=0.5).strike == 6300
        with pytest.raises(ValueError, match="no strike 6305"):
            choose(contracts, spx, strike=6305, delta=None)

    def test_the_chain_read_is_bounded_and_for_one_right(self, armed, chain):
        load_chain(armed, DAY, "PUT")
        kw = [c[1] for c in chain.calls if c[0] == "market_read"][-1]
        assert kw["kind"] == "chains"
        assert kw["params"]["strikeCount"] == "40" and kw["params"]["contractType"] == "PUT"
        assert kw["params"]["fromDate"] == "2026-08-26" == kw["params"]["toDate"]


# ── the priced ticket ────────────────────────────────────────────────────

class TestPrice:
    def test_the_ticket_carries_every_number(self, armed, chain):
        p = price(armed, Selection(side="call", expiry=DAY, delta=0.30))
        assert p.error is None and p.contract.symbol == CALL
        assert p.limit == 2.10 and p.cost_usd == 210.0 and p.commissions_usd == 1.30
        t = p.ticket
        assert t.stop_trigger_spx < SPX_NOW                        # a call cuts below spot
        assert p.stop_price is not None and p.stop_price < p.limit
        assert p.net_at_stop_usd == pytest.approx((p.stop_price - 2.10) * 100 - 1.30)
        d = p.to_dict()
        assert d["contract"]["chosen"] and d["stop_spx"] == t.stop_trigger_spx
        assert d["derivation"]["attempts_left"] == 2 and d["budget_usd"] == 100.0
        assert [s["strike"] for s in d["strikes"]] == [6350, 6360, 6370, 6380, 6390, 6400, 6410, 6420]
        assert sum(1 for s in d["strikes"] if s["chosen"]) == 1

    def test_the_limit_sits_on_the_services_tick_grid(self, armed, chain):
        p = price(armed, Selection(side="put", expiry=DAY, strike=6320))   # ask 3.20 → 0.10 grid
        assert p.limit == 3.20
        chain.set_chain("SPXW", {"calls": {}, "puts": {"2026-08-26:0": {"6320.0": [{
            "symbol": PUT.replace("6300", "6320").replace("06300000", "06320000"),
            "strikePrice": 6320.0, "bid": 3.75, "ask": 3.85, "delta": -0.4}]}}})
        p = price(armed, Selection(side="put", expiry=DAY))
        assert p.limit == 3.90                                       # 3.85 is off the 0.10 grid

    def test_faults_are_words_not_exceptions(self, armed, chain):
        assert price(armed, Selection()).error == "pick BULLISH or BEARISH"
        chain.fail_next = "down"
        assert "could not be read" in price(armed, Selection(side="call", expiry=DAY)).error
        chain.set_chain("SPXW", {"calls": {}, "puts": {}})
        assert "no calls expiring" in price(armed, Selection(side="call", expiry=DAY)).error

    def test_a_budget_the_friction_eats_is_reported(self, armed, chain):
        p = price(armed, Selection(side="call", expiry=DAY, strike=6350, budget_usd=20, attempts=2))
        assert p.error and "could not fund" in p.error and p.contract.strike == 6350

    def test_intent_for_is_the_services_wire_form(self, armed, chain):
        p = price(armed, Selection(side="call", expiry=DAY, delta=0.30))
        i = intent_for(p, intent_id="page-20260826T100000", engine_sha="testsha")
        assert i == {"intent_id": "page-20260826T100000", "symbol": CALL, "side": "BUY_TO_OPEN",
                     "qty": 1, "order_type": "LIMIT", "limit": 2.10,
                     "stop_spx": p.ticket.stop_trigger_spx, "delta": 0.3,
                     "source": "page", "engine_sha": "testsha"}


# ── the page ─────────────────────────────────────────────────────────────

class TestPage:
    def test_no_side_asks_for_one(self, order_page):
        body = text(order_page.get("/exec/order"))
        assert "pick a side" in body and "BULLISH" in body and "BEARISH" in body
        assert "<title>trade</title>" in body and "apple-mobile-web-app-capable" in body
        assert "reauth" not in body and "re-authorise" not in body   # account controls live elsewhere

    def test_a_side_starts_at_the_delta_target_and_a_blank_box_means_spot(self, order_page):
        """The δ box starts at 0.80 (Steve, 2026-09-15): the .78 row is chosen.
        A blank box — the field present and empty — means nearest to spot."""
        body = text(order_page.get("/exec/order?side=call"))
        assert "tap a strike" in body and "value='0.8'" in body
        chosen = body.split("<tr class='chosen'>")[1].split("</tr>")[0]
        assert ">6350<" in chosen
        assert "cut if SPX" in body and "stop rests at" in body and "take-profit rests at" in body
        assert ">SEND<" in body and "PREVIEW" not in body and "name=nonce value='" in body
        body = text(order_page.get("/exec/order?side=call&delta="))
        assert ">6380<" in body.split("<tr class='chosen'>")[1].split("</tr>")[0]

    def test_delta_override_and_a_tapped_strike(self, order_page):
        body = text(order_page.get("/exec/order?side=call&delta=0.30"))
        assert ">6400<" in body.split("<tr class='chosen'>")[1].split("</tr>")[0]
        body = text(order_page.get("/exec/order?side=put&strike=6300"))
        assert ">6300<" in body.split("<tr class='chosen'>")[1].split("</tr>")[0]

    def test_price_and_state_json(self, order_page):
        j = order_page.get("/exec/order/price?side=call&delta=0.3").json
        assert j["contract"]["symbol"] == CALL and j["limit"] == 2.10
        assert j["stop_spx"] and j["stop_price"] and "fd0_html" in j and "strikes_html" in j
        s = order_page.get(f"/exec/order/state?symbol={CALL}").json
        assert s["quote"]["ask"] == 2.10 and s["spx"] == SPX_NOW
        assert s["arming"]["state"] == "ARMED" and "position_html" in s and "bid 2.00" in s["quote_html"]

    def test_send_walks_the_whole_ticket_in_one_tap(self, order_page, armed, chain):
        """SEND is the ticket's one action (st-igw0): the page carries a
        single-use token, the send prices the selection at that moment and
        places it, and the service runs the broker's own preview inside."""
        page = text(order_page.get("/exec/order?side=call&delta=0.3"))
        assert ">SEND<" in page and "PREVIEW" not in page and "action='/exec/order/send'" in page
        nonce = page.split("name=nonce value='")[1].split("'")[0]
        assert not any(c[0] == "place" for c in chain.calls)

        r = order_page.post("/exec/order/send", data={"side": "call", "delta": "0.3", "nonce": nonce})
        assert r.status_code == 303
        landing = text(order_page.get(r.headers["Location"]))
        assert "SENT AND FILLED" in landing and "Protective stop resting" in landing
        st = armed.status()
        assert st["positions"][0]["symbol"] == CALL and st["positions"][0]["stop_order_id"]
        assert st["positions"][0]["target_order_id"]                  # the bracket (st-fn5y)
        assert "Take-profit resting" in landing
        # entry + the bracket: stop and take-profit
        assert [c[0] for c in chain.calls if c[0] == "place"] == ["place", "place", "place"]
        ids = {e.get("intent_id") for e in armed.journal.read() if e.get("intent_id")}
        page_ids = [i for i in ids if str(i).startswith("page-")]
        assert len(page_ids) == 1 and page_ids[0].endswith("-" + nonce[:6])
        events = [e["event"] for e in armed.journal.find(page_ids[0])]
        # the broker's own preview runs inside the place — no page step for it
        assert events[:2] == ["request", "preview"] and "placed" in events and "filled" in events
        assert armed.journal.find(page_ids[0])[0]["kind"] == "place"
        assert armed.journal.find(page_ids[0])[0]["intent"]["source"] == "page"
        # the same token again is a replay: answered with what happened, never sent twice
        r = order_page.post("/exec/order/send", data={"side": "call", "delta": "0.3", "nonce": nonce})
        again = text(order_page.get(r.headers["Location"]))
        assert "SENT AND FILLED" in again
        assert [c[0] for c in chain.calls if c[0] == "place"] == ["place", "place", "place"]
        # the position, its money and the bracket editor are on the page now
        assert "FILLED" in landing and "NET NOW" in landing and "C6400 × 1" in landing
        assert "value='21.00'" in landing and ">SET<" in landing
        assert "name=stop inputmode" in landing and "name=target inputmode" in landing

    def test_a_send_answered_in_place_paints_the_card_and_re_arms_the_button(self, order_page, armed, chain):
        page = text(order_page.get("/exec/order?side=call&delta=0.3"))
        assert "<div id=panel hidden " in page and "<div id=answer></div>" in page
        nonce = page.split("name=nonce value='")[1].split("'")[0]
        r = order_page.post("/exec/order/send", data={"side": "call", "delta": "0.3", "nonce": nonce, "ajax": "1"})
        assert r.status_code == 200
        j = r.json
        assert j["ok"] is True and "SENT AND FILLED" in j["msg"] and j["bad"] is None
        assert j["panel_stage"] == "filled" and "NET NOW" in j["panel_body_html"]
        assert j["send_nonce"] and j["send_nonce"] != nonce and j["replayed"] is False
        assert j["quote"]["ask"] == 2.10                                # the chosen contract's quote rides along
        # the script: fetch on the send form, paint, unhide, re-arm
        assert "classList.contains('sendform')" in page and "pn.hidden = false" in page
        assert "n.value = j.send_nonce" in page and "SENDING…" in page

    def test_an_unknown_token_is_refused_and_a_spent_one_replays(self, order_page, armed, chain):
        r = order_page.post("/exec/order/send", data={"side": "call", "delta": "0.3", "nonce": "bogus", "ajax": "1"})
        j = r.json
        assert j["ok"] is False and "reload the page" in j["bad"] and not any(c[0] == "place" for c in chain.calls)

    def test_a_stale_send_token_refuses(self, order_page, mono, chain):
        from execd.orderform import SEND_NONCE_TTL_S
        body = text(order_page.get("/exec/order?side=call&delta=0.3"))
        nonce = body.split("name=nonce value='")[1].split("'")[0]
        mono.t += SEND_NONCE_TTL_S + 1
        r = order_page.post("/exec/order/send", data={"side": "call", "delta": "0.3", "nonce": nonce})
        assert "older than" in text(order_page.get(r.headers["Location"]))
        assert not any(c[0] == "place" for c in chain.calls)

    def test_a_refused_send_says_so(self, order_page, armed, chain):
        armed.stop()
        r = page_send(order_page, {"side": "call", "delta": "0.3"})
        body = text(order_page.get(r.headers["Location"]))
        assert "Refused (" in body and "Nothing sent" in body and "data-stage=refused" in body
        assert not any(c[0] == "place" for c in chain.calls)

    def test_locked_shows_the_strikes_but_no_flatten_and_refuses_a_send(self, service, chain, clock, mono, tmp_path):
        vault = Vault(tmp_path / "vault.json")
        vault.store(vault_payload(), PASS)
        mfile = tmp_path / "market.json"
        mfile.write_text(json.dumps(market_payload()))
        market = CredentialFile(mfile)
        market.load()
        app = create_page(service, vault=vault, market=market, callback_url=CALLBACK,
                          clock=clock, monotonic=mono)
        app.config["TESTING"] = True
        c = same_origin(app.test_client())
        body = text(c.get("/exec/order?side=put"))
        assert "6400" in body and ">LOCKED<" in body and "FLATTEN" not in body
        assert "href='/exec/account'" in body
        r = page_send(c, {"side": "put"})
        assert "Refused (" in text(c.get(r.headers["Location"]))

    def test_paper_mode_is_the_badge_and_the_send_fills_in_the_book(self, service, chain, clock, mono, tmp_path):
        from execd.service import ServiceConfig
        from execd.paper import PaperBroker
        paper = PaperBroker(chain, clock=clock)
        svc = ExecService(paper, ServiceConfig(state_dir=tmp_path / "p", sha="t", mode="paper"), clock=clock)
        svc.unlock({"token": "x"})
        vault = Vault(tmp_path / "vault.json")
        vault.store(vault_payload(), PASS)
        app = create_page(svc, vault=vault, market=None, callback_url=CALLBACK, clock=clock, monotonic=mono)
        app.config["TESTING"] = True
        c = same_origin(app.test_client())
        r = page_send(c, {"side": "call", "delta": "0.3"})
        body = text(c.get(r.headers["Location"]))
        # the badge is the word; no "(simulated)" prefix (Steve, 2026-09-15, st-2hei)
        assert "SENT AND FILLED" in body and "<span class='badge paper'>PAPER</span>" in body
        assert "simulated" not in body and svc.status()["positions"][0]["symbol"] == CALL

    def test_embed_has_no_shell(self, order_page):
        body = text(order_page.get("/exec/order?side=call&embed=1"))
        assert "<h1>" not in body and "tailnet only" not in body and "class=embed" in body
        assert "cut if SPX" in body

    def test_every_form_and_link_stays_under_exec(self, order_page):
        body = text(order_page.get("/exec/order?side=call&delta=0.3"))
        actions = [a.split("'")[0] for a in body.split("action='")[1:]]
        hrefs = [a.split("'")[0] for a in body.split("href='")[1:]]
        assert actions and all(a.startswith("/exec/") for a in actions), actions
        assert hrefs and all(h.startswith("/exec/") for h in hrefs), hrefs

    def test_no_secret_on_the_order_page_or_in_its_json(self, order_page):
        for body in (text(order_page.get("/exec/order?side=call")),
                     text(order_page.get("/exec/order/price?side=call")),
                     text(order_page.get(f"/exec/order/state?symbol={CALL}"))):
            assert PASS not in body and "refresh-old" not in body and "acc" not in body.split("access")[0][-3:]


class TestThePadlockAndRePrice:
    """Steve, 2026-09-15: "the re-price button should simply reprice existing
    strike. not force a new preview. the alternative is to leave the price
    watcher live but give a control to lock price at current allowing a
    submission at that price. this is how TOS platform works. a padlock icon
    toggled between locked and unlocked." [st-2s4u]"""

    def test_a_lock_is_parsed_and_re_price_drops_it(self):
        s = Selection.from_args({"side": "call", "strike": "6400", "limit": "2.00"}, today=DAY)
        assert s.limit == 2.00 and s.locked and s.as_query()["limit"] == "2.00"
        s = Selection.from_args({"side": "call", "strike": "6400", "limit": "2.00", "reprice": "1"}, today=DAY)
        assert s.limit is None and not s.locked and "limit" not in s.as_query()
        assert Selection.from_args({"limit": "x"}, today=DAY).limit is None
        assert Selection.from_args({"limit": "-1"}, today=DAY).limit is None
        assert Selection(side="call", limit=2.0).as_query(limit=None).get("limit") is None

    def test_a_locked_price_is_the_limit_and_the_stop_derives_from_it(self, armed, chain):
        live = price(armed, Selection(side="call", expiry=DAY, strike=6400))
        locked = price(armed, Selection(side="call", expiry=DAY, strike=6400, limit=2.00))
        assert live.limit == 2.10 and locked.limit == 2.00
        assert locked.contract.symbol == live.contract.symbol
        assert locked.cost_usd == 200.0 and locked.stop_price != live.stop_price
        assert intent_for(locked, intent_id="page-x", engine_sha="t")["limit"] == 2.00

    def test_re_price_keeps_the_tapped_strike(self, order_page):
        body = text(order_page.get("/exec/order?side=put&strike=6300"))
        form = body.split("<form id=sel")[1].split("</form>")[0]
        assert "name=strike value='6300'" in form and "name=reprice value=1>RE-PRICE" in form
        assert "name=limit value=''" in form
        # what the RE-PRICE button submits: the strike stays, the box is blank
        body = text(order_page.get("/exec/order?side=put&expiry=2026-08-26&strike=6300&delta=&limit=&reprice=1"))
        assert ">6300<" in body.split("<tr class='chosen'>")[1].split("</tr>")[0]

    def test_the_ticket_says_when_it_was_priced(self, order_page):
        """Beside the price, the time the ask was read — 'priced HH:MM:SS' in
        Chicago time, from the service's clock (st-sk9r, audit note 37); the
        poll's script rewrites it from the quote's as_of while following."""
        body = text(order_page.get("/exec/order?side=call&strike=6400"))
        head = body.split("<div class=trow>")[1].split("</div></div>")[0]
        assert "<span id=priced class=k>priced 10:00:00</span>" in head   # MIDSESSION, 15:00 UTC
        # the poll never rewrites the head alone: a moved ask reprices the whole ticket (st-hzr6)
        assert "window.__lastReprice" in body and "px.textContent" not in body

    def test_the_ticket_is_in_plain_words(self, order_page):
        """Steve, 2026-09-17: 'priced at 60 but max loss is 50? reference to
        spread? noise?' — every row says what the number is."""
        body = text(order_page.get("/exec/order?side=call&strike=6400"))
        for phrase in ("to buy it", "the most this attempt may lose", "is the bid-ask gap and",
                       "is left for the move against you", "where the cut goes",
                       "wobble allowance", "bid / ask", "if it fills there",
                       "cut if SPX falls to", "below spot)"):
            assert phrase in body, phrase
        for gone in ("most this costs", "less friction", "tape noise", "Noise floor",
                     "in premium", "NOISE FLOOR"):
            assert gone not in body, gone
        # the boxes are drawn as boxes and the stop box says what it takes
        assert "border:2px solid #9ca3af" in body and "stop: strike or price</span><input id=stopbox" in body
        # the padlock answers the tap and a second tap inside half a second is the same tap
        assert "window.__lockTap" in body and "b.classList.toggle('on', !!lf.value)" in body

    def test_the_padlock_on_the_ticket(self, order_page):
        body = text(order_page.get("/exec/order?side=call&strike=6400"))
        assert "id=lock class='lock'" in body and "&#128275;" in body and "data-limit='2.10'" in body
        assert "<span id=px>2.10</span>" in body and "id=cost>$210.00" in body
        assert "<span id=live class=k></span>" in body
        locked = text(order_page.get("/exec/order?side=call&strike=6400&limit=2.00"))
        assert "id=lock class='lock on'" in locked and "&#128274;" in locked
        assert "<span id=px>2.00</span>" in locked and "id=cost>$200.00" in locked
        assert "ask 2.10 now" in locked
        # SEND carries the lock; the RE-PRICE form holds it for the script to flip
        assert "name='limit' value='2.00'" in locked.split("id=sendfields")[1].split("</span>")[0]
        assert "name=limit value='2.00'" in locked.split("<form id=sel")[1].split("</form>")[0]
        # a strike, an expiry or a side is a new price: the lock does not travel
        hrefs = [h.split("'")[0] for h in locked.split("href='")[1:]]
        assert not any("limit=" in h for h in hrefs), hrefs

    def test_send_sends_the_locked_price(self, order_page, armed, chain):
        r = page_send(order_page, {"side": "call", "strike": "6400", "limit": "2.00"})
        landing = text(order_page.get(r.headers["Location"]))
        assert "1 at 2.00 ($200.00)" in landing
        req = [e for e in armed.journal.read() if e.get("event") == "request" and e.get("kind") == "place"][-1]
        assert req["intent"]["limit"] == 2.00
        assert armed.status()["positions"][0]["entry_price"] == 2.00

    def test_the_state_poll_carries_the_live_limit_and_its_cost(self, order_page):
        s = order_page.get(f"/exec/order/state?symbol={CALL}&lots=1").json
        assert s["limit_now"] == 2.10 and s["cost_now"] == "$210.00"
        s = order_page.get("/exec/order/state").json
        assert s["limit_now"] is None and s["cost_now"] is None

    def test_the_fresh_page_still_ticks_without_a_stage_card(self, order_page):
        body = text(order_page.get("/exec/order?side=call"))
        assert "<div id=panel hidden " in body.split("<script>")[0]   # on the page, hidden, until a stage arrives (st-igw0)
        assert "getElementById('panel') || document.body" in body and "window.__onQuote" in body


class TestLockedInPlaceAndFewerWords:
    """Steve, 2026-09-15: "if panel is locked the Passphrase should be
    displayed. way too many words in execd screen, static clock, no need to
    define PAPER. Still don't need 'GRANTS' section. Still looking for
    Options Buying Power amt." [st-2hei]"""

    def _locked_client(self, service, clock, mono, tmp_path):
        vault = Vault(tmp_path / "vault.json")
        vault.store(vault_payload(), PASS)
        mfile = tmp_path / "market.json"
        mfile.write_text(json.dumps(market_payload()))
        market = CredentialFile(mfile)
        market.load()
        app = create_page(service, vault=vault, market=market, callback_url=CALLBACK,
                          clock=clock, monotonic=mono)
        app.config["TESTING"] = True
        return same_origin(app.test_client())

    def test_a_locked_trading_page_unlocks_in_place(self, service, chain, clock, mono, tmp_path):
        c = self._locked_client(service, clock, mono, tmp_path)
        body = text(c.get("/exec/order"))
        strip_end = body.index("</div></div>", body.index("class=strip")) + len("</div></div>")
        after = body[strip_end:strip_end + 400]
        assert "action='/exec/unlock'" in after and "name=back value='order'" in after
        assert "name=passphrase" in after and ">UNLOCK<" in after
        assert "account page" not in body and "account:" not in body and "unlock on" not in body
        r = c.post("/exec/unlock", data={"passphrase": PASS, "back": "order"})
        assert r.status_code == 303 and r.headers["Location"].startswith("/exec/order")
        landing = text(c.get(r.headers["Location"]))
        assert "Armed until" in landing and "action='/exec/unlock'" not in landing

    def test_the_money_sits_under_the_strip_when_armed(self, order_page, armed, chain):
        armed._balances_cache = (armed.clock(), {"available_funds": 1234.5,
                                                 "option_buying_power": 2345.0})
        body = text(order_page.get("/exec/order?side=call"))
        money = body.index("class=money id=balances")
        assert body.index("class=strip") < money < body.index("class=side")
        assert "option buying power <b>$2,345.00</b>" in body and "available $1,234.50" in body
        assert "class=foot id=balances" not in body

    def test_a_near_or_past_wall_is_one_red_line_on_the_trading_page(self, order_page, armed):
        """The grants card is gone; the wall it showed is the live feed's
        failure point, so it survives as one line, only when it matters."""
        from execd.orderpage import wall_alert_html
        now = armed.clock()
        far = {"credential": {"armed": True, "refresh_wall": (now + dt.timedelta(days=5)).isoformat()}}
        near = {"credential": {"armed": True, "refresh_wall": (now + dt.timedelta(days=1)).isoformat()}}
        past = {"credential": {"armed": False, "last_known_trading_wall": (now - dt.timedelta(days=1)).isoformat()}}
        assert wall_alert_html(far, now) == ""
        assert "hours left" in wall_alert_html(near, now) and "class=bad" in wall_alert_html(near, now)
        assert "PAST THE WALL" in wall_alert_html(past, now)
        assert wall_alert_html({"credential": None}, now) == ""

    def test_the_account_page_has_no_definitions_and_no_grants(self, order_page):
        body = text(order_page.get("/exec/account"))
        for words in ("grants", "simulated", "orders reach Schwab", "enter the passphrase",
                      "tailnet only", "vault present", "blocks new positions",
                      "asks once more", "forget the credential", "do both in one sitting"):
            assert words not in body, words
        assert "<span class='badge live'>LIVE</span>" in body and ">STOP<" in body
        assert "re-authorise (weekly)" in body and ">Today<" in body


class TestAStageChangeAlwaysPaints:
    """Steve, 2026-09-15 13:21 CT: "the stop was hit immediately but the
    message panel didn't display it." The service log shows the poll fetching
    the CLOSED card every 3 s; the page kept the FILLED editor because a
    bracket input had focus. [st-f3y3]"""

    def test_the_poll_returns_closed_on_the_first_tick_after_a_stop_fill(self, order_page, armed, chain, clock):
        r = page_send(order_page, {"side": "call", "delta": "0.3"})
        page = text(order_page.get(r.headers["Location"]))
        assert "data-stage=filled" in page and "class=msg" in page
        p = armed.status()["positions"][0]
        clock.advance(seconds=31)
        chain.fill_resting(p["stop_order_id"])
        armed.poll_fills()
        s = order_page.get(f"/exec/order/state?symbol={p['symbol']}&lots=1").json
        assert s["panel_stage"] == "closed" and "P&amp;L" in s["panel_body_html"]
        assert "-$35.00" in s["panel_body_html"] and "protective-stop" in s["panel_body_html"]

    def test_the_script_paints_a_stage_change_over_a_focused_input_and_drops_the_stale_message(self, order_page):
        body = text(order_page.get("/exec/order?side=call"))
        script = body.split("var STATE = ")[1]
        # the guard holds only for a dirty input, and never across a stage change
        assert "a.value !== a.defaultValue" in script
        assert "(changed || !editing())" in script
        assert "document.querySelector('.msg')" in script and "removeChild(m)" in script
        # a failed poll is said, not swallowed
        assert "poll failed" in script and "throw new Error('HTTP '" in script


class TestARefusedSendIsShown:
    """2026-09-15 09:54 CT: Steve tapped SEND and saw nothing —
    Schwab's own preview had refused the order (buying power) and the page
    swallowed it. A refused send must land as the red box AND the REFUSED
    stage, and the journal must be one tap away on the trading page."""

    def test_a_refused_send_lands_red_with_the_refused_stage_and_the_journal(
            self, order_page, armed, chain):
        from execd.broker import Preview
        real = chain.preview

        def rejecting(intent):
            p = real(intent)
            return Preview(symbol=p.symbol, side=p.side, qty=p.qty, order_type=p.order_type,
                           price=p.price, cost_usd=p.cost_usd, commission_usd=p.commission_usd,
                           accepted=False,
                           messages=("reject: You do not have enough available cash/buying "
                                     "power for this order.",))
        chain.preview = rejecting
        r = page_send(order_page, {"side": "call", "delta": "0.3"})
        assert r.status_code == 303 and "bad=" in r.headers["Location"], r.headers["Location"]
        landing = text(order_page.get(r.headers["Location"]))
        assert "<div class=bad>" in landing or "data-stage=refused" in landing
        assert "buying" in landing and "Nothing sent" in landing
        assert "data-stage=refused" in landing
        assert not any(c[0] == "place" for c in chain.calls)
        # the journal is on the trading page, latest first, behind one tap
        assert "<details id=journalbox" in landing and "refused" in landing.split("id=journalbox")[1]
        j = order_page.get(f"/exec/order/state?symbol={CALL}").json
        assert "journal_html" in j and "refused" in j["journal_html"]

    def test_a_recent_refusal_renders_from_the_journal_even_with_no_message(
            self, order_page, armed, chain, clock):
        """The redirect's query can be lost on the way (it was, 09:54 CT).
        The page reads its own record: a refusal that is the latest thing the
        service did, and recent, IS the REFUSED stage."""
        from execd.broker import Preview
        real = chain.preview
        chain.preview = lambda intent: Preview(symbol=intent.symbol, side=intent.side, qty=intent.qty,
                                               order_type=intent.order_type, price=2.10, cost_usd=210.0,
                                               commission_usd=0.65, accepted=False,
                                               messages=("reject: not enough buying power",))
        page_send(order_page, {"side": "call", "delta": "0.3"})   # refused by the broker's preview
        chain.preview = real
        assert armed.journal.tail(1)[-1]["event"] == "refused"
        plain = text(order_page.get("/exec/order"))          # no msg, no bad on the query
        assert "data-stage=refused" in plain and "buying power" in plain
        clock.advance(minutes=11)
        later = text(order_page.get("/exec/order"))
        assert "data-stage=refused" not in later               # an old refusal is history


class TestAStopOfHisOwn:
    """Steve, 2026-09-17: "permit me to input a stop loss strike price in
    addition to the existing hard-coded dollar amount. just add an input on
    the SEND screen pre-populated with the dollar amount. over-riding that
    follows the same rule as updating - absent a decimal point means a
    strike price." The conftest chain: the 6400 call at 2.00/2.10, δ 0.30,
    SPX 6380. [st-m3bl]"""

    def test_the_selection_carries_the_text_as_typed_and_drops_it_with_the_contract(self):
        s = Selection.from_args({"side": "call", "strike": "6400", "stop": " 6376 "}, today=DAY)
        assert s.stop == "6376" and s.as_query()["stop"] == "6376"
        assert "stop" not in s.as_query(stop=None)
        s = Selection.from_args({"side": "call", "strike": "6400", "stop": "1.50", "reprice": "1"}, today=DAY)
        assert s.stop == "1.50"                                    # RE-PRICE keeps his stop
        assert Selection.from_args({"side": "call", "stop": ""}, today=DAY).stop is None

    def test_a_price_is_the_resting_stop_and_its_level_is_walked_back(self, armed, chain):
        base = price(armed, Selection(side="call", expiry=DAY, strike=6400))
        p = price(armed, Selection(side="call", expiry=DAY, strike=6400, stop="1.50"))
        assert p.error is None and p.stop_set_by == "price"
        assert p.stop_price == 1.50 and p.ticket.stop_trigger_spx == 6378.0    # (2.10 − 1.50)/0.30 = 2 pts
        assert p.stop_price != base.stop_price
        d = p.ticket.derivation
        assert d.stop_premium_pts == 0.60 and d.attempt_risk_usd == 60.0 and d.stop_distance_spx == 2.0
        assert p.net_at_stop_usd == pytest.approx(-60.0 - 1.30)
        assert p.ticket.template_fields != base.ticket.template_fields
        i = intent_for(p, intent_id="page-x", engine_sha="t")
        assert i["stop_spx"] == 6378.0 and i["limit"] == 2.10
        assert p.to_dict()["stop_set_by"] == "price" and p.to_dict()["stop_text"] == "1.50"

    def test_a_level_is_the_trigger_and_its_price_is_walked_forward(self, armed, chain):
        p = price(armed, Selection(side="call", expiry=DAY, strike=6400, stop="6376"))
        assert p.error is None and p.stop_set_by == "spx"
        assert p.ticket.stop_trigger_spx == 6376.0 and p.stop_price == 0.90   # 2.10 − 4 × 0.30
        assert p.ticket.derivation.stop_distance_spx == 4.0
        assert intent_for(p, intent_id="page-x", engine_sha="t")["stop_spx"] == 6376.0
        assert any(w.startswith("YOUR STOP RISKS $120.00") for w in p.ticket.warnings)

    def test_a_put_level_sits_above_the_market(self, armed, chain):
        p = price(armed, Selection(side="put", expiry=DAY, strike=6300, stop="6384"))
        assert p.error is None and p.ticket.stop_trigger_spx == 6384.0
        assert p.stop_price == round(p.limit - 4 * p.contract.abs_delta, 2) or p.stop_price > 0

    def test_a_stop_inside_the_noise_floor_is_warned_not_refused(self, armed, chain):
        p = price(armed, Selection(side="call", expiry=DAY, strike=6400, stop="2.05"))
        assert p.error is None and p.stop_price == 2.05
        assert any(w.startswith("STOP INSIDE THE NOISE FLOOR") for w in p.ticket.warnings)
        assert sum(1 for w in p.ticket.warnings if w.startswith("STOP INSIDE")) == 1

    @pytest.mark.parametrize("raw, words", [
        ("1.83", "not on the 0.05 grid"),
        ("2.10", "not below the 2.10 limit"),
        ("2.50", "not below the 2.10 limit"),
        ("0.00", "must be positive"),
        ("6385", "a call's stop sits below the market, and SPX 6385 is not below the 6380.00 mark"),
        ("abc", "must be a number"),
        ("1e-1", "not a whole SPX level"),
    ])
    def test_a_stop_that_cannot_be_one_is_words_on_the_ticket_and_no_send(self, armed, chain, raw, words):
        p = price(armed, Selection(side="call", expiry=DAY, strike=6400, stop=raw))
        assert p.error and p.error.startswith("your stop:") and words in p.error
        assert p.contract is not None                     # the ticket still shows the contract
        with pytest.raises(ValueError, match="your stop"):
            intent_for(p, intent_id="page-x", engine_sha="t")

    def test_a_level_past_zero_rests_one_tick_and_says_so(self, armed, chain):
        p = price(armed, Selection(side="call", expiry=DAY, strike=6400, stop="6370"))
        assert p.error is None and p.stop_price == 0.05 and p.ticket.stop_trigger_spx == 6370.0
        assert any(w.startswith("SPX 6370 WALKS THE OPTION BELOW ZERO") for w in p.ticket.warnings)

    def test_the_box_is_on_the_page_pre_filled_with_the_derived_stop(self, order_page, armed, chain):
        base = price(armed, Selection(side="call", expiry=DAY, strike=6400))
        body = text(order_page.get("/exec/order?side=call&strike=6400"))
        form = body.split("<form id=sel")[1].split("</form>")[0]
        assert f"id=stopbox inputmode=decimal enterkeyhint=done autocomplete=off value='{base.stop_price:.2f}' data-derived='{base.stop_price:.2f}'" in form
        assert "name=stop value=''" in form
        assert "makes it a price (8.30); none makes it an SPX level (7610)" in form
        assert "your price" not in body and "your level" not in body
        assert "function stopField()" in body and "window.__followStop = function(j)" in body
        assert "fd.set('stop', sf.elements['stop'].value || '')" in body

    def test_his_stop_rides_the_form_the_ticket_and_no_link(self, order_page):
        body = text(order_page.get("/exec/order?side=call&strike=6400&stop=1.50"))
        form = body.split("<form id=sel")[1].split("</form>")[0]
        assert "name=stop value='1.50'" in form and "id=stopbox" in form and "value='1.50' data-derived=" in form
        assert "cut if SPX falls to <b>6378.00</b>" in body and "stop rests at <b>1.50</b>" in body
        assert "id=ownstop>· your price</span>" in body
        assert "name='stop' value='1.50'" in body.split("id=sendfields")[1].split("</span>")[0]
        hrefs = [h.split("'")[0] for h in body.split("href='")[1:]]
        assert not any("stop=" in h for h in hrefs), hrefs
        level = text(order_page.get("/exec/order?side=call&strike=6400&stop=6376"))
        assert "id=ownstop>· your level</span>" in level and "stop rests at <b>0.90</b>" in level
        assert "YOUR STOP RISKS $120.00" in level

    def test_the_price_json_carries_the_stop_for_the_box_to_follow(self, order_page):
        j = order_page.get("/exec/order/price?side=call&strike=6400").json
        assert j["stop_set_by"] is None and j["stop_text"] is None and j["stop_price"]
        j = order_page.get("/exec/order/price?side=call&strike=6400&stop=6376").json
        assert j["stop_set_by"] == "spx" and j["stop_price"] == 0.90 and j["stop_spx"] == 6376.0
        assert "name='stop' value='6376'" in j["send_fields_html"]

    def test_send_rests_his_price_and_watches_its_level(self, order_page, armed, chain):
        r = page_send(order_page, {"side": "call", "strike": "6400", "stop": "1.50"})
        landing = text(order_page.get(r.headers["Location"]))
        assert "Not sent" not in landing and "Refused" not in landing
        p = armed.status()["positions"][0]
        assert p["stop_price"] == 1.50 and p["stop_spx"] == 6378.0
        req = [e for e in armed.journal.read() if e.get("event") == "request" and e.get("kind") == "place"][-1]
        assert req["intent"]["stop_spx"] == 6378.0
        assert armed.journal.events("sending")[-1]["page_query"]["stop"] == "1.50"

    def test_send_rests_the_walked_price_for_his_level(self, order_page, armed, chain):
        page_send(order_page, {"side": "call", "strike": "6400", "stop": "6376"})
        p = armed.status()["positions"][0]
        assert p["stop_spx"] == 6376.0 and p["stop_price"] == 0.90
        assert armed.observe(SPX_NOW - 3.9)["fired"] == []
        assert armed.observe(SPX_NOW - 4.0)["fired"][0]["closed"] is True

    def test_a_bad_stop_is_not_sent(self, order_page, armed, chain):
        r = page_send(order_page, {"side": "call", "strike": "6400", "stop": "6385"})
        assert r.status_code == 303 and "bad=Not+sent:+your+stop" in r.headers["Location"]
        assert armed.status()["positions"] == [] and armed.status()["working"] == []
