"""Level-state tracker tests. [st-qih1]

The regression half replays a REAL frozen day — 2026-08-05 plan levels against
2026-08-04 20:00 UTC → 2026-08-06 03:55 UTC Schwab /ES 5-minute candles — and
pins the states the machine produced when the fixture was frozen. Live and
replay share one code path (``build_state`` ← ``compute_interactions``), so
this is also the overnight-brief agreement check the bead requires: a change
that moves these goldens changes the published brief and the Pine markers too,
and must say so.
"""
import json
from pathlib import Path

import pytest

from runbook.mancini import tracker
from runbook.mancini.schema import ParseResult

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def frozen_state():
    candles = json.loads((FIXTURES / "candles-2026-08-05.json").read_text())
    parse = ParseResult.from_dict(
        json.loads((FIXTURES / "parse-2026-08-05.json").read_text()))
    return tracker.build_state(parse, candles)


def test_replay_goldens(frozen_state):
    s = frozen_state
    assert s["day"] == "2026-08-05"
    assert len(s["levels"]) == 47
    assert s["last_price"] == 7763.25
    r = s["rollups"]
    assert r["broken"] == []
    assert r["reclaimed"] == [7774.0, 7763.0, 7755.0, 7783.0, 7790.0,
                              7803.0, 7815.0]
    assert r["tested_held"] == []
    assert len(r["untested_above"]) == 8
    assert len(r["untested_below"]) == 32
    # Ordering contracts: above ascending (next overhead first when read),
    # below descending (nearest underneath first).
    assert r["untested_above"] == sorted(r["untested_above"])
    assert r["untested_below"] == sorted(r["untested_below"], reverse=True)


def test_replay_evidence_chain(frozen_state):
    """Every claim carries tape: the 7774 support's full arc, pinned."""
    lv = {l["price"]: l for l in frozen_state["levels"]}[7774.0]
    assert lv["state"] == "reclaimed"
    assert lv["first_touch"] == "2026-08-04T20:00:00+00:00"
    assert lv["n_touches"] == 31
    assert lv["n_defenses"] == 9
    events = [(e["event"], e["ts"]) for e in lv["events"]]
    assert ("break", "2026-08-04T20:15:00+00:00") in events
    assert ("reclaim", "2026-08-04T20:55:00+00:00") in events
    # Chronological, and every event carries its candle row.
    tss = [e["ts"] for e in lv["events"]]
    assert tss == sorted(tss)
    assert all({"open", "high", "low", "close"} <= set(e["candle"])
               for e in lv["events"])


def test_every_touched_level_has_evidence(frozen_state):
    for lv in frozen_state["levels"]:
        if lv["state"] == "untouched":
            assert lv["events"] == [] and lv["first_touch"] is None
        else:
            assert lv["events"], f"{lv['price']} is {lv['state']} with no evidence"
            assert lv["first_touch"] is not None
            assert lv["last_event_ts"] is not None


def test_distance_from_price(frozen_state):
    s = frozen_state
    for lv in s["levels"]:
        assert lv["distance_from_price"] == round(
            s["last_price"] - lv["price"], 2)


# --- tick / lifecycle -------------------------------------------------------

def _mini_parse(tmp_path, day="2026-08-05"):
    src = json.loads((FIXTURES / "parse-2026-08-05.json").read_text())
    src["date"] = day
    (tmp_path / f"{day}.json").write_text(json.dumps(src), encoding="utf-8")


def test_tick_writes_current_and_day_files(tmp_path):
    parsed, state_root = tmp_path / "parsed", tmp_path / "state"
    parsed.mkdir()
    _mini_parse(parsed)
    candles = json.loads((FIXTURES / "candles-2026-08-05.json").read_text())

    ok, note = tracker.tick("2026-08-05", parsed, state_root, candles=candles)

    assert ok
    cur = json.loads((state_root / "current.json").read_text())
    day = json.loads((state_root / "2026-08-05.json").read_text())
    assert cur["levels"] == day["levels"]
    assert "7 reclaimed" in note


def test_tick_without_parse_waits(tmp_path):
    ok, note = tracker.tick("2026-08-05", tmp_path, tmp_path / "state",
                            candles=[])
    assert not ok and "no parse yet" in note
    assert not (tmp_path / "state" / "current.json").exists()


def test_pidlock_blocks_second_tracker(tmp_path):
    a, b = tracker._PidLock(tmp_path), tracker._PidLock(tmp_path)
    assert a.acquire()
    assert not b.acquire()          # live pid → refused
    a.release()
    assert not (tmp_path / "tracker.pid").exists()


def test_pidlock_reaps_stale(tmp_path):
    (tmp_path / "tracker.pid").write_text("999999999", encoding="utf-8")
    assert tracker._PidLock(tmp_path).acquire()
