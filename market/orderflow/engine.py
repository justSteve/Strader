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
  - Sweep runs: same-side prints whose event-time gaps stay within
    SWEEP_WINDOW_MS and whose prices advance monotonically with the side;
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
    SWEEP_MAX_SPAN_MS,
    SWEEP_MIN_CONCENTRATION,
    SWEEP_MIN_SIZE,
    SWEEP_MIN_TICKS,
    SWEEP_WINDOW_MS,
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
        out: list[Signal] = []
        r = self._run
        if r is not None:
            gap_ms = (t.ts - r["last_ts"]).total_seconds() * 1000.0
            advancing = (t.price >= r["last_price"]) if r["side"] == "B" else (t.price <= r["last_price"])
            if t.side == r["side"] and gap_ms <= SWEEP_WINDOW_MS and advancing:
                r["last_ts"] = t.ts
                r["last_price"] = t.price
                r["size"] += t.size
                r["biggest"] = max(r["biggest"], t.size)
                r["prices"].add(round(t.price / TICK))
                return out
            out.extend(self._end_run())
        if t.side in ("B", "A"):
            self._run = {"side": t.side, "start_ts": t.ts, "last_ts": t.ts,
                         "start_price": t.price, "last_price": t.price,
                         "size": t.size, "biggest": t.size,
                         "prices": {round(t.price / TICK)}}
        return out

    def _end_run(self) -> list[Signal]:
        r, self._run = self._run, None
        if r is None or len(r["prices"]) < SWEEP_MIN_TICKS or r["size"] < SWEEP_MIN_SIZE:
            return []
        # ONE ORDER, NOT A CROWD [2026-08-27]. The gates above measure how much
        # aggression happened; these two measure whether it came from a single
        # participant. Without them the emission fires ~42x a session on
        # thirteen small prints leaning the same way for 56ms, which is a real
        # thing but is not a sweep. See orderflow_config for the measurement.
        # Both are recorded on the signal, not just tested — the span is the
        # field that best separates the two populations and it was previously
        # computed and thrown away, so nothing downstream could filter on it.
        span_ms = (r["last_ts"] - r["start_ts"]).total_seconds() * 1000.0
        concentration = r["biggest"] / r["size"] if r["size"] else 0.0
        if span_ms > SWEEP_MAX_SPAN_MS or concentration < SWEEP_MIN_CONCENTRATION:
            return []
        direction = "buy" if r["side"] == "B" else "sell"
        ticks = len(r["prices"])
        return [SweepPrint(
            timestamp=r["last_ts"], source="orderflow.sweep",
            confidence=min(1.0, ticks / (2 * SWEEP_MIN_TICKS)),
            # The line said "N levels" here and "N ticks" in speech.py for one
            # field the lexicon had already named tick-level. Both now render
            # from that one word — st-bkvt, Desk Ruling 1 item 5.
            reason=render("sweep-print", "reason", {
                "direction": direction,
                "span": (r["start_price"], r["last_price"]),
                "ticks_swept": ticks,
                "total_size": r["size"],
            }),
            direction=direction, start_price=r["start_price"],
            end_price=r["last_price"], ticks_swept=ticks, total_size=r["size"],
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
