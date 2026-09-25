"""The Alpaca transport — the second real broker behind the seam. [co-8mb1z]

Steve, 2026-09-23: "Update Strader's codebase to allow trading against either
Alpaca or Schwab." This module is the third implementation of the
:class:`~execd.broker.Broker` protocol and the second module in the package
allowed a transport (``tests/execd/test_wall.py`` names both). The service
never learns which broker it holds; every bound, the bracket, the journal and
the arming rules are the same code over either.

**What Alpaca trades, measured 2026-09-23 from Alpaca's own pages.** Index
options — SPX, SPXW, VIX, VIXW, DJX, XSP — went live on the Trading API on
2026-09-02 (Alpaca blog, "Alpaca Launches Live Trading for Index Options via
Trading API"), cash-settled, $0.50 a contract plus pass-through exchange and
regulatory fees. The same post says Alpaca "does not currently provide index
data through its Market Data offering". So the $SPX mark the exit loop reads,
and the SPX chain the order page builds from, cannot come from Alpaca: this
transport takes a ``market`` delegate — in production the Schwab transport
bound to the market-data credential only, which cannot trade — and asks it
for every quote, chain and raw market read. Without a delegate, quotes go to
Alpaca's data API (equities, crypto, equity options) and an index quote or a
chain is refused by name.

**What is recorded and what is not.** Nothing here has been recorded against
Alpaca. The request and response shapes follow Alpaca's API reference
(``docs.alpaca.markets/reference``; ``POST /v2/orders`` read 2026-09-23: 200
with the order, 403 buying power, 422 bad input). The first paper order is
what turns these into recorded shapes; until then a mis-named field is a
possibility this module is honest about.

**Two venues, chosen by Steve's mode file, never by a URL argument.**
``paper`` is ``paper-api.alpaca.markets`` — Alpaca's own simulated venue, so
unlike Schwab the service does not wrap this broker in its paper book; the
orders go to Alpaca's paper account. ``live`` is ``api.alpaca.markets``. The
venue is fixed at construction from the instance's mode file
(``/etc/execd-alpaca/mode``), and the credential the passphrase puts in
memory carries its own venue; a paper key offered to
the live venue, or a live key to paper, is refused before any call. So live
Alpaca sits behind the same three gates as live Schwab: the mode file Steve
writes, his passphrase, and the bounds.

**What this module refuses to do**, the same list as ``execd/schwab.py``:
GET, POST and DELETE only (no PATCH — Alpaca's replace verb — so a chase
arrives as a cancel and a new intent through the bounds); no retry of a send;
no key, secret or account number in any log line or exception.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Mapping

import httpx

from .arming import Locked
from .broker import (MARKET_READS, BrokerError, Fill, OrderLeg, OrderResult, OrderStatus,
                     Position, Preview, Quote)
from .intent import OrderIntent, OrderType, Side, parse_occ

log = logging.getLogger("execd.alpaca")

#: The two trading venues. Chosen by :class:`AlpacaBroker`'s ``venue``, which
#: ``python -m execd`` takes from Steve's mode file and nowhere else.
VENUES: dict[str, str] = {
    "paper": "https://paper-api.alpaca.markets",
    "live": "https://api.alpaca.markets",
}
#: Market data: one host for both venues.
DATA = "https://data.alpaca.markets"

TIMEOUT_S = 15.0
ORDERS_LOOKBACK = timedelta(days=2)
CANCEL_CONFIRM_S = 6.0
CANCEL_POLL_S = 0.5
FILLS_PAGE_SIZE = 100

OPTION_MULTIPLIER = 100
#: Alpaca's published index-option fee (2026-09-02 post), per contract.
#: Exchange and regulatory pass-throughs are not in it; the preview says so.
INDEX_OPTION_FEE_USD = 0.50

_HEADER_ID = "APCA-API-KEY-ID"
_HEADER_SECRET = "APCA-API-SECRET-KEY"

#: Alpaca's order statuses that are terminal, mapped to ours. Everything else
#: (new, accepted, pending_new, partially_filled, pending_cancel, held, ...) is
#: an order the broker still holds: WORKING, with Alpaca's word in ``message``.
_STATUS = {
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELED,
    "expired": OrderStatus.CANCELED,
    "replaced": OrderStatus.CANCELED,
    "done_for_day": OrderStatus.CANCELED,
    "rejected": OrderStatus.REJECTED,
}

_ORDER_TYPES = {"limit": OrderType.LIMIT, "market": OrderType.MARKET,
                "stop": OrderType.STOP, "stop_limit": OrderType.STOP,
                "trailing_stop": OrderType.STOP}

#: Alpaca writes an option as OCC with no padding: ``SPXW260918C06600000``.
_ALPACA_OPTION_RE = re.compile(r"^(?P<root>[A-Z]{1,6})(?P<rest>\d{6}[CP]\d{8})$")


# ── symbols ──────────────────────────────────────────────────────────────


def asset_class(symbol: str) -> str:
    """``option`` for an OCC symbol (either spelling), ``crypto`` for a pair
    written with a slash, ``equity`` otherwise."""
    try:
        parse_occ(symbol)
        return "option"
    except ValueError:
        pass
    if _ALPACA_OPTION_RE.match(symbol):
        return "option"
    return "crypto" if "/" in symbol else "equity"


def to_alpaca_symbol(symbol: str) -> str:
    """The service's padded OCC (``SPXW  260918C06600000``) → Alpaca's
    unpadded form. Equities and crypto pass unchanged."""
    try:
        occ = parse_occ(symbol)
    except ValueError:
        return symbol
    return f"{occ.root}{symbol[-15:]}"


def from_alpaca_symbol(symbol: str) -> str:
    """Alpaca's unpadded option symbol → the padded OCC the service and its
    bounds read. Anything that is not an option passes unchanged."""
    m = _ALPACA_OPTION_RE.match(symbol or "")
    if not m:
        return symbol
    return f"{m.group('root'):<6}{m.group('rest')}"


def format_price(pts: float) -> str:
    """Two decimals, half-up, as text — the same rounding the Schwab transport
    uses, so a limit the bounds approved is the limit that is sent."""
    return str(Decimal(str(pts)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ── credential ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AlpacaCredential:
    """One venue's key pair, checked for shape. ``repr`` never shows it."""

    venue: str
    key_id: str
    secret_key: str

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"AlpacaCredential({self.venue}, <redacted>)"

    @classmethod
    def from_payload(cls, payload: Any) -> "AlpacaCredential":
        """Shape check only. Names the missing field, never a value."""
        if not isinstance(payload, Mapping):
            raise ValueError("alpaca credential payload is not a mapping")
        venue = payload.get("venue")
        if venue not in VENUES:
            raise ValueError(f"alpaca credential names no venue (paper or live), found {venue!r}")
        if not payload.get("key_id") or not payload.get("secret_key"):
            raise ValueError(f"alpaca {venue} credential has no key_id / secret_key")
        return cls(str(venue), str(payload["key_id"]), str(payload["secret_key"]))


def alpaca_payload(vault_payload: Any, venue: str) -> dict[str, Any]:
    """The credential for ``venue`` out of the execd vault's envelope.

    The envelope keeps Schwab's ``trading`` section untouched and carries
    ``alpaca: {paper: {key_id, secret_key}, live: {...}}`` beside it, written
    by ``scripts/execd_vault_init.py --add-alpaca``. Raises ``ValueError``
    naming what is missing."""
    if venue not in VENUES:
        raise ValueError(f"no such Alpaca venue: {venue!r}")
    section = vault_payload.get("alpaca") if isinstance(vault_payload, Mapping) else None
    if not isinstance(section, Mapping):
        raise ValueError("the vault holds no alpaca section — run "
                         "scripts/execd_vault_init.py --add-alpaca")
    pair = section.get(venue)
    if not isinstance(pair, Mapping):
        raise ValueError(f"the vault holds no alpaca {venue} keys — run "
                         f"scripts/execd_vault_init.py --add-alpaca")
    payload = {"venue": venue, "key_id": pair.get("key_id"), "secret_key": pair.get("secret_key")}
    AlpacaCredential.from_payload(payload)
    return payload


def alpaca_payloads(vault_payload: Any, need: str | None = None) -> dict[str, Any]:
    """Every Alpaca venue the vault holds, as the one credential the service
    keeps in memory: ``{"venues": {"paper": {...}, "live": {...}}}``. Each
    :class:`AlpacaBroker` takes its own venue's pair from it, so the page's
    PAPER/LIVE switch (co-8mb1z) moves between venues without asking the
    vault again. ``need`` names a venue that must be present — the mode the
    instance is in, or the one the switch is going to; its absence is a
    ``ValueError`` in words."""
    venues: dict[str, Any] = {}
    for venue in VENUES:
        try:
            venues[venue] = alpaca_payload(vault_payload, venue)
        except ValueError:
            continue
    if need is not None and need not in venues:
        raise ValueError(f"the vault holds no Alpaca {need} keys — put them in with "
                         f"vault-set.py Strader ALPACA_{need.upper()}_API_KEY_ID (and "
                         f"ALPACA_{need.upper()}_API_SECRET_KEY), then "
                         f"scripts/execd_vault_init.py --add-alpaca")
    if not venues:
        raise ValueError("the vault holds no alpaca section — run "
                         "scripts/execd_vault_init.py --add-alpaca")
    return {"venues": venues}


# ── wire shapes ──────────────────────────────────────────────────────────


def build_order(intent: OrderIntent, client_order_id: str) -> dict[str, Any]:
    """One single-leg order in ``POST /v2/orders`` shape.

    ``day`` for options and equities, as on Schwab: nothing this service
    places may outlive the session. Crypto has no session, so it is ``gtc``,
    and Alpaca takes no plain stop on crypto, so a STOP intent there is
    refused here rather than at the broker."""
    klass = asset_class(intent.symbol)
    body: dict[str, Any] = {
        "symbol": to_alpaca_symbol(intent.symbol),
        "qty": str(int(intent.qty)),
        "side": "buy" if intent.side is Side.BUY_TO_OPEN else "sell",
        "type": intent.order_type.value.lower(),
        "time_in_force": "gtc" if klass == "crypto" else "day",
        "client_order_id": client_order_id,
    }
    if klass == "option":
        body["position_intent"] = intent.side.value.lower()
    if intent.order_type is OrderType.LIMIT:
        if intent.limit is None:
            raise ValueError("a LIMIT intent needs a limit")
        body["limit_price"] = format_price(intent.limit)
    elif intent.order_type is OrderType.STOP:
        if klass == "crypto":
            raise ValueError("Alpaca takes no plain stop order on crypto")
        if intent.stop_price is None:
            raise ValueError("a STOP intent needs a stop_price")
        body["stop_price"] = format_price(intent.stop_price)
    elif intent.order_type is not OrderType.MARKET:
        raise ValueError(f"the service does not send {intent.order_type.value} orders")
    return body


def client_order_id(intent: OrderIntent) -> str:
    """The intent id plus a short suffix. Alpaca refuses a repeated
    ``client_order_id``, and the service legitimately re-sends under one
    intent id (a stop re-rested at the same size is ``<id>:stop:1`` both
    times). Idempotency is the service's, from its journal; the suffix keeps
    Alpaca's own check from turning a re-rest into a rejection."""
    return f"{intent.intent_id}~{uuid.uuid4().hex[:8]}"[:128]


def _f(v: Any) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _qty(v: Any) -> int:
    f = _f(v)
    return int(round(f)) if f is not None else 0


def _ts(v: Any, fallback: datetime) -> datetime:
    if not v:
        return fallback
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        # Alpaca stamps nanoseconds; fromisoformat takes six digits at most.
        m = re.match(r"^(.*\.\d{6})\d*(Z|[+-]\d\d:\d\d)$", str(v))
        if not m:
            return fallback
        try:
            dt = datetime.fromisoformat(m.group(1) + m.group(2).replace("Z", "+00:00"))
        except ValueError:
            return fallback
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _error_detail(r: httpx.Response) -> str:
    """Alpaca's error body is ``{"code": n, "message": "..."}``. It carries no
    key; safe to quote, truncated."""
    try:
        body = r.json()
    except ValueError:
        return (r.text or "")[:200]
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])[:200]
    return ""


# ── the broker ───────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlpacaBroker:
    """The :class:`~execd.broker.Broker` protocol over Alpaca's Trading API.

    :param venue: ``paper`` or ``live`` — Steve's mode file, read by
        ``python -m execd``. Fixes the trading host; there is no URL argument.
    :param credential_source: returns the venue's key pair or raises
        :class:`~execd.arming.Locked`; :meth:`bind` wires it to the arming
        state, so a lock is a lock on this transport too.
    :param market: the market-data delegate (the Schwab transport bound to
        its market credential in production). Every quote, chain and raw
        market read goes to it when it is given.
    :param roots: the OCC roots whose positions are this service's — the
        bounds' ``instruments``. Everything else is counted, not shown.
    """

    def __init__(self, venue: str, credential_source: Callable[[], Any] | None = None, *,
                 market: Any | None = None,
                 roots: tuple[str, ...] = ("SPX", "SPXW"),
                 clock: Callable[[], datetime] = _utcnow,
                 transport: httpx.BaseTransport | None = None,
                 timeout_s: float = TIMEOUT_S,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if venue not in VENUES:
            raise ValueError(f"no such Alpaca venue: {venue!r} (paper or live)")
        self.venue = venue
        self.base = VENUES[venue]
        self.credential_source = credential_source
        self.market = market
        self.roots: frozenset[str] = frozenset(r.upper() for r in roots)
        self.clock = clock
        self._sleep = sleep
        self._client = httpx.Client(timeout=timeout_s, transport=transport)
        self._lock = threading.RLock()
        self.excluded_positions: dict[str, int] = {}

    def bind(self, arming: Any) -> "AlpacaBroker":
        self.credential_source = arming.credential
        return self

    def close(self) -> None:
        self._client.close()

    # ── credential ───────────────────────────────────────────────────────
    def _credential(self) -> AlpacaCredential:
        if self.credential_source is None:
            raise BrokerError("no credential source is bound to the Alpaca transport")
        try:
            payload = self.credential_source()
        except Locked:
            raise BrokerError("the service is locked — no Alpaca credential in memory") from None
        if isinstance(payload, Mapping) and "venues" in payload:
            venues = payload.get("venues") or {}
            if self.venue not in venues:
                raise BrokerError(f"no Alpaca {self.venue} keys in memory — the vault held "
                                  f"none when the service was unlocked")
            payload = venues[self.venue]
        try:
            cred = AlpacaCredential.from_payload(payload)
        except ValueError as exc:
            raise BrokerError(f"the credential in memory is not an Alpaca one: {exc}") from None
        if cred.venue != self.venue:
            # The one mistake that matters most: a key for one venue reaching
            # the other. Refused before a byte leaves the box.
            raise BrokerError(f"the credential in memory is for Alpaca {cred.venue}; "
                              f"this service is running against Alpaca {self.venue}")
        return cred

    def token_status(self) -> dict[str, Any]:
        """For ``/status``: which broker, which venue, armed or not. Alpaca
        keys have no seven-day wall, so there is none to report; the market
        delegate's own line hangs under ``market``."""
        try:
            self._credential()
            out: dict[str, Any] = {"broker": "alpaca", "venue": self.venue, "armed": True}
        except BrokerError as exc:
            out = {"broker": "alpaca", "venue": self.venue, "armed": False, "detail": str(exc)}
        status = getattr(self.market, "token_status", None)
        if callable(status):
            try:
                out["market"] = dict(status()).get("market") or {}
            except Exception as exc:  # reported, not hidden
                out["market"] = {"armed": False, "detail": type(exc).__name__}
        return out

    # ── requests ─────────────────────────────────────────────────────────
    def _send(self, method: str, url: str, *, params: Mapping[str, Any] | None = None,
              json: Any = None) -> httpx.Response:
        assert method in ("GET", "POST", "DELETE"), method
        cred = self._credential()
        headers = {_HEADER_ID: cred.key_id, _HEADER_SECRET: cred.secret_key,
                   "Accept": "application/json"}
        try:
            return self._client.request(method, url, params=params, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise BrokerError(f"alpaca {method} {url.split('://', 1)[-1].split('/', 1)[-1]}: "
                              f"{type(exc).__name__}") from None

    def _get(self, url: str, what: str, params: Mapping[str, Any] | None = None) -> Any:
        r = self._send("GET", url, params=params)
        if r.status_code != 200:
            raise BrokerError(f"alpaca {what}: HTTP {r.status_code} {_error_detail(r)}".rstrip())
        try:
            return r.json()
        except ValueError:
            raise BrokerError(f"alpaca answered {what} with a non-JSON body") from None

    # ── market data ──────────────────────────────────────────────────────
    def market_read(self, kind: str, params: dict[str, str]) -> Any:
        if kind not in MARKET_READS:
            raise BrokerError(f"no such market read: {kind}")
        if self.market is None:
            raise BrokerError(f"no market-data source for {kind}: Alpaca publishes no index "
                              f"data — start execd with --market-credential")
        return self.market.market_read(kind, params)

    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]:
        if self.market is None:
            raise BrokerError(f"no chain source for {root}: Alpaca publishes no index data — "
                              f"start execd with --market-credential")
        return self.market.chain(root, expiry)

    def quote(self, symbol: str) -> Quote:
        if self.market is not None:
            return self.market.quote(symbol)
        if symbol.startswith("$"):
            raise BrokerError(f"no quote for {symbol}: Alpaca publishes no index data")
        klass = asset_class(symbol)
        sym = to_alpaca_symbol(symbol)
        now = self.clock()
        if klass == "equity":
            body = self._get(f"{DATA}/v2/stocks/{sym}/quotes/latest", "stock quote")
            q = body.get("quote") if isinstance(body, dict) else None
        else:
            path = ("/v1beta3/crypto/us/latest/quotes" if klass == "crypto"
                    else "/v1beta1/options/quotes/latest")
            body = self._get(f"{DATA}{path}", f"{klass} quote", params={"symbols": sym})
            quotes = body.get("quotes") if isinstance(body, dict) else None
            q = quotes.get(sym) if isinstance(quotes, dict) else None
        if not isinstance(q, dict):
            raise BrokerError(f"no quote for {symbol}")
        bid, ask = _f(q.get("bp")) or 0.0, _f(q.get("ap")) or 0.0
        return Quote(symbol=symbol, bid=bid, ask=ask, last=(bid + ask) / 2.0 if bid and ask else bid or ask,
                     as_of=_ts(q.get("t"), now))

    # ── account ──────────────────────────────────────────────────────────
    def balances(self) -> dict[str, float | None]:
        """``GET /v2/account``, in the service's names. Alpaca's
        ``options_buying_power`` is what an option buy is checked against, so
        it answers both ``available_funds`` and ``option_buying_power``."""
        body = self._get(f"{self.base}/v2/account", "account")
        if not isinstance(body, dict):
            raise BrokerError("alpaca account body is not an object")
        obp = _f(body.get("options_buying_power"))
        return {"available_funds": obp if obp is not None else _f(body.get("cash")),
                "option_buying_power": obp,
                "buying_power": _f(body.get("buying_power")),
                "cash_balance": _f(body.get("cash")),
                "liquidation_value": _f(body.get("equity"))}

    def positions(self) -> list[Position]:
        """``GET /v2/positions``. Only options whose OCC root is in
        :attr:`roots` are reported — the same test the bounds make. The rest
        are counted in :attr:`excluded_positions` so ``/status`` shows them."""
        body = self._get(f"{self.base}/v2/positions", "positions")
        if not isinstance(body, list):
            raise BrokerError("alpaca positions body is not a list")
        out: list[Position] = []
        excluded: dict[str, int] = {}
        for p in body:
            if not isinstance(p, dict):
                continue
            symbol = from_alpaca_symbol(str(p.get("symbol") or ""))
            klass = str(p.get("asset_class") or "unknown").upper()
            try:
                root = parse_occ(symbol).root
            except ValueError:
                root = ""
            if root not in self.roots:
                excluded[klass] = excluded.get(klass, 0) + 1
                continue
            qty = _qty(p.get("qty"))
            if str(p.get("side") or "") == "short" and qty > 0:
                qty = -qty
            if qty == 0:
                continue
            out.append(Position(symbol=symbol, qty=qty,
                                avg_price=_f(p.get("avg_entry_price")) or 0.0))
        self.excluded_positions = excluded
        return out

    # ── orders ───────────────────────────────────────────────────────────
    def preview(self, intent: OrderIntent) -> Preview:
        """Alpaca has no preview endpoint, so this is computed here and says
        so in its messages: the price the intent names (or the touch for a
        market order), times the multiplier, against the account's buying
        power. A cost the account cannot pay is ``accepted=False`` — the one
        refusal Alpaca would otherwise answer with a 403 at the send."""
        klass = asset_class(intent.symbol)
        mult = OPTION_MULTIPLIER if klass == "option" else 1
        if intent.order_type is OrderType.LIMIT:
            price = intent.limit
        elif intent.order_type is OrderType.STOP:
            price = intent.stop_price
        else:
            q = self.quote(intent.symbol)
            price = q.ask if intent.side is Side.BUY_TO_OPEN else q.bid
        cost = round(float(price or 0.0) * mult * intent.qty, 2)
        fee = 0.0
        messages = ["computed by execd: Alpaca has no preview endpoint"]
        if klass == "option":
            try:
                root = parse_occ(intent.symbol).root
            except ValueError:
                root = ""
            if root in ("SPX", "SPXW", "VIX", "VIXW", "DJX", "XSP"):
                fee = round(INDEX_OPTION_FEE_USD * intent.qty, 2)
                messages.append("fee is Alpaca's $0.50/contract; exchange and regulatory "
                                "pass-throughs are not included")
        accepted = True
        if intent.side is Side.BUY_TO_OPEN:
            money = self.balances()
            avail = money["option_buying_power"] if klass == "option" else money["buying_power"]
            if avail is not None and cost + fee > avail:
                accepted = False
                messages.append(f"reject: costs ${cost + fee:,.2f}; the account has "
                                f"${avail:,.2f} buying power")
        return Preview(symbol=intent.symbol, side=intent.side, qty=intent.qty,
                       order_type=intent.order_type,
                       price=float(price) if price is not None else None,
                       cost_usd=cost, commission_usd=fee, accepted=accepted,
                       messages=tuple(messages))

    def place(self, intent: OrderIntent) -> OrderResult:
        """``POST /v2/orders`` → 200 with the order. 403 (buying power) and
        422 (Alpaca would not take it) are the broker's rejection, returned as
        one; anything else non-200 is :class:`BrokerError`. Never retried."""
        try:
            body = build_order(intent, client_order_id(intent))
        except ValueError as exc:
            return self._synthetic(intent, OrderStatus.REJECTED, f"rejected:{intent.intent_id}",
                                   str(exc))
        r = self._send("POST", f"{self.base}/v2/orders", json=body)
        if r.status_code in (403, 422):
            return self._synthetic(intent, OrderStatus.REJECTED, f"rejected:{intent.intent_id}",
                                   _error_detail(r) or f"rejected (HTTP {r.status_code})")
        if r.status_code not in (200, 201):
            raise BrokerError(f"alpaca POST v2/orders: HTTP {r.status_code} "
                              f"{_error_detail(r)}".rstrip())
        try:
            order = r.json()
        except ValueError:
            order = None
        if not isinstance(order, dict) or not order.get("id"):
            # Taken, and cannot be named: hold the slot and let reconcile find
            # it in the listing, as the Schwab transport does.
            return self._synthetic(intent, OrderStatus.WORKING, f"unnamed:{intent.intent_id}",
                                   "placed but Alpaca returned no order id — reconcile must "
                                   "find it in the broker's listing")
        log.info("alpaca %s: placed %s %s x%d as %s", self.venue, intent.side.value,
                 intent.symbol.strip(), intent.qty, order.get("id"))
        return self._to_result(order)

    def cancel(self, order_id: str) -> OrderResult:
        """``DELETE /v2/orders/{id}`` → 204, then re-read until terminal or
        :data:`CANCEL_CONFIRM_S`. A 422 (not cancelable — usually already
        filled) is not an error: the read says what happened."""
        r = self._send("DELETE", f"{self.base}/v2/orders/{order_id}")
        if r.status_code in (401, 403, 404) or r.status_code >= 500:
            raise BrokerError(f"alpaca DELETE v2/orders/{order_id}: HTTP {r.status_code} "
                              f"{_error_detail(r)}".rstrip())
        polls = max(1, int(CANCEL_CONFIRM_S / CANCEL_POLL_S))
        for i in range(polls):
            result = self._get_order(order_id)
            if not result.is_working or i == polls - 1:
                return result
            self._sleep(CANCEL_POLL_S)
        raise AssertionError("unreachable")  # pragma: no cover

    def orders(self) -> list[OrderResult]:
        now = self.clock()
        body = self._get(f"{self.base}/v2/orders", "orders",
                         params={"status": "all", "after": _iso(now - ORDERS_LOOKBACK),
                                 "limit": 500, "direction": "desc", "nested": "true"})
        if not isinstance(body, list):
            raise BrokerError("alpaca orders body is not a list")
        return [self._to_result(o) for o in body if isinstance(o, dict)]

    def fills_since(self, since: datetime) -> list[Fill]:
        """``GET /v2/account/activities/FILL?after=``, paged by the last
        activity id. One Fill per activity; an Alpaca order is one leg here."""
        fills: list[Fill] = []
        params: dict[str, Any] = {"after": _iso(since), "direction": "asc",
                                  "page_size": FILLS_PAGE_SIZE}
        for _ in range(50):
            body = self._get(f"{self.base}/v2/account/activities/FILL", "fills", params=params)
            if not isinstance(body, list):
                raise BrokerError("alpaca activities body is not a list")
            for a in body:
                if not isinstance(a, dict):
                    continue
                at = _ts(a.get("transaction_time"), self.clock())
                qty = _qty(a.get("qty"))
                if at <= since or qty <= 0:
                    continue
                side = Side.BUY_TO_OPEN if a.get("side") == "buy" else Side.SELL_TO_CLOSE
                fills.append(Fill(order_id=str(a.get("order_id") or ""),
                                  symbol=from_alpaca_symbol(str(a.get("symbol") or "")),
                                  side=side, qty=qty, price=_f(a.get("price")) or 0.0, at=at,
                                  leg_id=1, instruction=side.value))
            if len(body) < FILLS_PAGE_SIZE or not isinstance(body[-1], dict):
                break
            params["page_token"] = body[-1].get("id")
        fills.sort(key=lambda f: f.at)
        return fills

    # ── internals ────────────────────────────────────────────────────────
    def _get_order(self, order_id: str) -> OrderResult:
        body = self._get(f"{self.base}/v2/orders/{order_id}", "order")
        if not isinstance(body, dict):
            raise BrokerError("alpaca order body is not an object")
        return self._to_result(body)

    def _synthetic(self, intent: OrderIntent, status: OrderStatus, order_id: str,
                   message: str) -> OrderResult:
        return OrderResult(
            order_id=order_id, status=status, symbol=intent.symbol, side=intent.side,
            qty=intent.qty, order_type=intent.order_type,
            price=intent.limit if intent.order_type is OrderType.LIMIT else intent.stop_price,
            submitted_at=self.clock(), message=message,
            legs=(OrderLeg(symbol=intent.symbol, instruction=intent.side.value,
                           side=intent.side, qty=intent.qty, leg_id=1),))

    def _to_result(self, o: Mapping[str, Any]) -> OrderResult:
        """An Alpaca order → :class:`OrderResult`. A multi-leg (``mleg``)
        order Steve placed by hand is reported with its legs and empty
        single-leg fields, as the Schwab transport does [st-ilp9]."""
        raw_legs = [leg for leg in (o.get("legs") or []) if isinstance(leg, dict)]
        sources = raw_legs if str(o.get("order_class") or "") == "mleg" and raw_legs else [o]
        legs: list[OrderLeg] = []
        for i, leg in enumerate(sources, start=1):
            word = str(leg.get("position_intent") or leg.get("side") or "").upper()
            side = Side.BUY_TO_OPEN if word.startswith("BUY") else Side.SELL_TO_CLOSE
            legs.append(OrderLeg(symbol=from_alpaca_symbol(str(leg.get("symbol") or "")),
                                 instruction=word, side=side,
                                 qty=_qty(leg.get("qty") or leg.get("ratio_qty")), leg_id=i))
        one = legs[0] if len(legs) == 1 else None
        raw_status = str(o.get("status") or "unknown")
        status = _STATUS.get(raw_status, OrderStatus.WORKING)
        otype = _ORDER_TYPES.get(str(o.get("type") or o.get("order_type") or ""),
                                 OrderType.LIMIT if o.get("limit_price") else OrderType.MARKET)
        price = _f(o.get("stop_price")) if otype is OrderType.STOP else _f(o.get("limit_price"))
        message = ""
        if status is OrderStatus.WORKING and raw_status not in ("new", "accepted"):
            message = raw_status.upper()
        if status is OrderStatus.REJECTED:
            message = "rejected"
        return OrderResult(
            order_id=str(o.get("id")), status=status,
            symbol=one.symbol if one else "", side=one.side if one else Side.SELL_TO_CLOSE,
            qty=_qty(o.get("qty")), order_type=otype, price=price,
            filled_qty=_qty(o.get("filled_qty")), fill_price=_f(o.get("filled_avg_price")),
            submitted_at=_ts(o.get("submitted_at") or o.get("created_at"), self.clock()),
            message=message, legs=tuple(legs),
            strategy="mleg" if len(legs) > 1 else "")
