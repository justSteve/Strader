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
import re
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


# ── raw DBN archive reader (co-qp8cn) ────────────────────────────────────────
# The live collector's JSONL writes action/side/price/size as null on every
# book row (scripts/corpus_stream_databento.py `_book_row`), so a forward-
# collected day cannot drive AbsorptionTracker from the JSONL — measured
# 2026-09-21: 3,838,605 of 3,838,605 rows on 09-18 carry action=null. The raw
# `.dbn.zst` segments teed beside it keep the full MBP-1 record, trades
# included, and are row-for-row the same stream.

_RAW_SEGMENT_RE = re.compile(r"^databento_glbx_es_mbp1\.(\d+)\.dbn(\.zst)?$")


def mbp1_raw_segments(day: _date | Path) -> list[Path]:
    """The day's raw MBP-1 segments in capture order.

    The collector opens a new numbered segment on every (re)connect, so the
    order is numeric — a lexical sort puts segment 10 before segment 2. Accepts
    a date (resolved under ``data/corpus/``) or an explicit directory.
    """
    root = day if isinstance(day, Path) else _CORPUS_ROOT / day.isoformat()
    found: list[tuple[int, Path]] = []
    if root.is_dir():
        for p in root.iterdir():
            m = _RAW_SEGMENT_RE.match(p.name)
            if m:
                found.append((int(m.group(1)), p))
    return [p for _, p in sorted(found)]


def read_mbp1_raw_segment(path: Path) -> Iterator[BookEvent]:
    """Stream one raw DBN segment as ``BookEvent`` rows in stream order.

    One segment is one unbroken connection: a reconnect, and with it any
    contract roll of the continuous symbol, starts a new segment. Callers that
    keep book-dependent state (AbsorptionTracker) should reset it per segment
    rather than carry a defended price across a gap or a roll.

    Symbols come from the in-stream ``SymbolMappingMsg`` records. Raises
    ``ValueError`` on a ``ts_event`` regression inside the segment, the same
    contract as ``read_mbp1_day``.
    """
    import databento as db

    from market.ingest.databento import book_event_from_databento

    if not path.exists():
        raise FileNotFoundError(f"no raw MBP-1 segment at {path}")
    if path.stat().st_size == 0:
        # a connection that dropped before its first byte; the vendor library
        # refuses an empty file, and there is nothing in it to refuse
        logger.info("%s is empty — no events", path.name)
        return

    symbols: dict[int, str] = {}
    prev_ns: int | None = None
    for rec in db.DBNStore.from_file(path):
        kind = type(rec).__name__
        if kind == "SymbolMappingMsg":
            symbols[rec.instrument_id] = rec.stype_out_symbol
            continue
        if kind != "MBP1Msg":
            continue
        ns = rec.ts_event
        if prev_ns is not None and ns < prev_ns:
            raise ValueError(
                f"{path.name}: ts_event regression {ns} < {prev_ns} — "
                f"raw segment is not in event order"
            )
        prev_ns = ns
        yield book_event_from_databento(rec, symbols)
