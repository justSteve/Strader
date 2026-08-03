"""FD0 composition — pick the strike, price it, derive the stop from budget.

Design: ``docs/superpowers/specs/2026-08-02-fd0-flushdown-design.md``.
Bead: Cut And Await (st-apzt), child of Coded Counter Wisdom (st-ug5).

This module is pure. It takes a chain snapshot and a budget and returns a
:class:`Ticket`; it opens no sockets, reads no credentials, and transmits no
orders. The order-transmission wall is st-5ey's job and is not breached here —
FD0 renders a string for Steve to paste, and nothing more.

**Units are the sharp edge in this file**, so every name carries them:

===================  ==========================================================
``*_pts``            option premium in points. 1 point = $100 on one contract.
``*_usd``            dollars.
``*_spx``            distance or level on the SPX index, in index points.
``delta``            as the chain reports it — **negative for puts**. Every
                     calculation uses ``abs()``; the sign is preserved on the
                     contract only so a mis-parsed chain is visible.
===================  ==========================================================

The budget engine is the heart, and it runs backwards from the money rather
than forwards from a chart: the stop distance is whatever the remaining risk
budget can fund at the live delta. It is never a fixed number of points. Steve
set that explicitly on 08-02 — his 0.60δ two-point sketch priced out at roughly
3.6× the $100 ceiling, which is how the derivation ended up inverted.
"""
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Iterable, Literal, Sequence

log = logging.getLogger(__name__)

__all__ = [
    "Contract", "Budget", "Derivation", "Ticket",
    "parse_chain", "pick_strike", "derive", "noise_floor_spx", "compose",
    "NoStrikeInBand", "CannotFund",
    "CONTRACT_MULTIPLIER", "DELTA_TARGET", "DELTA_BAND", "FEES_RT_USD",
]

# One SPX option contract controls 100× the premium in dollars.
CONTRACT_MULTIPLIER = 100

DELTA_TARGET = 0.30
DELTA_BAND = (0.25, 0.35)

# Round-turn commission + fees, one contract. Conservative; the ticket prints
# it so a wrong assumption is visible rather than buried in the stop distance.
FEES_RT_USD = 3.0

# SPX options quote in nickels.
PREMIUM_TICK_PTS = 0.05


class NoStrikeInBand(Exception):
    """No contract sits inside the delta band. Compose refuses rather than
    reaching for the nearest strike outside it — a 0.5δ put doubles the dollar
    risk per SPX point and silently breaks the budget derivation."""


class CannotFund(Exception):
    """The remaining budget cannot fund another attempt once friction is paid.
    Carries the arithmetic so the refusal is auditable, per the design."""


# ---------------------------------------------------------------- inputs ---

@dataclass(frozen=True)
class Contract:
    """One option line from the chain, normalized."""

    symbol: str
    strike: float
    bid_pts: float
    ask_pts: float
    delta: float                    # signed, as the chain reports it
    expiration: str                 # ISO date, e.g. "2026-08-03"
    dte: int

    @property
    def mid_pts(self) -> float:
        return (self.bid_pts + self.ask_pts) / 2

    @property
    def spread_pts(self) -> float:
        return self.ask_pts - self.bid_pts

    @property
    def spread_usd(self) -> float:
        return self.spread_pts * CONTRACT_MULTIPLIER

    @property
    def abs_delta(self) -> float:
        return abs(self.delta)


@dataclass(frozen=True)
class Budget:
    """The hard ceiling. ``total_usd`` is realized loss, not notional."""

    total_usd: float = 100.0
    attempts: int = 2
    spent_usd: float = 0.0
    attempts_used: int = 0

    @property
    def remaining_usd(self) -> float:
        return self.total_usd - self.spent_usd

    @property
    def attempts_left(self) -> int:
        return self.attempts - self.attempts_used

    def debit(self, realized_loss_usd: float) -> "Budget":
        """Book a closed attempt. Returns a new Budget — the ledger is a value,
        so a mis-sequenced update cannot corrupt the running one in place."""
        if realized_loss_usd < 0:
            log.info("attempt closed for a gain of $%.2f — budget not debited",
                     -realized_loss_usd)
            realized_loss_usd = 0.0
        return Budget(
            total_usd=self.total_usd,
            attempts=self.attempts,
            spent_usd=self.spent_usd + realized_loss_usd,
            attempts_used=self.attempts_used + 1,
        )


# ---------------------------------------------------------------- output ---

@dataclass(frozen=True)
class Derivation:
    """Every number between the budget and the stop, in order, so the ticket
    can be audited at a glance and the journal can replay the reasoning."""

    budget_remaining_usd: float
    attempts_left: int
    spread_usd: float
    fees_rt_usd: float
    friction_usd: float
    attempt_risk_usd: float
    stop_premium_pts: float
    delta_live: float
    stop_distance_spx: float
    noise_floor_spx: float

    @property
    def inside_noise_floor(self) -> bool:
        return self.stop_distance_spx < self.noise_floor_spx

    def as_record(self) -> dict:
        d = asdict(self)
        d["inside_noise_floor"] = self.inside_noise_floor
        return d


@dataclass(frozen=True)
class Ticket:
    """What Steve reads, pastes, and sends. Nothing here is transmitted."""

    contract: Contract
    limit_pts: float
    spx_at_compose: float
    stop_trigger_spx: float
    derivation: Derivation
    order_string: str
    template_fields: dict
    warnings: tuple[str, ...] = ()
    composed_at: datetime | None = None

    @property
    def max_loss_usd(self) -> float:
        """What this attempt costs if the stop fills at the trigger, including
        the friction already assumed. This is the number the ceiling governs."""
        return self.derivation.attempt_risk_usd + self.derivation.friction_usd

    def as_record(self) -> dict:
        return {
            "symbol": self.contract.symbol,
            "strike": self.contract.strike,
            "delta": self.contract.delta,
            "limit_pts": self.limit_pts,
            "spx_at_compose": self.spx_at_compose,
            "stop_trigger_spx": self.stop_trigger_spx,
            "max_loss_usd": round(self.max_loss_usd, 2),
            "order_string": self.order_string,
            "warnings": list(self.warnings),
            "derivation": self.derivation.as_record(),
            "composed_at": self.composed_at.isoformat() if self.composed_at else None,
        }


# ----------------------------------------------------------------- chain ---

def parse_chain(data: dict, *, expiration: str | None = None) -> list[Contract]:
    """Normalize a Schwab chain payload into put :class:`Contract` s.

    ``expiration`` selects one expiry (ISO date); omitted, the nearest is used
    — FD0 is a 0DTE tool and the front expiry is the intent. Contracts missing
    a delta or a two-sided market are dropped, not defaulted: a strike we
    cannot price is a strike we must not pick.
    """
    exp_map = data.get("putExpDateMap") or {}
    if not exp_map:
        return []

    # Keys look like "2026-08-03:0" — date, then DTE.
    def _key_date(key: str) -> str:
        return key.split(":")[0]

    if expiration is not None:
        keys = [k for k in exp_map if _key_date(k) == expiration]
        if not keys:
            log.warning("no put expiry %s in chain; have %s",
                        expiration, sorted(_key_date(k) for k in exp_map))
            return []
    else:
        keys = [min(exp_map, key=lambda k: (_key_date(k), k))]

    out: list[Contract] = []
    for key in keys:
        for strike_str, lines in exp_map[key].items():
            for line in lines:
                delta = line.get("delta")
                bid = line.get("bid")
                ask = line.get("ask")
                if delta is None or bid is None or ask is None:
                    continue
                # Schwab sends a sentinel delta on illiquid or expired lines.
                if abs(delta) > 1.0 or ask <= 0 or ask < bid:
                    log.debug("dropping %s: delta=%s bid=%s ask=%s",
                              line.get("symbol"), delta, bid, ask)
                    continue
                out.append(Contract(
                    symbol=line.get("symbol", f"?{strike_str}"),
                    strike=float(line.get("strikePrice", strike_str)),
                    bid_pts=float(bid),
                    ask_pts=float(ask),
                    delta=float(delta),
                    expiration=_key_date(key),
                    dte=int(line.get("daysToExpiration", 0)),
                ))
    return out


def pick_strike(
    contracts: Iterable[Contract],
    *,
    target: float = DELTA_TARGET,
    band: tuple[float, float] = DELTA_BAND,
) -> Contract:
    """The contract whose |delta| is nearest ``target`` **within** ``band``.

    Ties break to the tighter spread — at equal delta, the cheaper crossing is
    strictly better, and it is the spread that eats the attempt budget.
    """
    lo, hi = band
    eligible = [c for c in contracts if lo <= c.abs_delta <= hi]
    if not eligible:
        seen = sorted({round(c.abs_delta, 3) for c in contracts})
        raise NoStrikeInBand(
            f"no put with |delta| in [{lo}, {hi}]; chain offers {seen or 'nothing'}"
        )
    return min(eligible, key=lambda c: (abs(c.abs_delta - target), c.spread_pts))


# ---------------------------------------------------------------- engine ---

def noise_floor_spx(
    spread_pts: float,
    delta_live: float,
    recent_minute_ranges_spx: Sequence[float] = (),
) -> float:
    """How far SPX moves on nothing.

    ``max(spread/delta, median 1-minute high-low over the last 15 minutes)``,
    per the design. The first term says a stop cannot be tighter than the cost
    of crossing; the second says it cannot be tighter than the tape's own
    fidget. A stop inside this is a stop the noise takes out.

    With no recent bars the median term is skipped and only the spread term
    applies — the caller is told, because a floor computed from half its inputs
    is a weaker guarantee than it looks.
    """
    delta_live = abs(delta_live)
    if delta_live <= 0:
        raise ValueError("delta_live must be non-zero to convert premium to SPX points")

    spread_term = spread_pts / delta_live
    if not recent_minute_ranges_spx:
        log.warning("noise floor computed from spread alone — no recent 1-min ranges")
        return spread_term
    return max(spread_term, statistics.median(recent_minute_ranges_spx))


def derive(
    budget: Budget,
    contract: Contract,
    *,
    recent_minute_ranges_spx: Sequence[float] = (),
    fees_rt_usd: float = FEES_RT_USD,
) -> Derivation:
    """Run the budget backwards into a stop distance.

        friction   = spread + fees
        attempt    = remaining / attempts_left − friction
        premium    = attempt / 100
        distance   = premium / delta

    Raises :class:`CannotFund` when friction alone exhausts the slice. That is
    a refusal with arithmetic attached, not a crash — the design requires the
    numbers be printed so the refusal can be argued with.
    """
    if budget.attempts_left <= 0:
        raise CannotFund(
            f"no attempts left: {budget.attempts_used} of {budget.attempts} used"
        )

    friction_usd = contract.spread_usd + fees_rt_usd
    slice_usd = budget.remaining_usd / budget.attempts_left
    attempt_risk_usd = slice_usd - friction_usd

    if attempt_risk_usd <= 0:
        raise CannotFund(
            f"${budget.remaining_usd:.2f} remaining / {budget.attempts_left} "
            f"attempt(s) = ${slice_usd:.2f} per attempt, but friction is "
            f"${friction_usd:.2f} (${contract.spread_usd:.2f} spread + "
            f"${fees_rt_usd:.2f} fees). Nothing left to risk."
        )

    stop_premium_pts = attempt_risk_usd / CONTRACT_MULTIPLIER
    stop_distance_spx = stop_premium_pts / contract.abs_delta

    return Derivation(
        budget_remaining_usd=budget.remaining_usd,
        attempts_left=budget.attempts_left,
        spread_usd=contract.spread_usd,
        fees_rt_usd=fees_rt_usd,
        friction_usd=friction_usd,
        attempt_risk_usd=attempt_risk_usd,
        stop_premium_pts=stop_premium_pts,
        delta_live=contract.abs_delta,
        stop_distance_spx=stop_distance_spx,
        noise_floor_spx=noise_floor_spx(
            contract.spread_pts, contract.abs_delta, recent_minute_ranges_spx
        ),
    )


# -------------------------------------------------------------- rendering ---

_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def _tos_expiry(expiration: str) -> str:
    """TOS paste grammar wants ``3 AUG 26`` — day unpadded, month, 2-digit year."""
    d = datetime.fromisoformat(expiration)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year % 100:02d}"


def _round_limit_up(pts: float, tick: float = PREMIUM_TICK_PTS) -> float:
    """Round a BUY limit **up** to the next tick.

    Not to-nearest, and deliberately not bare ``round``: that is banker's
    rounding, so a 1.525 mid lands on 1.50 — a limit *below* where the book
    was, i.e. a miss. On a flush entry a miss costs the whole trade, while
    rounding up costs at most one tick ($5 on one contract) against an $18
    friction assumption. The asymmetry is not close.
    """
    return round(math.ceil(round(pts / tick, 6)) * tick, 2)


def order_string(contract: Contract, limit_pts: float) -> str:
    """The validated entry-leg spine from the design (survey §2.1).

    The conditional exit is deliberately absent: whether the paste grammar can
    carry an SPX-underlying condition is exactly the open question on Steve's
    TOS validation card. Until he answers, the exit is rendered as separate
    fields rather than guessed into this string.
    """
    return (
        f"BUY +1 SPX 100 (Weeklys) {_tos_expiry(contract.expiration)} "
        f"{contract.strike:g} PUT @{limit_pts:.2f} LMT"
    )


def template_fields(contract: Contract, limit_pts: float, stop_trigger_spx: float) -> dict:
    """The two-number overwrite for the saved-template fallback: load ``FD0``,
    replace strike and condition price, send."""
    return {
        "strike": contract.strike,
        "limit_pts": round(limit_pts, 2),
        "condition_spx": round(stop_trigger_spx, 2),
        "expiry": _tos_expiry(contract.expiration),
        "exit": "SELL -1, MARKET on trigger",
    }


# --------------------------------------------------------------- compose ---

def compose(
    chain: dict | Sequence[Contract],
    spx_now: float,
    budget: Budget,
    *,
    expiration: str | None = None,
    recent_minute_ranges_spx: Sequence[float] = (),
    limit_mode: Literal["ask", "mid"] = "ask",
    fees_rt_usd: float = FEES_RT_USD,
    now: datetime | None = None,
) -> Ticket:
    """Build one ticket. Raises :class:`NoStrikeInBand` or :class:`CannotFund`.

    ``limit_mode`` defaults to ``ask`` — a marketable limit. This is consistent
    with the budget engine, which already charges the *full* spread as friction
    (half on the way in, half on the way out). Bidding mid would understate the
    risk the engine just priced, and a miss on a flush costs more than a nickel.
    """
    contracts = parse_chain(chain, expiration=expiration) if isinstance(chain, dict) else list(chain)
    contract = pick_strike(contracts)

    derivation = derive(
        budget, contract,
        recent_minute_ranges_spx=recent_minute_ranges_spx,
        fees_rt_usd=fees_rt_usd,
    )

    raw_limit = contract.ask_pts if limit_mode == "ask" else contract.mid_pts
    limit_pts = _round_limit_up(raw_limit)

    # Long put: the loss case is SPX rallying away from the strike.
    stop_trigger_spx = spx_now + derivation.stop_distance_spx

    warnings: list[str] = []
    if derivation.inside_noise_floor:
        warnings.append(
            f"STOP INSIDE THE NOISE FLOOR — {derivation.stop_distance_spx:.2f} SPX pts "
            f"of room against a {derivation.noise_floor_spx:.2f} pt floor. "
            f"The tape can take this out without the trade being wrong."
        )
    if not recent_minute_ranges_spx:
        warnings.append(
            "Noise floor used the spread only — no recent 1-minute ranges supplied."
        )

    ticket = Ticket(
        contract=contract,
        limit_pts=limit_pts,
        spx_at_compose=spx_now,
        stop_trigger_spx=stop_trigger_spx,
        derivation=derivation,
        order_string=order_string(contract, limit_pts),
        template_fields=template_fields(contract, limit_pts, stop_trigger_spx),
        warnings=tuple(warnings),
        composed_at=now,
    )

    for w in warnings:
        log.warning("compose: %s", w)
    return ticket
