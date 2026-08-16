"""Trade source seam — one place that turns a corpus day into ordered, deduped
``Trade`` objects for anyone who is not the live feeder. [st-n0qm.4, plan §2a]

The feeder tails and follows (``scripts/live_footprint_feed.py``:
``tail_rows`` → ``ordered_trades``); replay and any offline consumer read a
whole day. Both already share ``replay.trade_from_row`` / ``replay.dedup_key``;
this module gives the offline path a name and a start-time filter so the
anchored profile's prior-day pre-seed and, later, the premarket page read
through the same door instead of parsing rows themselves.

Deliberately NOT built here: Schwab or GexBot adapters. Schwab supplies bars,
GexBot supplies no prints — neither is a trade source, and a stub interface
for a source that cannot exist is the over-building the plan's seam-admission
guard exists to stop.
"""
from __future__ import annotations

from datetime import date as _date, datetime
from pathlib import Path
from typing import Iterator

from market.entities.trade import Trade
from market.orderflow.replay import read_corpus_day


def iter_trades(day: _date | Path, *, start_ts: datetime | None = None,
                end_ts: datetime | None = None) -> Iterator[Trade]:
    """Yield the day's trades in canonical order (deduped, sorted), optionally
    windowed to ``start_ts <= ts < end_ts``. Reads ``.jsonl`` or the compacted
    ``.jsonl.gz`` transparently (``read_corpus_day``). Raises FileNotFoundError
    when the day has no ES file — a silent empty day would read as an empty
    profile, which is a lie about the tape."""
    for t in read_corpus_day(day):
        if start_ts is not None and t.ts < start_ts:
            continue
        if end_ts is not None and t.ts >= end_ts:
            break
        yield t
