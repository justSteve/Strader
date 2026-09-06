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

**Two apps, two credentials, chosen by the endpoint family** (st-p9mx). Steve
has two Schwab registrations. App 1 carries market data and *cannot trade* —
developer.schwab.com refuses to add the Accounts and Trading product to it, so
every ``/trader/v1`` call on it answers 401 ``no apiproduct match found``, and
Steve confirmed on 2026-09-05 that the refusal is permanent. App 2 carries
Accounts and Trading. So this module holds two credential sources and picks
between them with :func:`app_for`, which reads the *request path* — there is no
parameter saying which app to use, because a parameter is the thing that can
drift. An unmapped path is refused rather than defaulted, so a new endpoint
family fails loudly on its first call instead of quietly borrowing whichever
credential was to hand.

That split is what lets the two live at different tiers. The trading credential
is the vault's, held by :class:`~execd.arming.Arming`, and LOCKED means it is
not in memory. The market credential needs no such protection — it cannot place
an order, by Schwab's enforcement rather than our promise — so the service may
hold it from start-up, and :meth:`quote` and :meth:`chain` answer while the
service is LOCKED. That is what settles st-p8k8's open question about the 07:00
premarket jobs, which run before Steve is awake to type a passphrase. Schwab's
401 is an observation with a date on it, not a guarantee, so the code holds the
same boundary independently: nothing routes a ``/trader/v1`` call to the market
credential, and ``tests/execd/test_schwab.py`` pins the mapping by watching
which bearer token reaches which path.

**The credential.** This class never holds one of its own. It is given
callables — :meth:`execd.arming.Arming.credential` for trading in production —
and asks on every call, so a lock on the arming state is a lock on the trading
half with no second flag to forget. The payload each expects is the vault's:
``{"app": {"key": ..., "secret": ...}, "token": {schwab-py wrapped}}``. The
access token derived from each is cached in memory per app for as long as it is
valid and refreshed from that app's refresh token when it is not; refreshing
never touches the vault, because the refresh token is the durable half and it
does not change on refresh. The weekly re-authorisation — a new refresh token —
happens on Steve's page (stage 3) with his passphrase present, through
:func:`authorize_url` and :func:`exchange`. Two grants mean two seven-day walls:
they are re-authorised in one sitting so they expire on the same day, and
:meth:`token_status` reports both.

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
from enum import Enum
from typing import Any, Callable, Mapping

import httpx

from .arming import Locked
from .broker import (BrokerError, Fill, OrderLeg, OrderResult, OrderStatus, Position,
                     Preview, Quote)
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


class App(str, Enum):
    """Which of Steve's two Schwab registrations a call belongs to."""

    MARKET = "market"
    TRADING = "trading"


#: Path prefix → app. The whole mapping, in one place, so the answer to "which
#: app does this call use" is a lookup rather than a reading of call sites.
APP_BY_PREFIX: tuple[tuple[str, App], ...] = (
    ("/trader/", App.TRADING),
    ("/marketdata/", App.MARKET),
)


#: The vault payload's version. v1 was one app at the top level
#: (``{"app": ..., "token": ...}``); v2 names the app it belongs to, because
#: there are two of them now (st-p9mx).
VAULT_VERSION = 2


def trading_payload(vault_payload: Any) -> Any:
    """The trading credential out of a vault payload, v1 or v2.

    A vault Steve wrote before the split keeps opening: v1 had exactly one
    credential and it was the trading one, so an envelope with no ``trading``
    key *is* the trading credential. The market credential is deliberately not
    in here — a credential that must load without the passphrase cannot live
    behind it."""
    if isinstance(vault_payload, Mapping) and "trading" in vault_payload:
        return vault_payload["trading"]
    return vault_payload


def app_for(path: str) -> App:
    """The app a request path belongs to, or a refusal.

    Derived, never passed in: acceptance (b) of st-p9mx is that a call cannot
    drift to the wrong app, and an argument is precisely what drifts. An
    unmapped family raises rather than falling back — a ``/v1/userpreference``
    added by hand next year should stop on its first call and be given an app
    deliberately, not inherit one by accident."""
    for prefix, app in APP_BY_PREFIX:
        if path.startswith(prefix):
            return app
    raise BrokerError(
        f"no Schwab app is mapped to {path} — every request family must be "
        f"given one deliberately (execd.schwab.APP_BY_PREFIX)"
    )


_STATUS = {
    "FILLED": OrderStatus.FILLED,
    "REJECTED": OrderStatus.REJECTED,
    "CANCELED": OrderStatus.CANCELED,
    "EXPIRED": OrderStatus.CANCELED,
    "REPLACED": OrderStatus.CANCELED,
}
#: Every other status Schwab lists (ACCEPTED, WORKING, QUEUED, NEW, PENDING_*,
#: AWAITING_*, UNKNOWN) is an order the broker still holds: WORKING to us.

_ORDER_TYPES = {
    "LIMIT": OrderType.LIMIT,
    "MARKET": OrderType.MARKET,
    "STOP": OrderType.STOP,
    "NET_CREDIT": OrderType.NET_CREDIT,
    "NET_DEBIT": OrderType.NET_DEBIT,
}
#: Anything else beginning STOP (STOP_LIMIT, TRAILING_STOP) reads as STOP. Only
#: after both of those does the price-shaped guess run — until st-ilp9 the
#: guess ran for NET_CREDIT and NET_DEBIT too, and called them LIMIT [st-ilp9].


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

    :param credential_source: the TRADING credential — returns the vault
        payload, or raises :class:`~execd.arming.Locked`. Bound after
        construction with :meth:`bind` in production because the service owns
        the arming state and is built after its broker.
    :param market_credential_source: the MARKET credential, held from start-up
        and outside the arming lock (see the module docstring). When it is not
        given, market calls fall back to ``credential_source`` — which is what
        a one-app test or a mock wants, and is safe in the only direction that
        matters: nothing ever routes a ``/trader/v1`` call to the market
        credential, whatever is or is not bound.
    :param underlying: the index whose options this service trades. Positions
        in anything else are not this service's to see — see :meth:`positions`.
    :param transport: an ``httpx`` transport, for tests. Production uses the
        default.
    """

    def __init__(self, credential_source: Callable[[], Any] | None = None, *,
                 market_credential_source: Callable[[], Any] | None = None,
                 clock: Callable[[], datetime] = _utcnow,
                 underlying: str = "$SPX", account_index: int = 0,
                 transport: httpx.BaseTransport | None = None,
                 timeout_s: float = TIMEOUT_S) -> None:
        self.credential_source = credential_source
        self.market_credential_source = market_credential_source
        self.clock = clock
        self.underlying = underlying
        self.account_index = account_index
        self._client = httpx.Client(base_url=API, timeout=timeout_s, transport=transport)
        self._lock = threading.RLock()
        # in-memory only, per app, keyed on the refresh token they were derived
        # from: two apps mean two access tokens with two lifetimes.
        self._access: dict[App, tuple[str, str, int]] = {}   # app → (refresh, access, expires_at)
        self._hash: tuple[str, str] | None = None            # (refresh, account hash)
        #: positions the last sweep saw and did not report, by asset type —
        #: for the status page, so an excluded holding is visible, not silent.
        self.excluded_positions: dict[str, int] = {}

    def bind(self, arming: Any) -> "SchwabBroker":
        """Wire the TRADING credential to the arming state. The market
        credential is deliberately not touched: it is held from start-up so the
        premarket reads work while the service is LOCKED."""
        self.credential_source = arming.credential
        return self

    def bind_market(self, source: Callable[[], Any]) -> "SchwabBroker":
        """Wire the market credential. Separate from :meth:`bind` because these
        two are wired at different moments by different things — this one at
        start-up from a file the service user owns, the other from the vault
        when Steve enters his passphrase."""
        self.market_credential_source = source
        return self

    def close(self) -> None:
        self._client.close()

    # ── credential and access token ──────────────────────────────────────
    def _source_for(self, app: App) -> Callable[[], Any] | None:
        if app is App.TRADING:
            return self.credential_source
        return self.market_credential_source or self.credential_source

    def _credential(self, app: App = App.TRADING) -> Credential:
        source = self._source_for(app)
        if source is None:
            raise BrokerError(f"no {app.value} credential source is bound to the "
                              f"Schwab transport")
        try:
            payload = source()
        except Locked:
            raise BrokerError(f"the service is locked — no {app.value} credential "
                              f"in memory") from None
        try:
            return Credential.from_payload(payload)
        except ValueError as exc:
            raise BrokerError(f"the {app.value} credential in memory is unusable: "
                              f"{exc}") from None

    def _bearer(self, app: App, cred: Credential, *, force: bool = False) -> str:
        now = int(time.time())
        with self._lock:
            cached = self._access.get(app)
            if (not force and cached is not None and cached[0] == cred.refresh_token
                    and cached[2] - now > ACCESS_LEEWAY_S):
                return cached[1]
            inner = cred.token.get("token") or {}
            stored_access = inner.get("access_token")
            stored_exp = int(inner.get("expires_at") or 0)
            if (not force and stored_access and stored_exp - now > ACCESS_LEEWAY_S
                    and (cached is None or cached[0] != cred.refresh_token)):
                # A fresh unlock whose stored access token is still good.
                self._access[app] = (cred.refresh_token, str(stored_access), stored_exp)
                return str(stored_access)
            if cred.refresh_wall <= datetime.fromtimestamp(now, tz=timezone.utc):
                raise BrokerError(f"the {app.value} refresh token is past its "
                                  f"seven-day wall — re-authorise on the page")
            wrapped = refresh(self._client, cred, now=now)
            self._access[app] = (cred.refresh_token,
                                 str(wrapped["token"]["access_token"]),
                                 int(wrapped["token"]["expires_at"]))
            return self._access[app][1]

    def _app_status(self, app: App) -> dict[str, Any]:
        try:
            cred = self._credential(app)
        except BrokerError as exc:
            return {"armed": False, "detail": str(exc)}
        cached = self._access.get(app)
        fresh = bool(cached and cached[0] == cred.refresh_token)
        return {
            "armed": True,
            "refresh_wall": cred.refresh_wall.isoformat(),
            "refresh_wall_in_s": int((cred.refresh_wall - self.clock()).total_seconds()),
            "access_cached": fresh,
            "access_expires_at": (datetime.fromtimestamp(cached[2], tz=timezone.utc).isoformat()
                                  if fresh and cached else None),
        }

    def token_status(self) -> dict[str, Any]:
        """For the status page: when each wall is, and whether an access token
        is in hand. No values.

        The top level is the TRADING app, because that is what "armed" means to
        the page and to everything that reads this; the market app's own line
        hangs under ``market``. Two grants expire independently, so the page
        shows the nearer of the two walls — and the re-auth discipline is to
        renew both in one sitting, which keeps them on the same day."""
        status = self._app_status(App.TRADING)
        status["market"] = self._app_status(App.MARKET)
        return status

    # ── requests ─────────────────────────────────────────────────────────
    def _scrub(self, text: str) -> str:
        h = self._hash
        return text.replace(h[1], "<account>") if h else text

    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None,
                 json: Any = None, ok: tuple[int, ...] = (200,)) -> httpx.Response:
        """One call, with one retry on a 401 after a forced refresh. Nothing
        else is retried — a send that timed out is reported, not repeated.

        The app is read off the path (:func:`app_for`), not taken as an
        argument: there is no way for a caller to name the wrong one."""
        assert method in ("GET", "POST", "DELETE"), method
        app = app_for(path)
        cred = self._credential(app)
        token = self._bearer(app, cred)
        r = self._send(method, path, token, params, json)
        if r.status_code == 401 and method == "GET":
            # A GET is safe to repeat. A POST is not — a 401 there is reported,
            # and the service's reconcile discovers whether anything went in.
            token = self._bearer(app, cred, force=True)
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
        number is never kept — and cached against the TRADING credential, which
        is the only one that can ask the question at all."""
        cred = self._credential(App.TRADING)
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
        path = f"/trader/v1/accounts/{h}/orders"
        app = app_for(path)
        cred = self._credential(app)
        token = self._bearer(app, cred)
        r = self._send("POST", path, token, None, build_order(intent))
        if r.status_code == 400:
            return OrderResult(
                order_id=f"rejected:{intent.intent_id}", status=OrderStatus.REJECTED,
                symbol=intent.symbol, side=intent.side, qty=intent.qty,
                order_type=intent.order_type,
                price=intent.limit if intent.order_type is OrderType.LIMIT else intent.stop_price,
                submitted_at=self.clock(), legs=_intent_leg(intent),
                message=_error_detail(r) or "rejected (HTTP 400)")
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
                submitted_at=self.clock(), legs=_intent_leg(intent),
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
                submitted_at=self.clock(), legs=_intent_leg(intent),
                message=f"placed; the follow-up read failed ({exc}) — status unknown until reconcile")

    def cancel(self, order_id: str) -> OrderResult:
        """Spec-derived: ``DELETE .../orders/{id}`` → 200 empty; then a read.
        A DELETE the broker refuses (already filled, already gone) is not an
        error here: the read that follows says what actually happened, which
        is the race the stop logic is written to survive."""
        h = self.account_hash()
        path = f"/trader/v1/accounts/{h}/orders/{order_id}"
        app = app_for(path)
        cred = self._credential(app)
        token = self._bearer(app, cred)
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
        """Each order's ``orderActivityCollection`` entries with
        ``activityType == EXECUTION`` carry ``executionLegs[{legId, price,
        quantity, time}]``. One Fill per execution leg after ``since``, each
        attributed to *its own* leg.

        The attribution is a join the data already supports and the code simply
        did not make: every one of the 72 execution legs in the 2026-09-05
        recording carries a ``legId``, and so does every entry of every
        ``orderLegCollection``. Without it a three-leg fill produced three Fill
        records all stamped with leg 0's symbol and side — wrong data entering
        the service's fill tracking, not merely incomplete data [st-ilp9]. An
        execution leg whose ``legId`` matches nothing is reported with an empty
        symbol rather than borrowed from a leg that happens to be first."""
        fills: list[Fill] = []
        for o in self._orders_raw():
            by_id = {leg.leg_id: leg for leg in _legs(o) if leg.leg_id is not None}
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
                    leg_id = leg.get("legId")
                    leg_id = int(leg_id) if isinstance(leg_id, (int, float)) else None
                    ordered = by_id.get(leg_id)
                    fills.append(Fill(
                        order_id=str(o.get("orderId")),
                        symbol=ordered.symbol if ordered else "",
                        side=ordered.side if ordered else Side.SELL_TO_CLOSE,
                        qty=qty, price=float(leg.get("price") or 0.0), at=at,
                        leg_id=leg_id,
                        instruction=ordered.instruction if ordered else "",
                    ))
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
        """``Order`` → :class:`OrderResult`, faithful to what the account holds.

        Recorded against 38 real orders on 2026-09-05, of which 18 were
        three-leg butterflies Steve placed by hand. Read the leg collection, not
        leg 0; take the type from the broker's word rather than inferring
        ``LIMIT`` from the presence of a price; and for a spread leave the
        single-leg convenience fields empty [st-ilp9]."""
        legs = _legs(o)
        one = legs[0] if len(legs) == 1 else None
        symbol = one.symbol if one else ""
        side = one.side if one else Side.SELL_TO_CLOSE
        raw_status = str(o.get("status") or "UNKNOWN")
        status = _STATUS.get(raw_status, OrderStatus.WORKING)
        raw_type = str(o.get("orderType") or "")
        if raw_type in _ORDER_TYPES:
            otype = _ORDER_TYPES[raw_type]
        elif raw_type.startswith("STOP"):
            otype = OrderType.STOP
        else:
            otype = OrderType.LIMIT if o.get("price") is not None else OrderType.MARKET
        price = o.get("price") if otype is not OrderType.STOP else o.get("stopPrice")
        filled = int(round(float(o.get("filledQuantity") or 0.0)))
        fill_price = _net_fill_price(o, legs) if len(legs) > 1 else _avg_fill_price(o)
        qty = int(round(float(o.get("quantity") or (legs[0].qty if legs else 0) or 0)))
        message = raw_status if status is OrderStatus.WORKING and raw_status != "WORKING" else ""
        if status is OrderStatus.REJECTED:
            message = str(o.get("statusDescription") or o.get("tag") or "rejected")
        strategy = str(o.get("complexOrderStrategyType") or "")
        return OrderResult(
            order_id=str(o.get("orderId")), status=status, symbol=symbol, side=side,
            qty=qty, order_type=otype,
            price=float(price) if price is not None else None,
            filled_qty=filled, fill_price=fill_price,
            submitted_at=_iso(o.get("enteredTime"), self.clock()), message=message,
            legs=legs, strategy="" if strategy == "NONE" else strategy,
        )


def _order_id_from_location(location: str | None) -> str | None:
    if not location:
        return None
    tail = location.rstrip("/").rsplit("/", 1)[-1]
    return tail if tail.isdigit() else None


def _intent_leg(intent: OrderIntent) -> tuple[OrderLeg, ...]:
    """The single leg an intent describes, for the three results the transport
    has to synthesize when the broker's own answer cannot be read. The service
    sends nothing else — ``SENDABLE_ORDER_TYPES`` in ``intent.py`` says so."""
    return (OrderLeg(symbol=intent.symbol, instruction=intent.side.value,
                     side=intent.side, qty=intent.qty, leg_id=1),)


def _side_of(instruction: str) -> Side:
    """Reduce a broker instruction to the two sides the service can express.

    Lossy on purpose and only for the convenience fields: ``BUY_TO_CLOSE``
    lands on ``BUY_TO_OPEN``. :class:`~execd.broker.OrderLeg` keeps the word
    itself, which is what to read for a leg the service did not send."""
    return Side.BUY_TO_OPEN if instruction.startswith("BUY") else Side.SELL_TO_CLOSE


def _legs(o: Mapping[str, Any]) -> tuple[OrderLeg, ...]:
    """Every leg of ``orderLegCollection``, in the order the broker gave them.

    ``orderStrategyType`` is *not* the leg count — it says SINGLE for all 38
    orders in the 2026-09-05 recording, 18 of which have three legs. It
    distinguishes a plain order from an OCO or TRIGGER group. The count lives
    here and nowhere else [st-ilp9]."""
    out: list[OrderLeg] = []
    for leg in o.get("orderLegCollection") or []:
        if not isinstance(leg, dict):
            continue
        inst = leg.get("instrument") or {}
        instruction = str(leg.get("instruction") or "")
        leg_id = leg.get("legId")
        out.append(OrderLeg(
            symbol=str(inst.get("symbol") or ""),
            instruction=instruction,
            side=_side_of(instruction),
            qty=int(round(float(leg.get("quantity") or 0.0))),
            leg_id=int(leg_id) if isinstance(leg_id, (int, float)) else None,
        ))
    return tuple(out)


def _net_fill_price(o: Mapping[str, Any], legs: tuple[OrderLeg, ...]) -> float | None:
    """The net premium per contract a multi-leg order actually filled at.

    Averaging the leg prices, which is what a single-leg order wants, is
    meaningless for a spread: the butterfly recorded on 2026-08-28 filled its
    legs at 3.23, 0.85 and 0.22 and was a net credit of 1.75. So sell legs are
    added and buy legs subtracted, and the total is divided by the order's
    filled quantity. Reported unsigned, the way the broker reports it — the
    direction is in ``order_type``, ``NET_CREDIT`` or ``NET_DEBIT``.

    Checked against the recording: this reproduces the order's own price for 10
    of the 11 filled multi-leg orders exactly, and the eleventh differs by 0.10
    in the customer's favour, which is a fill better than the limit [st-ilp9]."""
    by_id = {leg.leg_id: leg for leg in legs if leg.leg_id is not None}
    total = 0.0
    seen = False
    for act in o.get("orderActivityCollection") or []:
        if not isinstance(act, dict) or act.get("activityType") != "EXECUTION":
            continue
        for el in act.get("executionLegs") or []:
            if not isinstance(el, dict):
                continue
            leg = by_id.get(el.get("legId"))
            price = el.get("price")
            if leg is None or price is None:
                # One unattributable leg makes the net wrong, not approximate.
                return None
            qty = float(el.get("quantity") or 0.0)
            if qty <= 0:
                continue
            total += (1.0 if leg.instruction.startswith("SELL") else -1.0) * float(price) * qty
            seen = True
    filled = float(o.get("filledQuantity") or 0.0)
    if not seen or filled <= 0:
        return None
    return round(abs(total / filled), 4)


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
