"""Offline tests for the fly-replay core (market.measurement.fly).

Pure-function tests — no corpus, no I/O: OCC parsing, forward-filled fly
combination, the entry-time sweep (patience/drawdown logic), cash settle
intrinsic, and put-call parity settle.
"""
from __future__ import annotations

from market.measurement import fly as fr


def test_parse_occ():
    assert fr.parse_occ("SPXW  260608C07485000") == ("260608", "C", 7485.0)
    assert fr.parse_occ("SPXW  260612P07450000") == ("260612", "P", 7450.0)
    assert fr.parse_occ("") is None
    assert fr.parse_occ("ES.c.0") is None


def test_fly_intrinsic_cash_settle():
    assert round(fr.fly_intrinsic(7405.73, 7400, 7405, 7410, "C"), 2) == 4.27
    assert round(fr.fly_intrinsic(7500, 7400, 7405, 7410, "C"), 2) == 0.0
    assert round(fr.fly_intrinsic(7405.73, 7400, 7405, 7410, "P"), 2) == 4.27


def test_fly_series_forward_fill():
    t0 = 1000.0
    legs = {
        7400.0: [(t0, 10.0)],
        7405.0: [(t0, 5.0), (t0 + 30, 6.0)],
        7410.0: [(t0, 1.0)],
    }
    series = fr.fly_series(legs, 7400.0, 7405.0, 7410.0, t0, t0 + 60, bin_seconds=30)
    assert series == [(t0, 1.0), (t0 + 30, -1.0), (t0 + 60, -1.0)]


def test_fly_series_skips_bins_missing_a_leg():
    t0 = 1000.0
    legs = {7400.0: [(t0 + 30, 10.0)], 7405.0: [(t0, 5.0)], 7410.0: [(t0, 1.0)]}
    series = fr.fly_series(legs, 7400.0, 7405.0, 7410.0, t0, t0 + 60, bin_seconds=30)
    assert [round(p, 2) for _, p in series] == [1.0, 1.0]
    assert series[0][0] == t0 + 30


def test_entry_sweep_later_entry_lower_dd():
    series = [(0.0, 1.0), (30.0, 0.5), (60.0, 0.8)]
    rows = fr.entry_sweep(series, settle_value=2.0, entry_eps=[0.0, 30.0])
    early, late = rows[0], rows[1]
    assert early["entry_price"] == 1.0 and early["max_drawdown"] == 0.5
    assert early["pnl_to_settle"] == 1.0
    assert late["entry_price"] == 0.5 and late["max_drawdown"] == 0.0
    assert late["pnl_to_settle"] == 1.5


def test_settle_parity_picks_atm_strike():
    # window: (epoch, right, strike, price). 7405 is most-ATM (|C-P|=0.7).
    w = [
        (100.0, "C", 7400.0, 6.0), (100.0, "P", 7400.0, 0.3),   # S=7405.7
        (100.0, "C", 7405.0, 1.2), (100.0, "P", 7405.0, 0.5),   # S=7405.7, ATM
        (100.0, "C", 7410.0, 0.1), (100.0, "P", 7410.0, 4.6),   # S=7405.5
    ]
    s = fr.settle_parity(w, near_lo=0.0, near_hi=200.0)
    assert round(s, 2) == 7405.7


def test_settle_parity_uses_latest_print_per_strike():
    # later put print should win (max epoch), changing implied S
    w = [
        (100.0, "C", 7405.0, 1.2), (100.0, "P", 7405.0, 0.5),
        (200.0, "P", 7405.0, 0.9),   # latest put -> S = 7405 + 1.2 - 0.9 = 7405.3
    ]
    assert round(fr.settle_parity(w, 0.0, 300.0), 2) == 7405.3
