"""Window, loop and failure logic of the last-hour Schwab chain leg. [st-9dyz]

No Schwab client is ever imported here: ``run()`` takes ``pull`` injected, and
the script defers the real import into ``main()``. The gate hook allows pytest;
these tests must keep it that way.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, time as _time, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market.corpus.paths import CENTRAL  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "corpus_poll_schwab_late_chain", ROOT / "scripts" / "corpus_poll_schwab_late_chain.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def ct(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=CENTRAL)


START, UNTIL = _time(14, 0), _time(15, 1)


def test_module_does_not_import_the_schwab_reach_at_load():
    assert "market.corpus.schwab_stream" not in sys.modules
    assert "schwab" not in sys.modules and "broker_schwab" not in sys.modules


@pytest.mark.parametrize("now,expected", [
    (ct(2026, 8, 26, 13, 59), "before"),
    (ct(2026, 8, 26, 14, 0), "open"),
    (ct(2026, 8, 26, 15, 0, 59), "open"),
    (ct(2026, 8, 26, 15, 1), "after"),
    (ct(2026, 8, 29, 14, 30), "weekend"),   # Saturday
])
def test_window_state(now, expected):
    assert mod.window_state(now, START, UNTIL) == expected


def test_window_state_reads_central_even_from_utc_input():
    from datetime import timezone
    utc = datetime(2026, 8, 26, 19, 30, tzinfo=timezone.utc)   # 14:30 CDT
    assert mod.window_state(utc, START, UNTIL) == "open"


def test_seconds_until_start():
    assert mod.seconds_until(ct(2026, 8, 26, 13, 58), START) == 120.0
    assert mod.seconds_until(ct(2026, 8, 26, 14, 5), START) == 0.0


def _fake_pull_factory(errors_by_call=None):
    calls = []

    def pull(symbol):
        n = len(calls)
        calls.append(symbol)
        errs = (errors_by_call or {}).get(n, [])
        return {"ts_pull_utc": f"2026-08-26T19:{n:02d}:00Z", "stream": "schwab",
                "data": {"spot_spx": 7680.0 + n, "spot_es": 7694.0 + n, "chain_window": []},
                "errors": list(errs)}
    return pull, calls


class Clock:
    """A clock that advances only when the loop sleeps."""
    def __init__(self, start):
        self.now = start
        self.sleeps = []

    def now_fn(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now = self.now + timedelta(seconds=s)


def test_loop_polls_every_interval_inside_window_and_stamps_stage(tmp_path, monkeypatch):
    out = tmp_path / "late.jsonl"
    manifest_calls = []
    monkeypatch.setattr(mod, "update_manifest", lambda **kw: manifest_calls.append(kw))
    pull, calls = _fake_pull_factory()
    clock = Clock(ct(2026, 8, 26, 15, 0, 0))            # 60s of window at 30s cadence
    rc = mod.run(pull=pull, start=START, until=UNTIL, interval=30.0,
                 now_fn=clock.now_fn, sleep_fn=clock.sleep, out_path=lambda: out)
    assert rc == 0
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(rows) == len(calls) == 2
    assert all(r["stage"] == "late-chain" for r in rows)
    assert clock.sleeps == [30.0, 30.0]
    # the tail manifest write carries the cycle count
    assert manifest_calls and manifest_calls[-1]["increment_cycles"] == 2


def test_started_early_waits_for_the_window(tmp_path, monkeypatch):
    out = tmp_path / "late.jsonl"
    monkeypatch.setattr(mod, "update_manifest", lambda **kw: None)
    pull, calls = _fake_pull_factory()
    clock = Clock(ct(2026, 8, 26, 13, 59, 30))
    # window is 14:00..14:00:30 effectively: make until tiny so it runs once
    rc = mod.run(pull=pull, start=START, until=_time(14, 1), interval=30.0,
                 now_fn=clock.now_fn, sleep_fn=clock.sleep, out_path=lambda: out)
    assert rc == 0
    assert clock.sleeps[0] == 30.0          # waited to 14:00:00 first
    assert len(calls) == 2                  # 14:00:00 and 14:00:30


def test_started_after_window_exits_zero_without_polling(tmp_path):
    pull, calls = _fake_pull_factory()
    rc = mod.run(pull=pull, start=START, until=UNTIL, now_fn=lambda: ct(2026, 8, 26, 15, 30),
                 sleep_fn=lambda s: None, out_path=lambda: tmp_path / "x.jsonl")
    assert rc == 0 and calls == []


def test_weekend_exits_zero_without_polling(tmp_path):
    pull, calls = _fake_pull_factory()
    rc = mod.run(pull=pull, start=START, until=UNTIL, now_fn=lambda: ct(2026, 8, 30, 14, 30),
                 sleep_fn=lambda s: None, out_path=lambda: tmp_path / "x.jsonl")
    assert rc == 0 and calls == []


def test_auth_error_exits_2_immediately_and_still_writes_the_row(tmp_path, monkeypatch):
    out = tmp_path / "late.jsonl"
    notes = []
    monkeypatch.setattr(mod, "update_manifest", lambda **kw: notes.append(kw))
    pull, calls = _fake_pull_factory({0: ["get_quotes: HTTPError: 401 Unauthorized"]})
    clock = Clock(ct(2026, 8, 26, 14, 10))
    rc = mod.run(pull=pull, start=START, until=UNTIL, interval=30.0,
                 now_fn=clock.now_fn, sleep_fn=clock.sleep, out_path=lambda: out)
    assert rc == 2
    assert len(calls) == 1 and out.read_text().count("\n") == 1
    assert "auth" in (notes[-1].get("note") or "")


def test_five_consecutive_failures_back_off(tmp_path, monkeypatch):
    out = tmp_path / "late.jsonl"
    monkeypatch.setattr(mod, "update_manifest", lambda **kw: None)
    pull, calls = _fake_pull_factory({i: ["get_chain: ConnectionError: boom"] for i in range(5)})
    clock = Clock(ct(2026, 8, 26, 14, 55))
    rc = mod.run(pull=pull, start=START, until=UNTIL, interval=30.0,
                 now_fn=clock.now_fn, sleep_fn=clock.sleep, out_path=lambda: out)
    assert rc == 0
    assert mod.FAILURE_BACKOFF_S in clock.sleeps      # backed off once after the 5th failure
    assert len(calls) == 5                            # the backoff carried it past 15:01


def test_once_runs_a_single_cycle_regardless_of_window(tmp_path, monkeypatch):
    out = tmp_path / "late.jsonl"
    monkeypatch.setattr(mod, "update_manifest", lambda **kw: None)
    pull, calls = _fake_pull_factory()
    rc = mod.run(pull=pull, start=START, until=UNTIL, once=True,
                 now_fn=lambda: ct(2026, 8, 30, 9, 0), sleep_fn=lambda s: None,
                 out_path=lambda: out)
    assert rc == 0 and len(calls) == 1
    assert json.loads(out.read_text())["stage"] == "late-chain"


def test_is_auth_error():
    assert mod.is_auth_error(["get_quotes: HTTPError: 403 Forbidden"])
    assert mod.is_auth_error(["create_client: token file expired"])
    assert not mod.is_auth_error(["get_chain: ConnectionError: boom"])
    assert not mod.is_auth_error([])
