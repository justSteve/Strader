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
# deliberately, not automatically"). 7/20 added by st-sfb; 8/19 added by
# st-z1a1 as the up day the resistance-side (↑) references need.
DECK_DAYS = {DECK_DAY.isoformat(), "2026-07-20", "2026-08-19"}
SIDE_KIND = {"down": "support", "up": "resistance"}
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
            if sc["id"].startswith("S"):
                # direction is an axis (st-z1a1): every level story ref says
                # which side it is on, and the label leads with the arrow
                assert SIDE_KIND[r["side"]] == r["kind"]
                assert r["label"].startswith({"down": "↓", "up": "↑"}[r["side"]])


def test_every_level_story_examples_both_sides():
    """st-z1a1: S2–S5 carry at least one ↓ (support) and one ↑ (resistance)
    reference; S1/S6 are [to tag] on both sides and ship empty."""
    for sc in deck_raw()["scenarios"]:
        if sc["id"] in ("S2", "S3", "S4", "S5"):
            sides = {r["side"] for r in sc["refs"]}
            assert sides == {"down", "up"}, (sc["id"], sides)


def test_deck_day_at_deck_bar_n_gets_bar_jumps():
    by_id = {s["id"]: s for s in scenario_deck_for(DECK_DAY, DECK_BAR_N)}
    refs = by_id["S2"]["refs"]  # 7/2 only; 7/20's and 8/19's filter out
    assert [r["side"] for r in refs].count("down") == 3  # the three ↓ FBDs
    assert [r["side"] for r in refs].count("up") == 3    # the three ↑ bull traps
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
