"""Tests for scripts/speak_replay.py — the replay harness for the phrasebook.

The derivation covered here is correctness-critical rather than cosmetic: a
missing fire_index does not produce an error or an obviously wrong sentence, it
produces a *plausible* one that understates a repeat engagement. Bead: st-mhkp.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "speak_replay",
    Path(__file__).resolve().parents[2] / "scripts" / "speak_replay.py",
)
speak_replay = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(speak_replay)

CENTRAL = ZoneInfo("America/Chicago")


def _confirm(n: int, anchor: float, hhmm: str, **extra) -> dict:
    rec = {
        "run": "test", "n": n, "type": "SetupRecognition",
        "timestamp": datetime(2026, 7, 24, *map(int, hhmm.split(":")),
                              tzinfo=CENTRAL).isoformat(),
        "source": "orderflow.recognizer", "confidence": 0.8,
        "reason": "harness vocabulary", "setup": "failed_breakdown",
        "bias": "bullish", "anchor_price": anchor, "anchor_kind": "support",
        "state": "confirmed", "beats": ["flush", "stall", "flip", "confirm"],
        "mancini_confluence": True,
    }
    rec.update(extra)
    return rec


def _write(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "signals.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return p


def test_absent_fire_index_is_derived_from_confirm_order(tmp_path):
    path = _write(tmp_path, [
        _confirm(1, 7447.0, "08:49"),
        _confirm(2, 7447.0, "09:21"),
        _confirm(3, 7474.0, "10:20"),   # different anchor — its own sequence
        _confirm(4, 7447.0, "09:55"),
    ])
    got = [s.fire_index for s in speak_replay.load(path)]
    assert got == [1, 2, 1, 3]


def test_serialized_fire_index_stays_authoritative(tmp_path):
    # The recognizer's own value wins; the derivation is only a backfill.
    path = _write(tmp_path, [
        _confirm(1, 7447.0, "08:49", fire_index=6),
        _confirm(2, 7447.0, "09:21", fire_index=7),
    ])
    assert [s.fire_index for s in speak_replay.load(path)] == [6, 7]


def test_forming_setups_do_not_consume_a_fire_number(tmp_path):
    # fire_index counts *confirmed* engagements. A forming setup between two
    # confirms must not push the second confirm to number three.
    path = _write(tmp_path, [
        _confirm(1, 7447.0, "08:49"),
        _confirm(2, 7447.0, "09:00", state="forming", beats=["flush"]),
        _confirm(3, 7447.0, "09:21"),
    ])
    confirms = [s for s in speak_replay.load(path) if s.state == "confirmed"]
    assert [s.fire_index for s in confirms] == [1, 2]


def test_run_bookkeeping_records_are_skipped_not_guessed(tmp_path):
    path = _write(tmp_path, [
        {"run": "test", "n": 0, "type": "RunMeta", "date": "2026-07-24"},
        {"run": "test", "n": 1, "type": "DayType", "day_type": "b"},
        _confirm(2, 7447.0, "08:49"),
    ])
    assert len(speak_replay.load(path)) == 1


def test_unparseable_and_unknown_records_are_survived(tmp_path, caplog):
    p = tmp_path / "signals.jsonl"
    p.write_text(
        "not json at all\n"
        + json.dumps({"run": "t", "n": 1, "type": "NoSuchSignal"}) + "\n"
        + json.dumps({"run": "t", "n": 2, "type": "SweepPrint"}) + "\n"   # no timestamp
        + json.dumps(_confirm(3, 7447.0, "08:49")) + "\n"
    )
    signals = speak_replay.load(p)
    assert len(signals) == 1          # the one good record survives
    assert "not JSON" in caplog.text
    assert "unknown record type" in caplog.text


def test_derivation_reaches_the_spoken_sentence(tmp_path, capsys):
    path = _write(tmp_path, [
        _confirm(1, 7447.0, "08:49"),
        _confirm(2, 7447.0, "09:21"),
    ])
    assert speak_replay.main([str(path), "--confirmed-only"]) == 0
    out = capsys.readouterr().out
    assert "the second time at this level today" in out


def test_missing_file_is_reported_not_raised(tmp_path):
    assert speak_replay.main([str(tmp_path / "nope.jsonl")]) == 2
