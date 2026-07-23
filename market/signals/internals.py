"""Market-internals signals — interpretations emitted by the MI gauge. [st-3fr]

Same contract as market/signals/orderflow.py: frozen Signal subclasses,
score-with-exposed-evidence, never a bare boolean. The gauge's design rule
(Steve, 2026-07-22): one number, but it always names its driver — the display
teaches the pattern instead of hiding it inside math.
"""
from __future__ import annotations

from dataclasses import dataclass

from market.signals.types import Signal


@dataclass(frozen=True)
class InternalsRead(Signal):
    """One gauge reading for one minute of tape.

    ``score`` is signed −100..+100: sign = tape direction, magnitude =
    conviction. ``driver`` names the dominant component in plain words
    ("TICK climax", "TICK capitulation", "cum TICK spine", "quiet tape").
    ``confidence`` mirrors |score|/100. Components stay exposed:
    ``instant`` (minute wick vs bucket climax thresholds) and ``cum``
    (time-normalized cumulative TICK pace), both already in score units.
    ``band`` is the action zone: "climax" | "lean" | "neutral"."""

    score: int = 0
    driver: str = "quiet tape"
    band: str = "neutral"
    bucket: str = ""
    instant: int = 0
    cum: int = 0
    tick_high: int = 0
    tick_low: int = 0
    cum_tick: int = 0
