"""ExecService — the narrow door, and everything behind it. [st-eznu]

One object holds the whole service: the arming state, the journal, the bounds,
the broker seam, and the open position. Every path that can transmit runs
through :meth:`place`, and :meth:`place` runs through the bounds. There is no
second way in; the HTTP layer in ``execd.api`` is a translator over this class
and holds no policy of its own, which is why the bounds can be tested without
a socket.

Three asymmetries are deliberate and each has a test:

**Entries are hard, exits are easy.** An entry clears arming, the STOP file,
the session window, the position limit, the daily ceiling, a price band and a
preview whose cost agrees with the intent. An exit clears that the contract is
one this service trades and that the side really closes. Nothing that exists to
keep Steve out of risk may keep him in it.

**A fill without a protective stop is a state this service does not reach.**
The stop's inputs are checked before the entry is previewed, so an intent that
could not produce a resting stop is refused while refusing is still free. The
stop is placed the moment the fill comes back, and the placement is journaled
whether it succeeds or fails — a failure there is loud, because the position
is live and unprotected until the SPX-mark loop or Steve deals with it.

**The day's ceiling is read from the journal, not remembered.** A restart
recovers it. See ``execd.journal``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .arming import Arming
from .bounds import (
    CT, Bounds, DayState, QuoteView, Refusal, check_entry, check_exit,
    check_preview_cost, session_close,
)
from .broker import Broker, BrokerError, OrderResult, OrderStatus, Position, Quote
from .intent import OrderIntent, OrderType, Side, parse_occ
from .journal import Journal
from .stops import (
    CONTRACT_MULTIPLIER, exit_triggered, protective_stop_price, risk_usd,
    stop_is_consistent,
)


class Refused(Exception):
    """A bound said no. Carries the bound so the caller can name it."""

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(f"{refusal.bound}: {refusal.reason}")
        self.refusal = refusal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ServiceConfig:
    state_dir: Path
    bounds: Bounds = field(default_factory=Bounds)
    sha: str = "unknown"
    index_symbol: str = "$SPX"

    def __post_init__(self) -> None:
        self.state_dir = Path(self.state_dir)
        self.bounds = self.bounds.validated()


@dataclass
class OpenPosition:
    """What the service must remember about a live position to protect it."""

    symbol: str
    qty: int
    entry_price: float
    intent_id: str
    right: str
    stop_spx: float | None = None
    delta: float | None = None
    stop_order_id: str | None = None
    stop_price: float | None = None
    entry_order_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "qty": self.qty, "entry_price": self.entry_price,
            "intent_id": self.intent_id, "right": self.right,
            "stop_spx": self.stop_spx, "delta": self.delta,
            "stop_order_id": self.stop_order_id, "stop_price": self.stop_price,
            "entry_order_id": self.entry_order_id,
        }


class ExecService:
    def __init__(self, broker: Broker, config: ServiceConfig,
                 clock: Callable[[], datetime] = _utcnow) -> None:
        self.broker = broker
        self.config = config
        self.clock = clock
        self.bounds = config.bounds
        state = Path(config.state_dir)
        state.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(state / "journal", sha=config.sha, clock=clock)
        self.arming = Arming(state / "STOP", clock=clock)
        self._lock = threading.RLock()
        self._open: dict[str, OpenPosition] = {}
        self._last_fill_poll = clock()
        self._recover()

    # ── arming (page-only; none of these has an API route) ───────────────
    def unlock(self, credential: Any, until: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            expiry = until or session_close(self.clock(), self.bounds)
            state = self.arming.unlock(credential, expiry)
            self.journal.record("unlock", state=state.value, until=expiry)
            return self.status()

    def stand_down(self) -> dict[str, Any]:
        with self._lock:
            state = self.arming.stand_down()
            self.journal.record("stand_down", state=state.value)
            return self.status()

    def lock(self) -> dict[str, Any]:
        with self._lock:
            state = self.arming.lock()
            self.journal.record("lock", state=state.value)
            return self.status()

    def stop(self) -> dict[str, Any]:
        """STOP on. Reachable from the API and from Steve's phone: turning the
        kill switch on is the one control that must never be gated."""
        with self._lock:
            self.arming.stop()
            self.journal.record("stop", killed=True)
            return self.status()

    def resume(self) -> dict[str, Any]:
        """STOP off. Page-only — an agent must not be able to undo the switch."""
        with self._lock:
            self.arming.resume()
            self.journal.record("resume", killed=False)
            return self.status()

    # ── reads ────────────────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        now = self.clock()
        day = self.day_state()
        return {
            "now": now.isoformat(),
            "now_ct": now.astimezone(CT).strftime("%Y-%m-%d %H:%M:%S CT"),
            "sha": self.config.sha,
            "arming": self.arming.status(),
            "day": {
                "open_positions": day.open_positions,
                "realized_loss_usd": day.realized_loss_usd,
                "attempts_used": day.attempts_used,
                "attempts_left": max(0, self.bounds.max_attempts - day.attempts_used),
                "loss_headroom_usd": round(
                    max(0.0, self.bounds.daily_loss_ceiling_usd - day.realized_loss_usd), 2),
            },
            "positions": [p.to_dict() for p in self._open.values()],
            "bounds": self.bounds.to_dict(),
            "journal": str(self.journal.path_for()),
        }

    def day_state(self) -> DayState:
        return self.journal.day_state()

    def quote(self, symbol: str) -> Quote:
        return self.broker.quote(symbol)

    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]:
        return self.broker.chain(root, expiry)

    def orders(self) -> list[OrderResult]:
        return self.broker.orders()

    def positions(self) -> list[Position]:
        return self.broker.positions()

    def spx_mark(self) -> float:
        """The index level the stops are denominated in."""
        q = self.broker.quote(self.config.index_symbol)
        return q.last or q.mid

    # ── preview ──────────────────────────────────────────────────────────
    def preview(self, intent: OrderIntent) -> dict[str, Any]:
        """Price an intent through every bound without sending anything."""
        with self._lock:
            intent = intent.validated()
            self.journal.record("request", kind="preview", intent_id=intent.intent_id,
                                intent=intent.to_dict())
            refusal = self._entry_refusal(intent) if intent.is_entry else self._exit_refusal(intent)
            if refusal is not None:
                return self._refuse(intent, refusal, kind="preview")
            prev = self.broker.preview(intent)
            self.journal.record("preview", intent_id=intent.intent_id,
                                preview=prev.to_dict())
            return {"refused": None, "preview": prev.to_dict(), "would_send": prev.accepted}

    # ── the one path that transmits ──────────────────────────────────────
    def place(self, intent: OrderIntent) -> dict[str, Any]:
        with self._lock:
            intent = intent.validated()

            replay = self._replay(intent.intent_id)
            if replay is not None:
                self.journal.record("replayed", intent_id=intent.intent_id,
                                    order_id=replay.get("order", {}).get("order_id"))
                return {**replay, "replayed": True}

            self.journal.record("request", kind="place", intent_id=intent.intent_id,
                                intent=intent.to_dict())
            if intent.is_entry:
                return self._place_entry(intent)
            return self._place_exit(intent)

    def cancel(self, order_id: str) -> dict[str, Any]:
        """Cancelling is getting out of the way of an order, so it is an exit-
        class action: legal whenever there is a credential."""
        with self._lock:
            if (r := self.arming.permits_exit()) is not None:
                self.journal.record("refused", kind="cancel", order_id=order_id,
                                    refused=r.to_dict())
                raise Refused(r)
            result = self.broker.cancel(order_id)
            self.journal.record("canceled", order_id=order_id, order=result.to_dict())
            for pos in self._open.values():
                if pos.stop_order_id == order_id:
                    pos.stop_order_id = None
            return {"refused": None, "order": result.to_dict()}

    def flatten(self, reason: str = "flatten") -> dict[str, Any]:
        """Close everything at market. Legal while STOPped, while stood down,
        and outside the session window — the whole point of the switch is that
        it never traps him."""
        with self._lock:
            if (r := self.arming.permits_exit()) is not None:
                self.journal.record("refused", kind="flatten", refused=r.to_dict())
                raise Refused(r)
            self.journal.record("request", kind="flatten", reason=reason,
                                positions=[p.symbol for p in self._open.values()])
            closed: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            for pos in list(self._open.values()):
                try:
                    closed.append(self._market_close(pos, reason=reason))
                except (BrokerError, Refused) as exc:
                    self.journal.record("error", kind="flatten", symbol=pos.symbol,
                                        detail=str(exc))
                    errors.append({"symbol": pos.symbol, "detail": str(exc)})
            self.journal.record("flattened", closed=len(closed), errors=len(errors),
                                reason=reason)
            return {"refused": None, "closed": closed, "errors": errors}

    # ── the live exit loop ───────────────────────────────────────────────
    def observe(self, spx: float) -> dict[str, Any]:
        """Feed the service the index mark. Fires the SPX-level exit FD0 derived.

        This is the accurate stop while the box is alive; the resting order at
        the broker is the one that survives it not being."""
        with self._lock:
            fired: list[dict[str, Any]] = []
            for pos in list(self._open.values()):
                if pos.stop_spx is None:
                    continue
                if exit_triggered(pos.right, spx, pos.stop_spx):
                    self.journal.record("exit_triggered", symbol=pos.symbol,
                                        spx=spx, stop_spx=pos.stop_spx,
                                        intent_id=pos.intent_id)
                    fired.append(self._market_close(pos, reason="spx-stop"))
            return {"spx": spx, "fired": fired}

    def poll_fills(self) -> dict[str, Any]:
        """Pick up fills the service did not initiate — a resting protective
        stop that triggered while nothing was watching."""
        with self._lock:
            since = self._last_fill_poll
            now = self.clock()
            try:
                fills = self.broker.fills_since(since)
            except BrokerError as exc:
                self.journal.record("error", kind="poll_fills", detail=str(exc))
                return {"picked_up": [], "error": str(exc)}
            self._last_fill_poll = now
            picked: list[dict[str, Any]] = []
            for fill in fills:
                pos = self._open.get(fill.symbol)
                if pos is None or fill.side is not Side.SELL_TO_CLOSE:
                    continue
                if pos.stop_order_id and fill.order_id != pos.stop_order_id:
                    continue
                closed_qty = min(fill.qty or pos.qty, pos.qty)
                remaining = pos.qty - closed_qty
                pnl = self._pnl_usd(pos, fill.price, closed_qty)
                self.journal.record("closed", symbol=pos.symbol, qty=closed_qty,
                                    remaining_qty=remaining, intent_id=pos.intent_id,
                                    kind="protective-stop", entry_price=pos.entry_price,
                                    exit_price=fill.price, pnl_usd=pnl,
                                    order_id=fill.order_id, reason="resting-stop")
                if remaining:
                    # The stop that fired took part of the position; what is
                    # left needs one of its own or it is running naked.
                    pos.qty = remaining
                    self._rest_stop_at(pos, pos.stop_price)
                else:
                    self._open.pop(pos.symbol, None)
                picked.append({"symbol": pos.symbol, "exit_price": fill.price,
                               "pnl_usd": pnl, "remaining_qty": remaining,
                               "order_id": fill.order_id})
            return {"picked_up": picked}

    # ── internals: the entry ─────────────────────────────────────────────
    def _entry_refusal(self, intent: OrderIntent) -> Refusal | None:
        if (r := self.arming.permits_entry()) is not None:
            return r
        quote = self._quote_view(intent.symbol)
        r = check_entry(intent, self.bounds, self.day_state(), quote,
                        self.clock(), killed=self.arming.killed)
        if r is not None:
            return r
        return self._protective_stop_refusal(intent)

    def _protective_stop_refusal(self, intent: OrderIntent) -> Refusal | None:
        """Everything the resting stop needs, checked while refusing is free."""
        if not self.bounds.require_protective_stop:
            return None
        try:
            spx = self.spx_mark()
        except BrokerError as exc:
            return Refusal("protective_stop",
                           f"no {self.config.index_symbol} mark — cannot derive a stop ({exc})")
        if intent.stop_spx is None or intent.delta is None:
            # check_entry already refuses this; repeated rather than asserted
            # because `python -O` strips asserts and this one guards money.
            return Refusal(
                "protective_stop",
                "an entry must carry stop_spx and delta — the broker-resident "
                "stop is derived from them and is not optional",
            )
        if not stop_is_consistent(intent.occ.right, spx, intent.stop_spx):
            return Refusal(
                "protective_stop",
                f"a {intent.occ.right_word} stop at {intent.stop_spx:g} is already "
                f"triggered with SPX at {spx:g} — the sign is transposed",
            )
        return None

    def _place_entry(self, intent: OrderIntent) -> dict[str, Any]:
        if (refusal := self._entry_refusal(intent)) is not None:
            return self._refuse(intent, refusal, kind="place")

        try:
            prev = self.broker.preview(intent)
        except BrokerError as exc:
            self.journal.record("error", kind="preview", intent_id=intent.intent_id,
                                detail=str(exc))
            raise
        self.journal.record("preview", intent_id=intent.intent_id, preview=prev.to_dict())
        if not prev.accepted:
            return self._refuse(
                intent,
                Refusal("preview_cost", "the broker would not accept this order: "
                                        + "; ".join(prev.messages or ("no reason given",))),
                kind="place")
        if (r := check_preview_cost(intent, prev.total_usd, self.bounds)) is not None:
            return self._refuse(intent, r, kind="place")

        spx = self.spx_mark()
        order = self.broker.place(intent)
        self.journal.record("placed", intent_id=intent.intent_id, kind="entry",
                            spx=spx, order=order.to_dict())

        out: dict[str, Any] = {"refused": None, "order": order.to_dict(),
                               "preview": prev.to_dict(), "stop_order": None}
        if order.status is OrderStatus.REJECTED:
            self.journal.record("rejected", intent_id=intent.intent_id,
                                order_id=order.order_id, detail=order.message)
            return out
        if not order.is_filled:
            return out

        fill_px = order.fill_price if order.fill_price is not None else (intent.limit or 0.0)
        pos = OpenPosition(
            symbol=intent.symbol, qty=order.filled_qty, entry_price=fill_px,
            intent_id=intent.intent_id, right=intent.occ.right,
            stop_spx=intent.stop_spx, delta=intent.delta,
            entry_order_id=order.order_id,
        )
        self._open[pos.symbol] = pos
        # stop_spx and delta go on the FILL line, not only on the stop line: if
        # the resting stop fails to place, a restart must still recover a
        # position the SPX-mark loop can watch. Recovering it unwatched would
        # be the worst of both.
        self.journal.record("filled", kind="entry", intent_id=intent.intent_id,
                            symbol=pos.symbol, qty=pos.qty, price=fill_px,
                            cost_usd=round(fill_px * CONTRACT_MULTIPLIER * pos.qty, 2),
                            spx=spx, stop_spx=intent.stop_spx, delta=intent.delta,
                            order_id=order.order_id)
        out["stop_order"] = self._place_protective_stop(pos, spx)
        return out

    def _place_protective_stop(self, pos: OpenPosition, spx: float) -> dict[str, Any] | None:
        """Rest a stop at the broker. Loud on failure: the position is live."""
        if pos.stop_spx is None or pos.delta is None:
            self.journal.record("stop_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id,
                                detail="no stop_spx/delta on the entry")
            return None
        try:
            price = protective_stop_price(pos.entry_price, pos.delta, spx, pos.stop_spx)
        except ValueError as exc:
            self.journal.record("stop_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, detail=str(exc))
            return None
        return self._rest_stop_at(pos, price, spx=spx, kind="entry")

    # ── internals: the exit ──────────────────────────────────────────────
    def _exit_refusal(self, intent: OrderIntent) -> Refusal | None:
        if (r := self.arming.permits_exit()) is not None:
            return r
        held = self._open.get(intent.symbol)
        return check_exit(intent, self.bounds, held_qty=held.qty if held else None)

    def _place_exit(self, intent: OrderIntent) -> dict[str, Any]:
        if (refusal := self._exit_refusal(intent)) is not None:
            return self._refuse(intent, refusal, kind="place")
        pos = self._open.get(intent.symbol)
        order = self.broker.place(intent)
        self.journal.record("placed", intent_id=intent.intent_id, kind="exit",
                            order=order.to_dict())
        out = {"refused": None, "order": order.to_dict(), "closed": None}
        if order.is_filled and pos is not None:
            out["closed"] = self._settle(pos, order, reason=intent.source or "exit")
        return out

    def _market_close(self, pos: OpenPosition, reason: str) -> dict[str, Any]:
        """The service's own exit: market, one intent id per position per reason."""
        intent = OrderIntent(
            intent_id=f"{pos.intent_id}:exit:{reason}", symbol=pos.symbol,
            side=Side.SELL_TO_CLOSE, qty=pos.qty, order_type=OrderType.MARKET,
            source=reason, engine_sha=self.config.sha,
        )
        if (r := check_exit(intent, self.bounds, held_qty=pos.qty)) is not None:
            raise Refused(r)
        order = self.broker.place(intent)
        self.journal.record("placed", intent_id=intent.intent_id, kind="exit",
                            reason=reason, order=order.to_dict())
        if not order.is_filled:
            self.journal.record("exit_unfilled", symbol=pos.symbol, reason=reason,
                                order_id=order.order_id, status=order.status.value)
            return {"symbol": pos.symbol, "order_id": order.order_id,
                    "status": order.status.value, "closed": False}
        return self._settle(pos, order, reason=reason)

    def _settle(self, pos: OpenPosition, order: OrderResult, reason: str) -> dict[str, Any]:
        """Book the close, then deal with the resting stop.

        In that order: a journal line costs nothing if the cancel then fails,
        but a cancelled stop with no record of why is a hole in the audit.

        A **partial** fill is the case worth reading. The position shrinks but
        does not go away, so the resting stop — sized for the whole position —
        is now larger than what is held, and if it triggered it would sell
        contracts Steve does not own. So a partial exit cancels the stop and
        rests a new one at the same price for what is left. The mock never
        fills partially; a real broker does, which is why this is here before
        the transport is."""
        exit_px = order.fill_price if order.fill_price is not None else 0.0
        closed_qty = min(order.filled_qty or pos.qty, pos.qty)
        remaining = pos.qty - closed_qty
        pnl = self._pnl_usd(pos, exit_px, closed_qty)
        self.journal.record("closed", symbol=pos.symbol, qty=closed_qty,
                            remaining_qty=remaining, intent_id=pos.intent_id,
                            kind=reason, entry_price=pos.entry_price,
                            exit_price=exit_px, pnl_usd=pnl,
                            order_id=order.order_id, reason=reason)

        canceled = self._cancel_protective_stop(pos)
        restopped = None
        if remaining:
            pos.qty = remaining
            restopped = self._rest_stop_at(pos, pos.stop_price)
        else:
            self._open.pop(pos.symbol, None)

        return {"symbol": pos.symbol, "qty": closed_qty, "remaining_qty": remaining,
                "entry_price": pos.entry_price, "exit_price": exit_px,
                "pnl_usd": pnl, "reason": reason, "order_id": order.order_id,
                "closed": remaining == 0, "stop_canceled": canceled,
                "stop_replaced": restopped}

    def _cancel_protective_stop(self, pos: OpenPosition) -> dict[str, Any] | None:
        if not pos.stop_order_id:
            return None
        order_id = pos.stop_order_id
        pos.stop_order_id = None
        try:
            canceled = self.broker.cancel(order_id).to_dict()
        except BrokerError as exc:
            self.journal.record("error", kind="cancel-stop", symbol=pos.symbol,
                                order_id=order_id, detail=str(exc))
            return None
        self.journal.record("canceled", kind="protective-stop",
                            symbol=pos.symbol, order_id=order_id)
        return canceled

    def _rest_stop_at(self, pos: OpenPosition, price: float | None, *,
                      spx: float | None = None,
                      kind: str = "resized") -> dict[str, Any] | None:
        """Rest a SELL STOP at a price already derived, for what is held now.

        The one place a resting stop is created, so its size can never drift
        from the position: it is called with ``pos.qty`` whatever the caller
        was doing."""
        if price is None:
            self.journal.record("stop_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, qty=pos.qty,
                                detail=f"no stop price to rest ({kind})")
            return None
        stop_intent = OrderIntent(
            intent_id=f"{pos.intent_id}:stop:{pos.qty}", symbol=pos.symbol,
            side=Side.SELL_TO_CLOSE, qty=pos.qty, order_type=OrderType.STOP,
            stop_price=price, source="protective-stop", engine_sha=self.config.sha,
        )
        try:
            result = self.broker.place(stop_intent)
        except BrokerError as exc:
            self.journal.record("stop_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, qty=pos.qty, stop_price=price,
                                detail=f"broker refused the {kind} stop: {exc}")
            return None
        pos.stop_order_id = result.order_id
        pos.stop_price = price
        self.journal.record("stop_placed", symbol=pos.symbol, intent_id=pos.intent_id,
                            stop_price=price, stop_spx=pos.stop_spx, spx=spx,
                            delta=pos.delta, qty=pos.qty, order_id=result.order_id,
                            kind=kind, risk_usd=risk_usd(pos.entry_price, price, pos.qty),
                            order=result.to_dict())
        return result.to_dict()

    def _pnl_usd(self, pos: OpenPosition, exit_price: float,
                 qty: int | None = None) -> float:
        n = pos.qty if qty is None else qty
        return round((float(exit_price) - pos.entry_price) * CONTRACT_MULTIPLIER * n, 2)

    # ── internals: plumbing ──────────────────────────────────────────────
    def _quote_view(self, symbol: str) -> QuoteView | None:
        try:
            q = self.broker.quote(symbol)
        except BrokerError:
            return None
        return QuoteView(q.bid, q.ask, q.age_s(self.clock()))

    def _refuse(self, intent: OrderIntent, refusal: Refusal, kind: str) -> dict[str, Any]:
        self.journal.record("refused", kind=kind, intent_id=intent.intent_id,
                            symbol=intent.symbol, refused=refusal.to_dict())
        return {"refused": refusal.to_dict(), "order": None}

    def _replay(self, intent_id: str) -> dict[str, Any] | None:
        """An intent id the journal has already sent is answered, never re-sent."""
        for entry in self.journal.find(intent_id):
            if entry.get("event") == "placed":
                return {"refused": None, "order": entry.get("order"),
                        "replayed_from": entry.get("ts")}
        return None

    def _recover(self) -> None:
        """Rebuild open positions from today's journal after a restart.

        The service comes back LOCKED, so it cannot open anything; what it must
        not do is come back not knowing a position is live, because then the
        SPX-mark loop stops watching it and flatten misses it."""
        entries = self.journal.read()
        for e in entries:
            if e.get("event") == "filled" and e.get("kind") == "entry":
                symbol = str(e.get("symbol", ""))
                if not symbol:
                    continue
                try:
                    right = parse_occ(symbol).right
                except ValueError:
                    continue
                self._open[symbol] = OpenPosition(
                    symbol=symbol, qty=int(e.get("qty", 0) or 0),
                    entry_price=float(e.get("price", 0.0) or 0.0),
                    intent_id=str(e.get("intent_id", "")), right=right,
                    stop_spx=e.get("stop_spx"), delta=e.get("delta"),
                    entry_order_id=str(e.get("order_id", "")),
                )
            elif e.get("event") == "stop_placed":
                pos = self._open.get(str(e.get("symbol", "")))
                if pos is not None:
                    pos.stop_order_id = e.get("order_id")
                    pos.stop_price = e.get("stop_price")
                    if e.get("stop_spx") is not None:
                        pos.stop_spx = e.get("stop_spx")
                    if e.get("delta") is not None:
                        pos.delta = e.get("delta")
            elif e.get("event") == "closed":
                symbol = str(e.get("symbol", ""))
                remaining = e.get("remaining_qty")
                pos = self._open.get(symbol)
                if remaining and pos is not None:
                    pos.qty = int(remaining)
                else:
                    self._open.pop(symbol, None)
        if self._open:
            self.journal.record("recovered", positions=[p.to_dict() for p in self._open.values()])
