"""The lens state at a fire minute: built from the script's own functions,
never carrying the outcome, honest about a day it cannot score. [st-djb9]"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from strader.blotter import state as S
from tests.helpers.estimated_mark_corpus import write_corpus


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    c = tmp_path_factory.mktemp("corpus")
    write_corpus(c, {
        "2026-03-02": {"drift_per_min": +0.35, "side_bias": 0.7},   # runs up all afternoon on buying
        "2026-03-03": {"drift_per_min": -0.30, "side_bias": 0.3},   # slides on selling
        "2026-03-04": {"es_from": "14:50", "es_to": "15:00"},        # too thin for the lens
    })
    return c


@pytest.fixture(scope="module")
def parsed(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("parsed")
    (p / "2026-03-02.json").write_text(json.dumps({
        "date": "2026-03-02", "session_bias": "leaning up",
        "levels": [{"price": 6400.0, "kind": "support", "label": "s", "source_quote": "major support"},
                   {"price": 6520.0, "kind": "resistance", "label": "r", "source_quote": "lid"}],
    }))
    return p


def test_minute_of_day():
    assert S.minute_of_day("14:45") == 885
    with pytest.raises(ValueError):
        S.minute_of_day("2:45")


def test_state_has_the_three_lenses_and_no_outcome(corpus, parsed):
    inp = S.day_inputs("2026-03-02", corpus=corpus, parsed=parsed)
    assert inp.scoreable and inp.n_prints > 1000
    assert inp.levels is not None and inp.bias == "leaning up"
    st = S.state_at(inp, "14:45")
    assert st is not None
    assert set(st) >= {"day", "T", "pT", "fp", "mc", "gx"}
    assert "out" not in st
    assert st["T"] == "1445" and st["day"] == "2026-03-02"
    fp = st["fp"]
    assert 0.0 <= fp["pos"] <= 1.0
    assert fp["l30_chg"] > 0 and fp["l30_delta"] > 0          # the drift and the side bias
    assert fp["call"] == "up" and fp["pos"] >= 0.8
    # the letter was read (a dict, its keys present); the lens keeps only levels
    # within 25 points of p_T, so the count depends on where the walk ended
    assert st["mc"] is not None and {"floor", "lid", "lost", "taken", "n_levels"} <= set(st["mc"])
    assert st["gx"] is None                                     # no gexbot file on the synthetic day


def test_down_day_reads_down(corpus, parsed):
    inp = S.day_inputs("2026-03-03", corpus=corpus, parsed=parsed)
    st = S.state_at(inp, "14:45")
    assert st["fp"]["l30_delta"] < 0 and st["fp"]["pos"] <= 0.2
    assert st["mc"] is None                                     # no letter for this day


def test_thin_day_is_not_scoreable(corpus, parsed):
    inp = S.day_inputs("2026-03-04", corpus=corpus, parsed=parsed)
    assert not inp.scoreable and inp.skip == "thin"
    assert S.state_at(inp, "14:45") is None
    missing = S.day_inputs("2026-03-05", corpus=corpus, parsed=parsed)
    assert missing.skip == "no-es-file"


def test_fire_before_any_print_is_none(corpus, parsed):
    inp = S.day_inputs("2026-03-02", corpus=corpus, parsed=parsed)
    assert S.state_at(inp, "13:00") is None       # the box 13:00 -> 13:00 is empty
    assert S.state_at(inp, "13:31") is not None


def test_state_is_deterministic(corpus, parsed):
    a = S.state_at(S.day_inputs("2026-03-02", corpus=corpus, parsed=parsed), "14:45")
    b = S.state_at(S.day_inputs("2026-03-02", corpus=corpus, parsed=parsed), "14:45")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_the_lens_script_imports_with_a_neutral_argv(monkeypatch):
    monkeypatch.setattr(S, "_lens", None)
    monkeypatch.setattr("sys.argv", ["blotter_replay.py", "--from", "2026-01-01"])
    mod = S.lens_module()
    assert mod.OUT.endswith("final-hour-lens.jsonl")
    assert callable(mod.lens_state) and callable(mod.segmenter)
