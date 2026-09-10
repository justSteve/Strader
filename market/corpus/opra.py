"""Read-time duplicate guard for the OPRA options-trade tape. [st-c078]

WHY
    ``data/corpus/<day>/databento_opra.jsonl`` is append-only, and the batch
    puller has no idempotence: a pull that runs twice for one day writes the
    day's prints twice. 2026-07-20 is that day — 1,024,302 rows carrying
    512,151 distinct prints, two ``ts_pull_utc`` stamps thirteen seconds
    apart. Every count and every size total over it comes out exactly 2x;
    VWAP-type ratios happen to survive because numerator and denominator
    double together, which is precisely what makes the corruption quiet.

    The ES trade tape has had a guard since st-uqf: ``market.orderflow.replay``
    dedups on ``(sequence, ts_event)``, and ``ordered_trades`` applies the same
    key in the live feeder, so a doubled ES file is harmless to consumers. The
    OPRA tape had no equivalent — every consumer hand-rolled its own read loop
    and none of them dropped anything. This module is the missing half.

    Repairing the one bad day is a separate job. This guard is what makes the
    read path safe *regardless* of what is on disk, including the next time a
    pull double-fires before anyone notices.

WHAT
    :func:`opra_dedup_key`  the ONE definition of "the same OPRA print".
    :class:`OpraDedup`      a stateful guard for a loop that already parses.
    :func:`read_opra_rows`  gz-aware streaming reader yielding ``(line, row)``.

    Two entry points because the consumers split two ways. Most parse every
    row and want the reader. Two (``final_hour_premium``,
    ``final_fifteen_premium``) prefilter on the raw line with a substring test
    and parse only the survivors — for those, forcing a parse on every row
    would cost more than the guard is worth, so they hold an ``OpraDedup`` and
    ask it about the rows they were going to parse anyway. Both paths share one
    key, one counter and one log line.

THE KEY
    ``(ts_event, instrument_id, price, size, sequence)`` — the ES key
    ``(sequence, ts_event)`` widened by the three fields that identify *which*
    contract printed and at what. OPRA multiplexes ~4,200 SPXW instruments
    across participant channels whose sequence spaces are independent, so
    sequence alone does not identify a print the way it does on the single-
    instrument ES tape.

    Measured 2026-09-10 on the corpus, not assumed:

      2026-07-21 (clean)    325,730 rows   0 key collisions   (0.0000%)
      2026-07-20 (doubled) 1,024,302 rows  512,151 dropped    (50.0000%)

    Zero collisions on the clean day is the claim that matters: the guard
    drops only exact key collisions, so on a clean tape it is a no-op and
    cannot cost a real print. (For contrast, dropping ``sequence`` from the
    key collides 4.97% of the clean day's prints — distinct fills of the same
    size at the same price on the same contract in the same nanosecond are
    common at OPRA message rates. Those are real prints and must survive.)

MEMORY
    A per-day set of keys, streamed: nothing else is retained. One key is one
    ``str``, and it costs about 160 bytes of peak RSS including the set slot.
    All figures below were measured on this box 2026-09-10, not estimated.

    Isolated — a parse loop over the 367 MB / 1,024,302-row 2026-07-20 file,
    holding nothing else, so this is the guard's own footprint:

        guard off                12.1 MB peak RSS
        guard on (str key)       83.2 MB      512,151 keys retained
        guard on (tuple key)    153.7 MB      the shape not taken

    A tuple key is 1.8x the memory for 0.4s less CPU. ``final_hour_premium``
    and ``final_fifteen_premium`` run ``Pool(6)`` over the whole corpus, so six
    simultaneous copies of that difference decided it.

    End to end the cost is smaller than the isolated number, because dropping
    half the rows also halves what the consumer builds from them. Whole runs of
    ``fly_replay.py``, peak RSS and wall clock, guard off then on:

        2026-07-21  325,730 rows, 0 dropped        45 -> 99 MB   3.5 -> 4.7 s
        2026-07-20  1,024,302 rows, 512,151 dropped 108 -> 130 MB 15.4 -> 9.4 s

    So the clean day pays about 54 MB and a second — that is the real price of
    leaving the guard on — and the doubled day comes out *faster*, because the
    work it no longer does exceeds the work the guard adds.

ESCAPE HATCH
    ``dedup=False`` on either entry point. ``STRADER_OPRA_DEDUP=0`` in the
    environment flips the default for a whole process without touching a call
    site, which is how you reproduce a pre-guard number; an explicit argument
    always wins over the environment.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterator, Mapping

from market.corpus.paths import open_corpus_text

logger = logging.getLogger(__name__)

__all__ = ["opra_key_fields", "opra_dedup_key", "OpraDedup", "read_opra_rows",
           "dedup_default"]

_OFF = {"0", "false", "no", "off"}

# Absent-field token for the string key. A NUL cannot come out of ``str()`` on
# a JSON number, nor out of any symbol Databento writes, so an absent field can
# never be confused with a present one whose text happens to read "None" or "".
# Without it the string form and the tuple form disagree about a row carrying
# ``price: null`` versus ``price: ""`` — a pathological pair, but the two forms
# claiming the same equivalence relation is a promise this module makes.
_NULL = "\x00"


def dedup_default() -> bool:
    """Whether the guard is on when a caller does not say. [st-c078]

    True unless ``STRADER_OPRA_DEDUP`` names a falsey value. Read per call, not
    at import, so a test can set it with ``monkeypatch.setenv`` and a long-lived
    process picks up a change without a restart.
    """
    return (os.environ.get("STRADER_OPRA_DEDUP") or "").strip().lower() not in _OFF


def _canon_num(v) -> str:
    """Canonical text for a JSON number, so ``2`` and ``2.0`` key the same.

    The two pulls of a doubled day go through the same writer and encode a
    price identically, so this is belt-and-braces rather than an observed
    hazard — but a key that says two encodings of one number are different
    prints would let a duplicate through, and that is the failure this module
    exists to stop. Non-numeric or absent values fall back to their text.
    """
    if v is None:
        return _NULL
    try:
        return repr(float(v))
    except (TypeError, ValueError):
        return str(v)


def opra_key_fields(row: Mapping) -> tuple:
    """The five fields that identify an OPRA print, as raw values. [st-c078]

    ``(ts_event, instrument_id, price, size, sequence)`` — see THE KEY in the
    module docstring for why each field is in it and what the collision rate
    measures out at. THE definition; :func:`opra_dedup_key` is its compact
    form and nothing else in the repo should re-derive it.

    ``instrument_id`` is the venue's numeric contract id; it was present on
    100% of rows and mapped 1:1 onto ``symbol`` across the 325,730 rows of
    2026-07-21 (4,179 distinct ids, none carrying two symbols). ``symbol``
    stands in if it is ever absent, which can only *miss* a duplicate — it
    cannot make two different contracts key alike.

    Never raises: a malformed row keys off whatever it has. A row that cannot
    be keyed reliably is one the guard lets through, which is the safe
    direction — a surviving duplicate is a wrong count, a wrongly dropped
    print is lost data. A row with nothing identifying at all keys as all-None,
    which a caller can test for.

    Returned as a tuple for a caller that wants to inspect or filter the parts
    (``scripts/measurement/corpus_duplicate_sweep.py`` skips an all-None key
    that way). The read guard uses :func:`opra_dedup_key` instead: over the
    512,151 distinct keys of the 2026-07-20 file, a set of these tuples
    measured 153.7 MB against the string form's 83.2 MB.
    """
    data = row.get("data") or {}
    prov = row.get("provenance") or {}
    iid = data.get("instrument_id")
    if iid is None:
        iid = data.get("symbol")
    return (prov.get("ts_event"), iid, data.get("price"),
            data.get("size"), data.get("sequence"))


def opra_dedup_key(row: Mapping) -> str:
    """Compact canonical form of :func:`opra_key_fields` — what the guard stores.

    Same equivalence relation, half the memory: one ``str`` per distinct print
    rather than a tuple of five boxed objects. Numbers are canonicalised so the
    two forms agree that ``2`` and ``2.0`` are one price (the tuple form gets
    that free from Python's numeric equality).
    """
    ts, iid, price, size, seq = opra_key_fields(row)
    return "|".join((
        _NULL if ts is None else str(ts),
        _NULL if iid is None else str(iid),
        _canon_num(price),
        _canon_num(size),
        _NULL if seq is None else str(seq),
    ))


class OpraDedup:
    """Read-time duplicate guard over a stream of parsed OPRA rows. [st-c078]

    For a loop that already parses each row::

        guard = OpraDedup(label=path.name)
        for line in fh:
            row = json.loads(line)
            if guard.is_duplicate(row):
                continue
            ...
        guard.report()

    ``report()`` emits ``opra: N duplicate rows dropped of M`` at INFO, once,
    and only when N is non-zero — the same shape and the same silence-on-clean
    that ``ordered_trades`` and ``read_corpus_day`` use for the ES tape. M is
    the number of rows *presented to the guard*, which for a caller that
    prefilters is smaller than the row count of the file.
    """

    def __init__(self, *, dedup: bool | None = None, label: str = "") -> None:
        self.enabled = dedup_default() if dedup is None else bool(dedup)
        self.label = label
        self.rows = 0
        self.dupes = 0
        self._seen: set[str] = set()
        self._reported = False

    def is_duplicate(self, row: Mapping) -> bool:
        """True if ``row`` was already seen, and the caller should skip it."""
        self.rows += 1
        if not self.enabled:
            return False
        key = opra_dedup_key(row)
        if key in self._seen:
            self.dupes += 1
            return True
        self._seen.add(key)
        return False

    def summary(self) -> str:
        return f"opra: {self.dupes} duplicate rows dropped of {self.rows}"

    def report(self) -> str | None:
        """Log the one line if anything was dropped; return it, else None.

        Idempotent — a generator's ``finally`` and an explicit call from the
        consumer must not both log.
        """
        if self._reported or not self.dupes:
            self._reported = True
            return None
        self._reported = True
        msg = self.summary()
        logger.info("%s%s", msg, f" [{self.label}]" if self.label else "")
        return msg


def read_opra_rows(path: Path | str, *, dedup: bool | None = None,
                   label: str | None = None) -> Iterator[tuple[str, dict]]:
    """Stream ``(raw_line, parsed_row)`` from an OPRA tape, duplicates dropped.

    Transparently reads a compaction-packed ``.jsonl.gz`` (via
    ``market.corpus.paths.open_corpus_text``), so a consumer that used to test
    ``path.exists()`` on the plain name stops reading a compacted day as a
    missing one. Raises ``FileNotFoundError`` naming both candidates when
    neither exists.

    The raw line is yielded alongside the parsed row because two consumers do
    real work on the text — a ``"SPXW  260721" in line`` expiry prefilter and a
    substring clock read that beats parsing a timestamp. They keep both; they
    just stop parsing the row a second time.

    Unparseable lines are counted and skipped with one WARNING at the end, not
    one per line: a truncated tail on a file being written should not produce a
    million log records.

    Streams. The only thing held across the file is the key set — see MEMORY.
    """
    p = Path(path)
    guard = OpraDedup(dedup=dedup, label=label if label is not None else p.name)
    bad = 0
    fh = open_corpus_text(p)
    try:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                bad += 1
                continue
            if not isinstance(row, dict):
                bad += 1
                continue
            if guard.is_duplicate(row):
                continue
            yield line, row
    finally:
        fh.close()
        guard.report()
        if bad:
            logger.warning("opra: %d unparseable rows skipped in %s", bad, p.name)
