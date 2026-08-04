import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from drill_bridge import BridgeState  # noqa: E402


@pytest.fixture
def state(tmp_path):
    return BridgeState(log_dir=tmp_path)


def test_log_starts_with_bridge_start(state):
    events = state.tail(10)
    assert events[0]["kind"] == "bridge_start"


def test_state_events_append_and_count(state):
    state.add_state({"kind": "level_armed", "level": 7541.0})
    state.add_state({"kind": "call", "call": "reject"})
    assert state.stats()["events"] == 2
    kinds = [e.get("kind") for e in state.tail(10)]
    assert kinds[-2:] == ["level_armed", "call"]
    assert state.tail(10)[-1]["channel"] == "drill"


def test_coach_ids_are_monotonic_and_polled_incrementally(state):
    a = state.add_coach({"type": "say", "text": "watch the delta"})
    b = state.add_coach({"type": "jump", "bar": 190})
    assert (a["id"], b["id"]) == (1, 2)
    assert [c["id"] for c in state.commands_since(0)] == [1, 2]
    assert [c["id"] for c in state.commands_since(1)] == [2]
    assert state.commands_since(2) == []


def test_invalid_coach_type_rejected(state):
    with pytest.raises(ValueError, match="coach type"):
        state.add_coach({"type": "format_disk"})
    assert state.commands_since(0) == []


def test_coach_commands_also_land_in_log(state):
    state.add_coach({"type": "say", "text": "hello"})
    last = state.tail(5)[-1]
    assert last["channel"] == "coach" and last["type"] == "say"


def test_log_is_valid_jsonl(state):
    state.add_state({"kind": "bar", "bar": 1})
    for line in state.log_path.read_text().splitlines():
        json.loads(line)  # raises on corruption


def test_tail_bounds(state):
    for i in range(30):
        state.add_state({"kind": "bar", "bar": i})
    assert len(state.tail(5)) == 5
    assert len(state.tail(10_000)) == 31  # capped read, full log smaller


# --- end-of-session emissions channel [st-b0n9] ----------------------------

def test_final_emissions_are_served_on_every_bars_response(state):
    """Flush signals and the day's profile levels belong to no bar. They are
    held like meta — replaced, not appended — so a page that opens AFTER the
    close still receives them instead of having missed the one push."""
    state.add_bars([{"o": 1.0}], {"bar_n": 500})
    assert state.bars_since(0)["final"] == []

    final = [{"type": "Level", "price": 7541.0, "bar_i": None}]
    state.add_bars([], None, final)
    # served regardless of `since` — a late page asks for nothing new and must
    # still get the block
    assert state.bars_since(0)["final"] == final
    assert state.bars_since(99)["final"] == final
    assert state.bars_since(0)["total"] == 1     # no phantom bar appended


def test_final_block_is_replaced_not_accumulated(state):
    state.add_bars([], None, [{"type": "Level", "price": 1.0}])
    state.add_bars([], None, [{"type": "Level", "price": 2.0}])
    assert state.bars_since(0)["final"] == [{"type": "Level", "price": 2.0}]


def test_final_must_be_a_list(state):
    with pytest.raises(ValueError, match="final must be a list"):
        state.add_bars([], None, {"not": "a list"})


def test_bars_carry_their_emissions_through_the_bridge(state):
    ev = [{"type": "SweepPrint", "bar_i": 0, "direction": "buy"}]
    state.add_bars([{"o": 1.0, "ev": ev}], {"bar_n": 500})
    got = state.bars_since(0)["bars"]
    assert got[0]["ev"] == ev
    assert got[0]["i"] == 0
