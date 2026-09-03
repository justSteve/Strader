"""Corpus minute paths: the record shape, the coverage measurement, parity. [st-9hhc]

The corpus stores UTC nanosecond timestamps under ``provenance.ts_event`` and
the payload under ``data``; a top-level ``ts_event`` is a decoy. The synthetic
day writes that decoy on every row, so a reader that trusts the top level
fails these tests instead of returning an empty file in production.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from strader.marks.estimated import minute_index
from strader.marks.minute_paths import (
    ct_offset_seconds, es_at, es_minute_bars, parity_spx, parse_symbol, print_minute_marks,
    read_es_day, read_opra_day, resolve_day_file,
)
from tests.helpers.estimated_mark_corpus import BASIS, write_day


@pytest.fixture(scope="module")
def day_dir(tmp_path_factory) -> Path:
    corpus = tmp_path_factory.mktemp("corpus")
    return write_day(corpus, "2026-08-14", seed=1)


def test_ct_offset_is_dst_aware():
    assert ct_offset_seconds("2026-08-14") == -5 * 3600     # CDT
    assert ct_offset_seconds("2026-01-15") == -6 * 3600     # CST


def test_parse_symbol():
    assert parse_symbol("SPXW  250807C06345000") == ("250807", "C", 6345.0)
    assert parse_symbol("SPX   250807C06345000") is None
    assert parse_symbol("SPXW  25") is None


def test_opra_day_reads_provenance_timestamps_and_measures_coverage(day_dir):
    opra = read_opra_day(resolve_day_file(day_dir, "databento_opra.jsonl"), "2026-08-14")
    cov = opra.coverage
    # Prints were written 13:00-15:00 CT only; the coverage says so, measured.
    assert cov.first_minute_ct == "13:00"
    assert cov.last_minute_ct == "14:59"
    assert set(cov.rows_per_hour_ct) == {"13", "14"}
    assert cov.n_rows == cov.n_0dte + 1                      # one far-dated decoy symbol
    assert all(not s.startswith("SPXW  9912") for s in opra.prints)
    for ps in opra.prints.values():
        assert ps == sorted(ps)
        assert all(13 * 3600 <= s < 15 * 3600 for s, _ in ps)


def test_opra_day_counts_prints_before_the_window_when_they_exist(tmp_path):
    d = write_day(tmp_path, "2026-08-13", seed=2, opra_from="12:50")
    opra = read_opra_day(resolve_day_file(d, "databento_opra.jsonl"), "2026-08-13")
    assert opra.coverage.first_minute_ct == "12:50"
    assert "12" in opra.coverage.rows_per_hour_ct


def test_gzipped_day_reads_the_same(tmp_path):
    plain = write_day(tmp_path / "a", "2026-08-14", seed=1)
    gz = write_day(tmp_path / "b", "2026-08-14", seed=1, gz=True)
    a = read_opra_day(resolve_day_file(plain, "databento_opra.jsonl"), "2026-08-14")
    b = read_opra_day(resolve_day_file(gz, "databento_opra.jsonl"), "2026-08-14")
    assert a.prints == b.prints and a.coverage.to_dict() == b.coverage.to_dict()
    assert resolve_day_file(gz, "databento_opra.jsonl").suffix == ".gz"
    assert resolve_day_file(gz, "nothing.jsonl") is None


def test_es_window_bars_and_lookup(day_dir):
    es = read_es_day(resolve_day_file(day_dir, "databento_glbx_es.jsonl"), "2026-08-14", ("13:00", "15:00"))
    assert es and all(13 * 3600 <= s < 15 * 3600 for s, _ in es)
    bars = es_minute_bars(es)
    assert min(bars, key=minute_index) == "13:00" and max(bars, key=minute_index) == "14:59"
    b = bars["14:00"]
    assert b.low <= min(b.open, b.close) and b.high >= max(b.open, b.close) and b.n == 60
    assert es_at(es, 13 * 3600 - 1) is None
    assert es_at(es, 14 * 3600 + 30) == next(p for s, p in reversed(es) if s <= 14 * 3600 + 30)


def test_parity_recovers_the_synthetic_spot(day_dir):
    opra = read_opra_day(resolve_day_file(day_dir, "databento_opra.jsonl"), "2026-08-14")
    es = read_es_day(resolve_day_file(day_dir, "databento_glbx_es.jsonl"), "2026-08-14", ("12:00", "15:00"))
    at = 14 * 3600
    spx = parity_spx(opra.strikes(), at)
    assert spx is not None
    assert spx == pytest.approx(es_at(es, at) - BASIS, abs=0.6)   # nickel rounding on both legs
    assert parity_spx({}, at) is None


def test_print_minute_marks_exclude_the_entry_print_and_stop_at_the_close(day_dir):
    opra = read_opra_day(resolve_day_file(day_dir, "databento_opra.jsonl"), "2026-08-14")
    sym = sorted(opra.prints)[0]
    ps = opra.prints[sym]
    entry_sec = 14 * 3600
    marks = print_minute_marks(ps, from_sec=entry_sec, to_minute="15:00")
    assert min(marks, key=minute_index) == "14:00"
    assert max(marks, key=minute_index) == "14:59"
    first = marks["14:00"]
    assert first.n == len([s for s, _ in ps if entry_sec < s < entry_sec + 60])
    assert first.low <= first.close <= first.high
