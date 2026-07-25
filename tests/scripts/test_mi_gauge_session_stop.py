"""mi_gauge live lifetime: session-end exit + day-rollover guard (st-5n8).

The 7/24 capture proved the gauge had no stop condition at all — one launch ran
26 hours, wrote 1269 rows onto a closed tape, and spilled Saturday's minutes
into Friday's file. These tests pin both halves of the fix: WHEN the loop stops,
and that a minute from another day can never reach the capture file even if it
somehow doesn't.
"""
import sys
import types
from datetime import date as _date, datetime, time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
import mi_gauge  # noqa: E402
from mi_gauge import (  # noqa: E402
    SESSION_END_DEFAULT,
    append_capture,
    parse_session_end,
    stop_reason,
)

from market.internals.gauge import TickMinute  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
DAY = _date(2026, 7, 24)


def at(hh, mm, day=DAY):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=CENTRAL)


# --- stop_reason -----------------------------------------------------------

def test_runs_during_the_session():
    assert stop_reason(at(13, 45), DAY, _time(15, 15)) is None


def test_stops_at_session_end_boundary():
    assert stop_reason(at(15, 14), DAY, _time(15, 15)) is None
    assert stop_reason(at(15, 15), DAY, _time(15, 15)) == "session-end"
    assert stop_reason(at(16, 30), DAY, _time(15, 15)) == "session-end"


def test_day_rollover_stops_even_inside_the_hours():
    """Saturday 06:46 — the exact state the 7/24 process was found in."""
    sat = _date(2026, 7, 25)
    assert stop_reason(at(6, 46, day=sat), DAY, _time(15, 15)) == "rollover"
    # Rollover outranks session-end: it is the harder stop.
    assert stop_reason(at(23, 59, day=sat), DAY, _time(15, 15)) == "rollover"


def test_session_end_none_runs_until_killed_but_still_rolls_over():
    assert stop_reason(at(23, 59), DAY, None) is None
    assert stop_reason(at(0, 1, day=_date(2026, 7, 25)), DAY, None) == "rollover"


# --- parse_session_end -----------------------------------------------------

def test_parse_session_end_forms():
    assert parse_session_end("15:15") == _time(15, 15)
    assert parse_session_end(SESSION_END_DEFAULT) == _time(15, 15)
    assert parse_session_end("9:05") == _time(9, 5)
    for off in ("none", "NONE", "off", "", "  "):
        assert parse_session_end(off) is None
    assert parse_session_end(None) is None
    with pytest.raises(ValueError):
        parse_session_end("half past three")


# --- append_capture day guard ---------------------------------------------

def test_capture_refuses_a_foreign_day(tmp_path):
    cap = tmp_path / "mi_gauge_live.jsonl"
    mine = TickMinute(ts=at(14, 30), high=400, low=-200, close=180)
    theirs = TickMinute(ts=at(6, 46, day=_date(2026, 7, 25)),
                        high=-490, low=-490, close=-490)

    assert append_capture(cap, mine, day=DAY) is True
    assert append_capture(cap, theirs, day=DAY) is False

    lines = cap.read_text().splitlines()
    assert len(lines) == 1
    assert "2026-07-24T14:30" in lines[0]


def test_capture_day_guard_is_opt_in(tmp_path):
    """Back-compat: no day → no filtering (existing callers/tests)."""
    cap = tmp_path / "c.jsonl"
    assert append_capture(cap, TickMinute(ts=at(14, 30), high=1, low=1, close=1)) is True
    assert len(cap.read_text().splitlines()) == 1


# --- live() refuses to start outside the window ----------------------------

@pytest.fixture
def no_broker(monkeypatch):
    """Hard-fail any attempt to build the Schwab client. The stop check must
    happen BEFORE the broker exists — that is what makes an out-of-window
    launch free, and what keeps this test off the gated live API."""
    mod = types.ModuleType("broker_schwab.client")

    def _boom(*a, **k):
        raise AssertionError("live() reached create_client() outside the session window")

    mod.create_client = _boom
    monkeypatch.setitem(sys.modules, "broker_schwab.client", mod)
    return mod


def test_live_exits_immediately_when_past_session_end(no_broker, capsys, tmp_path):
    today = datetime.now(tz=CENTRAL).date()
    # 00:00 is always <= now, so this is deterministic at any wall-clock time.
    rc = mi_gauge.live(5, tmp_path / "c.jsonl",
                       session_end=_time(0, 0), capture_day=today)
    assert rc == 0
    assert "past session end" in capsys.readouterr().out
    assert not (tmp_path / "c.jsonl").exists()


def test_live_exits_immediately_on_a_stale_capture_day(no_broker, capsys, tmp_path):
    rc = mi_gauge.live(5, tmp_path / "c.jsonl",
                       session_end=_time(15, 15), capture_day=_date(2000, 1, 1))
    assert rc == 0
    assert "not today" in capsys.readouterr().out
