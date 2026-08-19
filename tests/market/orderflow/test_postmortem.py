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


# ------------------------------------------------------------------- legs

def _path(closes, *, spread=0.5):
    return [_bar(i, c, c + spread, c - spread, c) for i, c in enumerate(closes)]


def test_zigzag_legs_threshold_and_window():
    # up 8 in 5 minutes (kept), down 7 in 4 (kept), then up 9 at 0.2/min —
    # X=6 reached 30 minutes after the origin, outside Y=15 (dropped).
    closes = [100, 101, 103, 104, 106, 108, 108,
              106, 104, 102, 101] + [101 + 0.2 * n for n in range(1, 46)]
    bars = _path(closes, spread=0.0)
    knobs = pm.Knobs(x_pts=6.0, y_min=15)
    legs = pm.zigzag_legs(bars, knobs.x_pts)
    assert [(l.direction, round(l.pts, 1)) for l in legs] == \
        [("bullish", 8.0), ("bearish", 7.0), ("bullish", 9.0)]
    assert legs[2].reached_x_min == 30
    kept = pm.keep_legs(legs, knobs)
    assert [round(l.pts, 1) for l in kept] == [8.0, 7.0]
    a = kept[0]
    assert a.direction == "bullish" and a.origin_i == 0 and a.pts == 8.0
    assert a.end_i == 5 and a.minutes == 5 and a.reached_x_min <= 15


def test_zigzag_uses_highs_and_lows_not_closes():
    # closes flat, but bar 2 spikes 7 points high then back: one up leg, one down leg
    bars = [_bar(0, 100, 100.5, 99.5, 100), _bar(1, 100, 100.5, 99.5, 100),
            _bar(2, 100, 107, 99.5, 100), _bar(3, 100, 100.5, 99.5, 100),
            _bar(4, 100, 100.5, 99.5, 100)]
    legs = pm.zigzag_legs(bars, 6.0)
    assert [l.direction for l in legs][:2] == ["bullish", "bearish"]
    assert legs[0].pts == 7.5          # 99.5 low → 107 high


def test_tag_legs_called_hinted_silent_and_near_level():
    bars, events = _flush_reclaim_confirm()     # confirm at bar 7, sweep at bar 9
    # then a 10-point up leg from bar 16 (7723) → bar 20 (7731), inside W of the sweep
    extra = [_bar(16 + n, 7723 + 2 * n, 7723 + 2 * n + 0.5, 7723 + 2 * n - 0.5, 7723 + 2 * n)
             for n in range(5)]
    seg = _segment(bars + extra, events, mancini=[7720.0, 7734.0])
    knobs = pm.Knobs(x_pts=6.0, y_min=15, z_pts=3.0, w_min=10)
    legs = pm.keep_legs(pm.zigzag_legs(seg.bars, knobs.x_pts), knobs)
    tagged = pm.tag_legs(legs, seg, anchors=seg.mancini, knobs=knobs)
    up = [t for t in tagged if t["direction"] == "bullish"]
    assert up, "expected a kept bullish leg"
    assert up[-1]["tag"] in ("called", "hinted")      # a confirm or sweep preceded it
    assert up[-1]["nearest_level"] in (7720.0, 7734.0)
    assert "near_level" in up[-1] and "said_before" in up[-1]
    assert {"lid_rejections", "window_delta", "window_px_change"} <= set(up[-1])


def test_tag_legs_silent_when_nothing_in_window():
    bars = _path([100, 100, 100, 100, 101, 103, 105, 107, 108])
    seg = _segment(bars, [], mancini=[101.0])
    knobs = pm.Knobs(x_pts=6.0, y_min=15, z_pts=3.0, w_min=10)
    tagged = pm.tag_legs(pm.keep_legs(pm.zigzag_legs(bars, 6.0), knobs), seg,
                         anchors=[101.0], knobs=knobs)
    assert len(tagged) == 1 and tagged[0]["tag"] == "silent" and tagged[0]["near_level"] is True


def test_tag_legs_lid_rejections_and_window_delta():
    """Addendum A3: four highs within 8 ticks under the 7738 lid in the 30
    minutes before the origin; window delta sums the bars' d."""
    def b(i, h, d):
        return pm.Bar(i=i, t0=T0 + timedelta(minutes=i), t1=T0 + timedelta(minutes=i, seconds=55),
                      o=7735.5, h=h, l=7735.5, c=7735.5, v=2000, d=d)
    lid_highs = {2: 7737.75, 4: 7738.0, 6: 7737.5, 8: 7737.75}
    bars = [b(i, lid_highs.get(i, 7735.75), 50 if i in lid_highs else 20) for i in range(10)]
    bars.append(pm.Bar(i=10, t0=T0 + timedelta(minutes=10), t1=T0 + timedelta(minutes=10, seconds=55),
                       o=7735.5, h=7735.75, l=7735.25, c=7735.5, v=2000, d=-30))   # the origin low
    rise = [7737.0, 7738.5, 7740.0, 7741.5, 7743.0, 7744.0]
    bars += [pm.Bar(i=11 + n, t0=T0 + timedelta(minutes=11 + n), t1=T0 + timedelta(minutes=11 + n, seconds=55),
                    o=c - 0.5, h=c + 0.25, l=c - 0.5, c=c, v=2000, d=100) for n, c in enumerate(rise)]
    seg = _segment(bars, [], mancini=[7738.0])
    knobs = pm.Knobs(x_pts=6.0, y_min=15, z_pts=3.0, lid_ticks=8, lid_window_min=30)
    tagged = pm.tag_legs(pm.keep_legs(pm.zigzag_legs(bars, 6.0), knobs), seg,
                         anchors=[7738.0], knobs=knobs)
    assert len(tagged) == 1
    t = tagged[0]
    assert t["direction"] == "bullish" and t["origin_bar"] == 10 and t["near_level"] is True
    assert t["lid_rejections"] == 4
    assert t["window_delta"] == 4 * 50 + 6 * 20
    assert t["window_px_change"] == 0.0           # 7735.5 at origin, 7735.5 thirty minutes earlier
    # no level near the origin → the lid count is None, the delta still reports
    far = pm.tag_legs(pm.keep_legs(pm.zigzag_legs(bars, 6.0), knobs), seg,
                      anchors=[7760.0], knobs=knobs)
    assert far[0]["lid_rejections"] is None and far[0]["window_delta"] == 320


# ------------------------------------------------------------------ recap

RECAP = """On to today: Basic Themes
blah blah.
Trade Recap/Daily Summary
NOTE: The purpose of this trade recap section is to run down in greater detail previous examples of my three setup types that occurred within the last couple days.
The first high quality Failed Breakdown was the Failed Breakdown of 7777. I wrote yesterday at 2pm: "There is a safer Failed Breakdown just a little lower at 7777."
We recovered this shelf by 1:50PM, and I tweeted the long as well at 1:40PM: This was a classic, shallow Failed Breakdown not of a singular low, but a shelf at 7738.
Then a Level Reclaim of 7797 at 10:15AM which I did not take.
Trade Plan Wednesday
Supports are: 7777 (major), 7767.
"""


def test_extract_recap_rows():
    rows = pm.extract_recap(RECAP, letter_date=date(2026, 8, 18))
    setups = {(r["setup"], r["level"], r["time_et"]) for r in rows}
    assert any(s == "failed_breakdown" and lv == 7777.0 for s, lv, _ in setups)
    assert ("failed_breakdown", 7738.0, "1:40PM") in setups
    assert ("level_reclaim", 7797.0, "10:15AM") in setups
    assert all(r["letter_date"] == "2026-08-18" and r["quote"] for r in rows)


def test_extract_recap_without_section_is_empty():
    assert pm.extract_recap("no recap here. Trade Plan Monday", letter_date=date(2026, 8, 18)) == []


def test_match_recap_tiers_and_word_match():
    calls = [
        {"type": "SetupRecognition", "state": "confirmed", "setup": "failed_breakdown",
         "anchor": 7738.0, "ct": "12:45", "direction": "bullish"},      # 1:40PM ET = 12:40 CT → Δ5 EXACT
        {"type": "SetupRecognition", "state": "confirmed", "setup": "level_reclaim",
         "anchor": 7777.0, "ct": "10:00", "direction": "bullish"},
        {"type": "SetupRecognition", "state": "confirmed", "setup": "level_reclaim",
         "anchor": 7797.0, "ct": "09:30", "direction": "bullish"},      # his FBD 9:45AM ET = 08:45 CT → Δ45: LEVEL
    ]
    rows = [{"setup": "failed_breakdown", "level": 7738.0, "time_et": "1:40PM"},
            {"setup": "failed_breakdown", "level": 7777.0, "time_et": None},
            {"setup": "failed_breakdown", "level": 7797.0, "time_et": "9:45AM"},
            {"setup": "range_trap", "level": 7900.0, "time_et": "9:00AM"}]
    m = pm.match_recap(rows, calls)
    assert [x["tier"] for x in m] == ["EXACT", "LEVEL", "LEVEL", "MISS"]
    assert m[0]["matched_ct"] == "12:45" and m[1]["matched_ct"] == "10:00"
    # Addendum A4: his word against the machine's word, on every matched row
    assert [x["word_match"] for x in m] == [True, False, False, None]


def test_match_recap_family_tier():
    calls = [{"type": "SetupRecognition", "state": "confirmed", "setup": "level_reclaim",
              "anchor": 7738.0, "ct": "12:55", "direction": "bullish"}]   # Δ15 from 12:40 but other word
    rows = [{"setup": "failed_breakdown", "level": 7738.0, "time_et": "1:40PM"}]
    m = pm.match_recap(rows, calls)
    assert m[0]["tier"] == "FAMILY" and m[0]["word_match"] is False


# ----------------------------------------------------------- analyze_day

def test_session_of():
    assert pm.session_of(datetime(2026, 8, 18, 3, 0, tzinfo=CT)) == "overnight"
    assert pm.session_of(datetime(2026, 8, 18, 8, 30, tzinfo=CT)) == "cash"
    assert pm.session_of(datetime(2026, 8, 18, 14, 59, tzinfo=CT)) == "cash"
    assert pm.session_of(datetime(2026, 8, 18, 15, 0, tzinfo=CT)) == "evening"


def test_flags_rules():
    bars, events = _flush_reclaim_confirm()
    seg = _segment(bars, events, mancini=[7720.0])
    calls = pm.measure_calls(seg, pm.Knobs())
    legs = [{"tag": "silent", "near_level": True, "pts": 7.0, "direction": "bullish",
             "origin_ct": "09:00", "origin_bar": 3, "nearest_level": 7720.0, "said_before": []}]
    cen = pm.census(seg, calls)
    flags = pm.flags(calls, legs, cen, session_range=20.0, knobs=pm.Knobs())
    kinds = {f["flag"] for f in flags}
    assert "late-confirm" in kinds and "silent-move" in kinds   # lag 2 bars / +3.75; silent near level
    assert "dense-anchor" not in kinds and "grid-density" not in kinds
    assert "kind-mismatch" not in kinds                          # parse had no word for it


def test_flags_kind_mismatch():
    """Addendum A1: the parse says resistance, the recognizer said support."""
    bars, events = _flush_reclaim_confirm()
    seg = _segment(bars, events, mancini=[7720.0])
    for parse_kind, expect in (("resistance", True), ("support", False), (None, False),
                               ("trigger", False)):   # shown on the row, not a flag
        kinds = {7720.0: parse_kind} if parse_kind else {}
        calls = pm.measure_calls(seg, pm.Knobs(), parsed_kinds=kinds)
        fl = pm.flags(calls, [], pm.census(seg, calls), session_range=20.0, knobs=pm.Knobs())
        assert ("kind-mismatch" in {f["flag"] for f in fl}) is expect, parse_kind


def test_flags_dense_anchor_and_grid_density():
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(12)]
    events = [_ev(i, bars, setup="failed_breakdown", bias="bullish", anchor_price=99.0,
                  anchor_kind="support", state="confirmed", beats=[], fire_index=i + 1,
                  confidence=0.6) for i in range(6)]
    seg = _segment(bars, events, mancini=[99.0])
    calls = pm.measure_calls(seg, pm.Knobs())
    flags = pm.flags(calls, [], pm.census(seg, calls), session_range=5.0, knobs=pm.Knobs())
    assert {"dense-anchor", "grid-density"} <= {f["flag"] for f in flags}


def test_analyze_day_on_fixture_has_every_section_input():
    segs = pm.load_live_segments(FIXTURE)
    res = pm.analyze_day(segs, pm.Knobs(), day=date(2026, 8, 18), source="live",
                         pass_name="same-day", now=datetime(2026, 8, 18, 15, 30, tzinfo=CT))
    assert res["day"] == "2026-08-18" and res["source"] == "live" and res["pass"] == "same-day"
    assert res["runs"] == [
        {"run": 1, "started": segs[0].started, "bars": 3, "complete": True,
         "anchorless": True, "first_ct": segs[0].bars[0].t0.strftime("%H:%M"),
         "last_ct": segs[0].bars[-1].t1.strftime("%H:%M"), "overlap_bars": 0},
        {"run": 2, "started": segs[1].started, "bars": 41, "complete": True,
         "anchorless": False, "first_ct": segs[1].bars[0].t0.strftime("%H:%M"),
         "last_ct": segs[1].bars[-1].t1.strftime("%H:%M"), "overlap_bars": 0}]
    assert res["coverage"]["first_ct"] and res["coverage"]["last_ct"]
    assert res["census"]["by_type"]["SetupRecognition"]["confirmed"] >= 1
    per = {a["anchor"]: a for a in res["census"]["per_anchor"]}
    assert 7720.0 in per and per[7720.0]["confirmed"] >= 1
    assert isinstance(res["calls"], list) and isinstance(res["legs"], list)
    assert all("session" in c for c in res["calls"])
    assert res["recap"] == {"status": "not-received", "rows": []}
    assert isinstance(res["flags"], list)
    assert res["knobs"] == _knobs_dict(pm.Knobs())
    assert res["coverage"]["unmeasured_note"]            # record ends 13:57, pass at 15:30


# ----------------------------------------------------------------- ledger

def _res(day, pass_name, n_calls=2, n_legs=1):
    return {"day": day, "pass": pass_name, "source": "live", "generated_at": "x",
            "calls": [{"bar_i": i, "state": "confirmed", "setup": "failed_breakdown",
                       "verdict30": "win" if i % 2 else "loss", "type": "SetupRecognition"}
                      for i in range(n_calls)],
            "legs": [{"tag": "silent", "near_level": True} for _ in range(n_legs)],
            "flags": [], "census": {"by_type": {}, "per_anchor": [], "n_calls_measured": n_calls}}


def test_write_ledger_replaces_same_day_and_pass(tmp_path):
    root = tmp_path / "pm"
    pm.write_ledger(_res("2026-08-18", "same-day", 2, 1), root)
    pm.write_ledger(_res("2026-08-18", "same-day", 3, 2), root)     # re-run: replaces
    pm.write_ledger(_res("2026-08-18", "next-morning", 1, 1), root) # other pass: adds
    pm.write_ledger(_res("2026-08-17", "same-day", 1, 0), root)
    rows = [json.loads(l) for l in (root / "ledger.jsonl").read_text().splitlines()]
    assert sum(1 for r in rows if r["day"] == "2026-08-18" and r["pass"] == "same-day") == 3
    assert sum(1 for r in rows if r["day"] == "2026-08-18" and r["pass"] == "next-morning") == 1
    assert all({"day", "pass", "source"} <= set(r) for r in rows)
    legs = [json.loads(l) for l in (root / "legs.jsonl").read_text().splitlines()]
    assert len(legs) == 2 + 1 + 0
    assert json.loads((root / "2026-08-18.json").read_text())["pass"] == "next-morning"


def test_history_prefers_latest_pass_per_day(tmp_path):
    root = tmp_path / "pm"
    pm.write_ledger(_res("2026-08-17", "same-day", 4, 2), root)
    pm.write_ledger(_res("2026-08-17", "next-morning", 5, 3), root)
    pm.write_ledger(_res("2026-08-18", "same-day", 2, 1), root)
    h = pm.history(root, days=20, before="2026-08-19")
    assert h["days"] == ["2026-08-17", "2026-08-18"]
    assert h["confirms_per_day"] == [5, 2]
    assert h["silent_legs_per_day"] == [3, 1]
    assert h["median_confirms"] == 3.5
    assert h["by_setup"]["failed_breakdown"]["win"] == 3 and h["by_setup"]["failed_breakdown"]["loss"] == 4


# ------------------------------------------------------------------- page

HEADINGS = ["## Census", "## Calls made", "## Moves", "## Mancini's recap",
            "## Last 20 days", "## For Strader", "## What this page does not judge"]


def test_render_page_has_every_section_and_the_footer():
    segs = pm.load_live_segments(FIXTURE)
    res = pm.analyze_day(segs, pm.Knobs(), day=date(2026, 8, 18), source="live",
                         pass_name="same-day", now=datetime(2026, 8, 18, 15, 30, tzinfo=CT))
    md = pm.render_page(res, pm.history(Path("/nonexistent"), days=20))
    assert md.startswith("# Day post-mortem — 2026-08-18")
    for h in HEADINGS:
        assert h in md, h
    assert "what you saw" in md                    # live source label
    assert "Mancini's recap: not yet received" in md
    assert "| 13:" in md                           # a cash-session call row
    assert "The numbers above are the record." in md
    assert "Run 1 carried no Mancini levels" in md  # Addendum A2, from the fixture's first header
    assert "Lid rejections" in md                  # Addendum A3 columns on the Moves table


def test_render_page_replay_label_and_truncation_banner():
    segs = pm.load_live_segments(FIXTURE)
    res = pm.analyze_day(segs, pm.Knobs(), day=date(2026, 8, 18), source="replay",
                         pass_name="backfill", now=datetime(2026, 8, 18, 23, 0, tzinfo=CT))
    res["coverage"]["unmeasured_note"] = "record ends 13:35 CT; 565 minutes before the pass unmeasured"
    md = pm.render_page(res, pm.history(Path("/nonexistent")))
    assert "today's recognizer on that day's tape" in md
    assert "record ends 13:35 CT" in md


def test_render_page_parse_kind_and_word_match():
    """Addendum A1 on the call row; Addendum A4's count on the recap section."""
    bars, events = _flush_reclaim_confirm()
    seg = _segment(bars, events, mancini=[7720.0])
    recap_rows = [{"letter_date": "2026-08-18", "setup": "level_reclaim", "level": 7720.0,
                   "time_et": "9:40AM", "quote": "a Level Reclaim of 7720 at 9:40AM"},
                  {"letter_date": "2026-08-18", "setup": "range_trap", "level": 7900.0,
                   "time_et": None, "quote": "range trap at 7900"}]
    res = pm.analyze_day([seg], pm.Knobs(), day=date(2026, 8, 18), source="live",
                         pass_name="next-morning", now=datetime(2026, 8, 19, 8, 27, tzinfo=CT),
                         recap_rows=recap_rows, letter_status="received",
                         parsed_kinds={7720.0: "resistance"})
    md = pm.render_page(res, pm.history(Path("/nonexistent")))
    assert "@ 7720 (parse: resistance)" in md
    assert "**kind-mismatch**" in md
    assert "1 of 1 matched setups he named by the other word" in md


def test_stitch_drops_a_restarts_rewalk_and_keeps_run_numbers():
    """A restart re-walks the tape from the day's start; only the bars after
    the earlier run's last bar are new. Events on dropped bars go with them;
    a bar-less Level announcement is kept once."""
    a = [_bar(i, 100 + i, 100.5 + i, 99.5 + i, 100 + i) for i in range(6)]          # 08:30–08:35
    b = [_bar(i, 100 + i, 100.5 + i, 99.5 + i, 100 + i) for i in range(10)]         # 08:30–08:39, re-walk + 4 new
    ev_a = [_ev(3, a, type="SweepPrint", direction="buy", start_price=103.0, end_price=104.0)]
    ev_b = [_ev(3, b, type="SweepPrint", direction="buy", start_price=103.0, end_price=104.0),  # the re-walk's copy
            _ev(8, b, type="SweepPrint", direction="sell", start_price=108.0, end_price=107.0),
            {"k": "ev", "type": "Level", "bar_i": None, "price": 101.0, "level_type": "support"}]
    s1 = pm.Segment(run_no=1, bars=[pm.Bar(**{**asdict(x), "run": 1}) for x in a],
                    events=[dict(e, run=1) for e in ev_a], meta={"bar_n": 2000, "mancini": [101.0], "started": "x"})
    s2 = pm.Segment(run_no=2, bars=[pm.Bar(**{**asdict(x), "run": 2}) for x in b],
                    events=[dict(e, run=2) for e in ev_b]
                    + [{"k": "ev", "type": "Level", "bar_i": None, "price": 101.0, "level_type": "support", "run": 2}],
                    meta={"bar_n": 2000, "mancini": [], "started": "y"})
    day = pm.stitch([s1, s2])
    assert [(x.run, x.i) for x in day.bars] == [(1, i) for i in range(6)] + [(2, i) for i in range(6, 10)]
    assert day.meta["overlap_bars"] == {1: 0, 2: 6}
    kinds = [(e["type"], e.get("run"), e.get("bar_i")) for e in day.events]
    assert ("SweepPrint", 1, 3) in kinds and ("SweepPrint", 2, 8) in kinds
    assert ("SweepPrint", 2, 3) not in kinds                     # the re-walk's copy dropped
    assert sum(1 for k in kinds if k[0] == "Level") == 1       # announced once
    assert day.mancini == [101.0] and day.pos(8, 2) == 8 and day.pos(3, 1) == 3 and day.pos(3, 2) is None
    res = pm.analyze_day([s1, s2], pm.Knobs(), day=date(2026, 8, 18), source="live",
                         pass_name="same-day", now=datetime(2026, 8, 18, 15, 30, tzinfo=CT))
    assert [r["overlap_bars"] for r in res["runs"]] == [0, 6]
    assert sorted((c["run"], c["bar_i"]) for c in res["calls"]) == [(1, 3), (2, 8)]
    assert res["coverage"]["bars"] == 10


def test_flags_no_breakout_word():
    """A 10+ point leg through a level with only 'invalidated' said about it."""
    legs = [{"tag": "hinted", "near_level": True, "pts": 12.0, "direction": "bearish",
             "origin_ct": "09:00", "origin_bar": 3, "nearest_level": 7724.0,
             "said_before": ["failed_breakdown invalidated @7724 08:55"]},
            {"tag": "hinted", "near_level": True, "pts": 12.0, "direction": "bearish",
             "origin_ct": "10:00", "origin_bar": 9, "nearest_level": 7724.0,
             "said_before": ["failed_breakdown invalidated @7724 09:55", "SweepPrint 09:58"]}]
    cen = {"by_type": {}, "per_anchor": [], "n_calls_measured": 0}
    fl = pm.flags([], legs, cen, session_range=30.0, knobs=pm.Knobs())
    hits = [f for f in fl if f["flag"] == "no-breakout-word"]
    assert len(hits) == 1 and hits[0]["bar"] == 3


def test_measure_calls_carries_lid_and_delta_at_the_confirm():
    """Addendum A3 at the call: four highs under 7720 in the 30 minutes before the confirm bar."""
    bars, events = _flush_reclaim_confirm()
    seg = _segment(bars, events, mancini=[7720.0])
    c = next(r for r in pm.measure_calls(seg, pm.Knobs()) if r.get("state") == "confirmed")
    # bars 0..6 before the confirm: highs 7721.75, 7721.25, 7718.75, 7716.75, 7717.75, 7722.25, 7722.25
    # within 2 pts under 7720 (band 7718–7720) and closing under it: bar 2 (h 7718.75, c 7718);
    # bar 4's high 7717.75 is under the band → 1
    assert c["lid_rejections"] == 1
    assert c["window_delta"] == 0 and c["window_px_change"] == round(7723.75 - 7721, 2)


# --------------------------------------------------------------- backfill

def test_backfill_summary_distributions():
    days = [
        {"day": "2026-08-01", "status": "ok", "n_confirmed": 10, "n_legs": 4, "n_silent_near": 1,
         "legs_at": {"4": 9, "6": 4, "8": 2}, "by_setup": {"failed_breakdown": {"win": 4, "loss": 3}},
         "by_lid": {"ge3": {"win": 3, "loss": 1}, "lt3": {"win": 1, "loss": 2}}},
        {"day": "2026-08-04", "status": "ok", "n_confirmed": 20, "n_legs": 6, "n_silent_near": 3,
         "legs_at": {"4": 12, "6": 6, "8": 3}, "by_setup": {"failed_breakdown": {"win": 8, "loss": 9}},
         "by_lid": {"ge3": {"win": 2, "loss": 2}, "lt3": {"win": 6, "loss": 7}}},
        {"day": "2026-08-05", "status": "empty-tape"},
        {"day": "2026-08-06", "status": "ok", "n_confirmed": 0, "n_legs": 3, "n_silent_near": 0,
         "legs_at": {"4": 5, "6": 3, "8": 1}, "by_setup": {}, "by_lid": {}, "n_anchors": 0},
    ]
    s = pm.backfill_summary(days, pm.Knobs())
    assert s["n_days"] == 3 and len(s["skipped"]) == 1 and s["n_anchored_days"] == 2
    assert s["confirmed_per_day"]["median"] == 15          # the anchorless day does not drag it down
    assert s["legs_per_day_at"]["6"]["n"] == 3             # but it counts for legs
    assert s["legs_per_day_at"]["6"]["median"] == 4
    assert s["by_setup"]["failed_breakdown"] == {"win": 12, "loss": 12}
    assert s["by_lid"] == {"ge3": {"win": 5, "loss": 3}, "lt3": {"win": 7, "loss": 9}}
    md = pm.render_backfill_page(s)
    assert md.startswith("# Day post-mortem — backfill") and "| 6 |" in md and "2026-08-05" in md
    assert "3 or more lid rejections" in md
