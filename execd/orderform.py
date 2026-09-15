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
4. PREVIEW → ``service.preview`` (the rules, then Schwab's own cost line) and
   a single-use 60 s token; SEND with that token → ``service.place`` of the
   same intent under the same id, ``page-<stamp>``, source ``page``.
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
from .compose import Budget, CannotFund, Contract, Ticket, compose, parse_chain
from .intent import OrderIntent
from .service import ExecService
from .stops import _round_up_to_tick, protective_stop_price, tick_for

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
#: A preview's send token lives this long, single use.
PREVIEW_TTL_S = 60.0
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
        return cls(side=side, expiry=expiry,
                   strike=strike if strike and strike > 0 else None,
                   delta=abs(delta) if delta is not None else None, lots=lots,
                   budget_usd=budget if budget and budget > 0 else DEFAULT_BUDGET_USD,
                   attempts=max(1, attempts))

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
        }
        d.update(override)
        return {k: str(v) for k, v in d.items() if v is not None}


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
    # ceil to 0.05; the service refuses either when it is off the grid.
    out.limit = _round_up_to_tick(c.ask_pts, tick_for(c.ask_pts))
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
    return out


def intent_for(priced: Priced, *, intent_id: str, engine_sha: str) -> dict[str, Any]:
    """The service's ``OrderIntent`` wire form for the priced ticket, checked
    against the service's own rules before it leaves the form."""
    if priced.contract is None or priced.ticket is None or priced.limit is None:
        raise ValueError(priced.error or "nothing is priced")
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
