"""Live-run log + the parity checker's diff. [st-x2mp]

The run log exists so live/replay parity can be MEASURED rather than argued
from shared code. Two properties have to hold or the measurement is worthless:

  1. A run round-trips — what the writer wrote is what read_runs recovers,
     split correctly into runs even across a restart, and honest about a run
     that died mid-session.
  2. The diff actually catches a divergence. A checker that reports PASS on
     everything is worse than no checker, because it converts an unknown into
     a false assurance. Every negative case below perturbs one thing and
     asserts the report NAMES it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from market.entities.footprint import FootprintBar, FootprintCell
from market.orderflow.run_log import (
    Run, RunLogWriter, bar_record, read_runs, run_log_path,
)

CENTRAL = ZoneInfo("America/Chicago")
REPO_ROOT = Path(__file__).resolve().parents[3]
DAY = date(2026, 7, 31)
T0 = datetime(2026, 7, 31, 8, 30, tzinfo=CENTRAL)


def _load_checker():
    path = REPO_ROOT / "scripts" / "live_parity_check.py"
    spec = importlib.util.spec_from_file_location("live_parity_check", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


chk = _load_checker()


def _bar(i: int, *, price=7500.0, vol=200, delta=10):
    return FootprintBar(
        symbol="ESU6",
        start_ts=T0 + timedelta(seconds=30 * i),
        end_ts=T0 + timedelta(seconds=30 * i + 25),
        open=price, high=price + 1.0, low=price - 0.5, close=price + 0.25,
        volume=vol, delta=delta, none_vol=0,
        cells=(FootprintCell(price=price, bid_vol=95, ask_vol=105),),
    )


def _ev(bar_i, type_="SweepPrint", ts=None, **extra):
    return {"type": type_, "bar_i": bar_i,
            "timestamp": (ts or T0).isoformat(),
            "confidence": 0.5, "reason": "x"} | extra


def _write_run(path, *, bars=3, complete=True, started="2026-07-31T08:00:00"):
    w = RunLogWriter(path, day=DAY, bar_n=200, mancini=[7500.0],
                     reorder_lag=2.0, catch_up=False,
                     started=datetime.fromisoformat(started))
    for i in range(bars):
        w.on_bar(i, _bar(i), [_ev(i)])
    w.on_final([_ev(None, "Level")])
    if complete:
        w.close()
    else:
        w.close(quiet=True)
    return w


# --- round trip ------------------------------------------------------------

def test_a_run_round_trips(tmp_path):
    p = tmp_path / "day.jsonl"
    _write_run(p, bars=3)
    runs = read_runs(p)
    assert len(runs) == 1
    r = runs[0]
    assert r.complete and r.bar_n == 200 and r.mancini == [7500.0]
    assert len(r.bars) == 3
    assert [b["i"] for b in r.bars] == [0, 1, 2]
    # three per-bar emissions plus the one end-of-stream
    assert len(r.events) == 4
    assert r.events[-1]["bar_i"] is None


def test_bar_record_carries_the_boundary_fields_the_diff_needs():
    rec = bar_record(7, _bar(7))
    for f in chk.BAR_FIELDS:
        assert f in rec, f
    assert rec["i"] == 7


def test_a_restart_appends_a_second_run_rather_than_truncating(tmp_path):
    p = tmp_path / "day.jsonl"
    _write_run(p, bars=2, started="2026-07-31T08:00:00")
    _write_run(p, bars=5, started="2026-07-31T09:15:00")
    runs = read_runs(p)
    assert len(runs) == 2
    assert len(runs[0].bars) == 2 and len(runs[1].bars) == 5
    assert runs[0].started != runs[1].started


def test_an_incomplete_run_is_reported_not_hidden(tmp_path):
    p = tmp_path / "day.jsonl"
    _write_run(p, bars=2, complete=False)
    r = read_runs(p)[0]
    assert r.complete is False
    assert len(r.bars) == 2          # what it did record is still usable


def test_a_torn_last_line_does_not_lose_the_file(tmp_path):
    p = tmp_path / "day.jsonl"
    _write_run(p, bars=3)
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"k":"bar","i":9,"t0":"2026-')   # killed mid-write
    r = read_runs(p)[0]
    assert len(r.bars) == 3 and r.complete


def test_writer_degrades_instead_of_raising_when_the_path_is_unusable(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    w = RunLogWriter(blocker / "day.jsonl", day=DAY, bar_n=200, mancini=[],
                     reorder_lag=2.0, catch_up=False, started=datetime.now())
    assert w.live is False
    w.on_bar(0, _bar(0), [_ev(0)])   # must not raise into the feeder
    w.on_final([])
    w.close()


def test_run_log_path_is_under_derived_live_parity():
    p = run_log_path(DAY)
    assert p.name == "2026-07-31.jsonl"
    assert p.parent.name == "live-parity"


# --- pick_run --------------------------------------------------------------

def test_pick_run_defaults_to_the_last_complete_run():
    a = Run(meta={"started": "a"}, complete=True)
    b = Run(meta={"started": "b"}, complete=False)
    assert chk.pick_run([a, b], None) is a
    assert chk.pick_run([a, b], 1) is b
    assert chk.pick_run([], None) is None
    assert chk.pick_run([a], 5) is None


# --- the diff actually catches things --------------------------------------

def _live_side(bars=4):
    b = [bar_record(i, _bar(i)) for i in range(bars)]
    e = [{"k": "ev"} | _ev(i) for i in range(bars)]
    return b, e


def test_identical_sides_diff_clean():
    lb, le = _live_side()
    rb, re_ = _live_side()
    assert chk.diff_bars(lb, rb) == []
    assert chk.diff_events(le, re_) == []


def test_a_moved_bar_boundary_is_named_and_stops_the_run():
    lb, _ = _live_side()
    rb, _ = _live_side()
    rb[2]["t1"] = "2026-07-31T09:99:99"   # boundary moved on bar 2
    out = chk.diff_bars(lb, rb)
    assert out and "index 2" in out[0]
    assert any("t1" in line for line in out)
    # bar 3 differs for the same reason; the report must not list it
    assert not any("index 3" in line for line in out)


def test_a_dropped_bar_is_caught_as_a_count_difference():
    lb, _ = _live_side()
    rb, _ = _live_side()
    rb.pop()
    out = chk.diff_bars(lb, rb)
    assert out and "COUNT" in out[0]


def test_a_changed_emission_field_is_named():
    _, le = _live_side()
    _, re_ = _live_side()
    re_[1]["confidence"] = 0.99
    out = chk.diff_events(le, re_)
    assert out and any("confidence" in line for line in out)
    assert any("0.99" in line for line in out)


def test_an_emission_that_fired_on_a_different_print_is_caught():
    _, le = _live_side()
    _, re_ = _live_side()
    re_[2]["timestamp"] = (T0 + timedelta(seconds=1)).isoformat()
    out = chk.diff_events(le, re_)
    assert out and "emission 2" in out[0]


def test_an_extra_trailing_emission_is_named_not_just_counted():
    _, le = _live_side()
    _, re_ = _live_side()
    re_.append({"k": "ev"} | _ev(None, "Level"))
    out = chk.diff_events(le, re_)
    assert any("COUNT" in line for line in out)
    assert any("Level" in line for line in out)


def test_the_report_stops_after_five_emission_differences():
    _, le = _live_side(bars=40)
    _, re_ = _live_side(bars=40)
    for e in re_:
        e["confidence"] = 0.01
    out = chk.diff_events(le, re_)
    assert any("stopping after 5" in line for line in out)
