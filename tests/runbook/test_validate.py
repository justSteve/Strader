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


def test_invalid_enum_flagged():
    levels = [Level(price=5812, kind="floor")]  # not a valid kind
    res = validate.check(SOURCE, _result(levels))
    assert not res.ok
    assert any("invalid kind" in e for e in res.errors)


def test_empty_source_fails():
    res = validate.check("", _result([Level(price=5812, kind="support")]))
    assert not res.ok
