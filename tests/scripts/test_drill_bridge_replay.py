"""The bridge's region-replay door: query → CLI argv → cached JSON. [co-j9t1g]

The bridge shells out to scripts/replay_emissions.py; these tests replace the
subprocess so they run without a corpus and pin the contract the page relies
on: which parameters pass through, that a sentence needs no day, that errors
come back as JSON with the CLI's exit mapped to a status, and that a repeat
of the same ask is served from the cache without a second process.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import drill_bridge  # noqa: E402
from drill_bridge import replay_argv, run_replay  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_cache():
    drill_bridge._replay_cache.clear()
    yield
    drill_bridge._replay_cache.clear()


class _Proc:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = ""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def _fake_run(monkeypatch, stdout, returncode=0, stderr=""):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        return _Proc(stdout, returncode, stderr)

    monkeypatch.setattr(drill_bridge.subprocess, "run", run)
    return calls


# ── argv ───────────────────────────────────────────────────────────────────

def test_sentence_alone_is_enough():
    argv = replay_argv({"say": ["Monday 13:30 to 14:10, sweeps"]})
    assert argv == ["run", "--json", "--say", "Monday 13:30 to 14:10, sweeps"]


def test_flags_pass_through_and_repeat():
    argv = replay_argv({"day": ["2026-08-25"], "between": ["13:30-14:10"], "price": ["7680-7695"],
                        "kind": ["SweepPrint", "PLAN-LEVEL"], "path": ["engine"]})
    assert argv[:4] == ["run", "--json", "--from", "2026-08-25"]
    assert "--between" in argv and "13:30-14:10" in argv
    assert argv.count("--kind") == 2 and "--path" in argv


def test_the_pages_day_rides_beside_the_sentence():
    """A sentence with no day word replays the PAGE's day, not today's."""
    argv = replay_argv({"say": ["13:30 to 14:10"], "day": ["2026-08-25"]})
    assert "--from" in argv and "2026-08-25" in argv and "--say" in argv


def test_nothing_to_replay_is_refused():
    with pytest.raises(ValueError, match="day or a sentence"):
        replay_argv({})


def test_a_malformed_day_is_refused_before_any_process_runs():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        replay_argv({"day": ["25 aug"]})


def test_unknown_parameters_are_dropped_not_forwarded():
    argv = replay_argv({"day": ["2026-08-25"], "rm": ["-rf"], "--knobs": ["x"]})
    assert "rm" not in " ".join(argv) and "--knobs" not in argv


# ── the run ────────────────────────────────────────────────────────────────

def _ok_payload(day="2026-08-25", n=2):
    return json.dumps({"request": {"day": day, "readback": "Replay ..."}, "count": n,
                       "records": [{"line": f"l{i}"} for i in range(n)]})


def test_run_returns_the_clis_json_with_day_and_timing(monkeypatch):
    calls = _fake_run(monkeypatch, _ok_payload())
    code, payload = run_replay({"say": ["Monday sweeps"]})
    assert code == 200
    assert payload["count"] == 2 and payload["day"] == "2026-08-25"
    assert payload["cached"] is False and isinstance(payload["took_ms"], int)
    assert calls[0][1].endswith("replay_emissions.py") and calls[0][2:4] == ["run", "--json"]


def test_a_repeat_ask_is_served_from_the_cache(monkeypatch):
    calls = _fake_run(monkeypatch, _ok_payload())
    run_replay({"say": ["Monday sweeps"]})
    code, payload = run_replay({"say": ["Monday sweeps"]})
    assert code == 200 and payload["cached"] is True
    assert len(calls) == 1


def test_a_different_ask_is_a_different_process(monkeypatch):
    calls = _fake_run(monkeypatch, _ok_payload())
    run_replay({"say": ["Monday sweeps"]})
    run_replay({"say": ["Monday stacks"]})
    assert len(calls) == 2


def test_cli_parse_failure_is_a_400_with_the_clis_message(monkeypatch):
    _fake_run(monkeypatch, json.dumps({"error": "window runs backwards: 14:10 to 13:30"}),
              returncode=2)
    code, payload = run_replay({"say": ["14:10 to 13:30"]})
    assert code == 400 and "backwards" in payload["error"]
    assert drill_bridge._replay_cache == {}, "a failure must not be cached"


def test_cli_crash_without_json_is_a_500_with_stderr(monkeypatch):
    _fake_run(monkeypatch, "", returncode=1, stderr="Traceback ... KeyError")
    code, payload = run_replay({"day": ["2026-08-25"]})
    assert code == 500 and "KeyError" in payload["stderr"]


def test_timeout_is_a_504(monkeypatch):
    def run(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout", 0))
    monkeypatch.setattr(drill_bridge.subprocess, "run", run)
    code, payload = run_replay({"day": ["2026-08-25"]})
    assert code == 504 and "longer than" in payload["error"]


def test_bad_query_is_a_400_from_the_handler_path():
    """The handler wraps run_replay in the same ValueError → 400 net every
    other route uses; here we only pin that replay_argv raises ValueError."""
    with pytest.raises(ValueError):
        run_replay({"to": ["nonsense"], "day": ["2026-08-25"]})


def test_cache_is_bounded(monkeypatch):
    _fake_run(monkeypatch, _ok_payload())
    monkeypatch.setattr(drill_bridge, "REPLAY_CACHE_MAX", 3)
    for i in range(6):
        run_replay({"say": [f"ask {i}"]})
    assert len(drill_bridge._replay_cache) == 3
