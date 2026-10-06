"""Level history AS OF a bar, from our own tape. [st-ygoz]

WHY THIS EXISTS
    Fuel's first component, "touched Nx / defended Nx since ... , <state>", used
    to come from ``data/level_state/<day>.json``: the tracker's Schwab-candle
    read, rewritten every minute, which the feeder loaded once and never re-read.
    On 2026-10-06 Bar 232 printed "touched 0x / defended 0x, untouched" for 7879
    at 09:38 CT. By then the level had been touched at 08:55, broken above at
    09:00 and fallen back under at 09:15. Steve: "i take emissions to be
    potentially actionable so it's not acceptable for them to be unchecked."

    Re-reading that file more often only shrinks the window. It stays a second
    process's view, on a second data source, timed by a second clock, and it
    can't be reproduced afterwards because touch counts are not stored with
    times. So the history is now computed here, from the same trades the bars
    are built from, by the SAME machine the tracker runs
    (``overnight.compute_interactions``), over five-minute candles cut at the
    bar's close. It cannot be older than the bar it prints on, and live, replay
    and backfill compute it identically.

WINDOW: ``overnight.letter_window_start`` (4pm ET the day before the plan-day),
the tracker's rule, so the counts mean what the tracker's counts mean. Candles
are Databento ES trades bucketed to five minutes, not Schwab's candles; at
the ±2-pt tolerance the two agree except where a print sits right on a band
edge. Only COMPLETED candles count, meaning end <= the bar's close. A candle
still forming says nothing yet.

Rows carry the tracker's keys (``n_touches``, ``n_defenses``, ``first_touch``,
``state``) so ``fuel._history_phrase`` reads them unchanged, plus ``asof`` (the
last candle end included) and ``source: "tape"`` so every line can be audited.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
PARSED = ROOT / "runbook" / "mancini" / "parsed"
CANDLE_S = 300


class TapeLevelHistory:
    """Feed trades in time order; ask ``as_of(ts)`` for {price: history row}."""

    def __init__(self, levels: list, *, window_start: datetime,
                 tolerance: float | None = None):
        from runbook.mancini import overnight
        self._compute = overnight.compute_interactions
        self.tolerance = overnight.DEFAULT_TOLERANCE_PTS if tolerance is None else tolerance
        self.levels = [lv for lv in levels if getattr(lv, "kind", None) in ("support", "resistance")]
        self.window_start = window_start.astimezone(timezone.utc)
        self._candles: list[dict] = []        # completed, ascending
        self._cur: dict | None = None         # forming
        self._cache_key: tuple | None = None
        self._cache: dict[float, dict] = {}

    def add(self, trade) -> None:
        ts = trade.ts.astimezone(timezone.utc)
        if ts < self.window_start:
            return
        b = int(ts.timestamp()) // CANDLE_S * CANDLE_S
        cur = self._cur
        if cur is None or b != cur["_b"]:
            if cur is not None:
                self._candles.append(cur)
            self._cur = {"_b": b, "datetime": b * 1000, "open": trade.price,
                         "high": trade.price, "low": trade.price, "close": trade.price}
            return
        p = trade.price
        if p > cur["high"]:
            cur["high"] = p
        if p < cur["low"]:
            cur["low"] = p
        cur["close"] = p

    def seed(self, trades: Iterable) -> int:
        n = 0
        for t in trades:
            self.add(t)
            n += 1
        return n

    def as_of(self, when: datetime) -> dict[float, dict]:
        """History over every candle that had CLOSED by ``when``."""
        if not self.levels:
            return {}
        cut = int(when.astimezone(timezone.utc).timestamp())
        done = [c for c in self._candles if c["_b"] + CANDLE_S <= cut]
        if self._cur is not None and self._cur["_b"] + CANDLE_S <= cut:
            done.append(self._cur)
        key = (len(done), done[-1]["_b"] if done else None)
        if key == self._cache_key:
            return self._cache
        asof = (datetime.fromtimestamp(done[-1]["_b"] + CANDLE_S, tz=timezone.utc).isoformat()
                if done else None)
        out: dict[float, dict] = {}
        for it in self._compute(self.levels, done, self.tolerance):
            out[float(it.price)] = {"n_touches": it.touches, "n_defenses": it.defenses,
                                    "first_touch": it.first_touch, "state": it.state,
                                    "asof": asof, "source": "tape"}
        self._cache_key, self._cache = key, out
        return out


def levels_for(day: _date, parsed_root: Path = PARSED) -> list:
    """The plan-day's parsed ladder as ``schema.Level`` objects ([] if unparsed)."""
    from runbook.mancini import schema
    p = parsed_root / f"{day.isoformat()}.json"
    try:
        return list(schema.ParseResult.from_dict(json.loads(p.read_text(encoding="utf-8"))).levels)
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.info("level history: no parse for %s (%s)", day, e)
        return []


def for_day(day: _date, *, prior_trades=None, parsed_root: Path = PARSED) -> TapeLevelHistory | None:
    """A history for ``day``, pre-seeded with the window before ``day``'s own tape.

    ``prior_trades(start_ts, day)`` yields trades from ``start_ts`` up to the
    start of ``day`` — the feeder and the backfill both pass the corpus reader.
    Returns None when the day has no parse (no levels, nothing to count)."""
    from runbook.mancini import overnight
    levels = levels_for(day, parsed_root)
    if not levels:
        return None
    start = overnight.letter_window_start(day.isoformat())
    h = TapeLevelHistory(levels, window_start=start)
    if prior_trades is not None:
        n = h.seed(prior_trades(start, day))
        logger.info("level history: seeded %d prints from %s", n, start.isoformat())
    return h


def corpus_prior_trades(start: datetime, day: _date):
    """Corpus trades from ``start`` up to ``day``'s midnight, calendar day by day
    (each calendar directory holds its own evening tape since 2026-08-18)."""
    from market.orderflow.tradesource import iter_trades
    from zoneinfo import ZoneInfo
    ct = ZoneInfo("America/Chicago")
    d = start.astimezone(ct).date()
    while d < day:
        try:
            yield from iter_trades(d, start_ts=start)
        except FileNotFoundError:
            logger.info("level history: no corpus file for %s", d)
        d += timedelta(days=1)
