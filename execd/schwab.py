"""The Schwab transport — the service's one way to a real broker. [st-w2nw]

Stage 2 of the live execution service (epic st-5qjq, design §4). This module
is the second implementation of the :class:`~execd.broker.Broker` protocol and
the only module in the package that imports a transport. It speaks to the
Trader API and the market-data API over HTTPS with an access token in a
header, and to nothing else. It does not import the repo's hobbled ``schwab``
library; ``tests/execd/test_wall.py`` asserts that, and asserts that ``httpx``
appears here and nowhere else in the package.

**What is recorded and what is not.** The market-data shapes here (quotes for
an index, a future and an option; the chain) were recorded against the live
API on 2026-09-04 (``tests/fixtures/schwab/``, ``_capture.json`` says when and
in what market state). The Trader API shapes — account numbers, positions,
orders, preview, the 201-with-Location on place — are written against the
Accounts and Trading API specification, because the app registered for this
box answered every ``/trader`` call with HTTP 401 ``no apiproduct match found``
on the day this was written: the Accounts and Trading product was not on the
app. Every function that reads a Trader API body says which it is in its
docstring. ``scripts/record_schwab_shapes.py`` re-runs the recording once the
product is on the app, and the spec-derived fixtures in the tests are replaced
by the recorded ones in that commit. Until then a mis-named field is a
possibility this module is honest about rather than one it hides.

**The credential.** This class never holds one of its own. It is given a
callable — :meth:`execd.arming.Arming.credential` in production — and asks
for the credential on every call, so a lock on the arming state is a lock on
the transport with no second flag to forget. The payload it expects is the
vault's: ``{"app": {"key": ..., "secret": ...}, "token": {schwab-py wrapped}}``.
The access token it derives is cached in memory for as long as it is valid
and is refreshed from the refresh token when it is not; refreshing never
touches the vault, because the refresh token is the durable half and it does
not change on refresh. The weekly re-authorisation — a new refresh token —
happens on Steve's page (stage 3) with his passphrase present, through
:func:`authorize_url` and :func:`exchange`.

**What this module refuses to do.** It sends GET, POST and DELETE. There is no
PUT — Schwab's replace-order verb — anywhere in it, so a bounded chase
(st-kdaq) cannot arrive by a one-line change here; it arrives as a cancel and
a new intent through the bounds. It never retries a send: a POST that timed
out is reported as :class:`BrokerError` and the service's reconcile finds out
what the broker actually did. It never logs, prints, or puts in an exception
message any part of a token, a key, or an account identifier — the account
hash is replaced with ``<account>`` in every message that carries a path.
"""

from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Mapping

import httpx

from .arming import Locked
from .broker import (BrokerError, Fill, OrderResult, OrderStatus, Position, Preview,
                     Quote)
from .intent import OrderIntent, OrderType, Side

API = "https://api.schwabapi.com"
TOKEN_ENDPOINT = f"{API}/v1/oauth/token"
AUTHORIZE_ENDPOINT = f"{API}/v1/oauth/authorize"

#: The refresh token's life, per Schwab. Measured on this box more than once:
#: the file's ``creation_timestamp`` plus seven days is the wall.
REFRESH_TOKEN_LIFETIME = timedelta(days=7)

#: How close to expiry an access token is refreshed rather than used.
ACCESS_LEEWAY_S = 120

#: One request, one deadline. A broker that has not answered in this long is
#: reported as unreachable; the service never waits on a send it cannot see.
TIMEOUT_S = 15.0

#: How far back ``orders()`` looks. Two days: a resting order entered before
#: midnight is still the service's business the next morning (finding 9).
ORDERS_LOOKBACK = timedelta(days=2)

CONTRACT_MULTIPLIER = 100

_STATUS = {
    "FILLED": OrderStatus.FILLED,
    "REJECTED": OrderStatus.REJECTED,
    "CANCELED": OrderStatus.CANCELED,
    "EXPIRED": OrderStatus.CANCELED,
    "REPLACED": OrderStatus.CANCELED,
}
#: Every other status Schwab lists (ACCEPTED, WORKING, QUEUED, NEW, PENDING_*,
#: AWAITING_*, UNKNOWN) is an order the broker still holds: WORKING to us.


# ── credential ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Credential:
    """The vault payload, checked for shape. Never printed — ``repr`` is the
    class name."""

    app_key: str
    secret: str
    token: dict[str, Any]     # schwab-py wrapped: creation_timestamp + token

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return "Credential(<redacted>)"

    @property
    def refresh_token(self) -> str:
        return str(self.token["token"]["refresh_token"])

    @property
    def created_at(self) -> datetime:
        return datetime.fromtimestamp(int(self.token["creation_timestamp"]), tz=timezone.utc)

    @property
    def refresh_wall(self) -> datetime:
        """When the refresh token dies and only Steve's browser brings it back."""
        return self.created_at + REFRESH_TOKEN_LIFETIME

    @classmethod
    def from_payload(cls, payload: Any) -> "Credential":
        """Shape check only. Names the missing field, never a value."""
        if not isinstance(payload, Mapping):
            raise ValueError("credential payload is not a mapping")
        app = payload.get("app")
        token = payload.get("token")
        if not isinstance(app, Mapping) or not app.get("key") or not app.get("secret"):
            raise ValueError("credential payload has no app.key / app.secret")
        if not isinstance(token, Mapping) or "creation_timestamp" not in token:
            raise ValueError("credential payload token is not in the wrapped shape "
                             "(creation_timestamp + token)")
        inner = token.get("token")
        if not isinstance(inner, Mapping) or not inner.get("refresh_token"):
            raise ValueError("credential payload token carries no refresh_token")
        return cls(str(app["key"]), str(app["secret"]), dict(token))


# ── OAuth: the two calls a re-authorisation needs ─────────────────────────


def authorize_url(app_key: str, callback_url: str, state: str) -> str:
    """The link Steve's page shows him. He logs in at Schwab; Schwab sends his
    browser to ``callback_url`` with a code; he pastes that URL back."""
    q = httpx.QueryParams({"client_id": app_key, "redirect_uri": callback_url,
                           "response_type": "code", "state": state})
    return f"{AUTHORIZE_ENDPOINT}?{q}"


def code_from_received_url(received_url: str, expected_state: str | None = None) -> str:
    """Pull the authorisation code out of the pasted redirect URL.

    Schwab's codes end in ``@`` and arrive percent-encoded; the query parser
    decodes them. A state mismatch is refused rather than ignored — it is the
    one defence the flow has against a pasted URL that came from somewhere
    else. (``httpx.URL`` rather than ``urllib``: the wall test bans the whole
    ``urllib`` root so that ``urllib.request`` can never arrive by accident.)"""
    try:
        query = httpx.URL(received_url.strip()).params
    except (httpx.InvalidURL, TypeError) as exc:
        raise ValueError(f"the pasted text is not a URL: {exc}") from None
    code = query.get("code")
    if not code:
        raise ValueError("the pasted URL carries no code= parameter")
    if expected_state is not None and query.get("state") != expected_state:
        raise ValueError("the pasted URL's state does not match the link that was shown")
    return code


def _basic(app_key: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{app_key}:{secret}".encode()).decode()


def _wrap(new: Mapping[str, Any], creation_timestamp: int,
          previous_refresh: str | None = None, now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    inner = dict(new)
    if "access_token" not in inner:
        raise BrokerError("schwab token endpoint answered without an access_token")
    if not inner.get("refresh_token"):
        if previous_refresh is None:
            raise BrokerError("schwab token endpoint answered without a refresh_token")
        inner["refresh_token"] = previous_refresh
    inner["expires_at"] = int(now) + int(inner.get("expires_in", 1800))
    return {"creation_timestamp": int(creation_timestamp), "token": inner}


def exchange(client: httpx.Client, app_key: str, secret: str, callback_url: str,
             code: str, *, now: float | None = None) -> dict[str, Any]:
    """Trade an authorisation code for a fresh token. Returns the wrapped shape
    with ``creation_timestamp`` = now, which is what starts the seven-day clock.
    The caller (the page, with Steve's passphrase in hand) stores it."""
    r = _post_token(client, app_key, secret,
                    {"grant_type": "authorization_code", "code": code,
                     "redirect_uri": callback_url})
    return _wrap(r, int(now if now is not None else time.time()), now=now)


def refresh(client: httpx.Client, credential: Credential, *,
            now: float | None = None) -> dict[str, Any]:
    """A new access token from the refresh token. ``creation_timestamp`` is
    preserved: refreshing does not move the seven-day wall."""
    r = _post_token(client, credential.app_key, credential.secret,
                    {"grant_type": "refresh_token",
                     "refresh_token": credential.refresh_token})
    return _wrap(r, int(credential.token["creation_timestamp"]),
                 previous_refresh=credential.refresh_token, now=now)


def _post_token(client: httpx.Client, app_key: str, secret: str,
                form: Mapping[str, str]) -> dict[str, Any]:
    try:
        r = client.post(TOKEN_ENDPOINT, data=dict(form),
                        headers={"Authorization": _basic(app_key, secret),
                                 "Content-Type": "application/x-www-form-urlencoded"})
    except httpx.HTTPError as exc:
        raise BrokerError(f"schwab token endpoint unreachable: {type(exc).__name__}") from None
    if r.status_code != 200:
        raise BrokerError(f"schwab token endpoint refused the {form.get('grant_type')} "
                          f"grant: HTTP {r.status_code} {_error_detail(r)}")
    try:
        body = r.json()
    except ValueError:
        raise BrokerError("schwab token endpoint answered 200 with a non-JSON body") from None
    if not isinstance(body, dict):
        raise BrokerError("schwab token endpoint answered 200 with a non-object body")
    return body


def _error_detail(r: httpx.Response) -> str:
    """Schwab's error body is ``{"errors": [{"title", "detail", ...}]}`` on the
    Trader API and ``{"error", "error_description"}`` from OAuth. Neither
    carries a token; both are safe to quote, truncated."""
    try:
        body = r.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    if isinstance(body.get("errors"), list) and body["errors"]:
        first = body["errors"][0]
        if isinstance(first, dict):
            return str(first.get("detail") or first.get("title") or "")[:200]
    if body.get("error_description") or body.get("error"):
        return str(body.get("error_description") or body.get("error"))[:200]
    if body.get("message"):
        return str(body["message"])[:200]
    return ""


# ── the broker ───────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ms(ts: Any, fallback: datetime) -> datetime:
    try:
        if ts is None or int(ts) <= 0:
            return fallback
        return datetime.fromtimestamp(int(ts) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return fallback


def _iso(ts: Any, fallback: datetime) -> datetime:
    if not ts:
        return fallback
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso_z(dt: datetime) -> str:
    """``yyyy-MM-dd'T'HH:mm:ss.SSSZ`` — the one form the orders query accepts."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def format_price(pts: float) -> str:
    """Two decimals, half-up, as a string. Schwab reads prices as strings, and
    the library's float truncation turns 2.07 into "2.06" — a limit one tick
    under the one the bounds approved. Half-up on the decimal text does not."""
    return str(Decimal(str(pts)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_order(intent: OrderIntent) -> dict[str, Any]:
    """One single-leg option order, in the Trader API's request shape.

    Spec-derived (OrderRequest / OrderLegCollection). Session NORMAL and
    duration DAY are the only values this service sends: nothing it places may
    outlive the session, and nothing trades outside regular hours."""
    body: dict[str, Any] = {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": intent.order_type.value,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [{
            "instruction": intent.side.value,
            "quantity": int(intent.qty),
            "instrument": {"symbol": intent.symbol, "assetType": "OPTION"},
        }],
    }
    if intent.order_type is OrderType.LIMIT:
        if intent.limit is None:
            raise ValueError("a LIMIT intent needs a limit")
        body["price"] = format_price(intent.limit)
    elif intent.order_type is OrderType.STOP:
        if intent.stop_price is None:
            raise ValueError("a STOP intent needs a stop_price")
        body["stopPrice"] = format_price(intent.stop_price)
    return body


class SchwabBroker:
    """The :class:`~execd.broker.Broker` protocol over the Trader API.

    :param credential_source: returns the vault payload, or raises
        :class:`~execd.arming.Locked`. Bound after construction with
        :meth:`bind` in production because the service owns the arming state
        and is built after its broker.
    :param underlying: the index whose options this service trades. Positions
        in anything else are not this service's to see — see :meth:`positions`.
    :param transport: an ``httpx`` transport, for tests. Production uses the
        default.
    """

    def __init__(self, credential_source: Callable[[], Any] | None = None, *,
                 clock: Callable[[], datetime] = _utcnow,
                 underlying: str = "$SPX", account_index: int = 0,
                 transport: httpx.BaseTransport | None = None,
                 timeout_s: float = TIMEOUT_S) -> None:
        self.credential_source = credential_source
        self.clock = clock
        self.underlying = underlying
        self.account_index = account_index
        self._client = httpx.Client(base_url=API, timeout=timeout_s, transport=transport)
        self._lock = threading.RLock()
        # in-memory only, keyed on the refresh token they were derived from
        self._access: tuple[str, str, int] | None = None   # (refresh, access, expires_at)
        self._hash: tuple[str, str] | None = None          # (refresh, account hash)
        #: positions the last sweep saw and did not report, by asset type —
        #: for the status page, so an excluded holding is visible, not silent.
        self.excluded_positions: dict[str, int] = {}

    def bind(self, arming: Any) -> "SchwabBroker":
        self.credential_source = arming.credential
        return self

    def close(self) -> None:
        self._client.close()

    # ── credential and access token ──────────────────────────────────────
    def _credential(self) -> Credential:
        if self.credential_source is None:
            raise BrokerError("no credential source is bound to the Schwab transport")
        try:
            payload = self.credential_source()
        except Locked:
            raise BrokerError("the service is locked — no credential in memory") from None
        try:
            return Credential.from_payload(payload)
        except ValueError as exc:
            raise BrokerError(f"the credential in memory is unusable: {exc}") from None

    def _bearer(self, cred: Credential, *, force: bool = False) -> str:
        now = int(time.time())
        with self._lock:
            cached = self._access
            if (not force and cached is not None and cached[0] == cred.refresh_token
                    and cached[2] - now > ACCESS_LEEWAY_S):
                return cached[1]
            inner = cred.token.get("token") or {}
            stored_access = inner.get("access_token")
            stored_exp = int(inner.get("expires_at") or 0)
            if (not force and stored_access and stored_exp - now > ACCESS_LEEWAY_S
                    and (cached is None or cached[0] != cred.refresh_token)):
                # A fresh unlock whose stored access token is still good.
                self._access = (cred.refresh_token, str(stored_access), stored_exp)
                return str(stored_access)
            if cred.refresh_wall <= datetime.fromtimestamp(now, tz=timezone.utc):
                raise BrokerError("the refresh token is past its seven-day wall — "
                                  "re-authorise on the page")
            wrapped = refresh(self._client, cred, now=now)
            self._access = (cred.refresh_token, str(wrapped["token"]["access_token"]),
                            int(wrapped["token"]["expires_at"]))
            return self._access[1]

    def token_status(self) -> dict[str, Any]:
        """For the status page: when the wall is, and whether an access token
        is in hand. No values."""
        try:
            cred = self._credential()
        except BrokerError as exc:
            return {"armed": False, "detail": str(exc)}
        cached = self._access
        return {
            "armed": True,
            "refresh_wall": cred.refresh_wall.isoformat(),
            "refresh_wall_in_s": int((cred.refresh_wall - self.clock()).total_seconds()),
            "access_cached": bool(cached and cached[0] == cred.refresh_token),
            "access_expires_at": (datetime.fromtimestamp(cached[2], tz=timezone.utc).isoformat()
                                  if cached and cached[0] == cred.refresh_token else None),
        }

    # ── requests ─────────────────────────────────────────────────────────
    def _scrub(self, text: str) -> str:
        h = self._hash
        return text.replace(h[1], "<account>") if h else text

    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None,
                 json: Any = None, ok: tuple[int, ...] = (200,)) -> httpx.Response:
        """One call, with one retry on a 401 after a forced refresh. Nothing
        else is retried — a send that timed out is reported, not repeated."""
        assert method in ("GET", "POST", "DELETE"), method
        cred = self._credential()
        token = self._bearer(cred)
        r = self._send(method, path, token, params, json)
        if r.status_code == 401 and method == "GET":
            # A GET is safe to repeat. A POST is not — a 401 there is reported,
            # and the service's reconcile discovers whether anything went in.
            token = self._bearer(cred, force=True)
            r = self._send(method, path, token, params, json)
        if r.status_code not in ok:
            raise BrokerError(f"schwab {method} {self._scrub(path)}: HTTP {r.status_code} "
                              f"{_error_detail(r)}".rstrip())
        return r

    def _send(self, method: str, path: str, token: str,
              params: Mapping[str, Any] | None, json: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            return self._client.request(method, path, params=params, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise BrokerError(f"schwab {method} {self._scrub(path)}: "
                              f"{type(exc).__name__}") from None

    @staticmethod
    def _json(r: httpx.Response, what: str) -> Any:
        try:
            return r.json()
        except ValueError:
            raise BrokerError(f"schwab answered {what} with a non-JSON body") from None

    def account_hash(self) -> str:
        """Spec-derived: ``GET /trader/v1/accounts/accountNumbers`` →
        ``[{accountNumber, hashValue}]``. Cached per credential; the plain
        number is never kept."""
        cred = self._credential()
        with self._lock:
            if self._hash and self._hash[0] == cred.refresh_token:
                return self._hash[1]
        body = self._json(self._request("GET", "/trader/v1/accounts/accountNumbers"),
                          "accountNumbers")
        if not isinstance(body, list) or len(body) <= self.account_index:
            raise BrokerError(f"schwab reported {len(body) if isinstance(body, list) else 0} "
                              f"account(s); this service is configured for index "
                              f"{self.account_index}")
        entry = body[self.account_index]
        h = str(entry.get("hashValue") or "")
        if not h:
            raise BrokerError("schwab accountNumbers entry carries no hashValue")
        with self._lock:
            self._hash = (cred.refresh_token, h)
        return h

    # ── market data (recorded 2026-09-04) ────────────────────────────────
    def quote(self, symbol: str) -> Quote:
        """Recorded: ``GET /marketdata/v1/quotes?symbols=`` →
        ``{symbol: {quote: {bidPrice, askPrice, lastPrice, quoteTime, tradeTime}}}``.
        An index carries no bid/ask (recorded: ``$SPX`` has ``lastPrice`` and
        ``tradeTime`` only), so its Quote is last on both sides, stamped with
        the trade time — which is what makes a pre-open index quote read as
        stale, correctly."""
        body = self._json(self._request("GET", "/marketdata/v1/quotes",
                                        params={"symbols": symbol}), "quotes")
        entry = body.get(symbol) if isinstance(body, dict) else None
        if not isinstance(entry, dict) or "quote" not in entry:
            detail = ""
            if isinstance(body, dict) and isinstance(body.get("errors"), dict):
                detail = f": {body['errors']}"[:200]
            raise BrokerError(f"no quote for {symbol}{detail}")
        q = entry["quote"]
        now = self.clock()
        last = float(q.get("lastPrice") or 0.0)
        bid = q.get("bidPrice")
        ask = q.get("askPrice")
        if bid is None or ask is None:
            return Quote(symbol=symbol, bid=last, ask=last, last=last,
                         as_of=_ms(q.get("tradeTime"), now))
        return Quote(symbol=symbol, bid=float(bid), ask=float(ask), last=last,
                     as_of=_ms(q.get("quoteTime") or q.get("tradeTime"), now))

    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]:
        """Recorded: ``GET /marketdata/v1/chains`` → ``{callExpDateMap:
        {"YYYY-MM-DD:dte": {"strike": [contract]}}, putExpDateMap, ...}``.
        Contracts carry ``optionRoot`` (``SPX`` or ``SPXW`` share one chain),
        so the map is filtered to the root asked for; the envelope is kept."""
        params: dict[str, Any] = {"symbol": self.underlying, "contractType": "ALL",
                                  "strategy": "SINGLE"}
        if expiry:
            params["fromDate"] = params["toDate"] = expiry
        else:
            today = self.clock().date().isoformat()
            params["fromDate"] = today
            params["toDate"] = (self.clock().date() + timedelta(days=7)).isoformat()
        body = self._json(self._request("GET", "/marketdata/v1/chains", params=params), "chains")
        if not isinstance(body, dict):
            raise BrokerError("schwab chain body is not an object")
        if body.get("status") not in (None, "SUCCESS"):
            raise BrokerError(f"schwab chain for {self.underlying}: status {body.get('status')}")
        want = root.upper()
        out = dict(body)
        for key in ("callExpDateMap", "putExpDateMap"):
            kept: dict[str, Any] = {}
            for exp, strikes in (body.get(key) or {}).items():
                filtered = {k: [c for c in v if str(c.get("optionRoot", want)).upper() == want]
                            for k, v in strikes.items()}
                filtered = {k: v for k, v in filtered.items() if v}
                if filtered:
                    kept[exp] = filtered
            out[key] = kept
        out["root"] = want
        return out

    # ── orders (spec-derived until the product is on the app) ────────────
    def preview(self, intent: OrderIntent) -> Preview:
        """Spec-derived: ``POST .../previewOrder`` → ``PreviewOrder`` with
        ``orderStrategy.orderBalance.{orderValue, projectedCommission}`` and
        ``orderValidationResult.{rejects, warns, alerts, reviews}``. A reject
        anywhere is ``accepted=False`` with every message carried."""
        h = self.account_hash()
        body = self._json(self._request("POST", f"/trader/v1/accounts/{h}/previewOrder",
                                        json=build_order(intent)), "previewOrder")
        if not isinstance(body, dict):
            raise BrokerError("schwab preview body is not an object")
        strategy = body.get("orderStrategy") or {}
        balance = strategy.get("orderBalance") or {}
        validation = body.get("orderValidationResult") or {}
        messages: list[str] = []
        rejected = False
        for bucket in ("rejects", "reviews", "warns", "alerts"):
            for item in validation.get(bucket) or []:
                if isinstance(item, dict):
                    text = str(item.get("message") or item.get("activityMessage")
                               or item.get("validationRuleName") or bucket)
                    messages.append(f"{bucket[:-1]}: {text}")
                    if bucket == "rejects":
                        rejected = True
        price = intent.limit if intent.order_type is OrderType.LIMIT else intent.stop_price
        legs = strategy.get("orderLegs") or []
        if price is None and legs and isinstance(legs[0], dict):
            leg = legs[0]
            price = leg.get("askPrice") if intent.side is Side.BUY_TO_OPEN else leg.get("bidPrice")
        cost = balance.get("orderValue")
        if cost is None:
            cost = (float(price) * CONTRACT_MULTIPLIER * intent.qty) if price is not None else 0.0
        return Preview(
            symbol=intent.symbol, side=intent.side, qty=intent.qty,
            order_type=intent.order_type, price=float(price) if price is not None else None,
            cost_usd=round(abs(float(cost)), 2),
            commission_usd=round(float(balance.get("projectedCommission") or 0.0), 2),
            accepted=not rejected, messages=tuple(messages),
        )

    def place(self, intent: OrderIntent) -> OrderResult:
        """Spec-derived: ``POST .../orders`` → 201, empty body, the new order's
        id in the ``Location`` header; then ``GET .../orders/{id}`` for what
        the broker did with it. A 400 is the broker's rejection and is
        returned as one; anything else non-2xx is :class:`BrokerError`.

        A 201 with no Location is treated as an order that exists and cannot
        be named: WORKING under a synthetic id, loudly, so the service holds
        the slot and reconcile finds it by the broker's own listing rather than
        the service believing nothing went in."""
        h = self.account_hash()
        cred = self._credential()
        token = self._bearer(cred)
        path = f"/trader/v1/accounts/{h}/orders"
        r = self._send("POST", path, token, None, build_order(intent))
        if r.status_code == 400:
            return OrderResult(
                order_id=f"rejected:{intent.intent_id}", status=OrderStatus.REJECTED,
                symbol=intent.symbol, side=intent.side, qty=intent.qty,
                order_type=intent.order_type,
                price=intent.limit if intent.order_type is OrderType.LIMIT else intent.stop_price,
                submitted_at=self.clock(), message=_error_detail(r) or "rejected (HTTP 400)")
        if r.status_code not in (200, 201):
            raise BrokerError(f"schwab POST {self._scrub(path)}: HTTP {r.status_code} "
                              f"{_error_detail(r)}".rstrip())
        order_id = _order_id_from_location(r.headers.get("Location"))
        if order_id is None:
            return OrderResult(
                order_id=f"unnamed:{intent.intent_id}", status=OrderStatus.WORKING,
                symbol=intent.symbol, side=intent.side, qty=intent.qty,
                order_type=intent.order_type,
                price=intent.limit if intent.order_type is OrderType.LIMIT else intent.stop_price,
                submitted_at=self.clock(),
                message="placed (HTTP 201) but the broker returned no order id — "
                        "reconcile must find it in the broker's listing")
        try:
            return self._get_order(h, order_id)
        except BrokerError as exc:
            return OrderResult(
                order_id=order_id, status=OrderStatus.WORKING,
                symbol=intent.symbol, side=intent.side, qty=intent.qty,
                order_type=intent.order_type,
                price=intent.limit if intent.order_type is OrderType.LIMIT else intent.stop_price,
                submitted_at=self.clock(),
                message=f"placed; the follow-up read failed ({exc}) — status unknown until reconcile")

    def cancel(self, order_id: str) -> OrderResult:
        """Spec-derived: ``DELETE .../orders/{id}`` → 200 empty; then a read.
        A DELETE the broker refuses (already filled, already gone) is not an
        error here: the read that follows says what actually happened, which
        is the race the stop logic is written to survive."""
        h = self.account_hash()
        cred = self._credential()
        token = self._bearer(cred)
        path = f"/trader/v1/accounts/{h}/orders/{order_id}"
        r = self._send("DELETE", path, token, None, None)
        if r.status_code in (401, 403) or r.status_code >= 500:
            raise BrokerError(f"schwab DELETE {self._scrub(path)}: HTTP {r.status_code} "
                              f"{_error_detail(r)}".rstrip())
        return self._get_order(h, order_id)

    def orders(self) -> list[OrderResult]:
        return [self._to_result(o) for o in self._orders_raw()]

    def positions(self) -> list[Position]:
        """Spec-derived: ``GET .../accounts/{hash}?fields=positions`` →
        ``{securitiesAccount: {positions: [{longQuantity, shortQuantity,
        averagePrice, instrument: {assetType, symbol, underlyingSymbol}}]}}``.

        Only options on ``underlying`` are reported. The service adopts any
        position it is shown so that flatten reaches it (st-v7oa); a share
        position in the same account is not this service's to flatten, so it
        is not shown. What was left out is counted in
        :attr:`excluded_positions` for the status page."""
        h = self.account_hash()
        body = self._json(self._request("GET", f"/trader/v1/accounts/{h}",
                                        params={"fields": "positions"}), "positions")
        acct = body.get("securitiesAccount") if isinstance(body, dict) else None
        if not isinstance(acct, dict):
            raise BrokerError("schwab account body carries no securitiesAccount")
        out: list[Position] = []
        excluded: dict[str, int] = {}
        want = self.underlying.lstrip("$").upper()
        for p in acct.get("positions") or []:
            if not isinstance(p, dict):
                continue
            inst = p.get("instrument") or {}
            asset = str(inst.get("assetType") or "UNKNOWN")
            under = str(inst.get("underlyingSymbol") or "").lstrip("$").upper()
            if asset != "OPTION" or (under and under != want):
                excluded[asset] = excluded.get(asset, 0) + 1
                continue
            qty = int(round(float(p.get("longQuantity") or 0.0) - float(p.get("shortQuantity") or 0.0)))
            if qty == 0:
                continue
            out.append(Position(symbol=str(inst.get("symbol") or ""), qty=qty,
                                avg_price=float(p.get("averagePrice") or 0.0)))
        self.excluded_positions = excluded
        return out

    def fills_since(self, since: datetime) -> list[Fill]:
        """Spec-derived: each order's ``orderActivityCollection`` entries with
        ``activityType == EXECUTION`` carry ``executionLegs[{price, quantity,
        time}]``. One Fill per execution leg after ``since``."""
        fills: list[Fill] = []
        for o in self._orders_raw():
            symbol, side = _leg_symbol_side(o)
            for act in o.get("orderActivityCollection") or []:
                if not isinstance(act, dict) or act.get("activityType") != "EXECUTION":
                    continue
                for leg in act.get("executionLegs") or []:
                    if not isinstance(leg, dict):
                        continue
                    at = _iso(leg.get("time"), self.clock())
                    if at <= since:
                        continue
                    qty = int(round(float(leg.get("quantity") or 0.0)))
                    if qty <= 0:
                        continue
                    fills.append(Fill(order_id=str(o.get("orderId")), symbol=symbol, side=side,
                                      qty=qty, price=float(leg.get("price") or 0.0), at=at))
        fills.sort(key=lambda f: f.at)
        return fills

    # ── internals ────────────────────────────────────────────────────────
    def _orders_raw(self) -> list[dict[str, Any]]:
        """Spec-derived: ``GET .../orders?fromEnteredTime&toEnteredTime`` →
        ``[Order]``. Both times are required by the API."""
        h = self.account_hash()
        now = self.clock()
        body = self._json(self._request(
            "GET", f"/trader/v1/accounts/{h}/orders",
            params={"fromEnteredTime": _iso_z(now - ORDERS_LOOKBACK),
                    "toEnteredTime": _iso_z(now + timedelta(days=1))}), "orders")
        if not isinstance(body, list):
            raise BrokerError("schwab orders body is not a list")
        return [o for o in body if isinstance(o, dict)]

    def _get_order(self, account_hash: str, order_id: str) -> OrderResult:
        body = self._json(self._request("GET", f"/trader/v1/accounts/{account_hash}/orders/{order_id}"),
                          "order")
        if not isinstance(body, dict):
            raise BrokerError("schwab order body is not an object")
        return self._to_result(body)

    def _to_result(self, o: Mapping[str, Any]) -> OrderResult:
        """Spec-derived ``Order`` → :class:`OrderResult`."""
        symbol, side = _leg_symbol_side(o)
        raw_status = str(o.get("status") or "UNKNOWN")
        status = _STATUS.get(raw_status, OrderStatus.WORKING)
        raw_type = str(o.get("orderType") or "")
        if raw_type in ("LIMIT", "MARKET", "STOP"):
            otype = OrderType(raw_type)
        elif raw_type.startswith("STOP"):
            otype = OrderType.STOP
        else:
            otype = OrderType.LIMIT if o.get("price") is not None else OrderType.MARKET
        price = o.get("price") if otype is not OrderType.STOP else o.get("stopPrice")
        filled = int(round(float(o.get("filledQuantity") or 0.0)))
        fill_price = _avg_fill_price(o)
        legs = o.get("orderLegCollection") or []
        qty = int(round(float(o.get("quantity") or (legs[0].get("quantity") if legs else 0) or 0)))
        message = raw_status if status is OrderStatus.WORKING and raw_status != "WORKING" else ""
        if status is OrderStatus.REJECTED:
            message = str(o.get("statusDescription") or o.get("tag") or "rejected")
        return OrderResult(
            order_id=str(o.get("orderId")), status=status, symbol=symbol, side=side,
            qty=qty, order_type=otype,
            price=float(price) if price is not None else None,
            filled_qty=filled, fill_price=fill_price,
            submitted_at=_iso(o.get("enteredTime"), self.clock()), message=message,
        )


def _order_id_from_location(location: str | None) -> str | None:
    if not location:
        return None
    tail = location.rstrip("/").rsplit("/", 1)[-1]
    return tail if tail.isdigit() else None


def _leg_symbol_side(o: Mapping[str, Any]) -> tuple[str, Side]:
    legs = o.get("orderLegCollection") or []
    leg = legs[0] if legs and isinstance(legs[0], dict) else {}
    inst = leg.get("instrument") or {}
    symbol = str(inst.get("symbol") or "")
    instruction = str(leg.get("instruction") or "")
    side = Side.BUY_TO_OPEN if instruction.startswith("BUY") else Side.SELL_TO_CLOSE
    return symbol, side


def _avg_fill_price(o: Mapping[str, Any]) -> float | None:
    total_qty = 0.0
    total_val = 0.0
    for act in o.get("orderActivityCollection") or []:
        if not isinstance(act, dict) or act.get("activityType") != "EXECUTION":
            continue
        for leg in act.get("executionLegs") or []:
            if not isinstance(leg, dict):
                continue
            q = float(leg.get("quantity") or 0.0)
            p = leg.get("price")
            if q > 0 and p is not None:
                total_qty += q
                total_val += q * float(p)
    if total_qty <= 0:
        return None
    return round(total_val / total_qty, 4)
