"""Anti-hallucination validator tests. [co-7lyf]

The poisoned-fixture test is the load-bearing one: a price the model invented
that is NOT in the source must be rejected.
"""
from runbook.mancini.schema import (
    Level,
    Commentary,
    Trigger,
    ParseResult,
)
from runbook.mancini import validate


SOURCE = (
    "ES Trade Plan for Wednesday.\n"
    "Supports are: 5812, 5800 (major), 5785.50.\n"
    "Resistances are: 5840, 5862.\n"
    "Bull case: if we hold 5800, look for a push to 5840 then 5862.\n"
    "Bear case: losing 5785.50 opens the door to 5760.\n"
)


def _result(levels, commentary=None) -> ParseResult:
    return ParseResult(
        date="2026-06-29",
        instrument="ES",
        session_bias="neutral-bullish above 5800",
        levels=levels,
        commentary=commentary or [],
    )


def test_clean_levels_pass():
    levels = [
        Level(price=5812, kind="support", source_quote="Supports are: 5812"),
        Level(price=5800, kind="support", source_quote="5800 (major)"),
        Level(price=5840, kind="resistance", source_quote="Resistances are: 5840"),
    ]
    res = validate.check(SOURCE, _result(levels))
    assert res.ok, res.errors


def test_decimal_level_present_passes():
    # 5785.50 appears as "5785.50" in the source; the model returns 5785.5.
    levels = [Level(price=5785.5, kind="support", source_quote="5785.50")]
    res = validate.check(SOURCE, _result(levels))
    assert res.ok, res.errors


def test_hallucinated_price_rejected():
    # 5999 never appears in the source — the model invented it.
    levels = [
        Level(price=5812, kind="support"),
        Level(price=5999, kind="resistance"),  # poison
    ]
    res = validate.check(SOURCE, _result(levels))
    assert not res.ok
    assert 5999 in res.missing_prices
    assert any("5999" in e for e in res.errors)


def test_substring_number_not_falsely_matched():
    # 581 is a substring of 5812 but is not a standalone number in the source.
    levels = [Level(price=581, kind="support")]
    res = validate.check(SOURCE, _result(levels))
    assert not res.ok
    assert 581 in res.missing_prices


def test_commentary_anchor_validated():
    good = Commentary(
        text="If we hold 5800, target 5840.",
        trigger=Trigger(type="price_zone", anchor_prices=[5800, 5840]),
        source_quote="if we hold 5800, look for a push to 5840",
    )
    res = validate.check(SOURCE, _result([], [good]))
    assert res.ok, res.errors

    bad = Commentary(
        text="Watch 5900 for a breakout.",
        trigger=Trigger(type="price_cross", anchor_prices=[5900]),  # poison
    )
    res2 = validate.check(SOURCE, _result([], [bad]))
    assert not res2.ok
    assert 5900 in res2.missing_prices


ZONE_SOURCE = (
    "ES Trade Plan for Friday.\n"
    "Supports are: 7742, 7725-30 (major), 7718.\n"
    "Bull case: hold the 7725-30 shelf and we run.\n"
    "Copyright 2026-2027 AM Trade Companion Inc.\n"
)


def test_zone_shorthand_upper_edge_accepted():
    # "7725-30" names BOTH 7725 and 7730 — listlevels expands it that way and
    # the parity check then demands 7730, so the validator must see it too.
    # Rejecting it deadlocked the 2026-08-14 parse. [st-f3at]
    levels = [
        Level(price=7725, kind="support", source_quote="7725-30 (major)"),
        Level(price=7730, kind="support", source_quote="7725-30 (major)"),
    ]
    res = validate.check(ZONE_SOURCE, _result(levels))
    assert res.ok, res.errors


def test_zone_shorthand_does_not_admit_arbitrary_prices():
    # Control: the widened rule must not become a blanket pass. 7728 sits
    # inside the zone but is not an edge of it, and was never written.
    levels = [Level(price=7728, kind="support")]
    res = validate.check(ZONE_SOURCE, _result(levels))
    assert not res.ok
    assert 7728 in res.missing_prices


def test_year_range_is_not_read_as_a_zone():
    # "2026-2027" is a date range, not level shorthand: the suffix is as long
    # as the base, so it expands to nothing. (Both years still validate as
    # standalone numbers via the ordinary path — this pins the expander, which
    # is what would otherwise mint prices the letter never named.)
    edges = validate._zone_edges(ZONE_SOURCE)
    assert edges == {7725.0, 7730.0}


def test_invalid_enum_flagged():
    levels = [Level(price=5812, kind="floor")]  # not a valid kind
    res = validate.check(SOURCE, _result(levels))
    assert not res.ok
    assert any("invalid kind" in e for e in res.errors)


def test_empty_source_fails():
    res = validate.check("", _result([Level(price=5812, kind="support")]))
    assert not res.ok
