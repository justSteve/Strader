"""The order form — by code alone. [st-k6gl]

The choice rules (nearest to spot, a delta override, a tapped strike), the
priced ticket (the engine's derivation, the service's tick grid, the resting
stop), and the page: side → strikes → FD0 → preview → send, over the real
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

from .conftest import CALL, PUT, SPX_NOW, Clock, schwab_chain_maps
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
    return app.test_client()


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
        assert "<h1>order</h1>" in body and "apple-mobile-web-app-capable" in body

    def test_a_side_shows_the_strikes_with_the_nearest_chosen(self, order_page):
        body = text(order_page.get("/exec/order?side=call"))
        assert "tap a strike" in body and "6380" in body
        chosen = body.split("<tr class='chosen'>")[1].split("</tr>")[0]
        assert ">6380<" in chosen
        assert "cut if SPX reaches" in body and "resting stop the service places" in body
        assert "PREVIEW" in body and "SEND" not in body

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

    def test_preview_then_send_walks_the_whole_ticket(self, order_page, armed, chain):
        r = order_page.post("/exec/order/preview", data={"side": "call", "delta": "0.3"})
        body = text(r)
        assert r.status_code == 200
        assert "Preview from Schwab" in body and "total $210.65" in body and "accepts it" in body
        assert ">SEND<" in body and "PREVIEWED" in body
        nonce = body.split("name=nonce value='")[1].split("'")[0]
        assert not any(c[0] == "place" for c in chain.calls)

        r = order_page.post("/exec/order/send", data={"nonce": nonce})
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
        assert len(page_ids) == 1
        events = [e["event"] for e in armed.journal.find(page_ids[0])]
        assert events[:2] == ["request", "preview"] and "placed" in events and "filled" in events
        assert armed.journal.find(page_ids[0])[0]["intent"]["source"] == "page"
        # the same nonce is dead
        r = order_page.post("/exec/order/send", data={"nonce": nonce})
        assert "used already" in text(order_page.get(r.headers["Location"]))
        assert [c[0] for c in chain.calls if c[0] == "place"] == ["place", "place", "place"]
        # the position, its money and the bracket editor are on the page now
        assert "FILLED" in landing and "NET NOW" in landing and "C6400 × 1" in landing
        assert "value='21.00'" in landing and ">UPDATE<" in landing
        assert "name=stop_price" in landing and "name=target_price" in landing

    def test_a_stale_send_token_refuses(self, order_page, mono):
        from execd.orderform import PREVIEW_TTL_S
        body = text(order_page.post("/exec/order/preview", data={"side": "call", "delta": "0.3"}))
        nonce = body.split("name=nonce value='")[1].split("'")[0]
        mono.t += PREVIEW_TTL_S + 1
        r = order_page.post("/exec/order/send", data={"nonce": nonce})
        assert "older than" in text(order_page.get(r.headers["Location"]))

    def test_a_refused_preview_says_so_and_offers_no_send(self, order_page, armed):
        armed.stop()
        body = text(order_page.post("/exec/order/preview", data={"side": "call", "delta": "0.3"}))
        assert "Refused (" in body and "Nothing sent" in body and ">SEND<" not in body

    def test_locked_shows_the_strikes_but_no_flatten_and_refuses_a_preview(self, service, chain, clock, mono, tmp_path):
        vault = Vault(tmp_path / "vault.json")
        vault.store(vault_payload(), PASS)
        mfile = tmp_path / "market.json"
        mfile.write_text(json.dumps(market_payload()))
        market = CredentialFile(mfile)
        market.load()
        app = create_page(service, vault=vault, market=market, callback_url=CALLBACK,
                          clock=clock, monotonic=mono)
        app.config["TESTING"] = True
        c = app.test_client()
        body = text(c.get("/exec/order?side=put"))
        assert "6380" in body and "locked — unlock" in body and "FLATTEN" not in body
        body = text(c.post("/exec/order/preview", data={"side": "put"}))
        assert "Refused (" in body

    def test_paper_mode_prefixes_the_preview(self, service, chain, clock, mono, tmp_path):
        from execd.service import ServiceConfig
        from execd.paper import PaperBroker
        paper = PaperBroker(chain, clock=clock)
        svc = ExecService(paper, ServiceConfig(state_dir=tmp_path / "p", sha="t", mode="paper"), clock=clock)
        svc.unlock({"token": "x"})
        vault = Vault(tmp_path / "vault.json")
        vault.store(vault_payload(), PASS)
        app = create_page(svc, vault=vault, market=None, callback_url=CALLBACK, clock=clock, monotonic=mono)
        app.config["TESTING"] = True
        c = app.test_client()
        body = text(c.post("/exec/order/preview", data={"side": "call", "delta": "0.3"}))
        assert "PAPER (simulated) — Preview from Schwab" in body and "<span class='badge paper'>PAPER</span>" in body

    def test_embed_has_no_shell(self, order_page):
        body = text(order_page.get("/exec/order?side=call&embed=1"))
        assert "<h1>" not in body and "tailnet only" not in body and "class=embed" in body
        assert "cut if SPX reaches" in body

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
