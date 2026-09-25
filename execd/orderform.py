"""The order form — a ticket priced, previewed and sent by code alone. [st-k6gl]

Steve, 2026-09-14: "the page needed to run by code alone … a button to
indicate bearish or bullish intent … pre-populating the strikes available …
indicate a delta so I can over-ride the default … only the essential
elements of the order form … eventually this needs to run on an iPad."

Until this module the ticket was priced by COO typing ``single / price / go
/ send`` into the dictation desk. Here the page does the same work with the
same chain reader (``execd.compose.parse_chain``) and the
same service (``ExecService.preview`` / ``.place``, the same rules, journal,
paper/live mode, STOP and FLATTEN). No model, no agent, no terminal between
his intent and the service.

The flow, top to bottom on ``/exec/order``:

1. BULLISH (calls) or BEARISH (puts); the expiry (today, or the next
   weekday).
2. The chain, fetched **once** per side/expiry through the market door with
   a bounded ``strikeCount`` — never the unbounded ``service.chain`` — and
   shown as the strikes around spot with bid, ask and delta. The default row
   is nearest to spot (his ruling); a delta override picks the row whose
   |delta| is nearest; a row can be tapped directly.
3. The ticket: the limit on the service's own tick grid and the stop — a
   flat ``DEFAULT_STOP_LOSS_USD`` loss under the limit until he types a
   stop of his own (Steve, 2026-09-17: "stop loss amount should initially
   be set to flat $20"; st-bafu). There is no budget, no attempts and no
   derivation on the form: the FD0 budget the form once carried was a
   second budget beside the service's own bounds, and he had it removed
   ("Let's just completely remove that complete calculation"). The
   service's ceiling still refuses an entry that does not fit the day.
   The ticket's price follows the live ask through the poll until the
   padlock beside it is tapped (st-2s4u; Steve, 2026-09-15: "a padlock icon
   toggled between locked and unlocked … this is how TOS platform works").
   Locked, the price is frozen where it was, the stop is struck from that
   price, the live ask shows beside it, and SEND sends it as the limit; the
   service's price band still judges it. RE-PRICE keeps the strike and
   reprices at the market, dropping the lock.
   **The price is a box** (co-8mb1z, Steve 2026-09-25: "i want to be able
   to set the price of my entry"): it shows the limit, and what he types
   is the limit sent, to the nearest tick (``nearest_tick``) — typing is
   locking. The stop follows it at $20 under until he types his own.
4. SEND → ``service.place`` of the ticket as priced at that moment (the
   locked price or the ask), under the id ``page-<stamp>-<token>``, source
   ``page``. The service runs the broker's own preview inside every place,
   so there is no PREVIEW step on the page (Steve, 2026-09-16: "I want to
   remove the preview step as well. anything we can do to shorten the
   submission after the decision has been made", st-igw0). The SEND token
   is issued with the page, single use, and a replay of a spent token is
   answered from its remembered outcome — never sent twice. **SEND beside a
   working entry in the same contract re-prices it** (co-8mb1z): the old
   order comes off by a confirmed cancel first and only then does the new
   price go out; the form stays live for the next price.
5. The open position with its money, from the same status body the
   operations page reads.

Everything is server-rendered and works without a script; the small inline
script on the page only re-fetches the ticket when an input changes and
polls the quote and the position every few seconds, filling in place, and
pauses while the tab is hidden. All arithmetic is Python.

Nothing here imports a transport or names a credential; the wall tests
(``tests/execd/test_wall.py``) run over this module like every other.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from .bounds import CT
from .broker import COMMISSION_PER_CONTRACT_USD, CONTRACT_MULTIPLIER, BrokerError
from .compose import Contract, parse_chain
from .intent import OrderIntent
from .service import ExecService
from .stops import (_floor_to, _round_up_to_tick, on_tick, protective_stop_price, risk_usd,
                    stop_is_consistent, tick_for)

log = logging.getLogger("execd.orderform")

#: Strikes asked of the market door, either side of spot. Bounded on
#: purpose: the unbounded chain is hundreds of KB.
CHAIN_STRIKES = 40
#: Strikes shown either side of spot.
STRIKES_EACH_SIDE = 8
#: The source word the service journals for a page intent.
SOURCE = "page"
#: The loss the stop starts at, for the whole ticket, before commissions
#: (Steve, 2026-09-17: "stop loss amount should initially be set to flat
#: $20", st-bafu). The resting stop is the limit less this, on the tick
#: grid; a stop of his own in the box replaces it.
DEFAULT_STOP_LOSS_USD = 20.0
#: The δ target the form starts at when no delta and no strike is given.
#: Steve, 2026-09-15 (st-shhi), from his 2026-08-19 words that 0.8 is the
#: consensus point to buy a single; it replaces "nearest to spot" as the
#: page's default. ``choose`` itself still answers nearest-to-spot when a
#: caller passes no delta at all.
DEFAULT_DELTA = 0.80
#: A SEND token is issued with the page and lives this long, single use —
#: long, because it exists to stop a replay or a double send, not to time
#: him out (st-igw0: the PREVIEW step is gone, SEND is the one action).
SEND_NONCE_TTL_S = 4 * 3600.0
#: The page polls the quote and the position this often (seconds).
POLL_S = 3


# ── what he chose ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Selection:
    """The form's inputs, parsed once from a query string or a form body,
    tolerant of anything malformed (a bad number is 'not given')."""

    side: str | None = None          # "call" | "put" | None
    expiry: date | None = None
    strike: float | None = None
    delta: float | None = None
    lots: int = 1
    #: The padlock (st-2s4u). ``None`` is unlocked: the ticket is priced at
    #: the ask each time it is priced and the head follows the live quote.
    #: A number is the price he locked, sent as the limit whatever the ask
    #: does after; the service's price band still judges it at preview and
    #: send. RE-PRICE, a new strike, a new expiry or a new side drop it.
    limit: float | None = None
    #: A stop of his own (st-m3bl; Steve, 2026-09-17: "permit me to input a
    #: stop loss strike price in addition to the existing hard-coded dollar
    #: amount … absent a decimal point means a strike price"). The raw text
    #: of the box, kept as typed so the rule is applied once, in ``price``:
    #: a '.' makes it a dollar option price, none makes it an SPX level.
    #: ``None`` is the box untouched — the flat-loss stop stands.
    stop: str | None = None

    @property
    def right(self) -> str:
        return "CALL" if self.side == "call" else "PUT"

    @classmethod
    def from_args(cls, args: Mapping[str, Any], *, today: date,
                  lots_cap: int = 1) -> "Selection":
        side = str(args.get("side") or "").lower()
        side = side if side in ("call", "put") else None
        expiry = _parse_expiry(str(args.get("expiry") or ""), today)
        strike = _as_float(args.get("strike"))
        delta = _as_float(args.get("delta"))
        if delta is not None and not (0 < abs(delta) <= 1):
            delta = None
        if delta is None and "delta" not in args and not _as_float(args.get("strike")):
            delta = DEFAULT_DELTA       # a blank box ('delta' present, empty) means nearest to spot
        lots = _as_int(args.get("lots"), 1)
        lots = max(1, min(lots, max(1, lots_cap)))
        # ``reprice`` is the RE-PRICE button's own field: it means "at the
        # market", so a lock riding on the same form is dropped.
        limit = None if args.get("reprice") else _as_float(args.get("limit"))
        stop = str(args.get("stop") or "").strip() or None
        return cls(side=side, expiry=expiry,
                   strike=strike if strike and strike > 0 else None,
                   delta=abs(delta) if delta is not None else None, lots=lots,
                   limit=round(limit, 2) if limit and limit > 0 else None,
                   stop=stop)

    def as_query(self, **override: Any) -> dict[str, str]:
        """The selection as query/hidden fields; ``override`` replaces or,
        with ``None``, drops a key (a tapped strike drops the delta)."""
        d: dict[str, Any] = {
            "side": self.side, "expiry": self.expiry.isoformat() if self.expiry else None,
            "strike": f"{self.strike:g}" if self.strike is not None else None,
            "delta": f"{self.delta:g}" if self.delta is not None else None,
            "lots": str(self.lots) if self.lots != 1 else None,
            "limit": f"{self.limit:.2f}" if self.limit is not None else None,
            "stop": self.stop,
        }
        d.update(override)
        return {k: str(v) for k, v in d.items() if v is not None}

    @property
    def locked(self) -> bool:
        return self.limit is not None


def parse_leg_text(raw: str, name: str = "stop") -> tuple[str, float]:
    """Steve's rule for a box that takes either form (2026-09-16, st-2j3m;
    the SEND screen's stop since st-m3bl): a '.' in the text makes it a
    dollar option price, none makes it an SPX level. ``("price", 10.30)`` or
    ``("spx", 7585.0)``; ``ValueError`` in words for anything else."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError(f"{name} is empty")
    kind = "price" if "." in raw else "spx"
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number — a price with a '.' (10.30) or an "
                         f"SPX level without one (7585) — not {raw!r}") from None
    if kind == "spx" and not value.is_integer():
        raise ValueError(f"{name} {raw!r} is not a whole SPX level")
    return kind, value


def _parse_expiry(word: str, today: date) -> date:
    w = word.strip().lower()
    if w in ("", "0", "0dte", "today"):
        return today
    if w in ("1", "1dte", "tomorrow", "next"):
        return next_weekday(today)
    try:
        return date.fromisoformat(w)
    except ValueError:
        return today


def next_weekday(d: date) -> date:
    n = d + timedelta(days=1)
    while n.weekday() >= 5:
        n += timedelta(days=1)
    return n


def _as_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v: Any, default: int) -> int:
    f = _as_float(v)
    if f is None:
        return default
    return int(f) if f == int(f) else default


# ── the chain and the choice ─────────────────────────────────────────────

def load_chain(service: ExecService, expiry: date, right: str) -> tuple[list[Contract], float]:
    """One bounded market read for one right and one expiry, parsed with the
    engine's own reader. Weekly (SPXW) contracts when the chain has them —
    the desk trades SPXW — and the underlying's price from the same body."""
    iso = expiry.isoformat()
    body = service.market_read("chains", {
        "symbol": "$SPX", "contractType": right, "strikeCount": str(CHAIN_STRIKES),
        "includeUnderlyingQuote": "true", "fromDate": iso, "toDate": iso})
    contracts = parse_chain(body, expiration=iso, right=right)
    weekly = [c for c in contracts if c.symbol.upper().startswith("SPXW")]
    if weekly:
        contracts = weekly
    contracts.sort(key=lambda c: c.strike)
    spx = _as_float(body.get("underlyingPrice") if isinstance(body, dict) else None) or 0.0
    if spx <= 0:
        spx = service.spx_mark()
    return contracts, spx


def window(contracts: list[Contract], spx: float, n: int = STRIKES_EACH_SIDE) -> list[Contract]:
    below = [c for c in contracts if c.strike <= spx][-n:]
    above = [c for c in contracts if c.strike > spx][:n]
    return below + above


def choose(contracts: list[Contract], spx: float, *, strike: float | None,
           delta: float | None) -> Contract:
    """A tapped strike wins; else the delta override; else nearest to spot
    (Steve's ruling, 2026-09-14). Ties go to the tighter spread."""
    if not contracts:
        raise ValueError("the chain has no contracts to choose from")
    if strike is not None:
        for c in contracts:
            if abs(c.strike - strike) < 1e-6:
                return c
        raise ValueError(f"no strike {strike:g} in the chain")
    if delta is not None:
        return min(contracts, key=lambda c: (abs(c.abs_delta - delta), c.spread_pts))
    return min(contracts, key=lambda c: (abs(c.strike - spx), c.spread_pts))


# ── the priced ticket ────────────────────────────────────────────────────

def nearest_tick(pts: float) -> float:
    """A typed entry price on the exchange's grid, to the nearest tick —
    the price box shows this number, and it is the limit sent (co-8mb1z,
    Steve 2026-09-25: "i want to be able to set the price of my entry")."""
    t = tick_for(pts)
    return round(max(t, round(pts / t) * t), 2)


def limit_at(ask_pts: float) -> float:
    """The buy limit the form sends for an ask: the ask rounded up to the
    service's own tick grid. One place, so the page's live head, the priced
    ticket and the state poll all say the same number."""
    return _round_up_to_tick(ask_pts, tick_for(ask_pts))


@dataclass
class Priced:
    selection: Selection
    spx: float = 0.0
    contracts: list[Contract] = field(default_factory=list)   # the window shown
    contract: Contract | None = None
    limit: float | None = None
    #: the SPX level the intent carries — the service walks it into the
    #: resting stop at the fill
    stop_spx: float | None = None
    stop_price: float | None = None
    #: how the stop was set: ``None`` for the flat-loss default, ``"price"``
    #: or ``"spx"`` for a stop of his own (st-m3bl)
    stop_set_by: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    #: when the ask this ticket is priced from was read — the service's clock
    #: at pricing, shown beside SEND (st-sk9r, audit note 37)
    priced_at: datetime | None = None

    @property
    def ready(self) -> bool:
        """A contract at a limit — the ticket shows and SEND is offered. A
        fault on it (a stop that cannot be one) is on the ticket in red and
        ``intent_for`` refuses the send in the same words."""
        return self.contract is not None and self.limit is not None

    # ── money ──
    @property
    def lots(self) -> int:
        return self.selection.lots

    @property
    def cost_usd(self) -> float | None:
        return round(self.limit * CONTRACT_MULTIPLIER * self.lots, 2) if self.limit else None

    @property
    def commissions_usd(self) -> float:
        return round(COMMISSION_PER_CONTRACT_USD * self.lots * 2, 2)

    @property
    def stop_loss_usd(self) -> float | None:
        """What the resting stop loses if it fills at its price, before
        commissions — the one number the ticket's stop line shows."""
        if self.stop_price is None or self.limit is None:
            return None
        return risk_usd(self.limit, self.stop_price, self.lots)

    @property
    def net_at_stop_usd(self) -> float | None:
        loss = self.stop_loss_usd
        return None if loss is None else round(-loss - self.commissions_usd, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.selection.side, "right": self.selection.right,
            "expiry": self.selection.expiry.isoformat() if self.selection.expiry else None,
            "spx": self.spx, "lots": self.lots,
            "strikes": [_contract_row(c, self.contract) for c in self.contracts],
            "contract": _contract_row(self.contract, self.contract) if self.contract else None,
            "limit": self.limit, "cost_usd": self.cost_usd,
            "commissions_usd": self.commissions_usd,
            "stop_spx": self.stop_spx, "stop_price": self.stop_price,
            "stop_set_by": self.stop_set_by, "stop_text": self.selection.stop,
            "stop_loss_usd": self.stop_loss_usd,
            "net_at_stop_usd": self.net_at_stop_usd,
            "warnings": list(self.warnings),
            "error": self.error,
        }


def _contract_row(c: Contract | None, chosen: Contract | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {"symbol": c.symbol, "strike": c.strike, "bid": c.bid_pts, "ask": c.ask_pts,
            "delta": round(c.delta, 3), "chosen": chosen is not None and c.symbol == chosen.symbol}


def price(service: ExecService, sel: Selection) -> Priced:
    """Everything the form shows, from the live chain. Never raises: a fault
    is on ``.error`` in plain words, with whatever was priced before it."""
    out = Priced(selection=sel, priced_at=service.clock())
    if sel.side is None or sel.expiry is None:
        out.error = "pick BULLISH or BEARISH"
        return out
    try:
        contracts, spx = load_chain(service, sel.expiry, sel.right)
    except BrokerError as exc:
        out.error = f"the chain could not be read: {exc}"
        return out
    out.spx = spx
    if not contracts:
        out.error = f"no {sel.right.lower()}s expiring {sel.expiry.isoformat()} in the chain"
        return out
    out.contracts = window(contracts, spx)
    try:
        c = choose(contracts, spx, strike=sel.strike, delta=sel.delta)
    except ValueError as exc:
        out.error = str(exc)
        return out
    out.contract = c
    # The limit on the service's own tick grid (0.05 under $3, 0.10 at and
    # above), rounded up — the service refuses a price off the grid. A locked
    # price (the padlock, st-2s4u) is the limit instead, whatever the ask is
    # now; the service's price band judges it at the send.
    out.limit = nearest_tick(sel.limit) if sel.limit is not None else limit_at(c.ask_pts)
    if not (0 < c.abs_delta <= 1):
        out.error = f"the chain gives no usable delta for {c.strike:g} — no stop can be struck"
        return out
    if sel.stop:
        _apply_stop_of_his_own(out, c, spx)
    else:
        _apply_flat_loss_stop(out, c, spx)
    return out


def _wire_delta(c: Contract) -> float:
    """The delta as the intent carries it. The stop's level is struck with
    this number because the service walks the level back into a price with
    the intent's delta, not the chain's."""
    return round(c.abs_delta, 4)


def _level_for(right: str, spx: float, limit: float, stop_price: float, delta: float) -> float:
    """The SPX level that walks to ``stop_price`` — the inverse of
    ``protective_stop_price`` — rounded to the cent **away from spot**. The
    service rounds the walked price *up* to the tick, so a level a hair
    nearer spot than exact would rest the stop one tick higher than the
    number on the ticket; a hair farther lands on it."""
    distance = (limit - stop_price) / delta
    if right == "CALL":
        return math.floor(round((spx - distance) * 100, 6)) / 100
    return math.ceil(round((spx + distance) * 100, 6)) / 100


def _apply_flat_loss_stop(out: Priced, c: Contract, spx: float) -> None:
    """The stop the ticket starts with: ``DEFAULT_STOP_LOSS_USD`` under the
    limit for the whole ticket, on the tick grid. [st-bafu]

    Rounded *up* to the grid when the loss per contract is not a whole tick
    (more than one lot), so the ticket never risks more than the flat
    figure; held one tick under the limit and one tick above nothing, the
    same two clamps the service's own stop gets. A limit with no tick of
    room under it cannot carry a stop, and the ticket says so and offers no
    SEND — an entry with no stop is the state the service must not reach."""
    limit = out.limit
    per_contract = DEFAULT_STOP_LOSS_USD / (CONTRACT_MULTIPLIER * out.lots)
    floor_tick = tick_for(0.0)
    stop = _round_up_to_tick(max(limit - per_contract, floor_tick), floor_tick)
    cap = round(limit - tick_for(limit), 2)
    cap = _floor_to(cap, tick_for(cap)) if cap > 0 else cap
    stop = min(stop, cap)
    if stop < floor_tick:
        out.error = f"a {limit:.2f} limit leaves no room for a stop under it"
        return
    out.stop_price = round(stop, 2)
    out.stop_spx = _level_for(c.right, spx, limit, out.stop_price, _wire_delta(c))


def _apply_stop_of_his_own(out: Priced, c: Contract, spx: float) -> None:
    """The stop box on the SEND screen, applied to a priced ticket. [st-m3bl]

    Steve, 2026-09-17: *"permit me to input a stop loss strike price in
    addition to the existing hard-coded dollar amount. just add an input on
    the SEND screen pre-populated with the dollar amount. over-riding that
    follows the same rule as updating - absent a decimal point means a
    strike price."*

    The intent carries the stop as an SPX level and the service walks it
    into the resting price at the fill. A stop of his own keeps that shape.
    **Dollars** (a '.'): the price he typed becomes the resting stop, and
    its SPX level is the walk back from spot through the contract's delta
    at the limit — the inverse of ``protective_stop_price`` — so the intent
    still carries a level and the service rests his number when it fills at
    the limit with the mark where it was (a better fill or a moved mark
    re-walks from the level, which is the instrument). **A level** (no
    '.'): the level is the trigger as typed, and the resting price is the
    walk forward.

    Refused in words on the ticket — SEND is then refused with the same
    words: a price off the tick grid, at or above the limit, or not
    positive; a level on the wrong side of spot for the right, or one that
    walks to a price nothing can rest at. The form does not judge the size
    of his stop (st-bafu: the budget, the noise floor and their warnings
    left with the derivation); the service's ceiling does."""
    sel = out.selection
    if out.limit is None or not sel.stop:
        return
    try:
        kind, value = parse_leg_text(sel.stop, "stop")
    except ValueError as exc:
        out.error = f"your stop: {exc}"
        return
    right = c.right
    word = "call" if right == "CALL" else "put"
    delta = _wire_delta(c)
    if kind == "price":
        if value <= 0:
            out.error = f"your stop: a stop price must be positive, not {value:g}"
            return
        if not on_tick(value):
            tick = tick_for(value)
            out.error = (f"your stop: {value:.2f} is not on the {tick:.2f} grid SPX options "
                         f"quote in {'at and above' if tick > 0.05 else 'below'} $3.00")
            return
        if value >= out.limit:
            out.error = (f"your stop: {value:.2f} is not below the {out.limit:.2f} limit — "
                         f"it would fill at once")
            return
        stop_price = round(value, 2)
        level = _level_for(right, spx, out.limit, stop_price, delta)
    else:
        level = value
        if not stop_is_consistent(right, spx, level):
            side = "below" if right == "CALL" else "above"
            out.error = (f"your stop: a {word}'s stop sits {side} the market, and SPX {level:g} "
                         f"is not {side} the {spx:.2f} mark — it would fire at once")
            return
        try:
            stop_price = protective_stop_price(out.limit, delta, spx, level)
        except ValueError as exc:
            out.error = f"your stop: SPX {level:g} walks to no price a stop can rest at: {exc}"
            return
        if out.limit - abs(spx - level) * delta <= 0:
            # the same clamp the service's own stop gets
            # (stops.protective_stop_price): a level that walks the option
            # below nothing rests one tick above it, and the SPX loop at his
            # level is the stop that fires
            out.warnings.append(f"SPX {level:g} WALKS THE OPTION BELOW ZERO — the resting stop is "
                                f"one tick, {stop_price:.2f}; the SPX loop at {level:g} is the stop")
    out.stop_spx = round(level, 2)
    out.stop_price = stop_price
    out.stop_set_by = kind


def intent_for(priced: Priced, *, intent_id: str, engine_sha: str) -> dict[str, Any]:
    """The service's ``OrderIntent`` wire form for the priced ticket, checked
    against the service's own rules before it leaves the form."""
    if priced.error:
        # a ticket priced with a fault on it — a stop of his own that cannot
        # be one (st-m3bl), a limit with no room for a stop — is shown, never
        # sent
        raise ValueError(priced.error)
    if not priced.ready or priced.stop_spx is None:
        raise ValueError("nothing is priced")
    d = {
        "intent_id": intent_id, "symbol": priced.contract.symbol, "side": "BUY_TO_OPEN",
        "qty": priced.lots, "order_type": "LIMIT", "limit": priced.limit,
        "stop_spx": float(priced.stop_spx),
        "delta": _wire_delta(priced.contract),
        "source": SOURCE, "engine_sha": engine_sha,
    }
    OrderIntent.from_dict(d).validated()
    return d


def stamp(now: datetime) -> str:
    return now.astimezone(CT).strftime("%Y%m%dT%H%M%S")
