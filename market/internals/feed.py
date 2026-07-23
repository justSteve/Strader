"""Internals corpus feed — internals.jsonl day → TickMinute stream. [st-3fr]

Reads the ``schwab_internals`` corpus stream written by
scripts/corpus_pull_internals.py, filters one symbol (default $TICK), and
returns minutes in session order. The live path (scripts/mi_gauge.py polling
Schwab minute history) constructs TickMinute rows directly — both paths feed
the same MIGauge, same live==replay contract as the orderflow engine.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date, datetime
from pathlib import Path

from market.corpus.paths import internals_path
from market.internals.gauge import TickMinute

logger = logging.getLogger(__name__)


def read_tick_day(day: _date | Path, symbol: str = "$TICK") -> list[TickMinute]:
    """Load one corpus day of internals minutes for ``symbol``, sorted by ts.
    Raises FileNotFoundError if the day has no internals file."""
    path = day if isinstance(day, Path) else internals_path(day)
    if not path.exists():
        raise FileNotFoundError(f"no internals corpus file at {path}")
    minutes: list[TickMinute] = []
    bad = 0
    for lineno, line in enumerate(path.open(encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if row["data"]["symbol"] != symbol:
                continue
            d = row["data"]
            if d["high"] is None or d["low"] is None or d["close"] is None:
                continue
            minutes.append(TickMinute(
                ts=datetime.fromisoformat(row["provenance"]["ts_candle"]),
                high=int(d["high"]), low=int(d["low"]), close=int(d["close"]),
            ))
        except (KeyError, TypeError, ValueError) as e:
            bad += 1
            logger.warning("%s:%d unparseable internals row (%s) — skipped",
                           path.name, lineno, e)
    minutes.sort(key=lambda m: m.ts)  # stable: equal-ts rows keep file order
    deduped: list[TickMinute] = []
    seen: set[datetime] = set()
    for mm in minutes:
        if mm.ts in seen:
            continue
        seen.add(mm.ts)
        deduped.append(mm)
    if bad or len(deduped) != len(minutes):
        logger.info("read_tick_day %s: %d minutes (%d dupes dropped, %d bad rows)",
                    path.name, len(deduped), len(minutes) - len(deduped), bad)
    # Implausibility guard: a full settled session of $TICK with zero negative
    # minutes means the stale same-day clamped segment got stored (every real
    # session has hundreds). Warn loudly rather than let the gauge run on it.
    if symbol == "$TICK" and len(deduped) >= 300 and all(mm.low >= 0 for mm in deduped):
        logger.warning("%s: no negative $TICK minutes in a full session — "
                       "clamped same-day data? Re-pull with "
                       "scripts/corpus_pull_internals.py --force", path.name)
    return deduped
