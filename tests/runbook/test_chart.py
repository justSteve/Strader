"""Mancini daily chart (deterministic) tests. [co-t1z9]

Exercises the bridge to the existing pine_emitter and the tradingview-mcp
apply-plan. No live TV / MCP needed — pure generation.
"""
from runbook.mancini.schema import ParseResult, Level, Commentary, Trigger
from runbook.mancini import chart


def _result() -> ParseResult:
    return ParseResult(
        date="2026-06-29",
        instrument="ES",
        session_bias="bullish above 5800",
        levels=[
            Level(price=5800, kind="support", label="major"),
            Level(price=5785.5, kind="support", label=""),
            Level(price=5840, kind="resistance", label="major"),
            Level(price=5862, kind="resistance", label=""),
            Level(price=5820, kind="pivot", label="overnight pivot"),
        ],
        commentary=[
            Commentary(
                text="Holding 5800 targets 5840.",
                trigger=Trigger(type="price_zone", anchor_prices=[5800, 5840]),
            )
        ],
    )


def test_key_prices_from_commentary():
    keys = chart.key_prices(_result())
    assert keys == {5800.0, 5840.0}


def test_bridge_splits_support_resistance():
    email = chart.to_mancini_email(_result())
    sup = sorted(l.price for l in email.support_levels)
    res = sorted(l.price for l in email.resistance_levels)
    assert sup == [5785.5, 5800.0]
    assert res == [5840.0, 5862.0]


def test_bridge_major_annotation_from_label():
    email = chart.to_mancini_email(_result())
    by_price = {l.price: l.annotation for l in email.support_levels + email.resistance_levels}
    assert by_price[5800.0] == "major"
    assert by_price[5785.5] == ""
    assert by_price[5840.0] == "major"


def test_bridge_key_levels_include_commentary_and_pivot():
    email = chart.to_mancini_email(_result())
    # commentary anchors 5800/5840 plus the pivot 5820 (non-S/R kind -> key)
    assert set(email.key_levels) == {5800.0, 5820.0, 5840.0}


def test_emit_pine_contains_levels_and_is_v6():
    pine = chart.emit_pine(_result(), generated_at="2026-06-29T18:00:00")
    assert "//@version=6" in pine
    assert "5800" in pine
    assert "5840" in pine
    # major support 5800 should land in the major-support array
    assert "arrMajSup" in pine


def test_apply_plan_shape():
    plan = chart.apply_plan(_result(), generated_at="2026-06-29T18:00:00")
    assert plan["instrument"] == "ES"
    assert plan["date"] == "2026-06-29"
    assert "//@version=6" in plan["pine_source"]
    assert len(plan["lines"]) == 5
    # the 5800 support is key (cited in commentary), the 5862 resistance is not
    by_price = {l["price"]: l for l in plan["lines"]}
    assert by_price[5800.0]["is_key"] is True
    assert by_price[5862.0]["is_key"] is False
