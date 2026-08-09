"""Session-calendar tests. [st-p3lv]

The regression these exist for: 2026-08-08 was a Saturday and the GexBot poller
wrote 58.4 MB into the corpus. Anything below that returns True for a Saturday
has reintroduced it.
"""
from datetime import date, datetime, time

import pytest

from strader.market_calendar import (
    CENTRAL,
    EARLY_CLOSES,
    EARLY_CLOSE_CT,
    HOLIDAYS,
    REGULAR_CLOSE_CT,
    collect_window,
    describe,
    is_early_close,
    is_holiday,
    is_trading_day,
    next_trading_day,
    parse_hm,
    session_close_ct,
    window_state,
    year_is_known,
)


def ct(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=CENTRAL)


# --------------------------------------------------------------------------
# Table hygiene — a mis-derived "observed" date lands on a weekend
# --------------------------------------------------------------------------

@pytest.mark.parametrize("year", sorted(HOLIDAYS))
def test_no_holiday_falls_on_a_weekend(year):
    weekend = [d for d in HOLIDAYS[year] if d.weekday() >= 5]
    assert not weekend, f"{year} holidays on a weekend (bad observed date): {weekend}"


@pytest.mark.parametrize("year", sorted(EARLY_CLOSES))
def test_no_early_close_falls_on_a_weekend(year):
    weekend = [d for d in EARLY_CLOSES[year] if d.weekday() >= 5]
    assert not weekend, f"{year} early closes on a weekend: {weekend}"


@pytest.mark.parametrize("year", sorted(EARLY_CLOSES))
def test_early_close_is_never_also_a_full_holiday(year):
    """2026 has no July 3 early close precisely because July 3 IS the holiday."""
    both = EARLY_CLOSES[year] & HOLIDAYS.get(year, frozenset())
    assert not both, f"{year} lists these as both closed and early-close: {both}"


@pytest.mark.parametrize("year", sorted(HOLIDAYS))
def test_each_year_has_the_nine_or_ten_nyse_holidays(year):
    assert 9 <= len(HOLIDAYS[year]) <= 11, (
        f"{year} has {len(HOLIDAYS[year])} holidays — NYSE observes 10 "
        "(9 when one falls on a Saturday and is not made up)"
    )


# --------------------------------------------------------------------------
# is_trading_day
# --------------------------------------------------------------------------

def test_saturday_is_not_a_trading_day():
    assert not is_trading_day(date(2026, 8, 8))


def test_sunday_is_not_a_trading_day():
    assert not is_trading_day(date(2026, 8, 9))


def test_ordinary_weekday_is_a_trading_day():
    assert is_trading_day(date(2026, 8, 10))


def test_thanksgiving_is_not_a_trading_day():
    assert is_holiday(date(2026, 11, 26))
    assert not is_trading_day(date(2026, 11, 26))


def test_observed_independence_day_is_not_a_trading_day():
    """July 4 2026 is a Saturday; the market closes Friday July 3."""
    assert not is_trading_day(date(2026, 7, 3))
    assert is_trading_day(date(2026, 7, 2))


def test_unknown_year_degrades_to_weekday_only():
    """The fallback must keep collecting, never start skipping sessions."""
    assert not year_is_known(date(2099, 12, 25))
    assert is_trading_day(date(2099, 12, 25))          # a Friday — collect anyway
    assert not is_trading_day(date(2099, 12, 26))      # still a Saturday


def test_next_trading_day_skips_the_weekend():
    assert next_trading_day(date(2026, 8, 7)) == date(2026, 8, 10)


def test_next_trading_day_skips_a_holiday_too():
    assert next_trading_day(date(2026, 11, 25)) == date(2026, 11, 27)


# --------------------------------------------------------------------------
# Early closes
# --------------------------------------------------------------------------

def test_regular_session_closes_at_three():
    assert session_close_ct(date(2026, 8, 10)) == REGULAR_CLOSE_CT


def test_day_after_thanksgiving_closes_at_noon():
    assert is_early_close(date(2026, 11, 27))
    assert session_close_ct(date(2026, 11, 27)) == EARLY_CLOSE_CT


def test_collect_window_clamps_on_an_early_close():
    """15:05 default carries a 5-minute tail past the close; on a noon close
    that tail must ride down to 12:05, not sit three hours past a dead tape."""
    start, until = collect_window(date(2026, 11, 27), "07:30", "15:05")
    assert start == time(7, 30)
    assert until == time(12, 5)


def test_collect_window_is_unchanged_on_a_regular_session():
    start, until = collect_window(date(2026, 8, 10), "07:30", "15:05")
    assert (start, until) == (time(7, 30), time(15, 5))


def test_collect_window_with_an_until_before_the_close_is_left_alone():
    _, until = collect_window(date(2026, 8, 10), "07:30", "14:00")
    assert until == time(14, 0)


# --------------------------------------------------------------------------
# window_state — the gate the collector actually calls
# --------------------------------------------------------------------------

def test_saturday_is_closed_and_points_at_monday():
    state, resume = window_state(ct(2026, 8, 8, 11, 0), "07:30", "15:05")
    assert state == "closed"
    assert resume.date() == date(2026, 8, 10)
    assert resume.time() == time(7, 30)


def test_the_saturday_that_wrote_58mb_never_reports_open():
    """Every minute of 2026-08-08 must be closed — this is the regression."""
    for hour in range(24):
        state, _ = window_state(ct(2026, 8, 8, hour, 30), "07:30", "15:05")
        assert state == "closed", f"08-08 {hour:02d}:30 reported {state}"


def test_before_the_window_is_early_and_resumes_the_same_day():
    state, resume = window_state(ct(2026, 8, 10, 6, 0), "07:30", "15:05")
    assert state == "early"
    assert resume == ct(2026, 8, 10, 7, 30)


def test_inside_the_window_is_open():
    state, resume = window_state(ct(2026, 8, 10, 9, 15), "07:30", "15:05")
    assert state == "open"
    assert resume is None


def test_window_bounds_are_inclusive():
    assert window_state(ct(2026, 8, 10, 7, 30), "07:30", "15:05")[0] == "open"
    assert window_state(ct(2026, 8, 10, 15, 5), "07:30", "15:05")[0] == "open"


def test_after_the_window_is_closed_and_points_at_tomorrow():
    state, resume = window_state(ct(2026, 8, 10, 16, 0), "07:30", "15:05")
    assert state == "closed"
    assert resume == ct(2026, 8, 11, 7, 30)


def test_friday_evening_points_at_monday_not_saturday():
    """The 2026-08-07 failure: it kept polling to 23:59 and then all weekend."""
    state, resume = window_state(ct(2026, 8, 7, 23, 30), "07:30", "15:05")
    assert state == "closed"
    assert resume.date() == date(2026, 8, 10)


def test_holiday_is_closed_even_at_midday():
    state, resume = window_state(ct(2026, 11, 26, 10, 0), "07:30", "15:05")
    assert state == "closed"
    assert resume.date() == date(2026, 11, 27)


def test_early_close_session_shuts_the_window_at_noon_oh_five():
    assert window_state(ct(2026, 11, 27, 11, 59), "07:30", "15:05")[0] == "open"
    assert window_state(ct(2026, 11, 27, 12, 30), "07:30", "15:05")[0] == "closed"


# --------------------------------------------------------------------------
# Odds and ends
# --------------------------------------------------------------------------

def test_parse_hm_rejects_garbage():
    with pytest.raises(ValueError):
        parse_hm("half past eight")


def test_describe_names_the_reason():
    assert "Saturday" in describe(date(2026, 8, 8))
    assert "holiday" in describe(date(2026, 11, 26))
    assert "early close" in describe(date(2026, 11, 27))
    assert "regular session" in describe(date(2026, 8, 10))
