"""MIGauge unit tests (st-3fr phase B) — synthetic minute streams built
around the calibrated afternoon thresholds (climax +510/−594, extreme
+687/−892) and the open-drive weighting flip."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market.internals.gauge import MIGauge, TickMinute, bucket_of
from market.signals.internals_config import TICK_THRESHOLDS

CENTRAL = ZoneInfo("America/Chicago")


def m(hh, mm, high, low, close=None):
    return TickMinute(ts=datetime(2026, 7, 22, hh, mm, tzinfo=CENTRAL),
                      high=high, low=low,
                      close=close if close is not None else (high + low) // 2)


def test_bucket_resolution():
    assert bucket_of(m(8, 30, 0, 0).ts) == "open-drive"
    assert bucket_of(m(9, 15, 0, 0).ts) == "morning"
    assert bucket_of(m(12, 59, 0, 0).ts) == "midday"
    assert bucket_of(m(14, 59, 0, 0).ts) == "afternoon"
    assert bucket_of(m(15, 0, 0, 0).ts) is None
    assert bucket_of(m(8, 29, 0, 0).ts) is None


def test_outside_session_returns_none():
    assert MIGauge().process(m(7, 30, 500, -100)) is None


def test_flush_climax_names_itself():
    g = MIGauge()
    # afternoon negative climax = -594; print a wick right at it
    r = g.process(m(14, 0, 50, -594, close=-300))
    assert r is not None
    assert r.driver == "TICK flush climax"
    assert r.instant <= -75
    assert r.score < 0
    assert r.tick_low == -594


def test_capitulation_beyond_extreme():
    g = MIGauge()
    r = g.process(m(14, 5, 20, -950, close=-600))  # beyond afternoon p99 -892
    assert r.driver == "TICK capitulation"
    assert r.instant == -100


def test_positive_climax_side():
    g = MIGauge()
    r = g.process(m(10, 0, 442, -50, close=200))    # morning pos climax = +442
    assert r.driver == "TICK climax"
    assert r.instant >= 75 and r.score > 0


def test_quiet_tape_is_neutral():
    g = MIGauge()
    r = g.process(m(11, 30, 80, -60, close=10))
    assert r.band == "neutral"
    assert r.driver == "quiet tape"
    assert abs(r.score) < 40


def test_cum_spine_builds_and_dominates_when_wick_quiet():
    g = MIGauge()
    r = None
    # 30 one-sided minutes at ~p90 pace (+120/min close) with modest wicks
    for i in range(30):
        r = g.process(m(9, 20 + i, 160, -20, close=120))
    assert r.cum_tick == 30 * 120
    assert r.cum == 100                       # pegged at the p90 pace scale
    assert r.driver == "cum TICK spine"
    assert r.score > 0


def test_open_drive_weights_favor_cum():
    # identical inputs, different buckets: open-drive weighs cum 0.6
    g1, g2 = MIGauge(), MIGauge()
    r1 = g1.process(m(8, 45, 100, -30, close=120))   # open-drive
    r2 = g2.process(m(10, 45, 100, -30, close=120))  # morning
    assert r1.cum == r2.cum == 100
    # same components, open-drive leans harder on cum
    assert r1.score > r2.score


def test_session_rolls_reset_cum():
    g = MIGauge()
    g.process(m(14, 0, 100, -50, close=300))
    day2 = TickMinute(ts=datetime(2026, 7, 23, 8, 30, tzinfo=CENTRAL),
                      high=50, low=-40, close=10)
    r = g.process(day2)
    assert r.cum_tick == 10                   # not 310


def test_out_of_order_raises():
    g = MIGauge()
    g.process(m(10, 0, 10, -10))
    with pytest.raises(ValueError, match="out-of-order"):
        g.process(m(9, 59, 10, -10))


def test_determinism():
    stream = [m(13, i, 300 - 10 * i, -400 - 12 * i, close=-150) for i in range(30)]
    assert MIGauge().run(stream) == MIGauge().run(stream)


def test_thresholds_cover_all_buckets():
    from market.internals.gauge import bucket_of as _b  # noqa: F401
    for name in ("open-drive", "morning", "midday", "afternoon"):
        assert name in TICK_THRESHOLDS
