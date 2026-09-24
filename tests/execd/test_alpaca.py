"""The Alpaca transport, against a fake Alpaca. [co-8mb1z]

No socket is opened: ``httpx.MockTransport`` hands every request to
:class:`FakeAlpaca`, which answers in the shapes of Alpaca's API reference
(spec-derived — nothing here was recorded against Alpaca). What is asserted:

- the venue is the mode, and a key for one venue never reaches the other;
- a send is never retried, and a 403/422 is the broker's rejection, not an
  exception;
- the service's padded OCC and Alpaca's unpadded symbol convert both ways;
- a cancel is re-read until terminal, as on Schwab;
- positions outside the bounds' roots are counted, not shown;
- market data comes from the delegate when there is one (Alpaca publishes no
  index data), and an index quote without one is refused by name;
- the whole service runs over it: unlock, an SPX entry through every bound,
  the protective stop rested at Alpaca;
- ``python -m execd`` refuses the combinations it must, and the page's
  UNLOCK arms the Alpaca keys without ever swapping a Schwab grant over them;
- no key or secret appears in any error message.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from execd.alpaca import (AlpacaBroker, AlpacaCredential, alpaca_payload, asset_class,
                          build_order, from_alpaca_symbol, to_alpaca_symbol)
from execd.arming import ArmState, Locked
from execd.broker import BrokerError, MockBroker, OrderStatus
from execd.intent import OrderIntent, OrderType, Side
from execd.service import ExecService, ServiceConfig

from .conftest import CALL, MIDSESSION, SPX_NOW, Clock, entry

KEY = "PKTESTKEYID0000000"
SECRET = "test-secret-value-000000000000"
LIVE_KEY = "AKLIVEKEYID0000000"
ALPACA_CALL = "SPXW260826C06400000"


def paper_payload() -> dict[str, str]:
    return {"venue": "paper", "key_id": KEY, "secret_key": SECRET}


def order_body(oid: str = "ord-1", *, status: str = "new", symbol: str = ALPACA_CALL,
               side: str = "buy", qty: str = "1", type_: str = "limit",
               limit: str | None = "2.10", stop: str | None = None,
               filled_qty: str = "0", filled_avg: str | None = None) -> dict[str, Any]:
    return {"id": oid, "client_order_id": "x", "status": status, "symbol": symbol,
            "asset_class": "us_option", "side": side, "qty": qty, "type": type_,
            "order_type": type_, "limit_price": limit, "stop_price": stop,
            "filled_qty": filled_qty, "filled_avg_price": filled_avg,
            "position_intent": "buy_to_open" if side == "buy" else "sell_to_close",
            "submitted_at": "2026-08-26T15:00:00.123456789Z", "order_class": "", "legs": None}


class FakeAlpaca:
    """Alpaca's trading and data hosts, by spec."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.orders: dict[str, dict[str, Any]] = {}
        self.positions: list[dict[str, Any]] = []
        self.activities: list[dict[str, Any]] = []
        self.account = {"cash": "10000", "buying_power": "20000",
                        "options_buying_power": "10000", "equity": "10000"}
        self.place_status = 200
        self.place_error: Exception | None = None
        self.fill_on_place = False
        self.delete_status = 204
        self.cancel_to: str | None = "canceled"   # status a DELETE moves the order to
        self._seq = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, host = request.url.path, request.url.host
        if host == "data.alpaca.markets":
            if path.startswith("/v2/stocks/"):
                return httpx.Response(200, json={"symbol": path.split("/")[3],
                                                 "quote": {"bp": 100.0, "ap": 100.1,
                                                           "t": "2026-08-26T15:00:00Z"}})
            if path == "/v1beta3/crypto/us/latest/quotes":
                return httpx.Response(200, json={"quotes": {"BTC/USD": {
                    "bp": 60000.0, "ap": 60010.0, "t": "2026-08-26T15:00:00Z"}}})
            return httpx.Response(404, json={"message": "not found"})
        if path == "/v2/orders" and request.method == "POST":
            if self.place_error is not None:
                raise self.place_error
            body = json.loads(request.content)
            if self.place_status != 200:
                return httpx.Response(self.place_status,
                                      json={"code": 40310000, "message": "insufficient buying power"})
            self._seq += 1
            oid = f"ord-{self._seq}"
            o = order_body(oid, symbol=body["symbol"], side=body["side"], qty=body["qty"],
                           type_=body["type"], limit=body.get("limit_price"),
                           stop=body.get("stop_price"))
            if self.fill_on_place and body["type"] != "stop":
                o.update(status="filled", filled_qty=body["qty"],
                         filled_avg_price=body.get("limit_price") or "2.10")
                self.positions = [{"symbol": body["symbol"], "qty": body["qty"], "side": "long",
                                   "avg_entry_price": o["filled_avg_price"],
                                   "asset_class": "us_option"}]
            self.orders[oid] = o
            return httpx.Response(200, json=o)
        if path == "/v2/orders" and request.method == "GET":
            return httpx.Response(200, json=list(self.orders.values()))
        if path.startswith("/v2/orders/"):
            oid = path.rsplit("/", 1)[-1]
            if oid not in self.orders:
                return httpx.Response(404, json={"message": "order not found"})
            if request.method == "DELETE":
                if self.delete_status == 204 and self.cancel_to:
                    self.orders[oid]["status"] = self.cancel_to
                return httpx.Response(self.delete_status,
                                      json={} if self.delete_status != 204 else None)
            return httpx.Response(200, json=self.orders[oid])
        if path == "/v2/positions":
            return httpx.Response(200, json=self.positions)
        if path == "/v2/account":
            return httpx.Response(200, json=self.account)
        if path == "/v2/account/activities/FILL":
            token = request.url.params.get("page_token")
            size = int(request.url.params.get("page_size", 100))
            start = 0
            if token:
                start = next(i for i, a in enumerate(self.activities) if a["id"] == token) + 1
            return httpx.Response(200, json=self.activities[start:start + size])
        return httpx.Response(404, json={"message": f"no route {path}"})

    def hosts(self) -> set[str]:
        return {r.url.host for r in self.requests}


@pytest.fixture
def fake() -> FakeAlpaca:
    return FakeAlpaca()


def make(fake: FakeAlpaca, venue: str = "paper", payload: Any = None, *,
         market: Any = None, clock: Any = None) -> AlpacaBroker:
    payload = paper_payload() if payload is None else payload
    return AlpacaBroker(venue, lambda: payload, market=market,
                        transport=httpx.MockTransport(fake), sleep=lambda s: None,
                        **({"clock": clock} if clock else {}))


def intent(symbol: str = CALL, side: Side = Side.BUY_TO_OPEN, otype: OrderType = OrderType.LIMIT,
           limit: float | None = 2.10, stop: float | None = None, qty: int = 1) -> OrderIntent:
    return OrderIntent(intent_id="a-001", symbol=symbol, side=side, qty=qty, order_type=otype,
                       limit=limit if otype is OrderType.LIMIT else None, stop_price=stop)


def assert_no_secret(text: str) -> None:
    assert KEY not in text and SECRET not in text and LIVE_KEY not in text


# ── symbols and the wire ─────────────────────────────────────────────────

class TestSymbols:
    def test_padded_occ_round_trips_through_alpacas_form(self):
        assert to_alpaca_symbol(CALL) == ALPACA_CALL
        assert from_alpaca_symbol(ALPACA_CALL) == CALL
        assert to_alpaca_symbol("SPY   260826P00500000") == "SPY260826P00500000"

    def test_equities_and_crypto_pass_unchanged(self):
        for s in ("AAPL", "BTC/USD"):
            assert to_alpaca_symbol(s) == s and from_alpaca_symbol(s) == s
        assert asset_class("AAPL") == "equity"
        assert asset_class("BTC/USD") == "crypto"
        assert asset_class(CALL) == asset_class(ALPACA_CALL) == "option"


class TestBuildOrder:
    def test_an_option_limit_entry(self):
        body = build_order(intent(limit=2.075), "cid")
        assert body == {"symbol": ALPACA_CALL, "qty": "1", "side": "buy", "type": "limit",
                        "time_in_force": "day", "client_order_id": "cid",
                        "position_intent": "buy_to_open", "limit_price": "2.08"}

    def test_a_protective_stop(self):
        body = build_order(intent(side=Side.SELL_TO_CLOSE, otype=OrderType.STOP, stop=1.05), "c")
        assert body["type"] == "stop" and body["stop_price"] == "1.05"
        assert body["side"] == "sell" and body["position_intent"] == "sell_to_close"
        assert "limit_price" not in body

    def test_equity_is_day_and_carries_no_position_intent(self):
        body = build_order(intent("AAPL", otype=OrderType.MARKET, limit=None), "c")
        assert body["time_in_force"] == "day" and "position_intent" not in body

    def test_crypto_is_gtc_and_takes_no_plain_stop(self):
        assert build_order(intent("BTC/USD", limit=60000.0), "c")["time_in_force"] == "gtc"
        with pytest.raises(ValueError, match="no plain stop"):
            build_order(intent("BTC/USD", side=Side.SELL_TO_CLOSE, otype=OrderType.STOP,
                               stop=50000.0), "c")

    def test_a_spread_type_is_never_sent(self):
        with pytest.raises(ValueError):
            build_order(intent(otype=OrderType.NET_DEBIT), "c")


# ── the credential and the venue ─────────────────────────────────────────

class TestVenue:
    def test_paper_goes_to_the_paper_host_with_the_key_in_headers(self, fake):
        make(fake).place(intent())
        req = fake.requests[-1]
        assert req.url.host == "paper-api.alpaca.markets"
        assert req.headers["APCA-API-KEY-ID"] == KEY
        assert req.headers["APCA-API-SECRET-KEY"] == SECRET

    def test_live_goes_to_the_live_host(self, fake):
        b = make(fake, "live", {"venue": "live", "key_id": LIVE_KEY, "secret_key": SECRET})
        b.place(intent())
        assert fake.hosts() == {"api.alpaca.markets"}

    def test_a_paper_key_never_reaches_the_live_venue(self, fake):
        b = make(fake, "live", paper_payload())
        with pytest.raises(BrokerError, match="for Alpaca paper") as exc:
            b.place(intent())
        assert fake.requests == [], "refused before a byte left the box"
        assert_no_secret(str(exc.value))

    def test_a_live_key_never_reaches_the_paper_venue(self, fake):
        b = make(fake, "paper", {"venue": "live", "key_id": LIVE_KEY, "secret_key": SECRET})
        with pytest.raises(BrokerError):
            b.orders()
        assert fake.requests == []

    def test_locked_is_a_refusal_not_a_call(self, fake):
        def locked():
            raise Locked("locked")
        b = AlpacaBroker("paper", locked, transport=httpx.MockTransport(fake))
        with pytest.raises(BrokerError, match="locked"):
            b.positions()
        assert fake.requests == []

    def test_a_schwab_credential_in_memory_is_refused(self, fake):
        b = make(fake, payload={"app": {"key": "k", "secret": "s"}, "token": {}})
        with pytest.raises(BrokerError, match="not an Alpaca one"):
            b.orders()

    def test_no_such_venue(self):
        with pytest.raises(ValueError):
            AlpacaBroker("sandbox")

    def test_token_status_names_the_venue_and_no_value(self, fake):
        st = make(fake).token_status()
        assert st["broker"] == "alpaca" and st["venue"] == "paper" and st["armed"] is True
        assert_no_secret(json.dumps(st))


class TestVaultPayload:
    def test_picks_the_venue_from_the_envelope(self):
        env = {"version": 2, "trading": {}, "alpaca": {
            "paper": {"key_id": KEY, "secret_key": SECRET},
            "live": {"key_id": LIVE_KEY, "secret_key": SECRET}}}
        assert alpaca_payload(env, "paper")["key_id"] == KEY
        assert alpaca_payload(env, "live")["venue"] == "live"

    def test_missing_section_or_venue_says_how_to_fix_it(self):
        with pytest.raises(ValueError, match="--add-alpaca"):
            alpaca_payload({"trading": {}}, "paper")
        with pytest.raises(ValueError, match="no alpaca live keys"):
            alpaca_payload({"alpaca": {"paper": {"key_id": KEY, "secret_key": SECRET}}}, "live")

    def test_half_a_pair_is_not_a_credential(self):
        with pytest.raises(ValueError):
            AlpacaCredential.from_payload({"venue": "paper", "key_id": KEY})


# ── orders ───────────────────────────────────────────────────────────────

class TestPlace:
    def test_the_answer_is_the_order_with_the_padded_symbol(self, fake):
        r = make(fake).place(intent())
        assert r.status is OrderStatus.WORKING and r.order_id == "ord-1"
        assert r.symbol == CALL and r.side is Side.BUY_TO_OPEN and r.price == 2.10
        assert r.legs[0].instruction == "BUY_TO_OPEN"

    def test_client_order_id_is_unique_per_send_under_one_intent(self, fake):
        b = make(fake)
        b.place(intent())
        b.place(intent())
        ids = [json.loads(r.content)["client_order_id"] for r in fake.requests]
        assert ids[0] != ids[1] and all(i.startswith("a-001~") for i in ids)

    def test_403_is_a_rejection_not_an_exception(self, fake):
        fake.place_status = 403
        r = make(fake).place(intent())
        assert r.status is OrderStatus.REJECTED and "buying power" in r.message

    def test_500_is_a_broker_error(self, fake):
        fake.place_status = 500
        with pytest.raises(BrokerError):
            make(fake).place(intent())

    def test_a_timeout_is_reported_and_never_retried(self, fake):
        fake.place_error = httpx.ReadTimeout("slow")
        with pytest.raises(BrokerError, match="ReadTimeout") as exc:
            make(fake).place(intent())
        assert len([r for r in fake.requests if r.method == "POST"]) == 1
        assert_no_secret(str(exc.value))

    def test_crypto_stop_is_rejected_here_without_a_send(self, fake):
        r = make(fake).place(intent("BTC/USD", side=Side.SELL_TO_CLOSE,
                                    otype=OrderType.STOP, stop=50000.0))
        assert r.status is OrderStatus.REJECTED and fake.requests == []

    def test_equity_and_crypto_orders_go_through(self, fake):
        b = make(fake)
        assert b.place(intent("AAPL", otype=OrderType.MARKET, limit=None)).is_working
        assert b.place(intent("BTC/USD", limit=60000.0)).is_working
        sent = [json.loads(r.content)["symbol"] for r in fake.requests]
        assert sent == ["AAPL", "BTC/USD"]


class TestCancel:
    def test_a_cancel_is_re_read_until_terminal(self, fake):
        b = make(fake)
        oid = b.place(intent()).order_id
        r = b.cancel(oid)
        assert r.status is OrderStatus.CANCELED
        assert [q.method for q in fake.requests[-2:]] == ["DELETE", "GET"]

    def test_422_on_an_order_that_filled_reports_the_fill(self, fake):
        b = make(fake)
        oid = b.place(intent()).order_id
        fake.orders[oid].update(status="filled", filled_qty="1", filled_avg_price="2.05")
        fake.delete_status = 422
        r = b.cancel(oid)
        assert r.status is OrderStatus.FILLED and r.fill_price == 2.05

    def test_pending_cancel_at_the_deadline_is_still_working(self, fake):
        b = make(fake)
        oid = b.place(intent()).order_id
        fake.cancel_to = "pending_cancel"
        r = b.cancel(oid)
        assert r.is_working and r.message == "PENDING_CANCEL"

    def test_an_unknown_order_is_a_broker_error(self, fake):
        with pytest.raises(BrokerError):
            make(fake).cancel("nope")


class TestReads:
    def test_positions_outside_the_roots_are_counted_not_shown(self, fake):
        fake.positions = [
            {"symbol": ALPACA_CALL, "qty": "2", "side": "long", "avg_entry_price": "2.1",
             "asset_class": "us_option"},
            {"symbol": "SPY260826C00500000", "qty": "1", "side": "long",
             "avg_entry_price": "1", "asset_class": "us_option"},
            {"symbol": "AAPL", "qty": "10", "side": "long", "avg_entry_price": "100",
             "asset_class": "us_equity"},
        ]
        b = make(fake)
        ps = b.positions()
        assert [(p.symbol, p.qty) for p in ps] == [(CALL, 2)]
        assert b.excluded_positions == {"US_OPTION": 1, "US_EQUITY": 1}

    def test_a_short_is_negative(self, fake):
        fake.positions = [{"symbol": ALPACA_CALL, "qty": "1", "side": "short",
                           "avg_entry_price": "2", "asset_class": "us_option"}]
        assert make(fake).positions()[0].qty == -1

    def test_fills_are_paged_and_filtered_by_time(self, fake):
        since = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)
        fake.activities = [
            {"id": f"act-{i}", "activity_type": "FILL", "order_id": f"o{i}", "symbol": ALPACA_CALL,
             "side": "buy" if i % 2 else "sell", "qty": "1", "price": "2.00",
             "transaction_time": (since + timedelta(seconds=i)).isoformat().replace("+00:00", "Z")}
            for i in range(0, 130)]
        fills = make(fake).fills_since(since)
        assert len(fills) == 129, "the one at exactly `since` is not after it"
        assert fills[0].symbol == CALL and fills[0].side is Side.BUY_TO_OPEN
        pages = [r for r in fake.requests if r.url.path.endswith("/FILL")]
        assert len(pages) == 2 and pages[1].url.params["page_token"] == "act-99"

    def test_orders_report_a_hand_placed_spread_by_its_legs(self, fake):
        fake.orders["m1"] = {"id": "m1", "status": "filled", "order_class": "mleg", "qty": "1",
                             "type": "limit", "limit_price": "1.75", "filled_qty": "1",
                             "legs": [{"symbol": ALPACA_CALL, "side": "buy", "ratio_qty": "1",
                                       "position_intent": "buy_to_open"},
                                      {"symbol": "SPXW260826C06410000", "side": "sell",
                                       "ratio_qty": "2", "position_intent": "sell_to_open"}]}
        o = make(fake).orders()[0]
        assert o.is_multi_leg and o.symbol == "" and o.strategy == "mleg"
        assert [leg.instruction for leg in o.legs] == ["BUY_TO_OPEN", "SELL_TO_OPEN"]

    def test_balances_in_the_services_names(self, fake):
        b = make(fake).balances()
        assert b["option_buying_power"] == b["available_funds"] == 10000.0
        assert b["liquidation_value"] == 10000.0


class TestPreview:
    def test_computed_here_with_alpacas_index_fee(self, fake):
        p = make(fake).preview(intent(qty=2))
        assert p.cost_usd == 420.0 and p.commission_usd == 1.0 and p.accepted
        assert any("no preview endpoint" in m for m in p.messages)

    def test_more_than_the_account_can_pay_is_not_accepted(self, fake):
        fake.account["options_buying_power"] = "100"
        p = make(fake).preview(intent())
        assert not p.accepted and any(m.startswith("reject:") for m in p.messages)

    def test_an_exit_does_not_ask_about_buying_power(self, fake):
        make(fake).preview(intent(side=Side.SELL_TO_CLOSE))
        assert not any(r.url.path == "/v2/account" for r in fake.requests)


class TestMarketData:
    def test_quotes_and_chains_go_to_the_delegate(self, fake):
        data = MockBroker()
        data.set_quote("$SPX", SPX_NOW, SPX_NOW, SPX_NOW)
        data.set_chain("SPXW", {"root": "SPXW"})
        b = make(fake, market=data)
        assert b.quote("$SPX").last == SPX_NOW
        assert b.chain("SPXW")["root"] == "SPXW"
        assert fake.requests == []

    def test_without_a_delegate_an_index_quote_is_refused_by_name(self, fake):
        with pytest.raises(BrokerError, match="no index data"):
            make(fake).quote("$SPX")
        with pytest.raises(BrokerError, match="--market-credential"):
            make(fake).chain("SPXW")

    def test_without_a_delegate_equities_and_crypto_quote_from_alpaca(self, fake):
        b = make(fake)
        assert b.quote("AAPL").ask == 100.1
        assert b.quote("BTC/USD").bid == 60000.0
        assert fake.hosts() == {"data.alpaca.markets"}


# ── the service over Alpaca ──────────────────────────────────────────────

class TestService:
    def test_an_spx_entry_passes_every_bound_and_rests_its_stop_at_alpaca(self, fake, tmp_path):
        clock = Clock(MIDSESSION)
        data = MockBroker(clock=clock)
        data.set_quote(CALL, bid=2.00, ask=2.10)
        data.set_quote("$SPX", bid=SPX_NOW - 0.25, ask=SPX_NOW + 0.25, last=SPX_NOW)
        fake.fill_on_place = True
        b = AlpacaBroker("paper", market=data, clock=clock,
                         transport=httpx.MockTransport(fake), sleep=lambda s: None)
        svc = ExecService(b, ServiceConfig(state_dir=tmp_path / "execd", sha="t", mode="paper"),
                          clock=clock)
        b.bind(svc.arming)
        svc.unlock(paper_payload())
        assert svc.arming.state is ArmState.ARMED
        out = svc.place(entry())
        posted = [json.loads(r.content) for r in fake.requests if r.method == "POST"]
        assert posted[0]["symbol"] == ALPACA_CALL and posted[0]["type"] == "limit"
        assert any(p["type"] == "stop" and p["side"] == "sell" for p in posted), out
        assert fake.hosts() <= {"paper-api.alpaca.markets"}
        raw = svc.journal.path_for().read_text()
        assert_no_secret(raw)


# ── the entry point ──────────────────────────────────────────────────────

class TestMain:
    def test_alpaca_and_mock_together_are_refused(self, tmp_path):
        from execd.__main__ import main
        assert main(["--mock", "--alpaca", "--state-dir", str(tmp_path)]) == 2

    def test_alpaca_without_a_vault_or_market_credential_is_refused(self, tmp_path):
        from execd.__main__ import main
        assert main(["--alpaca", "--vault", str(tmp_path / "none.json"),
                     "--state-dir", str(tmp_path)]) == 2

    def test_mock_unlock_cannot_arm_alpaca(self, tmp_path):
        from execd.__main__ import main
        vault = tmp_path / "vault.json"
        vault.write_text("{}")
        assert main(["--alpaca", "--mock-unlock", "--vault", str(vault),
                     "--mode-file", str(tmp_path / "mode"),
                     "--state-dir", str(tmp_path)]) == 2

    def test_mock_unlock_refuses_the_alpaca_object(self):
        from execd.__main__ import may_mock_unlock
        assert may_mock_unlock(AlpacaBroker("paper")) is False


# ── the page ─────────────────────────────────────────────────────────────

class TestPage:
    PASS = "correct horse battery"

    def _page(self, tmp_path, fake, service_clock):
        from execd.page import create_page
        from execd.vault import Vault
        from .conftest import same_origin
        vault = Vault(tmp_path / "vault.json")
        vault.store({"version": 2,
                     "trading": {"app": {"key": "TKEY", "secret": "TSECRET"},
                                 "token": {"creation_timestamp": 1_757_000_000,
                                           "token": {"access_token": "a",
                                                     "refresh_token": "r"}}},
                     "alpaca": {"paper": {"key_id": KEY, "secret_key": SECRET}}}, self.PASS)
        b = make(fake, market=MockBroker())
        svc = ExecService(b, ServiceConfig(state_dir=tmp_path / "execd", sha="t", mode="paper"),
                          clock=service_clock)
        b.credential_source = None
        b.bind(svc.arming)
        app = create_page(svc, vault=vault, state_dir=tmp_path,
                          unlock_payload=lambda vp: alpaca_payload(vp, "paper"),
                          clock=service_clock)
        app.config["TESTING"] = True
        return svc, vault, same_origin(app.test_client())

    def test_unlock_arms_the_alpaca_keys(self, tmp_path, fake):
        svc, _, page = self._page(tmp_path, fake, Clock(MIDSESSION))
        r = page.post("/exec/unlock", data={"passphrase": self.PASS})
        assert r.status_code == 303, r.get_data(as_text=True)
        assert svc.arming.state is ArmState.ARMED
        assert svc.arming.credential()["venue"] == "paper"
        assert_no_secret(svc.journal.path_for().read_text())

    def test_a_schwab_grant_is_stored_but_never_swapped_over_alpaca(self, tmp_path, fake):
        from execd.page import _store_grant
        from execd.schwab import App
        svc, vault, page = self._page(tmp_path, fake, Clock(MIDSESSION))
        page.post("/exec/unlock", data={"passphrase": self.PASS})
        wrapped = {"creation_timestamp": 1_757_100_000,
                   "token": {"access_token": "n", "refresh_token": "new-refresh"}}
        _store_grant(svc, vault, None, App.TRADING, vault.load(self.PASS), wrapped,
                     self.PASS, in_memory=False)
        assert svc.arming.credential()["venue"] == "paper", "Alpaca keys still armed"
        stored = vault.load(self.PASS)
        assert stored["trading"]["token"]["token"]["refresh_token"] == "new-refresh"
        assert stored["alpaca"]["paper"]["key_id"] == KEY, "the alpaca section is kept"
        events = [e for e in svc.journal.read() if e["event"] == "reauth"]
        assert events[-1]["in_memory"] is False


# ── the vault script ─────────────────────────────────────────────────────

class TestVaultInit:
    def _mod(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "scripts" / "execd_vault_init.py"
        spec = importlib.util.spec_from_file_location("execd_vault_init", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_only_complete_pairs_become_venues(self):
        m = self._mod()
        assert m.alpaca_section({"ALPACA_PAPER_API_KEY_ID": KEY,
                                 "ALPACA_PAPER_API_SECRET_KEY": SECRET}) == {
            "paper": {"key_id": KEY, "secret_key": SECRET}}
        assert m.alpaca_section({}) == {}

    def test_half_a_pair_is_refused_without_the_value(self):
        m = self._mod()
        with pytest.raises(ValueError) as exc:
            m.alpaca_section({"ALPACA_LIVE_API_KEY_ID": LIVE_KEY})
        assert "ALPACA_LIVE_API_SECRET_KEY" in str(exc.value)
        assert_no_secret(str(exc.value))

    def test_add_alpaca_keeps_schwab_and_the_owner(self, tmp_path, monkeypatch):
        from execd.vault import Vault
        m = self._mod()
        path = tmp_path / "vault.json"
        Vault(path).store({"version": 2, "trading": {"app": {"key": "T"}}}, "correct horse battery")
        monkeypatch.setattr(m, "load_alpaca", lambda: {
            "ALPACA_PAPER_API_KEY_ID": KEY, "ALPACA_PAPER_API_SECRET_KEY": SECRET})
        monkeypatch.setattr(m, "_ask", lambda prompt: "correct horse battery")
        assert m.add_alpaca(path) == 0
        stored = Vault(path).load("correct horse battery")
        assert stored["trading"] == {"app": {"key": "T"}}
        assert stored["alpaca"]["paper"]["key_id"] == KEY
        assert oct(path.stat().st_mode & 0o777) == "0o600"
