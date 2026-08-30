"""The broker seam, and the mock that stands in for one until stage 2. [st-eznu]

Everything the service needs from a broker is the :class:`Broker` protocol
below — eight methods, all of them data in and data out. Stage 2 (st-w2nw)
lands a second implementation that speaks Schwab's Trader API over HTTPS. The
service never learns which one it is holding, which is what lets every bound,
every refusal and the whole protective-stop dance be tested here at full speed
with no credential in the room.

Nothing in this module imports the repo's ``schwab`` package. That is not an
accident of the moment — ``tests/execd/test_wall.py`` asserts it for every
module under ``execd/``, so the hook that stops agent code from importing the
hobbled library keeps its meaning while this service exists beside it.

``MockBroker`` is deliberately opinionated rather than permissive: it fills a
buy at ``min(limit, ask)`` and a market sell at the bid, rests STOP orders as
WORKING until something triggers them, and records every call. A test that
wants a rejection, a transport failure or an unfilled limit asks for it by
name (``reject_next``, ``fail_next``, ``rest_limits``) rather than by
arranging a market state that happens to produce one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from .intent import OrderIntent, OrderType, Side


class BrokerError(RuntimeError):
    """The broker could not be reached, or answered something unusable.

    Distinct from a rejection: a rejected order is a fact the broker asserted,
    a BrokerError is the absence of an answer. The service journals both but
    only retries neither — an execution service that retries by itself is a
    service that double-sends."""


class OrderStatus(str, Enum):
    WORKING = "WORKING"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    last: float = 0.0
    as_of: datetime = field(default_factory=_utcnow)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    def age_s(self, now: datetime) -> float:
        return max(0.0, (now - self.as_of).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "bid": self.bid, "ask": self.ask,
                "last": self.last, "as_of": self.as_of.isoformat()}


@dataclass(frozen=True)
class Preview:
    """What the broker says an order would cost, before it is sent."""

    symbol: str
    side: Side
    qty: int
    order_type: OrderType
    price: float | None
    cost_usd: float
    commission_usd: float = 0.0
    accepted: bool = True
    messages: tuple[str, ...] = ()

    @property
    def total_usd(self) -> float:
        return round(self.cost_usd + self.commission_usd, 2)

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "side": self.side.value, "qty": self.qty,
                "order_type": self.order_type.value, "price": self.price,
                "cost_usd": self.cost_usd, "commission_usd": self.commission_usd,
                "total_usd": self.total_usd, "accepted": self.accepted,
                "messages": list(self.messages)}


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    status: OrderStatus
    symbol: str
    side: Side
    qty: int
    order_type: OrderType
    price: float | None = None          # the limit or stop the order carries
    filled_qty: int = 0
    fill_price: float | None = None
    submitted_at: datetime = field(default_factory=_utcnow)
    message: str = ""

    @property
    def is_filled(self) -> bool:
        return self.status is OrderStatus.FILLED

    @property
    def is_working(self) -> bool:
        return self.status is OrderStatus.WORKING

    def to_dict(self) -> dict[str, Any]:
        return {"order_id": self.order_id, "status": self.status.value,
                "symbol": self.symbol, "side": self.side.value, "qty": self.qty,
                "order_type": self.order_type.value, "price": self.price,
                "filled_qty": self.filled_qty, "fill_price": self.fill_price,
                "submitted_at": self.submitted_at.isoformat(), "message": self.message}


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: int
    avg_price: float

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "qty": self.qty, "avg_price": self.avg_price}


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: int
    price: float
    at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {"order_id": self.order_id, "symbol": self.symbol,
                "side": self.side.value, "qty": self.qty, "price": self.price,
                "at": self.at.isoformat()}


@runtime_checkable
class Broker(Protocol):
    """The only surface the service knows. Eight methods, no credential."""

    def quote(self, symbol: str) -> Quote: ...
    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]: ...
    def preview(self, intent: OrderIntent) -> Preview: ...
    def place(self, intent: OrderIntent) -> OrderResult: ...
    def cancel(self, order_id: str) -> OrderResult: ...
    def orders(self) -> list[OrderResult]: ...
    def positions(self) -> list[Position]: ...
    def fills_since(self, since: datetime) -> list[Fill]: ...


# ── the mock ──────────────────────────────────────────────────────────────

COMMISSION_PER_CONTRACT_USD = 0.65   # Schwab's published options rate; stage 2 reads the real one
CONTRACT_MULTIPLIER = 100


class MockBroker:
    """A deterministic broker. No network, no clock drift, no surprises that a
    test did not ask for."""

    def __init__(self, clock: Callable[[], datetime] = _utcnow) -> None:
        self.clock = clock
        self._quotes: dict[str, Quote] = {}
        self._chains: dict[str, dict[str, Any]] = {}
        self._orders: dict[str, OrderResult] = {}
        self._positions: dict[str, Position] = {}
        self._fills: list[Fill] = []
        self._seq = 0

        #: every call, in order, as ``(method, kwargs)`` — the audit a test reads.
        self.calls: list[tuple[str, dict[str, Any]]] = []

        # knobs, each consumed by one call unless noted
        self.reject_next: str | None = None    # message for the next place()
        self.fail_next: str | None = None      # BrokerError from the next call
        self.rest_limits: bool = False         # standing: limits rest instead of filling
        self.partial_fill_qty: int | None = None   # next fill takes only this many

    # ── setup ────────────────────────────────────────────────────────────
    def set_quote(self, symbol: str, bid: float, ask: float,
                  last: float | None = None, as_of: datetime | None = None) -> Quote:
        q = Quote(symbol, bid, ask, last if last is not None else (bid + ask) / 2.0,
                  as_of or self.clock())
        self._quotes[symbol] = q
        return q

    def set_chain(self, root: str, chain: dict[str, Any]) -> None:
        self._chains[root.upper()] = chain

    def set_position(self, symbol: str, qty: int, avg_price: float) -> None:
        self._positions[symbol] = Position(symbol, qty, avg_price)

    # ── protocol ─────────────────────────────────────────────────────────
    def quote(self, symbol: str) -> Quote:
        self._record("quote", symbol=symbol)
        q = self._quotes.get(symbol)
        if q is None:
            raise BrokerError(f"no quote for {symbol}")
        return q

    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]:
        self._record("chain", root=root, expiry=expiry)
        ch = self._chains.get(root.upper())
        if ch is None:
            raise BrokerError(f"no chain for {root}")
        return ch

    def preview(self, intent: OrderIntent) -> Preview:
        self._record("preview", intent_id=intent.intent_id)
        price = self._expected_price(intent)
        cost = round(price * CONTRACT_MULTIPLIER * intent.qty, 2)
        return Preview(
            symbol=intent.symbol, side=intent.side, qty=intent.qty,
            order_type=intent.order_type, price=price,
            cost_usd=cost,
            commission_usd=round(COMMISSION_PER_CONTRACT_USD * intent.qty, 2),
        )

    def place(self, intent: OrderIntent) -> OrderResult:
        self._record("place", intent_id=intent.intent_id, symbol=intent.symbol,
                     side=intent.side.value, qty=intent.qty,
                     order_type=intent.order_type.value)
        if (msg := self.reject_next) is not None:
            self.reject_next = None
            return self._store(self._new_order(intent, OrderStatus.REJECTED, message=msg))

        if intent.order_type is OrderType.STOP:
            # A protective stop rests at the broker until price reaches it —
            # which is the entire reason it is placed there and not held here.
            return self._store(self._new_order(intent, OrderStatus.WORKING,
                                               price=intent.stop_price))

        if intent.order_type is OrderType.LIMIT and self.rest_limits:
            return self._store(self._new_order(intent, OrderStatus.WORKING,
                                               price=intent.limit))

        price = self._expected_price(intent)
        filled_qty = intent.qty
        if self.partial_fill_qty is not None:
            filled_qty = min(self.partial_fill_qty, intent.qty)
            self.partial_fill_qty = None
        order = self._new_order(intent, OrderStatus.FILLED, price=intent.limit,
                                filled_qty=filled_qty, fill_price=price)
        self._store(order)
        self._apply_fill(order)
        return order

    def cancel(self, order_id: str) -> OrderResult:
        self._record("cancel", order_id=order_id)
        order = self._orders.get(order_id)
        if order is None:
            raise BrokerError(f"no such order: {order_id}")
        if order.status is not OrderStatus.WORKING:
            # Not an error: a stop that already filled is a race the service
            # must survive, so cancelling it reports what actually happened.
            return order
        canceled = replace(order, status=OrderStatus.CANCELED)
        self._orders[order_id] = canceled
        return canceled

    def orders(self) -> list[OrderResult]:
        self._record("orders")
        return list(self._orders.values())

    def positions(self) -> list[Position]:
        self._record("positions")
        return [p for p in self._positions.values() if p.qty != 0]

    def fills_since(self, since: datetime) -> list[Fill]:
        self._record("fills_since", since=since.isoformat())
        return [f for f in self._fills if f.at > since]

    # ── test controls ────────────────────────────────────────────────────
    def trigger_stop(self, order_id: str) -> OrderResult:
        """Price reached a resting order. Fills it at the price it carries."""
        order = self._orders.get(order_id)
        if order is None:
            raise BrokerError(f"no such order: {order_id}")
        if order.status is not OrderStatus.WORKING:
            raise BrokerError(f"order {order_id} is {order.status.value}, not working")
        filled = replace(order, status=OrderStatus.FILLED, filled_qty=order.qty,
                         fill_price=order.price)
        self._orders[order_id] = filled
        self._apply_fill(filled)
        return filled

    def working_orders(self, symbol: str | None = None) -> list[OrderResult]:
        return [o for o in self._orders.values()
                if o.is_working and (symbol is None or o.symbol == symbol)]

    def calls_to(self, method: str) -> list[dict[str, Any]]:
        return [kw for name, kw in self.calls if name == method]

    # ── internals ────────────────────────────────────────────────────────
    def _record(self, method: str, **kw: Any) -> None:
        if (msg := self.fail_next) is not None:
            self.fail_next = None
            self.calls.append((method, {**kw, "failed": msg}))
            raise BrokerError(msg)
        self.calls.append((method, kw))

    def _expected_price(self, intent: OrderIntent) -> float:
        q = self._quotes.get(intent.symbol)
        if q is None:
            raise BrokerError(f"no quote for {intent.symbol}")
        if intent.order_type is OrderType.MARKET:
            return q.ask if intent.side is Side.BUY_TO_OPEN else q.bid
        if intent.order_type is OrderType.STOP:
            return intent.stop_price if intent.stop_price is not None else q.bid
        limit = intent.limit if intent.limit is not None else q.ask
        # A buy never pays more than its limit and never more than the offer;
        # a sell never takes less than its limit and never less than the bid.
        return min(limit, q.ask) if intent.side is Side.BUY_TO_OPEN else max(limit, q.bid)

    def _new_order(self, intent: OrderIntent, status: OrderStatus, *,
                   price: float | None = None, filled_qty: int = 0,
                   fill_price: float | None = None, message: str = "") -> OrderResult:
        self._seq += 1
        return OrderResult(
            order_id=f"mock-{self._seq:04d}", status=status, symbol=intent.symbol,
            side=intent.side, qty=intent.qty, order_type=intent.order_type,
            price=price, filled_qty=filled_qty, fill_price=fill_price,
            submitted_at=self.clock(), message=message,
        )

    def _store(self, order: OrderResult) -> OrderResult:
        self._orders[order.order_id] = order
        return order

    def _apply_fill(self, order: OrderResult) -> None:
        price = order.fill_price if order.fill_price is not None else 0.0
        signed = order.filled_qty if order.side is Side.BUY_TO_OPEN else -order.filled_qty
        held = self._positions.get(order.symbol)
        if held is None:
            self._positions[order.symbol] = Position(order.symbol, signed, price)
        else:
            new_qty = held.qty + signed
            if new_qty == 0:
                self._positions.pop(order.symbol, None)
            else:
                self._positions[order.symbol] = Position(order.symbol, new_qty, held.avg_price)
        self._fills.append(Fill(order.order_id, order.symbol, order.side,
                                order.filled_qty, price, self.clock()))
