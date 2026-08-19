"""Same-anchor rule across every path that watches a letter. [st-tme]

The drill / replay recorder (``day_anchors``), the live feed (``LiveAnchors``)
and the acuity sweep (``scripts/acuity_run2.letter_anchors_for``) must derive
the identical Mancini anchor set — price AND kind — from the same parse.
Until 2026-08-19 acuity kind-filtered the letter to supports while the other
two admitted every level as support; the bead's acceptance criterion is that
this cannot happen again without a test saying so.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DAY = date(2026, 8, 19)
LEVELS = [
    {"price": 7716.0, "kind": "support"},
    {"price": 7724.0, "kind": "support"},
    {"price": 7738.0, "kind": "trigger"},
    {"price": 7742.0, "kind": "resistance"},
    {"price": 7760.0, "kind": "target"},
    {"price": 7760.0, "kind": "resistance"},
    {"price": 7730.0, "kind": "pivot"},
]


def _acuity():
    path = ROOT / "scripts" / "acuity_run2.py"
    spec = importlib.util.spec_from_file_location("acuity_run2", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["acuity_run2"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_drill_live_and_acuity_watch_the_same_mancini_anchors(tmp_path, monkeypatch):
    from market.orderflow import anchors as A
    from market.orderflow.anchors import LiveAnchors, day_anchors, mancini_kinds_for, mancini_levels_for

    (tmp_path / f"{DAY.isoformat()}.json").write_text(json.dumps({"levels": LEVELS}))
    monkeypatch.setattr(A, "PARSED", tmp_path)

    def mancini_only(anchors):
        return sorted((a.price, a.kind) for a in anchors if a.mancini)

    # the drill / replay recorder
    drill = day_anchors(mancini_levels_for(DAY), 7800.0, 7700.0, mancini_kinds_for(DAY))
    # the live feed
    live = LiveAnchors(mancini_levels_for(DAY), kinds=mancini_kinds_for(DAY)).anchors
    # the acuity sweep (reads the same module-level PARSED through the same functions)
    acuity = _acuity()
    _, sweep = acuity.letter_anchors_for(DAY)

    expected = [(7716.0, "support"), (7724.0, "support"), (7730.0, "resistance"),
                (7730.0, "support"), (7742.0, "resistance"), (7760.0, "resistance")]
    assert mancini_only(drill) == expected
    assert mancini_only(live) == expected
    assert mancini_only(sweep) == expected
    assert not any(a.kind in ("range_high", "range_low") for a in sweep)   # the sweep never scored edges
    # and nothing else in the sweep's anchor set came from the letter
    assert all(a.mancini for a in sweep)
