"""Pricing a call: the strike, the exit resolution, the grid, and the two mark
paths on a synthetic day. [st-uc23]"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from strader.blotter import legs as L
from strader.marks.estimated import BinFit, Calibration
from tests.helpers.estimated_mark_corpus import BASIS, write_corpus


def test_strike_for_and_symbol():
    assert L.strike_for("up", 6432.0, 10) == ("C", 6420.0)
    assert L.strike_for("down", 6432.0, 10) == ("P", 6440.0)
    assert L.strike_for("up", 6437.6, 10) == ("C", 6430.0)
    with pytest.raises(ValueError):
        L.strike_for("pin", 6432.0, 10)
    assert L.occ_symbol("2026-03-02", "C", 6420.0) == "SPXW  260302C06420000"
    assert L.hms(53112) == "14:45:12"


def test_resolve_exit_first_touch_wins():
    path = [(1, 10.0), (2, 9.8), (3, 9.6), (4, 12.6), (5, 11.0)]
    assert L.resolve_exit(path, 10.0, stop_pts=0.30, target_pct=25) == ("stop", 3, 9.6)
    assert L.resolve_exit(path, 10.0, stop_pts=0.50, target_pct=25) == ("target", 4, 12.6)
    assert L.resolve_exit(path, 10.0, stop_pts=1.00, target_pct=100) == ("time", 5, 11.0)
    # a mark exactly at the level is a touch
    assert L.resolve_exit([(1, 9.7)], 10.0, stop_pts=0.30, target_pct=25) == ("stop", 1, 9.7)
    assert L.resolve_exit([(1, 12.5)], 10.0, stop_pts=0.30, target_pct=25) == ("target", 1, 12.5)


def test_sweep_grid_has_every_cell():
    path = [(1, 9.85), (2, 9.9), (3, 10.9), (4, 11.2), (5, 10.5)]
    g = L.sweep_grid(path, 10.0, stops=(0.10, 0.30), targets=(10, 25))
    assert set(g) == {"0.10x10", "0.10x25", "0.30x10", "0.30x25"}
    assert g["0.10x10"]["exit_reason"] == "stop" and g["0.10x10"]["pnl_pts"] == -0.15
    assert g["0.30x10"]["exit_reason"] == "target" and g["0.30x10"]["exit_ts"] == "00:00:04"   # 10.9 < 11.0; 11.2 touches
    assert g["0.30x25"]["exit_reason"] == "time" and g["0.30x25"]["pnl_pts"] == 0.5


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    c = tmp_path_factory.mktemp("corpus")
    write_corpus(c, {
        "2026-03-02": {"drift_per_min": +0.35},                      # prints all afternoon
        "2026-03-09": {"drift_per_min": +0.35, "opra_from": "15:00"},  # an OPRA file with no prints in the window
    })
    # 2026-03-09: an empty OPRA file plus a Schwab close-watch snapshot at 14:45
    d = c / "2026-03-09"
    snap_ts = "2026-03-09T19:45:08Z"                                 # 14:45:08 CDT (DST began 2026-03-08)
    cw = []
    for k in range(6300, 6600, 5):
        for side in ("CALL", "PUT"):
            cw.append({"strike": float(k), "side": side, "bid": 9.9, "ask": 10.0, "mark": 9.95, "delta": 0.9})
    (d / "schwab.jsonl").write_text(json.dumps({
        "ts_pull_utc": snap_ts, "stage": "close-watch", "stream": "schwab",
        "provenance": {}, "errors": [],
        "data": {"spot_spx": 6431.7, "spot_es": 6451.7, "chain_window": cw},
    }) + "\n")
    return c


def _cal() -> Calibration:
    fits = {}
    for right in ("C", "P"):
        for lo in range(-20, 20, 5):
            fits[(right, lo)] = BinFit(right, lo, 0.7, 0.5, 1000, 1000, 50, 0.5, 0.0)
    return Calibration(fits=fits, days=("2025-01-02",))


def test_prints_path_prices_from_the_symbols_own_prints(corpus):
    m = L.read_day_market("2026-03-02", corpus)
    assert m.opra is not None and m.bars and not m.chains
    p = L.price_call(m, "up", "14:45", offset_spx=10, stop_pts=0.30, target_pct=25, cal=None)
    assert isinstance(p, L.Priced)
    assert p.mark_path == "prints" and p.right == "C" and p.symbol.startswith("SPXW  260302C")
    assert 53100 <= p.entry_sec <= 53100 + L.ENTRY_GRACE_S
    assert p.exit_reason in ("stop", "target", "time") and p.grid and len(p.grid) == 16
    assert p.mae_pts <= 0 <= p.mfe_pts
    assert abs((p.es_at_entry - BASIS) - p.spx_at_entry) < 3.0    # parity SPX agrees with the synthetic basis
    q = L.price_call(m, "down", "14:45", offset_spx=10, stop_pts=0.30, target_pct=25, cal=None)
    assert isinstance(q, L.Priced) and q.right == "P" and q.strike >= p.strike


def test_fire_after_close_and_no_entry_print(corpus):
    m = L.read_day_market("2026-03-02", corpus)
    assert L.price_call(m, "up", "15:00", offset_spx=10, stop_pts=0.3, target_pct=25, cal=None).reason == "fire-after-close"
    # the synthetic tape prints every 10 s, so the last minute holds 5 prints: thin at a floor of 10
    late = L.price_call(m, "up", "14:59", offset_spx=10, stop_pts=0.3, target_pct=25, cal=None, min_prints=10)
    assert isinstance(late, L.Unpriced) and late.reason == "thin"


def test_estimated_path_from_the_snapshot_ask_resolves_time_only(corpus):
    m = L.read_day_market("2026-03-09", corpus)
    assert m.opra is not None and not m.opra.prints and len(m.chains) == 1
    assert m.chains[0].stage == "close-watch" and m.chains[0].sec_ct == 14 * 3600 + 45 * 60 + 8
    p = L.price_call(m, "up", "14:45", offset_spx=10, stop_pts=0.30, target_pct=25, cal=_cal())
    assert isinstance(p, L.Priced), p
    assert p.mark_path == "estimated" and p.exit_reason == "time" and p.grid is None
    assert p.entry_pts == 10.0 and p.entry_sec == m.chains[0].sec_ct
    assert p.strike == 6420.0 and p.spx_at_entry == 6431.7
    assert p.estimated_exit["would_exit_reason_extreme"] in ("stop", "target", "time")
    assert p.n_marks == 15 and p.exit_sec == 14 * 3600 + 59 * 60 + 59
    assert p.notes and "close-watch" in p.notes[0]
    # no calibration: an honest refusal, not a guess
    assert L.price_call(m, "up", "14:45", offset_spx=10, stop_pts=0.3, target_pct=25, cal=None).reason == "no-calibration"
    # a fire the snapshot cannot serve
    assert L.price_call(m, "up", "14:00", offset_spx=10, stop_pts=0.3, target_pct=25, cal=_cal()).reason == "no-entry-source"


def test_uncalibrated_bin_is_refused(corpus):
    m = L.read_day_market("2026-03-09", corpus)
    cal = Calibration(fits={("P", 10): BinFit("P", 10, 0.7, 0.5, 1000, 1000, 50, 0.5, 0.0)})
    p = L.price_call(m, "up", "14:45", offset_spx=10, stop_pts=0.3, target_pct=25, cal=cal)
    assert isinstance(p, L.Unpriced) and p.reason == "uncalibrated"
