"""read_opra_day reads through the OPRA duplicate guard. [st-c078]

This reader is the one that feeds strader.marks — the estimated-mark
calibration and its holdout validation — and it is the only OPRA consumer that
publishes a *measured coverage* claim alongside its numbers: rows in the file,
first and last print minute, rows per CT hour. That claim travels into the
write-up Steve reads.

So the guard has to sit ahead of the coverage tally, not merely ahead of
``prints``. On the doubled 2026-07-20 tape an unguarded read reports 1,024,302
rows for a day holding 512,151 prints, and a bound that is wrong by 2x is
worse than no bound: it reads as evidence.

The tests below use the same synthetic-corpus helper the estimated-mark script
tests use, so a change to the corpus row shape breaks both together.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from strader.marks.minute_paths import read_opra_day, resolve_day_file
from tests.helpers.estimated_mark_corpus import write_day

DAY = "2025-11-03"


def _double_in_place(path: Path) -> int:
    """Append the file to itself, as a batch pull that fires twice does.

    Returns the original row count. The copy is byte-identical here, which is
    the harder case: nothing but the guard's key can tell the halves apart.
    """
    opener = (lambda m: gzip.open(path, m + "t", encoding="utf-8")) if path.suffix == ".gz" \
        else (lambda m: open(path, m, encoding="utf-8"))
    with opener("r") as fh:
        text = fh.read()
    n = sum(1 for line in text.splitlines() if line.strip())
    with opener("w") as fh:
        fh.write(text + text)
    return n


def test_doubled_tape_gives_the_same_prints_and_the_same_coverage(tmp_path):
    """The whole point: a doubled file must read exactly like a clean one."""
    d_clean = write_day(tmp_path / "clean", DAY, seed=7)
    d_doubled = write_day(tmp_path / "doubled", DAY, seed=7)
    n = _double_in_place(d_doubled / "databento_opra.jsonl")

    clean = read_opra_day(d_clean / "databento_opra.jsonl", DAY)
    doubled = read_opra_day(d_doubled / "databento_opra.jsonl", DAY)

    assert doubled.prints == clean.prints
    assert doubled.coverage.to_dict() == clean.coverage.to_dict()
    # And the file really was twice the size, so the equality above is the
    # guard working rather than the doubling failing to happen.
    assert sum(1 for line in (d_doubled / "databento_opra.jsonl")
               .read_text().splitlines() if line.strip()) == 2 * n


def test_coverage_row_count_is_prints_not_rows_on_a_doubled_tape(tmp_path):
    """n_rows is a claim about the day, not about the file."""
    d = write_day(tmp_path / "c", DAY, seed=7)
    n = _double_in_place(d / "databento_opra.jsonl")
    cov = read_opra_day(d / "databento_opra.jsonl", DAY).coverage
    assert cov.n_rows == n
    assert sum(cov.rows_per_hour_ct.values()) == n


def test_escape_hatch_reproduces_the_pre_guard_read(tmp_path):
    d = write_day(tmp_path / "c", DAY, seed=7)
    n = _double_in_place(d / "databento_opra.jsonl")
    cov = read_opra_day(d / "databento_opra.jsonl", DAY, dedup=False).coverage
    assert cov.n_rows == 2 * n


def test_a_clean_tape_is_unchanged_by_the_guard(tmp_path):
    """Turning the guard off over clean data must change nothing at all."""
    d = write_day(tmp_path / "c", DAY, seed=7)
    p = d / "databento_opra.jsonl"
    on = read_opra_day(p, DAY)
    off = read_opra_day(p, DAY, dedup=False)
    assert on.prints == off.prints
    assert on.coverage.to_dict() == off.coverage.to_dict()


def test_compacted_day_still_reads(tmp_path):
    """corpus_compact_databento gzips a finished day and removes the source."""
    d = write_day(tmp_path / "c", DAY, seed=7, gz=True)
    p = resolve_day_file(d, "databento_opra.jsonl")
    assert p is not None and p.suffix == ".gz"
    day = read_opra_day(p, DAY)
    assert day.coverage.n_0dte > 0
    assert day.prints


def test_far_dated_decoy_row_is_still_excluded_from_prints(tmp_path):
    """The helper writes one 991231 symbol that is not 0DTE.

    It belongs in the coverage tally and not in ``prints`` — a property the
    guard must not disturb.
    """
    d = write_day(tmp_path / "c", DAY, seed=7)
    day = read_opra_day(d / "databento_opra.jsonl", DAY)
    assert not any("991231" in sym for sym in day.prints)
    assert day.coverage.n_rows == day.coverage.n_0dte + 1


def test_two_prints_alike_but_for_sequence_both_survive(tmp_path):
    """Distinct fills at one instant are real prints and must not be eaten."""
    d = tmp_path / "c" / DAY
    d.mkdir(parents=True)
    ts = "2025-11-03T19:30:00.000000000+00:00"

    def row(seq):
        return json.dumps({
            "provenance": {"ts_event": ts},
            "data": {"symbol": "SPXW  251103C06400000", "instrument_id": 5,
                     "price": 1.25, "size": 2, "sequence": seq},
        }) + "\n"

    (d / "databento_opra.jsonl").write_text(row(1) + row(2), encoding="utf-8")
    day = read_opra_day(d / "databento_opra.jsonl", DAY)
    assert len(day.prints["SPXW  251103C06400000"]) == 2
    assert day.coverage.n_rows == 2
