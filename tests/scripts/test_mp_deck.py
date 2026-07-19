"""MP drill deck integrity (st-3zh)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DECK = ROOT / "docs/drills/mp-deck.json"


def deck():
    return json.loads(DECK.read_text())


def test_deck_shape():
    d = deck()
    days = d["days"]
    assert len(days) == len({e["date"] for e in days}), "dates unique"
    assert all(e["label"] in {"D", "P", "b", "trend"} for e in days)
    assert all(isinstance(e["provisional"], bool) for e in days)
    assert all(e["note"] for e in days)


def test_two_per_archetype():
    tally: dict[str, int] = {}
    for e in deck()["days"]:
        tally[e["label"]] = tally.get(e["label"], 0) + 1
    assert all(v >= 2 for v in tally.values()), tally
    assert set(tally) == {"D", "P", "b", "trend"}


def test_provisional_labels_flag_the_heuristic_disagreement():
    for e in deck()["days"]:
        if e["provisional"]:
            assert "heuristic" in e["scan"], "provisional entries must record the heuristic's read"
