"""FaultBook — the paper book, with the broker behaviours it does not model. [st-ug1h]

``PaperBroker`` is honest about what it simulates and what it does not: it
fills an order whole, in one print, and its cancels and reads always
answer. Schwab does not always. The audit of 2026-10-01 found service
defects that only those behaviours reach, so a scenario that needs one asks
for it by name here — every knob is off by default, and with every knob off
this class is ``PaperBroker`` exactly (``test_harness.py`` pins that).

Knobs, each consumed or standing as noted:

``lose_answer``
    The next ``place`` / ``place_triggered`` is taken by the book and then
    the answer is lost: the order rests (or fills) and the caller gets a
    ``BrokerError`` — a POST that timed out after Schwab took it.
``children_fail``
    ``children_of`` raises this many times — the GET of the triggered
    order's children timing out.
``hide_target``
    ``children_of`` answers the stop and no target this many times — a
    child listing that has not caught up.
``pending_cancel``
    Order ids, or the predicate ``pending_cancel_if(order)``, whose cancel
    is acknowledged and not done: the order stays WORKING with the message
    ``PENDING_CANCEL`` until ``resolve_pending`` (Schwab's DELETE is an ask).
``partial``
    ``{"side": Side, "first": k, "hold_s": s}``: the next order on that side
    that fills does so for ``k`` contracts first, stays WORKING with
    ``filled_qty = k``, and fills the rest on the first sweep ``s`` seconds
    or more later.
``split_prints``
    A sell of two or more contracts fills in two prints (two ``Fill`` s for
    one order), ``print_gap_ms`` apart — 0 is the same millisecond.

``outside_fill`` books an execution the service did not send (a leg Steve
traded in TOS) straight into the fills list, for the sweep to find.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any, Callable

from execd.broker import BrokerError, Fill, OrderLeg, OrderResult, OrderStatus, Position
from execd.intent import OrderIntent, OrderType, Side
from execd.paper import PaperBroker


class FaultBook(PaperBroker):
    def __init__(self, live, **kw: Any) -> None:
        self.lose_answer = False
        self.children_fail = 0
        self.hide_target = 0
        self.pending_cancel: set[str] = set()
        self.pending_cancel_if: Callable[[OrderResult], bool] | None = None
        self.partial: dict[str, Any] | None = None
        self.split_prints = False
        self.print_gap_ms = 0
        self._partials: dict[str, tuple[int, Any]] = {}
        self._outside_seq = 0
        super().__init__(live, **kw)

    # ── answers lost ─────────────────────────────────────────────────────
    def place(self, intent: OrderIntent) -> OrderResult:
        out = super().place(intent)
        if self.lose_answer and intent.side is Side.BUY_TO_OPEN:
            self.lose_answer = False
            raise BrokerError("POST orders: ReadTimeout (the book took it; the answer is lost)")
        return out

    def place_triggered(self, entry: OrderIntent, stop: OrderIntent,
                        target: OrderIntent) -> OrderResult:
        lose, self.lose_answer = self.lose_answer, False
        out = super().place_triggered(entry, stop, target)
        if lose:
            raise BrokerError("POST orders: ReadTimeout (the book took it; the answer is lost)")
        return out

    def children_of(self, order_id: str):
        if self.children_fail:
            self.children_fail -= 1
            raise BrokerError("GET order: ReadTimeout")
        stop, target = super().children_of(order_id)
        if self.hide_target and target is not None:
            self.hide_target -= 1
            return stop, None
        return stop, target

    # ── cancels that are only acknowledged ───────────────────────────────
    def _pending(self, order: OrderResult) -> bool:
        return order.order_id in self.pending_cancel or bool(
            self.pending_cancel_if is not None and self.pending_cancel_if(order))

    def cancel(self, order_id: str) -> OrderResult:
        with self._lock:
            self._sweep()
            order = self._orders.get(order_id)
            if order is not None and order.status is OrderStatus.WORKING and self._pending(order):
                held = replace(order, message="PENDING_CANCEL")
                self._orders[order_id] = held
                self._save()
                return held
        return super().cancel(order_id)

    def resolve_pending(self, order_id: str) -> OrderResult:
        self.pending_cancel.discard(order_id)
        with self._lock:
            order = self._orders[order_id]
            if order.status is OrderStatus.WORKING:
                self._orders[order_id] = replace(order, status=OrderStatus.CANCELED, message="")
                self._pending_children.pop(order_id, None)
                self._save()
            return self._orders[order_id]

    # ── fills in more than one print ─────────────────────────────────────
    def _fill(self, order: OrderResult, price: float) -> OrderResult:
        oid = order.order_id
        if oid in self._partials:
            done, at = self._partials[oid]
            if self.clock() < at:
                return order                      # the rest is not there yet
            del self._partials[oid]
            rest = order.qty - done
            filled = super()._fill(replace(order, qty=rest, filled_qty=0), price)
            whole = replace(filled, qty=order.qty, filled_qty=order.qty)
            self._orders[oid] = whole
            self._save()
            return whole
        p = self.partial
        if p and order.side is p["side"] and order.filled_qty == 0 and order.qty > p["first"]:
            self.partial = None
            k = int(p["first"])
            part = replace(order, status=OrderStatus.WORKING, filled_qty=k,
                           fill_price=round(float(price), 2))
            self._orders[oid] = part
            self._cancel_partner(oid, self._oco.get(oid))
            self._move(order.symbol, order.side, k, price)
            self._fills.append(Fill(oid, order.symbol, order.side, k, round(float(price), 2),
                                    self.clock(), leg_id=1, instruction=order.side.value))
            self._partials[oid] = (k, self.clock() + timedelta(seconds=float(p["hold_s"])))
            self._save()
            return part
        filled = super()._fill(order, price)
        if self.split_prints and filled.side is Side.SELL_TO_CLOSE and filled.qty >= 2:
            last = self._fills.pop()
            first = filled.qty // 2
            self._fills.append(replace(last, qty=first))
            self._fills.append(replace(last, qty=filled.qty - first,
                                       at=last.at + timedelta(milliseconds=self.print_gap_ms)))
        return filled

    def _move(self, symbol: str, side: Side, qty: int, price: float) -> None:
        signed = qty if side is Side.BUY_TO_OPEN else -qty
        held = self._positions.get(symbol)
        if held is None:
            self._positions[symbol] = Position(symbol, signed, round(float(price), 2))
        elif held.qty + signed == 0:
            self._positions.pop(symbol, None)
        else:
            self._positions[symbol] = Position(symbol, held.qty + signed, held.avg_price)

    # ── an execution from outside the service ────────────────────────────
    def outside_fill(self, symbol: str, qty: int, price: float, *,
                     instruction: str = "SELL_TO_OPEN") -> str:
        """A fill the service did not send, as the transport reports it: a
        ``SELL_*`` instruction reduces to ``SELL_TO_CLOSE`` on ``side``
        (``execd.schwab._side_of``), the broker's own word on the leg.
        The book's positions are not touched — it is Steve's account's leg,
        not the paper book's."""
        self._outside_seq += 1
        oid = f"tos-{self._outside_seq:04d}"
        side = Side.SELL_TO_CLOSE if instruction.startswith("SELL") else Side.BUY_TO_OPEN
        now = self.clock()
        self._orders[oid] = OrderResult(
            order_id=oid, status=OrderStatus.FILLED, symbol=symbol, side=side, qty=qty,
            order_type=OrderType.LIMIT, price=price, filled_qty=qty, fill_price=price,
            submitted_at=now, legs=(OrderLeg(symbol=symbol, instruction=instruction,
                                             side=side, qty=qty, leg_id=1),))
        self._fills.append(Fill(oid, symbol, side, qty, price, now, leg_id=1,
                                instruction=instruction))
        return oid
