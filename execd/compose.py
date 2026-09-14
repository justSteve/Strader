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

2026-08-23, the join with the intent dialect (st-79z.3): the engine now takes
the contract the dialect chose (``compose(..., contract=)``) instead of always
picking by delta band, carries the contract's ``right`` so a long call's stop
sits *below* spot, and scales friction and premium by ``lots``. Flush-down on
one put is still the default and the only thing the delta-band pick returns.
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
    "order_string", "exit_fields", "template_fields", "stop_trigger",
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


def _usd(x: float) -> str:
    """Money, for operator-facing text.

    Snaps sub-cent magnitudes to zero. A ledger that has been drawn exactly to
    its ceiling lands on float noise like -7.1e-15, which prints as "$-0.00" —
    and a refusal that shows the operator negative zero looks like a bug in the
    arithmetic it exists to justify.
    """
    return f"${0.0 if abs(x) < 0.005 else x:.2f}"


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
    right: str = "PUT"              # PUT (FD0's own shape) or CALL (via the dialect)

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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Contract":
        return cls(symbol=d["symbol"], strike=float(d["strike"]), bid_pts=float(d["bid_pts"]),
                   ask_pts=float(d["ask_pts"]), delta=float(d["delta"]),
                   expiration=d["expiration"], dte=int(d.get("dte", 0)),
                   right=d.get("right", "PUT"))


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
    can be audited at a glance and the journal can replay the reasoning.
    Spread, fees and premium are for all ``lots`` together."""

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
    lots: int = 1

    @property
    def inside_noise_floor(self) -> bool:
        return self.stop_distance_spx < self.noise_floor_spx

    def as_record(self) -> dict:
        d = asdict(self)
        d["inside_noise_floor"] = self.inside_noise_floor
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Derivation":
        names = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in names})


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
    lots: int = 1

    @property
    def right(self) -> str:
        return self.contract.right

    @property
    def max_loss_usd(self) -> float:
        """What this attempt costs if the stop fills at the trigger, including
        the friction already assumed. This is the number the ceiling governs."""
        return self.derivation.attempt_risk_usd + self.derivation.friction_usd

    @property
    def exit_fields(self) -> dict:
        return exit_fields(self.stop_trigger_spx, right=self.right, lots=self.lots)

    def as_record(self) -> dict:
        """The journal's summary of a ticket."""
        return {
            "symbol": self.contract.symbol,
            "strike": self.contract.strike,
            "right": self.right,
            "lots": self.lots,
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

    def to_dict(self) -> dict:
        """Everything, so the ticket survives a process boundary — the dictation
        pane runs one line per process, and ``in <px>`` has to find what ``go``
        composed."""
        return {
            "contract": self.contract.to_dict(),
            "limit_pts": self.limit_pts,
            "spx_at_compose": self.spx_at_compose,
            "stop_trigger_spx": self.stop_trigger_spx,
            "derivation": asdict(self.derivation),
            "order_string": self.order_string,
            "template_fields": dict(self.template_fields),
            "warnings": list(self.warnings),
            "composed_at": self.composed_at.isoformat() if self.composed_at else None,
            "lots": self.lots,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Ticket":
        return cls(
            contract=Contract.from_dict(d["contract"]),
            limit_pts=float(d["limit_pts"]),
            spx_at_compose=float(d["spx_at_compose"]),
            stop_trigger_spx=float(d["stop_trigger_spx"]),
            derivation=Derivation.from_dict(d["derivation"]),
            order_string=d["order_string"],
            template_fields=dict(d.get("template_fields", {})),
            warnings=tuple(d.get("warnings", ())),
            composed_at=datetime.fromisoformat(d["composed_at"]) if d.get("composed_at") else None,
            lots=int(d.get("lots", 1)),
        )


# ----------------------------------------------------------------- chain ---

def parse_chain(data: dict, *, expiration: str | None = None,
                right: str = "PUT") -> list[Contract]:
    """Normalize a Schwab chain payload into :class:`Contract` s of one right.

    ``expiration`` selects one expiry (ISO date); omitted, the nearest is used
    — FD0 is a 0DTE tool and the front expiry is the intent. Contracts missing
    a delta or a two-sided market are dropped, not defaulted: a strike we
    cannot price is a strike we must not pick. ``right`` is PUT (FD0's own
    shape) or CALL (the dialect's long calls); the two maps are never mixed.
    """
    right = right.upper()
    if right not in ("PUT", "CALL"):
        raise ValueError(f"right must be PUT or CALL, not {right!r}")
    exp_map = data.get("putExpDateMap" if right == "PUT" else "callExpDateMap") or {}
    if not exp_map:
        return []

    # Keys look like "2026-08-03:0" — date, then DTE.
    def _key_date(key: str) -> str:
        return key.split(":")[0]

    if expiration is not None:
        keys = [k for k in exp_map if _key_date(k) == expiration]
        if not keys:
            log.warning("no %s expiry %s in chain; have %s",
                        right.lower(), expiration, sorted(_key_date(k) for k in exp_map))
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
                    right=right,
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
    lots: int = 1,
) -> Derivation:
    """Run the budget backwards into a stop distance.

        friction   = (spread + fees) × lots
        attempt    = remaining / attempts_left − friction
        premium    = attempt / (100 × lots)
        distance   = premium / delta

    Raises :class:`CannotFund` when friction alone exhausts the slice. That is
    a refusal with arithmetic attached, not a crash — the design requires the
    numbers be printed so the refusal can be argued with.
    """
    if lots < 1:
        raise ValueError(f"lots must be at least 1, not {lots}")
    if contract.abs_delta <= 0:
        raise ValueError(f"{contract.strike:g} {contract.right} has no delta in the "
                         f"snapshot — cannot turn premium into SPX points")
    if budget.attempts_left <= 0:
        raise CannotFund(
            f"no attempts left: {budget.attempts_used} of {budget.attempts} used"
        )

    spread_usd = contract.spread_usd * lots
    fees_usd = fees_rt_usd * lots
    friction_usd = spread_usd + fees_usd
    slice_usd = budget.remaining_usd / budget.attempts_left
    attempt_risk_usd = slice_usd - friction_usd

    if attempt_risk_usd <= 0:
        raise CannotFund(
            f"{_usd(budget.remaining_usd)} remaining / {budget.attempts_left} "
            f"attempt(s) = {_usd(slice_usd)} per attempt, but friction is "
            f"{_usd(friction_usd)} ({_usd(spread_usd)} spread + "
            f"{_usd(fees_usd)} fees{f' for {lots} lots' if lots > 1 else ''}). "
            f"Nothing left to risk."
        )

    stop_premium_pts = attempt_risk_usd / (CONTRACT_MULTIPLIER * lots)
    stop_distance_spx = stop_premium_pts / contract.abs_delta

    return Derivation(
        budget_remaining_usd=budget.remaining_usd,
        attempts_left=budget.attempts_left,
        spread_usd=spread_usd,
        fees_rt_usd=fees_usd,
        friction_usd=friction_usd,
        attempt_risk_usd=attempt_risk_usd,
        stop_premium_pts=stop_premium_pts,
        delta_live=contract.abs_delta,
        stop_distance_spx=stop_distance_spx,
        noise_floor_spx=noise_floor_spx(
            contract.spread_pts, contract.abs_delta, recent_minute_ranges_spx
        ),
        lots=lots,
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


def order_string(contract: Contract, limit_pts: float, lots: int = 1) -> str:
    """The entry leg, in thinkorswim's documented paste-from-clipboard grammar.

    Shape confirmed against TOS documentation (researched 08-03, design §"What
    the platform actually does"): action · signed qty · underlying · multiplier
    · expiry · strike · CALL/PUT · ``@``price · order type.

    **Returns the bare string and nothing else** — no indent, no trailing
    newline, no surrounding furniture. TOS's paste breaks on stray whitespace
    or extra text, and this value goes to the clipboard verbatim.

    The conditional exit is absent because the paste grammar cannot express one
    — that is a property of the platform, not an open question. The exit is
    built once in the UI via the Order Rules gear; see :func:`exit_fields` for
    the values that go into it.
    """
    return (
        f"BUY +{lots} SPX 100 (Weeklys) {_tos_expiry(contract.expiration)} "
        f"{contract.strike:g} {contract.right} @{limit_pts:.2f} LMT"
    )


# The condition triggers on the cash index, not the option and not the future.
# The stop distance is derived in SPX index points, so the trigger must watch
# the same instrument the arithmetic is denominated in.
CONDITION_SYMBOL = "SPX"


def stop_trigger(spx_now: float, stop_distance_spx: float, right: str = "PUT") -> float:
    """Where the cut sits. A long put loses as SPX rallies, so the trigger is
    above spot; a long call loses as SPX falls, so it is below. Same distance
    either way — the budget engine is direction-blind; the sign is not."""
    r = right.upper()
    if r == "PUT":
        return spx_now + stop_distance_spx
    if r == "CALL":
        return spx_now - stop_distance_spx
    raise ValueError(f"right must be PUT or CALL, not {right!r}")


def exit_fields(stop_trigger_spx: float, right: str = "PUT", lots: int = 1) -> dict:
    """The values Steve types into the TOS Order Rules condition.

    TOS conditions can trigger on a symbol other than the one being traded —
    documented, and the reason the SPX-conditional stop is buildable at all.
    But they live in the UI, so this is a short list of numbers to enter rather
    than anything pasteable.

    ``attach_to`` leads because it is the thing that goes wrong silently. A TOS
    condition gates order *submission*, and the Order Rules gear belongs to the
    row you clicked. Hung on the entry it would gate when you BUY — the opposite
    of a stop. It belongs on the SELL leg of a 1st Triggers pair, which comes
    into existence when the entry fills and then waits for SPX.

    ``method`` is ``mark``: a number compared to a number. The live Method list
    is bid / ask / mark / vol index / front vol / back vol / vol diff / study —
    there is no ``last``. ``study`` is thinkScript and is the one a saved order
    degrades, keeping the study's name but not its script, so nothing here is
    ever script-shaped.

    ``trigger_direction`` follows the right: a put is cut when SPX is at or
    above the trigger, a call when it is at or below.
    """
    r = right.upper()
    if r not in ("PUT", "CALL"):
        raise ValueError(f"right must be PUT or CALL, not {right!r}")
    return {
        "attach_to": "the SELL leg of a 1st Triggers order — never the entry",
        "trigger_symbol": CONDITION_SYMBOL,
        "method": "mark",
        "trigger_direction": "at or above" if r == "PUT" else "at or below",
        "trigger_price": round(stop_trigger_spx, 2),
        "action": f"SELL -{lots}, MARKET",
    }


def template_fields(contract: Contract, limit_pts: float, stop_trigger_spx: float,
                    lots: int = 1) -> dict:
    """Everything the operator retypes when reloading a saved ``FD0`` template."""
    return {
        "strike": contract.strike,
        "right": contract.right,
        "limit_pts": round(limit_pts, 2),
        "condition_spx": round(stop_trigger_spx, 2),
        "expiry": _tos_expiry(contract.expiration),
        "exit": f"SELL -{lots}, MARKET on trigger",
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
    contract: Contract | None = None,
    lots: int = 1,
) -> Ticket:
    """Build one ticket. Raises :class:`NoStrikeInBand` or :class:`CannotFund`.

    ``limit_mode`` defaults to ``ask`` — a marketable limit. This is consistent
    with the budget engine, which already charges the *full* spread as friction
    (half on the way in, half on the way out). Bidding mid would understate the
    risk the engine just priced, and a miss on a flush costs more than a nickel.

    ``contract`` is the strike the caller already chose — the intent dialect's
    ``price`` resolves one from what Steve said, and the desk must not overrule
    him with the delta-band pick. Given, the chain is not consulted; omitted,
    the put nearest the delta target inside the band is picked, which is FD0's
    own flush-down shape.
    """
    if contract is None:
        contracts = (parse_chain(chain, expiration=expiration) if isinstance(chain, dict)
                     else list(chain))
        contract = pick_strike(contracts)

    derivation = derive(
        budget, contract,
        recent_minute_ranges_spx=recent_minute_ranges_spx,
        fees_rt_usd=fees_rt_usd,
        lots=lots,
    )

    raw_limit = contract.ask_pts if limit_mode == "ask" else contract.mid_pts
    limit_pts = _round_limit_up(raw_limit)

    # Long put: the loss case is SPX rallying away from the strike. A long
    # call is the mirror; stop_trigger carries the sign.
    stop_trigger_spx = stop_trigger(spx_now, derivation.stop_distance_spx, contract.right)

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
        order_string=order_string(contract, limit_pts, lots),
        template_fields=template_fields(contract, limit_pts, stop_trigger_spx, lots),
        warnings=tuple(warnings),
        composed_at=now,
        lots=lots,
    )

    for w in warnings:
        log.warning("compose: %s", w)
    return ticket
