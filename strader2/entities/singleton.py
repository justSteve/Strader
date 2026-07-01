"""The singleton — a 0DTE long single-leg option traded as a futures proxy.

*"A single is a futures contract on its last day."* We go long a **call**
(bullish) or a **put** (bearish) to capture a brief directional move — Carmine's
8-15pt-in-<15min thesis — and we manage it on **delta, not theta**. This is
Strader2's first strategy entity (plan co-r10h, scope st-nd5). It mirrors the
frozen-dataclass conventions in ``market/entities`` and reuses ``Contract`` and
``Level`` rather than redefining them.

Two entities:
  - ``SingletonSetup``  — the trade *idea*: a directional bias justified by a
    Carmine trigger at a reference level (optionally in Mancini confluence).
  - ``SingletonPosition`` — an *entered* single-leg long option, exposing the
    futures-proxy lenses (delta exposure, R-multiple, distance-to-target).

Data only. It represents and measures a singleton; it does not recognize setups
or route orders (that is Phase 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from market.entities.instrument import Contract
from market.entities.level import Level

Bias = Literal["bullish", "bearish"]
Right = Literal["CALL", "PUT"]

# Carmine's setup taxonomy — the trigger that justifies taking the direction.
# These are *recognized from the datafeed* (volume profile / order flow), not
# ingested as posted alerts (plan co-r10h §6.2).
CarmineSetup = Literal[
    "failed_breakdown",  # big low flush, trap, recover — Carmine's core edge
    "level_reclaim",     # sweep then reclaim of a lost level
    "return_to_lvn",     # price returns to a ripped-through low-volume node
    "range_trap",        # trap at a range boundary, then reverse
]


@dataclass(frozen=True)
class SingletonSetup:
    """The trade idea, before entry.

    A directional ``bias`` justified by a Carmine ``trigger`` firing at an
    ``anchor`` level. ``mancini_confluence`` marks the highest-conviction case:
    the Carmine zone coincides with a Mancini level at one price.
    """

    bias: Bias
    trigger: CarmineSetup
    anchor: Level
    mancini_confluence: bool = False

    @property
    def right(self) -> Right:
        """We only go long — a call expresses bullish, a put expresses bearish."""
        return "CALL" if self.bias == "bullish" else "PUT"


@dataclass(frozen=True)
class SingletonPosition:
    """An entered single-leg long option, framed as a futures proxy.

    Prices are underlying (ES/SPX) points; ``target``/``stop`` are underlying
    levels, consistent with managing the trade as directional exposure. Premiums
    (``entry_price``/``current_value``) are per-contract option prices.
    """

    contract: Contract          # the single option leg
    setup: SingletonSetup       # what triggered the entry
    entry_price: float          # premium paid per contract (debit)
    quantity: int
    entry_time: datetime        # timezone-aware, US/Central
    underlying_at_entry: float  # ES/SPX spot at entry — the proxy reference
    underlying_now: float       # current ES/SPX spot
    target: float               # underlying price target (points-based exit)
    stop: float                 # underlying price stop
    current_value: float        # current option premium (mid)

    def __post_init__(self) -> None:
        if self.contract.contract_type != self.setup.right:
            raise ValueError(
                f"{self.setup.bias} setup needs a {self.setup.right} leg, "
                f"got {self.contract.contract_type}"
            )
        if self.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {self.quantity}")

    # ── directional identity ────────────────────────────────────────────────
    @property
    def is_bullish(self) -> bool:
        return self.setup.bias == "bullish"

    # ── futures-proxy lenses (delta is the litmus, not theta) ────────────────
    @property
    def net_delta(self) -> float:
        """Signed position delta. Long call > 0, long put < 0 (the contract's
        delta already carries the sign)."""
        return self.contract.delta * self.quantity

    @property
    def delta_exposure(self) -> float:
        """Dollar P&L per 1.0 point of underlying move — the 'futures size' the
        singleton is standing in for: ``|delta| * 100 * qty``."""
        return abs(self.contract.delta) * 100.0 * self.quantity

    # ── P&L and risk (a long option's max loss is defined = premium) ─────────
    @property
    def unrealized_pnl(self) -> float:
        return (self.current_value - self.entry_price) * self.quantity * 100.0

    @property
    def max_loss(self) -> float:
        return self.entry_price * self.quantity * 100.0

    @property
    def r_multiple(self) -> float:
        """Unrealized P&L in units of risk (premium at stake)."""
        risk = self.max_loss
        return self.unrealized_pnl / risk if risk else 0.0

    # ── distance to exits, signed by direction ───────────────────────────────
    @property
    def pts_to_target(self) -> float:
        """Underlying points still to travel to the target (>= 0 until hit)."""
        if self.is_bullish:
            return self.target - self.underlying_now
        return self.underlying_now - self.target

    @property
    def pts_to_stop(self) -> float:
        """Underlying points of cushion before the stop (>= 0 until breached)."""
        if self.is_bullish:
            return self.underlying_now - self.stop
        return self.stop - self.underlying_now

    @property
    def at_target(self) -> bool:
        return self.pts_to_target <= 0

    @property
    def at_stop(self) -> bool:
        return self.pts_to_stop <= 0
