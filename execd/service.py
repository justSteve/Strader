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

**A fill without a protective stop is a state this service does not reach
quietly.** The stop's inputs are checked before the entry is previewed, so an
intent that could not produce a resting stop is refused while refusing is still
free. The stop is placed the moment the fill comes back, and the placement is
journaled whether it succeeds or fails — a failure there is loud, because the
position is live and unprotected until the SPX-mark loop or Steve deals with it.
It used to say "does not reach", flatly; the 2026-08-30 audit found the way
through, which was to not notice the fill at all, and the word is now the one
the code earns. Every remaining route to an unprotected position — a fill too
cheap to leave room for a stop, a broker that refuses the stop, an adopted
position with no stop inputs, a stop cancelled by request — writes a
``stop_unprotected`` line, and that line is the guarantee.

**The day's ceiling is read from the journal, not remembered.** A restart
recovers it. See ``execd.journal``.

**What is open is read from the broker, not believed.** The journal is the
authority on what this service intended and the broker is the authority on what
is held; treating the first as both is the defect :meth:`ExecService.reconcile`
exists to close. See its docstring. [st-v7oa]
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .arming import Arming
from .bounds import (
    CT, Bounds, DayState, QuoteView, Refusal, check_entry, check_exit,
    check_preview_cost, check_risk_budget, session_close,
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


def _ts_of(entry: dict[str, Any]) -> datetime | None:
    """The moment a journal line was written, or ``None`` if it cannot be read.

    A recovered position keeps the age it actually has: the settle window that
    protects it from a lagging positions feed must not restart just because the
    service did."""
    raw = entry.get("ts")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


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
class WorkingEntry:
    """An entry the broker acknowledged and has not resolved. [st-v7oa]

    A limit that rests is the normal answer from a real broker, not an edge
    case, and until this existed the service handed the caller its order id and
    forgot it: no slot taken, no attempt debited, no protective stop owed, and
    nothing that ever looked at it again. It is not a position — nothing is held
    — but it is the only thing between the caller and one, so it holds a slot
    and an attempt until :meth:`ExecService.reconcile` learns what became of it.
    """

    order_id: str
    symbol: str
    qty: int
    intent_id: str
    right: str
    limit: float | None = None
    stop_spx: float | None = None
    delta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id, "symbol": self.symbol, "qty": self.qty,
            "intent_id": self.intent_id, "right": self.right, "limit": self.limit,
            "stop_spx": self.stop_spx, "delta": self.delta,
        }


#: How long a position must be absent from the broker's own account before the
#: service believes it is gone. A positions endpoint that has not caught up with
#: a fill it reported seconds ago is an ordinary thing for a REST broker to do,
#: and treating that lag as a close would drop a live position and cancel the
#: stop under it. Absence has to persist to mean anything. [st-v7oa]
POSITION_SETTLE_S = 90.0


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
    opened_at: datetime | None = None
    #: first time the broker failed to report this position, or ``None``
    missing_since: datetime | None = None
    #: the close this service has sent and not yet seen resolve. While this is
    #: set the SPX-mark loop does not fire again — re-sending a market close
    #: every tick until one fills was finding 2 of the 2026-08-30 audit, an
    #: oversell that grew once a second. [st-97z1]
    exit_order_id: str | None = None
    exit_reason: str | None = None

    @property
    def exit_in_flight(self) -> bool:
        return bool(self.exit_order_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "qty": self.qty, "entry_price": self.entry_price,
            "intent_id": self.intent_id, "right": self.right,
            "stop_spx": self.stop_spx, "delta": self.delta,
            "stop_order_id": self.stop_order_id, "stop_price": self.stop_price,
            "entry_order_id": self.entry_order_id,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "exit_order_id": self.exit_order_id, "exit_reason": self.exit_reason,
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
        self._working: dict[str, WorkingEntry] = {}
        self._last_fill_poll = clock()
        self._recover()

    # ── arming (page-only; none of these has an API route) ───────────────
    def unlock(self, credential: Any, until: datetime | None = None) -> dict[str, Any]:
        """Arm the service — for today, and never past today's close.

        ``session_close`` rolls to the *next* day's close when now is already
        past it, which is right for "when does this session end" and wrong as
        an arming expiry: unlocking at 15:30 CT used to arm the service until
        15:00 tomorrow (finding 16 of the 2026-08-30 audit). After the close
        there is nothing today to arm for, so the unlock is refused; an
        explicit ``until`` is capped at today's close for the same reason.
        Exits and flatten need no arming window — only entries do."""
        with self._lock:
            now = self.clock()
            close = session_close(now, self.bounds)
            if close.astimezone(CT).date() != now.astimezone(CT).date():
                refusal = Refusal(
                    "window",
                    f"the session closed at {self.bounds.close_ct} CT — an unlock "
                    f"now would arm the service until tomorrow's close, and "
                    f"there is nothing today to arm for")
                self.journal.record("refused", kind="unlock",
                                    refused=refusal.to_dict())
                raise Refused(refusal)
            expiry = min(until, close) if until is not None else close
            state = self.arming.unlock(credential, expiry)
            self.journal.record("unlock", state=state.value, until=expiry,
                                capped=bool(until is not None and until > close))
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
            "working": [w.to_dict() for w in self._working.values()],
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

            # The broker's account of what is open, before the bounds are asked
            # to judge against it. Without this the day's state is the journal's
            # belief, and the journal does not know what filled while nothing
            # was watching. [st-v7oa]
            self.reconcile()

            self.journal.record("request", kind="place", intent_id=intent.intent_id,
                                intent=intent.to_dict())
            if intent.is_entry:
                return self._place_entry(intent)
            return self._place_exit(intent)

    def cancel(self, order_id: str) -> dict[str, Any]:
        """Cancelling is getting out of the way of an order, so it is an exit-
        class action: legal whenever there is a credential — with one refusal.

        The resting stop under a live position is not an order in the way, it
        is the position's only protection if this box dies. Cancelling it alone
        opens risk, which no exit-class credential may do (finding 5 of the
        2026-08-30 audit — it used to succeed, silently). The ways out that
        exist all handle the stop properly: an exit and flatten cancel it in
        the same motion they close the position it protects."""
        with self._lock:
            if (r := self.arming.permits_exit()) is not None:
                self.journal.record("refused", kind="cancel", order_id=order_id,
                                    refused=r.to_dict())
                raise Refused(r)
            for pos in self._open.values():
                if pos.stop_order_id == order_id:
                    refusal = Refusal(
                        "protective_stop",
                        f"{order_id} is the resting stop under a live "
                        f"{pos.symbol} position — cancelling it alone leaves "
                        f"the position unprotected; close it with an exit or "
                        f"flatten, which take the stop off in the same motion")
                    self.journal.record("refused", kind="cancel", order_id=order_id,
                                        refused=refusal.to_dict())
                    raise Refused(refusal)
            result = self.broker.cancel(order_id)
            self.journal.record("canceled", order_id=order_id, order=result.to_dict())
            for pos in self._open.values():
                if pos.exit_order_id == order_id:
                    # The close was pulled by hand; the position is live again
                    # and gets its protection back, and the SPX loop may fire.
                    self.journal.record("exit_resolved", symbol=pos.symbol,
                                        order_id=order_id, outcome="canceled",
                                        reason=pos.exit_reason,
                                        detail="cancelled by request")
                    pos.exit_order_id = None
                    pos.exit_reason = None
                    self._rest_stop_at(pos, pos.stop_price)
            if order_id in self._working:
                self._resolve_working(order_id, outcome="canceled",
                                      detail="cancelled by request")
            return {"refused": None, "order": result.to_dict()}

    def flatten(self, reason: str = "flatten") -> dict[str, Any]:
        """Close everything at market. Legal while STOPped, while stood down,
        and outside the session window — the whole point of the switch is that
        it never traps him."""
        with self._lock:
            if (r := self.arming.permits_exit()) is not None:
                self.journal.record("refused", kind="flatten", refused=r.to_dict())
                raise Refused(r)
            # "Close everything" has to mean everything the broker holds, not
            # everything this service happens to remember. [st-v7oa]
            self.reconcile()
            self.journal.record("request", kind="flatten", reason=reason,
                                positions=[p.symbol for p in self._open.values()])
            closed: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            for pos in list(self._open.values()):
                try:
                    # force: an exit already in flight is cancelled and replaced
                    # rather than waited on — "get me out" does not queue.
                    closed.append(self._market_close(pos, reason=reason, force=True))
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
            pending: list[dict[str, Any]] = []
            for pos in list(self._open.values()):
                if pos.stop_spx is None:
                    continue
                if pos.exit_in_flight:
                    # A close is already working at the broker. Firing again
                    # would sell the position twice — finding 2 was exactly
                    # this, once a second. [st-97z1]
                    pending.append({"symbol": pos.symbol,
                                    "order_id": pos.exit_order_id,
                                    "reason": pos.exit_reason})
                    continue
                if exit_triggered(pos.right, spx, pos.stop_spx):
                    self.journal.record("exit_triggered", symbol=pos.symbol,
                                        spx=spx, stop_spx=pos.stop_spx,
                                        intent_id=pos.intent_id)
                    try:
                        fired.append(self._market_close(pos, reason="spx-stop"))
                    except (BrokerError, Refused) as exc:
                        # One position's trouble must not stop the loop watching
                        # the others. The stop was re-rested before this raised.
                        self.journal.record("error", kind="spx-stop",
                                            symbol=pos.symbol, detail=str(exc))
                        fired.append({"symbol": pos.symbol, "closed": False,
                                      "error": str(exc)})
            return {"spx": spx, "fired": fired, "pending": pending}

    def poll_fills(self) -> dict[str, Any]:
        """Pick up fills the service did not initiate — a resting protective
        stop that triggered while nothing was watching."""
        with self._lock:
            return self._pick_up_fills()

    def _pick_up_fills(self) -> dict[str, Any]:
        """The fill sweep, without the lock, so ``reconcile`` can run it first.

        Order matters: a stop that fired at the broker has to be booked — with
        its P&L, against the day's ceiling — before the position sweep notices
        the position is gone. Reversed, a losing trade would vanish from the
        ceiling it was supposed to debit."""
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
            if fill.order_id == pos.exit_order_id:
                # The close this service sent and was waiting on. [st-97z1]
                kind = pos.exit_reason or "exit"
                why = "in-flight-close"
                pos.exit_order_id = None
                pos.exit_reason = None
            elif pos.stop_order_id and fill.order_id != pos.stop_order_id:
                continue
            else:
                kind, why = "protective-stop", "resting-stop"
            closed_qty = min(fill.qty or pos.qty, pos.qty)
            remaining = pos.qty - closed_qty
            pnl = self._pnl_usd(pos, fill.price, closed_qty)
            self.journal.record("closed", symbol=pos.symbol, qty=closed_qty,
                                remaining_qty=remaining, intent_id=pos.intent_id,
                                kind=kind, entry_price=pos.entry_price,
                                exit_price=fill.price, pnl_usd=pnl,
                                order_id=fill.order_id, reason=why)
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

    # ── the second record ────────────────────────────────────────────────
    def reconcile(self) -> dict[str, Any]:
        """Ask the broker what is actually working and actually held. [st-v7oa]

        The journal is the authority on what this service *intended*. It is not
        the authority on what is *open* — only the broker is, and until this
        method existed nothing on the write path ever asked it, though
        ``Broker.orders`` and ``Broker.positions`` were in the protocol from the
        first commit. Three things get settled here:

        1. **Working entries.** Filled ones become tracked positions and get the
           protective stop they were owed; cancelled and rejected ones give
           their slot back; ones the broker cannot account for keep theirs,
           because holding a slot refuses new risk and forgetting one creates
           it.
        2. **Positions the service does not know about** — opened elsewhere, or
           lost with a journal — are adopted so that ``flatten`` and the exit
           sizing can see them. An adopted position carries no ``stop_spx``, so
           it is journaled as unprotected rather than quietly watched.
        3. **Sizes that disagree.** The broker's number wins and the resting
           stop is resized to it, because a stop larger than the position sells
           what Steve does not own.

        Silent when nothing has changed — a journal that records every heartbeat
        is a journal nobody reads. Never raises: a broker that cannot be reached
        leaves every belief in place and says so.
        """
        with self._lock:
            try:
                broker_orders = {o.order_id: o for o in self.broker.orders()}
                broker_positions = {p.symbol: p for p in self.broker.positions()}
            except BrokerError as exc:
                self.journal.record("error", kind="reconcile", detail=str(exc))
                return {"promoted": [], "released": [], "adopted": [],
                        "corrected": [], "error": str(exc)}

            # Fills first. A stop that fired has to be booked against the day's
            # ceiling before the position sweep sees the position is gone.
            self._pick_up_fills()
            promoted, released = self._reconcile_working(broker_orders)
            exits = self._reconcile_exits(broker_orders)
            adopted, corrected, gone = self._reconcile_positions(broker_positions)
            return {"promoted": promoted, "released": released, "exits": exits,
                    "adopted": adopted, "corrected": corrected, "gone": gone,
                    "error": None}

    def _reconcile_working(
        self, broker_orders: dict[str, OrderResult]
    ) -> tuple[list[str], list[str]]:
        promoted: list[str] = []
        released: list[str] = []
        for order_id, work in list(self._working.items()):
            order = broker_orders.get(order_id)
            if order is None:
                # The broker has no record of an order we were told it took.
                # Keep the slot — that only refuses new risk — and say so once.
                if not self._already_flagged_unknown(order_id):
                    self.journal.record("reconcile_unknown", order_id=order_id,
                                        symbol=work.symbol, intent_id=work.intent_id,
                                        detail="the broker does not report this order — "
                                               "its slot is held until it can be accounted for")
                continue
            if order.is_working:
                continue
            if order.is_filled:
                promoted.append(work.symbol)
                self._promote(work, order)
            else:
                released.append(order_id)
                self._resolve_working(order_id, outcome=order.status.value.lower(),
                                      detail=order.message)
        return promoted, released

    def _promote(self, work: WorkingEntry, order: OrderResult) -> None:
        """A working entry filled while nothing was watching. Book it, then owe
        it the same protective stop a synchronous fill would have got."""
        fill_px = order.fill_price if order.fill_price is not None else (work.limit or 0.0)
        qty = order.filled_qty or work.qty
        try:
            spx = self.spx_mark()
        except BrokerError:
            spx = None
        pos = self._open.get(work.symbol)
        if pos is None:
            pos = OpenPosition(
                symbol=work.symbol, qty=qty, entry_price=fill_px,
                intent_id=work.intent_id, right=work.right,
                stop_spx=work.stop_spx, delta=work.delta,
                entry_order_id=order.order_id, opened_at=self.clock(),
            )
            self._open[pos.symbol] = pos
        else:
            # The position grew. Its resting stop is now smaller than what is
            # held, which is the same silent hole in the other direction, so the
            # old one comes off before a correctly sized one goes on.
            self._cancel_protective_stop(pos)
            pos.qty += qty
        self.journal.record("filled", kind="entry", intent_id=work.intent_id,
                            symbol=pos.symbol, qty=qty, price=fill_px,
                            cost_usd=round(fill_px * CONTRACT_MULTIPLIER * qty, 2),
                            spx=spx, stop_spx=work.stop_spx, delta=work.delta,
                            order_id=order.order_id, found_by="reconcile")
        self._resolve_working(order.order_id, outcome="filled")
        if spx is None:
            self.journal.record("stop_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, qty=pos.qty,
                                detail="no index mark at reconcile — cannot derive a stop")
            return
        self._place_protective_stop(pos, spx)

    def _reconcile_exits(self, broker_orders: dict[str, OrderResult]) -> list[dict[str, Any]]:
        """What became of the closes this service sent. [st-97z1]

        The asymmetry with working *entries* is deliberate and worth reading.
        An entry order the broker cannot account for keeps its slot, because
        holding a slot only refuses new risk. An exit order the broker cannot
        account for is **cleared**, because a close that jams keeps Steve in
        risk — the SPX loop must be free to fire again. The cost of clearing
        wrongly is a possible double-sell if the lost order later surfaces;
        the cost of holding wrongly is a position nothing is closing. The
        second is worse, and the journal records the choice either way."""
        resolved: list[dict[str, Any]] = []
        for pos in list(self._open.values()):
            order_id = pos.exit_order_id
            if not order_id:
                continue
            order = broker_orders.get(order_id)
            if order is not None and order.is_working:
                continue
            if order is not None and order.is_filled:
                # The fill sweep usually books this first; this branch is the
                # backstop for a fill the sweep's window missed.
                pos.exit_order_id = None
                reason = pos.exit_reason or "exit"
                pos.exit_reason = None
                resolved.append(self._settle(pos, order, reason=reason))
                continue
            outcome = order.status.value.lower() if order is not None else "unknown"
            detail = (order.message if order is not None
                      else "the broker does not report this order — clearing it "
                           "so the exit path is free to fire again")
            self.journal.record("exit_resolved", symbol=pos.symbol,
                                order_id=order_id, outcome=outcome,
                                reason=pos.exit_reason, detail=detail)
            pos.exit_order_id = None
            pos.exit_reason = None
            # The close is not happening; the position is live again and needs
            # its broker-resident protection back.
            self._rest_stop_at(pos, pos.stop_price)
            resolved.append({"symbol": pos.symbol, "order_id": order_id,
                             "outcome": outcome, "closed": False})
        return resolved

    def _resolve_working(self, order_id: str, outcome: str, detail: str = "") -> None:
        work = self._working.pop(order_id, None)
        if work is None:
            return
        self.journal.record("entry_resolved", order_id=order_id, outcome=outcome,
                            symbol=work.symbol, intent_id=work.intent_id,
                            detail=detail)

    def _already_flagged_unknown(self, order_id: str) -> bool:
        return any(e.get("order_id") == order_id
                   for e in self.journal.events("reconcile_unknown"))

    def _reconcile_positions(
        self, broker_positions: dict[str, Position]
    ) -> tuple[list[str], list[str], list[str]]:
        adopted: list[str] = []
        corrected: list[str] = []
        gone: list[str] = []
        now = self.clock()

        for symbol, held in broker_positions.items():
            if held.qty <= 0:      # a short is not this service's to manage
                continue
            pos = self._open.get(symbol)
            if pos is None:
                try:
                    right = parse_occ(symbol).right
                except ValueError:
                    continue       # not an option this service can reason about
                pos = OpenPosition(
                    symbol=symbol, qty=held.qty, entry_price=held.avg_price,
                    intent_id=f"adopted:{symbol}", right=right, opened_at=now,
                )
                self._open[symbol] = pos
                adopted.append(symbol)
                self.journal.record("position_adopted", symbol=symbol, qty=held.qty,
                                    entry_price=held.avg_price,
                                    detail="the broker holds a position this service "
                                           "did not open")
                self.journal.record("stop_unprotected", symbol=symbol,
                                    intent_id=pos.intent_id, qty=held.qty,
                                    detail="adopted position carries no stop_spx or "
                                           "delta — no resting stop can be derived")
            elif pos.qty != held.qty:
                self.journal.record("position_corrected", symbol=symbol,
                                    tracked_qty=pos.qty, broker_qty=held.qty,
                                    intent_id=pos.intent_id,
                                    detail="the broker's size is the one that is real")
                corrected.append(symbol)
                self._cancel_protective_stop(pos)
                pos.qty = held.qty
                self._rest_stop_at(pos, pos.stop_price)

        for symbol, pos in list(self._open.items()):
            if symbol in broker_positions:
                pos.missing_since = None
                continue
            if pos.missing_since is None:
                pos.missing_since = now
            settled_for = (now - pos.missing_since).total_seconds()
            if settled_for < POSITION_SETTLE_S:
                # Absent once is a slow endpoint. Absent for a while is a close.
                continue
            gone.append(symbol)
            self.journal.record("position_gone", symbol=symbol, qty=pos.qty,
                                intent_id=pos.intent_id, missing_for_s=settled_for,
                                detail="the broker has not reported this position for "
                                       f"{settled_for:.0f}s — closed somewhere this "
                                       "service did not see")
            # A stop still resting under a position that is gone would open a
            # short if it triggered. Pull it before dropping the record of it.
            self._cancel_protective_stop(pos)
            self._open.pop(symbol, None)
        return adopted, corrected, gone

    def _broker_qty(self, symbol: str) -> int | None:
        """What the broker says is held, or ``None`` if it could not be asked."""
        try:
            for p in self.broker.positions():
                if p.symbol == symbol:
                    return max(0, p.qty)
        except BrokerError:
            return None
        return 0

    # ── internals: the entry ─────────────────────────────────────────────
    def _entry_refusal(self, intent: OrderIntent) -> Refusal | None:
        if (r := self.arming.permits_entry()) is not None:
            return r
        quote = self._quote_view(intent.symbol)
        state = self.day_state()
        # The journal's count is today's file; what the service is actually
        # holding can be older. A position carried past midnight fell out of
        # the day's count at rollover and its slot came free while it was
        # still open (audit finding 9, st-kh0l). The larger of the two numbers
        # is the honest one — max, not sum, so nothing counts twice.
        live = len(self._open) + len(self._working)
        if live > state.open_positions:
            state = replace(state, open_positions=live)
        r = check_entry(intent, self.bounds, state, quote,
                        self.clock(), killed=self.arming.killed)
        if r is not None:
            return r
        return self._protective_stop_refusal(intent)

    def _protective_stop_refusal(self, intent: OrderIntent) -> Refusal | None:
        """Everything the resting stop needs, checked while refusing is free.

        Unconditional: ``Bounds.problems`` refuses to load a file that turns
        ``require_protective_stop`` off, so there is no state in which this is
        skipped."""
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

        # Derive the stop the entry would rest, here, before anything is sent.
        # It was previously derived only after the fill, which meant an intent
        # priced too cheaply to leave room for a stop became a live position
        # with no stop under it and a journal line about it (finding 12), and
        # nothing ever compared the position's own worst case to the day's
        # ceiling (finding 6). Both are answered by the same arithmetic, and the
        # right time for both is while refusing is still free. [st-2j80]
        worst_fill = intent.limit if intent.limit is not None else 0.0
        try:
            stop_price = protective_stop_price(worst_fill, intent.delta, spx,
                                               intent.stop_spx)
        except ValueError as exc:
            return Refusal("protective_stop",
                           f"no resting stop can be derived for this entry: {exc}")
        return check_risk_budget(intent, self.bounds, self.day_state(), stop_price)

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
        # The STOP file was checked when the bounds ran, three broker
        # round-trips ago. It is one touch from Steve's phone, and the touch
        # that lands while an entry is being priced must win (audit finding
        # 10, st-kh0l): last look, immediately before the send.
        if self.arming.killed:
            return self._refuse(
                intent,
                Refusal("stop", "STOP came on while this entry was being "
                                "priced — not sending"),
                kind="place")
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
            # Acknowledged, not filled. Held, not forgotten: it takes a slot and
            # an attempt until reconcile() learns what the broker did with it.
            work = WorkingEntry(
                order_id=order.order_id, symbol=intent.symbol,
                qty=order.qty, intent_id=intent.intent_id, right=intent.occ.right,
                limit=intent.limit, stop_spx=intent.stop_spx, delta=intent.delta,
            )
            self._working[work.order_id] = work
            self.journal.record("working", kind="entry", intent_id=intent.intent_id,
                                symbol=work.symbol, qty=work.qty,
                                order_id=work.order_id, status=order.status.value,
                                limit=work.limit, stop_spx=work.stop_spx,
                                delta=work.delta, spx=spx)
            out["working"] = work.to_dict()
            return out

        fill_px = order.fill_price if order.fill_price is not None else (intent.limit or 0.0)
        pos = OpenPosition(
            symbol=intent.symbol, qty=order.filled_qty, entry_price=fill_px,
            intent_id=intent.intent_id, right=intent.occ.right,
            stop_spx=intent.stop_spx, delta=intent.delta,
            entry_order_id=order.order_id, opened_at=self.clock(),
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
        """The size an exit is checked against comes from the broker when this
        service has no position of its own to check it against. [st-v7oa]

        ``check_exit`` lets an unknown size through on purpose — refusing on
        ignorance is how an exit gate traps someone — but "unknown" used to mean
        "did not look", and an unbounded SELL_TO_CLOSE against a long-premium
        account is a naked short. Now it means the broker was asked and could
        not answer, which is journaled and still sent."""
        if (r := self.arming.permits_exit()) is not None:
            return r
        held = self._open.get(intent.symbol)
        if held is not None:
            return check_exit(intent, self.bounds, held_qty=held.qty)
        qty = self._broker_qty(intent.symbol)
        if qty is None:
            self.journal.record("exit_unverified", symbol=intent.symbol,
                                intent_id=intent.intent_id, qty=intent.qty,
                                detail="the broker could not be asked what is held — "
                                       "sending unverified rather than trapping a position")
        return check_exit(intent, self.bounds, held_qty=qty)

    def _place_exit(self, intent: OrderIntent) -> dict[str, Any]:
        if (refusal := self._exit_refusal(intent)) is not None:
            return self._refuse(intent, refusal, kind="place")
        pos = self._open.get(intent.symbol)

        if pos is not None and pos.exit_in_flight:
            return self._refuse(intent, Refusal(
                "exit_in_flight",
                f"a close for {intent.symbol} is already working at the broker "
                f"(order {pos.exit_order_id}) — cancel it or use flatten, which "
                f"replaces it, rather than stacking a second sell on it"),
                kind="place")

        # A full-size exit and the resting stop must not both be live at the
        # broker — same discipline as _market_close, same finding 3. A partial
        # exit leaves the stop standing and _settle resizes it on the fill;
        # the window where a partial rests unfilled beside a full-size stop is
        # a known residual, recorded on st-97z1.
        if pos is not None and intent.qty >= pos.qty and pos.stop_order_id:
            stop_id = pos.stop_order_id
            result = self.broker.cancel(stop_id)   # a BrokerError propagates: 502, nothing sent
            if result.is_filled:
                pos.stop_order_id = None
                settled = self._settle(pos, result, reason="resting-stop")
                return {"refused": None, "order": None, "closed": settled,
                        "note": "the resting stop had already filled — "
                                "the position was closed before this exit was sent"}
            pos.stop_order_id = None
            self.journal.record("canceled", kind="protective-stop",
                                symbol=pos.symbol, order_id=stop_id)

        order = self.broker.place(intent)
        self.journal.record("placed", intent_id=intent.intent_id, kind="exit",
                            order=order.to_dict())
        out = {"refused": None, "order": order.to_dict(), "closed": None}
        if pos is None:
            return out
        if order.status is OrderStatus.REJECTED:
            self._rest_stop_at(pos, pos.stop_price)
            return out
        if not order.is_filled:
            pos.exit_order_id = order.order_id
            pos.exit_reason = intent.source or "exit"
            self.journal.record("exit_unfilled", symbol=pos.symbol,
                                reason=pos.exit_reason, order_id=order.order_id,
                                status=order.status.value, intent_id=pos.intent_id)
            return out
        out["closed"] = self._settle(pos, order, reason=intent.source or "exit")
        return out

    def _market_close(self, pos: OpenPosition, reason: str,
                      force: bool = False) -> dict[str, Any]:
        """The service's own exit: market, one close in flight per position.

        Two rules, both from the 2026-08-30 audit. [st-97z1]

        **One close at a time (finding 2).** A close that is already working at
        the broker is reported, not re-sent — re-sending it every tick until one
        filled was an oversell that grew once a second. ``force`` (flatten's
        privilege) cancels the in-flight close first instead of waiting behind
        it, because "get me out" must not queue behind an earlier, slower exit.

        **The resting stop comes off before the close goes on (finding 3).**
        The SPX loop and the resting stop are designed to fire at the same
        price, so a close sent while the stop still rests is asking for both to
        fill — a one-contract short on a long-premium-only account. Cancelling
        first is safe in every branch: if the cancel reports the stop already
        FILLED, the stop won the race, the position is already closed at the
        broker, and no close is sent at all; if the broker cannot be reached,
        nothing is sent and the standing stop is the protection working; if the
        close is afterwards rejected or cannot be sent, the stop is re-rested
        and the failure is loud. Every caller journals its intent to close
        before this runs (``exit_triggered``, the flatten request line, the
        place request line), so the cancel always has its why one line above.
        """
        if pos.exit_in_flight:
            if not force:
                return {"symbol": pos.symbol, "order_id": pos.exit_order_id,
                        "status": "PENDING", "closed": False,
                        "reason": pos.exit_reason}
            settled = self._cancel_in_flight_exit(pos)
            if settled is not None:      # it had already filled — that IS the close
                return settled
            if pos.exit_in_flight:       # could not be cancelled; nothing sane to send
                return {"symbol": pos.symbol, "order_id": pos.exit_order_id,
                        "status": "PENDING", "closed": False,
                        "reason": pos.exit_reason}

        intent = OrderIntent(
            intent_id=f"{pos.intent_id}:exit:{reason}", symbol=pos.symbol,
            side=Side.SELL_TO_CLOSE, qty=pos.qty, order_type=OrderType.MARKET,
            source=reason, engine_sha=self.config.sha,
        )
        if (r := check_exit(intent, self.bounds, held_qty=pos.qty)) is not None:
            raise Refused(r)

        if pos.stop_order_id:
            stop_id = pos.stop_order_id
            try:
                result = self.broker.cancel(stop_id)
            except BrokerError as exc:
                self.journal.record("error", kind="cancel-stop", symbol=pos.symbol,
                                    order_id=stop_id, detail=str(exc))
                return {"symbol": pos.symbol, "order_id": None, "status": "DEFERRED",
                        "closed": False,
                        "detail": "the resting stop could not be cancelled — "
                                  "nothing sent, the stop is still the protection"}
            if result.is_filled:
                # The race, and the stop won it: price reached the level at the
                # broker before the cancel arrived. The position is already
                # closed there; book that instead of also selling it.
                pos.stop_order_id = None
                return self._settle(pos, result, reason="resting-stop")
            pos.stop_order_id = None
            self.journal.record("canceled", kind="protective-stop",
                                symbol=pos.symbol, order_id=stop_id)

        try:
            order = self.broker.place(intent)
        except BrokerError as exc:
            self.journal.record("error", kind="close", symbol=pos.symbol,
                                reason=reason, detail=str(exc))
            self._rest_stop_at(pos, pos.stop_price)   # the protection goes back on
            raise
        self.journal.record("placed", intent_id=intent.intent_id, kind="exit",
                            reason=reason, order=order.to_dict())
        if order.status is OrderStatus.REJECTED:
            self.journal.record("rejected", intent_id=intent.intent_id,
                                order_id=order.order_id, detail=order.message)
            self._rest_stop_at(pos, pos.stop_price)
            return {"symbol": pos.symbol, "order_id": order.order_id,
                    "status": order.status.value, "closed": False}
        if not order.is_filled:
            pos.exit_order_id = order.order_id
            pos.exit_reason = reason
            self.journal.record("exit_unfilled", symbol=pos.symbol, reason=reason,
                                order_id=order.order_id, status=order.status.value,
                                intent_id=pos.intent_id)
            return {"symbol": pos.symbol, "order_id": order.order_id,
                    "status": order.status.value, "closed": False}
        return self._settle(pos, order, reason=reason)

    def _cancel_in_flight_exit(self, pos: OpenPosition) -> dict[str, Any] | None:
        """Pull the close that is working so a forced one can replace it.

        Returns the settle dict if the in-flight close turns out to have already
        filled (there is nothing left to force), else ``None`` — with the exit
        fields cleared on success and left standing when the broker could not
        be reached, which the caller reads as "leave it alone"."""
        order_id = pos.exit_order_id or ""
        try:
            result = self.broker.cancel(order_id)
        except BrokerError as exc:
            self.journal.record("error", kind="cancel-exit", symbol=pos.symbol,
                                order_id=order_id, detail=str(exc))
            return None
        if result.is_filled:
            reason = pos.exit_reason or "exit"
            pos.exit_order_id = None
            pos.exit_reason = None
            return self._settle(pos, result, reason=reason)
        self.journal.record("exit_resolved", symbol=pos.symbol, order_id=order_id,
                            outcome="canceled", reason=pos.exit_reason,
                            detail="cancelled to make way for a forced close")
        pos.exit_order_id = None
        pos.exit_reason = None
        return None

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
                    opened_at=_ts_of(e) or self.clock(),
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
            elif e.get("event") == "working" and e.get("kind") == "entry":
                symbol = str(e.get("symbol", ""))
                order_id = str(e.get("order_id", ""))
                if not symbol or not order_id:
                    continue
                try:
                    right = parse_occ(symbol).right
                except ValueError:
                    continue
                self._working[order_id] = WorkingEntry(
                    order_id=order_id, symbol=symbol,
                    qty=int(e.get("qty", 0) or 0),
                    intent_id=str(e.get("intent_id", "")), right=right,
                    limit=e.get("limit"), stop_spx=e.get("stop_spx"),
                    delta=e.get("delta"),
                )
            elif e.get("event") == "entry_resolved":
                self._working.pop(str(e.get("order_id", "")), None)
            elif e.get("event") == "position_adopted":
                symbol = str(e.get("symbol", ""))
                if not symbol or symbol in self._open:
                    continue
                try:
                    right = parse_occ(symbol).right
                except ValueError:
                    continue
                self._open[symbol] = OpenPosition(
                    symbol=symbol, qty=int(e.get("qty", 0) or 0),
                    entry_price=float(e.get("entry_price", 0.0) or 0.0),
                    intent_id=f"adopted:{symbol}", right=right,
                    opened_at=_ts_of(e) or self.clock(),
                )
            elif e.get("event") == "position_gone":
                self._open.pop(str(e.get("symbol", "")), None)
            elif e.get("event") == "exit_unfilled":
                # A close was in flight when the service died. It must come
                # back known, or the SPX loop re-fires into it. [st-97z1]
                pos = self._open.get(str(e.get("symbol", "")))
                if pos is not None:
                    pos.exit_order_id = str(e.get("order_id", "")) or None
                    pos.exit_reason = e.get("reason")
            elif e.get("event") == "exit_resolved":
                pos = self._open.get(str(e.get("symbol", "")))
                if pos is not None and pos.exit_order_id == e.get("order_id"):
                    pos.exit_order_id = None
                    pos.exit_reason = None
            elif e.get("event") == "closed":
                symbol = str(e.get("symbol", ""))
                remaining = e.get("remaining_qty")
                pos = self._open.get(symbol)
                if remaining and pos is not None:
                    pos.qty = int(remaining)
                    pos.exit_order_id = None
                    pos.exit_reason = None
                else:
                    self._open.pop(symbol, None)
        if self._open or self._working:
            self.journal.record("recovered",
                                positions=[p.to_dict() for p in self._open.values()],
                                working=[w.to_dict() for w in self._working.values()])
        # The journal is what this service believed when it died. The broker is
        # what is true now, and a restart is exactly when those differ. [st-v7oa]
        self.reconcile()
