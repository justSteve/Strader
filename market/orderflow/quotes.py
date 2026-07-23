"""Corpus MBP-1 reader — streaming, order-checked (st-9vl).

The MBP-1 corpus files (``data/corpus/YYYY-MM-DD/databento_glbx_es_mbp1.jsonl``)
are large — a full ES RTH session is millions of book events, gigabytes of
JSONL — so unlike the trades reader (``replay.read_corpus_day``) this one
streams: it yields ``BookEvent`` rows lazily and never materializes the day.

That is safe because each MBP-1 file comes from a single ``get_range`` pull,
which Databento returns in event order — the multi-pull disorder the trades
sort rule exists for cannot occur. The reader still *verifies* the assumption:
a timestamp regression raises immediately rather than silently corrupting
downstream episode state. If MBP-1 days ever become multi-pull appends, they
need the replay.py dedup+sort treatment first (compact step), not a silent
widening of this reader.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import date as _date, datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from market.entities.book import BookEvent

logger = logging.getLogger(__name__)

CENTRAL = ZoneInfo("America/Chicago")

_CORPUS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"
_MBP1_FILENAME = "databento_glbx_es_mbp1.jsonl"

_ACTIONS = {"A", "C", "M", "T", "F", "R", "N"}
_SIDES = {"B", "A", "N"}


def mbp1_day_path(day: _date) -> Path:
    return _CORPUS_ROOT / day.isoformat() / _MBP1_FILENAME


def read_mbp1_day(day: _date | Path) -> Iterator[BookEvent]:
    """Stream one corpus day of MBP-1 book events in file order.

    Accepts a date (resolved under ``data/corpus/``) or an explicit path to a
    JSONL file in the corpus row format (fixtures use this). Raises
    ``FileNotFoundError`` for a missing file and ``ValueError`` on a timestamp
    regression (single-pull ordering assumption violated). Unparseable rows
    are logged and skipped, matching the trades reader's tolerance.
    """
    path = day if isinstance(day, Path) else mbp1_day_path(day)
    if not path.exists():
        raise FileNotFoundError(f"no MBP-1 corpus file at {path}")

    prev_ts: datetime | None = None
    bad = 0
    n = 0
    # committed fixtures are gzipped — MBP-1 density makes raw slices tens of MB
    opener = (lambda: gzip.open(path, "rt", encoding="utf-8")) \
        if path.suffix == ".gz" else (lambda: path.open(encoding="utf-8"))
    with opener() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                data = row["data"]
                ts = datetime.fromisoformat(row["provenance"]["ts_event"]).astimezone(CENTRAL)
                action = data.get("action") or "N"
                if action not in _ACTIONS:
                    action = "N"
                side = data.get("side") or "N"
                if side not in _SIDES:
                    side = "N"
                ev = BookEvent(
                    ts=ts,
                    symbol=data.get("symbol") or "",
                    instrument_id=int(data.get("instrument_id") or 0),
                    action=action,  # type: ignore[arg-type]
                    side=side,      # type: ignore[arg-type]
                    price=None if data.get("price") is None else float(data["price"]),
                    size=None if data.get("size") is None else int(data["size"]),
                    bid_px=None if data.get("bid_px") is None else float(data["bid_px"]),
                    ask_px=None if data.get("ask_px") is None else float(data["ask_px"]),
                    bid_sz=None if data.get("bid_sz") is None else int(data["bid_sz"]),
                    ask_sz=None if data.get("ask_sz") is None else int(data["ask_sz"]),
                    bid_ct=None if data.get("bid_ct") is None else int(data["bid_ct"]),
                    ask_ct=None if data.get("ask_ct") is None else int(data["ask_ct"]),
                    sequence=data.get("sequence"),
                )
            except (KeyError, TypeError, ValueError) as e:
                bad += 1
                logger.warning("%s:%d unparseable MBP-1 row (%s) — skipped",
                               path.name, lineno, e)
                continue
            if prev_ts is not None and ev.ts < prev_ts:
                raise ValueError(
                    f"{path.name}:{lineno} timestamp regression "
                    f"{ev.ts.isoformat()} < {prev_ts.isoformat()} — "
                    f"multi-pull file? needs dedup+sort compaction first"
                )
            prev_ts = ev.ts
            n += 1
            yield ev
    if bad:
        logger.info("read_mbp1_day %s: %d events (%d bad rows skipped)",
                    path.name, n, bad)
