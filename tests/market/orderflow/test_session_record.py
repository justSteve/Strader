"""Replay-session recorder tests. [st-055]

Uses the committed golden tape (the parity fixture day) — no corpus
dependency, so these run in CI.
"""
import json
from pathlib import Path

import market.signals.orderflow_config as orderflow_config
from market.orderflow.recognizer import Anchor
from market.orderflow.session_record import read_latest_run, record_day

FIXTURE = Path(__file__).resolve().parent.parent.parent \
    / "market/fixtures/es_ticks_golden_20260702.jsonl"
ANCHORS = [Anchor(7482.0, "support", "poc"), Anchor(7555.0, "resistance", "am")]


def _record(out):
    return record_day(FIXTURE, anchors=list(ANCHORS), mancini_prices=[7482.5],
                      out_path=out)


def test_record_rows_structure(tmp_path):
    out = tmp_path / "signals_test.jsonl"
    meta = _record(out)
    rows = [json.loads(l) for l in out.open()]
    assert rows[0]["type"] == "RunMeta" and rows[0]["n"] == 0
    assert rows[0]["bead"] == "st-055"
    assert rows[1]["type"] == "DayType" and rows[1]["n"] == 1
    ns = [r["n"] for r in rows]
    assert ns == sorted(ns) and len(set(ns)) == len(ns)
    assert all("bar_i" in r for r in rows[2:])
    assert all(r["run"] == meta["run"] for r in rows)
    # production floors, not parity fixture floors
    assert rows[0]["config"]["FLUSH_DELTA_MIN"] == orderflow_config.FLUSH_DELTA_MIN == 300
    assert meta["n_events"] == len(rows) - 2


def test_record_is_append_only_and_deterministic(tmp_path):
    out = tmp_path / "signals_test.jsonl"
    m1 = _record(out)
    first_block = out.read_text()
    m2 = _record(out)
    assert m1["run"] != m2["run"]
    # append-only: the first run's bytes are still there, untouched, in front
    assert out.read_text().startswith(first_block)
    rows = [json.loads(l) for l in out.open()]

    def strip(r):
        return {k: v for k, v in r.items() if k not in ("run", "logged_utc", "git")}

    r1 = [strip(r) for r in rows if r["run"] == m1["run"]]
    r2 = [strip(r) for r in rows if r["run"] == m2["run"]]
    assert r1 == r2  # same tape + same anchors + same code = same record


def test_read_latest_run_selects_last_block(tmp_path):
    out = tmp_path / "signals_test.jsonl"
    _record(out)
    m2 = _record(out)
    latest = read_latest_run(out)
    assert latest and all(r["run"] == m2["run"] for r in latest)
    assert latest[0]["type"] == "RunMeta"


MBP1_FIXTURE = Path(__file__).resolve().parent.parent.parent \
    / "market/fixtures/es_mbp1_golden_20260702.jsonl.gz"


def test_record_includes_absorption_when_book_present(tmp_path):
    without = tmp_path / "without.jsonl"
    with_book = tmp_path / "with.jsonl"
    m0 = record_day(FIXTURE, anchors=list(ANCHORS), out_path=without)
    m1 = record_day(FIXTURE, anchors=list(ANCHORS), out_path=with_book,
                    book_path=MBP1_FIXTURE)
    assert m0["mbp1"] is False and m1["mbp1"] is True
    assert m1["n_events"] > m0["n_events"]  # absorption reads appended
    rows = [json.loads(l) for l in with_book.open()]
    assert all("bar_i" in r for r in rows[2:])  # absorption rows carry bar_i=None
