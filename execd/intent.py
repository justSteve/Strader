"""OrderIntent — an order as data, the only thing a caller may hand the service.

An intent is frozen, carries a caller-chosen ``intent_id`` (the idempotency
key: the service answers a repeat from its journal and never re-sends), an
OCC option symbol, a side, a quantity and a price instruction. For an entry it
may also carry the SPX level at which the service exits (``stop_spx``) and the
option's delta at compose time — the two numbers the protective stop is
derived from (``execd.stops``). It never carries a credential, an account, or
anything the service would trust over its own bounds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import date
from enum import Enum
from typing import Any, Mapping


class Side(str, Enum):
    BUY_TO_OPEN = "BUY_TO_OPEN"
    SELL_TO_CLOSE = "SELL_TO_CLOSE"


class OrderType(str, Enum):
    """Every order type the service must be able to *name*.

    The first three are the only ones it can send. ``NET_CREDIT`` and
    ``NET_DEBIT`` exist because the account holds spreads Steve places by hand
    and the transport has to report them as what they are; until st-ilp9 an
    unrecognised type fell through to ``LIMIT``, so a three-leg net-credit
    butterfly was read back as a plain limit order [st-ilp9]. Naming a type is
    not permission to send it — :meth:`OrderIntent.problems` refuses any intent
    that asks for one outside :data:`SENDABLE_ORDER_TYPES`."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    NET_CREDIT = "NET_CREDIT"
    NET_DEBIT = "NET_DEBIT"


#: What an intent may ask the service to send. Widening this is a wall-crossing
#: decision, not a refactor: everything in bounds.py reasons about single-leg
#: long premium.
SENDABLE_ORDER_TYPES = frozenset({OrderType.LIMIT, OrderType.MARKET, OrderType.STOP})


_OCC_RE = re.compile(r"^(?P<root>[A-Z]{1,6}) *(?P<ymd>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,79}$")


@dataclass(frozen=True)
class Occ:
    """An OCC option symbol, parsed: ``SPXW  260822C06300000`` → SPXW, 2026-08-22, C, 6300."""

    root: str
    expiry: date
    right: str          # "C" | "P"
    strike: float

    @property
    def right_word(self) -> str:
        return "CALL" if self.right == "C" else "PUT"


def parse_occ(symbol: str) -> Occ:
    """Parse the 21-character OCC form (root padded to six with spaces).

    Raises ``ValueError`` naming the symbol on any malformation.
    """
    m = _OCC_RE.match(symbol)
    if not m:
        raise ValueError(f"not an OCC option symbol: {symbol!r}")
    ymd = m.group("ymd")
    try:
        expiry = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except ValueError as exc:
        raise ValueError(f"bad expiry in OCC symbol {symbol!r}: {exc}") from None
    return Occ(m.group("root"), expiry, m.group("right"), int(m.group("strike")) / 1000.0)


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    symbol: str
    side: Side
    qty: int
    order_type: OrderType = OrderType.LIMIT
    limit: float | None = None          # premium points, for LIMIT
    stop_price: float | None = None     # premium points, for STOP (the protective stop)
    stop_spx: float | None = None       # SPX level at which the service exits (entries)
    delta: float | None = None          # |delta| at compose (entries), for the protective stop
    source: str = ""                    # "intent-desk" | "rule:<id>" | "flatten" | "protective-stop"
    engine_sha: str = ""

    # ── derived ──
    @property
    def occ(self) -> Occ:
        return parse_occ(self.symbol)

    @property
    def is_entry(self) -> bool:
        return self.side == Side.BUY_TO_OPEN

    @property
    def max_cost_usd(self) -> float | None:
        """What a limit entry can cost at most, before commission."""
        if self.order_type == OrderType.LIMIT and self.limit is not None:
            return round(self.limit * 100 * self.qty, 2)
        return None

    # ── validation ──
    def problems(self) -> list[str]:
        out: list[str] = []
        if not _ID_RE.match(self.intent_id or ""):
            out.append("intent_id must be 3-80 characters of letters, digits, . _ : -")
        try:
            parse_occ(self.symbol)
        except ValueError as exc:
            out.append(str(exc))
        if not isinstance(self.qty, int) or isinstance(self.qty, bool) or self.qty <= 0:
            out.append(f"qty must be a positive integer, not {self.qty!r}")
        if self.order_type not in SENDABLE_ORDER_TYPES:
            # The type vocabulary is wider than the send vocabulary on purpose:
            # the transport must be able to report a multi-leg spread it reads
            # from the account without that becoming an order it can place.
            out.append(f"the service does not send {self.order_type.value} orders")
        if self.order_type == OrderType.LIMIT and (self.limit is None or self.limit <= 0):
            out.append("a LIMIT order needs a positive limit")
        if self.order_type == OrderType.STOP and (self.stop_price is None or self.stop_price <= 0):
            out.append("a STOP order needs a positive stop_price")
        if self.order_type == OrderType.MARKET and self.limit is not None:
            out.append("a MARKET order carries no limit")
        if self.delta is not None and not (0 < abs(self.delta) <= 1):
            out.append(f"delta must be within (0, 1], not {self.delta!r}")
        return out

    def validated(self) -> "OrderIntent":
        probs = self.problems()
        if probs:
            raise ValueError(f"intent {self.intent_id!r}: " + "; ".join(probs))
        return self

    # ── wire form ──
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["order_type"] = self.order_type.value
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "OrderIntent":
        try:
            side = Side(str(d["side"]))
            order_type = OrderType(str(d.get("order_type", "LIMIT")))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"bad intent: {exc}") from None
        return cls(
            intent_id=str(d.get("intent_id", "")),
            symbol=str(d.get("symbol", "")),
            side=side,
            qty=d.get("qty", 0) if isinstance(d.get("qty"), int) and not isinstance(d.get("qty"), bool) else _as_int(d.get("qty")),
            order_type=order_type,
            limit=_as_float(d.get("limit")),
            stop_price=_as_float(d.get("stop_price")),
            stop_spx=_as_float(d.get("stop_spx")),
            delta=_as_float(d.get("delta")),
            source=str(d.get("source", "")),
            engine_sha=str(d.get("engine_sha", "")),
        )


def _as_float(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def _as_int(v) -> int:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f) if f == int(f) else 0
