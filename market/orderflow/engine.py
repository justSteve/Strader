"""OrderflowEngine — the deterministic event-driven core (st-wnc, spec §5).

One code path for live and replay: ``process(trade)`` consumes trades in
canonical stream order and returns the signals that completed on that event.
Everything is a pure function of the input stream — no wall-clock, no
randomness; the parity harness (st-bw9) depends on it.

State maintained per engine instance:
  - CVD: running buy-aggr − sell-aggr, reset at the first print at/after the
    CVD_RESET_CT cash open of each session day; ``None``-side volume tracked
    separately, never in delta (NONE_SIDE_POLICY).
  - Large-lot: print size ≥ LARGE_LOT_K × rolling median of the last
    LARGE_LOT_MEDIAN_WINDOW print sizes. Silent during warm-up (the window
    must fill first) so live and replay see identical state.
  - Sweeps: one match event — consecutive same-side prints sharing
    (sequence, ts_event), i.e. one aggressor order's fills (st-exmw);
    a ``SweepPrint`` is emitted when a qualifying run ENDS (≥ SWEEP_MIN_TICKS
    distinct levels) — end-of-run emission keeps the signal deterministic.
  - Swing pivots: zigzag with PIVOT_FILTER_TICKS confirmation. On each
    confirmed pivot, the (price, CVD) pair is compared to the prior same-side
    pivot; price more extreme + CVD less extreme = ``DeltaDivergence``.

Large-lot events are exposed as engine state (``last_large_lot``) rather than
a Signal subclass for now — the spec reserves them as confirmation *inputs*
to the Q2 recognizer, not standalone alerts; st-2kf decides their surface.
"""
from __future__ import annotations

import bisect
import logging
from collections import deque
from datetime import datetime, time as _time
from typing import Iterable

from market.emission import render
from market.entities.trade import Trade
from market.signals.orderflow import DeltaDivergence, SweepPrint
from market.signals.types import Signal
from market.signals.orderflow_config import (
    CVD_RESET_CT,
    LARGE_LOT_K,
    LARGE_LOT_MEDIAN_WINDOW,
    LARGE_LOT_MIN_SIZE,
    PIVOT_FILTER_TICKS,
    SWEEP_LEVEL_MIN_SHARE,
    SWEEP_LEVEL_MIN_SIZE,
    SWEEP_MIN_SIZE,
    SWEEP_MIN_TICKS,
    TICK,
)

logger = logging.getLogger(__name__)

_RESET = _time(*(int(x) for x in CVD_RESET_CT.split(":")))


class _RollingMedian:
    """Order-statistics window over print sizes. O(log n) insert/evict via
    bisect on a sorted list — deterministic, no heap tie ambiguity."""

    def __init__(self, size: int):
        self.size = size
        self._fifo: deque[int] = deque()
        self._sorted: list[int] = []

    def push(self, v: int) -> None:
        self._fifo.append(v)
        bisect.insort(self._sorted, v)
        if len(self._fifo) > self.size:
            old = self._fifo.popleft()
            del self._sorted[bisect.bisect_left(self._sorted, old)]

    @property
    def full(self) -> bool:
        return len(self._fifo) >= self.size

    @property
    def median(self) -> float:
        s = self._sorted
        n = len(s)
        mid = n // 2
        return float(s[mid]) if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def level_split(levels: dict[int, int], total: int, *,
                ascending: bool) -> list[tuple[float, int, bool]]:
    """Each price a run traded, in the order the aggressor walked it:
    ``(price, contracts, counts)`` where ``counts`` says whether the price
    carries enough size to count as a level swept [st-r6ni]."""
    floor = max(SWEEP_LEVEL_MIN_SIZE, SWEEP_LEVEL_MIN_SHARE * total)
    return [(round(k * TICK, 2), n, n >= floor)
            for k, n in sorted(levels.items(), reverse=not ascending)]


class OrderflowEngine:
    """Process trades in stream order; collect per-event completed signals."""

    def __init__(self):
        # CVD
        self.cvd = 0
        self.none_vol = 0
        self.session_day = None  # date of the current CVD epoch
        # large-lot
        self._sizes = _RollingMedian(LARGE_LOT_MEDIAN_WINDOW)
        self.last_large_lot: Trade | None = None
        self.large_lot_count = 0
        # sweep run
        self._run: dict | None = None
        # zigzag pivots: direction +1 tracking a high, -1 tracking a low
        self._dir = 0
        self._ext_price = None   # running extreme price of current leg
        self._ext_cvd = 0
        self._prev_high: tuple[float, int] | None = None  # (price, cvd)
        self._prev_low: tuple[float, int] | None = None
        self._last_ts: datetime | None = None

    # ── public API ──────────────────────────────────────────────────────────
    def process(self, t: Trade) -> list[Signal]:
        if self._last_ts is not None and t.ts < self._last_ts:
            raise ValueError(
                f"out-of-order trade at {t.ts.isoformat()} (prev {self._last_ts.isoformat()})"
            )
        self._last_ts = t.ts
        out: list[Signal] = []
        self._roll_session(t)
        self._update_cvd(t)
        self._update_large_lot(t)
        out.extend(self._update_sweep(t))
        out.extend(self._update_pivots(t))
        return out

    def flush(self) -> list[Signal]:
        """End-of-stream: close any open sweep run."""
        return self._end_run()

    def run(self, trades: Iterable[Trade]) -> list[Signal]:
        signals: list[Signal] = []
        for t in trades:
            signals.extend(self.process(t))
        signals.extend(self.flush())
        return signals

    # ── CVD ─────────────────────────────────────────────────────────────────
    def _roll_session(self, t: Trade) -> None:
        day = t.ts.date()
        if self.session_day != day and t.ts.time() >= _RESET:
            if self.session_day is not None:
                logger.debug("CVD reset: %s -> %s (was %+d, none %d)",
                             self.session_day, day, self.cvd, self.none_vol)
            self.session_day = day
            self.cvd = 0
            self.none_vol = 0

    def _update_cvd(self, t: Trade) -> None:
        if t.side == "B":
            self.cvd += t.size
        elif t.side == "A":
            self.cvd -= t.size
        else:
            self.none_vol += t.size

    # ── large-lot ───────────────────────────────────────────────────────────
    def _update_large_lot(self, t: Trade) -> None:
        if (self._sizes.full and t.side != "N" and t.size >= LARGE_LOT_MIN_SIZE
                and t.size >= LARGE_LOT_K * self._sizes.median):
            self.last_large_lot = t
            self.large_lot_count += 1
        self._sizes.push(t.size)

    # ── sweep detection ─────────────────────────────────────────────────────
    def _update_sweep(self, t: Trade) -> list[Signal]:
        """ONE MATCH EVENT IS ONE ORDER [st-exmw, 2026-10-01]. Every fill of
        one aggressor order shares the event's ``(sequence, ts_event)`` — the
        key the corpus dedup used to collapse, which is why this could not be
        seen before. A run is now exactly that: consecutive same-side prints
        of one event. The 250 ms window and the span/concentration gates were
        stand-ins for "one order" on a tape that had lost the other fills."""
        out: list[Signal] = []
        r = self._run
        if r is not None:
            if (t.side == r["side"] and t.ts == r["last_ts"]
                    and t.sequence == r["sequence"]):
                r["last_price"] = t.price
                r["size"] += t.size
                r["biggest"] = max(r["biggest"], t.size)
                k = round(t.price / TICK)
                r["prices"].add(k)
                r["levels"][k] = r["levels"].get(k, 0) + t.size
                return out
            out.extend(self._end_run())
        if t.side in ("B", "A"):
            self._run = {"side": t.side, "sequence": t.sequence,
                         "start_ts": t.ts, "last_ts": t.ts,
                         "start_price": t.price, "last_price": t.price,
                         "size": t.size, "biggest": t.size,
                         "prices": {round(t.price / TICK)},
                         "levels": {round(t.price / TICK): t.size}}
        return out

    def _end_run(self) -> list[Signal]:
        r, self._run = self._run, None
        if r is None or len(r["prices"]) < SWEEP_MIN_TICKS or r["size"] < SWEEP_MIN_SIZE:
            return []
        span_ms = (r["last_ts"] - r["start_ts"]).total_seconds() * 1000.0
        concentration = r["biggest"] / r["size"] if r["size"] else 0.0
        # A PRICE COUNTS ONLY WHEN IT CARRIES SIZE [st-r6ni]. The count above
        # is prices touched; a one-lot tail two ticks up made a single-price
        # fill read as a three-price sweep (08-21 09:05 CT).
        levels = level_split(r["levels"], r["size"], ascending=r["side"] == "B")
        swept = sum(1 for _, _, counts in levels if counts)
        if swept < SWEEP_MIN_TICKS:
            return []
        # the span named is the counted prices', not a dust tail's (audit #2)
        counted = [p for p, _, c in levels if c]
        r["start_price"], r["last_price"] = counted[0], counted[-1]
        direction = "buy" if r["side"] == "B" else "sell"
        return [SweepPrint(
            timestamp=r["last_ts"], source="orderflow.sweep",
            confidence=min(1.0, swept / (2 * SWEEP_MIN_TICKS)),
            # The line said "N levels" here and "N ticks" in speech.py for one
            # field the lexicon had already named tick-level. Both now render
            # from that one word — st-bkvt, Desk Ruling 1 item 5.
            reason=render("sweep-print", "reason", {
                "direction": direction,
                "span": (r["start_price"], r["last_price"]),
                "levels_swept": swept,
                "total_size": r["size"],
            }),
            direction=direction, start_price=r["start_price"],
            end_price=r["last_price"], levels_swept=swept, total_size=r["size"],
            level_sizes=tuple((p, n) for p, n, _ in levels),
            span_ms=round(span_ms, 3), concentration=round(concentration, 4),
        )]

    # ── pivots + divergence ─────────────────────────────────────────────────
    def _update_pivots(self, t: Trade) -> list[Signal]:
        out: list[Signal] = []
        p = t.price
        if self._dir == 0:
            if self._ext_price is None:
                self._ext_price, self._ext_cvd = p, self.cvd
            elif p >= self._ext_price + PIVOT_FILTER_TICKS * TICK:
                self._dir, self._ext_price, self._ext_cvd = 1, p, self.cvd
            elif p <= self._ext_price - PIVOT_FILTER_TICKS * TICK:
                self._dir, self._ext_price, self._ext_cvd = -1, p, self.cvd
            return out
        if self._dir == 1:  # leg up: extending highs
            if p > self._ext_price:
                self._ext_price, self._ext_cvd = p, self.cvd
            elif p <= self._ext_price - PIVOT_FILTER_TICKS * TICK:
                out.extend(self._confirm_pivot(t, high=True))
                self._dir, self._ext_price, self._ext_cvd = -1, p, self.cvd
        else:               # leg down: extending lows
            if p < self._ext_price:
                self._ext_price, self._ext_cvd = p, self.cvd
            elif p >= self._ext_price + PIVOT_FILTER_TICKS * TICK:
                out.extend(self._confirm_pivot(t, high=False))
                self._dir, self._ext_price, self._ext_cvd = 1, p, self.cvd
        return out

    def _confirm_pivot(self, t: Trade, high: bool) -> list[Signal]:
        price, cvd = self._ext_price, self._ext_cvd
        prev = self._prev_high if high else self._prev_low
        if high:
            self._prev_high = (price, cvd)
        else:
            self._prev_low = (price, cvd)
        if prev is None:
            return []
        prev_price, prev_cvd = prev
        if high and price > prev_price and cvd < prev_cvd:
            kind = "bearish"
        elif not high and price < prev_price and cvd > prev_cvd:
            kind = "bullish"
        else:
            return []
        word = "high" if high else "low"
        return [DeltaDivergence(
            timestamp=t.ts, source="orderflow.divergence",
            confidence=0.5,  # divergence is evidence, not a timer (research Q1.2)
            reason=(f"{kind}: new swing {word} {price:.2f} vs {prev_price:.2f} "
                    f"but CVD {cvd:+d} vs {prev_cvd:+d} — move ran on weaker aggression"),
            kind=kind, price_extreme=price, prior_extreme=prev_price,
            cvd_at_extreme=cvd, cvd_at_prior=prev_cvd,
        )]
