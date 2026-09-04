"""strader/marks/prints.py — corpus parsing, minute marks, parity. [st-9hhc]

Deterministic, no network, no corpus: every record is synthesized in the
shape measured on the real files 2026-09-01 (``provenance.ts_event`` ISO 8601
UTC, payload under ``data``). One test pins exactly that shape hazard: a
top-level ``ts_event`` record parses to nothing.
"""
import gzip
import json

import pytest

from strader.marks import prints as pr


def opra_line(ts_utc: str, symbol: str, price: float, size: int = 1) -> str:
    return json.dumps({
        "ts_pull_utc": "2026-09-01T00:00:00Z",
        "stream": "databento_opra",
        "provenance": {"dataset": "OPRA.PILLAR", "schema": "trades",
                       "parent_symbol": "SPXW.OPT", "ts_event": ts_utc},
        "data": {"symbol": symbol, "instrument_id": 1, "price": price,
                 "size": size, "side": "N", "action": "T"},
    })


def es_line(ts_utc: str, price: float) -> str:
    return json.dumps({
        "stream": "databento_glbx_es",
        "provenance": {"dataset": "GLBX.MDP3", "schema": "trades",
                       "ts_event": ts_utc},
        "data": {"symbol": "ESM6", "price": price, "size": 1, "side": "B"},
    })


def sym(exp: str, cp: str, k: float) -> str:
    return f"SPXW  {exp}{cp}{int(k * 1000):08d}"


# --------------------------------------------------------------- parse_occ

def test_parse_occ():
    assert pr.parse_occ("SPXW  250807C06345000") == ("250807", "C", 6345.0)
    assert pr.parse_occ("SPXW  260415P07020000") == ("260415", "P", 7020.0)


@pytest.mark.parametrize("bad", [
    "SPX   250807C06345000",   # not SPXW
    "SPXW",                    # no body
    "SPXW  250807X06345000",   # bad side
    "SPXW  250807C0634500",    # short body
    "garbage",
])
def test_parse_occ_rejects(bad):
    assert pr.parse_occ(bad) is None


# ------------------------------------------------------- timestamp handling

def test_summer_and_winter_offsets():
    assert pr.utc_offset_hours("2025-06-02") == -5
    assert pr.utc_offset_hours("2026-01-05") == -6


def test_load_day_prints_summer_and_winter(tmp_path):
    # Summer day: 18:30 UTC = 13:30 CT (inside window)
    p = tmp_path / "databento_opra.jsonl"
    s = sym("250602", "C", 6000)
    p.write_text(opra_line("2025-06-02T18:30:00.000000000+00:00", s, 5.0) + "\n")
    got = pr.load_day_prints(str(p), "2025-06-02")
    assert got == {s: [(13 * 3600 + 1800, 5.0)]}

    # Winter day: the same 18:30 UTC is 12:30 CT — outside the window
    w = tmp_path / "winter.jsonl"
    s2 = sym("260105", "C", 6000)
    w.write_text(opra_line("2026-01-05T18:30:00.000000000+00:00", s2, 5.0) + "\n"
                 + opra_line("2026-01-05T19:30:00.000000000+00:00", s2, 6.0) + "\n")
    got = pr.load_day_prints(str(w), "2026-01-05")
    assert got == {s2: [(13 * 3600 + 1800, 6.0)]}


def test_load_day_prints_drops_non_0dte_and_gz(tmp_path):
    p = tmp_path / "databento_opra.jsonl.gz"
    good = sym("250602", "C", 6000)
    later_exp = sym("250603", "C", 6000)  # next-day expiry: not 0DTE
    with gzip.open(p, "wt") as f:
        f.write(opra_line("2025-06-02T19:00:00.000000000+00:00", good, 5.0) + "\n")
        f.write(opra_line("2025-06-02T19:00:01.000000000+00:00", later_exp, 5.0) + "\n")
    got = pr.load_day_prints(str(p), "2025-06-02")
    assert list(got) == [good]


def test_naive_toplevel_ts_event_parses_to_nothing(tmp_path):
    """The record shape hazard from the handover memo, inverted: a record
    carrying ts_event only at top level (not under provenance) has no usable
    timestamp and is dropped rather than misread."""
    p = tmp_path / "databento_opra.jsonl"
    r = {"ts_event": "2025-06-02T19:00:00.000000000+00:00",
         "data": {"symbol": sym("250602", "C", 6000), "price": 5.0, "size": 1}}
    p.write_text(json.dumps(r) + "\n")
    assert pr.load_day_prints(str(p), "2025-06-02") == {}


# ------------------------------------------------------------ minute marks

def test_minute_marks_locf():
    path = [(13 * 3600 + 30, 5.0),          # 13:00:30
            (13 * 3600 + 90, 5.2),          # 13:01:30
            (13 * 3600 + 300, 4.8)]         # 13:05:00
    marks = pr.minute_marks(path, 13 * 3600 + 30, 13 * 3600 + 360)
    assert marks == [
        (13 * 3600 + 60, 5.0),    # 13:01 <- 13:00:30 print
        (13 * 3600 + 120, 5.2),   # 13:02 <- 13:01:30 print
        (13 * 3600 + 180, 5.2),   # carried
        (13 * 3600 + 240, 5.2),   # carried
        (13 * 3600 + 300, 4.8),   # 13:05 print lands exactly on the minute
        (13 * 3600 + 360, 4.8),
    ]


def test_minute_marks_before_first_print_absent():
    path = [(13 * 3600 + 200, 5.0)]
    marks = pr.minute_marks(path, 13 * 3600, 13 * 3600 + 300)
    assert marks == [(13 * 3600 + 240, 5.0), (13 * 3600 + 300, 5.0)]


def test_es_minutes_grid(tmp_path):
    p = tmp_path / "databento_glbx_es.jsonl"
    lines = [
        es_line("2025-06-02T18:00:10.000000000+00:00", 6000.0),   # 13:00:10 CT
        es_line("2025-06-02T18:00:50.000000000+00:00", 6000.5),   # 13:00:50 CT
        es_line("2025-06-02T18:03:30.000000000+00:00", 6002.0),   # 13:03:30 CT
    ]
    p.write_text("\n".join(lines) + "\n")
    grid = pr.load_day_es_minutes(str(p), "2025-06-02",
                                  start_s=13 * 3600, end_s=13 * 3600 + 300)
    assert grid == [
        (13 * 3600 + 60, 6000.5),    # 13:01 <- last trade before it (13:00:50)
        (13 * 3600 + 120, 6000.5),   # carried
        (13 * 3600 + 180, 6000.5),   # carried (13:03:30 is after 13:03)
        (13 * 3600 + 240, 6002.0),   # 13:04 <- 13:03:30
        (13 * 3600 + 300, 6002.0),
    ]


# ------------------------------------------------------------------ parity

def test_infer_spx_from_parity():
    spx = 6002.0
    prints = {}
    for k in (5990, 5995, 6000, 6005, 6010):
        prints[sym("250602", "C", k)] = [(14 * 3600, max(spx - k, 0.0) + 2.0)]
        prints[sym("250602", "P", k)] = [(14 * 3600, max(k - spx, 0.0) + 2.0)]
    est = pr.infer_spx(prints, 14 * 3600)
    assert est == pytest.approx(spx, abs=0.75)


def test_infer_spx_needs_three_strikes():
    prints = {
        sym("250602", "C", 6000): [(14 * 3600, 4.0)],
        sym("250602", "P", 6000): [(14 * 3600, 2.0)],
    }
    assert pr.infer_spx(prints, 14 * 3600) is None


# ----------------------------------------------------------- fire scanning

def test_first_print_at_or_below_uses_raw_prints():
    path = [(50400, 5.0), (50430, 4.6), (50490, 5.1)]
    hit = pr.first_print_at_or_below(path, 4.7, after_s=50400)
    assert hit == (50430, 4.6)  # the within-minute touch counts
    assert pr.first_print_at_or_below(path, 4.5, after_s=50400) is None
    assert pr.first_print_at_or_above(path, 5.05, after_s=50400) == (50490, 5.1)
