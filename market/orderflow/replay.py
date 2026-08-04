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

from market.corpus.paths import open_corpus_text, resolve_existing
from market.entities.trade import Trade

logger = logging.getLogger(__name__)

CENTRAL = ZoneInfo("America/Chicago")

_CORPUS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"
_ES_FILENAME = "databento_glbx_es.jsonl"


def es_day_path(day: _date) -> Path:
    """The canonical (uncompressed) ES file for ``day``.

    This is a NAME, not a promise the file exists in that form — a compacted
    day lives at ``<this>.gz``. Use ``has_es_day`` to test presence.
    """
    return _CORPUS_ROOT / day.isoformat() / _ES_FILENAME


def has_es_day(day: _date) -> bool:
    """True if ``day`` has ES trades readable, compacted or not. [st-itky]

    Callers used to write ``es_day_path(day).exists()``, which reads a
    compacted day as an absent one and silently skips it.
    """
    return resolve_existing(es_day_path(day)) is not None


def dedup_key(row: dict) -> tuple[int | None, str]:
    """Identity of a corpus trade row, for duplicate suppression. [st-re1o]

    (sequence, ts_event). Live reconnects can redeliver rows the previous
    connection already wrote, so both the replay reader and the live feeder
    must agree on what "the same trade" means.
    """
    return (row["data"].get("sequence"), row["provenance"]["ts_event"])


def trade_from_row(row: dict) -> tuple[datetime, int, Trade]:
    """Parse one corpus row into ``(ts, sort_seq, Trade)``. [st-re1o]

    THE shared parse. read_corpus_day and the live footprint feeder both go
    through here, so a live-collected bar cannot diverge from the replayed one
    — which is the whole basis of the spec §5 live/replay parity guarantee.
    Raises KeyError/TypeError/ValueError on a malformed row; callers decide
    whether to skip or fail.
    """
    data = row["data"]
    ts_raw = row["provenance"]["ts_event"]
    seq = data.get("sequence")
    ts = datetime.fromisoformat(ts_raw).astimezone(CENTRAL)
    side = data.get("side") or "N"
    if side not in ("B", "A", "N"):
        side = "N"
    return (ts, seq if seq is not None else -1, Trade(
        ts=ts,
        symbol=data.get("symbol") or "",
        instrument_id=int(data.get("instrument_id") or 0),
        price=float(data["price"]),
        size=int(data["size"]),
        side=side,  # type: ignore[arg-type]
        sequence=seq,
    ))


def read_corpus_day(day: _date | Path) -> list[Trade]:
    """Load one corpus day of ES trades in canonical order.

    Accepts a date (resolved under ``data/corpus/``) or an explicit path to a
    JSONL file in the corpus row format (fixtures use this). Returns trades
    deduped and sorted per the module rule. Raises ``FileNotFoundError`` if
    the day has no ES file — a silent empty day would poison downstream
    determinism assumptions.

    Transparently reads a compaction-packed ``.jsonl.gz`` when the plain file
    has been removed.
    """
    path = day if isinstance(day, Path) else es_day_path(day)

    trades: list[tuple[datetime, int, Trade]] = []
    seen: set[tuple[int | None, str]] = set()
    dupes = 0
    bad = 0
    fh = open_corpus_text(path)
    for lineno, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            key = dedup_key(row)
            if key in seen:
                dupes += 1
                continue
            seen.add(key)
            trades.append(trade_from_row(row))
        except (KeyError, TypeError, ValueError) as e:
            bad += 1
            logger.warning("%s:%d unparseable corpus row (%s) — skipped",
                           path.name, lineno, e)
    fh.close()

    trades.sort(key=lambda t: (t[0], t[1]))
    if dupes or bad:
        logger.info("read_corpus_day %s: %d trades (%d duplicates dropped, %d bad rows)",
                    path.name, len(trades), dupes, bad)
    return [t for _, _, t in trades]
