"""absorption_definition_variants (co-4owbx): the re-load multiple, the anchor
test, the one-defense-per-price collapse and the variant evaluation.
Synthetic episode rows only."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scripts.measurement import absorption_definition_variants as dv

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 9, 10, 10, 0, tzinfo=CENTRAL)


def ep(start_s=0, dur_s=2, side="bid", price=7500.0, vol=300, shown=100, expected=4.0,
       held=True, rth=True, mancini=2, refills=0):
    s = T0 + timedelta(seconds=start_s)
    return {"start_ts": s.isoformat(), "ts": (s + timedelta(seconds=dur_s)).isoformat(),
            "side": side, "price": price, "vol": vol, "shown_start": shown,
            "expected": expected, "held": held, "rth": rth, "mancini_ticks": mancini,
            "refills": refills, "hidden": 0,
            "fwd": {"5": [0.5, 2.0, False, True]} if held and rth else None}


def test_reload_multiple_is_traded_over_shown_and_tolerates_an_empty_level():
    assert dv.reload_multiple(ep(vol=300, shown=100)) == 3
    assert dv.reload_multiple(ep(vol=5, shown=0)) == 5


def test_near_anchor_needs_a_level_within_the_distance():
    assert dv.near_anchor(ep(mancini=4))
    assert not dv.near_anchor(ep(mancini=5))
    assert not dv.near_anchor(ep(mancini=None))


def test_same_side_and_price_inside_the_window_is_one_defense_ending_on_the_last():
    a = ep(start_s=0, dur_s=2, held=True, vol=100)
    b = ep(start_s=30, dur_s=2, held=False, vol=200)         # 28 s after a ended
    c = ep(start_s=200, dur_s=2, held=True)                  # outside the window
    d = ep(start_s=10, side="ask")                           # other side
    out = dv.collapse_repeats([b, a, c, d])
    bids = [g for g in out if g["side"] == "bid"]
    assert len(out) == 3 and len(bids) == 2
    first = min(bids, key=lambda g: g["start_ts"])
    assert first["members"] == 2 and first["vol"] == 300
    assert first["held"] is False and first["start_ts"] == a["start_ts"] and first["ts"] == b["ts"]


def test_evaluate_counts_rth_and_overnight_apart_and_scores_held_rth_only():
    eps = [ep(vol=300, shown=100), ep(start_s=100, vol=150, shown=100),
           ep(start_s=500, vol=400, shown=100, rth=False, held=True),
           ep(start_s=900, vol=400, shown=100, expected=2.5)]
    rows = [{"date": "2026-09-10", "episodes": eps,
             "baseline": {"rows": [{"kind": "off", "ticks": 2, "fwd": {"5": [2.0, 0.5, True, False]}}]}}]
    v2 = next(v for v in dv.VARIANTS if v.name.startswith("V2 "))
    r = dv.evaluate(rows, v2)
    assert (r["rth"], r["overnight"], r["held"], r["fwd5_n"]) == (1, 1, 1, 1)
    assert r["fwd5_win"] == 1.0 and r["base5_broke"] == 1.0
    v0 = dv.VARIANTS[0]
    assert dv.evaluate(rows, v0)["rth"] == 2
