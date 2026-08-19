"""Deterministic extractor tests (st-ze6) — title plan-day + list levels."""
from datetime import date

from runbook.mancini.listlevels import (
    extract_list_levels,
    parity_check,
    resolve_plan_day,
)

LISTS = (
    "Trade Plan Wednesday\n\n"
    "Supports are: 7539, 7533 (major), 7523, 7512, 7506 (major).\n\n"
    "Resistances are: 7547 (Major), 7554, 7563 (major), 7640-45 (major).\n"
)


def test_title_day_with_ordinal():
    text = "View in browser\n\nThe Range Matures. Breakout Close? July 22nd Plan\n"
    assert resolve_plan_day(text, date(2026, 7, 21)) == date(2026, 7, 22)


def test_title_day_without_ordinal():
    text = "3 Weeks Rangebound. Will It Leave This Week? July 23 Plan\n"
    assert resolve_plan_day(text, date(2026, 7, 22)) == date(2026, 7, 23)


def test_title_day_year_straddle():
    # letter published Dec 31 for the Jan 2 session: reference year differs
    text = "New Year, Same Range. January 2nd Plan\n"
    assert resolve_plan_day(text, date(2026, 12, 31)) == date(2027, 1, 2)


def test_title_day_absent():
    assert resolve_plan_day("no plan phrase here", date(2026, 7, 22)) is None


def test_list_extraction_counts_and_labels():
    levels = extract_list_levels(LISTS)
    supports = [l for l in levels if l.kind == "support"]
    resistances = [l for l in levels if l.kind == "resistance"]
    assert [l.price for l in supports] == [7539, 7533, 7523, 7512, 7506]
    assert [l.label for l in supports] == ["", "major", "", "", "major"]
    # zone 7640-45 expands to both edges, label carried to both
    assert [l.price for l in resistances] == [7547, 7554, 7563, 7640, 7645]
    assert resistances[0].label == "major"          # "(Major)" normalizes
    assert resistances[-2].label == resistances[-1].label == "major"


def test_source_quotes_are_verbatim_tokens():
    levels = extract_list_levels(LISTS)
    by_price = {l.price: l for l in levels}
    assert by_price[7533].source_quote == "7533 (major)"
    assert by_price[7547].source_quote == "7547 (Major)"
    assert by_price[7640].source_quote == "7640-45 (major)"


def test_unparseable_tokens_skipped_not_guessed():
    text = "Supports are: 7539, garbage token, 7523.\n"
    prices = [l.price for l in extract_list_levels(text)]
    assert prices == [7539, 7523]


def test_parity_check_flags_omissions():
    det = extract_list_levels(LISTS)
    parsed = {l.price for l in det} - {7512}
    missing = parity_check(det, parsed)
    assert [l.price for l in missing] == [7512]
    assert parity_check(det, {l.price for l in det}) == []


def test_real_letter_2026_07_23_if_cached():
    """Ground-truth check against the real cached 7/23 letter (skipped when
    the gitignored cache is absent, e.g. fresh clone / CI)."""
    import pytest
    from pathlib import Path
    from runbook.mancini.clean import clean_newsletter
    cache = Path(__file__).resolve().parent.parent.parent.parent / "data" / "mancini-letters"
    blobs = sorted(cache.glob("2026-07-22-*.txt")) if cache.exists() else []
    if not blobs:
        pytest.skip("letter cache absent")
    text = clean_newsletter(blobs[-1].read_text(encoding="utf-8", errors="replace"))
    assert resolve_plan_day(text, date(2026, 7, 22)) == date(2026, 7, 23)
    levels = extract_list_levels(text)
    supports = sum(1 for l in levels if l.kind == "support")
    resistances = sum(1 for l in levels if l.kind == "resistance")
    # the in-session parse recorded 30 supports + 39 resistances from lists
    assert supports >= 25 and resistances >= 30


# ------------------------------------------------- resolve_plan_day_full [co-vp45h]

from datetime import datetime, timezone   # noqa: E402

import pytest   # noqa: E402

from runbook.mancini.listlevels import resolve_plan_day_full, title_line   # noqa: E402


def _sent(y, m, d, hh=20, mm=25):
    """A blob timestamp: Mancini sends ~16:25 ET = 20:25 UTC."""
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def _letter(title, header="Trade Plan Thursday", preview="Preview line.\n\n"):
    return (f"{preview}View in browser\n\n{title}\n\nBody.\n\n{header}\n\n"
            "Supports are: 7539, 7533 (major).\n")


def test_title_line_is_first_text_after_view_in_browser():
    assert title_line(_letter("Can Bulls Hold? Sept 4th Plan")) == "Can Bulls Hold? Sept 4th Plan"
    assert title_line("no marker at all\n") == ""


def test_full_title_plain_and_abbreviated_months():
    # Wednesday 2025-09-03 letter -> Thursday the 4th; "Sept" abbreviation
    r = resolve_plan_day_full(_letter("Can SPX Bulls Hold The Low? Sept 4th Plan"), _sent(2025, 9, 3))
    assert (r.day, r.rule, r.confidence) == (date(2025, 9, 4), "title", 3)
    # "Dec 18 Plan" on a Wednesday 12-17 letter
    r = resolve_plan_day_full(_letter("CPI Tomorrow. Dec 18 Plan"), _sent(2025, 12, 17))
    assert r.day == date(2025, 12, 18)


def test_full_title_trailing_period_without_plan_word():
    r = resolve_plan_day_full(_letter("Have Bulls Dropped The Ball In SPX? July 28.", "Trade Plan Tuesday"),
                              _sent(2026, 7, 27))
    assert (r.day, r.rule) == (date(2026, 7, 28), "title")


def test_full_title_last_date_wins_over_an_earlier_mention():
    r = resolve_plan_day_full(_letter("First Dip Since July 15th. Will It Get Bought? July 29 Plan",
                                      "Trade Plan Tuesday"), _sent(2025, 7, 28))
    assert r.day == date(2025, 7, 29)


def test_full_title_mid_sentence_date_is_not_a_plan_date():
    # "July 4th" is seasonal talk, not the plan; the header carries the day.
    r = resolve_plan_day_full(_letter("Can July 4th Seasonals Keep It Going?", "Trade Plan Tuesday"),
                              _sent(2025, 6, 30))
    assert (r.day, r.rule, r.confidence) == (date(2025, 7, 1), "weekday-header", 2)


def test_full_title_typo_is_caught_by_the_weekday_header():
    # Friday 2026-04-17 letter titled "April 18 Plan" (a Saturday): the header
    # says Monday, so the 20th.
    r = resolve_plan_day_full(_letter("Will SPX Pull Back Next Week? April 18 Plan", "Trade Plan Monday"),
                              _sent(2026, 4, 17))
    assert (r.day, r.rule) == (date(2026, 4, 20), "weekday-header")
    # "June 17 Plan" sent July 16th (a Wednesday): header Thursday -> 07-17
    r = resolve_plan_day_full(_letter("Coiled In A Triangle. June 17 Plan", "Trade Plan Thursday"),
                              _sent(2025, 7, 16))
    assert (r.day, r.rule) == (date(2025, 7, 17), "weekday-header")


def test_full_forwarded_old_letter_keeps_its_title_date():
    # The 2026-07-17 batch: "July 7th Plan" re-sent on the 17th. July 7 2026
    # is a Tuesday and the header says Tuesday — the title is right.
    r = resolve_plan_day_full(_letter("Is The Bottom In For SPX? July 7th Plan", "Trade Plan Tuesday"),
                              _sent(2026, 7, 17, 10, 17))
    assert (r.day, r.rule) == (date(2026, 7, 7), "title")


def test_full_title_pair_prefers_the_session_the_tape_confirms():
    letter = _letter("Is The Rally Done? Nov 27/28 Plan", "Trade Plan Thursday")
    # Thanksgiving (27th) has no session; the 28th does
    r = resolve_plan_day_full(letter, _sent(2025, 11, 26), has_session=lambda d: d != date(2025, 11, 27))
    assert (r.day, r.rule, r.also) == (date(2025, 11, 28), "title", None)
    # both trade ("July 3rd/6th"): first is the day, second is filed too
    r = resolve_plan_day_full(_letter("Dip Bought Next Week? July 3rd/6th Plan", "Trade Plan Monday"),
                              _sent(2026, 7, 2), has_session=lambda d: True)
    assert (r.day, r.also) == (date(2026, 7, 3), date(2026, 7, 6))
    # no tape knowledge: the later day
    r = resolve_plan_day_full(letter, _sent(2025, 11, 26))
    assert (r.day, r.also) == (date(2025, 11, 28), None)


def test_full_same_day_when_sent_before_the_open():
    # 2026-07-17 07:58 UTC = 02:58 CT Friday, "July 17 Plan": the same day
    r = resolve_plan_day_full(_letter("When Will It Break Out? July 17 Plan", "Trade Plan Friday"),
                              _sent(2026, 7, 17, 7, 58))
    assert (r.day, r.rule) == (date(2026, 7, 17), "title")
    # no title, no header, sent before the open on a weekday -> that day
    r = resolve_plan_day_full("nothing useful", _sent(2026, 7, 17, 7, 58))
    assert (r.day, r.rule, r.confidence) == (date(2026, 7, 17), "next-session", 1)


def test_full_next_session_fallback_skips_the_weekend():
    # Friday evening, truncated email, no title, no header
    r = resolve_plan_day_full("This post may be too long for email.", _sent(2025, 12, 5))
    assert (r.day, r.rule) == (date(2025, 12, 8), "next-session")


def test_full_weekday_header_too_far_out_falls_through():
    # Monday resend saying "Trade Plan Monday" after the open: next Monday is
    # a week off — not a plan; the fallback gives Tuesday and the caller's
    # resend clustering puts it right.
    r = resolve_plan_day_full(_letter("Will The Trend Continue? August 15 Plan", "Trade Plan Monday"),
                              _sent(2026, 8, 17, 16, 51))
    assert (r.day, r.rule) == (date(2026, 8, 18), "next-session")


def test_full_requires_aware_datetime():
    with pytest.raises(ValueError):
        resolve_plan_day_full("x", datetime(2026, 7, 17, 20, 0))
