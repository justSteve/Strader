"""Corpus-day replay reader — the canonical sort + dedup rule (st-uqf).

The corpus ES trade files (``data/corpus/YYYY-MM-DD/databento_glbx_es.jsonl``)
are append-only: multiple pulls for one day may land out of chronological
order (the 7/2 file holds the 13:00–15:00 pull *before* the 08:30–13:00
backfill) and cron retries can duplicate ticks (~8.3k dupes observed on 7/2,
st-f05 hygiene note). This module owns the one rule that turns that file into
the canonical stream every orderflow computation consumes:

  1. **Dedup** on ``(sequence, ts_event)`` — the venue sequence number plus
     the event timestamp uniquely identify a print; later duplicates dropped.
  2. **Sort** by ``(ts_event, sequence)`` — event time first, venue sequence
     as the equal-timestamp tie-break (spec §4 determinism rules).

Live-parity note: the live adapter reads an already-ordered exchange stream,
so it needs neither step; both paths deliver the same canonical order to
``build_bars`` / the engine.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from market.entities.trade import Trade

logger = logging.getLogger(__name__)

CENTRAL = ZoneInfo("America/Chicago")

_CORPUS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"
_ES_FILENAME = "databento_glbx_es.jsonl"


def es_day_path(day: _date) -> Path:
    return _CORPUS_ROOT / day.isoformat() / _ES_FILENAME


def read_corpus_day(day: _date | Path) -> list[Trade]:
    """Load one corpus day of ES trades in canonical order.

    Accepts a date (resolved under ``data/corpus/``) or an explicit path to a
    JSONL file in the corpus row format (fixtures use this). Returns trades
    deduped and sorted per the module rule. Raises ``FileNotFoundError`` if
    the day has no ES file — a silent empty day would poison downstream
    determinism assumptions.
    """
    path = day if isinstance(day, Path) else es_day_path(day)
    if not path.exists():
        raise FileNotFoundError(f"no ES corpus file at {path}")

    trades: list[tuple[datetime, int, Trade]] = []
    seen: set[tuple[int | None, str]] = set()
    dupes = 0
    bad = 0
    for lineno, line in enumerate(path.open(encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            data = row["data"]
            ts_raw = row["provenance"]["ts_event"]
            seq = data.get("sequence")
            key = (seq, ts_raw)
            if key in seen:
                dupes += 1
                continue
            seen.add(key)
            ts = datetime.fromisoformat(ts_raw).astimezone(CENTRAL)
            side = data.get("side") or "N"
            if side not in ("B", "A", "N"):
                side = "N"
            trades.append((ts, seq if seq is not None else -1, Trade(
                ts=ts,
                symbol=data.get("symbol") or "",
                instrument_id=int(data.get("instrument_id") or 0),
                price=float(data["price"]),
                size=int(data["size"]),
                side=side,  # type: ignore[arg-type]
                sequence=seq,
            )))
        except (KeyError, TypeError, ValueError) as e:
            bad += 1
            logger.warning("%s:%d unparseable corpus row (%s) — skipped",
                           path.name, lineno, e)

    trades.sort(key=lambda t: (t[0], t[1]))
    if dupes or bad:
        logger.info("read_corpus_day %s: %d trades (%d duplicates dropped, %d bad rows)",
                    path.name, len(trades), dupes, bad)
    return [t for _, _, t in trades]
