"""Parity pipeline — the full orderflow stack as one deterministic run (st-bw9).

Spec §5: live == replay is proven, not assumed. This module defines THE
canonical pipeline the parity harness snapshots: reader-ordered trades →
volume bars → engine signals → per-bar imbalances → recognizer events →
profile levels, serialized to plain dicts in a documented, stable order.

The CI test (tests/market/orderflow/test_parity_harness.py) replays the
committed fixture through ``parity_run`` and diffs the result against the
committed snapshot JSON — field-by-field, so a failure names the first
divergent event rather than just failing a hash. Regenerate deliberately via
``scripts/regen_parity_snapshot.py --reason "..."`` (one commit: snapshot +
CHANGES entry + the engine change that motivated it).

Ordering rules (stable by construction):
  1. Per completed bar, in stream order:
     a. engine signals emitted while the bar's trades were processed
     b. the bar's imbalance stacks (ascending stack start price)
     c. recognizer events for the bar (anchor list order)
  2. Engine flush() signals (end of stream)
  3. Profile levels (emission order: POC, HVNs ascending, LVNs ascending)

Threshold overrides: the committed fixture is a small slice, so production
floors (sized for institutional prints) would yield a near-empty snapshot.
``PARITY_OVERRIDES`` scales them to fixture scale — applied and restored
around the run, and part of the harness definition itself (changing them is
a snapshot regeneration like any engine change).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import fields
from typing import Iterable

import market.orderflow.engine as _engine_mod
import market.orderflow.recognizer as _recognizer_mod
from market.entities.trade import Trade
from market.orderflow.bars import build_bars
from market.orderflow.engine import OrderflowEngine
from market.orderflow.imbalance import find_stacks
from market.orderflow.profile import build_profile, profile_levels
from market.orderflow.recognizer import Anchor, SetupRecognizer
from market.signals.types import Signal

logger = logging.getLogger(__name__)

PARITY_BAR_N = 500

# fixture-scale floors; every value here is part of the harness contract
PARITY_OVERRIDES = {
    _engine_mod: {"SWEEP_MIN_SIZE": 30, "LARGE_LOT_MIN_SIZE": 20},
    _recognizer_mod: {"FLUSH_DELTA_MIN": 30, "QUIET_DELTA_MAX": 10,
                      "FLIP_DELTA_MIN": 20, "CONFIRM_DELTA_MIN": 25},
}

# anchors the parity recognizer watches on the fixture (fixture price range:
# ~7555 morning slice, ~7482 afternoon slice)
PARITY_ANCHORS = (
    Anchor(7482.0, "support", "parity-poc"),
    Anchor(7555.0, "resistance", "parity-am"),
)
PARITY_MANCINI = (7482.5,)  # exercises the confluence flag deterministically


@contextmanager
def _overridden():
    saved = [(mod, name, getattr(mod, name))
             for mod, kv in PARITY_OVERRIDES.items() for name in kv]
    try:
        for mod, kv in PARITY_OVERRIDES.items():
            for name, value in kv.items():
                setattr(mod, name, value)
        yield
    finally:
        for mod, name, value in saved:
            setattr(mod, name, value)


def serialize(sig: Signal) -> dict:
    """Signal → plain dict: type name + every dataclass field, timestamps as
    ISO strings, floats rounded to the tick grid's 2 decimals."""
    out = {"type": type(sig).__name__}
    for f in fields(sig):
        v = getattr(sig, f.name)
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        elif isinstance(v, float):
            v = round(v, 4)
        elif isinstance(v, tuple):
            v = [round(x, 4) if isinstance(x, float) else x for x in v]
        out[f.name] = v
    return out


def parity_run(trades: Iterable[Trade]) -> list[dict]:
    """The canonical full-stack replay. Deterministic: same trades, same list."""
    trades = list(trades)
    events: list[dict] = []
    with _overridden():
        engine = OrderflowEngine()
        recognizer = SetupRecognizer(list(PARITY_ANCHORS), mancini_prices=PARITY_MANCINI)

        pending: list[Trade] = []
        bar_iter = build_bars(iter(trades), n=PARITY_BAR_N, include_partial=True)
        # Drive engine per-trade and bar-consumers per-bar in one pass:
        # bars close on known trade boundaries, so process trades until each
        # bar's end_ts/volume is covered. Simplest faithful drive: rebuild the
        # engine stream alongside the bar stream on the same trade list.
        idx = 0
        for bar in bar_iter:
            vol = 0
            while idx < len(trades) and vol < bar.volume:
                t = trades[idx]
                for s in engine.process(t):
                    events.append(serialize(s))
                vol += t.size
                idx += 1
            for stack in find_stacks(bar):
                events.append(serialize(stack))
            for rec in recognizer.on_bar(bar):
                events.append(serialize(rec))
        while idx < len(trades):
            for s in engine.process(trades[idx]):
                events.append(serialize(s))
            idx += 1
        for s in engine.flush():
            events.append(serialize(s))

        prof = build_profile(trades)
        for lv in profile_levels(prof, reference_price=trades[-1].price):
            events.append(serialize(lv))

    logger.info("parity_run: %d trades -> %d events", len(trades), len(events))
    return events
