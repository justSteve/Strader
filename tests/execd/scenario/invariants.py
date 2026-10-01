"""The invariants — what must be true after every step of every scenario. [st-ug1h]

One function, :func:`check`, run by the harness after each step. It returns
a list of :class:`Violation` s, each with a stable ``name`` (the thing a
test or a bead cites) and the numbers that broke it. The paper book is the
ground truth — it is the account — and the service's beliefs, its journal
and its status body are checked against it.

The names, and what each guards (the 09-30 bug each would have caught is in
brackets):

``short_position``
    The paper book is short a contract. Long premium only, ever. [st-0f5q]
``oversold_journaled``
    The service itself wrote ``oversold`` or ``short_held``. [st-0f5q]
``stop_level_crossed_at_fill``
    A position's SPX stop level is already behind the index on the
    ``filled`` line — the SPX-mark loop market-sells it on its next pass.
``false_short_alarm``
    An ``unattributed_sell`` line ("if it is this service's leg the account
    is short; check the broker") for a fill the service then booked as its
    own close — a loud alarm with nothing behind it.
``two_stops`` / ``two_targets``
    More than one working protective stop, or take-profit, on one held
    contract. [st-0f5q: the second bracket]
``bracket_not_linked``
    A held contract's one stop and one target rest as two orders, not one
    one-cancels-other pair — the paper book holds a bracket as OCO, as
    Schwab does, so both can fill.
``resting_sell_exceeds_held`` / ``resting_sell_without_position``
    Working sells (stop or target) for more than is held, or with nothing
    held behind them — a short waiting for a print.
``stop_not_below_bid_when_placed`` / ``target_not_above_bid_when_placed``
    A stop at or above the bid, or a target at or under it, at the moment
    it was placed: it fills at once, a sale rather than a trigger. A stop
    the entry carried (a triggered child) is judged at the entry's SEND —
    the service's decision — not when the book brought it to life on the
    fill; a market that gaps through it in between is the market.
    [st-0f5q: the 9.00 stop over an 8.80 fill]
``open_mismatch``
    What the service holds (``_open``) differs from the book's positions
    after reconcile has run.
``closed_kind_unknown`` / ``external_close_of_own_order``
    A ``closed`` line whose kind/reason pair is not one the service writes,
    or a close booked ``external`` for an order the service sent. [st-0f5q]
``pnl_mismatch``
    A ``closed`` line's exit price is not the book's fill, its P&L is not
    (exit − entry) × 100 × qty, an entry's ``filled`` price is not the
    book's, or the status body's realized P&L is not the journal's sum.
    [the 'today' total, 13e43dd, at the service level]
``trail_moved_down``
    Once the trailing stop has armed, the resting stop's price fell without
    Steve moving it.
``trail_locked_a_loss``
    The trailing stop has armed (its first tier promises +$30) and rests
    where a fill would net a loss after fees.
``stop_dollars_off_ticket``
    An entry whose stop was set in dollars rests its stop further from the
    FILL than the ticket's distance from the limit, by more than one tick.
    [st-0f5q: 9.20 limit, 8.80 fill; st-7p5u]

Nothing here mutates the service or the book: no reconcile, no sweep (it
reads the book's dictionaries, not its sweeping methods).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from execd.broker import OrderStatus
from execd.intent import OrderType, Side, parse_occ
from execd.stops import exit_triggered, tick_for

if TYPE_CHECKING:  # pragma: no cover
    from .harness import Scenario

#: The ``(kind, reason)`` pairs a ``closed`` line may carry — every place
#: ``_book_close`` / ``_settle`` / ``_book_found_fill`` is reached from.
_EXIT_REASONS = ("spx-stop", "spx-exit", "spx-target", "flatten", "exit", "page", "scenario")
KNOWN_CLOSES: frozenset[tuple[str, str]] = frozenset(
    {("protective-stop", "resting-stop"), ("protective-stop", "protective-stop"),
     ("target", "resting-target"), ("target", "target"),
     ("resting-stop", "resting-stop"),
     ("external", "closed-outside-this-service")}
    | {(k, "in-flight-close") for k in _EXIT_REASONS}
    | {(k, k) for k in _EXIT_REASONS})


@dataclass(frozen=True)
class Violation:
    name: str
    detail: str

    def __str__(self) -> str:
        return f"{self.name}: {self.detail}"


class InvariantViolation(AssertionError):
    def __init__(self, label: str, violations: list[Violation], log: str = "") -> None:
        self.violations = violations
        self.names = sorted({v.name for v in violations})
        body = "\n  ".join(str(v) for v in violations)
        super().__init__(f"after {label}:\n  {body}" + (f"\n\nsequence:\n{log}" if log else ""))


@dataclass
class Memory:
    """What the checks remember between steps (it lives on the scenario and
    survives a restart of the service)."""

    #: symbol → the resting stop's price at the last check, once trailing
    trail_stop: dict[str, float] = field(default_factory=dict)
    #: symbols Steve moved a leg on (no trail or ticket comparison after)
    hand_adjusted: set[str] = field(default_factory=set)
    #: order ids the scenario placed "in TOS", outside the service
    outside_orders: set[str] = field(default_factory=set)
    #: violations already reported, so a standing one is reported once
    seen: set[tuple[str, str]] = field(default_factory=set)


def _working_sells(book, symbol: str | None = None) -> list:
    return [o for o in book._orders.values()
            if o.status is OrderStatus.WORKING and o.side is Side.SELL_TO_CLOSE
            and (symbol is None or o.symbol == symbol)]


def _parent_of(book) -> dict[str, str]:
    out: dict[str, str] = {}
    for parent, kids in book._children.items():
        for k in kids:
            out[k] = parent
    return out


def check(scn: "Scenario") -> list[Violation]:
    book, svc, mem = scn.paper, scn.service, scn.memory
    out: list[Violation] = []
    journal = svc.journal.read()

    # ── long premium only ────────────────────────────────────────────────
    for sym, p in book._positions.items():
        if p.qty < 0:
            out.append(Violation("short_position", f"the book is short {p.qty} {sym.strip()}"))
    for e in journal:
        if e.get("event") in ("oversold", "short_held"):
            out.append(Violation("oversold_journaled",
                                 f"{e['event']} {e.get('symbol', '').strip()} qty {e.get('qty')} "
                                 f"order {e.get('order_id')} — {e.get('detail', '')[:120]}"))

    # ── a position is not born past its own stop level ───────────────────
    for e in journal:
        if e.get("event") != "filled" or e.get("kind") != "entry":
            continue
        spx, level, sym = e.get("spx"), e.get("stop_spx"), str(e.get("symbol", ""))
        if spx is None or level is None:
            continue
        try:
            right = parse_occ(sym).right
        except ValueError:
            continue
        if exit_triggered(right, float(spx), float(level)):
            out.append(Violation("stop_level_crossed_at_fill",
                                 f"{sym.strip()} filled at {e.get('price')} with SPX {spx} — "
                                 f"its stop level {level} is already behind the market, so the "
                                 f"SPX loop sells it on its next pass"))

    # ── a loud 'check the broker' only when there is something to check ──
    booked = {str(e.get("order_id")) for e in journal if e.get("event") == "closed"}
    for e in journal:
        if e.get("event") == "unattributed_sell" and str(e.get("order_id")) in booked:
            out.append(Violation("false_short_alarm",
                                 f"unattributed_sell for {e.get('order_id')} "
                                 f"({e.get('symbol', '').strip()}) — the service then booked "
                                 f"that same fill as a close of its own position"))

    # ── one bracket per held contract, never larger than what is held ────
    held = {s: p.qty for s, p in book._positions.items() if p.qty > 0}
    symbols = {o.symbol for o in _working_sells(book)} | set(held)
    for sym in symbols:
        sells = _working_sells(book, sym)
        stops = [o for o in sells if o.order_type is OrderType.STOP]
        targets = [o for o in sells if o.order_type is OrderType.LIMIT]
        if len(stops) > 1:
            out.append(Violation("two_stops", f"{sym.strip()}: " + ", ".join(
                f"{o.order_id}@{o.price}x{o.qty}" for o in stops)))
        if len(targets) > 1:
            out.append(Violation("two_targets", f"{sym.strip()}: " + ", ".join(
                f"{o.order_id}@{o.price}x{o.qty}" for o in targets)))
        if len(stops) == 1 and len(targets) == 1 and \
                book._oco.get(stops[0].order_id) != targets[0].order_id:
            out.append(Violation("bracket_not_linked",
                                 f"{sym.strip()}: stop {stops[0].order_id} and target "
                                 f"{targets[0].order_id} rest as two orders, not one OCO — "
                                 f"both can fill"))
        h = held.get(sym, 0)
        if sells and h == 0:
            out.append(Violation("resting_sell_without_position", f"{sym.strip()}: " + ", ".join(
                f"{o.order_id} {o.order_type.value}@{o.price}x{o.qty}" for o in sells)))
        elif sum(o.qty for o in stops) > h or sum(o.qty for o in targets) > h:
            out.append(Violation("resting_sell_exceeds_held",
                                 f"{sym.strip()}: held {h}, stops "
                                 f"{sum(o.qty for o in stops)}, targets "
                                 f"{sum(o.qty for o in targets)}"))

    # ── every leg on the right side of the bid when it was placed ────────
    parents = _parent_of(book)
    for o in book._orders.values():
        if o.side is not Side.SELL_TO_CLOSE or o.price is None or o.order_id in mem.outside_orders:
            continue
        if o.order_type not in (OrderType.STOP, OrderType.LIMIT):
            continue
        at = o.submitted_at
        when = "placed"
        if o.order_id in parents and parents[o.order_id] in book._orders:
            at = book._orders[parents[o.order_id]].submitted_at
            when = f"sent with entry {parents[o.order_id]}"
        try:
            q = scn.market.quote_at(o.symbol, at)
        except Exception:  # noqa: BLE001 — a symbol off the tape is not judged
            continue
        if q.bid <= 0:
            continue
        if o.order_type is OrderType.STOP and o.price >= q.bid - 1e-9:
            out.append(Violation("stop_not_below_bid_when_placed",
                                 f"{o.order_id} stop {o.price:.2f} with the bid {q.bid:.2f} "
                                 f"(ask {q.ask:.2f}) when {when}"))
        if o.order_type is OrderType.LIMIT and o.price <= q.bid + 1e-9:
            out.append(Violation("target_not_above_bid_when_placed",
                                 f"{o.order_id} target {o.price:.2f} with the bid {q.bid:.2f} "
                                 f"when {when}"))

    # ── what the service holds is what the book holds ────────────────────
    if scn.reconciled:
        mine = {s: p.qty for s, p in svc._open.items()}
        if mine != held:
            out.append(Violation("open_mismatch",
                                 f"service holds {_fmt(mine)}, the book holds {_fmt(held)}"))

    # ── every close is one the service knows how to name ────────────────
    own = _own_order_ids(book, mem)
    realized = 0.0
    for e in journal:
        ev = e.get("event")
        if ev == "closed":
            kind, why = e.get("kind"), e.get("reason")
            if (kind, why) not in KNOWN_CLOSES:
                out.append(Violation("closed_kind_unknown",
                                     f"closed {e.get('symbol', '').strip()} kind={kind!r} "
                                     f"reason={why!r} order {e.get('order_id')}"))
            if kind == "external" and e.get("order_id") in own:
                out.append(Violation("external_close_of_own_order",
                                     f"order {e.get('order_id')} was sent by the service and its "
                                     f"fill was booked as a close outside it"))
            order = book._orders.get(str(e.get("order_id")))
            if order is not None and order.fill_price is not None and \
                    abs(float(order.fill_price) - float(e.get("exit_price", -1))) > 1e-9:
                out.append(Violation("pnl_mismatch",
                                     f"closed line exit {e.get('exit_price')} but the book filled "
                                     f"{order.order_id} at {order.fill_price}"))
            want = round((float(e["exit_price"]) - float(e["entry_price"])) * 100 * int(e["qty"]), 2)
            if abs(want - float(e.get("pnl_usd", 0))) > 0.005:
                out.append(Violation("pnl_mismatch", f"closed line pnl {e.get('pnl_usd')} but "
                                                     f"(exit − entry) × 100 × qty is {want}"))
            realized += float(e.get("pnl_usd") or 0)
        elif ev == "filled" and e.get("kind") == "entry":
            order = book._orders.get(str(e.get("order_id")))
            if order is not None and order.fill_price is not None and \
                    abs(float(order.fill_price) - float(e.get("price", -1))) > 1e-9:
                out.append(Violation("pnl_mismatch",
                                     f"filled line price {e.get('price')} but the book filled "
                                     f"{order.order_id} at {order.fill_price}"))
    pnl = scn.status_pnl()
    if pnl is not None and abs(pnl - round(realized, 2)) > 0.005:
        out.append(Violation("pnl_mismatch", f"status realized {pnl} but the journal's closed "
                                             f"lines sum to {round(realized, 2)}"))

    # ── the trailing stop only rises ─────────────────────────────────────
    for sym, pos in svc._open.items():
        stops = [o for o in _working_sells(book, sym) if o.order_type is OrderType.STOP]
        if pos.trail_tier >= 0 and sym not in mem.trail_stop and stops:
            mem.trail_stop[sym] = max(o.price for o in stops)
    for sym in list(mem.trail_stop):
        if sym not in held:
            mem.trail_stop.pop(sym)
            continue
        if sym in mem.hand_adjusted:
            mem.trail_stop.pop(sym)
            continue
        stops = [o for o in _working_sells(book, sym) if o.order_type is OrderType.STOP]
        if not stops:
            continue
        now = max(o.price for o in stops)
        if now < mem.trail_stop[sym] - 1e-9:
            out.append(Violation("trail_moved_down",
                                 f"{sym.strip()}: the trailing stop was {mem.trail_stop[sym]:.2f} "
                                 f"and rests at {now:.2f} now"))
        mem.trail_stop[sym] = max(now, mem.trail_stop[sym])

    # ── once the trail has armed, the stop locks a profit, not a loss ────
    for sym, pos in svc._open.items():
        if pos.trail_tier < 0 or sym in mem.hand_adjusted:
            continue
        stops = [o for o in _working_sells(book, sym) if o.order_type is OrderType.STOP]
        if len(stops) != 1:
            continue
        fees = pos.entry_commission_usd + 0.65 * pos.qty
        at_stop = round((float(stops[0].price) - pos.entry_price) * 100 * pos.qty - fees, 2)
        if at_stop < 0:
            out.append(Violation("trail_locked_a_loss",
                                 f"{sym.strip()} x{pos.qty} in at {pos.entry_price}: the trail "
                                 f"(tier {pos.trail_tier}) rests the stop at {stops[0].price:.2f}, "
                                 f"{at_stop:+.2f} net if it fills there"))

    # ── a dollar stop is that many dollars from the fill ─────────────────
    tickets = {str(e.get("intent_id")): e.get("intent") or {} for e in journal
               if e.get("event") == "request" and e.get("kind") == "place"}
    trailed = {str(e.get("intent_id")) for e in journal if e.get("event") == "trail"}
    for sym, pos in svc._open.items():
        intent = tickets.get(pos.intent_id) or {}
        if intent.get("stop_price") is None or intent.get("limit") is None:
            continue
        if sym in mem.hand_adjusted or pos.intent_id in trailed or pos.trail_tier >= 0:
            continue
        if pos.qty != intent.get("qty") or not held.get(sym):
            continue
        stops = [o for o in _working_sells(book, sym) if o.order_type is OrderType.STOP]
        if len(stops) != 1:
            continue
        entry = book._orders.get(pos.entry_order_id)
        fill = float(entry.fill_price) if entry is not None and entry.fill_price else pos.entry_price
        want = round(float(intent["limit"]) - float(intent["stop_price"]), 2)
        got = round(fill - float(stops[0].price), 2)
        tick = tick_for(float(stops[0].price))
        if abs(got - want) > tick + 1e-9:
            out.append(Violation("stop_dollars_off_ticket",
                                 f"{sym.strip()}: the ticket's stop was {want:.2f} under the "
                                 f"{float(intent['limit']):.2f} limit; the fill was {fill:.2f} "
                                 f"and the stop rests at {stops[0].price:.2f}, {got:.2f} under it"))
    # a standing violation is reported at the step it appears, once
    fresh: list[Violation] = []
    for v in out:
        key = (v.name, v.detail)
        if key not in mem.seen:
            mem.seen.add(key)
            fresh.append(v)
    return fresh


def _own_order_ids(book, mem: Memory) -> set[str]:
    """Every order in the book the service sent — all of them, but those the
    scenario placed by hand 'in TOS'."""
    return {oid for oid in book._orders
            if oid not in mem.outside_orders and not oid.startswith("paper-expiry-")}


def _fmt(d: dict[str, int]) -> str:
    return "{" + ", ".join(f"{k.strip()}: {v}" for k, v in sorted(d.items())) + "}" if d else "nothing"
