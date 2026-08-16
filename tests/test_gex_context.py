"""GexContext — the bar/GEX join. [st-8ywx]

The tests that matter here are the refusals: no lookahead, no stale book, and
no failure mode that can reach the feeder. A bug in this module must degrade
the render, never the capture.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from market.orderflow.gex_context import GexContext


@dataclass
class FakeBar:
    end_ts: datetime
    close: float
    high: float
    low: float


def _poll(ts: datetime, *, spot=7700.0, flip=7690.0, pos=7750.0, neg=7650.0,
          net_oi=1.5e9, one_pos=7790.0, one_neg=7625.0) -> str:
    return json.dumps({
        "ts_pull_utc": ts.isoformat().replace("+00:00", "Z"),
        "stream": "gexbot",
        "data": {
            "summary": {
                "spot_at_gamma_zero": spot,
                "major_positive": pos, "major_negative": neg,
                "major_long_gamma": 7752.1, "major_short_gamma": 7648.3,
                "one_major_positive": one_pos, "one_major_negative": one_neg,
            },
            "responses": {
                "/SPX/classic/gex_zero/majors": {
                    "zero_gamma": flip, "net_gex_oi": net_oi,
                    "net_gex_vol": net_oi / 2, "spot": spot,
                },
            },
        },
        "errors": [],
    })


def _write(tmp_path, lines):
    p = tmp_path / "gexbot.jsonl"
    p.write_text("".join(l + "\n" for l in lines), encoding="utf-8")
    return p


T0 = datetime(2026, 8, 6, 14, 0, 0, tzinfo=timezone.utc)


def test_absent_file_is_silent(tmp_path):
    ctx = GexContext(tmp_path / "nope.jsonl")
    assert ctx.refresh() == 0
    assert ctx.for_bar(FakeBar(T0, 7700, 7705, 7695)) is None


def test_stamps_bar_with_nearest_prior_poll(tmp_path):
    p = _write(tmp_path, [_poll(T0), _poll(T0 + timedelta(seconds=60))])
    ctx = GexContext(p)
    assert ctx.refresh() == 2
    g = ctx.for_bar(FakeBar(T0 + timedelta(seconds=90), 7700, 7705, 7695), basis=0.0)
    assert g is not None
    assert g["age_s"] == 30.0          # the 60s poll, not the 0s one
    assert g["flip"] == 7690.0
    assert g["regime"] == "pos"
    assert g["dflip"] == 10.0
    assert g["one_pos"] == 7790.0


def test_never_uses_a_poll_from_the_future(tmp_path):
    """Lookahead would make every backtest of this data optimistic."""
    p = _write(tmp_path, [_poll(T0 + timedelta(seconds=120))])
    ctx = GexContext(p)
    ctx.refresh()
    assert ctx.for_bar(FakeBar(T0, 7700, 7705, 7695)) is None


def test_stale_poll_is_refused_not_silently_used(tmp_path):
    p = _write(tmp_path, [_poll(T0)])
    ctx = GexContext(p)
    ctx.refresh()
    assert ctx.for_bar(FakeBar(T0 + timedelta(seconds=299), 7700, 7705, 7695))
    assert ctx.for_bar(FakeBar(T0 + timedelta(seconds=301), 7700, 7705, 7695)) is None


def test_negative_net_gex_reads_as_trending_regime(tmp_path):
    p = _write(tmp_path, [_poll(T0, net_oi=-2.2e9)])
    ctx = GexContext(p)
    ctx.refresh()
    assert ctx.for_bar(FakeBar(T0, 7700, 7705, 7695))["regime"] == "neg"


def test_touch_reports_majors_inside_the_bar_range(tmp_path):
    # Levels are SPX; the bar is ES. With basis 0 the fixture is same-domain.
    p = _write(tmp_path, [_poll(T0, flip=7700.0, pos=7704.0, neg=7500.0)])
    ctx = GexContext(p)
    ctx.refresh()
    g = ctx.for_bar(FakeBar(T0, 7702, 7706, 7698), basis=0.0)
    assert "flip" in g["touch"] and "pos" in g["touch"]
    assert "neg" not in g["touch"]
    assert g["basis"] == 0.0 and g["dflip"] == 2.0


def test_touch_and_dflip_convert_spx_levels_through_the_basis(tmp_path):
    # SPX flip 7700 with a +20 basis sits at ES 7720: inside a 7718..7724 bar,
    # outside a 7698..7706 one — the unconverted compare would say the reverse.
    p = _write(tmp_path, [_poll(T0, flip=7700.0, pos=7704.0, neg=7500.0)])
    ctx = GexContext(p)
    ctx.refresh()
    g = ctx.for_bar(FakeBar(T0, 7722, 7724, 7718), basis=20.0)
    assert "flip" in g["touch"] and "pos" in g["touch"]
    assert g["dflip"] == 2.0 and g["basis"] == 20.0
    g2 = ctx.for_bar(FakeBar(T0, 7702, 7706, 7698), basis=20.0)
    assert g2["touch"] == [] and g2["dflip"] == -18.0


def test_no_basis_means_unknown_not_mixed_units(tmp_path):
    p = _write(tmp_path, [_poll(T0, flip=7700.0, pos=7704.0, neg=7500.0)])
    ctx = GexContext(p)
    ctx.refresh()
    g = ctx.for_bar(FakeBar(T0, 7702, 7706, 7698))
    assert g["basis"] is None and g["touch"] == [] and g["dflip"] is None
    assert g["flip"] == 7700.0  # levels stay SPX on the wire


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    p = _write(tmp_path, ["{not json", json.dumps([1, 2]), _poll(T0)])
    ctx = GexContext(p)
    assert ctx.refresh() == 1
    assert ctx.for_bar(FakeBar(T0, 7700, 7705, 7695)) is not None


def test_torn_final_line_is_re_read_whole(tmp_path):
    """The collector appends while we read; a half-line must not be consumed."""
    p = tmp_path / "gexbot.jsonl"
    p.write_text(_poll(T0) + "\n" + _poll(T0 + timedelta(seconds=60))[:40],
                 encoding="utf-8")
    ctx = GexContext(p)
    assert ctx.refresh() == 1
    p.write_text(_poll(T0) + "\n" + _poll(T0 + timedelta(seconds=60)) + "\n",
                 encoding="utf-8")
    assert ctx.refresh() == 1          # the completed line, not a duplicate
    assert len(ctx._polls) == 2


def test_missing_majors_leg_still_yields_a_context(tmp_path):
    """A cycle can error on one endpoint; the rest of the book is still real."""
    rec = json.loads(_poll(T0))
    rec["data"]["responses"] = {"/SPX/classic/gex_zero/majors":
                                {"status_code": 500, "error_body": "boom"}}
    p = _write(tmp_path, [json.dumps(rec)])
    ctx = GexContext(p)
    ctx.refresh()
    g = ctx.for_bar(FakeBar(T0, 7700, 7705, 7695))
    assert g is not None
    assert g["flip"] is None and g["regime"] is None and g["dflip"] is None
    assert g["pos"] == 7750.0          # the state leg survived


def test_unusable_bar_returns_none_rather_than_raising(tmp_path):
    p = _write(tmp_path, [_poll(T0)])
    ctx = GexContext(p)
    ctx.refresh()

    class Hostile:
        end_ts = T0
        close = property(lambda self: 1 / 0)
        high = 7705.0
        low = 7695.0

    assert ctx.for_bar(Hostile()) is None
