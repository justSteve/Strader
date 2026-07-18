"""Offline tests for the Structural Leg Profiler study core. [st-bg4]

Pure-function tests on synthetic trades/bars — no corpus, no I/O. Covers:
time bars + delta, Wilder ATR warm-up, ZigZag leg segmentation and its
determinism, per-leg profile true-delta buckets, naked-POC touch scoring
(bounce / penetrate / never-touched), the repaint audit, delta-divergence
extension events, and volume-anomaly flags.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from market.entities.trade import Trade
from market.measurement import legprofiler as lp

T0 = datetime(2026, 1, 5, 9, 0, 0)


def mk_trade(sec: float, price: float, size: int = 1, side: str = "B") -> Trade:
    return Trade(ts=T0 + timedelta(seconds=sec), symbol="ES.c.0",
                 instrument_id=1, price=price, size=size, side=side)  # type: ignore[arg-type]


def mk_bar(i: int, h: float, l: float, delta: int = 0, volume: int = 100) -> lp.TimeBar:
    start = T0 + timedelta(minutes=i)
    return lp.TimeBar(start_ts=start, end_ts=start + timedelta(seconds=59),
                      open=(h + l) / 2, high=h, low=l, close=(h + l) / 2,
                      volume=volume, delta=delta)


# ── time bars ───────────────────────────────────────────────────────────────
def test_time_bars_ohlcv_and_delta():
    trades = [
        mk_trade(0, 100.0, 2, "B"), mk_trade(20, 101.0, 3, "A"),
        mk_trade(59, 100.5, 1, "N"),          # N: volume yes, delta no
        mk_trade(60, 99.0, 5, "A"),           # next minute
    ]
    bars = lp.build_time_bars(trades)
    assert len(bars) == 2
    b = bars[0]
    assert (b.open, b.high, b.low, b.close) == (100.0, 101.0, 100.0, 100.5)
    assert b.volume == 6 and b.delta == 2 - 3
    assert bars[1].delta == -5


def test_time_bars_reject_out_of_order():
    trades = [mk_trade(10, 100.0), mk_trade(5, 100.0)]
    try:
        lp.build_time_bars(trades)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_time_bars_skip_empty_minutes():
    bars = lp.build_time_bars([mk_trade(0, 100.0), mk_trade(300, 101.0)])
    assert len(bars) == 2   # no synthetic bars for the empty minutes between


# ── ATR ─────────────────────────────────────────────────────────────────────
def test_wilder_atr_warmup_and_value():
    bars = [mk_bar(i, 101.0, 100.0) for i in range(20)]   # constant TR = 1.0
    atrs = lp.wilder_atr(bars, period=14)
    assert atrs[:13] == [None] * 13
    assert all(abs(a - 1.0) < 1e-9 for a in atrs[13:])


# ── leg segmentation ────────────────────────────────────────────────────────
def _zigzag_bars() -> list[lp.TimeBar]:
    """100 -> 90 (down), 90 -> 98 (up), 98 -> 93 (down, unconfirmed tail)."""
    hs = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91,          # falling
          92.5, 94, 95.5, 97, 98,                            # rallying
          97, 96, 95, 94]                                    # falling again
    return [mk_bar(i, h, h - 1.0) for i, h in enumerate(hs)]


def test_segment_legs_zigzag():
    bars = _zigzag_bars()
    atrs = [1.0] * len(bars)                # fixed ATR -> thresh = 2.0 at mult 2
    legs = lp.segment_legs(bars, atrs, mult=2.0)
    assert len(legs) == 2
    down, up = legs
    assert down.direction == "down"
    assert down.start_price == 100.0 and down.end_price == 90.0
    assert down.end_idx == 9
    assert down.confirm_idx > down.end_idx          # confirmed only after reversal
    assert up.direction == "up"
    assert up.start_price == 90.0 and up.end_price == 98.0
    assert up.start_idx == down.end_idx             # legs chain pivot-to-pivot
    # trailing down move never reversed >= 2.0 -> not emitted
    assert legs[-1].direction == "up"


def test_segment_legs_deterministic():
    bars = _zigzag_bars()
    atrs = [1.0] * len(bars)
    assert lp.segment_legs(bars, atrs, 2.0) == lp.segment_legs(bars, atrs, 2.0)


def test_segment_legs_higher_mult_fewer_legs():
    bars = _zigzag_bars()
    atrs = [1.0] * len(bars)
    assert len(lp.segment_legs(bars, atrs, 9.0)) <= len(lp.segment_legs(bars, atrs, 2.0))


# ── per-leg profile ─────────────────────────────────────────────────────────
def test_leg_profile_true_delta_buckets():
    trades = [
        mk_trade(0, 100.0, 10, "B"),
        mk_trade(1, 100.25, 4, "A"),          # same 1.0-pt bucket as 100.0
        mk_trade(2, 101.5, 7, "A"),
        mk_trade(3, 101.5, 2, "N"),           # volume counts, delta excluded
    ]
    prof = lp.build_leg_profile(trades)
    assert prof.profile.prices == (100.0, 101.0)
    assert prof.profile.volumes == (14, 9)
    assert prof.deltas == (6, -7)
    assert prof.poc_price == 100.0


# ── H1 naked POC scoring ────────────────────────────────────────────────────
def _score(path: list[float], level: float = 109.0):
    """Score ``level`` against a scripted price path (one trade / 10s)."""
    trades = [mk_trade(i * 10, float(p)) for i, p in enumerate(path)]
    ts_index = [t.ts for t in trades]
    return lp._score_level(level, trades[0].ts, trades, ts_index, 0, "poc")


def test_h1_arm_below_then_bounce():
    # bucket [109, 110): armed below at <= 108, touch at 109.5, bounce at <= 107
    ev = _score([105.0, 106.0, 109.5, 108.0, 107.0])
    assert ev.approach == "below" and ev.outcome == "bounce"
    assert ev.touch_ts is not None


def test_h1_arm_above_then_penetrate():
    # armed above at >= 111, touch at 109.25, penetrate at <= 107
    ev = _score([112.0, 111.5, 109.25, 108.5, 106.5])
    assert ev.approach == "above" and ev.outcome == "penetrate"


def test_h1_gap_across_bucket_counts_as_touch():
    # armed above, then a print below the bucket with no print inside it
    ev = _score([112.0, 108.0, 106.5])
    assert ev.approach == "above" and ev.outcome == "penetrate"


def test_h1_never_touched():
    ev = _score([105.0, 106.0, 107.5, 106.0, 105.0])
    assert ev.outcome == "never_touched" and ev.touch_ts is None


def test_h1_timeout():
    # touch, then drift inside/near the bucket past the reaction window
    path = [105.0, 106.0, 109.5] + [109.25, 109.5] * 60   # 10s per trade > 15 min
    ev = _score(path)
    assert ev.outcome == "timeout"


def _full_pipeline():
    trades = []
    sec = 0.0
    for px in [110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100,
               101, 102, 103, 104, 105, 104, 103, 102, 101, 100, 99, 98,
               99, 100, 101, 102, 103]:
        for _ in range(60):
            trades.append(mk_trade(sec, float(px), 1, "B" if px % 2 else "A"))
            sec += 1
    bars = lp.build_time_bars(trades)
    atrs = lp.wilder_atr(bars, period=3)
    legs = lp.segment_legs(bars, atrs, mult=2.0)
    ts_index = [t.ts for t in trades]
    profs = [lp.build_leg_profile(lp.leg_trades(trades, ts_index, leg)) for leg in legs]
    events = lp.score_naked_pocs(legs, profs, trades, ts_index, "test")
    return legs, events


def test_h1_pipeline_audit_and_determinism():
    legs, events = _full_pipeline()
    assert legs and events
    assert lp.audit_no_repaint(events, legs) == []
    legs2, events2 = _full_pipeline()
    assert [(e.kind, e.level, e.outcome) for e in events] == \
           [(e.kind, e.level, e.outcome) for e in events2]


# ── H2 delta divergence ─────────────────────────────────────────────────────
def test_h2_divergent_extension_flagged():
    # up leg 100 -> 106: extensions at every bar; delta strong early, negative late
    bars = [
        mk_bar(0, 101, 100, delta=+50), mk_bar(1, 102, 101, delta=+60),
        mk_bar(2, 103, 102, delta=+70), mk_bar(3, 104, 103, delta=-10),
        mk_bar(4, 105, 104, delta=-20), mk_bar(5, 106, 105, delta=-30),
        mk_bar(6, 105, 103.5, delta=-40),
    ]
    leg = lp.Leg("up", 0, 5, 100.0, 106.0, bars[0].start_ts, bars[5].end_ts,
                 6, bars[6].end_ts)
    events = lp.score_delta_divergence([leg], bars)
    # extensions at bars 1..5; bar 1 sets the reference (no event), events at 2..5
    assert len(events) == 4
    div = {e.bar_idx: e.divergent for e in events}
    assert div[2] is False           # cum still rising
    assert div[4] is True and div[5] is True   # new price highs, cum fell
    assert all(e.terminal for e in events if e.bar_idx >= 1)  # short leg: all within 5 bars


# ── H3 volume anomalies ─────────────────────────────────────────────────────
def test_anomaly_flags_and_zones():
    bars = [mk_bar(i, 101, 100, volume=100) for i in range(25)]
    bars[22] = mk_bar(22, 101, 100, volume=500)      # 5x trailing avg
    flags = lp.anomaly_flags(bars, k=2.0, window=20)
    assert flags[22] is True
    assert sum(flags) == 1                            # warm-up + normal bars quiet
    # position zoning within a synthetic up leg spanning all bars
    up_bars = [mk_bar(i, 100 + i * 0.5 + 1, 100 + i * 0.5) for i in range(25)]
    leg = lp.Leg("up", 0, 24, 100.0, up_bars[24].high, up_bars[0].start_ts,
                 up_bars[24].end_ts, 24, up_bars[24].end_ts)
    fl = [False] * 25
    fl[2] = fl[23] = True
    events = lp.score_volume_anomalies([leg], up_bars, fl)
    zones = {e.bar_idx: e.zone for e in events}
    assert zones[2] == "body" and zones[23] == "extreme"
    assert [e.terminal for e in sorted(events, key=lambda e: e.bar_idx)] == [False, True]


def test_extension_anomalies_realtime_variant():
    # up leg 100 -> 103 over bars 0..3, bar 4 reverses; anomaly only on bar 3
    bars = [mk_bar(0, 101, 100), mk_bar(1, 102, 101), mk_bar(2, 101.5, 100.5),
            mk_bar(3, 103, 102), mk_bar(4, 102, 100.5)]
    leg = lp.Leg("up", 0, 3, 100.0, 103.0, bars[0].start_ts, bars[3].end_ts,
                 4, bars[4].end_ts)
    fl = [False, False, False, True, False]
    events = lp.score_extension_anomalies([leg], bars, fl)
    # extensions at bars 1 and 3 only (bar 2 does not extend)
    assert [(e.bar_idx, e.anomalous, e.terminal) for e in events] == \
           [(1, False, True), (3, True, True)]


# ── stats helper ────────────────────────────────────────────────────────────
def test_two_prop_z():
    p1, p2, z = lp.two_prop_z(60, 100, 40, 100)
    assert (round(p1, 2), round(p2, 2)) == (0.6, 0.4)
    assert z > 2.0
    assert lp.two_prop_z(0, 0, 5, 10)[2] == 0.0
