"""Callout attribution: which words in a callout are Mancini's. [st-9r51]

Two things are pinned here, and they fail independently:

1. `attribution` itself finds the quoted runs and classifies them. The cases are
   real shapes from the corpus — a callout that is pure quotation, one that
   stitches a quotation into extractor connective tissue, and one that is
   entirely the extractor's characterisation.
2. The result survives to the WRITTEN state file. Same drop-site hazard the
   label tests were written for (test_tracker_labels.py): `LevelInteraction` and
   `build_state` are two independent places the field can die, and asserting on
   an in-memory object catches neither. So these assert on parsed JSON, and on
   the VALUES rather than key presence — a file where every attribution is ""
   satisfies `"callout_attribution" in level` perfectly well.
"""
import json

import pytest

from runbook.mancini import attribution, tracker
from runbook.mancini.schema import Level, ParseResult

# A letter fragment in Mancini's register. Every quoted case below must be
# findable in here verbatim, or the test is asserting on the wrong thing.
LETTER = (
    "Supports are: 7734, 7723, 7714 (major), 7704, 7695 (major).\n"
    "7734 is 1st support down. I won't touch this but if you are desperate to "
    "trade at least wait for it to flush a little, recover, and trigger the "
    "non-acceptance protocol to long. Below there is 7714 and things get more "
    "interesting here. 7714 remains support. This was a clear resistance shelf "
    "until yesterday then broke and flipped to support today. We've trapped "
    "below it numerous times. There is not much below there until 7671 now. "
    "A Failed Breakdown here is highly actionable."
)


def test_whole_callout_quotation_is_quoted():
    text = "A Failed Breakdown here is highly actionable"
    spans = attribution.quoted_spans(text, LETTER)
    assert spans == [text]
    assert attribution.classify(text, spans) == attribution.ATTR_QUOTED


def test_stitched_callout_is_mixed_and_returns_only_the_quoted_runs():
    # The extractor's own "clear resistance shelf ... — bid it (risky)" join
    # around two runs that ARE Mancini's.
    text = ("clear resistance shelf until yesterday then broke and flipped to "
            "support today; the extractor's own words here, then We've trapped "
            "below it numerous times")
    spans = attribution.quoted_spans(text, LETTER)
    assert attribution.classify(text, spans) == attribution.ATTR_MIXED
    assert "clear resistance shelf until yesterday then broke and flipped to support today" in spans
    assert "We've trapped below it numerous times" in spans
    # The invented middle must not be attributed to Mancini.
    assert not any("extractor's own words" in s for s in spans)


def test_pure_gloss_is_gloss():
    # "the preferred entry" is the real case from the 08-13 measurement: zero
    # occurrences in the letter it was attached to, presented as characterisation.
    text = "the preferred entry for this rotation"
    spans = attribution.quoted_spans(text, LETTER)
    assert spans == []
    assert attribution.classify(text, spans) == attribution.ATTR_GLOSS


def test_empty_callout_is_none_not_gloss():
    # A bare `major` level says nothing; that is different from saying something
    # unattributable, and the sentinel must be able to tell them apart.
    assert attribution.classify("", []) == attribution.ATTR_NONE
    assert attribution.quoted_spans("", LETTER) == []


def test_short_overlap_does_not_count_as_quotation():
    # Three words of incidental overlap is below the floor.
    text = "much below there"
    assert attribution.quoted_spans(text, LETTER, min_words=4) == []


def test_curly_punctuation_matches_straight():
    # The letter arrives with curly apostrophes; a callout typed with a straight
    # one must still match, or real quotations score as gloss.
    spans = attribution.quoted_spans("We’ve trapped below it numerous times", LETTER)
    assert spans and "trapped below it numerous times" in spans[0]


def test_annotate_fills_levels_in_place_and_strips_the_major_prefix():
    levels = [
        Level(price=7671, kind="support",
              label="major · A Failed Breakdown here is highly actionable",
              source_quote="7671 (major)"),
        Level(price=7695, kind="support", label="major", source_quote="7695 (major)"),
    ]
    attribution.annotate(levels, LETTER)
    # The `major ·` prefix is not Mancini's prose and must not drag the callout
    # out of `quoted` by sitting outside the quoted run.
    assert levels[0].callout_attribution == attribution.ATTR_QUOTED
    assert levels[0].callout_quotes == ["A Failed Breakdown here is highly actionable"]
    assert levels[1].callout_attribution == attribution.ATTR_NONE
    assert levels[1].callout_quotes == []


# --- the carry-through, asserted on the written file ------------------------

def _candles():
    """Epoch-ms candles spanning the levels, so interactions actually run."""
    return [
        {"open": 7700.0, "high": 7740.0, "low": 7660.0, "close": 7720.0,
         "datetime": 1786806000000},
        {"open": 7720.0, "high": 7745.0, "low": 7710.0, "close": 7730.0,
         "datetime": 1786806060000},
    ]


def _result():
    levels = [
        Level(price=7671, kind="support",
              label="major · A Failed Breakdown here is highly actionable",
              source_quote="7671 (major)"),
        Level(price=7714, kind="support",
              label="major · clear resistance shelf until yesterday then broke "
                    "and flipped to support today",
              source_quote="7714 (major)"),
        Level(price=7734, kind="support",
              label="the preferred entry for this rotation", source_quote="7734"),
        Level(price=7695, kind="support", label="major", source_quote="7695 (major)"),
    ]
    attribution.annotate(levels, LETTER)
    return ParseResult(date="2026-08-28", instrument="ES", session_bias="test",
                       levels=levels, commentary=[])


def _written(tmp_path):
    path = tracker.write_state(tracker.build_state(_result(), _candles()), tmp_path)
    return {lv["price"]: lv for lv in json.loads(path.read_text(encoding="utf-8"))["levels"]}


def test_attribution_reaches_the_written_state_file(tmp_path):
    by_price = _written(tmp_path)
    assert by_price[7671.0]["callout_attribution"] == "quoted"
    assert by_price[7714.0]["callout_attribution"] == "quoted"
    assert by_price[7734.0]["callout_attribution"] == "gloss"
    assert by_price[7695.0]["callout_attribution"] == ""
    # Not just key presence: at least one level must carry real spans, or the
    # whole chain could be writing empty lists and still pass.
    assert by_price[7671.0]["callout_quotes"] == [
        "A Failed Breakdown here is highly actionable"]
    assert by_price[7734.0]["callout_quotes"] == []


def test_callout_reaches_the_written_state_file_without_the_major_prefix(tmp_path):
    by_price = _written(tmp_path)
    assert by_price[7671.0]["callout"] == "A Failed Breakdown here is highly actionable"
    assert by_price[7671.0]["label"].startswith("major")
    assert by_price[7695.0]["callout"] == ""


def test_level_roundtrips_the_new_fields_through_json():
    lv = Level(price=7671, kind="support", label="major · x",
               callout_quotes=["a b c d"], callout_attribution="mixed")
    back = Level.from_dict(json.loads(json.dumps(lv.to_dict())))
    assert back.callout_quotes == ["a b c d"]
    assert back.callout_attribution == "mixed"


def test_parse_published_before_this_field_existed_still_loads():
    # Every parsed/*.json written before 2026-08-28 lacks both keys. They must
    # load as "not computed", not raise and not lose the rest of the level.
    back = Level.from_dict({"price": 7671, "kind": "support",
                            "label": "major · old", "source_quote": "7671 (major)"})
    assert back.callout_quotes == []
    assert back.callout_attribution == ""
    assert back.label == "major · old"


@pytest.mark.parametrize("attr", attribution.ATTRIBUTIONS)
def test_attribution_vocabulary_is_closed(attr):
    assert attr in ("quoted", "mixed", "gloss", "")
