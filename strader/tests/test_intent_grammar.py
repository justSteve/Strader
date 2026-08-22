"""The deterministic extractor on the constructed specimen and the guard cases. [st-79z.3]"""
from __future__ import annotations

from pathlib import Path

from strader.intent import grammar
from strader.intent.readback import anchor_echo, read_back
from strader.intent.entities import DayPlan

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "intent" / "constructed-day-read.txt"


def _specimen() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_specimen_four_tiers():
    ex = grammar.extract(_specimen(), "ES")
    # tier 1 — levels, with frames and provenance
    by_value = {lv.price.value: lv for lv in ex.levels}
    assert set(by_value) == {6412.0, 6474.0, 6320.0}, [str(l.price) for l in ex.levels]
    assert by_value[6412.0].kind == "support" and by_value[6412.0].tier == "major"
    assert by_value[6412.0].source == "mancini" and by_value[6412.0].price.frame == "ES"
    assert by_value[6474.0].kind == "pivot" and by_value[6474.0].source == "mancini"
    assert [lv.price.value for lv in ex.levels] == [6412.0, 6474.0, 6320.0]   # as said, pivot after its level
    assert by_value[6320.0].price.frame == "SPX" and by_value[6320.0].label == "consolidation"
    assert by_value[6320.0].kind == "target"
    # tier 2 — regime keyed to a pivot
    assert ex.regime.day_type == "b-day"
    assert ex.regime.control == "bears" and ex.regime.pivot.value == 6474.0
    assert "range-chop" in ex.regime.tags           # "we've been balancing since"
    # tier 3 — one branch, anchored
    assert len(ex.intents) == 1
    i = ex.intents[0]
    assert i.setup.name == "v_down" and i.direction == "long" and i.direction_anchor == "down"
    assert i.window == "window-late" and i.vehicle_hint == "fly" and i.trigger.type == "price_zone"
    assert not i.looks_inverted and not i.confirmed
    # tier 4 — the vehicle
    assert len(ex.structures) == 1
    s = ex.structures[0]
    assert (s.vehicle, s.width, s.expiry, s.right, s.lots, s.center) == ("fly", 20, "0DTE", "CALL", 2, "consolidation")
    # nothing left over, and a time did not become a price
    assert ex.unparsed == []
    assert all(lv.price.value >= grammar.PRICE_FLOOR for lv in ex.levels)


def test_unknown_sentence_is_reported_not_guessed():
    ex = grammar.extract("the cat sat on the mat. sixty-four twelve is the major support.", "ES")
    assert ex.unparsed == ["the cat sat on the mat."]
    assert len(ex.levels) == 1


def test_frame_resolution_and_echo_notes():
    lv, notes = grammar.extract_levels("mark sixty-three twenty spx as the magnet", "ES")
    assert lv[0].price.frame == "SPX" and "because you said so" in notes[0]
    lv, notes = grammar.extract_levels("seventy-seven twenty is major resistance, mancini", "SPX")
    assert lv[0].price.frame == "ES" and "Mancini" in notes[0]
    lv, notes = grammar.extract_levels("seventy-seven twenty is resistance", "SPX")
    assert lv[0].price.frame == "SPX" and "default" in notes[0]


def test_zone_from_two_prices():
    lv, _ = grammar.extract_levels("sixty-four twelve to sixty-four twenty is the shelf", "ES")
    assert len(lv) == 1 and lv[0].price.value == 6412.0 and lv[0].price2.value == 6420.0
    assert lv[0].kind == "support" and lv[0].label == "shelf"


def test_direction_anchor_echo_catches_an_inversion():
    bad, _ = grammar.extract_intent("arm the failed breakdown at sixty-four twelve, short on the reclaim", "ES")
    assert bad.direction == "short" and bad.direction_anchor == "down" and bad.looks_inverted
    echo = anchor_echo(bad)
    assert "INVERTED" in echo and "First move down" in echo and "long" in echo
    good, _ = grammar.extract_intent("arm the failed breakdown at sixty-four twelve, long on the reclaim", "ES")
    assert not good.looks_inverted and "Say yes" in anchor_echo(good)


def test_continuation_family_pays_with_the_move():
    i, _ = grammar.extract_intent("if it breaks sixty-four twelve clean, breakdown short to the next level", "ES")
    assert i.setup.name == "breakdown_short" and i.direction == "short" and i.direction_anchor == "down"
    assert not i.looks_inverted


def test_intent_without_a_first_move_asks_for_it():
    i, _ = grammar.extract_intent("if it holds, long", "ES")
    assert i is not None and i.direction_anchor is None
    assert "flush direction first" in anchor_echo(i)


def test_structure_variants():
    s, _ = grammar.extract_structure("single, first strike in the money, calls, three lots", "ES")
    assert (s.vehicle, s.right, s.lots, s.delta_hint) == ("single", "CALL", 3, "first-ITM")
    s, _ = grammar.extract_structure("fly centered on sixty-three twenty, twenty wide, one dte puts", "SPX")
    assert (s.center, s.width, s.expiry, s.right, s.lots) == ("6320", 20, "1DTE", "PUT", 1)


def test_read_back_speaks_prices_and_names_the_unparsed():
    ex = grammar.extract(_specimen() + " the cat sat on the mat.", "ES")
    plan = DayPlan(date="2026-08-22", levels=ex.levels, regime=ex.regime, intents=ex.intents,
                   structures=ex.structures, unparsed=ex.unparsed)
    eye = read_back(plan)
    ear = read_back(plan, speak=True)
    assert "6412 ES major support, Mancini's" in eye
    assert "sixty-four twelve E S major support, Mancini's" in ear
    assert "Bears control below" in eye and "Day type b day" in ear
    assert "expiring today" in ear and "0DTE" in eye
    assert "I did not understand" in eye and "the cat sat on the mat" in eye
