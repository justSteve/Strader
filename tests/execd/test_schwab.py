"""The Schwab transport, exercised against a fake Trader API. [st-w2nw]

Two kinds of fixture, and the file says which is which:

**Recorded** — ``tests/fixtures/schwab/*.json`` were captured from the live
market-data API on 2026-09-04 by ``scripts/record_schwab_shapes.py``
(``_capture.json`` carries the time and market state). The quote and chain
tests read those files, so a field Schwab renames breaks a test here before
it breaks the service.

**Spec-derived** — the Trader API bodies (account numbers, positions, orders,
preview) are built in this file from the Accounts and Trading API
specification, because on the day this was written the app answered every
``/trader`` call with 401 ``no apiproduct match found``. They are marked
``SPEC`` below. When the product is on the app the recorder replaces them
with captures and these constants go.

The fake never opens a socket: ``httpx.MockTransport`` hands every request to
:class:`FakeSchwab`, which records it and answers from state. That is also
what lets the suite assert what the transport *never* sends — a PUT, a token
in an error message, a retried POST.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from execd.arming import Locked
from execd.broker import BrokerError, OrderStatus
from execd.intent import OrderIntent, OrderType, Side
from execd import schwab as S
from execd.schwab import Credential, SchwabBroker, build_order, format_price

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "schwab"

CALL = "SPXW  260904C07690000"          # the recorded option
ACCT_HASH = "0F3A9B1C2D4E5F60718293A4B5C6D7E8F9A0B1C2D3E4F5A6B7C8D9E0F1A2B3C4"
ACCT_NUMBER = "12345678"
NOW = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)   # 09:30 CT, RTH


def _load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


# ── SPEC-derived Trader API bodies ───────────────────────────────────────

def spec_account_numbers() -> list[dict[str, Any]]:
    return [{"accountNumber": ACCT_NUMBER, "hashValue": ACCT_HASH}]


def spec_position(symbol: str, long_qty: float, short_qty: float, avg: float,
                  asset: str = "OPTION", underlying: str = "$SPX") -> dict[str, Any]:
    inst: dict[str, Any] = {"assetType": asset, "symbol": symbol, "description": symbol}
    if asset == "OPTION":
        inst.update({"putCall": "CALL", "underlyingSymbol": underlying, "optionMultiplier": 100,
                     "type": "VANILLA"})
    return {"shortQuantity": short_qty, "averagePrice": avg, "currentDayProfitLoss": 0.0,
            "currentDayProfitLossPercentage": 0.0, "longQuantity": long_qty,
            "settledLongQuantity": long_qty, "settledShortQuantity": short_qty,
            "instrument": inst, "marketValue": avg * 100 * (long_qty - short_qty),
            "maintenanceRequirement": 0.0, "averageLongPrice": avg, "taxLotAverageLongPrice": avg,
            "longOpenProfitLoss": 0.0, "previousSessionLongQuantity": 0.0,
            "currentDayCost": avg * 100 * long_qty}


def spec_account(positions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"securitiesAccount": {"type": "MARGIN", "accountNumber": ACCT_NUMBER,
                                  "roundTrips": 0, "isDayTrader": False,
                                  "isClosingOnlyRestricted": False, "pfcbFlag": False,
                                  "positions": positions,
                                  "currentBalances": {"cashBalance": 25000.0}}}


def spec_order(order_id: int, *, status: str, symbol: str = CALL, instruction: str = "BUY_TO_OPEN",
               qty: int = 1, order_type: str = "LIMIT", price: float | None = 2.10,
               stop_price: float | None = None, fills: list[tuple[float, float, str]] = (),
               entered: str = "2026-09-04T14:31:02+0000") -> dict[str, Any]:
    filled = sum(q for q, _p, _t in fills)
    o: dict[str, Any] = {
        "session": "NORMAL", "duration": "DAY", "orderType": order_type,
        "complexOrderStrategyType": "NONE", "quantity": float(qty),
        "filledQuantity": float(filled), "remainingQuantity": float(qty - filled),
        "requestedDestination": "AUTO", "destinationLinkName": "AutoRoute",
        "orderLegCollection": [{
            "orderLegType": "OPTION", "legId": 1,
            "instrument": {"assetType": "OPTION", "cusip": "0SPXW.I40790000", "symbol": symbol,
                           "description": "SPXW 09/04/2026 7690.00 C", "instrumentId": 144452587,
                           "type": "VANILLA", "putCall": "CALL", "underlyingSymbol": "$SPX"},
            "instruction": instruction, "positionEffect": "OPENING" if instruction.endswith("OPEN") else "CLOSING",
            "quantity": float(qty)}],
        "orderStrategyType": "SINGLE", "orderId": order_id, "cancelable": status in ("WORKING", "ACCEPTED", "QUEUED"),
        "editable": False, "status": status, "enteredTime": entered,
        "tag": "API_TOS:CHART", "accountNumber": int(ACCT_NUMBER),
    }
    if price is not None:
        o["price"] = price
    if stop_price is not None:
        o["stopPrice"] = stop_price
    if status in ("FILLED", "CANCELED", "REJECTED", "EXPIRED"):
        o["closeTime"] = "2026-09-04T14:31:05+0000"
    if fills:
        o["orderActivityCollection"] = [{
            "activityType": "EXECUTION", "activityId": 90000000 + order_id, "executionType": "FILL",
            "quantity": float(q), "orderRemainingQuantity": 0.0,
            "executionLegs": [{"legId": 1, "quantity": float(q), "mismarkedQuantity": 0.0,
                               "price": p, "time": t, "instrumentId": 144452587}],
        } for q, p, t in fills]
    return o


def spec_preview(*, order_value: float = 210.0, commission: float = 0.65,
                 rejects: list[str] = (), warns: list[str] = ()) -> dict[str, Any]:
    def details(msgs: list[str], sev: str) -> list[dict[str, Any]]:
        return [{"validationRuleName": f"rule{i}", "message": m, "activityMessage": m,
                 "originalSeverity": sev, "overrideName": "", "overrideSeverity": sev}
                for i, m in enumerate(msgs)]
    return {
        "orderId": 0,
        "orderStrategy": {
            "accountNumber": ACCT_NUMBER, "advancedOrderType": "NONE",
            "orderBalance": {"orderValue": order_value, "projectedAvailableFund": 24789.35,
                             "projectedBuyingPower": 24789.35, "projectedCommission": commission},
            "orderStrategyType": "SINGLE", "orderVersion": 1, "session": "NORMAL",
            "status": "ACCEPTED", "allOrNone": False, "discretionary": False, "duration": "DAY",
            "filledQuantity": 0.0, "orderType": "LIMIT", "orderValue": order_value, "price": 2.10,
            "quantity": 1.0, "remainingQuantity": 1.0, "strategy": "NONE", "amountIndicator": "SHARES",
            "orderLegs": [{"askPrice": 2.15, "bidPrice": 2.05, "lastPrice": 2.10, "markPrice": 2.10,
                           "projectedCommission": commission, "quantity": 1.0, "finalSymbol": CALL,
                           "legId": 1, "assetType": "OPTION", "instruction": "BUY_TO_OPEN"}],
        },
        "orderValidationResult": {"alerts": [], "accepts": details(["ok"], "ACCEPT"),
                                  "rejects": details(list(rejects), "REJECT"),
                                  "reviews": [], "warns": details(list(warns), "ALERT")},
        "commissionAndFee": {
            "commission": {"commissionLegs": [{"commissionValues": [{"value": commission, "type": "COMMISSION"}]}]},
            "fee": {"feeLegs": [{"feeValues": [{"value": 0.04, "type": "INDEX_OPTION_FEE"}]}]},
            "trueCommission": {"commissionLegs": [{"commissionValues": [{"value": commission, "type": "COMMISSION"}]}]},
        },
    }


def schwab_error(status: int, detail: str) -> httpx.Response:
    return httpx.Response(status, json={"errors": [{"id": "corr-1", "status": status,
                                                     "title": "Unauthorized" if status == 401 else "Error",
                                                     "detail": detail}]})


# ── the fake API ─────────────────────────────────────────────────────────

class FakeSchwab:
    """State plus a handler. Every request is appended to ``calls`` as
    ``(method, path, params, json_body, authorization)``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str], Any, str]] = []
        self.token_posts: list[dict[str, str]] = []
        self.valid_access = {"ACCESS-STORED", "ACCESS-FRESH"}
        self.reject_all = False            # every bearer is refused, minted or not
        self.access_counter = 0
        self.refresh_ok = True
        self.orders: dict[int, dict[str, Any]] = {}
        self.next_order_id = 4242
        self.place_status = 201            # what POST orders answers
        self.place_location = True
        self.place_detail = "rejected by validation"
        self.fail_get_order_once = False
        self.cancel_status = 200
        self.positions: list[dict[str, Any]] = []
        self.preview = spec_preview()
        self.fill_on_place: list[tuple[float, float, str]] | None = None
        self.quotes = {**_load("quotes_index"), **_load("quotes_option")}
        self.chain = _load("chain")

    # what a placed order becomes
    def _placed(self, body: dict[str, Any]) -> dict[str, Any]:
        oid = self.next_order_id
        self.next_order_id += 1
        leg = body["orderLegCollection"][0]
        fills = self.fill_on_place or []
        status = "FILLED" if fills else "WORKING"
        o = spec_order(oid, status=status, symbol=leg["instrument"]["symbol"],
                       instruction=leg["instruction"], qty=int(leg["quantity"]),
                       order_type=body["orderType"],
                       price=float(body["price"]) if "price" in body else None,
                       stop_price=float(body["stopPrice"]) if "stopPrice" in body else None,
                       fills=fills)
        self.orders[oid] = o
        return o

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = dict(request.url.params)
        auth = request.headers.get("Authorization", "")
        body: Any = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = dict(httpx.QueryParams(request.content.decode()))
        self.calls.append((request.method, path, params, body, auth))

        if path == "/v1/oauth/token":
            self.token_posts.append(body)
            if not self.refresh_ok:
                return httpx.Response(400, json={"error": "invalid_grant",
                                                 "error_description": "refresh token invalid"})
            self.access_counter += 1
            new = f"ACCESS-NEW-{self.access_counter}"
            self.valid_access.add(new)
            answer = {"access_token": new, "expires_in": 1800, "token_type": "Bearer",
                      "scope": "api", "id_token": "ID-TOKEN-VALUE"}
            # Schwab returns the refresh token on both grants; on a refresh it is
            # the same one, on an authorization_code grant it is new.
            answer["refresh_token"] = (body.get("refresh_token") if body.get("grant_type") == "refresh_token"
                                       else "REFRESH-VALUE")
            return httpx.Response(200, json=answer)

        if self.reject_all or not auth.startswith("Bearer ") or auth[7:] not in self.valid_access:
            return schwab_error(401, "Client not authorized")

        if path == "/marketdata/v1/quotes":
            wanted = params.get("symbols", "").split(",")
            out = {s: self.quotes[s] for s in wanted if s in self.quotes}
            for s in wanted:
                if s not in self.quotes:
                    out.setdefault("errors", {"invalidSymbols": []})["invalidSymbols"].append(s)
            return httpx.Response(200, json=out)
        if path == "/marketdata/v1/chains":
            return httpx.Response(200, json=self.chain)

        if path == "/trader/v1/accounts/accountNumbers":
            return httpx.Response(200, json=spec_account_numbers())
        if path == f"/trader/v1/accounts/{ACCT_HASH}":
            return httpx.Response(200, json=spec_account(self.positions))
        if path == f"/trader/v1/accounts/{ACCT_HASH}/previewOrder" and request.method == "POST":
            return httpx.Response(200, json=self.preview)
        if path == f"/trader/v1/accounts/{ACCT_HASH}/orders":
            if request.method == "GET":
                return httpx.Response(200, json=list(self.orders.values()))
            if self.place_status == 400:
                return schwab_error(400, self.place_detail)
            if self.place_status >= 500:
                return schwab_error(self.place_status, "server error")
            o = self._placed(body)
            headers = {}
            if self.place_location:
                headers["Location"] = f"https://api.schwabapi.com/trader/v1/accounts/{ACCT_HASH}/orders/{o['orderId']}"
            return httpx.Response(201, headers=headers)
        m = re.fullmatch(rf"/trader/v1/accounts/{ACCT_HASH}/orders/(\d+)", path)
        if m:
            oid = int(m.group(1))
            if request.method == "GET":
                if self.fail_get_order_once:
                    self.fail_get_order_once = False
                    return schwab_error(503, "temporarily unavailable")
                if oid not in self.orders:
                    return schwab_error(404, "order not found")
                return httpx.Response(200, json=self.orders[oid])
            if request.method == "DELETE":
                if self.cancel_status >= 500:
                    return schwab_error(self.cancel_status, "server error")
                o = self.orders.get(oid)
                if o is None:
                    return schwab_error(404, "order not found")
                if o["status"] in ("WORKING", "ACCEPTED", "QUEUED"):
                    o["status"] = "CANCELED"
                    o["cancelable"] = False
                    return httpx.Response(200)
                return schwab_error(400, "order is not cancelable")
        return schwab_error(404, f"no route {request.method} {path}")


def payload(*, expires_in_s: int = 1500, created_ago_s: int = 3600) -> dict[str, Any]:
    now = int(time.time())
    return {"app": {"key": "APPKEY-VALUE", "secret": "APPSECRET-VALUE"},
            "token": {"creation_timestamp": now - created_ago_s,
                      "token": {"access_token": "ACCESS-STORED", "refresh_token": "REFRESH-VALUE",
                                "expires_at": now + expires_in_s, "expires_in": 1800,
                                "token_type": "Bearer", "scope": "api", "id_token": "ID-VALUE"}}}


SECRETS = ("ACCESS-STORED", "ACCESS-NEW", "ACCESS-FRESH", "REFRESH-VALUE", "APPSECRET-VALUE",
           "ID-VALUE", "ID-TOKEN-VALUE", ACCT_NUMBER, ACCT_HASH)


def assert_no_secret(text: str) -> None:
    for s in SECRETS:
        assert s not in text, f"{s!r} leaked into: {text!r}"


@pytest.fixture
def fake() -> FakeSchwab:
    return FakeSchwab()


@pytest.fixture
def cred() -> dict[str, Any]:
    return payload()


@pytest.fixture
def broker(fake: FakeSchwab, cred: dict[str, Any]) -> SchwabBroker:
    return SchwabBroker(lambda: cred, clock=lambda: NOW,
                        transport=httpx.MockTransport(fake.handler))


def intent(**kw: Any) -> OrderIntent:
    base = dict(intent_id="t-1", symbol=CALL, side=Side.BUY_TO_OPEN, qty=1,
                order_type=OrderType.LIMIT, limit=2.10)
    base.update(kw)
    return OrderIntent(**base)


# ── credential and OAuth helpers ─────────────────────────────────────────

class TestCredential:
    def test_from_payload_names_the_missing_field_and_never_a_value(self):
        p = payload()
        del p["token"]["token"]["refresh_token"]
        with pytest.raises(ValueError) as exc:
            Credential.from_payload(p)
        assert "refresh_token" in str(exc.value)
        assert_no_secret(str(exc.value))

    @pytest.mark.parametrize("mutate", [
        lambda p: p.pop("app"),
        lambda p: p["app"].pop("secret"),
        lambda p: p.pop("token"),
        lambda p: p["token"].pop("creation_timestamp"),
        lambda p: "not a mapping",
    ])
    def test_every_missing_piece_is_refused(self, mutate):
        p = payload()
        r = mutate(p)
        with pytest.raises(ValueError):
            Credential.from_payload(r if isinstance(r, str) else p)

    def test_the_wall_is_seven_days_from_creation(self):
        c = Credential.from_payload(payload(created_ago_s=0))
        assert c.refresh_wall - c.created_at == timedelta(days=7)
        assert "REFRESH" not in repr(c)


class TestOAuthHelpers:
    def test_authorize_url_carries_the_four_parameters(self):
        url = S.authorize_url("APPKEY-VALUE", "https://127.0.0.1:8182", "state-xyz")
        assert url.startswith(S.AUTHORIZE_ENDPOINT + "?")
        q = dict(httpx.URL(url).params)
        assert q == {"client_id": "APPKEY-VALUE", "redirect_uri": "https://127.0.0.1:8182",
                     "response_type": "code", "state": "state-xyz"}

    def test_code_is_decoded_from_the_pasted_url(self):
        url = "https://127.0.0.1:8182/?code=C0.abc%40&session=xyz&state=state-xyz"
        assert S.code_from_received_url(url, "state-xyz") == "C0.abc@"

    def test_a_state_mismatch_is_refused(self):
        with pytest.raises(ValueError, match="state"):
            S.code_from_received_url("https://x/?code=abc&state=other", "state-xyz")

    def test_a_url_without_a_code_is_refused(self):
        with pytest.raises(ValueError, match="code"):
            S.code_from_received_url("https://x/?state=state-xyz")

    def test_exchange_posts_the_code_with_basic_auth_and_starts_the_clock(self, fake):
        client = httpx.Client(transport=httpx.MockTransport(fake.handler))
        wrapped = S.exchange(client, "APPKEY-VALUE", "APPSECRET-VALUE", "https://cb", "C0.abc@",
                             now=1_800_000_000)
        method, path, _params, body, auth = fake.calls[-1]
        assert (method, path) == ("POST", "/v1/oauth/token")
        assert auth.startswith("Basic ")
        assert body == {"grant_type": "authorization_code", "code": "C0.abc@",
                        "redirect_uri": "https://cb"}
        assert wrapped["creation_timestamp"] == 1_800_000_000
        assert wrapped["token"]["expires_at"] == 1_800_000_000 + 1800
        assert wrapped["token"]["access_token"] == "ACCESS-NEW-1"

    def test_exchange_without_a_refresh_token_in_the_answer_is_an_error(self, fake):
        # A defective grant (the 2026-08-12 incident shape): 200, access token, no refresh.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "ACCESS-FRESH", "expires_in": 1800})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(BrokerError, match="refresh_token"):
            S.exchange(client, "k", "s", "https://cb", "code")

    def test_refresh_keeps_the_creation_timestamp_and_the_refresh_token(self, fake, cred):
        client = httpx.Client(transport=httpx.MockTransport(fake.handler))
        c = Credential.from_payload(cred)
        wrapped = S.refresh(client, c, now=1_800_000_100)
        assert wrapped["creation_timestamp"] == cred["token"]["creation_timestamp"]
        assert wrapped["token"]["refresh_token"] == "REFRESH-VALUE"
        assert wrapped["token"]["expires_at"] == 1_800_000_100 + 1800
        assert fake.token_posts[-1] == {"grant_type": "refresh_token", "refresh_token": "REFRESH-VALUE"}

    def test_a_refused_refresh_is_a_broker_error_without_the_token_in_it(self, fake, cred):
        fake.refresh_ok = False
        client = httpx.Client(transport=httpx.MockTransport(fake.handler))
        with pytest.raises(BrokerError) as exc:
            S.refresh(client, Credential.from_payload(cred))
        assert "HTTP 400" in str(exc.value) and "refresh token invalid" in str(exc.value)
        assert_no_secret(str(exc.value))


# ── prices and order bodies ──────────────────────────────────────────────

class TestOrderBody:
    @pytest.mark.parametrize("pts,text", [(2.07, "2.07"), (2.1, "2.10"), (0.05, "0.05"),
                                          (12.5, "12.50"), (3.125, "3.13")])
    def test_prices_are_two_decimal_strings_half_up(self, pts, text):
        assert format_price(pts) == text

    def test_limit_buy_golden(self):
        assert build_order(intent()) == {
            "session": "NORMAL", "duration": "DAY", "orderType": "LIMIT",
            "orderStrategyType": "SINGLE", "price": "2.10",
            "orderLegCollection": [{"instruction": "BUY_TO_OPEN", "quantity": 1,
                                    "instrument": {"symbol": CALL, "assetType": "OPTION"}}],
        }

    def test_market_sell_carries_no_price(self):
        body = build_order(intent(side=Side.SELL_TO_CLOSE, order_type=OrderType.MARKET, limit=None))
        assert body["orderType"] == "MARKET" and "price" not in body and "stopPrice" not in body
        assert body["orderLegCollection"][0]["instruction"] == "SELL_TO_CLOSE"

    def test_stop_carries_stop_price_only(self):
        body = build_order(intent(side=Side.SELL_TO_CLOSE, order_type=OrderType.STOP,
                                  limit=None, stop_price=1.45))
        assert body["orderType"] == "STOP" and body["stopPrice"] == "1.45" and "price" not in body

    def test_the_only_session_and_duration_are_normal_and_day(self):
        body = build_order(intent())
        assert (body["session"], body["duration"]) == ("NORMAL", "DAY")


# ── the transport, locked and unlocked ───────────────────────────────────

class TestArmingAndTokens:
    def test_locked_is_a_broker_error_and_no_request_is_made(self, fake):
        def locked() -> Any:
            raise Locked("no credential")
        b = SchwabBroker(locked, transport=httpx.MockTransport(fake.handler))
        with pytest.raises(BrokerError, match="locked"):
            b.quote(CALL)
        assert fake.calls == []

    def test_unbound_is_a_broker_error(self, fake):
        b = SchwabBroker(transport=httpx.MockTransport(fake.handler))
        with pytest.raises(BrokerError, match="credential source"):
            b.positions()
        assert fake.calls == []

    def test_bind_takes_the_arming_state(self, fake, cred):
        class Arming:
            def credential(self) -> Any:
                return cred
        b = SchwabBroker(transport=httpx.MockTransport(fake.handler)).bind(Arming())
        assert b.quote(CALL).bid == 56.2

    def test_a_fresh_stored_access_token_is_used_without_a_refresh(self, broker, fake):
        broker.quote(CALL)
        assert fake.token_posts == []
        assert fake.calls[0][4] == "Bearer ACCESS-STORED"

    def test_an_expiring_access_token_is_refreshed_first_and_cached(self, fake):
        cred = payload(expires_in_s=30)
        b = SchwabBroker(lambda: cred, clock=lambda: NOW, transport=httpx.MockTransport(fake.handler))
        b.quote(CALL)
        b.quote(CALL)
        assert len(fake.token_posts) == 1
        assert fake.token_posts[0]["grant_type"] == "refresh_token"
        bearers = [c[4] for c in fake.calls if c[1] == "/marketdata/v1/quotes"]
        assert bearers == ["Bearer ACCESS-NEW-1", "Bearer ACCESS-NEW-1"]

    def test_the_refresh_uses_basic_auth_with_the_app_key_and_secret(self, fake):
        cred = payload(expires_in_s=30)
        b = SchwabBroker(lambda: cred, transport=httpx.MockTransport(fake.handler))
        b.quote(CALL)
        auth = [c[4] for c in fake.calls if c[1] == "/v1/oauth/token"][0]
        import base64
        assert base64.b64decode(auth.split(" ", 1)[1]).decode() == "APPKEY-VALUE:APPSECRET-VALUE"

    def test_a_401_on_a_get_forces_one_refresh_and_one_retry(self, fake):
        cred = payload()
        cred["token"]["token"]["access_token"] = "ACCESS-REVOKED"
        b = SchwabBroker(lambda: cred, transport=httpx.MockTransport(fake.handler))
        assert b.quote(CALL).ask == 57.8
        methods = [(c[0], c[1]) for c in fake.calls]
        assert methods == [("GET", "/marketdata/v1/quotes"), ("POST", "/v1/oauth/token"),
                           ("GET", "/marketdata/v1/quotes")]

    def test_a_second_401_is_reported_not_retried_again(self, fake):
        cred = payload()
        cred["token"]["token"]["access_token"] = "ACCESS-REVOKED"
        fake.reject_all = True             # nothing the fake mints is accepted either
        b = SchwabBroker(lambda: cred, transport=httpx.MockTransport(fake.handler))
        with pytest.raises(BrokerError) as exc:
            b.quote(CALL)
        assert "HTTP 401" in str(exc.value)
        assert sum(1 for c in fake.calls if c[1] == "/marketdata/v1/quotes") == 2
        assert_no_secret(str(exc.value))

    def test_a_401_on_a_post_is_never_retried(self, fake):
        cred = payload()
        cred["token"]["token"]["access_token"] = "ACCESS-REVOKED"
        b = SchwabBroker(lambda: cred, clock=lambda: NOW, transport=httpx.MockTransport(fake.handler))
        b._hash = ("REFRESH-VALUE", ACCT_HASH)     # skip the hash lookup: the POST is the subject
        with pytest.raises(BrokerError, match="HTTP 401"):
            b.place(intent())
        posts = [c for c in fake.calls if c[0] == "POST" and c[1].endswith("/orders")]
        assert len(posts) == 1

    def test_a_refresh_token_past_its_wall_is_refused_before_any_call(self, fake):
        cred = payload(expires_in_s=30, created_ago_s=8 * 86400)
        b = SchwabBroker(lambda: cred, transport=httpx.MockTransport(fake.handler))
        with pytest.raises(BrokerError, match="seven-day wall"):
            b.quote(CALL)
        assert fake.calls == []

    def test_a_new_credential_invalidates_the_cached_access_token(self, fake):
        holder = {"cred": payload(expires_in_s=30)}
        b = SchwabBroker(lambda: holder["cred"], transport=httpx.MockTransport(fake.handler))
        b.quote(CALL)
        second = payload(expires_in_s=30)
        second["token"]["token"]["refresh_token"] = "REFRESH-SECOND"
        holder["cred"] = second
        b.quote(CALL)
        assert [p["refresh_token"] for p in fake.token_posts] == ["REFRESH-VALUE", "REFRESH-SECOND"]

    def test_token_status_carries_the_wall_and_no_values(self, broker):
        st = broker.token_status()
        assert st["armed"] is True and st["refresh_wall_in_s"] > 0
        assert_no_secret(json.dumps(st))

    def test_token_status_when_locked(self, fake):
        def locked() -> Any:
            raise Locked("no credential")
        b = SchwabBroker(locked, transport=httpx.MockTransport(fake.handler))
        assert b.token_status()["armed"] is False


# ── market data (recorded fixtures) ──────────────────────────────────────

class TestMarketData:
    def test_the_fixtures_are_recorded_and_say_when(self):
        meta = _load("_capture")
        assert meta["recorded_by"] == "scripts/record_schwab_shapes.py"
        assert set(meta["captures"]) >= {"quotes_index", "quotes_option", "chain"}
        for c in meta["captures"].values():
            assert c["status"] == 200 and c["captured_at_utc"].startswith("2026-")

    def test_an_option_quote_reads_bid_ask_last_and_quote_time(self, broker):
        q = broker.quote(CALL)
        assert (q.bid, q.ask, q.last) == (56.2, 57.8, 61.53)
        assert q.as_of == datetime.fromtimestamp(1788469198132 / 1000, tz=timezone.utc)
        assert q.symbol == CALL

    def test_an_index_quote_has_no_book_so_last_stands_on_both_sides(self, broker):
        q = broker.quote("$SPX")
        assert q.bid == q.ask == q.last == 7747.71
        assert q.as_of == datetime.fromtimestamp(1788468548887 / 1000, tz=timezone.utc)

    def test_a_future_quote_reads_its_book(self, broker):
        q = broker.quote("/ESU26")
        assert (q.bid, q.ask, q.last) == (7739.0, 7739.25, 7739.0)

    def test_an_unknown_symbol_is_a_broker_error(self, broker):
        with pytest.raises(BrokerError, match="no quote for"):
            broker.quote("SPXW  260904C99990000")

    def test_the_chain_is_filtered_to_the_root_and_keeps_its_envelope(self, broker, fake):
        ch = broker.chain("SPXW")
        assert ch["status"] == "SUCCESS" and ch["root"] == "SPXW" and ch["underlyingPrice"] == 7747.71
        assert list(ch["callExpDateMap"]) == ["2026-09-04:0"]
        contracts = [c for strikes in ch["callExpDateMap"].values() for v in strikes.values() for c in v]
        assert contracts and all(c["optionRoot"] == "SPXW" for c in contracts)
        assert all(len(c["symbol"]) == 21 for c in contracts), "Schwab spells option symbols padded to 21"
        params = fake.calls[-1][2]
        assert params["symbol"] == "$SPX" and params["strategy"] == "SINGLE"
        assert params["fromDate"] == "2026-09-04"

    def test_the_chain_for_another_root_is_empty_not_wrong(self, broker):
        ch = broker.chain("SPX")
        assert ch["callExpDateMap"] == {} and ch["putExpDateMap"] == {}

    def test_an_expiry_pins_both_dates(self, broker, fake):
        broker.chain("SPXW", "2026-09-08")
        params = fake.calls[-1][2]
        assert params["fromDate"] == params["toDate"] == "2026-09-08"


# ── the account (SPEC) ───────────────────────────────────────────────────

class TestAccount:
    def test_the_hash_is_fetched_once_and_the_number_is_never_kept(self, broker, fake):
        assert broker.account_hash() == ACCT_HASH
        assert broker.account_hash() == ACCT_HASH
        assert sum(1 for c in fake.calls if c[1].endswith("/accountNumbers")) == 1
        assert ACCT_NUMBER not in json.dumps(broker.__dict__, default=str)

    def test_an_error_message_never_carries_the_hash(self, broker, fake):
        broker.account_hash()
        fake.reject_all = True
        with pytest.raises(BrokerError) as exc:
            broker.positions()
        assert "<account>" in str(exc.value)
        assert_no_secret(str(exc.value))

    def test_positions_reports_index_options_only(self, broker, fake):
        fake.positions = [
            spec_position(CALL, 2, 0, 2.10),
            spec_position("SPXW  260904P07600000", 0, 1, 1.50),
            spec_position("AAPL", 100, 0, 190.0, asset="EQUITY"),
            spec_position("SPY   260918C00500000", 1, 0, 3.0, underlying="SPY"),
            spec_position("SPXW  260904C07800000", 1, 1, 0.5),     # flat
        ]
        got = {p.symbol: p for p in broker.positions()}
        assert set(got) == {CALL, "SPXW  260904P07600000"}
        assert got[CALL].qty == 2 and got[CALL].avg_price == 2.10
        assert got["SPXW  260904P07600000"].qty == -1
        assert broker.excluded_positions == {"EQUITY": 1, "OPTION": 1}

    def test_positions_asks_for_the_positions_field(self, broker, fake):
        broker.positions()
        method, path, params, _b, _a = fake.calls[-1]
        assert (method, path, params) == ("GET", f"/trader/v1/accounts/{ACCT_HASH}", {"fields": "positions"})


# ── orders (SPEC) ────────────────────────────────────────────────────────

class TestPreview:
    def test_the_request_is_the_golden_body(self, broker, fake):
        broker.preview(intent())
        method, path, _p, body, _a = fake.calls[-1]
        assert (method, path) == ("POST", f"/trader/v1/accounts/{ACCT_HASH}/previewOrder")
        assert body == build_order(intent())

    def test_cost_and_commission_come_from_the_order_balance(self, broker):
        p = broker.preview(intent())
        assert (p.cost_usd, p.commission_usd, p.total_usd) == (210.0, 0.65, 210.65)
        assert p.accepted and p.messages == () and p.price == 2.10

    def test_a_reject_is_carried_not_swallowed(self, broker, fake):
        fake.preview = spec_preview(rejects=["Insufficient buying power"], warns=["Wide spread"])
        p = broker.preview(intent())
        assert p.accepted is False
        assert p.messages == ("reject: Insufficient buying power", "warn: Wide spread")

    def test_a_market_preview_prices_off_the_leg(self, broker):
        p = broker.preview(intent(order_type=OrderType.MARKET, limit=None))
        assert p.price == 2.15          # the leg's ask, for a buy


class TestPlace:
    def test_a_marketable_limit_fills_and_reports_the_fill(self, broker, fake):
        fake.fill_on_place = [(1, 2.08, "2026-09-04T14:31:03+0000")]
        r = broker.place(intent())
        assert r.status is OrderStatus.FILLED and r.order_id == "4242"
        assert (r.filled_qty, r.fill_price, r.price, r.qty) == (1, 2.08, 2.10, 1)
        assert r.side is Side.BUY_TO_OPEN and r.order_type is OrderType.LIMIT
        assert r.submitted_at == datetime(2026, 9, 4, 14, 31, 2, tzinfo=timezone.utc)
        methods = [(c[0], c[1].rsplit("/", 1)[-1]) for c in fake.calls]
        assert methods[-2:] == [("POST", "orders"), ("GET", "4242")]

    def test_an_acknowledged_order_is_working_with_the_broker_status_in_its_message(self, broker, fake):
        r = broker.place(intent())
        assert r.status is OrderStatus.WORKING and r.order_id == "4242" and r.filled_qty == 0

    def test_a_partial_fill_reports_the_average(self, broker, fake):
        fake.fill_on_place = [(1, 2.00, "2026-09-04T14:31:03+0000"), (1, 2.10, "2026-09-04T14:31:04+0000")]
        r = broker.place(intent(qty=2))
        assert (r.filled_qty, r.fill_price) == (2, 2.05)

    def test_a_400_is_a_rejection_not_an_exception(self, broker, fake):
        fake.place_status = 400
        r = broker.place(intent())
        assert r.status is OrderStatus.REJECTED and "rejected by validation" in r.message
        assert r.order_id.startswith("rejected:")

    def test_a_500_is_a_broker_error(self, broker, fake):
        fake.place_status = 503
        with pytest.raises(BrokerError, match="HTTP 503"):
            broker.place(intent())

    def test_a_201_without_a_location_is_held_as_working_and_says_so(self, broker, fake):
        fake.place_location = False
        r = broker.place(intent())
        assert r.status is OrderStatus.WORKING and r.order_id.startswith("unnamed:")
        assert "no order id" in r.message

    def test_a_failed_read_after_the_201_still_holds_the_order(self, broker, fake):
        fake.fail_get_order_once = True
        r = broker.place(intent())
        assert r.status is OrderStatus.WORKING and r.order_id == "4242"
        assert "status unknown until reconcile" in r.message

    def test_a_stop_rests(self, broker, fake):
        r = broker.place(intent(side=Side.SELL_TO_CLOSE, order_type=OrderType.STOP, limit=None, stop_price=1.45))
        assert r.status is OrderStatus.WORKING and r.order_type is OrderType.STOP and r.price == 1.45


class TestCancel:
    def test_a_working_order_cancels_and_the_read_confirms_it(self, broker, fake):
        placed = broker.place(intent())
        r = broker.cancel(placed.order_id)
        assert r.status is OrderStatus.CANCELED and r.order_id == placed.order_id
        methods = [(c[0], c[1].rsplit("/", 1)[-1]) for c in fake.calls[-2:]]
        assert methods == [("DELETE", placed.order_id), ("GET", placed.order_id)]

    def test_cancelling_a_filled_order_reports_the_fill(self, broker, fake):
        fake.fill_on_place = [(1, 2.08, "2026-09-04T14:31:03+0000")]
        placed = broker.place(intent())
        r = broker.cancel(placed.order_id)
        assert r.status is OrderStatus.FILLED and r.fill_price == 2.08

    def test_a_broker_outage_on_cancel_is_a_broker_error(self, broker, fake):
        placed = broker.place(intent())
        fake.cancel_status = 503
        with pytest.raises(BrokerError, match="HTTP 503"):
            broker.cancel(placed.order_id)

    def test_cancelling_an_unknown_order_is_a_broker_error(self, broker):
        with pytest.raises(BrokerError, match="HTTP 404"):
            broker.cancel("999999")


class TestOrdersAndFills:
    def test_the_window_is_two_days_back_in_schwabs_format(self, broker, fake):
        broker.orders()
        params = fake.calls[-1][2]
        assert params == {"fromEnteredTime": "2026-09-02T14:30:00.000Z",
                          "toEnteredTime": "2026-09-05T14:30:00.000Z"}

    @pytest.mark.parametrize("raw,expected", [
        ("FILLED", OrderStatus.FILLED), ("REJECTED", OrderStatus.REJECTED),
        ("CANCELED", OrderStatus.CANCELED), ("EXPIRED", OrderStatus.CANCELED),
        ("REPLACED", OrderStatus.CANCELED), ("WORKING", OrderStatus.WORKING),
        ("ACCEPTED", OrderStatus.WORKING), ("QUEUED", OrderStatus.WORKING),
        ("PENDING_ACTIVATION", OrderStatus.WORKING), ("AWAITING_STOP_CONDITION", OrderStatus.WORKING),
        ("PENDING_CANCEL", OrderStatus.WORKING), ("NEW", OrderStatus.WORKING),
        ("UNKNOWN", OrderStatus.WORKING),
    ])
    def test_every_schwab_status_maps(self, broker, fake, raw, expected):
        fake.orders[1] = spec_order(1, status=raw)
        (r,) = broker.orders()
        assert r.status is expected
        if expected is OrderStatus.WORKING and raw != "WORKING":
            assert r.message == raw

    def test_a_hand_placed_stop_limit_reads_as_a_stop(self, broker, fake):
        fake.orders[7] = spec_order(7, status="WORKING", order_type="STOP_LIMIT", price=1.40, stop_price=1.45,
                                    instruction="SELL_TO_CLOSE")
        (r,) = broker.orders()
        assert r.order_type is OrderType.STOP and r.price == 1.45 and r.side is Side.SELL_TO_CLOSE

    def test_fills_since_reads_execution_legs_after_the_mark(self, broker, fake):
        fake.orders[1] = spec_order(1, status="FILLED", fills=[(1, 2.08, "2026-09-04T14:31:03+0000")])
        fake.orders[2] = spec_order(2, status="FILLED", instruction="SELL_TO_CLOSE",
                                    fills=[(1, 2.40, "2026-09-04T15:02:00+0000")])
        fills = broker.fills_since(datetime(2026, 9, 4, 14, 45, tzinfo=timezone.utc))
        assert [(f.order_id, f.side, f.qty, f.price) for f in fills] == [("2", Side.SELL_TO_CLOSE, 1, 2.40)]
        assert fills[0].at == datetime(2026, 9, 4, 15, 2, tzinfo=timezone.utc)

    def test_fills_are_sorted_by_time(self, broker, fake):
        fake.orders[2] = spec_order(2, status="FILLED", fills=[(1, 2.40, "2026-09-04T15:02:00+0000")])
        fake.orders[1] = spec_order(1, status="FILLED", fills=[(1, 2.08, "2026-09-04T14:31:03+0000")])
        fills = broker.fills_since(datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc))
        assert [f.order_id for f in fills] == ["1", "2"]


# ── what the transport never does ────────────────────────────────────────

class TestNever:
    def test_no_put_anywhere_in_a_full_day(self, broker, fake):
        fake.positions = [spec_position(CALL, 1, 0, 2.10)]
        broker.quote(CALL)
        broker.chain("SPXW")
        broker.preview(intent())
        placed = broker.place(intent())
        broker.place(intent(intent_id="t-2", side=Side.SELL_TO_CLOSE, order_type=OrderType.STOP,
                            limit=None, stop_price=1.45))
        broker.orders()
        broker.positions()
        broker.fills_since(NOW - timedelta(hours=1))
        broker.cancel(placed.order_id)
        assert {c[0] for c in fake.calls} == {"GET", "POST", "DELETE"}

    def test_the_source_has_no_replace_verb(self):
        source = (REPO / "execd" / "schwab.py").read_text(encoding="utf-8")
        assert '"PUT"' not in source and ".put(" not in source and "replace_order" not in source

    def test_a_transport_failure_is_a_broker_error_with_no_secret(self, cred):
        def down(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out", request=request)
        b = SchwabBroker(lambda: cred, transport=httpx.MockTransport(down))
        with pytest.raises(BrokerError, match="ConnectTimeout"):
            b.quote(CALL)

    def test_no_failure_path_puts_a_secret_in_its_message(self, fake, cred):
        b = SchwabBroker(lambda: cred, clock=lambda: NOW, transport=httpx.MockTransport(fake.handler))
        b.account_hash()
        fake.reject_all = True
        fake.refresh_ok = False
        for call in (lambda: b.quote(CALL), lambda: b.positions(), lambda: b.orders(),
                     lambda: b.place(intent()), lambda: b.cancel("1"), lambda: b.preview(intent())):
            with pytest.raises(BrokerError) as exc:
                call()
            assert_no_secret(str(exc.value))


# ── the entry point ──────────────────────────────────────────────────────

class TestMain:
    def test_schwab_and_mock_together_are_refused(self, tmp_path):
        from execd.__main__ import main
        assert main(["--mock", "--schwab", "--state-dir", str(tmp_path)]) == 2

    def test_schwab_without_a_vault_is_refused(self, tmp_path):
        from execd.__main__ import main
        assert main(["--schwab", "--vault", str(tmp_path / "none.json"),
                     "--state-dir", str(tmp_path)]) == 2

    def test_mock_unlock_cannot_arm_the_real_broker(self):
        from execd.__main__ import may_mock_unlock
        assert may_mock_unlock(SchwabBroker()) is False


# ── two apps, chosen by the endpoint family ──────────────────────────────
#
# st-p9mx. Steve has two Schwab registrations: app 1 carries market data and
# cannot trade (the portal refuses to add the Accounts and Trading product, so
# every /trader/v1 call on it answers 401 "no apiproduct match found"), app 2
# carries trading. The transport picks between them by reading the request
# path, and these tests pin that mapping by watching which bearer token
# actually reached which path — a behavioural check rather than a reading of
# the source, so a path computed at run time cannot slip past it.

MARKET_ACCESS = "ACCESS-MARKET"
MARKET_REFRESH = "REFRESH-MARKET"


def market_payload() -> dict[str, Any]:
    """A second credential, distinguishable from :func:`payload` in every field
    the transport touches."""
    p = payload()
    p["app"] = {"key": "MARKETKEY-VALUE", "secret": "MARKETSECRET-VALUE"}
    p["token"]["token"]["access_token"] = MARKET_ACCESS
    p["token"]["token"]["refresh_token"] = MARKET_REFRESH
    return p


@pytest.fixture
def two_app_broker(fake: FakeSchwab, cred: dict[str, Any]):
    """The production shape: a trading source and a market source, each with
    its own token. Returns (broker, market_payload)."""
    market = market_payload()
    fake.valid_access.add(MARKET_ACCESS)
    b = SchwabBroker(lambda: cred, market_credential_source=lambda: market,
                     clock=lambda: NOW, transport=httpx.MockTransport(fake.handler))
    return b, market


def bearers_by_family(fake: FakeSchwab) -> dict[str, set[str]]:
    """Every Authorization header the fake saw, grouped by endpoint family.
    The OAuth endpoint is excluded: it authenticates with the app pair, not a
    bearer, and it is covered by its own tests."""
    out: dict[str, set[str]] = {}
    for _method, path, _params, _body, auth in fake.calls:
        if path.startswith("/v1/oauth/"):
            continue
        family = "/trader/" if path.startswith("/trader/") else (
            "/marketdata/" if path.startswith("/marketdata/") else path)
        out.setdefault(family, set()).add(auth)
    return out


class TestAppForPath:
    def test_the_two_families_map_to_the_two_apps(self):
        assert S.app_for("/trader/v1/accounts/accountNumbers") is S.App.TRADING
        assert S.app_for("/marketdata/v1/quotes") is S.App.MARKET

    def test_an_unmapped_family_is_refused_not_defaulted(self):
        """The safe direction. A family added by hand next year stops on its
        first call and is given an app deliberately."""
        with pytest.raises(BrokerError) as exc:
            S.app_for("/v1/userpreference")
        assert "no Schwab app is mapped" in str(exc.value)

    def test_every_prefix_in_the_table_is_absolute(self):
        """A prefix without its leading slash would match nothing, silently."""
        for prefix, _app in S.APP_BY_PREFIX:
            assert prefix.startswith("/") and prefix.endswith("/")


class TestEndpointFamilyBindsTheApp:
    def test_market_data_carries_the_market_token(self, two_app_broker, fake):
        b, _market = two_app_broker
        b.quote("$SPX")
        b.chain("SPXW")
        families = bearers_by_family(fake)
        assert set(families) == {"/marketdata/"}
        assert families["/marketdata/"] == {f"Bearer {MARKET_ACCESS}"}

    def test_trader_calls_carry_the_trading_token(self, two_app_broker, fake):
        b, _market = two_app_broker
        b.account_hash()
        b.positions()
        b.orders()
        families = bearers_by_family(fake)
        assert set(families) == {"/trader/"}
        assert families["/trader/"] == {"Bearer ACCESS-STORED"}

    def test_a_mixed_run_never_crosses_the_two(self, two_app_broker, fake):
        """The one that matters: the same broker, both families, one sweep."""
        b, _market = two_app_broker
        b.quote("$SPX")
        b.positions()
        b.chain("SPXW")
        b.preview(intent())
        b.place(intent())
        b.orders()
        families = bearers_by_family(fake)
        assert families["/marketdata/"] == {f"Bearer {MARKET_ACCESS}"}
        assert families["/trader/"] == {"Bearer ACCESS-STORED"}
        assert MARKET_ACCESS not in "".join(
            auth for _m, path, _p, _b, auth in fake.calls if path.startswith("/trader/"))

    def test_the_market_token_never_reaches_a_trader_path_even_when_it_is_the_only_one(
            self, fake):
        """No market-only construction can produce a trader call: the trading
        source is unbound, so the call is refused rather than served by the
        credential that happens to be present."""
        market = market_payload()
        fake.valid_access.add(MARKET_ACCESS)
        b = SchwabBroker(market_credential_source=lambda: market,
                         clock=lambda: NOW, transport=httpx.MockTransport(fake.handler))
        assert b.quote("$SPX").symbol == "$SPX"
        with pytest.raises(BrokerError) as exc:
            b.positions()
        assert "trading credential" in str(exc.value)
        assert not [c for c in fake.calls if c[1].startswith("/trader/")]


class TestReadsWorkWhileLocked:
    """st-p8k8's open design point, settled by the split: the 07:00 premarket
    jobs run before Steve is awake to type a passphrase, and they only ever
    read market data."""

    def test_quote_and_chain_answer_with_the_trading_side_locked(self, fake):
        market = market_payload()
        fake.valid_access.add(MARKET_ACCESS)

        def locked() -> Any:
            raise Locked("no passphrase yet")

        b = SchwabBroker(locked, market_credential_source=lambda: market,
                         clock=lambda: NOW, transport=httpx.MockTransport(fake.handler))
        assert b.quote("$SPX").last > 0
        assert b.chain("SPXW")["root"] == "SPXW"

    def test_every_trader_call_still_refuses_while_locked(self, fake):
        market = market_payload()
        fake.valid_access.add(MARKET_ACCESS)

        def locked() -> Any:
            raise Locked("no passphrase yet")

        b = SchwabBroker(locked, market_credential_source=lambda: market,
                         clock=lambda: NOW, transport=httpx.MockTransport(fake.handler))
        for call in (b.positions, b.orders, b.account_hash,
                     lambda: b.preview(intent()), lambda: b.place(intent()),
                     lambda: b.cancel("4242")):
            with pytest.raises(BrokerError) as exc:
                call()
            assert "locked" in str(exc.value)
            assert_no_secret(str(exc.value))
        assert not [c for c in fake.calls if c[1].startswith("/trader/")]


class TestTwoWalls:
    def test_token_status_reports_both_apps(self, two_app_broker):
        b, _market = two_app_broker
        st = b.token_status()
        assert st["armed"] is True
        assert st["market"]["armed"] is True
        assert st["refresh_wall"] and st["market"]["refresh_wall"]
        assert_no_secret(json.dumps(st))

    def test_a_locked_trading_side_still_reports_the_market_wall(self, fake):
        market = market_payload()

        def locked() -> Any:
            raise Locked("no passphrase yet")

        b = SchwabBroker(locked, market_credential_source=lambda: market,
                         clock=lambda: NOW, transport=httpx.MockTransport(fake.handler))
        st = b.token_status()
        assert st["armed"] is False
        assert st["market"]["armed"] is True

    def test_each_app_caches_its_own_access_token(self, two_app_broker, fake):
        """One shared cache would hand the second app the first app's bearer."""
        b, _market = two_app_broker
        b.quote("$SPX")
        b.positions()
        assert b._access[S.App.MARKET][1] == MARKET_ACCESS
        assert b._access[S.App.TRADING][1] == "ACCESS-STORED"
