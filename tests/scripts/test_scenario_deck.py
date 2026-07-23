"""Scenario deck + ladder dropdown payload (st-5ov)."""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from orderflow_drill import DECK, scenario_deck_for  # noqa: E402

DECK_DAY = date(2026, 7, 2)
# Days deliberately frozen into the deck (catalog: "fresh days are added
# deliberately, not automatically"). 7/20 added by st-sfb.
DECK_DAYS = {DECK_DAY.isoformat(), "2026-07-20"}
DECK_BAR_N = 2000


def deck_raw():
    return json.loads(DECK.read_text())


def test_deck_is_ladder_ordered_with_unique_ids():
    raw = deck_raw()
    units = [s["unit"] for s in raw["scenarios"]]
    ids = [s["id"] for s in raw["scenarios"]]
    assert units == sorted(units), "dropdown order IS the curriculum — keep units non-decreasing"
    assert len(ids) == len(set(ids))
    assert ids[:2] == ["T", "F"], "perceptual primitives lead the ladder"
    assert ids[2] == "S2", "prototype first"


def test_refs_are_well_formed():
    for sc in deck_raw()["scenarios"]:
        for r in sc["refs"]:
            assert r["date"] in DECK_DAYS
            assert r["start"] <= r["end"]
            assert r["level"] is None or 5000 < r["level"] < 9000
            assert r["label"]


def test_deck_day_at_deck_bar_n_gets_bar_jumps():
    by_id = {s["id"]: s for s in scenario_deck_for(DECK_DAY, DECK_BAR_N)}
    assert len(by_id["S2"]["refs"]) == 3  # 7/2's three S2 refs; 7/20's filter out
    assert all(r["start"] is not None for r in by_id["S2"]["refs"])
    # [to tag] scenarios ship empty — never guess a reference
    assert by_id["S1"]["refs"] == [] and by_id["S1"]["deck_days"] == []
    assert by_id["S6"]["refs"] == []


def test_other_day_keeps_deck_days_pointer():
    by_id = {s["id"]: s for s in scenario_deck_for(date(2026, 7, 3), DECK_BAR_N)}
    assert by_id["S2"]["refs"] == []
    assert by_id["S2"]["deck_days"] == sorted(DECK_DAYS)


def test_bar_n_mismatch_falls_back_to_level_arming():
    by_id = {s["id"]: s for s in scenario_deck_for(DECK_DAY, 1000)}
    marquee = by_id["S2"]["refs"][0]
    assert marquee["start"] is None and marquee["end"] is None
    assert marquee["level"] == 7511


def test_template_carries_ladder_dropdown_and_marker():
    html = (ROOT / "scripts/orderflow_drill_template.html").read_text()
    assert "/*__DRILL_DATA__*/null" in html
    assert 'id="scenario"' in html
    assert 'id="scendeck"' in html
    assert "buildScenarioSelect()" in html
