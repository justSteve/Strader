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


def _with_commentary(price, text, tags):
    c = Commentary(text=text,
                   trigger=Trigger(type="price_cross", anchor_prices=[price],
                                   condition_text=""),
                   tags=tags, source_quote=text)
    return ParseResult(date="2026-07-27", instrument="ES", session_bias="",
                       levels=[Level(price=price, kind="support", label="major",
                                     source_quote=f"{price:g} (major)")],
                       commentary=[c], raw_excerpt="", model="t",
                       parsed_at="2026-07-27T13:00:00+00:00")


def test_key_flag_and_level_quality_descriptor():
    # A level-narrow phrase becomes a short descriptor, not a spliced sentence.
    r = _with_commentary(7434.0,
                         "7434 is en route but so well tested it is difficult to engage.",
                         ["failed-breakdown", "entry"])
    line = build_payload(r).splitlines()[1]
    assert line.startswith("S 7434 . major key")
    assert line.endswith('"well tested"')


def test_letter_summary_commentary_never_reaches_a_label():
    # st-ybd: bull/bear case, positioning and regime prose belong in the letter
    # summary. Steve: "I never care what M. is holding."
    for tags in (["bull-case", "breakout", "targets"], ["positioning", "runner"],
                 ["mode2", "range"], ["bear-case", "breakdown"], ["summary", "lean"]):
        r = _with_commentary(7533.0,
                             "Bull case: ES spends more time in the 7418-7506 range "
                             "engaging the zones above, then breaks out.", tags)
        line = build_payload(r).splitlines()[1]
        assert '"' not in line, f"{tags} leaked prose onto the label: {line}"


def test_no_matching_descriptor_yields_no_note():
    # Most levels have nothing particular said about them. Silence is correct.
    r = _with_commentary(7398.0,
                         "7398 is below there. One could bid it, but Mancini never "
                         "does when bears control - no knife catching.",
                         ["support", "entry"])
    assert build_payload(r).splitlines()[1] == "S 7398 . major key"


def test_descriptor_text_keeps_its_lowercase_r():
    # Guards the renderer bug from the emitter side: the payload on disk must
    # carry intact spelling, so any future r-dropping is provably renderer-side.
    r = _with_commentary(7458.0, "7458 is first support down.",
                         ["failed-breakdown", "optional"])
    line = build_payload(r).splitlines()[1]
    assert '"first support"' in line
    assert "fist" not in line


def test_range_boundary_outranks_shelf():
    # 7418 is both "an obvious shelf" and the bottom of the range; the range
    # placement is the more actionable of the two.
    r = _with_commentary(7418.0,
                         "Range support is now 7418 - last Thursday's low plus big "
                         "lows Monday and Tuesday, an obvious shelf.",
                         ["support", "range-boundary"])
    assert build_payload(r).splitlines()[1].endswith('"range edge"')


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


def test_push_clipboard_uses_injected_runner():
    sent = {}
    def fake_run(cmd, text):
        sent["cmd"], sent["text"] = cmd, text
        return 0
    from runbook.mancini.payload_emitter import push_clipboard
    rc = push_clipboard("v1 2026-07-27 ES", run=fake_run)
    assert rc == 0 and sent["cmd"] == ["clip.exe"] and sent["text"].startswith("v1 ")


def test_ceiling_probe_sizes():
    from runbook.mancini.payload_emitter import ceiling_probe
    for kb in (2, 4, 8, 16):
        p = ceiling_probe(kb)
        assert p.startswith("v1 2099-01-01 ES")
        assert abs(len(p.encode()) - kb * 1024) < 64


def test_descriptor_attaches_to_nearest_preceding_price():
    # "Safer: wait for 7398 to hold, then recover the 7418 shelf" is anchored on
    # 7398, but the shelf belongs to 7418. Whole-text scanning hung it on 7398.
    r = _with_commentary(7398.0,
                         "7398 is below there. One could bid it, but Mancini never does "
                         "when bears control - no knife catching. Safer: wait for 7398 "
                         "to hold, then recover the 7418 shelf.",
                         ["support", "entry"])
    assert build_payload(r).splitlines()[1] == "S 7398 . major key"


def test_descriptor_after_its_price_in_a_two_price_sentence():
    # Same rule, opposite outcome: "very strong" follows 7311, so 7311 owns it
    # even though 7358 is named earlier in the sentence.
    r = _with_commentary(7311.0,
                         "Nothing below 7358 until 7311, which is a very strong support.",
                         ["support"])
    assert build_payload(r).splitlines()[1].endswith('"very strong"')
