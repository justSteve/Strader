"""The estimated mark path: the model, its fit, and its two refusals. [st-9hhc]

Pinned here: the ES->premium conversion at known bins, the decay term, the
intrinsic floor, the coverage guard that refuses to extrapolate silently, and
the refusal to mark a leg whose bin was never calibrated.
"""
from __future__ import annotations

import json
import math
import random

import pytest

from strader.marks.estimated import (
    BinFit, Calibration, CalibrationRow, CoverageError, LegEntry, MinuteBar, Uncalibrated,
    bin_lower_edge, estimate_mark, estimate_path, fit_bin, intrinsic_pts, minute_index,
    minutes_to_close, moneyness_spx,
)


def _cal(**fits_kw) -> Calibration:
    fits = {}
    for (right, lo), (delta, kappa) in fits_kw.get("fits", {("P", 10): (0.9, 0.5)}).items():
        fits[(right, lo)] = BinFit(right=right, bin_lo=lo, delta_pts_per_es=delta, kappa=kappa,
                                   n_rows=1000, n_live=990, n_legs=20, resid_mae_pts=0.1, resid_p50_pts=0.0)
    return Calibration(window_ct=("13:00", "15:00"), fits=fits, days=("2026-08-14",))


def _bars(start: str, n: int, es0: float, step: float) -> list[MinuteBar]:
    out = []
    idx = minute_index(start)
    es = es0
    for i in range(n):
        m = f"{(idx + i) // 60:02d}:{(idx + i) % 60:02d}"
        o, c = es, es + step
        out.append(MinuteBar(m, o, max(o, c) + 0.5, min(o, c) - 0.5, c, 10))
        es += step
    return out


# ------------------------------------------------------------ primitives ---

def test_minute_arithmetic_is_ct_wall_clock():
    assert minute_index("14:03") == 843
    assert minutes_to_close("14:00") == 60
    assert minutes_to_close("15:00") == 0
    assert minutes_to_close("15:30") == 0
    with pytest.raises(ValueError):
        minute_index("2:03")


def test_moneyness_is_itm_positive_for_both_rights():
    assert moneyness_spx("P", 6410, 6400) == 10        # put above spot: ITM
    assert moneyness_spx("C", 6390, 6400) == 10        # call below spot: ITM
    assert moneyness_spx("PUT", 6390, 6400) == -10
    assert bin_lower_edge(12.4) == 10 and bin_lower_edge(-0.1) == -5 and bin_lower_edge(0) == 0
    assert intrinsic_pts("P", 6410, 6400) == 10 and intrinsic_pts("C", 6410, 6400) == 0


# ---------------------------------------------------------------- model ---

def test_mark_equals_entry_at_zero_move_and_zero_decay():
    assert estimate_mark(entry_premium_pts=12.4, tv_entry_pts=2.4, delta=0.9, kappa=0.5,
                         fav_move=0.0, tau_ratio=1.0, intrinsic_now_pts=10.0) == 12.4


def test_time_value_is_gone_at_the_close_and_intrinsic_floors_the_mark():
    # At tau_ratio 0 the whole time value has decayed: 12.4 - 2.4 = 10.0 = intrinsic.
    assert estimate_mark(entry_premium_pts=12.4, tv_entry_pts=2.4, delta=0.9, kappa=0.5,
                         fav_move=0.0, tau_ratio=0.0, intrinsic_now_pts=10.0) == 10.0
    # A 20-point move the leg's way at delta 0.7 says 24.0 but intrinsic is 30: the floor wins.
    assert estimate_mark(entry_premium_pts=12.4, tv_entry_pts=2.4, delta=0.7, kappa=0.5,
                         fav_move=20.0, tau_ratio=0.0, intrinsic_now_pts=30.0) == 30.0
    # And never below zero.
    assert estimate_mark(entry_premium_pts=1.0, tv_entry_pts=1.0, delta=0.5, kappa=0.5,
                         fav_move=-40.0, tau_ratio=0.5, intrinsic_now_pts=0.0) == 0.0


def test_decay_shape_kappa_half_is_square_root_of_time():
    half = estimate_mark(entry_premium_pts=5.0, tv_entry_pts=4.0, delta=0.5, kappa=0.5,
                         fav_move=0.0, tau_ratio=0.25, intrinsic_now_pts=1.0)
    assert half == pytest.approx(5.0 - 4.0 * (1 - 0.5))          # sqrt(0.25) = 0.5 of the TV left
    linear = estimate_mark(entry_premium_pts=5.0, tv_entry_pts=4.0, delta=0.5, kappa=1.0,
                           fav_move=0.0, tau_ratio=0.25, intrinsic_now_pts=1.0)
    assert linear == pytest.approx(5.0 - 4.0 * 0.75)
    with pytest.raises(ValueError):
        estimate_mark(entry_premium_pts=5.0, tv_entry_pts=4.0, delta=0.5, kappa=1.0,
                      fav_move=0.0, tau_ratio=1.5, intrinsic_now_pts=1.0)


def test_path_marks_close_adverse_and_favourable_per_minute():
    cal = _cal()
    leg = LegEntry(right="P", strike=6410, entry_premium_pts=12.4, entry_spx=6400, entry_es=6420,
                   entry_minute="14:00")
    assert leg.moneyness == 10 and leg.time_value_pts == pytest.approx(2.4)
    bars = _bars("14:00", 3, 6420.0, -1.0)   # ES falling one point a minute: the put's way
    path = estimate_path(leg, bars, cal)
    assert [p.minute for p in path] == ["14:00", "14:01", "14:02"]
    first = path[0]
    # close: fav 1.0 * 0.9, TV decayed by (1 - (59/60)^0.5)
    tau_ratio = 59 / 60
    expect = 12.4 + 0.9 * 1.0 - 2.4 * (1 - tau_ratio ** 0.5)
    assert first.premium_pts == pytest.approx(expect, abs=1e-4)
    # adverse for a put is the bar HIGH (ES up = against): fav move = -(high - entry_es) = -0.5
    assert first.adverse_pts == pytest.approx(12.4 - 0.45 - 2.4 * (1 - tau_ratio ** 0.5), abs=1e-4)
    # favourable is the bar LOW: -(low - entry_es) = +1.5
    assert first.favourable_pts == pytest.approx(12.4 + 1.35 - 2.4 * (1 - tau_ratio ** 0.5), abs=1e-4)
    assert not any(p.extrapolated for p in path)


def test_path_ignores_bars_before_entry_and_at_or_after_the_close():
    cal = _cal()
    leg = LegEntry(right="P", strike=6410, entry_premium_pts=12.4, entry_spx=6400, entry_es=6420,
                   entry_minute="14:58")
    bars = _bars("14:57", 4, 6420.0, 0.0)   # 14:57 .. 15:00
    path = estimate_path(leg, bars, cal)
    assert [p.minute for p in path] == ["14:58", "14:59"]
    # 14:59's close is the session close: tau_ratio 0, so the TV is gone and the mark is intrinsic.
    assert path[-1].premium_pts == pytest.approx(10.0)


def test_coverage_guard_refuses_outside_the_window_unless_told_and_then_labels():
    cal = _cal()
    leg = LegEntry(right="P", strike=6410, entry_premium_pts=12.4, entry_spx=6400, entry_es=6420,
                   entry_minute="10:15")
    bars = _bars("10:15", 3, 6420.0, -1.0)
    with pytest.raises(CoverageError):
        estimate_path(leg, bars, cal)
    path = estimate_path(leg, bars, cal, allow_extrapolation=True)
    assert all(p.extrapolated for p in path)
    # A leg inside a narrower window whose bars run past its end is refused the
    # same way, and labelled minute by minute when allowed.
    narrow = Calibration(window_ct=("13:00", "14:30"), fits=cal.fits, days=cal.days)
    inside = LegEntry(right="P", strike=6410, entry_premium_pts=12.4, entry_spx=6400, entry_es=6420,
                      entry_minute="14:28")
    bars = _bars("14:28", 4, 6420.0, 0.0)          # 14:28 .. 14:31
    with pytest.raises(CoverageError):
        estimate_path(inside, bars, narrow)
    path = estimate_path(inside, bars, narrow, allow_extrapolation=True)
    assert [(p.minute, p.extrapolated) for p in path] == [
        ("14:28", False), ("14:29", False), ("14:30", True), ("14:31", True)]


def test_uncalibrated_bin_is_refused_not_borrowed():
    cal = _cal()   # only (P, 10) exists
    call = LegEntry(right="C", strike=6390, entry_premium_pts=12.4, entry_spx=6400, entry_es=6420,
                    entry_minute="14:00")
    with pytest.raises(Uncalibrated):
        estimate_path(call, _bars("14:00", 2, 6420.0, 0.0), cal)
    far = LegEntry(right="P", strike=6440, entry_premium_pts=40.0, entry_spx=6400, entry_es=6420,
                   entry_minute="14:00")   # 40 ITM: outside the edges
    with pytest.raises(Uncalibrated):
        cal.fit_for(far.right, far.moneyness)
    with pytest.raises(ValueError):
        cal.fit_for("X", 10)


# ------------------------------------------------------------------ fit ---

def _rows(delta: float, kappa: float, *, n_legs: int, minutes: int, seed: int, noise: float = 0.05,
          entry: float = 12.0, dead_tail: int = 0):
    """Synthetic minute rows for one bin. ``dead_tail`` appends that many rows
    per leg where the option has died at 0.05 after a large adverse move."""
    rng = random.Random(seed)
    rows = []
    for leg in range(n_legs):
        tv = 2.0 + rng.random()
        es = 0.0
        for i in range(minutes):
            es += rng.gauss(0, 0.8)
            tau_ratio = (minutes - i - 1) / minutes
            y = delta * es - tv * (1 - tau_ratio ** kappa) + rng.gauss(0, noise)
            rows.append(CalibrationRow(leg_id=f"leg{leg:03d}", right="P", bin_lo=10, fav_move=es,
                                       tau_ratio=tau_ratio, tv_entry_pts=tv, y_pts=y,
                                       entry_premium_pts=entry, intrinsic_now_pts=max(0.0, entry - tv + es)))
        for j in range(dead_tail):
            rows.append(CalibrationRow(leg_id=f"leg{leg:03d}", right="P", bin_lo=10, fav_move=-40.0 - j,
                                       tau_ratio=0.1, tv_entry_pts=tv, y_pts=0.05 - entry,
                                       entry_premium_pts=entry, intrinsic_now_pts=0.0))
    return rows


def test_fit_recovers_delta_and_kappa_from_synthetic_rows():
    rows = _rows(0.85, 0.5, n_legs=12, minutes=60, seed=7)
    fit = fit_bin("P", 10, rows)
    assert fit is not None
    assert fit.delta_pts_per_es == pytest.approx(0.85, abs=0.03)
    assert fit.kappa == 0.5
    assert fit.n_rows == 720 and fit.n_live == 720 and fit.n_legs == 12
    assert fit.resid_mae_pts < 0.1


def test_dead_rows_do_not_drag_the_slope_and_are_answered_by_the_floor():
    live_only = fit_bin("P", 10, _rows(0.85, 0.5, n_legs=12, minutes=60, seed=7))
    with_dead = fit_bin("P", 10, _rows(0.85, 0.5, n_legs=12, minutes=60, seed=7, dead_tail=30))
    assert live_only is not None and with_dead is not None
    assert with_dead.delta_pts_per_es == live_only.delta_pts_per_es
    assert with_dead.kappa == live_only.kappa
    assert with_dead.n_rows == 720 + 360 and with_dead.n_live == 720
    # The dead rows are still in the residual, and the floor answers them: a
    # -40 move at delta 0.85 says -22 points, the floor says 0, the print says 0.05.
    assert with_dead.resid_mae_pts < 0.1


def test_fit_is_deterministic_under_row_order():
    rows = _rows(0.7, 1.0, n_legs=8, minutes=50, seed=11)
    a = fit_bin("P", 10, rows)
    b = fit_bin("P", 10, list(reversed(rows)))
    assert a == b


def test_thin_bins_are_not_fitted():
    rows = _rows(0.85, 0.5, n_legs=3, minutes=60, seed=1)
    assert fit_bin("P", 10, rows) is None                       # 3 legs < 5
    assert fit_bin("P", 10, rows, min_legs=1, min_rows=1000) is None   # 180 rows < 1000
    assert fit_bin("P", 10, rows, min_legs=1, min_rows=100) is not None


def test_fit_never_returns_a_negative_delta():
    rows = _rows(-0.5, 0.5, n_legs=6, minutes=40, seed=3)      # nonsense: premium falls as ES helps
    fit = fit_bin("P", 10, rows)
    assert fit is not None and fit.delta_pts_per_es == 0.0


# ---------------------------------------------------------- persistence ---

def test_calibration_round_trips_through_json(tmp_path):
    cal = _cal(fits={("P", 10): (0.9, 0.5), ("C", -10): (0.3, 1.25)})
    p = tmp_path / "cal.json"
    cal.dump(p)
    back = Calibration.load(p)
    assert back == cal
    text = p.read_text()
    assert json.loads(text)["fits"][0]["right"] == "C"          # sorted keys, sorted fits
    cal.dump(tmp_path / "again.json")
    assert (tmp_path / "again.json").read_bytes() == p.read_bytes()
