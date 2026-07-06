"""Orderflow signals — interpretations emitted by the orderflow engine.

Design spec §6 (docs/superpowers/specs/2026-07-03-orderflow-signal-layer-design.md).
These extend the frozen ``Signal`` hierarchy in ``market/signals/types.py`` —
data artifacts (FootprintBar) live in ``market/entities``; interpretations
live here. Arrives bead-by-bead: SweepPrint + DeltaDivergence (st-wnc);
ImbalanceStack (st-su4), AbsorptionRead + SetupRecognition (st-2kf) follow
under their own beads.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from market.signals.types import Signal


@dataclass(frozen=True)
class SweepPrint(Signal):
    """One aggressor walked through multiple price levels near-instantly —
    urgency: immediacy mattered more than price. Emitted when the run ends."""

    direction: Literal["buy", "sell"] = "buy"
    start_price: float = 0.0
    end_price: float = 0.0
    ticks_swept: int = 0
    total_size: int = 0


@dataclass(frozen=True)
class DeltaDivergence(Signal):
    """Price made a more extreme swing point than the prior one, but CVD did
    not confirm — the move ran on weaker aggression (effect without force).
    Emitted when the swing pivot confirms (price retraces PIVOT_FILTER_TICKS)."""

    kind: Literal["bullish", "bearish"] = "bullish"
    price_extreme: float = 0.0
    prior_extreme: float = 0.0
    cvd_at_extreme: int = 0
    cvd_at_prior: int = 0


@dataclass(frozen=True)
class ImbalanceStack(Signal):
    """STACK_MIN+ consecutive prices in one bar where one aggressor side
    diagonally dominated (research doc Q1.3) — an institutional footprint,
    often defended on retests. Emitted per stack when the bar completes."""

    direction: Literal["buy", "sell"] = "buy"
    prices: tuple[float, ...] = ()   # ascending, one per stacked level
    ratios: tuple[float, ...] = ()   # dominant/opposite per level (opposite floored at 1)


@dataclass(frozen=True)
class SetupRecognition(Signal):
    """A Carmine setup forming / confirmed / invalidated at a level (spec §3,
    §6). Score-don't-gate: partial recognitions surface as ``forming`` with
    the beats that fired; ``confirmed`` carries everything SingletonSetup
    needs. The four beats: flush (aggression past the level), stall (failed
    acceptance), flip (delta turns), confirm (reversal re-takes the level)."""

    setup: str = "failed_breakdown"            # CarmineSetup literal
    bias: Literal["bullish", "bearish"] = "bullish"
    anchor_price: float = 0.0
    anchor_kind: str = "support"               # support|resistance|range_high|range_low|lvn
    state: Literal["forming", "confirmed", "invalidated"] = "forming"
    beats: tuple[str, ...] = ()                # subset of (flush, stall, flip, confirm)
    mancini_confluence: bool = False
