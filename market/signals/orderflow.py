"""Orderflow signals — interpretations emitted by the orderflow engine.

Design spec §6 (docs/superpowers/specs/2026-07-03-orderflow-signal-layer-design.md).
These extend the frozen ``Signal`` hierarchy in ``market/signals/types.py`` —
data artifacts (FootprintBar) live in ``market/entities``; interpretations
live here. Arrives bead-by-bead: SweepPrint + DeltaDivergence (st-wnc);
ImbalanceStack (st-su4); SetupRecognition (st-2kf); AbsorptionRead (st-9vl).
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
class AbsorptionRead(Signal):
    """A passive defender soaked one-sided aggression at a top-of-book level:
    heavy aggressive volume hit the level while resting size repeatedly
    refilled and price refused to move (research doc Q4 — force without
    effect). Scored evidence, never a boolean gate: ``confidence`` carries the
    score, components stay exposed. Emitted when the level episode ends.

    ``displacement_ticks`` is signed from the defender's perspective: where
    top-of-book went when the episode closed. For a bid defense, negative =
    the level finally broke; positive = price lifted away (defense won).
    ``refill_events`` requires MBP-1 quotes; 0 when running trades-only
    (degraded, and labeled so in ``reason``)."""

    side: Literal["bid", "ask"] = "bid"
    price: float = 0.0
    aggressive_vol: int = 0
    displacement_ticks: int = 0
    refill_events: int = 0


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
    # 1-based per-anchor confirmed-fire sequence [st-98z]: which confirm this
    # is (or, on forming/invalidated, would be) for its anchor within the
    # recognizer's lifetime. Confirmed confidence is step-damped at >= 4.
    fire_index: int = 1
