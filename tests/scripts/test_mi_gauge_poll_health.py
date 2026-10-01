"""mi_gauge live: a failed $TICK poll is loud, and two missed minutes mark the
read STALE on the pane and in _mi_gauge_health.json. [st-epa3]

Before: `prices = ... if r.status_code == 200 else {}` — a 401/5xx printed
nothing and the pane kept its last band as if the tape were still being read.
"""
import json
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import mi_gauge  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 10, 1, 10, 0, tzinfo=CENTRAL)


def test_bad_poll_alerts_with_ct_stamp_and_code():
    h = mi_gauge.PollHealth(T0)
    lines = h.observe(T0 + timedelta(seconds=5), "HTTP 401")
    assert lines == ["[ALERT] 10:00:05 CT $TICK poll HTTP 401 (1 in a row)"]
    assert h.snapshot(T0 + timedelta(seconds=5))["status"] == "degraded"


def test_alert_repeats_once_a_minute_not_every_poll():
    h = mi_gauge.PollHealth(T0)
    out = []
    for s in range(5, 70, 5):
        out += h.observe(T0 + timedelta(seconds=s), "HTTP 503")
    assert sum(l.startswith("[ALERT]") for l in out) == 2   # 10:00:05 and 10:01:05


def test_two_missed_minutes_mark_stale_then_recovery_clears():
    h = mi_gauge.PollHealth(T0)
    h.observe(T0, None)
    out = []
    for s in range(5, 125, 5):
        out += h.observe(T0 + timedelta(seconds=s), "HTTP 401")
    assert any("STALE" in l and "10:00:00 CT" in l for l in out)
    assert h.snapshot(T0 + timedelta(seconds=120))["status"] == "stale"
    rec = h.observe(T0 + timedelta(seconds=125), None)
    assert rec and "recovered" in rec[0] and "STALE" in rec[0]
    assert h.snapshot(T0 + timedelta(seconds=125))["status"] == "ok"


def test_never_good_since_launch_also_goes_stale():
    h = mi_gauge.PollHealth(T0)
    assert not h.stale(T0 + timedelta(seconds=119))
    assert h.stale(T0 + timedelta(seconds=120))


class _Stop(Exception):
    pass


def test_live_loop_on_401_alerts_and_writes_stale_health(monkeypatch, capsys, tmp_path):
    """Drive the real loop: the broker answers 401 forever."""
    class _Resp:
        status_code = 401
        def json(self):  # pragma: no cover — must not be read on a 401
            raise AssertionError("parsed a 401 body")

    class _Client:
        def get_quotes(self, syms):
            return _Resp()

    mod = types.ModuleType("broker_schwab.client")
    mod.create_client = lambda: _Client()
    monkeypatch.setitem(sys.modules, "broker_schwab.client", mod)

    today = datetime.now(tz=CENTRAL).date()
    clock = [datetime.combine(today, T0.time(), tzinfo=CENTRAL)]
    monkeypatch.setattr(mi_gauge, "_now", lambda: clock[0])
    polls = [0]

    def _sleep(s):
        polls[0] += 1
        if polls[0] >= 30:          # 150 s of 5 s polls
            raise _Stop
        clock[0] += timedelta(seconds=s)

    monkeypatch.setattr(mi_gauge.time_mod, "sleep", _sleep)
    capture = tmp_path / "mi_gauge_live.jsonl"
    with pytest.raises(_Stop):
        mi_gauge.live(5, capture, session_end=None, capture_day=today)

    out = capsys.readouterr().out
    assert "[ALERT] 10:00:00 CT $TICK poll HTTP 401" in out
    assert "MI gauge read STALE" in out
    snap = json.loads((tmp_path / mi_gauge.HEALTH_NAME).read_text())
    assert snap["status"] == "stale"
    assert snap["last_error"] == "HTTP 401"
    assert snap["last_good"] is None
