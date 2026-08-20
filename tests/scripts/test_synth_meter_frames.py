"""Synthetic meter frames must be schema-true and causal. [st-88ei]

The acceptance criteria name schema drift as the thing that "silently
invalidates every replay" — a synthetic frame the watcher mis-parses produces
a clean-looking result that measures nothing. These pin both halves: the frame
shape against a REAL live journal frame, and the causality of the move.
"""
from __future__ import annotations

import json
import sys
from datetime import date as _date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "measurement"))

import synth_meter_frames as sm  # noqa: E402

LIVE_JOURNAL = ROOT / "data" / "exec" / "continuation-meter-2026-08-04.jsonl"
FLUSH_DAY = _date(2026, 7, 22)


@pytest.fixture(scope="module")
def frames():
    return sm.synth_frames(FLUSH_DAY)


def _live_frame() -> dict:
    """A real frame the live meter wrote, with a populated move."""
    for line in LIVE_JOURNAL.read_text().splitlines():
        f = json.loads(line)
        if f.get("move"):
            return f
    raise AssertionError("no live frame with a move")


def test_top_level_schema_matches_the_live_meter(frames):
    """Every key the live meter emits must be present, spelled the same."""
    live = set(_live_frame())
    missing = live - set(frames[0])
    assert not missing, f"synthetic frames are missing live keys: {missing}"


def test_extra_keys_are_additive_provenance_only(frames):
    """New keys are allowed; RENAMED ones are the drift that invalidates."""
    extra = set(frames[0]) - set(_live_frame())
    assert extra == {"synthetic", "price_source"}, extra
    assert frames[0]["synthetic"] is True
    assert frames[0]["price_source"] == "ES"


def test_move_schema_matches_the_live_meter(frames):
    """`start_t`/`end_t`, not the study's `start_ts`/`end_ts`."""
    live_mv = set(_live_frame()["move"])
    graded = next(f for f in frames if f["move"])
    assert not live_mv - set(graded["move"]), live_mv - set(graded["move"])
    assert "start_t" in graded["move"] and "start_ts" not in graded["move"]


def test_move_timestamps_are_iso_strings_the_watcher_can_slice(frames):
    """flush_watcher.compose does mv['start_t'][11:16] — a datetime would raise."""
    mv = next(f for f in frames if f["move"])["move"]
    assert isinstance(mv["start_t"], str)
    assert datetime.fromisoformat(mv["start_t"])
    assert len(mv["start_t"][11:16]) == 5


def test_frames_are_causal(frames):
    """Frame i's move may not reflect any close after minute i.

    Without this the lead-time numbers are meaningless: a move computed over
    the whole day is 'known' from the first frame.
    """
    for f in frames:
        mv = f["move"]
        if not mv:
            continue
        assert mv["end_t"] <= f["ts"], (
            f"frame {f['ts']} carries a move ending at {mv['end_t']}")


def test_first_frame_cannot_know_the_days_move(frames):
    """The 07-22 flush is ~26 pts; the 08:30 frame must not carry it."""
    first = frames[0]["move"]
    assert first is None or first["size"] < 5.0, first


def test_replay_uses_the_real_watcher_not_a_paraphrase():
    assert sm.watcher.evaluate.__module__ == "flush_watcher"
    assert sm.watcher.FLUSH_PTS == 25.0
    assert sm.watcher.FLUSH_DIR == -1


def test_known_flush_day_is_caught():
    """The whole point of the bead: a detector validated only on days it
    should ignore is not validated."""
    r = sm.replay(FLUSH_DAY)
    assert r["fired"], "2026-07-22 is a known flush day and must fire"
    assert r["fires"][0]["lag_min"] > 0
