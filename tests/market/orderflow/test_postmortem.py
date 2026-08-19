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
