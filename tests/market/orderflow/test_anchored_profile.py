"""Anchored volume profile — bar distribution, value area, anchor. [st-eo0]"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from market.orderflow.anchored_profile import (
    CENTRAL,
    ValueArea,
    anchor_utc,
    build_profile_from_bars,
    value_area,
)


def _bar(low, high, close, volume, ts="2026-08-10T13:30:00+00:00"):
    return {
        "datetime": int(datetime.fromisoformat(ts).timestamp() * 1000),
        "open": low, "high": high, "low": low, "close": close, "volume": volume,
    }


class TestAnchor:
    def test_rth_open_is_0830_central(self):
        got = anchor_utc(date(2026, 8, 10))
        assert got.astimezone(CENTRAL).strftime("%Y-%m-%d %H:%M") == "2026-08-10 08:30"
        assert got.tzinfo is timezone.utc

    def test_anchor_tracks_dst_not_a_fixed_utc_offset(self):
        summer = anchor_utc(date(2026, 8, 10)).hour
        winter = anchor_utc(date(2026, 1, 12)).hour
        assert summer == 13 and winter == 14


class TestBarDistribution:
    def test_volume_is_conserved_exactly(self):
        # 7 does not divide evenly across the 5 buckets 7750..7754.
        prof = build_profile_from_bars([_bar(7750, 7754, 7752, 7)])
        assert prof.total == 7

    def test_remainder_lands_on_the_close_bucket(self):
        prof = build_profile_from_bars([_bar(7750, 7754, 7752, 7)])
        by_price = dict(zip(prof.prices, prof.volumes))
        assert by_price[7752.0] == 3          # 1 each + remainder 2
        assert by_price[7750.0] == by_price[7754.0] == 1

    def test_flat_bar_puts_everything_in_one_bucket(self):
        prof = build_profile_from_bars([_bar(7751, 7751, 7751, 40)])
        assert prof.total == 40
        assert dict(zip(prof.prices, prof.volumes))[7751.0] == 40

    def test_zero_volume_bars_are_skipped_not_counted(self):
        prof = build_profile_from_bars([_bar(7750, 7754, 7752, 0),
                                        _bar(7760, 7760, 7760, 5)])
        assert prof.total == 5

    def test_all_zero_volume_raises_rather_than_emitting_an_empty_profile(self):
        with pytest.raises(ValueError):
            build_profile_from_bars([_bar(7750, 7754, 7752, 0)])

    def test_buckets_are_contiguous_across_a_gap_between_bars(self):
        # Nothing traded 7756-7759; those buckets must exist at zero so the
        # value-area walk cannot step over a hole.
        prof = build_profile_from_bars([_bar(7750, 7755, 7752, 60),
                                        _bar(7760, 7765, 7762, 60)])
        assert dict(zip(prof.prices, prof.volumes))[7757.0] == 0
        assert prof.prices == tuple(float(p) for p in range(7750, 7766))


class TestValueArea:
    def test_poc_is_the_heaviest_bucket(self):
        va = value_area(build_profile_from_bars([
            _bar(7750, 7750, 7750, 10), _bar(7751, 7751, 7751, 100),
            _bar(7752, 7752, 7752, 10)]))
        assert va.poc == 7751.0

    def test_band_encloses_at_least_the_requested_coverage(self):
        va = value_area(build_profile_from_bars(
            [_bar(p, p, p, v) for p, v in
             [(7750, 5), (7751, 20), (7752, 50), (7753, 20), (7754, 5)]]))
        assert va.achieved >= 0.70
        assert va.val <= va.poc <= va.vah

    def test_expansion_takes_the_heavier_side(self):
        # Volume sits above the POC, so the band must open upward. It also
        # stops the moment coverage is met: 100+60 of 222 clears 70% in one
        # step, so VAH lands on 7751 and the thin lows are never included.
        va = value_area(build_profile_from_bars(
            [_bar(p, p, p, v) for p, v in
             [(7748, 1), (7749, 1), (7750, 100), (7751, 60), (7752, 60)]]))
        assert (va.val, va.vah) == (7750.0, 7751.0)
        assert va.achieved >= 0.70

    def test_single_bucket_profile_is_its_own_value_area(self):
        va = value_area(build_profile_from_bars([_bar(7751, 7751, 7751, 40)]))
        assert va.val == va.poc == va.vah == 7751.0
        assert va.achieved == 1.0

    def test_width_and_achieved_report_the_real_band(self):
        va = ValueArea(val=7740.0, poc=7750.0, vah=7760.0,
                       volume=70, total=100, coverage=0.70)
        assert va.width == 20.0 and va.achieved == 0.70


# ── anchor_start: the three anchors Steve asked for (2026-09-10) ──────────────
from datetime import time as _time  # noqa: E402
from market.orderflow.anchored_profile import ANCHORS, GLOBEX_OPEN_CT, anchor_start  # noqa: E402


def _ct(y, m, d, hh, mm):
    from market.orderflow.anchored_profile import CENTRAL
    return datetime(y, m, d, hh, mm, tzinfo=CENTRAL).astimezone(timezone.utc)


class TestAnchorStart:
    def test_the_three_kinds_and_nothing_else(self):
        assert list(ANCHORS) == ["prior", "overnight", "today"]
        with pytest.raises(ValueError, match="prior, overnight, today"):
            anchor_start("lastweek")

    def test_midday_thursday(self):
        now = _ct(2026, 9, 10, 12, 45)                       # Thu
        assert anchor_start("prior", now) == anchor_utc(date(2026, 9, 9))
        assert anchor_start("today", now) == anchor_utc(date(2026, 9, 10))
        assert anchor_start("overnight", now) == anchor_utc(date(2026, 9, 9), GLOBEX_OPEN_CT)

    def test_before_the_open_today_is_the_prior_open(self):
        now = _ct(2026, 9, 10, 8, 15)                        # the 08:15 cron moment
        assert anchor_start("today", now) == anchor_start("prior", now) == anchor_utc(date(2026, 9, 9))
        assert anchor_start("overnight", now) == anchor_utc(date(2026, 9, 9), GLOBEX_OPEN_CT)

    def test_evening_after_globex_open(self):
        now = _ct(2026, 9, 10, 18, 30)                       # Thu evening
        assert anchor_start("overnight", now) == anchor_utc(date(2026, 9, 10), GLOBEX_OPEN_CT)
        assert anchor_start("today", now) == anchor_utc(date(2026, 9, 10))

    def test_monday_overnight_is_sunday_and_weekend_rolls_to_thursday(self):
        mon = _ct(2026, 9, 14, 10, 0)
        assert anchor_start("overnight", mon) == anchor_utc(date(2026, 9, 13), GLOBEX_OPEN_CT)  # Sun 17:00
        assert anchor_start("prior", mon) == anchor_utc(date(2026, 9, 11))                      # Fri
        sat = _ct(2026, 9, 12, 12, 0)
        assert anchor_start("overnight", sat) == anchor_utc(date(2026, 9, 10), GLOBEX_OPEN_CT)  # Thu 17:00
        assert anchor_start("today", sat) == anchor_utc(date(2026, 9, 11))                      # Fri open
        sun_evening = _ct(2026, 9, 13, 19, 0)
        assert anchor_start("overnight", sun_evening) == anchor_utc(date(2026, 9, 13), GLOBEX_OPEN_CT)
