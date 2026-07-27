"""Tests for payload_emitter (st-5rc). Fixture is deliberately tiny and inline —
golden behavior is asserted line-by-line so failures name the exact line."""
from runbook.mancini.payload_emitter import build_payload
from runbook.mancini.schema import ParseResult, Level


def _result(levels):
    return ParseResult(date="2026-07-27", instrument="ES",
                       session_bias="", levels=levels, commentary=[],
                       raw_excerpt="", model="t", parsed_at="2026-07-27T13:00:00+00:00")


def test_header_and_single_levels():
    r = _result([
        Level(price=7458.0, kind="support", label="major", source_quote="7458 (major)"),
        Level(price=7453.0, kind="support", label="", source_quote="7453"),
        Level(price=7506.0, kind="resistance", label="major", source_quote="7506 (major)"),
    ])
    lines = build_payload(r).splitlines()
    assert lines[0] == "v1 2026-07-27 ES"
    assert "S 7458 . major" in lines
    assert "S 7453 . minor" in lines
    assert "R 7506 . major" in lines


def test_trigger_kind_levels_are_skipped():
    # kind='trigger' extras (e.g. 7437 shelf) are narrative anchors, not ladder
    # levels — the renderer draws the ladder; triggers stay in commentary.
    r = _result([Level(price=7437.0, kind="trigger", label="shelf", source_quote="7437")])
    assert len(build_payload(r).splitlines()) == 1  # header only
