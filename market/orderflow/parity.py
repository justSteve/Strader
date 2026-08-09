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
from market.entities.book import BookEvent
from market.entities.trade import Trade
from market.orderflow.absorption import AbsorptionTracker
from market.orderflow.bars import build_bars
from market.orderflow.engine import OrderflowEngine
from market.orderflow.imbalance import find_stacks
from market.orderflow.profile import ProfileAccumulator, profile_levels
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


class StackDriver:
    """The canonical pipeline as an INCREMENTAL drive — one bar at a time.

    ``full_stack_events`` is a batch pass over a finished day; a live session
    has no finished day to pass. Rather than let the live feeder grow a second
    drive loop — the exact divergence the spec §5 parity guarantee exists to
    prevent — the loop lives here and ``full_stack_events`` is a thin caller of
    it. Whatever the live surface shows, the replay record therefore recomputes
    identically. [st-b0n9]

    Contract: feed COMPLETED bars in order together with the trade slice that
    built each one, then call ``finish``. The per-bar emission order and the
    end-of-stream order are the module docstring's ordering rules.

    ONE KNOWN LIVE/RECORD DIVERGENCE, by construction: ``full_stack_events``
    builds bars with ``include_partial=True``, so a day's trailing under-N bar
    is a real bar whose stacks and recognitions carry its ``bar_i``. The live
    feeder renders closed bars only, so those same trades reach ``finish`` as
    trailing trades and produce engine signals with ``bar_i=None`` and no
    stacks or recognitions. Only the final partial bar of a session is
    affected; every closed bar agrees exactly.
    """

    def __init__(self, *, anchors: Iterable[Anchor],
                 mancini_prices: Iterable[float] = ()):
        self.engine = OrderflowEngine()
        self.recognizer = SetupRecognizer(list(anchors),
                                          mancini_prices=list(mancini_prices))
        self._profile = ProfileAccumulator()
        self._last_price: float | None = None

    def _observe(self, t: Trade) -> None:
        self._profile.add(t)
        self._last_price = t.price

    def on_bar(self, bar_i: int, bar, trades: Iterable[Trade]) -> list[dict]:
        """Emissions for one completed bar: engine signals raised while its
        trades were processed, then its imbalance stacks, then its recognizer
        events. ``trades`` is the bar's own slice in stream order."""
        out: list[dict] = []
        for t in trades:
            for s in self.engine.process(t):
                out.append(serialize(s) | {"bar_i": bar_i})
            self._observe(t)
        for stack in find_stacks(bar):
            out.append(serialize(stack) | {"bar_i": bar_i})
        for rec in self.recognizer.on_bar(bar):
            out.append(serialize(rec) | {"bar_i": bar_i})
        return out

    def finish(self, trailing_trades: Iterable[Trade] = ()) -> list[dict]:
        """End-of-stream emissions: any trades past the last completed bar,
        then engine ``flush()``, then the session's profile levels. All carry
        ``bar_i=None``. Safe on an empty stream — a live page that never saw a
        trade gets an empty list, not a raised profile."""
        out: list[dict] = []
        for t in trailing_trades:
            for s in self.engine.process(t):
                out.append(serialize(s) | {"bar_i": None})
            self._observe(t)
        for s in self.engine.flush():
            out.append(serialize(s) | {"bar_i": None})
        if self._profile.n:
            prof = self._profile.build()
            for lv in profile_levels(prof, reference_price=self._last_price):
                out.append(serialize(lv) | {"bar_i": None})
        return out


def live_drive(bars_with_trades, driver: "StackDriver", live_anchors):
    """The LIVE drive order, in one place. [st-x2mp]

    Yields ``(bar_i, bar, trades, events)`` per completed bar. Two rules ride
    here and nowhere else, because both are silent when broken and both change
    what the recognizer sees:

      1. ``live_anchors.observe(bar)`` runs BEFORE ``driver.on_bar`` — the bar
         extends the developing range it belongs to, then is judged against
         it. Reversed, a bar that sets a new extreme is judged against the
         range it just broke.
      2. Closed bars only. The caller's iterator must not include a partial.

    The feeder consumes this live; ``scripts/live_parity_check.py`` consumes it
    over a replayed tape. That is the whole point: if the loop existed twice,
    the parity check would be measuring the copy rather than the original.
    ``live_anchors`` may be None when nothing is developing (tests).
    """
    for bar_i, (bar, bar_trades) in enumerate(bars_with_trades):
        if live_anchors is not None:
            live_anchors.observe(bar)
        yield bar_i, bar, bar_trades, driver.on_bar(bar_i, bar, bar_trades)


def full_stack_events(trades: list[Trade], *, bar_n: int,
                      anchors: Iterable[Anchor],
                      mancini_prices: Iterable[float] = ()) -> list[dict]:
    """One deterministic pass of the full stack at CURRENT module thresholds.

    The canonical batch run (ordering rules in the module docstring), shared
    by the parity harness (fixture floors via ``_overridden``) and the replay
    recorder (production floors, st-055). Every event dict carries ``bar_i``
    — the index of the completed bar it was emitted under, ``None`` for
    end-of-stream flush signals and profile levels.

    The drive itself is ``StackDriver``; this function only slices trades to
    bars. The live feeder drives the same object one bar at a time.
    """
    driver = StackDriver(anchors=anchors, mancini_prices=mancini_prices)
    events: list[dict] = []

    idx = 0
    # Bars close on known trade boundaries, so walk trades until each bar's
    # volume is covered — the slice a live adapter reclaims per bar is the
    # same slice, by the same straddle convention.
    for bar_i, bar in enumerate(build_bars(iter(trades), n=bar_n, include_partial=True)):
        vol = 0
        start = idx
        while idx < len(trades) and vol < bar.volume:
            vol += trades[idx].size
            idx += 1
        events += driver.on_bar(bar_i, bar, trades[start:idx])
    events += driver.finish(trades[idx:])
    return events


def parity_run(trades: Iterable[Trade]) -> list[dict]:
    """The canonical full-stack replay. Deterministic: same trades, same list."""
    trades = list(trades)
    with _overridden():
        events = full_stack_events(trades, bar_n=PARITY_BAR_N,
                                   anchors=PARITY_ANCHORS,
                                   mancini_prices=PARITY_MANCINI)
    for e in events:
        e.pop("bar_i", None)  # snapshot format predates bar_i; keep it stable
    logger.info("parity_run: %d trades -> %d events", len(trades), len(events))
    return events


def absorption_parity_run(book_events: Iterable[BookEvent]) -> list[dict]:
    """The MBP-1 absorption replay (st-9vl). Runs at PRODUCTION floors — the
    committed fixture (a 65s slice of the purchased 2026-07-02 MBP-1 day,
    around the 10:11:28 CT defended-ask read) was chosen to contain a
    production-scale emission, so no override scaling is needed. Deterministic:
    same events, same list."""
    tracker = AbsorptionTracker()
    events: list[dict] = []
    n = 0
    for e in book_events:
        n += 1
        for s in tracker.process(e):
            events.append(serialize(s))
    for s in tracker.flush():
        events.append(serialize(s))
    logger.info("absorption_parity_run: %d book events -> %d reads", n, len(events))
    return events
