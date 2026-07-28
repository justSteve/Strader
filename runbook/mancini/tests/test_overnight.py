"""Tests for the overnight interaction brief (st-doz).

Synthetic five-minute candles; no network. Timestamps are arbitrary but
increasing (ms epoch). The state semantics under test are the same
close-based ones the Pine renderer implements.
"""
from runbook.mancini.overnight import (
    DEFAULT_TOLERANCE_PTS,
    build_overnight_section,
    compute_interactions,
    letter_window_start,
)
from runbook.mancini.schema import Level, ParseResult

T0 = 1_785_200_000_000  # arbitrary ms epoch base


def bar(i, o, h, l, c):
    return {"datetime": T0 + i * 300_000, "open": o, "high": h, "low": l,
            "close": c, "volume": 100}


def sup(price, label="major"):
    return Level(price=float(price), kind="support", label=label,
                 source_quote=str(price))


def res(price, label=""):
    return Level(price=float(price), kind="resistance", label=label,
                 source_quote=str(price))


def test_untouched_level_stays_untouched():
    candles = [bar(0, 7450, 7455, 7448, 7452)]
    [it] = compute_interactions([sup(7400)], candles)
    assert it.state == "untouched" and it.touches == 0


def test_tested_and_held_counts_defenses():
    candles = [
        bar(0, 7440, 7442, 7434, 7441),   # touches 7434 (+tol), closes above
        bar(1, 7441, 7443, 7435, 7440),   # touches again, holds again
    ]
    [it] = compute_interactions([sup(7434)], candles)
    assert it.state == "tested-held"
    assert it.touches == 2 and it.defenses == 2


def test_broken_requires_close_beyond_tolerance_not_wick():
    wick_only = [bar(0, 7440, 7441, 7425, 7436)]   # wick through, close above
    [it] = compute_interactions([sup(7434)], wick_only)
    assert it.state == "tested-held"  # a flush wick is noise, not a break

    closed_through = [bar(0, 7440, 7441, 7425, 7431.5)]  # close 2.5 under
    [it] = compute_interactions([sup(7434)], closed_through)
    assert it.state == "broken" and it.break_time is not None


def test_break_tolerance_boundary_is_exclusive():
    at_tol = [bar(0, 7440, 7441, 7425, 7432.0)]  # exactly tol under: NOT broken
    [it] = compute_interactions([sup(7434)], at_tol, tolerance=2.0)
    assert it.state != "broken"


def test_reclaimed_after_break_and_extreme_tracked():
    candles = [
        bar(0, 7440, 7441, 7425, 7430),  # break (close 4 under)
        bar(1, 7430, 7432, 7422, 7428),  # still under, deeper extreme 7422
        bar(2, 7428, 7438, 7427, 7436),  # close back above: reclaimed
    ]
    [it] = compute_interactions([sup(7434)], candles)
    assert it.state == "reclaimed"
    assert it.extreme == 7422
    assert it.break_time is not None and it.reclaim_time is not None


def test_resistance_directions_mirror():
    candles = [
        bar(0, 7500, 7509, 7499, 7508.5),  # close 2.5 over 7506: broken
        bar(1, 7508, 7509, 7501, 7503),    # close back under: reclaimed
    ]
    [it] = compute_interactions([res(7506)], candles)
    assert it.state == "reclaimed"


def test_letter_window_start_is_prior_day_4pm_eastern():
    start = letter_window_start("2026-07-28")
    # 2026-07-27 16:00 ET == 20:00 UTC (EDT)
    assert start.strftime("%Y-%m-%d %H:%M") == "2026-07-27 20:00"


def test_build_section_renders_states_and_untouched_count():
    r = ParseResult(date="2026-07-28", instrument="ES", session_bias="",
                    levels=[sup(7434), res(7506), sup(7300)], commentary=[],
                    raw_excerpt="", model="t", parsed_at="x")
    candles = [
        bar(0, 7440, 7441, 7425, 7430),
        bar(1, 7428, 7438, 7427, 7436),
        bar(2, 7500, 7509, 7499, 7508.5),
    ]
    text = build_overnight_section(r, fetch=lambda start: candles)
    assert "## Overnight interaction" in text
    assert "7434 major support: RECLAIMED" in text
    assert "7506 resistance: BROKEN" in text
    assert "1 of 3 levels untouched overnight" in text


def test_build_section_degrades_without_raising():
    r = ParseResult(date="2026-07-28", instrument="ES", session_bias="",
                    levels=[sup(7434)], commentary=[], raw_excerpt="",
                    model="t", parsed_at="x")

    def dead_fetch(start):
        raise RuntimeError("token expired")

    text = build_overnight_section(r, fetch=dead_fetch)
    assert "Overnight data unavailable (token expired)" in text
