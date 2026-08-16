"""BasisEstimator — the live SPX→ES conversion. [st-n0qm.8]

What matters: no lookahead (a vendor row after the bar close is never used),
the sentinel's skip shapes are refused, a torn line is re-read whole, the
median window behaves, and nothing here can raise into the feeder.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from market.orderflow.basis import BasisEstimator, row_spot

T0 = datetime(2026, 8, 14, 13, 30, 0, tzinfo=timezone.utc)


@dataclass
class FakeBar:
    end_ts: datetime
    close: float


def _row(ts: datetime, spot: float, *, pull_lag_s: float = 1.0, **extra) -> str:
    r = {"ts_pull_utc": (ts + timedelta(seconds=pull_lag_s)).isoformat().replace("+00:00", "Z"),
         "timestamp": int(ts.timestamp()), "ticker": "SPX", "spot": spot,
         "z_mlgamma": 7806.13, "z_msgamma": 7799.77, "agg_dex": 400.08}
    r.update(extra)
    return json.dumps(r)


def _write(tmp_path, lines, name="gexbot_orderflow_1s.jsonl"):
    p = tmp_path / name
    p.write_text("".join(l + "\n" for l in lines), encoding="utf-8")
    return p


def test_absent_file_yields_unknown_not_error(tmp_path):
    est = BasisEstimator(tmp_path / "nope.jsonl")
    assert est.refresh() == 0
    assert est.sample(FakeBar(T0, 7825.0)) == {"pts": None, "n": 0, "age_s": None}


def test_sample_pairs_the_bar_close_with_the_vendor_second(tmp_path):
    p = _write(tmp_path, [_row(T0 + timedelta(seconds=i), 7804.0 + 0.1 * i) for i in range(5)])
    est = BasisEstimator(p)
    assert est.refresh() == 5
    e = est.sample(FakeBar(T0 + timedelta(seconds=3, milliseconds=400), 7825.0))
    # row at T0+3 (spot 7804.3) is the newest at-or-before; 7825 - 7804.3
    assert e["pts"] == 20.7 and e["n"] == 1


def test_never_pairs_with_a_row_from_after_the_bar_close(tmp_path):
    p = _write(tmp_path, [_row(T0 + timedelta(seconds=10), 7900.0)])
    est = BasisEstimator(p)
    est.refresh()
    assert est.sample(FakeBar(T0 + timedelta(seconds=9), 7825.0))["pts"] is None


def test_a_row_older_than_the_pair_window_is_refused(tmp_path):
    p = _write(tmp_path, [_row(T0, 7804.0)])
    est = BasisEstimator(p, max_pair_age_s=5.0)
    est.refresh()
    assert est.sample(FakeBar(T0 + timedelta(seconds=6), 7825.0))["pts"] is None
    assert est.sample(FakeBar(T0 + timedelta(seconds=5), 7825.0))["pts"] == 21.0


def test_median_over_the_window_and_the_window_slides(tmp_path):
    rows = [_row(T0 + timedelta(seconds=i), 7800.0) for i in range(30)]
    est = BasisEstimator(_write(tmp_path, rows), window=3)
    est.refresh()
    for i, close in enumerate([7820.0, 7821.0, 7899.0]):    # one odd second
        e = est.sample(FakeBar(T0 + timedelta(seconds=i), close))
    assert e == {"pts": 21.0, "n": 3, "age_s": e["age_s"]}     # median shrugs off 99
    for i, close in enumerate([7822.0, 7822.5, 7823.0], start=3):
        e = est.sample(FakeBar(T0 + timedelta(seconds=i), close))
    assert e["pts"] == 22.5 and e["n"] == 3                    # 7899 slid out


def test_sentinel_skip_shapes_are_refused():
    good = json.loads(_row(T0, 7804.0))
    assert row_spot(good) == (int(T0.timestamp()), 7804.0)
    assert row_spot(json.loads(_row(T0, 7804.0, anomaly="collector"))) is None
    reset = json.loads(_row(T0, 7804.0, z_mlgamma=7535.0, z_msgamma=7535.0, agg_dex=0))
    assert row_spot(reset) is None
    stale = json.loads(_row(T0, 7804.0, pull_lag_s=17.5 * 3600))   # prior-close snapshot
    assert row_spot(stale) is None
    assert row_spot(json.loads(_row(T0, 0.0))) is None
    assert row_spot({"timestamp": "x", "spot": 7804.0}) is None


def test_torn_final_line_is_re_read_whole(tmp_path):
    p = tmp_path / "gexbot_orderflow_1s.jsonl"
    full = _row(T0, 7804.0)
    p.write_text(full + "\n" + full[:20], encoding="utf-8")
    est = BasisEstimator(p)
    assert est.refresh() == 1
    p.write_text(full + "\n" + full + "\n", encoding="utf-8")
    assert est.refresh() == 1


def test_estimate_reports_sample_age(tmp_path):
    p = _write(tmp_path, [_row(T0, 7804.0)])
    est = BasisEstimator(p)
    est.refresh()
    est.sample(FakeBar(T0, 7825.0))
    e = est.estimate(now=T0 + timedelta(seconds=42))
    assert e == {"pts": 21.0, "n": 1, "age_s": 42.0}


def test_a_broken_bar_object_cannot_raise(tmp_path):
    p = _write(tmp_path, [_row(T0, 7804.0)])
    est = BasisEstimator(p)
    est.refresh()
    assert est.sample(object())["pts"] is None
    assert est.sample(FakeBar("not a datetime", 7825.0))["pts"] is None


def test_whole_file_refresh_then_replay_pairs_every_bar(tmp_path):
    """The hindsight harness refreshes once over a full day's file, then walks
    the bars. Trimming must happen behind the sampled bar, never at refresh,
    or an offline replay pairs only the file's tail."""
    rows = [_row(T0 + timedelta(seconds=i), 7800.0) for i in range(6000)]   # 100 min
    est = BasisEstimator(_write(tmp_path, rows))
    assert est.refresh() == 6000
    paired = 0
    for i in range(0, 6000, 60):     # a bar a minute across the whole file
        before = est.estimate()["n"]
        e = est.sample(FakeBar(T0 + timedelta(seconds=i), 7820.0))
        paired += int(e["n"] != before or e["n"] == 10)
    assert paired == 100 and e["pts"] == 20.0
    # and memory stayed bounded: rows well behind the last bar were dropped
    assert len(est._rows) < 2100 and est._rows[0][0] >= T0.timestamp() + 5940 - 600 - 2000
