"""OPRA read-time duplicate guard. [st-c078]

The ES tape has dropped duplicates at the read since st-uqf; the OPRA options
tape had no equivalent, so a batch pull that double-fired (2026-07-20 —
1,024,302 rows carrying 512,151 prints) doubled every count and every size
total that any of eight consumers computed over it. These tests pin the three
properties that make the guard safe to leave on:

  * a doubled tape yields each print exactly once,
  * a clean tape passes through untouched — the guard cannot cost a real
    print, which is the whole reason the key is as wide as it is,
  * the escape hatch turns it off, by argument and by environment.

The fixtures are tiny hand-built tapes in the corpus row shape. The real
proportions they stand in for were measured on the corpus: 0 key collisions
across 325,730 rows of the clean 2026-07-21, exactly 50% dropped on the
doubled 2026-07-20.
"""
from __future__ import annotations

import gzip
import json
import logging

import pytest

from market.corpus.opra import (
    OpraDedup, dedup_default, opra_dedup_key, opra_key_fields, read_opra_rows,
)


def _row(ts: str, iid: int, price: float, size: int, seq: int,
         *, symbol: str = "SPXW  260721C07510000", pull: str = "PULL-A") -> dict:
    """One corpus row in the shape corpus_pull_databento.py writes."""
    return {
        "ts_pull_utc": pull,
        "stream": "databento_opra",
        "provenance": {"dataset": "OPRA.PILLAR", "schema": "trades",
                       "parent_symbol": "SPXW.OPT", "ts_event": ts},
        "data": {"symbol": symbol, "instrument_id": iid, "price": price,
                 "size": size, "side": "N", "action": "T", "sequence": seq,
                 "flags": 192},
    }


CLEAN = [
    _row("2026-07-21T18:00:00.038767292+00:00", 1325414995, 1.35, 1, 1825331000),
    _row("2026-07-21T18:00:00.038854808+00:00", 1342179097, 1.75, 1, 1791233072,
         symbol="SPXW  260730C07725000"),
    _row("2026-07-21T18:00:00.038917634+00:00", 1325419135, 0.55, 3, 1825331017,
         symbol="SPXW  260727C07675000"),
]


def _write(path, rows, *, gz: bool = False):
    text = "".join(json.dumps(r) + "\n" for r in rows)
    if gz:
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The key
# --------------------------------------------------------------------------

def test_the_two_key_forms_induce_the_same_equivalence():
    """The tuple form and the string form must agree on every pair.

    They exist because a caller who wants to inspect the parts needs the
    tuple, while the read guard needs the string's smaller footprint. Two
    forms are two chances to drift; this is the pin. The fields are named in
    one place — ``opra_key_fields`` — and the string form is built from it,
    so a drift would have to be introduced deliberately.
    """
    rows = [
        _row("2026-07-21T18:00:00.1+00:00", 1, 1.35, 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", 1, 1.35, 1, 900, pull="PULL-B"),
        _row("2026-07-21T18:00:00.1+00:00", 1, 1.35, 1, 901),
        _row("2026-07-21T18:00:00.2+00:00", 1, 1.35, 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", 2, 1.35, 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", 1, 1.40, 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", 1, 1.35, 2, 900),
        _row("2026-07-21T18:00:00.1+00:00", 1, 1, 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", 1, 1.0, 1, 900),
        # The pathological pairs: an absent field against text that renders
        # the same way. Without a distinct absent-field token these collide in
        # the string form only, and the two forms stop agreeing.
        _row("2026-07-21T18:00:00.1+00:00", 1, None, 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", 1, "", 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", 1, "None", 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", None, 1.35, 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", "None", 1.35, 1, 900),
        _row("2026-07-21T18:00:00.1+00:00", 1, 1.35, 1, None),
        _row("2026-07-21T18:00:00.1+00:00", 1, 1.35, 1, "None"),
    ]
    for a in rows:
        for b in rows:
            assert (opra_key_fields(a) == opra_key_fields(b)) is \
                   (opra_dedup_key(a) == opra_dedup_key(b))


def test_key_fields_are_the_five_named_in_the_docstring():
    r = _row("2026-07-21T18:00:00.1+00:00", 1325414995, 1.35, 1, 1825331000)
    assert opra_key_fields(r) == (
        "2026-07-21T18:00:00.1+00:00", 1325414995, 1.35, 1, 1825331000)


def test_key_fields_are_all_none_for_a_row_with_nothing_identifying():
    """corpus_duplicate_sweep skips such a row rather than bucketing it."""
    assert opra_key_fields({}) == (None,) * 5


def test_key_separates_prints_that_differ_in_any_field():
    """Two prints alike in all but one field must key apart.

    Every field is load-bearing or it should not be in the key. Dropping
    ``sequence`` alone collides 4.97% of the clean 2026-07-21 tape — distinct
    fills of the same size at the same price on the same contract in the same
    nanosecond, which are real prints.
    """
    base = _row("2026-07-21T18:00:00.038767292+00:00", 1325414995, 1.35, 1, 1825331000)
    k = opra_dedup_key(base)
    variants = [
        _row("2026-07-21T18:00:00.038767293+00:00", 1325414995, 1.35, 1, 1825331000),
        _row("2026-07-21T18:00:00.038767292+00:00", 1325414996, 1.35, 1, 1825331000),
        _row("2026-07-21T18:00:00.038767292+00:00", 1325414995, 1.40, 1, 1825331000),
        _row("2026-07-21T18:00:00.038767292+00:00", 1325414995, 1.35, 2, 1825331000),
        _row("2026-07-21T18:00:00.038767292+00:00", 1325414995, 1.35, 1, 1825331001),
    ]
    assert len({opra_dedup_key(v) for v in variants} | {k}) == 6


def test_key_ignores_ts_pull_utc():
    """The two halves of a doubled day differ ONLY in ts_pull_utc.

    On 2026-07-20 the stamps are thirteen seconds apart. A key that included
    the pull stamp would call every duplicate a distinct print, which is the
    one way this guard could silently do nothing.
    """
    a = _row("2026-07-21T18:00:00.038767292+00:00", 1325414995, 1.35, 1, 1825331000,
             pull="2026-07-21T11:31:55Z")
    b = _row("2026-07-21T18:00:00.038767292+00:00", 1325414995, 1.35, 1, 1825331000,
             pull="2026-07-21T11:32:08Z")
    assert opra_dedup_key(a) == opra_dedup_key(b)


def test_key_treats_int_and_float_encodings_of_one_number_alike():
    """``2`` and ``2.0`` are the same price and must key the same."""
    a = _row("2026-07-21T18:00:00.1+00:00", 1, 2, 3, 4)
    b = _row("2026-07-21T18:00:00.1+00:00", 1, 2.0, 3, 4)
    assert opra_dedup_key(a) == opra_dedup_key(b)


def test_key_never_raises_on_a_malformed_row():
    """A row the key cannot read is let through, not dropped.

    A surviving duplicate is a wrong count; a wrongly dropped print is lost
    data. The guard fails in the recoverable direction.
    """
    for bad in ({}, {"data": None, "provenance": None},
                {"data": {"price": "n/a"}, "provenance": {}}):
        assert isinstance(opra_dedup_key(bad), str)


def test_key_falls_back_to_symbol_when_instrument_id_is_absent():
    """instrument_id was on 100% of 2026-07-21's rows; symbol covers the gap.

    The fallback can only miss a duplicate, never conflate two contracts.
    """
    a = _row("2026-07-21T18:00:00.1+00:00", 1, 1.0, 1, 9,
             symbol="SPXW  260721C07510000")
    b = _row("2026-07-21T18:00:00.1+00:00", 1, 1.0, 1, 9,
             symbol="SPXW  260721P07510000")
    del a["data"]["instrument_id"], b["data"]["instrument_id"]
    assert opra_dedup_key(a) != opra_dedup_key(b)


# --------------------------------------------------------------------------
# The guard, over a tape
# --------------------------------------------------------------------------

def test_doubled_tape_yields_each_print_once(tmp_path):
    """The 2026-07-20 shape in miniature: the whole file appended twice."""
    second_pull = [dict(r, ts_pull_utc="PULL-B") for r in CLEAN]
    p = _write(tmp_path / "databento_opra.jsonl", CLEAN + second_pull)

    rows = [row for _line, row in read_opra_rows(p)]

    assert len(rows) == 3
    assert [r["data"]["sequence"] for r in rows] == [1825331000, 1791233072, 1825331017]
    # File order is preserved: the guard filters, it does not sort.
    assert [r["ts_pull_utc"] for r in rows] == ["PULL-A"] * 3


def test_clean_tape_passes_through_untouched(tmp_path):
    """The property that makes the guard safe to leave on by default."""
    p = _write(tmp_path / "databento_opra.jsonl", CLEAN)
    guarded = [row for _line, row in read_opra_rows(p)]
    raw = [row for _line, row in read_opra_rows(p, dedup=False)]
    assert guarded == raw == CLEAN


def test_escape_hatch_argument_keeps_every_row(tmp_path):
    p = _write(tmp_path / "databento_opra.jsonl", CLEAN + CLEAN)
    assert len(list(read_opra_rows(p, dedup=False))) == 6
    assert len(list(read_opra_rows(p, dedup=True))) == 3


def test_escape_hatch_environment_flips_the_default(tmp_path, monkeypatch):
    """STRADER_OPRA_DEDUP=0 reproduces a pre-guard number without a code edit."""
    p = _write(tmp_path / "databento_opra.jsonl", CLEAN + CLEAN)

    monkeypatch.setenv("STRADER_OPRA_DEDUP", "0")
    assert dedup_default() is False
    assert len(list(read_opra_rows(p))) == 6
    # An explicit argument still wins over the environment.
    assert len(list(read_opra_rows(p, dedup=True))) == 3

    monkeypatch.setenv("STRADER_OPRA_DEDUP", "1")
    assert dedup_default() is True
    assert len(list(read_opra_rows(p))) == 3


def test_reader_handles_a_compacted_day(tmp_path):
    """corpus_compact_databento gzips a finished day and removes the source."""
    _write(tmp_path / "databento_opra.jsonl.gz", CLEAN + CLEAN, gz=True)
    # Called with the PLAIN name, which is what every consumer holds.
    rows = list(read_opra_rows(tmp_path / "databento_opra.jsonl"))
    assert len(rows) == 3


def test_reader_names_both_candidates_when_the_day_is_absent(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        list(read_opra_rows(tmp_path / "databento_opra.jsonl"))
    assert "databento_opra.jsonl" in str(e.value) and ".gz" in str(e.value)


def test_reader_skips_blank_and_unparseable_lines(tmp_path):
    p = tmp_path / "databento_opra.jsonl"
    p.write_text("\n".join([json.dumps(CLEAN[0]), "", "{not json", "[]",
                            json.dumps(CLEAN[1])]) + "\n", encoding="utf-8")
    rows = [row for _line, row in read_opra_rows(p)]
    assert rows == [CLEAN[0], CLEAN[1]]


def test_reader_yields_the_raw_line_alongside_the_row(tmp_path):
    """Two consumers do substring work on the text and must keep it."""
    p = _write(tmp_path / "databento_opra.jsonl", CLEAN)
    line, row = next(iter(read_opra_rows(p)))
    assert '"ts_event": "' in line
    assert json.loads(line) == row


# --------------------------------------------------------------------------
# The log line
# --------------------------------------------------------------------------

def test_logs_one_line_naming_dropped_and_total(tmp_path, caplog):
    p = _write(tmp_path / "databento_opra.jsonl", CLEAN + CLEAN)
    with caplog.at_level(logging.INFO, logger="market.corpus.opra"):
        list(read_opra_rows(p))
    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 1
    assert lines[0].startswith("opra: 3 duplicate rows dropped of 6")


def test_silent_on_a_clean_tape(tmp_path, caplog):
    """Same silence-on-clean as ordered_trades and read_corpus_day."""
    p = _write(tmp_path / "databento_opra.jsonl", CLEAN)
    with caplog.at_level(logging.INFO, logger="market.corpus.opra"):
        list(read_opra_rows(p))
    assert caplog.records == []


def test_log_fires_when_the_consumer_breaks_out_early(tmp_path, caplog):
    """trough_time_volume_analysis breaks at the end of its window.

    The report rides the generator's ``finally``, so an abandoned read still
    accounts for what it dropped instead of going quiet. The tape here repeats
    its first row, so a duplicate is already behind the reader when the
    consumer walks away.
    """
    p = _write(tmp_path / "databento_opra.jsonl",
               [CLEAN[0], dict(CLEAN[0], ts_pull_utc="PULL-B"), CLEAN[1], CLEAN[2]])
    with caplog.at_level(logging.INFO, logger="market.corpus.opra"):
        gen = read_opra_rows(p)
        taken = 0
        for _ in gen:
            taken += 1
            if taken == 2:   # the duplicate lies between yield 1 and yield 2
                break
        gen.close()          # GeneratorExit -> finally -> report
    # Rows presented before the walk-away: the two that were yielded plus the
    # duplicate the reader swallowed between them. The generator is parked ON
    # its yield, so the fourth row was never read.
    assert [r.getMessage() for r in caplog.records] == [
        "opra: 1 duplicate rows dropped of 3 [databento_opra.jsonl]"]

    # And with the file exhausted rather than abandoned, the full count.
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="market.corpus.opra"):
        assert len(list(read_opra_rows(p))) == 3
    assert [r.getMessage() for r in caplog.records] == [
        "opra: 1 duplicate rows dropped of 4 [databento_opra.jsonl]"]


def test_report_is_idempotent(tmp_path, caplog):
    """A consumer's explicit report() and a generator finally must not double."""
    guard = OpraDedup(label="day")
    for r in CLEAN + CLEAN:
        guard.is_duplicate(r)
    with caplog.at_level(logging.INFO, logger="market.corpus.opra"):
        first = guard.report()
        second = guard.report()
    assert first == "opra: 3 duplicate rows dropped of 6"
    assert second is None
    assert len(caplog.records) == 1


# --------------------------------------------------------------------------
# The stateful guard, for the two consumers that prefilter
# --------------------------------------------------------------------------

def test_guard_counts_only_rows_presented_to_it():
    """final_hour_premium asks about the rows it was going to parse anyway."""
    guard = OpraDedup()
    kept = [r for r in CLEAN + CLEAN if not guard.is_duplicate(r)]
    assert len(kept) == 3
    assert (guard.rows, guard.dupes) == (6, 3)
    assert guard.summary() == "opra: 3 duplicate rows dropped of 6"


def test_guard_disabled_keeps_everything_and_still_counts_rows():
    guard = OpraDedup(dedup=False)
    kept = [r for r in CLEAN + CLEAN if not guard.is_duplicate(r)]
    assert len(kept) == 6
    assert (guard.rows, guard.dupes) == (6, 0)
    assert guard.report() is None


def test_guard_streams_rather_than_buffering(tmp_path):
    """Only the key set is retained: rows are not held.

    A 367 MB day is 1.02M rows; buffering them would cost gigabytes. This
    asserts the shape (a generator), which is what keeps the footprint to the
    key set the module docstring measures.
    """
    import types
    p = _write(tmp_path / "databento_opra.jsonl", CLEAN)
    assert isinstance(read_opra_rows(p), types.GeneratorType)
