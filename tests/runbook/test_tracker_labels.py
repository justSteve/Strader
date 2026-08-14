"""The level callout must survive all the way to the written state file. [st-ui8m]

The bug this pins had TWO drop sites, and either one alone silently emptied the
field: `LevelInteraction` carried no `label`/`source_quote` at all (so the value
died at construction, before tracker.py was reached), and `build_state` listed
neither key when assembling the per-level dict by hand.

These tests assert on the **written JSON**, not on an in-memory object, and they
assert a **count of non-empty labels** rather than key presence. A test that only
checks `"label" in level` passes happily on a file where every label is "" —
which is exactly the state the bug produced.
"""
import json

from runbook.mancini.schema import Level, ParseResult
from runbook.mancini import tracker


def _candles():
    """Two candles spanning the levels below, so interactions actually run.

    ``datetime`` is epoch-ms, matching the Schwab price-history rows the tracker
    consumes.
    """
    return [
        {"open": 7800.0, "high": 7810.0, "low": 7795.0, "close": 7805.0,
         "datetime": 1786806000000},
        {"open": 7805.0, "high": 7812.0, "low": 7799.0, "close": 7801.0,
         "datetime": 1786806060000},
    ]


def _result():
    return ParseResult(
        date="2026-08-14", instrument="ES", session_bias="test",
        levels=[
            Level(price=7794, kind="support",
                  label="major · flag resistance all week, broke out today",
                  source_quote="7794 (major)"),
            Level(price=7777, kind="support",
                  label="major · significant low set at 830AM this morning",
                  source_quote="7777 (major)"),
            Level(price=7767, kind="support",
                  label="the ideal flush depth for the 7777 Failed Breakdown",
                  source_quote="7767"),
            # Unannotated levels are the majority in a real ladder; they must
            # round-trip as empty strings without breaking the count.
            Level(price=7749, kind="support", label="", source_quote="7749"),
            Level(price=7820, kind="resistance", label="major",
                  source_quote="7820 (major)"),
        ],
        commentary=[],
    )


def test_callout_reaches_the_written_state_file(tmp_path):
    result = _result()
    path = tracker.write_state(tracker.build_state(result, _candles()), tmp_path)
    written = json.loads(path.read_text(encoding="utf-8"))

    # The count that matters: how many levels the parse annotated is how many
    # the state file must carry. Four of the five above have a label.
    expected = sum(1 for lv in result.levels
                   if lv.kind in ("support", "resistance") and lv.label)
    got = sum(1 for lv in written["levels"] if lv.get("label"))
    assert got == expected == 4, (
        f"parse carried {expected} callouts, state file carried {got}")


def test_callout_text_survives_verbatim(tmp_path):
    path = tracker.write_state(tracker.build_state(_result(), _candles()), tmp_path)
    by_price = {lv["price"]: lv
                for lv in json.loads(path.read_text(encoding="utf-8"))["levels"]}

    assert by_price[7767]["label"] == (
        "the ideal flush depth for the 7777 Failed Breakdown")
    assert by_price[7777]["source_quote"] == "7777 (major)"
    # `major` is derived from the same field and is not a substitute for it:
    # it survives the trip, but it cannot reconstruct the prose.
    assert by_price[7777]["major"] is True
    assert by_price[7749]["label"] == ""


def test_major_flag_and_label_stay_independent(tmp_path):
    """A callout containing the word "major" must not promote the level.

    schema.is_major tests a prefix precisely so "lost the major June 11th low"
    stays minor. Pinned here because both fields now travel together and a
    future refactor could plausibly re-derive one from the other.
    """
    result = ParseResult(
        date="2026-08-14", instrument="ES", session_bias="test",
        levels=[Level(price=7794, kind="support",
                      label="lost the major June 11th low here",
                      source_quote="7794")],
        commentary=[],
    )
    path = tracker.write_state(tracker.build_state(result, _candles()), tmp_path)
    lv = json.loads(path.read_text(encoding="utf-8"))["levels"][0]

    assert lv["major"] is False
    assert lv["label"] == "lost the major June 11th low here"
