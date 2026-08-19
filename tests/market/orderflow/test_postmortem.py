"""Day post-mortem: measuring, legs, recap, flags, page. [co-7kgte]

Every number on the page is a rule; these tests pin the rules on hand-built
bars so a change to any rule is a visible diff here first.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market.orderflow import postmortem as pm

CT = ZoneInfo("America/Chicago")
T0 = datetime(2026, 8, 18, 8, 30, tzinfo=CT)
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "postmortem" / "2026-08-18-trimmed.jsonl"


# ----------------------------------------------------------------- helpers

def _bar(i: int, o: float, h: float, l: float, c: float, *, d: int = 0,
         minute: int | None = None) -> pm.Bar:
    """One bar per minute from T0 unless ``minute`` is given."""
    m = i if minute is None else minute
    t0 = T0 + timedelta(minutes=m)
    return pm.Bar(i=i, t0=t0, t1=t0 + timedelta(seconds=55), o=o, h=h, l=l, c=c, v=2000, d=d)


def _ev(bar_i: int, bars: list[pm.Bar], **fields) -> dict:
    base = {"k": "ev", "type": "SetupRecognition", "bar_i": bar_i,
            "timestamp": bars[bar_i].t1.isoformat(), "confidence": 0.8,
            "reason": "x", "source": "orderflow.recognizer"}
    return base | fields


def _segment(bars, events, *, mancini=(), run_no=1, complete=True) -> pm.Segment:
    return pm.Segment(run_no=run_no, bars=list(bars), events=list(events),
                      meta={"bar_n": 2000, "mancini": list(mancini),
                            "started": T0.isoformat()},
                      complete=complete)


def _knobs_dict(k: pm.Knobs) -> dict:
    d = asdict(k)
    d["windows_min"] = list(d["windows_min"])
    return d


# ------------------------------------------------------------------- knobs

def test_default_knobs_match_spec():
    k = pm.Knobs()
    assert (k.x_pts, k.y_min, k.z_pts, k.w_min) == (6.0, 15, 3.0, 10)
    assert k.windows_min == (5, 15, 30)
    assert k.target_pts == 5.0
    assert (k.dense_anchor_fires, k.late_confirm_bars, k.late_confirm_pts,
            k.breakout_pts, k.grid_density) == (5, 2, 3.0, 10.0, 8.0)
    assert (k.lid_ticks, k.lid_window_min) == (8, 30)      # Addendum A3


def test_load_knobs_reads_yaml_and_falls_back(tmp_path):
    p = tmp_path / "postmortem.yaml"
    p.write_text("x_pts: 8\ny_min: 20\n")
    k = pm.load_knobs(p)
    assert (k.x_pts, k.y_min) == (8.0, 20)
    assert k.z_pts == 3.0                       # untouched keys keep defaults
    assert pm.load_knobs(tmp_path / "absent.yaml") == pm.Knobs()


def test_load_knobs_rejects_unknown_key(tmp_path):
    p = tmp_path / "postmortem.yaml"
    p.write_text("x_pts: 8\nbogus: 1\n")
    with pytest.raises(ValueError, match="bogus"):
        pm.load_knobs(p)


def test_shipped_config_loads_and_round_trips():
    k = pm.load_knobs(pm.CONFIG_PATH)
    assert pm.knobs_from_dict(pm.knobs_to_dict(k)) == k


# ---------------------------------------------------------------- loaders

def test_bar_from_record_parses_times_and_prices():
    rec = {"k": "bar", "i": 7, "t0": "2026-08-18T08:30:15-05:00",
           "t1": "2026-08-18T08:31:05-05:00", "o": 7720.0, "h": 7721.5,
           "l": 7719.75, "c": 7721.0, "v": 2000, "d": 120, "nv": 0}
    b = pm.Bar.from_record(rec)
    assert b.i == 7 and b.h == 7721.5 and b.d == 120
    assert b.t0.tzinfo is not None and b.t0.hour == 8 and b.t1.minute == 31


def test_load_live_segments_splits_runs_and_keeps_feeder_bar_numbers():
    segs = pm.load_live_segments(FIXTURE)
    assert [s.run_no for s in segs] == [1, 2]
    assert len(segs[0].bars) == 3 and segs[0].bars[0].i == 0
    assert segs[0].mancini == [] and segs[0].anchorless is True      # Addendum A2
    assert segs[1].bars[0].i == 380 and segs[1].bars[-1].i == 420
    assert all(e["bar_i"] is None or 380 <= e["bar_i"] <= 420 for e in segs[1].events)
    assert 7720.0 in segs[1].mancini and segs[1].anchorless is False
    assert segs[1].complete is True
    confirmed = [e for e in segs[1].events
                 if e["type"] == "SetupRecognition" and e["state"] == "confirmed"]
    assert any(e["anchor_price"] == 7720.0 and e["bar_i"] == 395 for e in confirmed)


def test_load_live_segments_skips_runs_without_bar_n(tmp_path, caplog):
    p = tmp_path / "x.jsonl"
    p.write_text('{"k":"run","day":"2026-08-18","mancini":[]}\n'
                 '{"k":"bar","i":0,"t0":"2026-08-18T08:30:00-05:00","t1":"2026-08-18T08:31:00-05:00",'
                 '"o":1,"h":2,"l":0,"c":1,"v":2000,"d":0,"nv":0}\n')
    with caplog.at_level("WARNING"):
        segs = pm.load_live_segments(p)
    assert segs == []
    assert "bar_n" in caplog.text


def test_segment_pos_maps_bar_number_to_index():
    bars = [_bar(i + 10, 10, 11, 9, 10) for i in range(3)]     # numbered 10, 11, 12
    seg = _segment(bars, [])
    assert seg.pos(11) == 1
    assert seg.pos(99) is None and seg.pos(None) is None


# -------------------------------------------------------------- excursion

def test_excursion_for_and_against_from_bars():
    # entry 100 at bar 0 close; next bars: up to 103, down to 98, up to 106
    bars = [_bar(0, 100, 100, 100, 100),
            _bar(1, 100, 103, 99.5, 102),
            _bar(2, 102, 102, 98, 99),
            _bar(3, 99, 106, 99, 105)]
    r = pm.excursion(bars, start=0, entry=100.0, sign=+1,
                     until=bars[0].t1 + timedelta(minutes=30), target=5.0)
    assert r == pm.Excursion(mfe=6.0, mae=2.0, verdict="win", truncated=True)
    r = pm.excursion(bars, start=0, entry=100.0, sign=-1,
                     until=bars[0].t1 + timedelta(minutes=30), target=5.0)
    assert (r.mfe, r.mae, r.verdict) == (2.0, 6.0, "loss")


def test_excursion_window_stops_at_until():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 101, 99, 100),
            _bar(2, 100, 120, 100, 119)]
    r = pm.excursion(bars, start=0, entry=100.0, sign=+1,
                     until=bars[1].t1, target=5.0)
    assert (r.mfe, r.mae, r.verdict, r.truncated) == (1.0, 1.0, "neither", False)


def test_excursion_both_in_one_bar_is_named_not_guessed():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 106, 94, 100)]
    r = pm.excursion(bars, start=0, entry=100.0, sign=+1,
                     until=bars[1].t1, target=5.0)
    assert r.verdict == "both-in-one-bar"
    assert (r.mfe, r.mae) == (6.0, 6.0)


def test_excursion_truncated_when_record_ends_before_until():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 101, 99, 100)]
    r = pm.excursion(bars, start=0, entry=100.0, sign=+1,
                     until=bars[1].t1 + timedelta(minutes=30), target=5.0)
    assert r.truncated is True and r.verdict == "neither"


# ------------------------------------------------------------------ calls

def _flush_reclaim_confirm():
    """Anchor 7720. Bars: above, flush below (bar 2), stay below, first close
    back above at bar 5 (the reclaim), confirm at bar 7 (lag 2) with close
    7723.75 (+3.75 from the anchor). Then a drift back under the level at
    bar 12 (back-to-level after 5 minutes)."""
    closes = [7721, 7720.5, 7718, 7716, 7717, 7721.5, 7721.5, 7723.75,
              7724, 7723, 7722, 7721, 7719.5, 7719, 7720.5, 7722]
    bars = [_bar(i, c, c + 0.75, c - 0.75, c) for i, c in enumerate(closes)]
    events = [
        _ev(2, bars, setup="failed_breakdown", bias="bullish", anchor_price=7720.0,
            anchor_kind="support", state="forming", beats=["flush"], fire_index=1,
            confidence=0.35, mancini_confluence=True),
        _ev(7, bars, setup="failed_breakdown", bias="bullish", anchor_price=7720.0,
            anchor_kind="support", state="confirmed", beats=["flush", "flip", "stall", "confirm"],
            fire_index=1, confidence=0.8, mancini_confluence=True),
        _ev(9, bars, type="SweepPrint", direction="buy", start_price=7723.0,
            end_price=7724.5, ticks_swept=6, total_size=300, confidence=1.0),
    ]
    return bars, events


def test_measure_calls_rows_and_confirm_lag():
    bars, events = _flush_reclaim_confirm()
    seg = _segment(bars, events, mancini=[7720.0])
    rows = pm.measure_calls(seg, pm.Knobs())
    kinds = [(r["type"], r.get("state")) for r in rows]
    assert ("SetupRecognition", "confirmed") in kinds and ("SweepPrint", None) in kinds
    assert ("SetupRecognition", "forming") not in kinds       # counted elsewhere, not measured
    c = next(r for r in rows if r.get("state") == "confirmed")
    assert c["bar_i"] == 7 and c["entry"] == 7723.75 and c["direction"] == "bullish"
    assert c["fire_index"] == 1 and c["anchor"] == 7720.0
    assert c["confirm_lag_bars"] == 2 and c["confirm_lag_pts"] == 3.75
    assert c["back_to_level_min"] == 5            # bar 12 closes under 7720
    assert c["mfe5"] >= 0 and "verdict30" in c and "truncated30" in c
    assert c["anchor_kind"] == "support" and c["anchor_kind_parse"] is None
    s = next(r for r in rows if r["type"] == "SweepPrint")
    assert s["direction"] == "bullish" and s["entry"] == 7723.0 and s["anchor"] is None


def test_measure_calls_anchor_kind_from_the_parse():
    """Addendum A1: the recognizer says support for every level; the parse
    knows which were resistance. Exact price match; None when absent."""
    bars, events = _flush_reclaim_confirm()
    seg = _segment(bars, events, mancini=[7720.0])
    rows = pm.measure_calls(seg, pm.Knobs(), parsed_kinds={7720.0: "resistance"})
    c = next(r for r in rows if r.get("state") == "confirmed")
    assert c["anchor_kind_parse"] == "resistance"
    rows = pm.measure_calls(seg, pm.Knobs(), parsed_kinds={7724.0: "support"})
    c = next(r for r in rows if r.get("state") == "confirmed")
    assert c["anchor_kind_parse"] is None


def test_measure_calls_direction_mapping_and_invalidated_sign():
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(4)]
    events = [
        _ev(0, bars, type="DeltaDivergence", kind="bearish", price_extreme=100.0,
            prior_extreme=99.0, cvd_at_extreme=1, cvd_at_prior=2),
        _ev(1, bars, type="ImbalanceStack", direction="sell", prices=[100.0], ratios=[3.0]),
        _ev(2, bars, setup="level_reclaim", bias="bullish", anchor_price=99.0,
            anchor_kind="support", state="invalidated", beats=[], fire_index=2, confidence=0.0),
    ]
    rows = pm.measure_calls(_segment(bars, events), pm.Knobs())
    assert [r["direction"] for r in rows] == ["bearish", "bearish", "bullish"]
    assert rows[2]["state"] == "invalidated"


def test_measure_calls_skips_events_without_a_known_bar():
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(2)]
    ev = _ev(0, bars, type="Level", price=100.0, level_type="support")
    ev["bar_i"] = None
    rows = pm.measure_calls(_segment(bars, [ev]), pm.Knobs())
    assert rows == []
