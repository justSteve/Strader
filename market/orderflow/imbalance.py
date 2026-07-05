"""Diagonal footprint imbalance + stacked-imbalance detection (st-su4, spec §2).

The diagonal rule (research doc Q1.3): aggressive buyers lift offers resting
at price P while aggressive sellers hit bids resting one tick below, so the
honest comparison is

  buy  imbalance at P: ask_vol[P] vs bid_vol[P - tick]
  sell imbalance at P: bid_vol[P] vs ask_vol[P + tick]

A level is imbalanced when the dominant side is ≥ IMBALANCE_RATIO × the
diagonal opposite AND ≥ IMBALANCE_FLOOR contracts. STACK_MIN+ consecutive
(tick-adjacent) same-direction imbalances form an ``ImbalanceStack`` — the
signal the four-beat recognizer consumes as beat-4 evidence.

Pure per-bar functions: deterministic by construction, stacks never span
bars, and a zero-volume void price breaks adjacency (nothing traded there,
so nothing dominated there).
"""
from __future__ import annotations

import logging
from typing import Literal

from market.entities.footprint import FootprintBar
from market.signals.orderflow import ImbalanceStack
from market.signals.orderflow_config import (
    IMBALANCE_FLOOR,
    IMBALANCE_RATIO,
    STACK_MIN,
    TICK,
)

logger = logging.getLogger(__name__)


def find_imbalances(bar: FootprintBar) -> list[tuple[float, Literal["buy", "sell"], float]]:
    """Per-price diagonal imbalances in one bar: (price, direction, ratio),
    ascending by price. Ratio divides by max(opposite, 1) so a zero diagonal
    opposite is dominance, not a crash."""
    vols = {round(c.price / TICK): (c.bid_vol, c.ask_vol) for c in bar.cells}
    out: list[tuple[float, Literal["buy", "sell"], float]] = []
    for tk in sorted(vols):
        bid, ask = vols[tk]
        below_bid = vols.get(tk - 1, (0, 0))[0]
        above_ask = vols.get(tk + 1, (0, 0))[1]
        if ask >= IMBALANCE_FLOOR and ask >= IMBALANCE_RATIO * max(below_bid, 1):
            out.append((tk * TICK, "buy", ask / max(below_bid, 1)))
        elif bid >= IMBALANCE_FLOOR and bid >= IMBALANCE_RATIO * max(above_ask, 1):
            out.append((tk * TICK, "sell", bid / max(above_ask, 1)))
    return out


def find_stacks(bar: FootprintBar) -> list[ImbalanceStack]:
    """Group tick-adjacent same-direction imbalances into ImbalanceStack
    signals (length ≥ STACK_MIN). Timestamped at bar close — a stack is only
    knowable when the bar completes."""
    imbs = find_imbalances(bar)
    stacks: list[ImbalanceStack] = []
    run: list[tuple[float, Literal["buy", "sell"], float]] = []

    def _flush() -> None:
        if len(run) >= STACK_MIN:
            direction = run[0][1]
            prices = tuple(p for p, _, _ in run)
            ratios = tuple(round(r, 2) for _, _, r in run)
            stacks.append(ImbalanceStack(
                timestamp=bar.end_ts, source="orderflow.imbalance",
                confidence=min(1.0, len(run) / (2 * STACK_MIN)),
                reason=(f"{direction} imbalance stack {prices[0]:.2f}-{prices[-1]:.2f} "
                        f"({len(run)} levels, ratios {ratios[0]:.1f}..{ratios[-1]:.1f})"),
                direction=direction, prices=prices, ratios=ratios,
            ))
        run.clear()

    prev_tk: int | None = None
    for price, direction, ratio in imbs:
        tk = round(price / TICK)
        if run and (direction != run[-1][1] or prev_tk is None or tk != prev_tk + 1):
            _flush()
        run.append((price, direction, ratio))
        prev_tk = tk
    _flush()
    return stacks
