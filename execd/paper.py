"""PaperBroker — everything live except the order. [st-k6gl]

Steve, 2026-09-14: "since schwab doesn't support paper trading via api I'd
like to simulate one by defining a mode where every api submission is live
except anything that submits a live order."

This wraps the real transport. Every read — quotes, chains, the raw market
reads, the account, the token walls — and the broker's own **preview** go to
Schwab exactly as in live mode. The four calls that would change the account
never reach it:

``place``
    A limit buy fills at once when the live offer is at or under the limit
    (at the offer, never above the limit), else it rests. A market order
    fills at once at the live touch. A stop rests. Nothing rests without a
    live quote — a simulation with no market is not a simulation.
``cancel``
    Resting → CANCELED. Already filled → reported as filled, the race the
    service is built to survive.
``orders`` / ``positions`` / ``fills_since``
    The paper book, never the account. Steve's own spreads in the real
    account are invisible here on purpose: paper must not adopt, watch or
    flatten what it did not open.

Resting orders are swept against live quotes on every read: a resting buy
fills when the offer comes down to it; a resting stop triggers once the
**mid** is at or under the stop price and then fills at the bid, which is
where a market sell lands. The mid, not the bid, because that is the basis
the live order names — ``stopType: MARK`` — and a stop the two surfaces
trigger differently is not a simulation of it (st-qb7w). That is what lets
the service's own loop — the watcher, reconcile, the fill sweep — run
unchanged over paper.

The book persists as JSON so a restart recovers it the way the journal
recovers the day: the service asks the broker what is held, and the answer
must not be "nothing" just because the process restarted.

Every journal line, status body and desk read-back says ``paper`` while this
is the broker, so a simulated fill can never read as a real one.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .broker import (
    Broker, BrokerError, Fill, OrderLeg, OrderResult, OrderStatus, Position,
    Preview, Quote,
)
from .bounds import CT
from .intent import OrderIntent, OrderType, Side, parse_occ

log = logging.getLogger("execd.paper")

MODE = "paper"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _mid(q: Quote) -> float:
    """The midpoint of bid and offer — what triggers a protective stop here.

    Until 2026-09-19 the book triggered a stop on the bid while the live
    order named no basis at all and ran on the account default, so the two
    surfaces disagreed by the width of the spread: the bid is the lowest of
    the three, so a bid-triggered sell stop fires first (st-qb7w). Steve:
    "convention is to use 'mid'. split the diff between bid and offer."
    Live sends that basis as ``stopType: MARK``
    (:data:`execd.schwab.STOP_TRIGGER`).

    One-sided quotes fall back to whichever side is there; a stop is never
    triggered off a side that is not quoted.
    """
    if q.bid > 0 and q.ask > 0:
        return (q.bid + q.ask) / 2.0
    return q.ask if q.ask > 0 else q.bid


class PaperBroker:
    def __init__(self, live: Broker, *, book_path: str | Path | None = None,
                 clock: Callable[[], datetime] = _utcnow) -> None:
        self.live = live
        self.book_path = Path(book_path) if book_path else None
        self.clock = clock
        self._lock = threading.RLock()
        self._orders: dict[str, OrderResult] = {}
        self._positions: dict[str, Position] = {}
        self._fills: list[Fill] = []
        self._seq = 0
        self._load()

    # ── pass-through: every read, and the broker's own preview ───────────
    def __getattr__(self, name: str) -> Any:
        # bind, bind_market, close, token_status, account_hash — whatever the
        # live transport offers beyond the Broker protocol, unchanged.
        return getattr(self.live, name)

    def quote(self, symbol: str) -> Quote:
        return self.live.quote(symbol)

    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]:
        return self.live.chain(root, expiry)

    def market_read(self, kind: str, params: dict[str, str]) -> Any:
        return self.live.market_read(kind, params)

    def preview(self, intent: OrderIntent) -> Preview:
        return self.live.preview(intent)

    # ── the book ─────────────────────────────────────────────────────────
    def place(self, intent: OrderIntent) -> OrderResult:
        with self._lock:
            q = self._quote_or_raise(intent.symbol)
            if intent.order_type is OrderType.STOP:
                order = self._new(intent, OrderStatus.WORKING, price=intent.stop_price)
                return self._store(order)
            if intent.order_type is OrderType.LIMIT:
                limit = float(intent.limit or 0.0)
                if intent.side is Side.BUY_TO_OPEN and q.ask > limit:
                    return self._store(self._new(intent, OrderStatus.WORKING, price=limit))
                if intent.side is Side.SELL_TO_CLOSE and q.bid < limit:
                    return self._store(self._new(intent, OrderStatus.WORKING, price=limit))
                px = min(limit, q.ask) if intent.side is Side.BUY_TO_OPEN else max(limit, q.bid)
                return self._fill(self._new(intent, OrderStatus.WORKING, price=limit), px)
            px = q.ask if intent.side is Side.BUY_TO_OPEN else q.bid
            return self._fill(self._new(intent, OrderStatus.WORKING), px)

    def cancel(self, order_id: str) -> OrderResult:
        with self._lock:
            self._sweep()
            order = self._orders.get(order_id)
            if order is None:
                raise BrokerError(f"paper: no such order: {order_id}")
            if order.status is not OrderStatus.WORKING:
                return order
            canceled = replace(order, status=OrderStatus.CANCELED)
            self._orders[order_id] = canceled
            self._save()
            return canceled

    def orders(self) -> list[OrderResult]:
        with self._lock:
            self._sweep()
            return list(self._orders.values())

    def positions(self) -> list[Position]:
        with self._lock:
            self._sweep()
            return [p for p in self._positions.values() if p.qty != 0]

    def fills_since(self, since: datetime) -> list[Fill]:
        with self._lock:
            self._sweep()
            return [f for f in self._fills if f.at > since]

    # ── internals ────────────────────────────────────────────────────────
    def _quote_or_raise(self, symbol: str) -> Quote:
        try:
            q = self.live.quote(symbol)
        except BrokerError as exc:
            raise BrokerError(f"paper: no live quote for {symbol} — nothing simulated ({exc})") from exc
        if q.bid <= 0 and q.ask <= 0:
            raise BrokerError(f"paper: the live quote for {symbol} is empty — nothing simulated")
        return q

    def _sweep(self) -> None:
        """Resting orders against live quotes. A quote that cannot be read
        leaves that order resting; the next read tries again."""
        self._expire()
        # One live read per symbol per sweep: a bracket is two resting orders
        # on one contract, and every cancel runs a sweep first, so a moved
        # leg was paying for two Schwab quotes it did not need — 1.2 s of the
        # 3 s an UPDATE took on 2026-09-15 (st-bmaz).
        quotes: dict[str, Quote | None] = {}
        for order in list(self._orders.values()):
            if order.status is not OrderStatus.WORKING:
                continue
            if order.symbol not in quotes:
                try:
                    quotes[order.symbol] = self.live.quote(order.symbol)
                except BrokerError as exc:
                    log.warning("paper: sweep skipped %s — %s", order.symbol, exc)
                    quotes[order.symbol] = None
            q = quotes[order.symbol]
            if q is None:
                continue
            if order.order_type is OrderType.STOP:
                trigger = _mid(q)   # not the bid — live triggers on MARK [st-qb7w]
                if order.price is not None and 0 < trigger <= order.price and q.bid > 0:
                    self._fill(order, q.bid)
            elif order.order_type is OrderType.LIMIT and order.price is not None:
                if order.side is Side.BUY_TO_OPEN and 0 < q.ask <= order.price:
                    self._fill(order, q.ask)
                elif order.side is Side.SELL_TO_CLOSE and q.bid >= order.price:
                    self._fill(order, q.bid)
            else:  # a market order that somehow rested — fill at the touch
                px = q.ask if order.side is Side.BUY_TO_OPEN else q.bid
                if px > 0:
                    self._fill(order, px)

    def _expire(self) -> None:
        """What the exchange does at the close and the book did not: a
        resting order in a contract that has expired is gone, and a position
        in one is worth nothing. Until 2026-09-15 the book carried both into
        the next day and swept them against a quote for a contract that no
        longer existed (finding 33 of the audit, st-ee8f). An order expires
        as CANCELED with the word ``expired``; a position leaves the book
        through a SELL_TO_CLOSE fill at 0.00 so the service books the loss
        the way it books any other close."""
        today = self.clock().astimezone(CT).date()
        changed = False
        for order in list(self._orders.values()):
            if order.status is not OrderStatus.WORKING:
                continue
            try:
                expiry = parse_occ(order.symbol).expiry
            except ValueError:
                continue
            if expiry < today:
                self._orders[order.order_id] = replace(order, status=OrderStatus.CANCELED,
                                                       message="expired")
                changed = True
                log.warning("paper: %s expired unfilled (%s, %s)", order.order_id,
                            order.symbol.strip(), expiry)
        for symbol, held in list(self._positions.items()):
            try:
                expiry = parse_occ(symbol).expiry
            except ValueError:
                continue
            if expiry >= today or held.qty == 0:
                continue
            self._seq += 1
            oid = f"paper-expiry-{self._seq:04d}"
            side = Side.SELL_TO_CLOSE if held.qty > 0 else Side.BUY_TO_OPEN
            self._orders[oid] = OrderResult(
                order_id=oid, status=OrderStatus.FILLED, symbol=symbol, side=side,
                qty=abs(held.qty), order_type=OrderType.MARKET, price=None,
                filled_qty=abs(held.qty), fill_price=0.0, submitted_at=self.clock(),
                message="expired worthless",
                legs=(OrderLeg(symbol=symbol, instruction=side.value, side=side,
                               qty=abs(held.qty), leg_id=1),))
            self._fills.append(Fill(oid, symbol, side, abs(held.qty), 0.0, self.clock(),
                                    leg_id=1, instruction=side.value))
            self._positions.pop(symbol, None)
            changed = True
            log.warning("paper: %s × %d expired worthless (%s)", symbol.strip(), held.qty, expiry)
        if changed:
            self._save()

    def _new(self, intent: OrderIntent, status: OrderStatus, *,
             price: float | None = None) -> OrderResult:
        self._seq += 1
        return OrderResult(
            order_id=f"paper-{self._seq:04d}", status=status, symbol=intent.symbol,
            side=intent.side, qty=intent.qty, order_type=intent.order_type,
            price=price, submitted_at=self.clock(),
            legs=(OrderLeg(symbol=intent.symbol, instruction=intent.side.value,
                           side=intent.side, qty=intent.qty, leg_id=1),),
        )

    def _store(self, order: OrderResult) -> OrderResult:
        self._orders[order.order_id] = order
        self._save()
        return order

    def _fill(self, order: OrderResult, price: float) -> OrderResult:
        filled = replace(order, status=OrderStatus.FILLED, filled_qty=order.qty,
                         fill_price=round(float(price), 2))
        self._orders[filled.order_id] = filled
        signed = filled.qty if filled.side is Side.BUY_TO_OPEN else -filled.qty
        held = self._positions.get(filled.symbol)
        if held is None:
            self._positions[filled.symbol] = Position(filled.symbol, signed, filled.fill_price or 0.0)
        else:
            new_qty = held.qty + signed
            if new_qty == 0:
                self._positions.pop(filled.symbol, None)
            else:
                self._positions[filled.symbol] = Position(filled.symbol, new_qty, held.avg_price)
        self._fills.append(Fill(filled.order_id, filled.symbol, filled.side, filled.qty,
                                filled.fill_price or 0.0, self.clock(), leg_id=1,
                                instruction=filled.side.value))
        self._save()
        return filled

    # ── persistence ──────────────────────────────────────────────────────
    def _save(self) -> None:
        if self.book_path is None:
            return
        data = {
            "seq": self._seq,
            "orders": [{**o.to_dict()} for o in self._orders.values()],
            "positions": [p.to_dict() for p in self._positions.values()],
            "fills": [{"order_id": f.order_id, "symbol": f.symbol, "side": f.side.value,
                       "qty": f.qty, "price": f.price, "at": _iso(f.at)} for f in self._fills],
        }
        try:
            self.book_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.book_path.with_suffix(self.book_path.suffix + ".partial")
            tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            tmp.replace(self.book_path)
        except OSError as exc:
            log.error("paper: could not save the book to %s: %s", self.book_path, exc)

    def _load(self) -> None:
        if self.book_path is None or not self.book_path.is_file():
            return
        try:
            data = json.loads(self.book_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # A book that cannot be read is an error, not a fresh start — a
            # fresh start would forget an open paper position.
            raise BrokerError(f"paper: the book at {self.book_path} cannot be read: {exc}") from exc
        self._seq = int(data.get("seq", 0))
        for o in data.get("orders", []):
            self._orders[o["order_id"]] = OrderResult(
                order_id=o["order_id"], status=OrderStatus(o["status"]), symbol=o["symbol"],
                side=Side(o["side"]), qty=int(o["qty"]), order_type=OrderType(o["order_type"]),
                price=o.get("price"), filled_qty=int(o.get("filled_qty") or 0),
                fill_price=o.get("fill_price"), submitted_at=_from_iso(o["submitted_at"]),
                message=o.get("message", ""),
                legs=tuple(OrderLeg(symbol=l["symbol"], instruction=l["instruction"],
                                    side=Side(l["side"]), qty=int(l["qty"]), leg_id=l.get("leg_id"))
                           for l in o.get("legs", [])))
        for p in data.get("positions", []):
            self._positions[p["symbol"]] = Position(p["symbol"], int(p["qty"]), float(p["avg_price"]))
        for f in data.get("fills", []):
            self._fills.append(Fill(f["order_id"], f["symbol"], Side(f["side"]), int(f["qty"]),
                                    float(f["price"]), _from_iso(f["at"]), leg_id=1,
                                    instruction=f["side"]))
        log.info("paper: book loaded from %s — %d orders, %d positions",
                 self.book_path, len(self._orders), len(self._positions))


#: The page's own mode switch, in the instance's state directory (co-8mb1z).
MODE_STATE_FILE = "mode"
MODES = ("paper", "live")


def current_mode(seed_path: str | Path, state_dir: str | Path) -> str:
    """The mode this instance runs in, by precedence:

    1. ``<state-dir>/mode`` — written by the page's PAPER/LIVE switch (Steve,
       2026-09-25: "support moving between paper and live without need to
       re-run the installer"). The service owns this file, so the switch
       works with no install and survives a restart.
    2. the seed file (``/etc/execd/mode``, ``/etc/execd-alpaca/mode``) —
       Steve's, root-owned, read-only to the service; it decides the mode
       until the page has been used once.
    3. ``paper``.

    A state file holding anything but ``paper`` or ``live`` is ignored (with
    a log line) rather than trusted — the seed decides then."""
    state = Path(state_dir) / MODE_STATE_FILE
    try:
        word = state.read_text(encoding="utf-8").strip().lower()
    except OSError:
        word = ""
    if word in MODES:
        return word
    if word:
        log.error("mode: %s holds %r — ignored; the seed file decides", state, word)
    return read_mode(seed_path)


def write_mode(state_dir: str | Path, mode: str) -> None:
    """Persist the page's switch: write, fsync, rename."""
    if mode not in MODES:
        raise ValueError(f"mode must be paper or live, not {mode!r}")
    state = Path(state_dir) / MODE_STATE_FILE
    state.parent.mkdir(parents=True, exist_ok=True)
    tmp = state.with_name(f".{state.name}.partial")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(mode + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(state)


class ModeSwitch:
    """Two brokers, one per mode, and the one in use (co-8mb1z).

    The service holds this in place of a single broker, so a flip on the page
    changes where every call goes at once: ``mode`` is set by
    :meth:`execd.service.ExecService.set_mode` and nothing else. On Schwab
    the paper side is the :class:`PaperBroker` book over the same transport
    the live side uses; on Alpaca the two sides are its paper and live
    venues. Anything beyond the Broker protocol (``bind``, ``token_status``,
    ``balances``, ``excluded_positions``) is the current side's."""

    def __init__(self, paper: Broker, live: Broker, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be paper or live, not {mode!r}")
        self.__dict__["brokers"] = {"paper": paper, "live": live}
        self.__dict__["mode"] = mode

    @property
    def current(self) -> Broker:
        return self.brokers[self.mode]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.brokers[self.__dict__["mode"]], name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "mode" and value not in MODES:
            raise ValueError(f"mode must be paper or live, not {value!r}")
        self.__dict__[name] = value

    def quote(self, symbol: str) -> Quote:
        return self.current.quote(symbol)

    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]:
        return self.current.chain(root, expiry)

    def market_read(self, kind: str, params: dict[str, str]) -> Any:
        return self.current.market_read(kind, params)

    def preview(self, intent: OrderIntent) -> Preview:
        return self.current.preview(intent)

    def place(self, intent: OrderIntent) -> OrderResult:
        return self.current.place(intent)

    def cancel(self, order_id: str) -> OrderResult:
        return self.current.cancel(order_id)

    def orders(self) -> list[OrderResult]:
        return self.current.orders()

    def positions(self) -> list[Position]:
        return self.current.positions()

    def fills_since(self, since: datetime) -> list[Fill]:
        return self.current.fills_since(since)


def read_mode(path: str | Path) -> str:
    """``paper`` or ``live`` from Steve's mode file. Absent → ``paper``: the
    safe default is the one that cannot send. Anything else is a start-up
    error rather than a guess."""
    p = Path(path)
    if not p.exists():
        return MODE
    word = p.read_text(encoding="utf-8").strip().lower()
    if word not in ("paper", "live"):
        raise ValueError(f"{p}: expected 'paper' or 'live', found {word!r}")
    return word
