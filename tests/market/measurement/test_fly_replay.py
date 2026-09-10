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


# --------------------------------------------------------------------------
# collect_window reads through the OPRA duplicate guard [st-c078]
#
# These touch a file, unlike everything above. A doubled OPRA tape (a batch
# pull that ran twice — 2026-07-20) used to inflate this study's "leg prints"
# counts 2x; the fly price itself survived, because a forward-filled last
# trade does not care how many times it was written. The counts are what the
# study reports on screen, so they have to be the real ones.
# --------------------------------------------------------------------------

def _tape(tmp_path, rows):
    import json
    p = tmp_path / "databento_opra.jsonl"
    p.write_text("".join(
        json.dumps({
            "ts_pull_utc": pull,
            "provenance": {"ts_event": ts},
            "data": {"symbol": sym, "instrument_id": iid, "price": px,
                     "size": sz, "sequence": seq},
        }) + "\n" for ts, sym, iid, px, sz, seq, pull in rows), encoding="utf-8")
    return p


_EP = 1753120800.0   # 2026-07-21 13:00:00 CT, whole seconds


def _iso(offset_s: int) -> str:
    from datetime import datetime, timezone
    t = datetime.fromtimestamp(_EP + offset_s, timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + ".000000000+00:00"


_THREE = [
    (_iso(0), "SPXW  260721C07510000", 111, 1.35, 1, 900, "PULL-A"),
    (_iso(1), "SPXW  260721C07515000", 222, 0.80, 2, 901, "PULL-A"),
    (_iso(2), "SPXW  260721C07520000", 333, 0.40, 3, 902, "PULL-A"),
]


def test_collect_window_drops_duplicates_from_a_doubled_tape(tmp_path):
    doubled = _THREE + [(ts, sym, iid, px, sz, seq, "PULL-B")
                        for ts, sym, iid, px, sz, seq, _ in _THREE]
    p = _tape(tmp_path, doubled)
    w = fr.collect_window(p, "260721", _EP, _EP + 60)
    assert len(w) == 3
    legs = fr.legs_from_window(w, {7510.0, 7515.0, 7520.0}, "C")
    assert [len(legs[k]) for k in (7510.0, 7515.0, 7520.0)] == [1, 1, 1]


def test_collect_window_leaves_a_clean_tape_alone(tmp_path):
    p = _tape(tmp_path, _THREE)
    assert len(fr.collect_window(p, "260721", _EP, _EP + 60)) == 3


def test_collect_window_dedup_false_is_the_pre_guard_read(tmp_path):
    doubled = _THREE + [(ts, sym, iid, px, sz, seq, "PULL-B")
                        for ts, sym, iid, px, sz, seq, _ in _THREE]
    p = _tape(tmp_path, doubled)
    assert len(fr.collect_window(p, "260721", _EP, _EP + 60, dedup=False)) == 6


def test_collect_window_keeps_distinct_prints_at_one_instant(tmp_path):
    """Same contract, same nanosecond, same price and size, different sequence.

    These are real fills — 4.97% of the clean 2026-07-21 tape looks like this —
    and a narrower key would eat them.
    """
    ts = _iso(0)
    p = _tape(tmp_path, [
        (ts, "SPXW  260721C07510000", 111, 1.35, 1, 900, "PULL-A"),
        (ts, "SPXW  260721C07510000", 111, 1.35, 1, 901, "PULL-A"),
    ])
    assert len(fr.collect_window(p, "260721", _EP, _EP + 60)) == 2
