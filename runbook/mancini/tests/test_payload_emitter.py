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


from runbook.mancini.schema import Commentary, Trigger


def test_zone_pairing_by_shared_source_quote():
    # listlevels expands "7640-45" into two Levels sharing one source_quote;
    # the emitter reunites them into one zone line: near edge first.
    r = _result([
        Level(price=7640.0, kind="resistance", label="major", source_quote="7640-45 (major)"),
        Level(price=7645.0, kind="resistance", label="major", source_quote="7640-45 (major)"),
    ])
    lines = build_payload(r).splitlines()
    assert lines[1] == "R 7640 7645 major"
    assert len(lines) == 2  # one zone line, not two singles


def test_key_flag_and_note_from_commentary():
    c = Commentary(text="Bear case Monday: begins below 7434 — breakdown trade.",
                   trigger=Trigger(type="price_cross", anchor_prices=[7434.0],
                                   condition_text=""),
                   tags=[], source_quote="Bear case Monday: Begins below 7434.")
    r = ParseResult(date="2026-07-27", instrument="ES", session_bias="",
                    levels=[Level(price=7434.0, kind="support", label="major",
                                  source_quote="7434 (major)")],
                    commentary=[c], raw_excerpt="", model="t",
                    parsed_at="2026-07-27T13:00:00+00:00")
    line = build_payload(r).splitlines()[1]
    assert line.startswith("S 7434 . major key")
    assert '"Bear case Monday: begins below 7434' in line


def test_conf_flag_within_tolerance_and_profile_lines():
    r = _result([Level(price=7461.0, kind="support", label="", source_quote="7461")])
    out = build_payload(r, profile_levels=[("poc", 7461.5), ("val", 7438.0)])
    lines = out.splitlines()
    assert "S 7461 . minor conf" in lines
    assert "P poc 7461.5" in lines
    assert "P val 7438" in lines


def test_conf_flag_respects_tolerance_boundary():
    r = _result([Level(price=7461.0, kind="support", label="", source_quote="7461")])
    at_tol = build_payload(r, profile_levels=[("poc", 7463.0)])      # == 2.0 away
    beyond = build_payload(r, profile_levels=[("poc", 7463.01)])     # > 2.0 away
    assert "conf" in at_tol.splitlines()[1]
    assert "conf" not in beyond.splitlines()[1]


import json, pathlib, pytest

_PARSED = pathlib.Path(__file__).resolve().parents[1] / "parsed" / "2026-07-27.json"


@pytest.mark.skipif(not _PARSED.exists(), reason="no last-good parse on this box")
def test_real_day_payload_shape_and_size():
    from runbook.mancini.schema import ParseResult, Level, Commentary, Trigger
    d = json.loads(_PARSED.read_text())
    r = ParseResult(date=d["date"], instrument=d["instrument"],
                    session_bias=d["session_bias"],
                    levels=[Level(**l) for l in d["levels"]],
                    commentary=[Commentary(text=c["text"],
                                           trigger=Trigger(**c["trigger"]),
                                           tags=c["tags"],
                                           source_quote=c["source_quote"])
                                for c in d["commentary"]],
                    raw_excerpt="", model=d["model"], parsed_at=d["parsed_at"])
    payload = build_payload(r)
    lines = payload.splitlines()
    assert lines[0] == f"v1 {d['date']} ES"
    assert 40 < len(lines) < 100
    assert len(payload.encode()) < 4096  # spec: ~2 KB for a 60-level day
