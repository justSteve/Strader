"""Segmenting the letter down to the plan for the NEXT session. [st-9r51]

The hazard these pin is not a parsing inconvenience. Mancini quotes his own
previous letter inside today's recap — "I expanded on this yesterday:" followed
by yesterday's bull case verbatim — so the forward section headers legitimately
appear twice, and the FIRST one is out of date. Taking it hands the extractor
yesterday's directional plan wearing today's date, on 201 of 353 real letters.

So every test here is built around a letter that contains both, and asserts the
segmenter reads the forward one.
"""
import pytest

from runbook.mancini import segment as seg_mod
from runbook.mancini.segment import segment, render

# A letter in the real shape: recap quoting the prior edition, then doctrine,
# then the ladder, then this session's plan. The recap's bull case names 7500 —
# a price that appears NOWHERE in the forward plan, so any test that reads the
# wrong section fails on content rather than on position.
LETTER = """\
SPX Racks Up Another Green Day. August 28th Plan.

As readers know, the theme for the past several months has been buy dips.

The basic theme heading into today was described in yesterday's newsletter:

Bull case tomorrow: ES is rangebound. Support is 7500 which has been a shelf of
lows since last week. Way above here 7550 remains a key resistance.

Bear case tomorrow: Begins below 7500. That was yesterday's read.

The Run Down on The Level To Level Approach: What, Why, How

This section is intended for newer readers. Ninety percent of intraday moves do
not follow through. Trade level to level. Leave runners.

Trade Recap/Daily Summary

We saw this Monday. ES sold off and recovered.

Trade Plan Friday

Supports are: 7734, 7723, 7714 (major), 7704.

In terms of lvls I'd bid direct: 7734 is 1st support down. I won't touch this.
7714 remains support and a Failed Breakdown there is highly actionable.

Resistances are: 7745, 7758 (major), 7771 (major).

Bull case tomorrow: ES can continue to defend 7714 (or quick traps below).
7758, 7771 are targets.

Bear case tomorrow: Begins below 7659. Likely 7648 trigger down.

In summary for tomorrow: My general lean is we continue up.

As always no crystal balls.
"""


def test_forward_region_starts_at_the_ladder():
    s = segment(LETTER)
    assert s.anchored
    assert s.forward_text.startswith("Supports are:")
    # The recap and the doctrine section are gone.
    assert "The Run Down on The Level" not in s.forward_text
    assert "Trade Recap" not in s.forward_text


def test_bull_case_is_this_session_not_the_quoted_prior_letter():
    """The defect in one assertion. 7500 is only in the quoted prior letter."""
    s = segment(LETTER)
    bull = s.get("bull_case")
    assert "7714" in bull and "7758" in bull
    assert "7500" not in bull
    assert "rangebound" not in bull


def test_bear_case_is_this_session_not_the_quoted_prior_letter():
    s = segment(LETTER)
    bear = s.get("bear_case")
    assert "7659" in bear and "7648" in bear
    assert "7500" not in bear


def test_all_six_sections_found_and_nothing_reported_missing():
    s = segment(LETTER)
    assert set(s.sections) == set(seg_mod.SECTION_NAMES)
    assert s.missing == ()


def test_weekday_named_headers_are_found():
    """`Bull case Monday:` is more common than `Bull case tomorrow:`, and the
    08-13 plan's marker set — 'tomorrow' only — missed every one of them."""
    letter = LETTER.replace("Bull case tomorrow: ES can continue",
                            "Bull case Monday: ES can continue")
    s = segment(letter)
    assert "7714" in s.get("bull_case")
    assert "bull_case" not in s.missing


def test_absent_section_is_reported_not_silently_empty():
    letter = LETTER.replace(
        "Bear case tomorrow: Begins below 7659. Likely 7648 trigger down.\n", "")
    s = segment(letter)
    assert "bear_case" in s.missing
    assert s.get("bear_case") == ""
    assert "bull_case" not in s.missing  # the others still resolve


def test_bid_direct_before_the_ladder_does_not_drag_the_anchor_back():
    """Regression pin for the 2026-03-19 shape.

    That letter quotes its own prior edition's bid-direct paragraph 19,242 chars
    before the real ladder. An earlier draft let that paragraph open the forward
    region, which pulled 19k of recap back in. The ladder is the only marker
    Mancini never quotes; it is the sole anchor.
    """
    letter = LETTER.replace(
        "The basic theme heading into today",
        "In terms of lvls I'd bid direct: I have no position heading into the\n"
        "close but will be willing to engage in the evening.\"\n\n"
        "The basic theme heading into today")
    s = segment(letter)
    assert s.forward_text.startswith("Supports are:")
    assert "I have no position heading into the" not in s.forward_text
    assert "7500" not in s.forward_text


def test_no_ladder_degrades_loudly_rather_than_guessing():
    """25 letters in the corpus are truncated editions with no ladder — and
    `listlevels` finds zero levels in them too, so the run already fails. The
    segmenter must not paper over that with a confident-looking split."""
    s = segment("Some prose with no ladder at all. Bull case tomorrow: up.")
    assert not s.anchored
    assert s.missing == seg_mod.SECTION_NAMES
    assert s.sections == {}
    assert "Bull case tomorrow" in s.forward_text  # nothing thrown away
    assert "NOT ANCHORED" in render(s)


def test_sections_partition_the_forward_region_without_dropping_content():
    """Section bodies concatenated must reconstruct the forward region, so no
    plan content can go missing between two markers."""
    s = segment(LETTER)
    joined = "".join(s.get(n) for n in seg_mod.SECTION_NAMES)
    stripped = "".join(s.forward_text.split())
    assert "".join(joined.split()) == stripped


def test_render_marks_an_absent_section_explicitly():
    letter = LETTER.replace(
        "In summary for tomorrow: My general lean is we continue up.\n", "")
    out = render(segment(letter))
    assert "--- SUMMARY ---" in out
    assert "(absent in this letter)" in out
    assert "SECTIONS ABSENT: summary" in out


def test_kept_fraction_is_a_real_reduction():
    s = segment(LETTER)
    assert 0 < s.kept_fraction < 0.6
    assert s.source_len == len(LETTER)


@pytest.mark.parametrize("header", [
    "Bull case tomorrow:", "Bull case Monday:", "Bull case for tomorrow:",
    "bull case friday:",
])
def test_bull_header_variants(header):
    assert seg_mod.BULL_RE.search(f"...text... {header} ES can defend 7714.")


@pytest.mark.parametrize("not_a_header", [
    "Its tough talking a bull case when we are near the high of day",
    "The bull case is that ES holds",
])
def test_prose_mentions_are_not_headers(not_a_header):
    """`Bull case` in running prose must not open a section — the header form
    is `Bull case <day>:` and the colon is load-bearing."""
    assert not seg_mod.BULL_RE.search(not_a_header)
