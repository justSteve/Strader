"""The spoken door to a region replay: sentence → day, window, band, kinds. [co-j9t1g]

Every case is a sentence Steve could say. ``today`` is pinned to a Friday so
the relative day words are deterministic.
"""
from __future__ import annotations

from datetime import date, time

import pytest

from strader.intent.replay import ReplayParseError, parse_replay, readback
from strader.intent.session import Session

FRIDAY = date(2026, 8, 28)


def p(text: str):
    return parse_replay(text, today=FRIDAY)


def test_the_memo_sentence():
    r = p("replay Monday 13:30 to 14:10, sweeps and plan-level only")
    assert r.day == date(2026, 8, 24)
    assert r.between == (time(13, 30), time(14, 10))
    assert r.kinds == {"SweepPrint", "PLAN-LEVEL"}
    assert r.price_band is None and r.unknown == ()
    assert readback(r) == "Replay Mon 2026-08-24, 13:30 to 14:10 CT, plan-level and sweeps only."


@pytest.mark.parametrize("text, day, word", [
    ("yesterday first hour", date(2026, 8, 27), "yesterday"),
    ("today", FRIDAY, "today"),
    ("last Tuesday", date(2026, 8, 25), "Tuesday"),
    ("Friday", FRIDAY, "Friday"),               # today is Friday: this Friday
    ("2026-08-25", date(2026, 8, 25), "2026-08-25"),
    ("8/25 sweeps", date(2026, 8, 25), "8/25"),
    ("aug 25th", date(2026, 8, 25), "aug 25th"),
    ("August 25", date(2026, 8, 25), "August 25"),
])
def test_day_words(text, day, word):
    r = p(text)
    assert r.day == day and r.day_word == word


def test_a_mondays_yesterday_is_friday():
    r = parse_replay("yesterday", today=date(2026, 8, 24))
    assert r.day == date(2026, 8, 21)


def test_no_day_word_takes_the_callers_default():
    r = parse_replay("13:30 to 14:10", today=FRIDAY, default_day=date(2026, 8, 25))
    assert r.day == date(2026, 8, 25) and r.day_word == ""


@pytest.mark.parametrize("text, lo, hi", [
    ("13:30 to 14:10", time(13, 30), time(14, 10)),
    ("1:30-2:10", time(13, 30), time(14, 10)),          # before eight with no am/pm: afternoon
    ("1:30 pm to 2:10pm", time(13, 30), time(14, 10)),
    ("1330 to 1410", time(13, 30), time(14, 10)),
    ("between 9 and 10", time(9, 0), time(10, 0)),
    ("from 13:30", time(13, 30), time(23, 59)),
    ("after 13:30", time(13, 30), time(23, 59)),
    ("before 10:00", time(0, 0), time(10, 0)),
    ("around 13:45", time(13, 35), time(13, 55)),
    ("at 13:45", time(13, 40), time(13, 50)),
    ("first hour", time(8, 30), time(9, 30)),
    ("the open", time(8, 30), time(9, 0)),
    ("last hour", time(14, 0), time(15, 0)),
    ("into the close", time(14, 0), time(15, 0)),
    ("midday", time(11, 0), time(13, 0)),
    ("rth", time(8, 30), time(15, 0)),
    ("cash session", time(8, 30), time(15, 0)),
    ("overnight", time(0, 0), time(8, 30)),
])
def test_windows(text, lo, hi):
    assert p(text).between == (lo, hi)


def test_no_window_means_the_whole_day():
    assert p("Monday sweeps").between is None
    assert "the whole day" in readback(p("Monday sweeps"))


def test_a_backwards_window_is_refused_not_guessed():
    with pytest.raises(ReplayParseError, match="backwards"):
        p("14:10 to 13:30")


@pytest.mark.parametrize("text, band", [
    ("7680 to 7695", (7680.0, 7695.0)),
    ("between 7680 and 7695", (7680.0, 7695.0)),
    ("7695 to 7680", (7680.0, 7695.0)),
    ("around 7686", (7681.0, 7691.0)),
    ("near 7686", (7681.0, 7691.0)),
    ("at 7686", (7684.0, 7688.0)),
    ("seventy-six eighty to seventy-six ninety five", (7680.0, 7695.0)),
])
def test_price_bands(text, band):
    assert p(text).price_band == band


def test_above_and_below_are_open_ended():
    up = p("above 7690")
    assert up.price_band[0] == 7690.0 and up.price_band[1] > 10_000
    assert "above 7690" in readback(up)
    down = p("below 7690")
    assert down.price_band[1] == 7690.0 and down.price_band[0] < 0
    assert "below 7690" in readback(down)


def test_a_clock_and_a_price_in_one_sentence_do_not_collide():
    r = p("2026-08-25 between 7680 and 7695 after 13:30")
    assert r.between == (time(13, 30), time(23, 59))
    assert r.price_band == (7680.0, 7695.0)
    assert r.day == date(2026, 8, 25)


@pytest.mark.parametrize("text, kinds", [
    ("sweeps", {"SweepPrint"}),
    ("plan level", {"PLAN-LEVEL"}),
    ("plan-level only", {"PLAN-LEVEL"}),
    ("stacks and divergences", {"ImbalanceStack", "DeltaDivergence"}),
    ("absorption", {"ABSORPTION-CLUSTER", "AbsorptionRead"}),
    ("setups, climax, superlatives", {"SetupRecognition", "CLIMAX", "SUPERLATIVE"}),
    ("everything", set()),
    ("", set()),
])
def test_kind_words(text, kinds):
    assert p(text).kinds == frozenset(kinds)


def test_a_word_nothing_knows_is_reported_not_guessed():
    r = p("replay the open with sweeps and bananas")
    assert r.unknown == ("bananas",)
    assert r.kinds == {"SweepPrint"}
    assert readback(r).endswith("Not understood: bananas.")


def test_noise_words_are_not_unknown():
    r = p("please show me everything that fired in the cash session on Monday")
    assert r.unknown == ()


# ── the verb on a session ──────────────────────────────────────────────────

def test_replay_verb_reads_back_then_lists_the_lines(tmp_path):
    s = Session(plan_dir=tmp_path, day=FRIDAY)
    seen = {}

    def runner(req):
        seen["req"] = req
        return [{"line": "13:46 CT  EVENT PLAN-LEVEL TOUCH  level=7692"},
                {"line": "13:51:37 CT  ENGINE DeltaDivergence bearish  ..."}]

    out = s.replay("Monday 13:30 to 14:10, sweeps and plan-level only", runner=runner)
    assert seen["req"].day == date(2026, 8, 24)
    assert out.splitlines()[0] == "Replay Mon 2026-08-24, 13:30 to 14:10 CT, plan-level and sweeps only."
    assert "2 emissions:" in out and "PLAN-LEVEL TOUCH" in out
    assert any(line.startswith("replay:") for line in [l.split(" ", 1)[1] for l in s.plan.log])


def test_replay_verb_says_when_nothing_fired_and_when_there_is_no_tape(tmp_path):
    s = Session(plan_dir=tmp_path, day=FRIDAY)
    assert s.replay("Monday", runner=lambda r: []).endswith("Nothing fired there.")
    assert "No tape for 2026-08-24" in s.replay("Monday", runner=lambda r: None)


def test_replay_verb_refuses_a_backwards_window(tmp_path):
    s = Session(plan_dir=tmp_path, day=FRIDAY)
    assert s.replay("14:10 to 13:30", runner=lambda r: []).startswith("Cannot replay that")


def test_handle_routes_the_verb(tmp_path):
    s = Session(plan_dir=tmp_path, day=FRIDAY)
    s.replay = lambda rest, runner=None: f"REPLAY<{rest}>"   # type: ignore[method-assign]
    assert s.handle("replay Monday sweeps") == "REPLAY<Monday sweeps>"
