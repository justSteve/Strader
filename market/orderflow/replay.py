"""Corpus-day replay reader — the canonical sort + dedup rule (st-uqf).

The corpus ES trade files (``data/corpus/YYYY-MM-DD/databento_glbx_es.jsonl``)
are append-only: multiple pulls for one day may land out of chronological
order (the 7/2 file holds the 13:00–15:00 pull *before* the 08:30–13:00
backfill) and cron retries can duplicate ticks (~8.3k dupes observed on 7/2,
st-f05 hygiene note). This module owns the one rule that turns that file into
the canonical stream every orderflow computation consumes:

  1. **Dedup** re-delivered copies only (:class:`TradeDeduper`): a repeat of
     ``(sequence, ts_event)`` written more than 5 s after the first. That key
     is shared by every fill of one match event, so it is NOT a print's
     identity; repeats written together are kept (st-exmw, 2026-10-01).
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


#: A copy of a key already seen counts as a duplicate only when it was written
#: more than this long after the first (``ts_pull_utc``). [st-exmw]
REDELIVERY_GAP_S = 5.0


class TradeDeduper:
    """Drop re-delivered copies of trades; keep every fill of a match event.

    ``(sequence, ts_event)`` is NOT the identity of a print. One CME match
    event — an aggressor filling several resting orders — produces several
    trade records that share both, sometimes at different sizes, and they
    arrive together in one write batch. Dropping every repeat of the key threw
    away 3–5 % of ES volume, live and in replay, mostly inside sweeps (audit
    2026-10-01: 09-30 lost 95,534 contracts, 5.0 %; the 08-21 09:05 sweep was
    575 contracts, not 538). The same class of loss was fixed once before, when
    the key was ``ts_event`` alone (3.42 % of 08-14, st-n0qm.1).

    What a duplicate actually looks like is a row a LATER write re-delivered —
    a reconnect replaying its window, a cron pull appended twice — so the copy
    carries a ``ts_pull_utc`` well after the original's. Measured over five
    days (07-02, 08-21, 09-10, 09-29, 09-30): 1,600–5,800 key collisions a day,
    none spanning more than 5 s of write time. So: a repeat of a key is kept
    when it was written within ``REDELIVERY_GAP_S`` of the key's first row,
    and dropped when it was written later. A row with no ``ts_pull_utc``
    (fixtures) is treated as written with the first.
    """

    def __init__(self, gap_s: float | None = None) -> None:
        # read at construction, not definition, so a caller reproducing a
        # pre-2026-10-01 log can set the module constant to -1 (every repeat
        # of a key dropped — the old rule)
        self.gap_s = REDELIVERY_GAP_S if gap_s is None else gap_s
        self._first: dict[tuple[int | None, str], float] = {}
        self._pull_cache: dict[str, float] = {}
        self.dropped = 0

    def _pull_epoch(self, row: dict) -> float | None:
        raw = row.get("ts_pull_utc")
        if not raw:
            return None
        v = self._pull_cache.get(raw)
        if v is None:
            v = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
            if len(self._pull_cache) > 4096:
                self._pull_cache.clear()
            self._pull_cache[raw] = v
        return v

    def admit(self, row: dict) -> bool:
        key = dedup_key(row)
        pulled = self._pull_epoch(row)
        first = self._first.get(key)
        if first is None:
            self._first[key] = pulled if pulled is not None else float("-inf")
            return True
        if self.gap_s >= 0 and (pulled is None or first == float("-inf")
                                or pulled - first <= self.gap_s):
            return True             # another fill of the same match event
        self.dropped += 1
        return False


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
    dedup = TradeDeduper()
    bad = 0
    fh = open_corpus_text(path)
    for lineno, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if not dedup.admit(row):
                continue
            trades.append(trade_from_row(row))
        except (KeyError, TypeError, ValueError) as e:
            bad += 1
            logger.warning("%s:%d unparseable corpus row (%s) — skipped",
                           path.name, lineno, e)
    fh.close()

    trades.sort(key=lambda t: (t[0], t[1]))
    if dedup.dropped or bad:
        logger.info("read_corpus_day %s: %d trades (%d re-delivered copies dropped, %d bad rows)",
                    path.name, len(trades), dedup.dropped, bad)
    return [t for _, _, t in trades]
