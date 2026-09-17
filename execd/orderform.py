"""The order form — a ticket priced, previewed and sent by code alone. [st-k6gl]

Steve, 2026-09-14: "the page needed to run by code alone … a button to
indicate bearish or bullish intent … pre-populating the strikes available …
indicate a delta so I can over-ride the default … only the essential
elements of the order form … eventually this needs to run on an iPad."

Until this module the ticket was priced by COO typing ``single / price / go
/ send`` into the dictation desk. Here the page does the same work with the
same engine (``execd.compose``, the FD0 derivation the desk uses) and the
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
3. FD0: the budget (total, attempts — defaults $100 / 2, his to change on
   the form), every line of the derivation, the SPX cut level, the limit on
   the service's own tick grid, and the resting stop the service will place
   (``execd.stops.protective_stop_price`` at that limit) with the net there.
   The ticket's price follows the live ask through the poll until the
   padlock beside it is tapped (st-2s4u; Steve, 2026-09-15: "a padlock icon
   toggled between locked and unlocked … this is how TOS platform works").
   Locked, the price is frozen where it was, the derivation is re-run at
   that price, the live ask shows beside it, and SEND sends it as the
   limit; the service's price band still judges it. RE-PRICE keeps the
   strike and reprices at the market, dropping the lock.
4. SEND → ``service.place`` of the ticket as priced at that moment (the
   locked price or the ask), under the id ``page-<stamp>-<token>``, source
   ``page``. The service runs the broker's own preview inside every place,
   so there is no PREVIEW step on the page (Steve, 2026-09-16: "I want to
   remove the preview step as well. anything we can do to shorten the
   submission after the decision has been made", st-igw0). The SEND token
   is issued with the page, single use, and a replay of a spent token is
   answered from its remembered outcome — never sent twice.
5. The open position with its money, from the same status body the
   operations page reads.

Everything is server-rendered and works without a script; the small inline
script on the page only re-fetches the FD0 block when an input changes and
polls the quote and the position every few seconds, filling in place, and
pauses while the tab is hidden. All arithmetic is Python.

Nothing here imports a transport or names a credential; the wall tests
(``tests/execd/test_wall.py``) run over this module like every other.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from .bounds import CT
from .broker import COMMISSION_PER_CONTRACT_USD, CONTRACT_MULTIPLIER, BrokerError
import dataclasses as _dc

from .compose import Budget, CannotFund, Contract, Ticket, compose, parse_chain, template_fields
from .intent import OrderIntent
from .service import ExecService
from .stops import _round_up_to_tick, on_tick, protective_stop_price, stop_is_consistent, tick_for

log = logging.getLogger("execd.orderform")

#: Strikes asked of the market door, either side of spot. Bounded on
#: purpose: the unbounded chain is hundreds of KB.
CHAIN_STRIKES = 40
#: Strikes shown either side of spot.
STRIKES_EACH_SIDE = 8
#: The source word the service journals for a page intent.
SOURCE = "page"
#: FD0's standing budget for sizing the stop — the form's defaults, his to
#: change per ticket.
DEFAULT_BUDGET_USD = 100.0
DEFAULT_ATTEMPTS = 2
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
    budget_usd: float = DEFAULT_BUDGET_USD
    attempts: int = DEFAULT_ATTEMPTS
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
    #: ``None`` is the box untouched — FD0's derived stop stands.
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
        budget = _as_float(args.get("budget"))
        attempts = _as_int(args.get("attempts"), DEFAULT_ATTEMPTS)
        # ``reprice`` is the RE-PRICE button's own field: it means "at the
        # market", so a lock riding on the same form is dropped.
        limit = None if args.get("reprice") else _as_float(args.get("limit"))
        stop = str(args.get("stop") or "").strip() or None
        return cls(side=side, expiry=expiry,
                   strike=strike if strike and strike > 0 else None,
                   delta=abs(delta) if delta is not None else None, lots=lots,
                   budget_usd=budget if budget and budget > 0 else DEFAULT_BUDGET_USD,
                   attempts=max(1, attempts),
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
            "budget": f"{self.budget_usd:g}" if self.budget_usd != DEFAULT_BUDGET_USD else None,
            "attempts": str(self.attempts) if self.attempts != DEFAULT_ATTEMPTS else None,
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
    ticket: Ticket | None = None
    limit: float | None = None
    stop_price: float | None = None
    stop_note: str | None = None
    #: how the stop was set: ``None`` for FD0's derived stop, ``"price"`` or
    #: ``"spx"`` for a stop of his own (st-m3bl)
    stop_set_by: str | None = None
    error: str | None = None

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
    def net_at_stop_usd(self) -> float | None:
        if self.stop_price is None or self.limit is None:
            return None
        return round((self.stop_price - self.limit) * CONTRACT_MULTIPLIER * self.lots
                     - self.commissions_usd, 2)

    def to_dict(self) -> dict[str, Any]:
        t = self.ticket
        return {
            "side": self.selection.side, "right": self.selection.right,
            "expiry": self.selection.expiry.isoformat() if self.selection.expiry else None,
            "spx": self.spx, "lots": self.lots,
            "budget_usd": self.selection.budget_usd, "attempts": self.selection.attempts,
            "strikes": [_contract_row(c, self.contract) for c in self.contracts],
            "contract": _contract_row(self.contract, self.contract) if self.contract else None,
            "limit": self.limit, "cost_usd": self.cost_usd,
            "commissions_usd": self.commissions_usd,
            "stop_spx": t.stop_trigger_spx if t else None,
            "stop_price": self.stop_price, "stop_note": self.stop_note,
            "stop_set_by": self.stop_set_by, "stop_text": self.selection.stop,
            "net_at_stop_usd": self.net_at_stop_usd,
            "max_loss_usd": round(t.max_loss_usd, 2) if t else None,
            "derivation": t.derivation.as_record() if t else None,
            "warnings": list(t.warnings) if t else [],
            "error": self.error,
        }


def _contract_row(c: Contract | None, chosen: Contract | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {"symbol": c.symbol, "strike": c.strike, "bid": c.bid_pts, "ask": c.ask_pts,
            "delta": round(c.delta, 3), "chosen": chosen is not None and c.symbol == chosen.symbol}


def price(service: ExecService, sel: Selection) -> Priced:
    """Everything the form shows, from the live chain and the engine. Never
    raises: a fault is on ``.error`` in plain words, with whatever was
    priced before it."""
    out = Priced(selection=sel)
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
    # above), rounded up — the desk sent round(ask, 2) and the engine shows
    # ceil to 0.05; the service refuses either when it is off the grid. A
    # locked price (the padlock, st-2s4u) is the limit instead, whatever the
    # ask is now; the service's price band judges it when it is previewed.
    out.limit = sel.limit if sel.limit is not None else limit_at(c.ask_pts)
    budget = Budget(total_usd=sel.budget_usd, attempts=sel.attempts)
    try:
        out.ticket = compose([c], spx, budget, contract=c, lots=sel.lots,
                             expiration=sel.expiry.isoformat())
    except CannotFund as exc:
        out.error = f"FD0 could not fund a stop: {exc}"
        return out
    except ValueError as exc:
        out.error = f"FD0 could not derive a stop: {exc}"
        return out
    try:
        out.stop_price = protective_stop_price(out.limit, c.abs_delta, spx,
                                               out.ticket.stop_trigger_spx)
    except ValueError as exc:
        out.stop_note = f"no resting stop can be derived at this limit: {exc}"
    if sel.stop:
        _apply_stop_of_his_own(out, c, spx)
    return out


def _apply_stop_of_his_own(out: Priced, c: Contract, spx: float) -> None:
    """The stop box on the SEND screen, applied to a priced ticket. [st-m3bl]

    Steve, 2026-09-17: *"permit me to input a stop loss strike price in
    addition to the existing hard-coded dollar amount. just add an input on
    the SEND screen pre-populated with the dollar amount. over-riding that
    follows the same rule as updating - absent a decimal point means a
    strike price."*

    FD0 derives the stop as an SPX level from the budget; the intent carries
    that level and the service walks it into the resting price at the fill.
    A stop of his own keeps that shape. **Dollars** (a '.'): the price he
    typed becomes the resting stop, and its SPX level is the walk back from
    spot through the contract's delta at the limit — the inverse of
    ``protective_stop_price`` — so the intent still carries a level and the
    service rests his number when it fills at the limit with the mark where
    it was (a better fill or a moved mark re-walks from the level, which is
    the instrument). **A level** (no '.'): the level is the trigger as
    typed, and the resting price is the walk forward. Either way the
    ticket's cut, resting stop, net and *most this costs* follow it, and
    the derivation's distance, premium and risk are re-struck so the
    ceiling check at the service sees the stop he set.

    Refused in words on the ticket — SEND is then refused with the same
    words: a price off the tick grid, at or above the limit, or not
    positive; a level on the wrong side of spot for the right, or one that
    walks to a price nothing can rest at. Warned, not refused: a stop
    inside the noise floor (as FD0 warns for its own), and a stop that
    risks more than the attempt was funded for — the budget was his rule
    too, and this box is him overriding it knowingly."""
    sel = out.selection
    t = out.ticket
    if t is None or out.limit is None or not sel.stop:
        return
    try:
        kind, value = parse_leg_text(sel.stop, "stop")
    except ValueError as exc:
        out.error = f"your stop: {exc}"
        return
    right = c.right
    word = "call" if right == "CALL" else "put"
    delta = c.abs_delta
    d = t.derivation
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
        distance = (out.limit - stop_price) / delta
        level = spx - distance if right == "CALL" else spx + distance
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
        distance = abs(spx - level)
    premium = round(out.limit - stop_price, 2)
    risk = round(premium * CONTRACT_MULTIPLIER * sel.lots, 2)
    new_d = _dc.replace(d, stop_distance_spx=round(distance, 4), stop_premium_pts=premium,
                        attempt_risk_usd=risk)
    warnings = [w for w in t.warnings if not w.startswith("STOP INSIDE THE NOISE FLOOR")]
    if kind == "spx" and out.limit - distance * delta <= 0:
        # the same clamp FD0's own stop gets (stops.protective_stop_price):
        # a level that walks the option below nothing rests one tick above
        # it, and the SPX loop at his level is the stop that fires
        warnings.insert(0, f"SPX {level:g} WALKS THE OPTION BELOW ZERO — the resting stop is one "
                           f"tick, {stop_price:.2f}; the SPX loop at {level:g} is the stop")
    if new_d.inside_noise_floor:
        warnings.insert(0, f"STOP INSIDE THE NOISE FLOOR — {distance:.2f} SPX pts of room "
                           f"against a {d.noise_floor_spx:.2f} pt floor. The tape can take "
                           f"this out without the trade being wrong.")
    if risk > d.attempt_risk_usd + 0.005:
        warnings.insert(0, f"YOUR STOP RISKS ${risk:.2f} — this attempt was funded for "
                           f"${d.attempt_risk_usd:.2f}; the budget rule is overridden")
    level = round(level, 2)
    out.ticket = _dc.replace(
        t, stop_trigger_spx=level, derivation=new_d, warnings=tuple(warnings),
        template_fields=template_fields(c, t.limit_pts, level, t.lots))
    out.stop_price = stop_price
    out.stop_note = None
    out.stop_set_by = kind


def intent_for(priced: Priced, *, intent_id: str, engine_sha: str) -> dict[str, Any]:
    """The service's ``OrderIntent`` wire form for the priced ticket, checked
    against the service's own rules before it leaves the form."""
    if priced.contract is None or priced.ticket is None or priced.limit is None:
        raise ValueError(priced.error or "nothing is priced")
    if priced.error:
        # a ticket priced with a fault on it — a stop of his own that cannot
        # be one (st-m3bl) — is shown, never sent
        raise ValueError(priced.error)
    d = {
        "intent_id": intent_id, "symbol": priced.contract.symbol, "side": "BUY_TO_OPEN",
        "qty": priced.lots, "order_type": "LIMIT", "limit": priced.limit,
        "stop_spx": float(priced.ticket.stop_trigger_spx),
        "delta": round(priced.contract.abs_delta, 4),
        "source": SOURCE, "engine_sha": engine_sha,
    }
    OrderIntent.from_dict(d).validated()
    return d


def stamp(now: datetime) -> str:
    return now.astimezone(CT).strftime("%Y%m%dT%H%M%S")
