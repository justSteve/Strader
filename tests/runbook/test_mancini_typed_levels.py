"""Typed level fields and the closed tag vocabulary. [st-9r51, Stage 1]

`label` is prose; a sentinel cannot branch on it. These add `intent`,
`conviction` and `setup` as closed vocabularies, enforced by validate the way
`kind` already is, and carried to the state file the sentinel reads.

The two enforcement styles here are deliberately different, and the tests pin
both: an out-of-vocabulary **level field** fails the parse, while an
out-of-vocabulary **tag** is folded or dropped and reported. A tag is
descriptive metadata and the parse runs fifteen minutes before the bell —
failing it there costs the session its levels for a spelling.
"""
import json

import pytest

from runbook.mancini import tracker, validate
from runbook.mancini.schema import (Commentary, Level, ParseResult, Trigger,
                                    COMMENTARY_TAGS, LEVEL_CONVICTIONS,
                                    LEVEL_INTENTS, LEVEL_SETUPS, normalize_tags)

SOURCE = "Supports are: 7714 (major), 7704. Resistances are: 7758 (major)."


def _result(levels, commentary=()):
    return ParseResult(date="2026-08-28", instrument="ES", session_bias="b",
                       levels=list(levels), commentary=list(commentary))


# --- defaults and round-tripping -------------------------------------------

def test_defaults_are_the_letter_did_not_say():
    lv = Level(price=7714, kind="support")
    assert (lv.intent, lv.conviction, lv.setup) == ("unstated", "unstated", "none")


def test_parse_written_before_these_fields_existed_reads_as_unstated():
    """Every parsed/*.json before 2026-08-28 lacks all three. They must load as
    'not said', never as a claim about what Mancini meant."""
    lv = Level.from_dict({"price": 7714, "kind": "support", "label": "major"})
    assert (lv.intent, lv.conviction, lv.setup) == ("unstated", "unstated", "none")


def test_explicit_nulls_fall_back_to_the_unstated_values():
    lv = Level.from_dict({"price": 7714, "kind": "support",
                          "intent": None, "conviction": "", "setup": None})
    assert (lv.intent, lv.conviction, lv.setup) == ("unstated", "unstated", "none")


def test_typed_fields_round_trip_through_json():
    lv = Level(price=7714, kind="support", intent="offered",
               conviction="low", setup="breakdown_short")
    back = Level.from_dict(json.loads(json.dumps(lv.to_dict())))
    assert (back.intent, back.conviction, back.setup) == (
        "offered", "low", "breakdown_short")


# --- validation: level fields are strict ------------------------------------

@pytest.mark.parametrize("field,bad", [
    ("intent", "maybe"), ("conviction", "hostile"), ("setup", "scalp")])
def test_out_of_vocabulary_level_field_fails_validation(field, bad):
    lv = Level(price=7714, kind="support", **{field: bad})
    res = validate.check(SOURCE, _result([lv]))
    assert not res.ok
    assert any(field in e and bad in e for e in res.errors)


def test_hostile_conviction_is_gone_on_purpose():
    """The 08-13 plan proposed it. Every candidate in the corpus is already
    intent=avoid plus conviction=low, so a fourth bucket never fires alone."""
    assert "hostile" not in LEVEL_CONVICTIONS
    assert "avoid" in LEVEL_INTENTS


def test_offered_exists_because_mancini_publishes_entries_he_does_not_take():
    """'I don't short ES ... but I still give short entries here.' Calling those
    `trade` misreports him; `avoid` discards a level he deliberately published.
    Steve trades long premium only, so this distinction has to survive."""
    assert "offered" in LEVEL_INTENTS
    lv = Level(price=7758, kind="resistance", intent="offered",
               setup="breakdown_short")
    assert validate.check(SOURCE, _result([lv])).ok


def test_level_reclaim_is_in_the_setup_vocabulary():
    """One of Mancini's two named trigger events, in 8.3% of rich callouts.
    Without it every reclaim would have to be recorded as `none`."""
    assert "level_reclaim" in LEVEL_SETUPS
    lv = Level(price=7714, kind="support", setup="level_reclaim")
    assert validate.check(SOURCE, _result([lv])).ok


@pytest.mark.parametrize("value", LEVEL_INTENTS + LEVEL_CONVICTIONS + LEVEL_SETUPS)
def test_every_vocabulary_value_is_accepted_somewhere(value):
    """Guards against a vocabulary entry the validator would reject — a typo in
    one of the two lists would otherwise only surface on the day it is used."""
    for fname, allowed in (("intent", LEVEL_INTENTS),
                           ("conviction", LEVEL_CONVICTIONS),
                           ("setup", LEVEL_SETUPS)):
        if value in allowed:
            lv = Level(price=7714, kind="support", **{fname: value})
            assert validate.check(SOURCE, _result([lv])).ok
            return
    pytest.fail(f"{value!r} belongs to no vocabulary")


# --- validation: tags are folded, never fatal -------------------------------

def test_known_variant_spellings_fold_to_the_canonical_tag():
    canon, unknown = normalize_tags(
        ["failed-breakdown", "bull-case", "shorts", "long_setup", "in_summary"])
    assert canon == ["failed_breakdown", "bull_case", "short_entry",
                     "long_entry", "summary"]
    assert unknown == []


def test_duplicates_collapse_after_folding():
    canon, _ = normalize_tags(["short", "shorts", "short_entry"])
    assert canon == ["short_entry"]


def test_an_unknown_tag_is_reported_and_dropped_but_never_fails_the_parse():
    c = Commentary(text="t", trigger=Trigger(type="price_zone",
                                             anchor_prices=[7714]),
                   tags=["bull-case", "invented_tag"])
    res = validate.check(SOURCE, _result([Level(price=7714, kind="support")], [c]))
    assert res.ok, "a bad tag must never cost the session its levels"
    assert any("invented_tag" in u for u in res.unknown_tags)
    assert c.tags == ["bull_case"]


def test_tag_vocabulary_has_no_variant_of_its_own_entries():
    """The bug being fixed was two spellings of one idea. The closed list must
    not itself contain a hyphen/underscore pair."""
    normalised = {t.replace("-", "_") for t in COMMENTARY_TAGS}
    assert len(normalised) == len(COMMENTARY_TAGS)


# --- the carry-through to the sentinel's input ------------------------------

def _candles():
    return [
        {"open": 7700.0, "high": 7740.0, "low": 7660.0, "close": 7720.0,
         "datetime": 1786806000000},
        {"open": 7720.0, "high": 7745.0, "low": 7710.0, "close": 7730.0,
         "datetime": 1786806060000},
    ]


def test_typed_fields_reach_the_written_state_file(tmp_path):
    result = _result([
        Level(price=7714, kind="support", label="major · x", intent="trade",
              conviction="high", setup="failed_breakdown"),
        Level(price=7758, kind="resistance", label="major · y", intent="offered",
              conviction="low", setup="breakdown_short"),
        Level(price=7704, kind="support", label=""),
    ])
    path = tracker.write_state(tracker.build_state(result, _candles()), tmp_path)
    by_price = {lv["price"]: lv
                for lv in json.loads(path.read_text(encoding="utf-8"))["levels"]}
    assert by_price[7714.0]["intent"] == "trade"
    assert by_price[7714.0]["setup"] == "failed_breakdown"
    assert by_price[7758.0]["intent"] == "offered"
    assert by_price[7758.0]["conviction"] == "low"
    # An un-annotated level carries the unstated values, not nulls.
    assert by_price[7704.0]["intent"] == "unstated"
    assert by_price[7704.0]["setup"] == "none"
