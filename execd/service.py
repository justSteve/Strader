"""ExecService — the narrow door, and everything behind it. [st-eznu]

One object holds the whole service: the arming state, the journal, the bounds,
the broker seam, and the open position. Every path that can transmit runs
through :meth:`place`, and :meth:`place` runs through the bounds. There is no
second way in; the HTTP layer in ``execd.api`` is a translator over this class
and holds no policy of its own, which is why the bounds can be tested without
a socket.

Three asymmetries are deliberate and each has a test:

**Entries are hard, exits are easy.** An entry clears arming, the STOP file,
the position limit, the daily ceiling, a price band and a
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

**The stop and the take-profit are one bracket.** Steve, 2026-09-14 (st-fn5y):
*"Future filled orders will result in resting 'take profit' orders in addition
to stoplosses. The screen should be a live editor allowing an update to both
trigger conditions."* On a fill the service rests both — the SELL STOP below
and a SELL LIMIT at the target above — and treats them as one-cancels-the-
other by its own hand, because Schwab's OCO is not something this service
sends: when either fills, the other comes off before the close is booked;
``_market_close`` takes both off before its own close goes on and puts both
back on every failure branch; a partial exit resizes both; :meth:`adjust`
moves either by the same cancel-then-rest motion and refuses when the cancel
finds the leg already filled. A target that cannot be derived or rested is
``target_unprotected`` — a warning, not a fault, because the stop still
stands. Nothing here replaces an order in place: the transport has no PUT.

**The day's ceiling is read from the journal, not remembered.** A restart
recovers it. See ``execd.journal``.

**What is open is read from the broker, not believed.** The journal is the
authority on what this service intended and the broker is the authority on what
is held; treating the first as both is the defect :meth:`ExecService.reconcile`
exists to close. See its docstring. [st-v7oa]
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .arming import Arming
from .bounds import (
    CT, Bounds, DayState, QuoteView, Refusal, check_entry, check_exit,
    check_preview_cost,
)
from .broker import (
    COMMISSION_PER_CONTRACT_USD, Broker, BrokerError, OrderResult, OrderStatus, Position, Quote,
)
from .intent import OrderIntent, OrderType, Side, parse_occ
from .journal import Journal
from .stops import (
    CONTRACT_MULTIPLIER, exit_triggered, on_tick, premium_at_level, protective_stop_price,
    risk_usd, stop_is_consistent, take_profit_price, target_reached,
)


class Refused(Exception):
    """A bound said no. Carries the bound so the caller can name it."""

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(f"{refusal.bound}: {refusal.reason}")
        self.refusal = refusal


def _wall_of(credential: Any) -> datetime | None:
    """The seven-day wall of a vault-shaped credential, from its wrapped
    token's ``creation_timestamp``; ``None`` for anything else (the mock's
    stand-in credential, say). Kept here rather than imported from the
    transport module so this module stays transport-free."""
    try:
        created = int(credential["token"]["creation_timestamp"])
    except (KeyError, TypeError, ValueError):
        return None
    return datetime.fromtimestamp(created, tz=timezone.utc) + timedelta(days=7)


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
    #: ``live`` or ``paper`` (``execd.paper``). Stamped on the journal, the
    #: status body and every preview/place answer.
    mode: str = "live"
    #: ``schwab``, ``alpaca`` or ``mock`` — which broker this instance sends
    #: to. On every journal line, in ``/status``, and the badge on its page;
    #: two instances run side by side, one per broker (co-8mb1z).
    broker: str = ""

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
    — but it is the only thing between the caller and one, so it is tracked
    until :meth:`ExecService.reconcile` learns what became of it.
    """

    order_id: str
    symbol: str
    qty: int
    intent_id: str
    right: str
    limit: float | None = None
    stop_spx: float | None = None
    delta: float | None = None
    #: The order page's selection query (side, expiry, strike, delta, budget,
    #: attempts) the intent was priced from, when the page sent it — so a
    #: cancel can bring the form back priced fresh (st-fn5y; Steve: "assume
    #: the canceled order will be re-priced and re-armed"). ``None`` for an
    #: entry the desk or the API sent.
    page_query: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id, "symbol": self.symbol, "qty": self.qty,
            "intent_id": self.intent_id, "right": self.right, "limit": self.limit,
            "stop_spx": self.stop_spx, "delta": self.delta,
            "page_query": dict(self.page_query) if self.page_query else None,
        }


#: How long a position must be absent from the broker's own account before the
#: service believes it is gone. A positions endpoint that has not caught up with
#: a fill it reported seconds ago is an ordinary thing for a REST broker to do,
#: and treating that lag as a close would drop a live position and cancel the
#: stop under it. Absence has to persist to mean anything. [st-v7oa]
POSITION_SETTLE_S = 90.0

#: A mark further than this from the last one ``observe`` accepted, and
#: younger than ``MARK_BAND_WINDOW_S``, is a bad quote before it is a market
#: move: at ``spx == 0`` every long call is past its cut and the loop would
#: market-sell each one for nothing (audit finding 32 / 04 §7, st-xv5e).
#: The resting bracket at the broker is the exit while a mark is refused; a
#: genuine gap is accepted once the window has passed.
MARK_BAND_PCT = 1.0
MARK_BAND_WINDOW_S = 300.0

#: How long a resting leg may be missing from the broker's listing before it
#: is journaled as unaccounted for (the listing lags a fresh rest the same
#: way it lags a fresh fill — POSITION_SETTLE_S is the same grace). The id is
#: kept and the leg is NOT re-rested: a second stop beside one that is merely
#: unlisted is a short waiting for a print (audit finding 39, st-vqmr).
LEG_SETTLE_S = POSITION_SETTLE_S
#: A leg the broker reports CANCELED or REJECTED — not this service's cancel —
#: is re-rested once; cancelled again inside this window it is left off, loud,
#: rather than rested a third time against a broker that keeps killing it.
LEG_REREST_COOLDOWN_S = 300.0
#: How long a close this service sent may be missing from the broker's
#: listing before it is declared unknown, cleared, and the bracket re-rested.
#: Until 2026-09-17 it was cleared on ONE absent listing while positions got
#: POSITION_SETTLE_S for the same broker's lag — and the bracket went back on
#: beside a working market sell, with observe() free to fire a second one
#: (audit finding 26, st-b7i4). The same grace, for the same reason.
EXIT_SETTLE_S = POSITION_SETTLE_S
#: The fill sweep asks the broker for fills since the last poll minus this,
#: not since the last poll: a fill stamped with the exchange's clock at T and
#: listed only after the sweep at T+1 had moved the watermark past it was
#: skipped by every later sweep (audit finding 27, st-b7i4). Repeats are
#: dropped on (order_id, leg_id, at).
FILL_OVERLAP_S = 60.0

#: How long a send whose answer never came back is held as unconfirmed before
#: reconcile, having swept the broker's listing and found nothing matching,
#: releases the intent. Until then no entry goes out at all: the broker may be
#: holding an order this service has no id for (finding 25, st-xlz9).
SEND_SETTLE_S = 60.0
#: How many days of journals a restart reads back for a position still
#: open. _recover read today's file only, so a position held past the close
#: — a next-day contract, or a close that failed — came back the next
#: morning as nothing, was adopted from the broker with no stop_spx and no
#: bracket, and neither exit existed (audit finding 38, st-btob; 03 §1).
RECOVER_LOOKBACK_DAYS = 7
#: The journal events that carry a position's life across days. A working
#: entry, an unconfirmed send and the day's counts are today's alone: a
#: buy order from a prior session is dead at the exchange, and recovering
#: it would hold a slot for an order the listing can never show.
_CARRIED_EVENTS = frozenset((
    "filled", "stop_placed", "target_placed", "stop_adjusted", "target_adjusted",
    "canceled", "position_adopted", "position_gone", "position_corrected",
    "leg_unconfirmed", "leg_resolved", "exit_unfilled", "exit_resolved", "closed",
))
#: An adjust identical to the last completed one, arriving inside this many
#: seconds of its answer, is a replay (browser or proxy re-sending after a
#: lost response) and is answered from that answer (st-gw5m).
ADJUST_REPLAY_S = 20.0


@dataclass
class UnconfirmedSend:
    """An entry the service sent and got no answer to. The broker may or may
    not have taken it; only its own listing can say. Written to the journal
    as ``sending`` before the send and ``send_unknown`` after the error, so a
    restart carries it (st-xlz9)."""

    intent_id: str
    symbol: str
    qty: int
    limit: float | None
    right: str
    stop_spx: float | None
    delta: float | None
    at: datetime
    page_query: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"intent_id": self.intent_id, "symbol": self.symbol, "qty": self.qty,
                "limit": self.limit, "right": self.right, "stop_spx": self.stop_spx,
                "delta": self.delta, "at": self.at.isoformat(),
                "page_query": dict(self.page_query) if self.page_query else None}

    def matches(self, order: OrderResult) -> bool:
        """The broker order this send would have become: same contract, same
        side, same size, same limit, entered no earlier than the send."""
        if order.side is not Side.BUY_TO_OPEN or order.symbol != self.symbol:
            return False
        if order.qty != self.qty:
            return False
        if (self.limit is None) != (order.price is None):
            return False
        if self.limit is not None and abs(float(order.price or 0.0) - self.limit) > 1e-6:
            return False
        return order.submitted_at >= self.at - timedelta(seconds=5)


def _filled_qty_of(order: OrderResult) -> int:
    """How many contracts a FILLED order filled. The broker's
    ``filledQuantity`` when it carries one; the order's own size when it does
    not — a FILLED order fills what it asked for. Never the *position's* size:
    ``filled_qty or pos.qty`` booked a full close for a partial the body did
    not size (audit 2026-08-30 01 §6, never closed; st-7ah8)."""
    return order.filled_qty if order.filled_qty > 0 else order.qty


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
    #: the take-profit half of the bracket (st-fn5y): the resting SELL LIMIT
    #: and its price. ``None`` when it could not be derived or rested — the
    #: journal says why under ``target_unprotected``.
    target_order_id: str | None = None
    target_price: float | None = None
    #: the SPX level the take-profit was set at, when it was set as one
    #: (st-2j3m): the loop fires a market close when the mark reaches it,
    #: while the resting limit at ``target_price`` stays the protection if
    #: the box dies. ``None`` for a target given as a price — a dollar target
    #: is the resting limit alone, and nothing fires on the mark for it.
    target_spx: float | None = None
    #: the index level when the entry filled; with ``delta`` it is what lets
    #: an adjusted stop price move the SPX-mark trigger with it
    entry_spx: float | None = None
    entry_order_id: str = ""
    opened_at: datetime | None = None
    #: first time the broker failed to report this position, or ``None``
    missing_since: datetime | None = None
    #: the bracket's legs against the broker's listing (st-vqmr): first time
    #: each resting leg was missing from it, whether it has been missing past
    #: ``LEG_SETTLE_S`` (the card says so), and when this service last
    #: re-rested it after the broker reported it terminal
    stop_unlisted_since: datetime | None = None
    target_unlisted_since: datetime | None = None
    #: first time the broker's listing failed to report the in-flight close
    exit_unlisted_since: datetime | None = None
    stop_unaccounted: bool = False
    target_unaccounted: bool = False
    stop_rerested_at: datetime | None = None
    target_rerested_at: datetime | None = None
    #: the close this service has sent and not yet seen resolve. While this is
    #: set the SPX-mark loop does not fire again — re-sending a market close
    #: every tick until one fills was finding 2 of the 2026-08-30 audit, an
    #: oversell that grew once a second. [st-97z1]
    exit_order_id: str | None = None
    exit_reason: str | None = None
    #: what the entry cost in commission, from the broker's preview when the
    #: service opened it; the published per-contract rate for a position it
    #: recovered or adopted. Part of the page's P&L (Steve, 2026-09-14).
    entry_commission_usd: float = 0.0
    #: the best and worst ``net_if_closed_usd`` this position has shown, and
    #: when — struck from the valuations the status body computes, so they
    #: move only while something is reading the status (the page's poll,
    #: every few seconds while he watches). In memory only; a restart starts
    #: them again. Written into the ``closed`` line so the record can answer
    #: "how far did it go my way before the stop took it" (st-ff5j, Steve
    #: 2026-09-15: "the running total showed price at +70 … not sure that was
    #: a valid profit mark").
    best_net_usd: float | None = None
    best_at: datetime | None = None
    worst_net_usd: float | None = None
    worst_at: datetime | None = None

    @property
    def exit_in_flight(self) -> bool:
        return bool(self.exit_order_id)

    def leg_state(self, leg: str) -> str | None:
        """What the card may say about a leg: ``resting`` (an id this service
        holds and the broker's listing has not contradicted), ``unaccounted``
        (an id the listing has not reported for ``LEG_SETTLE_S``), ``None``
        (no leg — nothing resting). The word comes from the listing, not from
        the id alone (audit finding 41, st-vqmr)."""
        if not getattr(self, f"{leg}_order_id"):
            return None
        return "unaccounted" if getattr(self, f"{leg}_unaccounted") else "resting"

    def mark_water(self, net: float | None, now: datetime) -> None:
        if net is None:
            return
        if self.best_net_usd is None or net > self.best_net_usd:
            self.best_net_usd, self.best_at = net, now
        if self.worst_net_usd is None or net < self.worst_net_usd:
            self.worst_net_usd, self.worst_at = net, now

    def water_dict(self) -> dict[str, Any]:
        return {"best_net_usd": self.best_net_usd,
                "best_at": self.best_at.isoformat() if self.best_at else None,
                "worst_net_usd": self.worst_net_usd,
                "worst_at": self.worst_at.isoformat() if self.worst_at else None}

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "qty": self.qty, "entry_price": self.entry_price,
            "intent_id": self.intent_id, "right": self.right,
            "stop_spx": self.stop_spx, "delta": self.delta,
            "stop_order_id": self.stop_order_id, "stop_price": self.stop_price,
            "stop_state": self.leg_state("stop"),
            "target_order_id": self.target_order_id, "target_price": self.target_price,
            "target_state": self.leg_state("target"),
            "target_spx": self.target_spx,
            "entry_spx": self.entry_spx,
            "entry_order_id": self.entry_order_id,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "exit_order_id": self.exit_order_id, "exit_reason": self.exit_reason,
            "entry_commission_usd": self.entry_commission_usd,
            **self.water_dict(),
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
        self.journal = Journal(state / "journal", sha=config.sha, clock=clock,
                               mode=config.mode, broker=config.broker)
        self.arming = Arming(state / "STOP", clock=clock)
        self._lock = threading.RLock()
        self._open: dict[str, OpenPosition] = {}
        self._working: dict[str, WorkingEntry] = {}
        #: bracket legs whose position is gone but whose cancel was never
        #: confirmed — order_id → {symbol, leg, qty, intent_id} (st-7ah8)
        self._loose_legs: dict[str, dict[str, Any]] = {}
        #: the last completed adjust — (symbol, stop, target), when, its answer (st-gw5m)
        self._last_adjust: tuple[tuple[Any, Any, Any], datetime, dict[str, Any]] | None = None
        #: what the broker holds short on this service's instruments — symbol
        #: → qty (negative). Never this service's to manage, always its to
        #: show: the one state the bracket exists to prevent (st-7ah8)
        self._shorts: dict[str, int] = {}
        #: sells the fill sweep could attribute to no position, by order id,
        #: so each is journaled once
        self._unattributed: set[str] = set()
        #: entries sent whose answer never came back — intent_id → the send;
        #: nothing else goes out until reconcile has accounted for each
        self._unconfirmed: dict[str, UnconfirmedSend] = {}
        #: the last mark ``observe`` acted on, and when — the band a new mark
        #: is judged against (st-xv5e)
        self._last_mark: tuple[float, datetime] | None = None
        #: every execution leg the fill sweep has seen, as (order_id, leg_id,
        #: at): the overlapping window returns each one again (st-b7i4)
        self._swept_fills: set[tuple[str, int | None, str]] = set()
        self._mark_refused_streak = 0
        #: working buy orders on this service's instruments that it did not
        #: send and cannot match to a send — order_id → OrderResult dict,
        #: journaled once, shown, never adopted
        self._foreign_orders: dict[str, dict[str, Any]] = {}
        #: long positions the broker holds on this service's instruments that
        #: this service never opened — Steve's own legs. symbol → Position.
        #: Shown on the page, never slotted, never flattened (finding 30,
        #: st-isx3: adopting them made FLATTEN sell the wings of his butterfly)
        self._foreign_positions: dict[str, Position] = {}
        #: order ids this service has already booked a close on, so a fill the
        #: broker reports twice — or reports after the close was booked from
        #: the place answer — is never booked again. 2026-09-16 10:19:29 CT a
        #: stop fill landed between reconcile's position read and its fill
        #: sweep; the stale snapshot adopted the position and the next poll
        #: booked the same fill against it: three closes for two orders.
        #: Rebuilt from the day's ``closed`` lines at recovery.
        self._booked_exits: set[str] = set()
        self._last_fill_poll = clock()
        self._recover()

    # ── arming (page-only; none of these has an API route) ───────────────
    def unlock(self, credential: Any) -> dict[str, Any]:
        """Arm the service until Steve presses LOCK or STOP, or the process
        restarts. No clock ends it.

        Until 2026-09-24 an unlock armed only until the session close (or
        23:59 CT after hours), and then ran the day's 14:55 close-out. Steve,
        that day: "omg - never ever place that kind of restriction on me ...
        As 0DTE trades, if i don't close them, they expire. flat. But I will
        _never ask that you do it automatically." Both are gone. [co-8mb1z]"""
        with self._lock:
            state = self.arming.unlock(credential)
            self.journal.record("unlock", state=state.value,
                                refresh_wall=_wall_of(credential))
            # The start-up reconcile, deferred from the constructor when the
            # service came back LOCKED (see _recover): now there is a
            # credential to ask the broker with.
            self.reconcile()
            return self.status()

    def _needs_credential(self) -> bool:
        """Does this broker need the arming state's credential to answer?
        The Schwab transport does (it is bound to ``arming.credential``); the
        mock does not. Read off the broker rather than its class name so a
        third broker declares itself."""
        return getattr(self.broker, "credential_source", None) is not None or \
            hasattr(self.broker, "bind")

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
        kill switch on is the one control that must never be gated.

        The kill file is written **before** the service lock is taken. ``place``
        holds that lock across every broker round trip of an entry — reconcile,
        the quote, the preview, the send — and a STOP that waited for it landed
        after the order it was meant to stop (finding 35 of the 2026-09-15
        audit, the half of finding 10 the first fix did not reach; st-jm6u).
        Nothing here takes the service lock at all: the touch is atomic and
        idempotent, the journal has its own lock, and the status read is a
        snapshot the page can afford to see mid-entry. Waiting for the lock
        even to journal would hold the page's STOP response open until the
        entry returned from the broker — true, but late."""
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
        valuations = [(p, self.valuation(p)) for p in list(self._open.values())]
        for p, v in valuations:
            p.mark_water(v.get("net_if_closed_usd"), now)
        return {
            "now": now.isoformat(),
            "now_ct": now.astimezone(CT).strftime("%Y-%m-%d %H:%M:%S CT"),
            "sha": self.config.sha,
            "mode": self.config.mode,
            "broker": self.config.broker,
            "arming": self.arming.status(),
            "day": {
                "open_positions": day.open_positions,
                "realized_loss_usd": day.realized_loss_usd,
            },
            # One quote read per position per status call: the position row
            # and the day row are struck at the same price (14:37 CT today
            # they were not — two reads, two bids, two different nets).
            "positions": [{**p.to_dict(), "valuation": v} for p, v in valuations],
            "working": [w.to_dict() for w in self._working.values()],
            # The three things that must never be silent (2026-09-15 audit,
            # st-7ah8 / st-zm2u): a leg resting with no position behind it, a
            # short the account holds, and holdings the positions reader left
            # out — each is a line on the page until it is gone.
            "loose_legs": [{"order_id": k, **v} for k, v in self._loose_legs.items()],
            "unconfirmed_sends": [s.to_dict() for s in self._unconfirmed.values()],
            "foreign_orders": list(self._foreign_orders.values()),
            "foreign_positions": [p.to_dict() for p in self._foreign_positions.values()],
            "shorts": [{"symbol": s, "qty": q} for s, q in self._shorts.items()],
            # the day's close-out: when it is due, whether it has run, and
            # anything still held past it (st-9j8e)
            "excluded_positions": dict(getattr(self.broker, "excluded_positions", {}) or {}),
            "pnl": self._day_pnl([v for _p, v in valuations]),
            "bounds": self.bounds.to_dict(),
            "journal": str(self.journal.path_for()),
            # When each grant's seven-day wall is, and nothing else (no
            # values) — so the token-age heartbeat can read the service instead
            # of a file once the files are gone (st-p8k8). Absent for a broker
            # that has no grants to report on.
            "credential": self._credential_status(),
            # The account's money in Schwab's own words, cached briefly so a
            # page polling every few seconds does not become an account read
            # every few seconds (st-shhi).
            "balances": self._balances_cached(now),
        }

    #: how long a balances read is reused before the broker is asked again
    BALANCES_TTL_S = 15.0

    def _balances_cached(self, now: datetime) -> dict[str, Any] | None:
        read = getattr(self.broker, "balances", None)
        if not callable(read):
            return None
        cached = getattr(self, "_balances_cache", None)
        if cached is not None and (now - cached[0]).total_seconds() < self.BALANCES_TTL_S:
            return cached[1]
        try:
            out: dict[str, Any] = dict(read())
            out["error"] = None
        except Exception as exc:  # a broker that cannot say is reported, not hidden
            out = {"available_funds": None, "option_buying_power": None,
                   "error": str(exc)}
        out["as_of"] = now.isoformat()
        self._balances_cache = (now, out)
        return out

    def _credential_status(self) -> dict[str, Any] | None:
        status = getattr(self.broker, "token_status", None)
        if not callable(status):
            return None
        try:
            out = dict(status())
        except Exception as exc:  # a broker that cannot say is reported, not hidden
            out = {"error": type(exc).__name__}
        # While LOCKED the trading grant is not in memory, so its wall cannot
        # be read — but the journal remembers the wall from the last unlock or
        # re-authorisation, and the 06:30 token-age heartbeat runs before
        # Steve is awake to unlock. A date is not a secret.
        out["last_known_trading_wall"] = self._last_known_trading_wall()
        return out

    def _last_known_trading_wall(self) -> str | None:
        days = self.journal.days()
        for day in reversed(days[-10:]):
            latest: str | None = None
            for e in self.journal.read(day):
                if e.get("event") == "unlock" and e.get("refresh_wall"):
                    latest = e["refresh_wall"]
                elif (e.get("event") == "reauth" and e.get("app") == "trading"
                        and e.get("refresh_wall")):
                    latest = e["refresh_wall"]
            if latest:
                return latest
        return None

    def day_state(self) -> DayState:
        return self.journal.day_state()

    # ── P&L, for the page (Steve, 2026-09-14: "the unrealized pnl including
    # all aspects of the order needs to display on the page") ─────────────
    def valuation(self, pos: OpenPosition) -> dict[str, Any]:
        """What the position is worth now and what it would net if closed.

        ``value_usd`` is at the live **bid** — the price a market sell gets —
        not the mid. ``commissions_usd`` counts both ways: what the entry cost
        (from the broker's preview) and what the exit will cost at the
        published per-contract rate. ``net_if_closed_usd`` is the number Steve
        asked for; ``at_stop_usd`` and ``at_target_usd`` are the same
        arithmetic at the resting stop's and the resting target's price. A
        quote that cannot be read leaves the money fields ``None`` and says
        why."""
        n = pos.qty
        cost = round(pos.entry_price * CONTRACT_MULTIPLIER * n, 2)
        exit_fee = round(COMMISSION_PER_CONTRACT_USD * n, 2)
        fees = round(pos.entry_commission_usd + exit_fee, 2)
        out: dict[str, Any] = {
            "cost_usd": cost, "entry_commission_usd": round(pos.entry_commission_usd, 2),
            "exit_commission_usd": exit_fee, "commissions_usd": fees,
            "bid": None, "ask": None, "quote_age_s": None,
            "value_usd": None, "unrealized_usd": None, "net_if_closed_usd": None,
            "at_stop_usd": None, "at_target_usd": None, "error": None,
        }
        if pos.stop_price is not None:
            out["at_stop_usd"] = round((pos.stop_price - pos.entry_price)
                                       * CONTRACT_MULTIPLIER * n - fees, 2)
        if pos.target_price is not None:
            out["at_target_usd"] = round((pos.target_price - pos.entry_price)
                                         * CONTRACT_MULTIPLIER * n - fees, 2)
        try:
            q = self.broker.quote(pos.symbol)
        except BrokerError as exc:
            out["error"] = str(exc)
            return out
        out["bid"], out["ask"] = q.bid, q.ask
        out["quote_age_s"] = round(q.age_s(self.clock()), 1)
        value = round(q.bid * CONTRACT_MULTIPLIER * n, 2)
        out["value_usd"] = value
        out["unrealized_usd"] = round(value - cost, 2)
        out["net_if_closed_usd"] = round(value - cost - fees, 2)
        return out

    def _day_pnl(self, valuations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Today's money in one place: realized from the journal's ``closed``
        lines (gains positive, as they are written), unrealized from the
        valuations handed in (struck once, shared with the position rows),
        and the two together."""
        realized = 0.0
        closes = 0
        for e in self.journal.read():
            if e.get("event") == "closed" and isinstance(e.get("pnl_usd"), (int, float)):
                realized += float(e["pnl_usd"])
                closes += 1
        realized = round(realized, 2)
        if valuations is None:
            valuations = [self.valuation(p) for p in list(self._open.values())]
        unrealized: float | None = 0.0
        for v in valuations:
            if v["net_if_closed_usd"] is None:
                unrealized = None
                break
            unrealized += v["net_if_closed_usd"]
        if unrealized is not None:
            unrealized = round(unrealized, 2)
        return {"realized_usd": realized, "closes": closes,
                "unrealized_net_usd": unrealized,
                "day_usd": None if unrealized is None else round(realized + unrealized, 2)}

    def has_exposure(self) -> bool:
        """Anything the watcher should be watching: a position held, or an
        entry the broker acknowledged and has not resolved. [st-k6gl]"""
        with self._lock:
            return bool(self._open or self._working)

    def has_working(self) -> bool:
        """Is an entry out at the broker, unresolved? The page asks before
        every poll, because while one is working the screen must show the
        BROKER's state and not this service's belief. [st-jdg5]"""
        with self._lock:
            return bool(self._working)

    def quote(self, symbol: str) -> Quote:
        return self.broker.quote(symbol)

    def chain(self, root: str, expiry: str | None = None) -> dict[str, Any]:
        return self.broker.chain(root, expiry)

    def market_read(self, kind: str, params: dict[str, str]) -> Any:
        """A raw market-data body for the repo's readers (st-p8k8). No bound
        applies — nothing here can transmit — and no arming state gates it:
        the market credential is held outside the lock on purpose."""
        return self.broker.market_read(kind, params)

    def orders(self) -> list[OrderResult]:
        return self.broker.orders()

    def positions(self) -> list[Position]:
        return self.broker.positions()

    def spx_mark(self) -> float:
        """The index level the stops are denominated in.

        A quote with no price in it is no mark — ``BrokerError``, the same as
        no quote at all — rather than the 0.0 that ``last or mid`` used to
        hand back, which every caller then compared to a stop as if it were
        the index at zero (finding 32, st-xv5e)."""
        q = self.broker.quote(self.config.index_symbol)
        mark = q.last or q.mid
        if not (isinstance(mark, (int, float)) and math.isfinite(mark) and mark > 0):
            raise BrokerError(
                f"no usable {self.config.index_symbol} mark — last {q.last!r}, "
                f"bid {q.bid!r}, ask {q.ask!r}")
        return float(mark)

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
            self._journal_preview(intent, prev)
            return {"refused": None, "preview": prev.to_dict(), "would_send": prev.accepted,
                    "mode": self.config.mode}

    def _journal_preview(self, intent: OrderIntent, prev: Any) -> None:
        """The shaped preview, and — when the transport kept it — the broker's
        raw body on its own line, so a live preview records the real shape
        the spec-derived fixture stands in for (st-k6gl)."""
        self.journal.record("preview", intent_id=intent.intent_id, preview=prev.to_dict())
        if getattr(prev, "raw", None) is not None:
            self.journal.record("preview_raw", intent_id=intent.intent_id, body=prev.raw)

    # ── the one path that transmits ──────────────────────────────────────
    def place(self, intent: OrderIntent, *,
              page_query: dict[str, str] | None = None) -> dict[str, Any]:
        """``page_query`` is the order page's selection the intent was priced
        from; it rides on the working entry so a cancel can re-price it. It
        is never part of the intent and never reaches the broker."""
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
            # The reconcile may just have found this very intent at the broker
            # (a send whose answer was lost): ask again before sending.
            replay = self._replay(intent.intent_id)
            if replay is not None:
                self.journal.record("replayed", intent_id=intent.intent_id,
                                    order_id=replay.get("order", {}).get("order_id"))
                return {**replay, "replayed": True}

            self.journal.record("request", kind="place", intent_id=intent.intent_id,
                                intent=intent.to_dict())
            if intent.is_entry:
                return self._place_entry(intent, page_query=page_query)
            return self._place_exit(intent)

    def cancel(self, order_id: str) -> dict[str, Any]:
        """Cancelling is getting out of the way of an order, so it is an exit-
        class action: legal whenever there is a credential — with one refusal.

        The resting stop under a live position is not an order in the way, it
        is the position's only protection if this box dies. Cancelling it alone
        opens risk, which no exit-class credential may do (finding 5 of the
        2026-08-30 audit — it used to succeed, silently). The resting
        take-profit is the other half of the same bracket and is refused for
        the same reason: the bracket is edited with :meth:`adjust`, never
        pulled apart. The ways out that exist all handle both properly: an
        exit and flatten cancel them in the same motion they close the
        position they protect.

        **The answer has three shapes, and the caller is told which** (the
        ``confirmed`` key; st-jdg5). ``CANCELED`` / ``REJECTED`` is off:
        resolved, and the form may be re-priced. Still working — Schwab
        acknowledges a cancel and then *works* it, so the read can say
        ``PENDING_CANCEL`` — is **not** off: the exchange still holds the
        order and it can still fill, so nothing is resolved and
        ``confirmed`` is false. ``FILLED`` is too late: the working entry is
        left in place on purpose so the ordinary fill path promotes it with
        its bracket, rather than the fill being adopted afterwards with no
        stop derivable from it."""
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
                        f"the position unprotected; move it with adjust, or close "
                        f"the position with an exit or flatten, which take the "
                        f"bracket off in the same motion")
                    self.journal.record("refused", kind="cancel", order_id=order_id,
                                        refused=refusal.to_dict())
                    raise Refused(refusal)
                if pos.target_order_id == order_id:
                    refusal = Refusal(
                        "take_profit",
                        f"{order_id} is the resting take-profit under a live "
                        f"{pos.symbol} position — it is one half of the bracket; "
                        f"move it with adjust, or close the position with an exit "
                        f"or flatten, which take the bracket off in the same motion")
                    self.journal.record("refused", kind="cancel", order_id=order_id,
                                        refused=refusal.to_dict())
                    raise Refused(refusal)
            result = self.broker.cancel(order_id)

            # A cancel is a REQUEST, and the answer has three shapes. Until
            # st-jdg5 this path read none of them: it journaled ``canceled``,
            # dropped the working entry and told him it was gone, whatever the
            # broker actually said. The transport has always known better — it
            # polls to a deadline and hands back the broker's own word — and
            # the bracket paths were taught to read it by finding 24 of the
            # 2026-09-15 audit. This, the one Steve taps, was not. [st-jdg5]
            if result.is_working:
                # PENDING_CANCEL and every other non-terminal status: Schwab
                # has the cancel and still has the ORDER. It can still fill.
                # Nothing is resolved and nothing is re-priced — the entry
                # stays working, so the card keeps showing it and he can ask
                # again. Telling him it was cancelled here is how a live
                # position appears out of an order he believes he pulled.
                self.journal.record("cancel_unconfirmed", order_id=order_id,
                                    status=result.status.value,
                                    detail=result.message or "the broker still holds it",
                                    order=result.to_dict())
                return {"refused": None, "order": result.to_dict(), "confirmed": False}
            if result.status is OrderStatus.FILLED:
                # The cancel lost the race. The working entry is deliberately
                # NOT resolved: it still carries the stop level and the delta,
                # so the ordinary fill path promotes it to a position AND
                # rests its bracket. Resolving it as cancelled would leave the
                # broker's fill to be adopted instead — a live position with
                # ``stop_unprotected`` against it, which is the worst state
                # this service has.
                self.journal.record("cancel_too_late", order_id=order_id,
                                    detail="it filled before the cancel reached the broker",
                                    order=result.to_dict())
                self.reconcile()
                return {"refused": None, "order": result.to_dict(), "confirmed": False,
                        "filled": True}

            self.journal.record("canceled", order_id=order_id, order=result.to_dict())
            for pos in self._open.values():
                if pos.exit_order_id == order_id:
                    # The close was pulled by hand; the position is live again
                    # and gets its bracket back, and the SPX loop may fire.
                    self.journal.record("exit_resolved", symbol=pos.symbol,
                                        order_id=order_id, outcome="canceled",
                                        reason=pos.exit_reason,
                                        detail="cancelled by request")
                    pos.exit_order_id = None
                    pos.exit_reason = None
                    self._rest_bracket(pos)
            if order_id in self._working:
                self._resolve_working(order_id, outcome="canceled",
                                      detail="cancelled by request")
            return {"refused": None, "order": result.to_dict(), "confirmed": True}

    def flatten(self, reason: str = "flatten") -> dict[str, Any]:
        """Close everything at market, taking both halves of every bracket
        off first. Legal while STOPped, while stood down, and at any hour —
        the whole point of the switch is that it never traps him."""
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

        This is the accurate stop while the box is alive; the resting bracket
        at the broker is what survives it not being. When it fires, both
        resting legs come off before the close goes on (``_market_close``).

        A take-profit set as an SPX level (st-2j3m) fires here too, the same
        way: the mark reaches ``target_spx``, both legs come off, a market
        close goes on, reason ``spx-target``. The resting limit at the broker
        is the target's floor under this loop the way the resting stop is the
        stop's — whichever reaches first is the exit, and the ``closed`` line
        names which. A target given as a price has no level and nothing
        fires on the mark for it."""
        with self._lock:
            fired: list[dict[str, Any]] = []
            pending: list[dict[str, Any]] = []
            if (why := self._mark_refusal(spx)) is not None:
                # Journaled once per streak: the watcher asks every 5 s and a
                # dead feed would otherwise write a line each pass.
                if self._mark_refused_streak == 0:
                    last = self._last_mark[0] if self._last_mark else None
                    self.journal.record("mark_refused", spx=spx, last_spx=last, detail=why)
                self._mark_refused_streak += 1
                return {"spx": spx, "fired": fired, "pending": pending, "refused": why}
            if self._mark_refused_streak:
                self.journal.record("mark_accepted", spx=spx,
                                    refused=self._mark_refused_streak)
                self._mark_refused_streak = 0
            self._last_mark = (float(spx), self.clock())
            for pos in list(self._open.values()):
                if pos.stop_spx is None and pos.target_spx is None:
                    continue
                if pos.exit_in_flight:
                    # A close is already working at the broker. Firing again
                    # would sell the position twice — finding 2 was exactly
                    # this, once a second. [st-97z1]
                    pending.append({"symbol": pos.symbol,
                                    "order_id": pos.exit_order_id,
                                    "reason": pos.exit_reason})
                    continue
                reason = None
                if pos.stop_spx is not None and exit_triggered(pos.right, spx, pos.stop_spx):
                    reason = "spx-stop"
                    self.journal.record("exit_triggered", symbol=pos.symbol,
                                        spx=spx, stop_spx=pos.stop_spx,
                                        intent_id=pos.intent_id)
                elif pos.target_spx is not None and target_reached(pos.right, spx, pos.target_spx):
                    reason = "spx-target"
                    self.journal.record("target_triggered", symbol=pos.symbol,
                                        spx=spx, target_spx=pos.target_spx,
                                        target_price=pos.target_price,
                                        intent_id=pos.intent_id)
                if reason is None:
                    continue
                try:
                    fired.append(self._market_close(pos, reason=reason))
                except (BrokerError, Refused) as exc:
                    # One position's trouble must not stop the loop watching
                    # the others. The bracket was re-rested before this raised.
                    self.journal.record("error", kind=reason,
                                        symbol=pos.symbol, detail=str(exc))
                    fired.append({"symbol": pos.symbol, "closed": False,
                                  "error": str(exc)})
            return {"spx": spx, "fired": fired, "pending": pending, "refused": None}

    def _mark_refusal(self, spx: Any) -> str | None:
        """A mark the exit loop must not act on: not a number, not a price
        (zero, negative, infinite), or — inside ``MARK_BAND_WINDOW_S`` of the
        last mark accepted — further from it than ``MARK_BAND_PCT``. Finding
        32 (st-xv5e): at ``spx == 0`` every long call is past its cut and the
        loop would market-sell each one for nothing, and a quote that is
        wrong rather than moved fires the same way. The resting bracket at
        the broker is the exit while a mark is refused; a genuine gap is
        accepted once the window has passed."""
        try:
            mark = float(spx)
        except (TypeError, ValueError):
            return f"mark {spx!r} is not a number — not acting on it"
        if not (math.isfinite(mark) and mark > 0):
            return f"mark {spx!r} is not a price — not acting on it"
        if self._last_mark is not None:
            last, at = self._last_mark
            age = (self.clock() - at).total_seconds()
            if age < MARK_BAND_WINDOW_S:
                moved = abs(mark - last)
                band = last * MARK_BAND_PCT / 100.0
                if moved > band:
                    return (f"mark {mark:g} is {moved:.2f} from the last mark accepted "
                            f"({last:g}, {age:.0f} s ago) — more than {MARK_BAND_PCT:g} % "
                            f"— not acting on it until {MARK_BAND_WINDOW_S:.0f} s have passed")
        return None

    def poll_fills(self) -> dict[str, Any]:
        """Pick up fills the service did not initiate — a resting protective
        stop or take-profit that triggered while nothing was watching."""
        with self._lock:
            return self._pick_up_fills()

    def _pick_up_fills(self) -> dict[str, Any]:
        """The fill sweep, without the lock, so ``reconcile`` can run it first.

        Order matters: a leg that fired at the broker has to be booked — with
        its P&L, against the day's ceiling — before the position sweep notices
        the position is gone. Reversed, a losing trade would vanish from the
        ceiling it was supposed to debit. Booking goes through ``_book_close``,
        which takes the *other* leg of the bracket off first (st-fn5y)."""
        since = self._last_fill_poll - timedelta(seconds=FILL_OVERLAP_S)
        now = self.clock()
        try:
            fills = self.broker.fills_since(since)
        except BrokerError as exc:
            self.journal.record("error", kind="poll_fills", detail=str(exc))
            return {"picked_up": [], "error": str(exc)}
        self._last_fill_poll = now
        picked: list[dict[str, Any]] = []
        for fill in fills:
            if fill.side is not Side.SELL_TO_CLOSE:
                continue
            key = (fill.order_id, fill.leg_id, fill.at.isoformat())
            if key in self._swept_fills:
                continue                # the overlap's own repeat; the same event
            self._swept_fills.add(key)
            if fill.order_id in self._booked_exits:
                # Already booked — from the place answer (a market close, a
                # target that filled as it landed) or an earlier sweep. A fill
                # made inside the broker call carries a time after the `now`
                # read above it, so the next window returns it again; the
                # flatten fill paper-0030 came back as `unattributed_sell`
                # four minutes later and stop fill paper-0032 was booked
                # twice (2026-09-16). Silent: it is the same event.
                continue
            pos = self._open.get(fill.symbol)
            if pos is None:
                # A sell on a symbol this service is not holding. Until
                # 2026-09-15 this was dropped on the floor, which is how a
                # stop that filled after its position was closed became an
                # invisible short (finding 29, st-7ah8). It is journaled
                # once, loud; a loose leg's fill is booked by reconcile.
                if fill.order_id in self._loose_legs or fill.order_id in self._unattributed:
                    continue
                self._unattributed.add(fill.order_id)
                self.journal.record("unattributed_sell", symbol=fill.symbol,
                                    order_id=fill.order_id, qty=fill.qty, price=fill.price,
                                    detail="a SELL_TO_CLOSE filled on a symbol this service "
                                           "holds no position in — if it is this service's "
                                           "leg the account is short; check the broker")
                continue
            if fill.order_id == pos.exit_order_id:
                # The close this service sent and was waiting on. [st-97z1]
                kind = pos.exit_reason or "exit"
                why = "in-flight-close"
                pos.exit_order_id = None
                pos.exit_reason = None
            elif pos.stop_order_id and fill.order_id == pos.stop_order_id:
                kind, why = "protective-stop", "resting-stop"
                pos.stop_order_id = None        # it filled; nothing to cancel
            elif pos.target_order_id and fill.order_id == pos.target_order_id:
                kind, why = "target", "resting-target"
                pos.target_order_id = None
            elif pos.stop_order_id or pos.target_order_id:
                # A sell on a held symbol from an order this service did not
                # place — closed by hand in the broker's app, or expired
                # (paper's expiry fill). Until 2026-09-15 this was skipped and
                # the position lingered until the gone-sweep dropped it 90 s
                # later with no P&L booked. It is a close; book it, and
                # _book_close pulls whatever legs still rest (st-ee8f).
                kind, why = "external", "closed-outside-this-service"
            else:
                kind, why = "protective-stop", "resting-stop"
            closed_qty = min(fill.qty, pos.qty) if fill.qty > 0 else pos.qty
            booked = self._book_close(pos, order_id=fill.order_id, exit_px=fill.price,
                                      closed_qty=closed_qty, reason=kind, why=why)
            picked.append({"symbol": pos.symbol, "exit_price": fill.price,
                           "pnl_usd": booked["pnl_usd"],
                           "remaining_qty": booked["remaining_qty"],
                           "order_id": fill.order_id, "reason": kind})
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
            except BrokerError as exc:
                self.journal.record("error", kind="reconcile", detail=str(exc))
                return {"promoted": [], "released": [], "adopted": [],
                        "corrected": [], "error": str(exc)}

            # Fills first. A stop that fired has to be booked against the day's
            # ceiling before the position sweep sees the position is gone.
            self._pick_up_fills()
            # The positions are read AFTER the fill sweep: a stop that fills
            # between a position read and the sweep leaves a snapshot that
            # still holds the contract, and the sweep below would adopt a
            # position this service just closed (2026-09-16 10:19:29 CT —
            # the paper book's sweep inside fills_since crossed the stop a
            # second after positions() had been read).
            try:
                broker_positions = {p.symbol: p for p in self.broker.positions()}
            except BrokerError as exc:
                self.journal.record("error", kind="reconcile", detail=str(exc))
                return {"promoted": [], "released": [], "adopted": [],
                        "corrected": [], "error": str(exc)}
            found = self._reconcile_orphans(broker_orders)
            promoted, released = self._reconcile_working(broker_orders)
            exits = self._reconcile_exits(broker_orders)
            legs = self._reconcile_legs(broker_orders)
            loose = self._reconcile_loose_legs(broker_orders)
            adopted, corrected, gone = self._reconcile_positions(broker_positions)
            return {"promoted": promoted, "released": released, "exits": exits,
                    "legs": legs, "loose": loose, "found": found,
                    "adopted": adopted, "corrected": corrected, "gone": gone,
                    "error": None}

    def _known_order_ids(self) -> set[str]:
        ids: set[str] = set(self._working) | set(self._loose_legs)
        for pos in self._open.values():
            for oid in (pos.entry_order_id, pos.stop_order_id, pos.target_order_id,
                        pos.exit_order_id):
                if oid:
                    ids.add(oid)
        return ids

    def _reconcile_orphans(self, broker_orders: dict[str, OrderResult]) -> list[dict[str, Any]]:
        """The orphan sweep: every order in the broker's listing that this
        service holds no id for. Three kinds (finding 25, st-xlz9):

        1. **A send whose answer never came back.** Matched by contract, side,
           size, limit and time to an ``UnconfirmedSend``; it becomes the
           working entry (or the position, if it already filled) that a
           returned answer would have made it. Nothing matching after
           ``SEND_SETTLE_S`` releases the intent: the broker did not take it.
        2. **A working entry the transport could not name** (``unnamed:…``
           when the 201 carried no usable Location). Matched the same way and
           re-keyed, instead of holding its slot forever under an id the
           listing can never contain.
        3. **Anything else buying to open on this service's instruments** —
           journaled once as ``foreign_order`` and shown, never adopted."""
        found: list[dict[str, Any]] = []
        known = self._known_order_ids()
        unknown = [o for oid, o in broker_orders.items()
                   if oid not in known and oid not in self._foreign_orders]
        now = self.clock()

        for intent_id, send in sorted(self._unconfirmed.items(), key=lambda kv: kv[1].at):
            match = next((o for o in unknown if send.matches(o)
                          and o.status not in (OrderStatus.CANCELED, OrderStatus.REJECTED)), None)
            if match is None:
                if (now - send.at).total_seconds() < SEND_SETTLE_S:
                    continue
                self._unconfirmed.pop(intent_id, None)
                self.journal.record("send_resolved", intent_id=intent_id, symbol=send.symbol,
                                    outcome="not-found",
                                    detail=f"nothing matching in the broker's listing "
                                           f"{SEND_SETTLE_S:.0f}s after the send — the "
                                           f"broker did not take it; the intent may be re-sent")
                found.append({"intent_id": intent_id, "outcome": "not-found", "order_id": None})
                continue
            unknown.remove(match)
            self._unconfirmed.pop(intent_id, None)
            self.journal.record("send_resolved", intent_id=intent_id, symbol=send.symbol,
                                outcome="found", order_id=match.order_id,
                                status=match.status.value)
            work = WorkingEntry(
                order_id=match.order_id, symbol=send.symbol, qty=send.qty,
                intent_id=intent_id, right=send.right, limit=send.limit,
                stop_spx=send.stop_spx, delta=send.delta, page_query=send.page_query)
            self._working[work.order_id] = work
            self.journal.record("working", kind="entry", intent_id=intent_id,
                                symbol=work.symbol, qty=work.qty, order_id=work.order_id,
                                status=match.status.value, limit=work.limit,
                                stop_spx=work.stop_spx, delta=work.delta,
                                page_query=work.page_query, found_by="reconcile")
            found.append({"intent_id": intent_id, "outcome": "found",
                          "order_id": match.order_id, "status": match.status.value})
            # _reconcile_working, next, promotes it if it already filled.

        for old_id, work in list(self._working.items()):
            if not old_id.startswith("unnamed:") or old_id in broker_orders:
                continue
            probe = UnconfirmedSend(intent_id=work.intent_id, symbol=work.symbol, qty=work.qty,
                                    limit=work.limit, right=work.right, stop_spx=work.stop_spx,
                                    delta=work.delta, at=datetime(2000, 1, 1, tzinfo=timezone.utc))
            match = next((o for o in unknown if probe.matches(o)), None)
            if match is None:
                continue
            unknown.remove(match)
            self._working.pop(old_id)
            self._working[match.order_id] = replace(work, order_id=match.order_id)
            self.journal.record("working_identified", intent_id=work.intent_id,
                                symbol=work.symbol, old_order_id=old_id,
                                order_id=match.order_id, status=match.status.value)
            found.append({"intent_id": work.intent_id, "outcome": "identified",
                          "order_id": match.order_id})

        for o in unknown:
            if o.side is not Side.BUY_TO_OPEN or not o.is_working:
                continue
            try:
                root = parse_occ(o.symbol).root
            except ValueError:
                continue
            if root not in self.bounds.instruments:
                continue
            self._foreign_orders[o.order_id] = o.to_dict()
            self.journal.record("foreign_order", order_id=o.order_id, symbol=o.symbol,
                                qty=o.qty, price=o.price,
                                detail="a working buy on this service's instruments that "
                                       "it did not send — shown, not adopted")
        return found

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
        qty = min(_filled_qty_of(order), work.qty)
        try:
            spx = self.spx_mark()
        except BrokerError:
            spx = None
        pos = self._open.get(work.symbol)
        if pos is not None:
            # The position grew. Its resting bracket is now smaller than what
            # is held, which is the same silent hole in the other direction,
            # so the old legs come off before correctly sized ones go on.
            self._add_to_position(pos, qty, fill_px, intent_id=work.intent_id,
                                  order_id=order.order_id, spx=spx,
                                  stop_spx=work.stop_spx, delta=work.delta,
                                  found_by="reconcile")
            self._resolve_working(order.order_id, outcome="filled")
            return
        pos = OpenPosition(
            symbol=work.symbol, qty=qty, entry_price=fill_px,
            intent_id=work.intent_id, right=work.right,
            stop_spx=work.stop_spx, delta=work.delta, entry_spx=spx,
            entry_order_id=order.order_id, opened_at=self.clock(),
        )
        self._open[pos.symbol] = pos
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
            self._place_take_profit(pos)
            return
        self._place_protective_stop(pos, spx)
        self._place_take_profit(pos)

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
            if order is None:
                # Absent has to persist to mean anything — the same rule the
                # position sweep applies to the same broker's listing. Meanwhile
                # the close stays in flight: observe() does not fire again and
                # the bracket stays off (finding 26, st-b7i4).
                since = pos.exit_unlisted_since
                if since is None:
                    pos.exit_unlisted_since = self.clock()
                    continue
                if (self.clock() - since).total_seconds() < EXIT_SETTLE_S:
                    continue
            else:
                pos.exit_unlisted_since = None
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
                      else f"the broker's listing has not reported this close for "
                           f"{EXIT_SETTLE_S:.0f} s — clearing it so the exit path is "
                           f"free to fire again")
            pos.exit_unlisted_since = None
            self.journal.record("exit_resolved", symbol=pos.symbol,
                                order_id=order_id, outcome=outcome,
                                reason=pos.exit_reason, detail=detail)
            pos.exit_order_id = None
            pos.exit_reason = None
            # The close is not happening; the position is live again and needs
            # its broker-resident bracket back.
            self._rest_bracket(pos)
            resolved.append({"symbol": pos.symbol, "order_id": order_id,
                             "outcome": outcome, "closed": False})
        return resolved

    def _reconcile_legs(self, broker_orders: dict[str, OrderResult]) -> list[dict[str, Any]]:
        """Each tracked position's resting legs against the broker's listing.

        Until 2026-09-17 the leg ids were believed, never reconciled: the
        service learned a leg's true state only when it cancelled it or when
        the fill sweep happened to catch its execution, so a stop the broker
        had cancelled, expired, rejected after acceptance, or Steve had
        cancelled by hand in the Schwab app was reported resting until the
        next cancel — and ``_recover`` restored the id from the journal with
        no check (audit finding 39, 04 §5 second bullet, st-vqmr). The same
        loop ``_reconcile_working`` is:

        - **working** — nothing to do; a leg that had been unlisted is
          listed again.
        - **filled** — the fill sweep usually books it first; this is the
          backstop for a fill its window missed, booked through ``_settle``
          like a found close.
        - **canceled / rejected** — not this service's cancel (that clears
          the id as it goes). Journaled ``leg_lost``, loud; the leg is
          re-rested at its standing price unless a close is in flight, or it
          was re-rested inside ``LEG_REREST_COOLDOWN_S`` and the broker has
          killed it again — then it stays off, ``stop_unprotected`` /
          ``target_unprotected`` say so, and the SPX-mark loop is the exit.
        - **absent** — kept, and after ``LEG_SETTLE_S`` journaled
          ``leg_unaccounted`` once; the card reads ``stop_state`` /
          ``target_state`` and says the listing does not show it. Not
          re-rested: a second stop beside one the listing merely lags is
          a short waiting for a print."""
        out: list[dict[str, Any]] = []
        now = self.clock()
        for pos in list(self._open.values()):
            for leg in ("stop", "target"):
                id_attr = self._LEG_ATTR[leg]
                order_id = getattr(pos, id_attr)
                if not order_id:
                    continue
                kind = self._LEG_KIND[leg]
                word = {"stop": "protective stop", "target": "take-profit"}[leg]
                unlisted_attr, unacc_attr = f"{leg}_unlisted_since", f"{leg}_unaccounted"
                order = broker_orders.get(order_id)
                if order is None:
                    since = getattr(pos, unlisted_attr)
                    if since is None:
                        setattr(pos, unlisted_attr, now)
                        continue
                    if getattr(pos, unacc_attr) or (now - since).total_seconds() < LEG_SETTLE_S:
                        continue
                    setattr(pos, unacc_attr, True)
                    self.journal.record(
                        "leg_unaccounted", kind=kind, symbol=pos.symbol, order_id=order_id,
                        intent_id=pos.intent_id, unlisted_since=since.isoformat(),
                        detail=f"the broker's listing has not reported the resting {word} "
                               f"{order_id} for {(now - since).total_seconds():.0f} s — the id is "
                               f"kept and the leg is not re-rested (a second {word} beside one "
                               f"the listing merely lags is a short); the card says so. "
                               f"If it is gone, UPDATE the {leg} to rest it again, or FLATTEN")
                    out.append({"symbol": pos.symbol, "leg": kind, "order_id": order_id,
                                "outcome": "unaccounted"})
                    continue
                if getattr(pos, unlisted_attr) is not None:
                    if getattr(pos, unacc_attr):
                        self.journal.record("leg_listed", kind=kind, symbol=pos.symbol,
                                            order_id=order_id, status=order.status.value,
                                            detail=f"the {word} is back in the broker's listing")
                    setattr(pos, unlisted_attr, None)
                    setattr(pos, unacc_attr, False)
                if order.is_working:
                    continue
                if order.is_filled:
                    setattr(pos, id_attr, None)
                    # the closed line's vocabulary: protective-stop / target
                    close_kind = "protective-stop" if leg == "stop" else "target"
                    out.append({"symbol": pos.symbol, "leg": kind, "order_id": order_id,
                                "outcome": "filled",
                                **self._settle(pos, order, reason=close_kind)})
                    break            # the position is closed or resized; its other leg went with it
                outcome = order.status.value.lower()
                setattr(pos, id_attr, None)
                in_flight = pos.exit_in_flight
                rerested_at = getattr(pos, f"{leg}_rerested_at")
                again = (rerested_at is not None
                         and (now - rerested_at).total_seconds() < LEG_REREST_COOLDOWN_S)
                self.journal.record(
                    "leg_lost", kind=kind, symbol=pos.symbol, order_id=order_id,
                    intent_id=pos.intent_id, outcome=outcome, broker_status=order.message,
                    detail=f"the broker reports the resting {word} {order_id} "
                           f"{order.status.value} and this service did not cancel it — "
                           f"cancelled by hand, expired, or rejected after acceptance; "
                           + ("a close is in flight, so it is not re-rested"
                              if in_flight else
                              f"it was re-rested {(now - rerested_at).total_seconds():.0f} s ago "
                              f"and killed again — not resting a third"
                              if again else "re-resting it at its standing price"))
                row = {"symbol": pos.symbol, "leg": kind, "order_id": order_id,
                       "outcome": outcome, "rerested": None}
                if in_flight:
                    out.append(row)
                    continue
                if again:
                    self.journal.record(
                        f"{leg}_unprotected", symbol=pos.symbol, intent_id=pos.intent_id,
                        qty=pos.qty, **{f"{leg}_price": getattr(pos, f"{leg}_price")},
                        detail=f"the re-rested {word} was {order.status.value} again within "
                               f"{LEG_REREST_COOLDOWN_S:.0f} s — left off; "
                               + ("the SPX-mark loop is the exit while the box is alive"
                                  if leg == "stop" else "the stop still stands"))
                    out.append(row)
                    continue
                setattr(pos, f"{leg}_rerested_at", now)
                if leg == "stop":
                    rested = self._rest_stop_at(pos, pos.stop_price, kind="re-rested")
                else:
                    rested = self._rest_target_at(pos, pos.target_price, kind="re-rested")
                row["rerested"] = getattr(pos, id_attr) if rested is not None else None
                out.append(row)
                if pos.symbol not in self._open:
                    break            # the re-rested leg filled as it landed
        return out

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

        shorts_now: dict[str, int] = {}
        foreign_now: dict[str, Position] = {}
        owned = self._owned_symbols()
        for symbol, held in broker_positions.items():
            if held.qty < 0:
                # A short is not this service's to manage — it only sells to
                # close — but it is the one state the bracket exists to
                # prevent, so it is never silent: journaled when it appears or
                # changes size, carried on /status as ``shorts`` (st-7ah8).
                shorts_now[symbol] = held.qty
                if self._shorts.get(symbol) != held.qty:
                    self.journal.record("short_held", symbol=symbol, qty=held.qty,
                                        detail="the account is short this contract; this "
                                               "service cannot buy to close — by hand")
                continue
            if held.qty == 0:
                continue
            pos = self._open.get(symbol)
            if pos is None:
                try:
                    right = parse_occ(symbol).right
                except ValueError:
                    continue       # not an option this service can reason about
                if symbol not in owned:
                    # Not this service's. Adoption exists for a position THIS
                    # service opened and lost track of — a journal gone, a
                    # send with no answer — and the journal says which those
                    # are. Steve trades spreads by hand in the same account;
                    # adopting a wing of one and then FLATTENing it left the
                    # short body naked (finding 30, st-isx3). Shown, not held.
                    foreign_now[symbol] = held
                    prior = self._foreign_positions.get(symbol)
                    if prior is None or prior.qty != held.qty:
                        self.journal.record("position_foreign", symbol=symbol, qty=held.qty,
                                            entry_price=held.avg_price,
                                            detail="held in the account, not opened by this "
                                                   "service — shown, never slotted, never "
                                                   "flattened")
                    continue
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
                self._cancel_bracket(pos)
                pos.qty = held.qty
                self._rest_bracket(pos)

        for symbol in list(self._shorts):
            if symbol not in shorts_now:
                self.journal.record("short_covered", symbol=symbol, qty=self._shorts[symbol])
        self._shorts = shorts_now
        self._foreign_positions = foreign_now

        for symbol, pos in list(self._open.items()):
            if symbol in broker_positions and broker_positions[symbol].qty > 0:
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
            # A leg still resting under a position that is gone would open a
            # short if it triggered. Pull both before dropping the record.
            self._cancel_bracket(pos)
            self._open.pop(symbol, None)
        return adopted, corrected, gone

    #: how many journal days back a symbol counts as this service's
    OWNED_LOOKBACK_DAYS = 7

    def _owned_symbols(self) -> set[str]:
        """Every contract this service has ever tried to open, over the last
        week of journals: sent (``sending``), acknowledged (``working``),
        filled, or adopted under the pre-2026-09-15 rule. Membership is what
        lets a position the broker reports be adopted; anything else the
        account holds is Steve's (st-isx3)."""
        owned: set[str] = set(self._open) | {w.symbol for w in self._working.values()}
        for day in self.journal.days()[-self.OWNED_LOOKBACK_DAYS:]:
            for e in self.journal.read(day):
                ev = e.get("event")
                if ev in ("sending", "working", "position_adopted") or \
                        (ev == "filled" and e.get("kind") == "entry"):
                    sym = str(e.get("symbol", ""))
                    if sym:
                        owned.add(sym)
        return owned

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
        if self._unconfirmed:
            # A send with no answer may be resting at the broker under an id
            # this service does not have. Until reconcile has swept the
            # listing for it, a second entry is a possible second order —
            # the same intent id most of all, which _replay cannot see
            # because no `placed` line was ever written (finding 25, st-xlz9).
            pending = ", ".join(sorted(self._unconfirmed))
            return Refusal("send_unconfirmed",
                           f"an earlier send has no answer from the broker ({pending}) — "
                           f"nothing else goes out until reconcile has accounted for it")
        quote = self._quote_view(intent.symbol)
        state = self.day_state()
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
            protective_stop_price(worst_fill, intent.delta, spx, intent.stop_spx)
        except ValueError as exc:
            return Refusal("protective_stop",
                           f"no resting stop can be derived for this entry: {exc}")
        # No daily loss ceiling, no headroom, no count of positions or losses
        # (Steve, 2026-09-24; see ``execd.bounds.Bounds``). [co-8mb1z]
        return None

    def _place_entry(self, intent: OrderIntent, *,
                     page_query: dict[str, str] | None = None) -> dict[str, Any]:
        if (refusal := self._entry_refusal(intent)) is not None:
            return self._refuse(intent, refusal, kind="place")

        try:
            prev = self.broker.preview(intent)
        except BrokerError as exc:
            self.journal.record("error", kind="preview", intent_id=intent.intent_id,
                                detail=str(exc))
            raise
        self._journal_preview(intent, prev)
        if not prev.accepted:
            return self._refuse(
                intent,
                Refusal("preview_cost", "the broker would not accept this order: "
                                        + "; ".join(prev.messages or ("no reason given",))),
                kind="place")
        if (r := check_preview_cost(intent, prev.total_usd, self.bounds)) is not None:
            return self._refuse(intent, r, kind="place")

        try:
            spx = self.spx_mark()
        except BrokerError as exc:
            return self._refuse(
                intent,
                Refusal("protective_stop",
                        f"no {self.config.index_symbol} mark at the send ({exc}) — "
                        "not sending"),
                kind="place")
        # The cut was checked against a mark read before the preview, a broker
        # round trip ago. Cycle 1 on 2026-09-14 was sent with the index already
        # through its cut — 7630.88 against a call stop at 7631.13 — and was
        # born past it; with the watcher live it would have been market-sold
        # on the first pass, bought at the ask and sold at the bid for nothing
        # (audit finding 32, st-xv5e). Last look at the cut, on the mark the
        # send is journaled with.
        if intent.stop_spx is not None and not stop_is_consistent(
                intent.occ.right, spx, intent.stop_spx):
            return self._refuse(
                intent,
                Refusal("protective_stop",
                        f"SPX moved through the cut while this entry was being priced — "
                        f"a {intent.occ.right_word} stop at {intent.stop_spx:g} is already "
                        f"triggered with SPX at {spx:g} — not sending"),
                kind="place")
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
        # The line BEFORE the send. A send that times out after the broker
        # took it used to leave no trace: no placed line, so a retry of the
        # same intent went out again, and reconcile — which only looks up ids
        # it already holds — never found the first (finding 25, st-xlz9).
        # Now the intent is unconfirmed until the broker's listing is swept.
        send = UnconfirmedSend(
            intent_id=intent.intent_id, symbol=intent.symbol, qty=intent.qty,
            limit=intent.limit, right=intent.occ.right, stop_spx=intent.stop_spx,
            delta=intent.delta, at=self.clock(),
            page_query=dict(page_query) if page_query else None)
        self.journal.record("sending", kind="entry", spx=spx, **send.to_dict())
        try:
            order = self.broker.place(intent)
        except BrokerError as exc:
            self._unconfirmed[intent.intent_id] = send
            self.journal.record("send_unknown", intent_id=intent.intent_id,
                                symbol=intent.symbol, detail=str(exc),
                                note="the broker may hold this order — no entry goes out "
                                     "until reconcile has swept the listing for it")
            raise
        self.journal.record("placed", intent_id=intent.intent_id, kind="entry",
                            spx=spx, order=order.to_dict())

        out: dict[str, Any] = {"refused": None, "order": order.to_dict(),
                               "preview": prev.to_dict(), "stop_order": None,
                               "target_order": None, "mode": self.config.mode}
        if order.status is OrderStatus.REJECTED:
            self.journal.record("rejected", intent_id=intent.intent_id,
                                order_id=order.order_id, detail=order.message)
            return out
        if not order.is_filled:
            # Acknowledged, not filled. Held, not forgotten: it takes a slot
            # until reconcile() learns what the broker did with it. (Not an
            # attempt — Steve, 2026-09-14: an attempt is a filled position.)
            work = WorkingEntry(
                order_id=order.order_id, symbol=intent.symbol,
                qty=order.qty, intent_id=intent.intent_id, right=intent.occ.right,
                limit=intent.limit, stop_spx=intent.stop_spx, delta=intent.delta,
                page_query=dict(page_query) if page_query else None,
            )
            self._working[work.order_id] = work
            self.journal.record("working", kind="entry", intent_id=intent.intent_id,
                                symbol=work.symbol, qty=work.qty,
                                order_id=work.order_id, status=order.status.value,
                                limit=work.limit, stop_spx=work.stop_spx,
                                delta=work.delta, spx=spx, page_query=work.page_query)
            out["working"] = work.to_dict()
            return out

        fill_px = order.fill_price if order.fill_price is not None else (intent.limit or 0.0)
        held = self._open.get(intent.symbol)
        if held is not None:
            # He already holds this contract: one position at the combined
            # size, one bracket resized to it (co-8mb1z).
            added = self._add_to_position(
                held, order.filled_qty, fill_px, intent_id=intent.intent_id,
                order_id=order.order_id, spx=spx, stop_spx=intent.stop_spx,
                delta=intent.delta, commission_usd=float(prev.commission_usd or 0.0))
            out["stop_order"] = added.get("stop_order")
            out["target_order"] = added.get("target_order")
            out["added_to"] = added.get("added_to")
            return out
        pos = OpenPosition(
            symbol=intent.symbol, qty=order.filled_qty, entry_price=fill_px,
            intent_id=intent.intent_id, right=intent.occ.right,
            stop_spx=intent.stop_spx, delta=intent.delta, entry_spx=spx,
            entry_order_id=order.order_id, opened_at=self.clock(),
            entry_commission_usd=float(prev.commission_usd or 0.0),
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
        out["target_order"] = self._place_take_profit(pos)
        return out

    def _add_to_position(self, pos: OpenPosition, qty: int, fill_px: float, *,
                         intent_id: str, order_id: str, spx: float | None,
                         stop_spx: float | None, delta: float | None,
                         commission_usd: float = 0.0,
                         found_by: str | None = None) -> dict[str, Any]:
        """A fill in a contract already held: one position at the combined
        size, one stop and one target resized to it. [co-8mb1z]

        Steve, 2026-09-24, on the one-position limit: "No idea where that
        'only one position' came from." Positions are tracked one per
        contract, so a second entry in the same contract is an add, not a
        second position — refusing it would be a new restriction, and
        tracking it separately would orphan the first bracket.

        The old legs come off first (a leg found already filled is booked
        against what was held, as every cancel does), the entry price
        becomes the size-weighted average, and the bracket goes back on for
        the whole size at the prices already standing — the stop and target
        he has, or moved to, are kept. A position with no standing price for
        a leg gets one derived the way a first fill does."""
        before_qty, before_px = pos.qty, pos.entry_price
        self._cancel_bracket(pos)
        if pos.qty <= 0:
            # A leg filled in the race and the old position is gone; this
            # fill is a fresh position of its own.
            self._open.pop(pos.symbol, None)
            fresh = OpenPosition(
                symbol=pos.symbol, qty=qty, entry_price=fill_px, intent_id=intent_id,
                right=pos.right, stop_spx=stop_spx, delta=delta, entry_spx=spx,
                entry_order_id=order_id, opened_at=self.clock(),
                entry_commission_usd=commission_usd)
            self._open[fresh.symbol] = fresh
            self.journal.record("filled", kind="entry", intent_id=intent_id,
                                symbol=fresh.symbol, qty=qty, price=fill_px,
                                cost_usd=round(fill_px * CONTRACT_MULTIPLIER * qty, 2),
                                spx=spx, stop_spx=stop_spx, delta=delta,
                                order_id=order_id, found_by=found_by)
            out: dict[str, Any] = {"added_to": None}
            out["stop_order"] = (self._place_protective_stop(fresh, spx)
                                 if spx is not None else None)
            out["target_order"] = self._place_take_profit(fresh)
            return out
        held = pos.qty
        pos.entry_price = round((pos.entry_price * held + fill_px * qty) / (held + qty), 4)
        pos.qty = held + qty
        pos.entry_commission_usd = round(pos.entry_commission_usd + commission_usd, 2)
        if pos.stop_spx is None:
            pos.stop_spx = stop_spx
        if pos.delta is None:
            pos.delta = delta
        self.journal.record("filled", kind="entry", intent_id=intent_id,
                            symbol=pos.symbol, qty=qty, price=fill_px,
                            cost_usd=round(fill_px * CONTRACT_MULTIPLIER * qty, 2),
                            spx=spx, stop_spx=stop_spx, delta=delta,
                            order_id=order_id, found_by=found_by, added_to=pos.intent_id)
        self.journal.record("position_added", symbol=pos.symbol, intent_id=pos.intent_id,
                            added_intent_id=intent_id, added_qty=qty, added_price=fill_px,
                            qty_before=before_qty, qty=pos.qty,
                            entry_price_before=before_px, entry_price=pos.entry_price)
        out = {"added_to": pos.intent_id, "stop_order": None, "target_order": None}
        if pos.exit_in_flight:
            self.journal.record("stop_unprotected", symbol=pos.symbol, intent_id=pos.intent_id,
                                qty=pos.qty, detail="added while a close is in flight — "
                                "the bracket goes back on when the close resolves")
            return out
        if pos.stop_price is not None:
            out["stop_order"] = self._rest_stop_at(pos, pos.stop_price, spx=spx, kind="added")
        elif spx is not None:
            out["stop_order"] = self._place_protective_stop(pos, spx)
        if pos.symbol in self._open:
            if pos.target_price is not None:
                out["target_order"] = self._rest_target_at(pos, pos.target_price, kind="added")
            else:
                out["target_order"] = self._place_take_profit(pos)
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

    def _place_take_profit(self, pos: OpenPosition) -> dict[str, Any] | None:
        """Rest the take-profit half of the bracket (st-fn5y). A warning on
        failure, not a fault: the stop is the protection, this is the exit
        Steve asked to have waiting. Runs after the stop so the ``risk`` basis
        has a stop price to multiply."""
        if pos.symbol not in self._open:
            return None        # the stop's placement closed it (a race) — nothing to target
        b = self.bounds
        try:
            price = take_profit_price(pos.entry_price, b.take_profit_multiple,
                                      b.take_profit_basis, stop_price=pos.stop_price)
        except ValueError as exc:
            self.journal.record("target_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, qty=pos.qty,
                                basis=b.take_profit_basis, multiple=b.take_profit_multiple,
                                detail=f"no take-profit can be derived: {exc}")
            return None
        return self._rest_target_at(pos, price, kind="entry")

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

        # A full-size exit and the resting bracket must not both be live at
        # the broker — same discipline as _market_close, same finding 3. A
        # partial exit leaves the bracket standing and _settle resizes it on
        # the fill; the window where a partial rests unfilled beside a
        # full-size bracket is a known residual, recorded on st-97z1.
        if pos is not None and intent.qty >= pos.qty:
            for leg, reason, word in (("stop", "resting-stop", "stop"),
                                      ("target", "target", "take-profit")):
                try:
                    _canceled, fill = self._pull_leg(pos, leg)
                except BrokerError:
                    # a BrokerError propagates: 502, nothing sent. If the stop
                    # had already come off, it goes back on first.
                    if leg == "target":
                        self._rest_stop_at(pos, pos.stop_price)
                    raise
                if fill is not None:
                    settled = self._settle(pos, fill, reason=reason)
                    return {"refused": None, "order": None, "closed": settled,
                            "note": f"the resting {word} had already filled — "
                                    f"the position was closed before this exit was sent"}

        order = self.broker.place(intent)
        self.journal.record("placed", intent_id=intent.intent_id, kind="exit",
                            order=order.to_dict())
        out = {"refused": None, "order": order.to_dict(), "closed": None}
        if pos is None:
            return out
        if order.status is OrderStatus.REJECTED:
            self._rest_bracket(pos)
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

        **The resting bracket comes off before the close goes on (finding 3,
        widened to both legs by st-fn5y).** The SPX loop and the resting stop
        are designed to fire at the same price, so a close sent while the stop
        still rests is asking for both to fill — a one-contract short on a
        long-premium-only account; the take-profit resting through a close is
        the same short from the other side. Cancelling first is safe in every
        branch: if a cancel reports that leg already FILLED, that leg won the
        race, the position is already closed at the broker, and no close is
        sent at all; if the broker cannot be reached, nothing is sent and what
        still rests is the protection working; if the close is afterwards
        rejected or cannot be sent, both legs are re-rested and the failure is
        loud. Every caller journals its intent to close before this runs
        (``exit_triggered``, the flatten request line, the place request
        line), so the cancels always have their why one line above.
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

        early = self._take_bracket_off(pos)
        if early is not None:
            return early

        try:
            order = self.broker.place(intent)
        except BrokerError as exc:
            self.journal.record("error", kind="close", symbol=pos.symbol,
                                reason=reason, detail=str(exc))
            self._rest_bracket(pos)   # the protection goes back on
            raise
        self.journal.record("placed", intent_id=intent.intent_id, kind="exit",
                            reason=reason, order=order.to_dict())
        if order.status is OrderStatus.REJECTED:
            self.journal.record("rejected", intent_id=intent.intent_id,
                                order_id=order.order_id, detail=order.message)
            self._rest_bracket(pos)
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
        """Book a close the broker reported as an order — a filled market
        close, or a leg found filled by a cancel. See ``_book_close``."""
        exit_px = order.fill_price if order.fill_price is not None else 0.0
        closed_qty = min(_filled_qty_of(order), pos.qty)
        return self._book_close(pos, order_id=order.order_id, exit_px=exit_px,
                                closed_qty=closed_qty, reason=reason, why=reason)

    def _book_close(self, pos: OpenPosition, *, order_id: str, exit_px: float,
                    closed_qty: int, reason: str, why: str) -> dict[str, Any]:
        """The one place a close is booked. Take the other leg(s) of the
        bracket off, then write the ``closed`` line, then resize or drop.

        The cancels go first because every moment the other leg rests past
        the fill is a moment it can fill too — a short on a long-premium-only
        account (st-fn5y). The journal loses nothing by waiting: a cancel that
        fails is caught and journaled, so the ``closed`` line is written
        either way. A cancel that finds the other leg already filled books
        that fill as well, capped at what was still held; anything past that
        is journaled as ``oversold``, loud, because it is a short this service
        cannot itself buy back.

        A **partial** fill is the case worth reading. The position shrinks but
        does not go away, so the resting legs — sized for the whole position —
        are now larger than what is held, and if either triggered it would
        sell contracts Steve does not own. So a partial exit cancels both and
        rests new ones at the same prices for what is left. The mock never
        fills partially unless asked; a real broker does."""
        self._booked_exits.add(order_id)
        stop_canceled, stop_fill = self._cancel_leg_quietly(pos, "stop")
        target_canceled, target_fill = self._cancel_leg_quietly(pos, "target")

        remaining = pos.qty - closed_qty
        pnl = self._pnl_usd(pos, exit_px, closed_qty)
        self.journal.record("closed", symbol=pos.symbol, qty=closed_qty,
                            remaining_qty=remaining, intent_id=pos.intent_id,
                            kind=reason, entry_price=pos.entry_price,
                            exit_price=exit_px, pnl_usd=pnl,
                            order_id=order_id, reason=why, **pos.water_dict())
        also_filled: list[dict[str, Any]] = []
        for other_reason, other in (("protective-stop", stop_fill), ("target", target_fill)):
            if other is None:
                continue
            remaining = self._book_found_fill(pos, other, other_reason, remaining=remaining)
            also_filled.append(other.to_dict())

        restopped = retargeted = None
        if remaining:
            pos.qty = remaining
            # A leg whose cancel is not confirmed is still resting at its old
            # size; re-resting beside it would be two legs for one position.
            if pos.stop_order_id is None:
                restopped = self._rest_stop_at(pos, pos.stop_price)
            if pos.target_order_id is None:
                retargeted = self._rest_target_at(pos, pos.target_price)
        else:
            self._release_loose_legs(pos)
            self._open.pop(pos.symbol, None)

        return {"symbol": pos.symbol, "qty": closed_qty, "remaining_qty": remaining,
                "entry_price": pos.entry_price, "exit_price": exit_px,
                "pnl_usd": pnl, "reason": reason, "order_id": order_id,
                "closed": remaining == 0,
                "stop_canceled": stop_canceled, "stop_replaced": restopped,
                "target_canceled": target_canceled, "target_replaced": retargeted,
                "also_filled": also_filled}

    def _book_found_fill(self, pos: OpenPosition, order: OrderResult, reason: str, *,
                         remaining: int | None = None) -> int:
        """A leg a cancel found already filled. Booked against what is still
        held, the way ``_pick_up_fills`` caps a fill at the position; the
        excess — both legs filled, a short — is ``oversold``. Returns what is
        still held afterwards."""
        held = pos.qty if remaining is None else remaining
        qty = min(_filled_qty_of(order), held)
        px = order.fill_price if order.fill_price is not None else 0.0
        if qty > 0:
            pnl = self._pnl_usd(pos, px, qty)
            self._booked_exits.add(order.order_id)
            self.journal.record("closed", symbol=pos.symbol, qty=qty,
                                remaining_qty=held - qty, intent_id=pos.intent_id,
                                kind=reason, entry_price=pos.entry_price,
                                exit_price=px, pnl_usd=pnl, order_id=order.order_id,
                                reason=reason, detail="found filled by the cancel")
        excess = _filled_qty_of(order) - qty
        if excess > 0:
            self.journal.record(
                "oversold", symbol=pos.symbol, intent_id=pos.intent_id,
                order_id=order.order_id, qty=excess, price=px, leg=reason,
                detail=f"both legs of the bracket filled — the account is short "
                       f"{excess} {pos.symbol.strip()}; this service only sells to "
                       f"close, so it must be bought back by hand")
        return held - qty

    # ── the bracket's legs ───────────────────────────────────────────────
    _LEG_KIND = {"stop": "protective-stop", "target": "take-profit"}
    _LEG_ATTR = {"stop": "stop_order_id", "target": "target_order_id"}

    def _pull_leg(self, pos: OpenPosition, leg: str) -> tuple[dict[str, Any] | None,
                                                            OrderResult | None]:
        """Cancel one resting leg. Returns ``(canceled, None)`` when it came
        off, ``(None, fill)`` when the cancel found it already filled — the
        race the exit path is built to survive — and ``(None, None)`` when
        nothing was resting. A ``BrokerError`` propagates with the order id
        still on the position, so the caller decides what "could not cancel"
        means where it stands."""
        attr = self._LEG_ATTR[leg]
        order_id = getattr(pos, attr)
        if not order_id:
            return None, None
        result = self.broker.cancel(order_id)
        if result.is_filled:
            setattr(pos, attr, None)
            return None, result
        if result.is_working:
            # The broker acknowledged the cancel and has not done it: the leg
            # is still at the exchange and can still fill. Booking it as off
            # here sent a market close out beside a live stop (finding 24 of
            # the 2026-09-15 audit, st-7ah8). The id stays on the position and
            # the caller decides — DEFER a close, or carry the leg as loose.
            self.journal.record("cancel_pending", kind=self._LEG_KIND[leg],
                                symbol=pos.symbol, order_id=order_id,
                                status=result.message or result.status.value)
            raise BrokerError(f"cancel of the {self._LEG_KIND[leg]} {order_id} is not "
                              f"confirmed — the broker says {result.message or 'WORKING'}")
        setattr(pos, attr, None)
        self.journal.record("canceled", kind=self._LEG_KIND[leg],
                            symbol=pos.symbol, order_id=order_id)
        return result.to_dict(), None

    def _cancel_leg_quietly(self, pos: OpenPosition, leg: str) -> tuple[dict[str, Any] | None,
                                                                      OrderResult | None]:
        """``_pull_leg`` for callers that are already past the point of
        refusing: a broker that cannot be reached, or a cancel it has not yet
        done, is journaled and the leg is **kept** — its id stays on the
        position so the next sweep can ask again. Until 2026-09-15 the id was
        cleared here, so a cancel that timed out but succeeded was forgotten
        and the next ``_rest_bracket`` rested a second stop beside the first
        (finding 39's mirror, st-7ah8). A position that is dropped with a leg
        still on it hands the leg to ``_loose_legs`` (see ``_book_close``)."""
        attr = self._LEG_ATTR[leg]
        order_id = getattr(pos, attr)
        try:
            return self._pull_leg(pos, leg)
        except BrokerError as exc:
            self.journal.record("error", kind=f"cancel-{leg}", symbol=pos.symbol,
                                order_id=order_id, detail=str(exc))
            return None, None

    def _release_loose_legs(self, pos: OpenPosition) -> None:
        """A position is being dropped with a leg still on it — a cancel the
        broker acknowledged and has not done, or one that errored. The leg is
        still at the exchange and, with the position gone, is a sell with
        nothing behind it: a short waiting for a print. It is carried in
        ``_loose_legs`` and in the journal until ``reconcile`` sees it
        terminal, and the page shows it until then (st-7ah8)."""
        for leg in ("stop", "target"):
            order_id = getattr(pos, self._LEG_ATTR[leg])
            if not order_id:
                continue
            self._loose_legs[order_id] = {"symbol": pos.symbol, "leg": self._LEG_KIND[leg],
                                          "qty": pos.qty, "intent_id": pos.intent_id}
            self.journal.record("leg_unconfirmed", kind=self._LEG_KIND[leg],
                                symbol=pos.symbol, order_id=order_id, qty=pos.qty,
                                intent_id=pos.intent_id,
                                detail="the position is closed but this leg's cancel was "
                                       "not confirmed — it may still be resting at the broker")

    def _reconcile_loose_legs(self, broker_orders: dict[str, OrderResult]) -> list[dict[str, Any]]:
        """Every loose leg against the broker's listing. Working → ask the
        broker to cancel it again; canceled/rejected/absent → resolved;
        filled → the account is **short**, journaled ``oversold`` and loud."""
        resolved: list[dict[str, Any]] = []
        for order_id, leg in list(self._loose_legs.items()):
            order = broker_orders.get(order_id)
            outcome: str
            if order is None:
                outcome = "gone"
            elif order.is_filled:
                outcome = "filled"
                self.journal.record(
                    "oversold", symbol=leg["symbol"], intent_id=leg["intent_id"],
                    order_id=order_id, qty=order.filled_qty or leg["qty"],
                    price=order.fill_price, leg=leg["leg"],
                    detail=f"a {leg['leg']} whose cancel was never confirmed filled after "
                           f"the position closed — the account is short "
                           f"{order.filled_qty or leg['qty']} {leg['symbol'].strip()}; this "
                           f"service only sells to close, so it must be bought back by hand")
            elif order.is_working:
                try:
                    again = self.broker.cancel(order_id)
                except BrokerError as exc:
                    self.journal.record("error", kind="cancel-loose", symbol=leg["symbol"],
                                        order_id=order_id, detail=str(exc))
                    continue
                if again.is_working:
                    continue           # still pending; ask again next sweep
                if again.is_filled:
                    self._loose_legs.pop(order_id, None)
                    self._reconcile_loose_legs({order_id: again})   # books the oversold
                    self._loose_legs.pop(order_id, None)
                    continue
                outcome = again.status.value.lower()
            else:
                outcome = order.status.value.lower()
            self._loose_legs.pop(order_id, None)
            self.journal.record("leg_resolved", kind=leg["leg"], symbol=leg["symbol"],
                                order_id=order_id, outcome=outcome, intent_id=leg["intent_id"])
            resolved.append({"symbol": leg["symbol"], "order_id": order_id,
                             "leg": leg["leg"], "outcome": outcome})
        return resolved

    def _cancel_protective_stop(self, pos: OpenPosition) -> dict[str, Any] | None:
        canceled, fill = self._cancel_leg_quietly(pos, "stop")
        if fill is not None:
            pos.qty = self._book_found_fill(pos, fill, "protective-stop")
        return canceled

    def _cancel_take_profit(self, pos: OpenPosition) -> dict[str, Any] | None:
        canceled, fill = self._cancel_leg_quietly(pos, "target")
        if fill is not None:
            pos.qty = self._book_found_fill(pos, fill, "target")
        return canceled

    def _cancel_bracket(self, pos: OpenPosition) -> None:
        """Both legs off, for a position whose size is about to change."""
        self._cancel_protective_stop(pos)
        self._cancel_take_profit(pos)

    def _take_bracket_off(self, pos: OpenPosition) -> dict[str, Any] | None:
        """Both legs off before a close goes on. ``None`` means clear to send.
        Anything else is the answer the caller returns instead of sending: a
        DEFERRED when a cancel could not reach the broker (nothing sent, and
        whatever still rests is the protection working — a stop that had
        already come off goes back on), or the settled close when a cancel
        found that leg already filled (the position is closed at the broker;
        selling it again would be the short)."""
        for leg, reason, word in (("stop", "resting-stop", "stop"),
                                  ("target", "target", "take-profit")):
            order_id = getattr(pos, self._LEG_ATTR[leg])
            try:
                _canceled, fill = self._pull_leg(pos, leg)
            except BrokerError as exc:
                self.journal.record("error", kind=f"cancel-{leg}", symbol=pos.symbol,
                                    order_id=order_id, detail=str(exc))
                if leg == "target":
                    self._rest_stop_at(pos, pos.stop_price)
                return {"symbol": pos.symbol, "order_id": None, "status": "DEFERRED",
                        "closed": False,
                        "detail": f"the resting {word} could not be cancelled — "
                                  f"nothing sent, the bracket is still the protection"}
            if fill is not None:
                return self._settle(pos, fill, reason=reason)
        return None

    def _rest_bracket(self, pos: OpenPosition) -> None:
        """Both legs back on at their standing prices, for what is held now.
        The stop first: it is the protection. The target only if the stop's
        placement did not itself close the position."""
        self._rest_stop_at(pos, pos.stop_price)
        if pos.symbol in self._open:
            self._rest_target_at(pos, pos.target_price)

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
        if result.status is OrderStatus.REJECTED:
            self.journal.record("stop_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, qty=pos.qty, stop_price=price,
                                order_id=result.order_id,
                                detail=f"broker rejected the {kind} stop: "
                                       f"{result.message or 'no reason given'}")
            return None
        pos.stop_order_id = result.order_id
        pos.stop_price = price
        self.journal.record("stop_placed", symbol=pos.symbol, intent_id=pos.intent_id,
                            stop_price=price, stop_spx=pos.stop_spx, spx=spx,
                            delta=pos.delta, qty=pos.qty, order_id=result.order_id,
                            kind=kind, risk_usd=risk_usd(pos.entry_price, price, pos.qty),
                            order=result.to_dict())
        return result.to_dict()

    def _rest_target_at(self, pos: OpenPosition, price: float | None, *,
                        kind: str = "resized") -> dict[str, Any] | None:
        """Rest the SELL LIMIT that takes the profit, for what is held now.

        The one place a resting target is created, the mirror of
        ``_rest_stop_at``. Failure is ``target_unprotected`` — a warning: the
        stop still stands. A target the book is already through when it
        lands fills at once, and that fill *is* the exit, booked here."""
        if price is None:
            self.journal.record("target_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, qty=pos.qty,
                                detail=f"no target price to rest ({kind})")
            return None
        target_intent = OrderIntent(
            intent_id=f"{pos.intent_id}:target:{pos.qty}", symbol=pos.symbol,
            side=Side.SELL_TO_CLOSE, qty=pos.qty, order_type=OrderType.LIMIT,
            limit=price, source="take-profit", engine_sha=self.config.sha,
        )
        try:
            result = self.broker.place(target_intent)
        except BrokerError as exc:
            self.journal.record("target_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, qty=pos.qty, target_price=price,
                                detail=f"broker refused the {kind} take-profit: {exc}")
            return None
        if result.status is OrderStatus.REJECTED:
            self.journal.record("target_unprotected", symbol=pos.symbol,
                                intent_id=pos.intent_id, qty=pos.qty, target_price=price,
                                order_id=result.order_id,
                                detail=f"broker rejected the {kind} take-profit: "
                                       f"{result.message or 'no reason given'}")
            return None
        b = self.bounds
        line = dict(symbol=pos.symbol, intent_id=pos.intent_id, target_price=price,
                    target_spx=pos.target_spx,
                    basis=b.take_profit_basis, multiple=b.take_profit_multiple,
                    qty=pos.qty, order_id=result.order_id, kind=kind,
                    reward_usd=round((price - pos.entry_price) * CONTRACT_MULTIPLIER * pos.qty, 2),
                    order=result.to_dict())
        if result.is_filled:
            # The bid was already at or through the target when it landed.
            # That is the exit, taken at once; recovery must not rebuild a
            # resting order from this line, hence the flag.
            pos.target_price = price
            self.journal.record("target_placed", filled_at_once=True, **line)
            settled = self._settle(pos, result, reason="target")
            return {**result.to_dict(), "closed": settled}
        pos.target_order_id = result.order_id
        pos.target_price = price
        self.journal.record("target_placed", **line)
        return result.to_dict()

    # ── the live editor: both trigger conditions ─────────────────────────
    def adjust(self, symbol: str, *, stop_price: float | None = None,
               target_price: float | None = None, stop_spx: float | None = None,
               target_spx: float | None = None) -> dict[str, Any]:
        """Move the resting stop, the resting target, or both. [st-fn5y]

        Steve, 2026-09-14: *"The screen should be a live editor allowing an
        update to both trigger conditions."* There is no replace-order in
        the transport (no PUT, by design), so a move is the same motion every
        other path uses: cancel the leg, rest a new one. Exit-class — legal
        while STOPped or stood down, needs a credential — with these
        refusals, each named: no such position; a close already in flight
        (the bracket is off while it works); a price off the tick grid; a
        stop not below the live bid or a target not above it (either would
        fill at once — a sale, not a trigger); and a stop at or above the
        target. How wide he moves his stop is his (no daily ceiling since
        2026-09-24, co-8mb1z). A cancel that finds the leg already filled books
        that fill and refuses the adjust with what happened.

        Moving the stop price also moves the SPX-mark trigger the loop
        watches, by the same delta walk in reverse from the level the entry
        filled at, so the two stops stay one stop. Journaled as
        ``stop_adjusted`` / ``target_adjusted`` with old and new.

        **Either leg may be given as an SPX level instead** (st-2j3m; Steve,
        2026-09-16: "a path to define a SPX target strike for both stop loss
        and take profit"): ``stop_spx`` / ``target_spx``, one form per leg,
        never both. A level is walked into the option price through the
        entry's delta from the level the entry filled at
        (``stops.premium_at_level``), and that price is what rests at the
        broker; the level itself is what the SPX loop watches — the stop's
        trigger, or a ``target_spx`` the loop fires a market close on when
        the mark reaches it, the resting limit staying the floor under it.
        A level is refused, bound ``level``, when the position has no delta
        or entry mark to walk from, when it is on the wrong side of the mark
        for the right (it would fire at once), when it sits inside the noise
        floor (the spread walked through delta — the market fidgets that far
        on nothing), or when it walks to a price nothing can rest at; the
        price it walks to then meets the same refusals a price given in
        dollars does, worded with the level. A level whose price is the one
        already resting moves the level alone, without a broker round trip."""
        with self._lock:
            if stop_price is None and target_price is None and \
                    stop_spx is None and target_spx is None:
                raise ValueError("adjust needs a stop_price, a target_price, or both")
            for leg, price, level in (("stop", stop_price, stop_spx),
                                      ("target", target_price, target_spx)):
                if price is not None and level is not None:
                    raise ValueError(f"the {leg} is a price or an SPX level, not both")
            # A replay — the same request arriving within seconds of the last
            # one's answer — is answered from that answer and touches nothing.
            # 2026-09-15 14:07:05 CT: the browser (or the tailnet proxy) re-sent
            # an UPDATE the instant the first one's 303 went out, and the
            # service ran it again (st-ff5j, st-gw5m).
            key = (symbol, stop_price, target_price, stop_spx, target_spx)
            last = self._last_adjust
            if last is not None and last[0] == key and \
                    (self.clock() - last[1]).total_seconds() <= ADJUST_REPLAY_S:
                self.journal.record("adjust_replayed", symbol=symbol, stop_price=stop_price,
                                    target_price=target_price, stop_spx=stop_spx,
                                    target_spx=target_spx,
                                    first_at=last[1].isoformat())
                return {**last[2], "replayed": True}
            self.journal.record("request", kind="adjust", symbol=symbol,
                                stop_price=stop_price, target_price=target_price,
                                stop_spx=stop_spx, target_spx=target_spx)
            out = self._adjust(symbol, stop_price=stop_price, target_price=target_price,
                               stop_spx=stop_spx, target_spx=target_spx)
            if out.get("refused") is None:
                self._last_adjust = (key, self.clock(), out)
            return out

    def _adjust(self, symbol: str, *, stop_price: float | None,
                target_price: float | None, stop_spx: float | None = None,
                target_spx: float | None = None) -> dict[str, Any]:
        with self._lock:
            if (r := self.arming.permits_exit()) is not None:
                return self._refuse_adjust(symbol, r)
            pos = self._open.get(symbol)
            if pos is None:
                return self._refuse_adjust(symbol, Refusal(
                    "position", f"no open position in {symbol.strip()} to adjust"))
            if pos.exit_in_flight:
                return self._refuse_adjust(symbol, Refusal(
                    "exit_in_flight",
                    f"a close for {symbol.strip()} is working at the broker (order "
                    f"{pos.exit_order_id}) and the bracket is off while it does — "
                    f"cancel that close first, or let it fill"))
            q = self.broker.quote(symbol)          # a BrokerError propagates: 502
            bid = float(q.bid)
            # A leg given as an SPX level is walked into its price first; the
            # price then meets every refusal a dollar price does (st-2j3m).
            if stop_spx is not None or target_spx is not None:
                try:
                    mark = self.spx_mark()
                except BrokerError as exc:
                    return self._refuse_adjust(symbol, Refusal(
                        "level", f"no {self.config.index_symbol} mark to place an SPX "
                                 f"level against ({exc}) — give the leg in dollars"))
                spread = max(float(q.ask) - bid, 0.0)
                if stop_spx is not None:
                    stop_price, r = self._price_at_level(pos, "stop", float(stop_spx),
                                                         mark, spread)
                    if r is not None:
                        return self._refuse_adjust(symbol, r)
                if target_spx is not None:
                    target_price, r = self._price_at_level(pos, "target", float(target_spx),
                                                           mark, spread)
                    if r is not None:
                        return self._refuse_adjust(symbol, r)
            new_stop = pos.stop_price if stop_price is None else float(stop_price)
            new_target = pos.target_price if target_price is None else float(target_price)
            if (r := self._adjust_refusal(pos, bid, new_stop, new_target,
                                          stop_given=stop_price is not None,
                                          target_given=target_price is not None,
                                          stop_level=stop_spx,
                                          target_level=target_spx)) is not None:
                return self._refuse_adjust(symbol, r)

            out: dict[str, Any] = {"refused": None, "symbol": symbol, "bid": bid,
                                   "stop": None, "target": None, "closed": None,
                                   "mode": self.config.mode}
            # A leg already resting at the price asked for is left alone: a
            # cancel-and-re-rest of an unchanged stop is a moment with no stop
            # resting and two broker round trips for nothing. 2026-09-15
            # 14:07 CT the page's UPDATE sent both boxes, the stop unchanged,
            # and the stop was pulled and re-rested twice at 10.30 (st-ff5j).
            # A level already set is unchanged the same way; a new level whose
            # price is the resting one moves the level alone (st-2j3m).
            if stop_price is not None:
                if pos.stop_order_id and (
                        self._same_price(pos.stop_spx, stop_spx) if stop_spx is not None
                        else self._same_price(pos.stop_price, stop_price)):
                    out["stop"] = self._unchanged_leg(
                        pos, "stop", given="spx" if stop_spx is not None else "price")
                elif stop_spx is not None and pos.stop_order_id and \
                        self._same_price(pos.stop_price, stop_price):
                    out["stop"] = self._move_level_only(pos, "stop", float(stop_spx), bid)
                else:
                    moved = self._move_leg(pos, "stop", float(stop_price), bid,
                                           level=stop_spx)
                    if moved.get("closed") is not None:
                        return self._adjust_closed(symbol, out, "stop", moved)
                    out["stop"] = moved
            if target_price is not None and pos.symbol in self._open:
                if pos.target_order_id and (
                        self._same_price(pos.target_spx, target_spx) if target_spx is not None
                        else self._same_price(pos.target_price, target_price)
                        and pos.target_spx is None):
                    out["target"] = self._unchanged_leg(
                        pos, "target", given="spx" if target_spx is not None else "price")
                elif pos.target_order_id and self._same_price(pos.target_price, target_price):
                    # the price already rests; only the level changes (a new
                    # one, or none — a dollar target has no level to fire on)
                    out["target"] = self._move_level_only(
                        pos, "target", None if target_spx is None else float(target_spx), bid)
                else:
                    moved = self._move_leg(pos, "target", float(target_price), bid,
                                           level=target_spx)
                    if moved.get("closed") is not None:
                        return self._adjust_closed(symbol, out, "target", moved)
                    out["target"] = moved
            return out

    @staticmethod
    def _same_price(resting: float | None, asked: float | None) -> bool:
        return resting is not None and asked is not None and \
            abs(float(asked) - float(resting)) < 1e-6

    @staticmethod
    def _right_word(right: str) -> str:
        return "call" if (right or "").upper() in ("C", "CALL") else "put"

    def _price_at_level(self, pos: OpenPosition, leg: str, level: float, mark: float,
                        spread: float) -> tuple[float | None, Refusal | None]:
        """Walk an SPX level into the option price that leg rests at, or say
        in words why it cannot be. [st-2j3m]

        Four refusals, all bound ``level``: the position carries no delta or
        entry mark to walk from (adopted, or recovered without one); the
        level is on the wrong side of the mark for the right — a call's stop
        sits below the market and its target above, a put's the mirror — so
        it would fire the moment the loop saw it; the level is inside the
        noise floor, the spread walked through delta, which is how far the
        index moves on nothing (``compose.noise_floor_spx``'s spread term —
        the service holds no minute bars, so the tape's own fidget is not in
        it here); or the walk lands at a price nothing can rest at."""
        word = self._right_word(pos.right)
        if pos.delta is None or pos.entry_spx is None or pos.entry_price <= 0:
            return None, Refusal(
                "level", f"this position carries no delta or entry mark to walk an SPX "
                         f"level into a price — give the {leg} in dollars")
        delta = abs(float(pos.delta))
        if leg == "stop":
            if not stop_is_consistent(pos.right, mark, level):
                side = "below" if word == "call" else "above"
                return None, Refusal(
                    "level", f"a {word}'s stop sits {side} the market, and SPX {level:g} is "
                             f"not {side} the {mark:.2f} mark — it would fire at once")
        elif target_reached(pos.right, mark, level):
            side = "above" if word == "call" else "below"
            return None, Refusal(
                "level", f"a {word}'s target sits {side} the market, and SPX {level:g} is "
                         f"not {side} the {mark:.2f} mark — it would fire at once")
        floor = spread / delta if delta > 0 else 0.0
        distance = abs(mark - level)
        if floor > 0 and distance < floor:
            return None, Refusal(
                "level", f"SPX {level:g} is {distance:.2f} points from the {mark:.2f} mark, "
                         f"inside the {floor:.2f}-point noise floor (the {spread:.2f} spread "
                         f"walked through the {delta:.2f} delta) — the market moves that far "
                         f"on nothing")
        try:
            price = premium_at_level(pos.entry_price, delta, pos.entry_spx, level, pos.right)
        except ValueError as exc:
            return None, Refusal(
                "level", f"SPX {level:g} walks to no price this {leg} can rest at: {exc}")
        return price, None

    def _unchanged_leg(self, pos: OpenPosition, leg: str, *,
                       given: str = "price") -> dict[str, Any]:
        price = pos.stop_price if leg == "stop" else pos.target_price
        order_id = pos.stop_order_id if leg == "stop" else pos.target_order_id
        level = pos.stop_spx if leg == "stop" else pos.target_spx
        self.journal.record("adjust_unchanged", symbol=pos.symbol, intent_id=pos.intent_id,
                            leg=leg, price=price, order_id=order_id, level=level, given=given)
        out = {"moved": False, "unchanged": True, "old_price": price, "new_price": price,
               "order_id": order_id, "given": given}
        if leg == "stop":
            out["stop_spx"] = pos.stop_spx
        else:
            out["target_spx"] = pos.target_spx
        return out

    def _move_level_only(self, pos: OpenPosition, leg: str, level: float | None,
                         bid: float) -> dict[str, Any]:
        """A new SPX level that walks to the price already resting: the loop's
        trigger moves, the broker is not touched. A target's level is cleared
        the same way (``None``) when the target is given again in dollars at
        the price already resting — the resting limit stands alone. [st-2j3m]"""
        if leg == "stop":
            old_level, pos.stop_spx = pos.stop_spx, level
            price, order_id = pos.stop_price, pos.stop_order_id
            self.journal.record("stop_adjusted", symbol=pos.symbol, intent_id=pos.intent_id,
                                old_price=price, new_price=price, old_order_id=order_id,
                                new_order_id=order_id, old_stop_spx=old_level,
                                new_stop_spx=level, given="spx", level_only=True,
                                bid=bid, qty=pos.qty)
            return {"moved": True, "level_only": True, "old_price": price, "new_price": price,
                    "order_id": order_id, "stop_spx": level, "old_stop_spx": old_level,
                    "given": "spx"}
        old_level, pos.target_spx = pos.target_spx, level
        price, order_id = pos.target_price, pos.target_order_id
        given = "spx" if level is not None else "price"
        self.journal.record("target_adjusted", symbol=pos.symbol, intent_id=pos.intent_id,
                            old_price=price, new_price=price, old_order_id=order_id,
                            new_order_id=order_id, old_target_spx=old_level,
                            new_target_spx=level, given=given, level_only=True,
                            bid=bid, qty=pos.qty)
        return {"moved": True, "level_only": True, "old_price": price, "new_price": price,
                "order_id": order_id, "target_spx": level, "old_target_spx": old_level,
                "given": given}

    def _adjust_refusal(self, pos: OpenPosition, bid: float, new_stop: float | None,
                        new_target: float | None, *, stop_given: bool,
                        target_given: bool, stop_level: float | None = None,
                        target_level: float | None = None) -> Refusal | None:
        # a leg given as an SPX level is named by both forms in the refusal,
        # so "a stop at 2.05" never puzzles someone who typed 6378 (st-2j3m)
        def name(label: str, price: float) -> str:
            level = stop_level if label == "stop" else target_level
            if level is not None:
                return f"a {label} at SPX {level:g} (which walks to {price:.2f})"
            return f"a {label} at {price:.2f}"

        for label, price, given in (("stop", new_stop, stop_given),
                                    ("target", new_target, target_given)):
            if not given or price is None:
                continue
            if price <= 0:
                return Refusal("bracket", f"a {label} price must be positive, not {price:g}")
            if not on_tick(price):
                from .stops import tick_for
                tick = tick_for(price)
                return Refusal(
                    "tick",
                    f"{label} {price:.2f} is not on the {tick:.2f} grid SPX options "
                    f"quote in {'at and above' if tick > 0.05 else 'below'} $3.00")
        if stop_given and new_stop is not None and new_stop >= bid:
            return Refusal("bracket", f"{name('stop', new_stop)} is not below the "
                                      f"{bid:.2f} bid — it would fill at once")
        if target_given and new_target is not None and new_target <= bid:
            return Refusal("bracket", f"{name('target', new_target)} is not above the "
                                      f"{bid:.2f} bid — it would fill at once")
        if new_stop is not None and new_target is not None and new_stop >= new_target:
            stop_word = f"SPX {stop_level:g} → {new_stop:.2f}" if stop_level is not None else f"{new_stop:.2f}"
            target_word = f"SPX {target_level:g} → {new_target:.2f}" if target_level is not None else f"{new_target:.2f}"
            return Refusal("bracket", f"the stop ({stop_word}) must sit below the "
                                      f"target ({target_word})")
        return None

    def _refuse_adjust(self, symbol: str, refusal: Refusal) -> dict[str, Any]:
        self.journal.record("refused", kind="adjust", symbol=symbol,
                            refused=refusal.to_dict())
        return {"refused": refusal.to_dict(), "symbol": symbol, "stop": None,
                "target": None, "closed": None, "mode": self.config.mode}

    def _adjust_closed(self, symbol: str, out: dict[str, Any], leg: str,
                       moved: dict[str, Any]) -> dict[str, Any]:
        """The cancel found the leg already filled: the position is closed
        (booked), and the adjust is refused with what happened."""
        settled = moved["closed"]
        word = "stop" if leg == "stop" else "take-profit"
        refusal = Refusal(
            "filled",
            f"the resting {word} filled at {settled['exit_price']:.2f} before it "
            f"could be moved — the position is closed ({self._money(settled['pnl_usd'])}); "
            f"nothing adjusted")
        self.journal.record("refused", kind="adjust", symbol=symbol,
                            refused=refusal.to_dict())
        return {**out, "refused": refusal.to_dict(), "closed": settled}

    @staticmethod
    def _money(v: float) -> str:
        sign = "+" if v > 0 else ("-" if v < 0 else "")
        return f"{sign}${abs(v):,.2f}"

    def _move_leg(self, pos: OpenPosition, leg: str, new_price: float,
                  bid: float, *, level: float | None = None) -> dict[str, Any]:
        """Cancel one leg and rest it at the new price. Returns what happened;
        ``closed`` is set when the cancel found the leg filled. ``level`` is
        the SPX level the price was walked from when the leg was given as
        one (st-2j3m): the stop's trigger becomes exactly that level rather
        than the price walked back; the target's level is set (or, for a
        target given in dollars, cleared) beside the resting limit."""
        old_price = pos.stop_price if leg == "stop" else pos.target_price
        old_id = getattr(pos, self._LEG_ATTR[leg])
        given = "spx" if level is not None else "price"
        try:
            _canceled, fill = self._pull_leg(pos, leg)
        except BrokerError as exc:
            self.journal.record("error", kind=f"adjust-{leg}", symbol=pos.symbol,
                                order_id=old_id, detail=str(exc))
            raise
        if fill is not None:
            reason = "resting-stop" if leg == "stop" else "target"
            return {"moved": False, "closed": self._settle(pos, fill, reason=reason)}

        if leg == "stop":
            old_spx = pos.stop_spx
            new_spx = level if level is not None else self._stop_spx_for(pos, new_price)
            if new_spx is not None:
                pos.stop_spx = new_spx
            placed = self._rest_stop_at(pos, new_price, kind="adjusted")
            if placed is None:
                # The new stop would not rest. The old one goes back — and the
                # SPX trigger with it — so the position is not left naked by an
                # edit. If that fails too, stop_unprotected is already written.
                pos.stop_spx = old_spx
                self._rest_stop_at(pos, old_price, kind="restored")
                return {"moved": False, "old_price": old_price, "new_price": new_price,
                        "order_id": pos.stop_order_id, "given": given,
                        "error": "the broker would not rest the stop at the new price; "
                                 "the old stop is back"}
            self.journal.record("stop_adjusted", symbol=pos.symbol, intent_id=pos.intent_id,
                                old_price=old_price, new_price=new_price,
                                old_order_id=old_id, new_order_id=pos.stop_order_id,
                                old_stop_spx=old_spx, new_stop_spx=pos.stop_spx,
                                given=given, bid=bid, qty=pos.qty)
            return {"moved": True, "old_price": old_price, "new_price": new_price,
                    "order_id": pos.stop_order_id, "stop_spx": pos.stop_spx,
                    "old_stop_spx": old_spx, "given": given}

        old_spx = pos.target_spx
        pos.target_spx = level           # None for a dollar target: nothing fires on the mark
        placed = self._rest_target_at(pos, new_price, kind="adjusted")
        if placed is None:
            pos.target_spx = old_spx
            self._rest_target_at(pos, old_price, kind="restored")
            return {"moved": False, "old_price": old_price, "new_price": new_price,
                    "order_id": pos.target_order_id, "given": given,
                    "error": "the broker would not rest the take-profit at the new "
                             "price; the old one is back"}
        if placed.get("closed") is not None:
            # the bid ran through the new target as it landed: that is the exit
            return {"moved": True, "old_price": old_price, "new_price": new_price,
                    "given": given, "closed": placed["closed"]}
        self.journal.record("target_adjusted", symbol=pos.symbol, intent_id=pos.intent_id,
                            old_price=old_price, new_price=new_price,
                            old_order_id=old_id, new_order_id=pos.target_order_id,
                            old_target_spx=old_spx, new_target_spx=pos.target_spx,
                            given=given, bid=bid, qty=pos.qty)
        return {"moved": True, "old_price": old_price, "new_price": new_price,
                "order_id": pos.target_order_id, "target_spx": pos.target_spx,
                "old_target_spx": old_spx, "given": given}

    def _stop_spx_for(self, pos: OpenPosition, stop_price: float) -> float | None:
        """The SPX level that corresponds to an option-price stop, by the
        entry's delta walked backwards from the level the entry filled at:
        the inverse of ``stops.premium_at_level``. Signed since st-2j3m — a
        stop raised above the fill (a call's, after the market has moved up)
        walks to a level on the winning side of the entry mark, and the loop
        must watch that level, not the one the wider stop had. ``None`` when
        the position has no delta or no entry mark (adopted, or recovered
        without one), in which case the SPX loop keeps whatever level it had."""
        if pos.delta is None or pos.entry_spx is None or pos.entry_price <= 0:
            return None
        delta = abs(float(pos.delta))
        if delta <= 0:
            return None
        distance = (pos.entry_price - float(stop_price)) / delta
        r = (pos.right or "").upper()
        if r in ("C", "CALL"):
            return round(float(pos.entry_spx) - distance, 2)
        return round(float(pos.entry_spx) + distance, 2)

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
        return {"refused": refusal.to_dict(), "order": None, "mode": self.config.mode}

    def _replay(self, intent_id: str) -> dict[str, Any] | None:
        """An intent id the journal has already sent is answered, never re-sent.

        ``placed`` is the ordinary answer. A send whose answer was lost and
        which the orphan sweep later found at the broker (``send_resolved``
        found) has no ``placed`` line, so it is answered from that line; until
        2026-09-24 the one-open-position limit was what refused a repeat of it,
        and that limit is gone (co-8mb1z)."""
        for entry in self.journal.find(intent_id):
            if entry.get("event") == "placed":
                return {"refused": None, "order": entry.get("order"),
                        "replayed_from": entry.get("ts")}
        for entry in self.journal.find(intent_id):
            if entry.get("event") == "send_resolved" and entry.get("outcome") == "found":
                return {"refused": None,
                        "order": {"order_id": entry.get("order_id"),
                                  "status": entry.get("status")},
                        "replayed_from": entry.get("ts")}
        return None

    def _recover(self) -> None:
        """Rebuild open positions from the journal after a restart.

        The service comes back LOCKED, so it cannot open anything; what it must
        not do is come back not knowing a position is live, because then the
        SPX-mark loop stops watching it and flatten misses it.

        The position-carrying events of the last ``RECOVER_LOOKBACK_DAYS`` are
        replayed before today's file, so a position opened on a prior day and
        never closed comes back with its stop_spx, delta and leg ids (which
        the reconcile at the unlock then checks against the listing, st-vqmr)
        instead of being adopted from the broker with no exit at all
        (finding 38, st-btob). A position closed on a prior day is dropped by
        its ``closed`` line as it is replayed."""
        today = self.journal.today()
        entries: list[dict[str, Any]] = []
        for day in self.journal.days()[-RECOVER_LOOKBACK_DAYS:]:
            if day >= today:
                continue
            entries.extend(e for e in self.journal.read(day)
                           if e.get("event") in _CARRIED_EVENTS)
        entries.extend(self.journal.read())
        for e in entries:
            if e.get("event") == "filled" and e.get("kind") == "entry":
                symbol = str(e.get("symbol", ""))
                if not symbol:
                    continue
                try:
                    right = parse_occ(symbol).right
                except ValueError:
                    continue
                held = self._open.get(symbol)
                if held is not None:
                    # an add to a contract already held (co-8mb1z)
                    q = int(e.get("qty", 0) or 0)
                    px = float(e.get("price", 0.0) or 0.0)
                    if q > 0:
                        held.entry_price = round((held.entry_price * held.qty + px * q)
                                                 / (held.qty + q), 4)
                        held.qty += q
                    continue
                self._open[symbol] = OpenPosition(
                    symbol=symbol, qty=int(e.get("qty", 0) or 0),
                    entry_price=float(e.get("price", 0.0) or 0.0),
                    intent_id=str(e.get("intent_id", "")), right=right,
                    stop_spx=e.get("stop_spx"), delta=e.get("delta"),
                    entry_spx=e.get("spx"),
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
            elif e.get("event") == "target_placed":
                pos = self._open.get(str(e.get("symbol", "")))
                if pos is not None:
                    pos.target_price = e.get("target_price")
                    pos.target_spx = e.get("target_spx")
                    # a target that filled the moment it landed never rested;
                    # the closed line that follows drops the position anyway
                    pos.target_order_id = None if e.get("filled_at_once") else e.get("order_id")
            elif e.get("event") in ("stop_adjusted", "target_adjusted") and e.get("level_only"):
                # a level moved without the leg being re-rested (st-2j3m):
                # no *_placed line follows, so the level is read from here
                pos = self._open.get(str(e.get("symbol", "")))
                if pos is not None:
                    if e.get("event") == "stop_adjusted":
                        pos.stop_spx = e.get("new_stop_spx")
                    else:
                        pos.target_spx = e.get("new_target_spx")
            elif e.get("event") == "canceled" and e.get("kind") in ("protective-stop", "take-profit"):
                # A leg that came off and was not put back (a close in flight
                # when the service died) must not come back as a resting id.
                pos = self._open.get(str(e.get("symbol", "")))
                if pos is not None:
                    attr = "stop_order_id" if e.get("kind") == "protective-stop" else "target_order_id"
                    if getattr(pos, attr) == e.get("order_id"):
                        setattr(pos, attr, None)
            elif e.get("event") == "working" and e.get("kind") == "entry":
                symbol = str(e.get("symbol", ""))
                order_id = str(e.get("order_id", ""))
                if not symbol or not order_id:
                    continue
                try:
                    right = parse_occ(symbol).right
                except ValueError:
                    continue
                query = e.get("page_query")
                self._working[order_id] = WorkingEntry(
                    order_id=order_id, symbol=symbol,
                    qty=int(e.get("qty", 0) or 0),
                    intent_id=str(e.get("intent_id", "")), right=right,
                    limit=e.get("limit"), stop_spx=e.get("stop_spx"),
                    delta=e.get("delta"),
                    page_query={str(k): str(v) for k, v in query.items()}
                    if isinstance(query, dict) else None,
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
            elif e.get("event") == "leg_unconfirmed":
                # A leg left at the broker when its position closed. It comes
                # back as loose so reconcile keeps asking after it (st-7ah8).
                oid = str(e.get("order_id", ""))
                if oid:
                    self._loose_legs[oid] = {"symbol": str(e.get("symbol", "")),
                                             "leg": str(e.get("kind", "")),
                                             "qty": int(e.get("qty", 0) or 0),
                                             "intent_id": str(e.get("intent_id", ""))}
            elif e.get("event") == "leg_resolved":
                self._loose_legs.pop(str(e.get("order_id", "")), None)
            elif e.get("event") == "send_unknown":
                # The send whose answer never came back. Its shape is on the
                # `sending` line just before it; hold it until reconcile has
                # swept the broker's listing (st-xlz9).
                iid = str(e.get("intent_id", ""))
                sending = next((s for s in reversed(entries[:entries.index(e)])
                                if s.get("event") == "sending" and s.get("intent_id") == iid), None)
                if sending is not None and iid:
                    query = sending.get("page_query")
                    self._unconfirmed[iid] = UnconfirmedSend(
                        intent_id=iid, symbol=str(sending.get("symbol", "")),
                        qty=int(sending.get("qty", 0) or 0), limit=sending.get("limit"),
                        right=str(sending.get("right", "")), stop_spx=sending.get("stop_spx"),
                        delta=sending.get("delta"),
                        at=_ts_of(sending) or self.clock(),
                        page_query={str(k): str(v) for k, v in query.items()}
                        if isinstance(query, dict) else None)
            elif e.get("event") in ("send_resolved", "placed"):
                self._unconfirmed.pop(str(e.get("intent_id", "")), None)
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
                if e.get("order_id"):
                    self._booked_exits.add(str(e["order_id"]))
                pos = self._open.get(symbol)
                if remaining and pos is not None:
                    pos.qty = int(remaining)
                    pos.exit_order_id = None
                    pos.exit_reason = None
                else:
                    self._open.pop(symbol, None)
        for pos in self._open.values():
            opened = pos.opened_at.astimezone(CT).date() if pos.opened_at else None
            if opened is not None and opened < today:
                self.journal.record(
                    "position_carried", symbol=pos.symbol, qty=pos.qty,
                    intent_id=pos.intent_id, opened_on=opened.isoformat(),
                    stop_order_id=pos.stop_order_id, target_order_id=pos.target_order_id,
                    detail=f"recovered from {opened.isoformat()}'s journal — held past that "
                           f"day's close; the reconcile checks its legs against the listing")
        if self._open or self._working:
            self.journal.record("recovered",
                                positions=[p.to_dict() for p in self._open.values()],
                                working=[w.to_dict() for w in self._working.values()])
        # The journal is what this service believed when it died. The broker is
        # what is true now, and a restart is exactly when those differ. [st-v7oa]
        # But a real service comes back LOCKED, and the transport's credential
        # source is bound only after this constructor returns — so the first
        # installed start (2026-09-14 06:50 CT) journaled one spurious
        # 'no trading credential source is bound' error. With no credential
        # there is nothing to ask the broker with; the reconcile runs at the
        # unlock instead, which is the first moment it can. The mock needs no
        # credential and keeps reconciling here, so the recovery tests hold.
        if self.arming.permits_exit() is None or not self._needs_credential():
            self.reconcile()
