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
