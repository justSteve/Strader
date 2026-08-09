"""Unit tests for the pure live-capture assessor. [st-6qx4]

Every branch runs with an injected Central `now`, a synthetic manifest and a
synthetic previous verdict, so nothing here needs a streamer, a clock or a
Databento connection. The contract under test: liveness is decided by PROCESS,
staleness by manifest cycles ADVANCING, and "not advancing" is only a fault when
GLBX is open.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from strader.capture_health import (
    CENTRAL,
    DEFAULT_STALE_SECS,
    STATUS_DEAD,
    STATUS_DUPLICATE,
    STATUS_IDLE,
    STATUS_OK,
    STATUS_QUIET,
    STATUS_STALE,
    STATUS_STARTING,
    STREAM_KEYS,
    assess_capture,
    globex_open,
    in_window,
    resolve_stream_names,
    utc_iso,
)

ES = "databento_glbx_es"
MBP1 = "databento_glbx_es_mbp1"

# Tuesday, deep in the overnight Globex session — the hour the whole bead is
# about ("dies at 02:00, noticed at 08:30").
NIGHT = datetime(2026, 8, 4, 2, 0, tzinfo=CENTRAL)


def manifest(es_cycles=1000, mbp1_cycles=50000):
    return {"date": "2026-08-04", "streams": {
        ES: {"cycles": es_cycles, "errors": [], "last_pull_utc": "2026-08-04T07:00:00Z"},
        MBP1: {"cycles": mbp1_cycles, "errors": [], "last_pull_utc": "2026-08-04T07:00:00Z"},
    }}


def assess(now=NIGHT, *, pids=(1234,), mf=None, prev=None, age=9999.0, **kw):
    return assess_capture(now, day=now.date(),
                          manifest=manifest() if mf is None else mf,
                          pids=list(pids), capture_age_secs=age, prev=prev, **kw)


# --- the GLBX calendar -----------------------------------------------------

@pytest.mark.parametrize("when,expect", [
    ((2026, 8, 4, 2, 0), True),      # Tue 02:00 — overnight, open
    ((2026, 8, 4, 10, 0), True),     # Tue 10:00 — RTH
    ((2026, 8, 4, 15, 20), False),   # Tue 15:20 — the daily 15:15-15:30 pause
    ((2026, 8, 4, 16, 30), False),   # Tue 16:30 — maintenance halt
    ((2026, 8, 4, 17, 30), True),    # Tue 17:30 — re-opened
    ((2026, 8, 7, 15, 0), True),     # Fri 15:00 — still open
    ((2026, 8, 7, 16, 30), False),   # Fri 16:30 — weekly close
    ((2026, 8, 8, 12, 0), False),    # Sat — closed all day
    ((2026, 8, 9, 12, 0), False),    # Sun noon — not yet
    ((2026, 8, 9, 17, 30), True),    # Sun 17:30 — weekly re-open
])
def test_globex_calendar(when, expect):
    assert globex_open(datetime(*when, tzinfo=CENTRAL)) is expect


def test_round_the_clock_window_includes_the_last_minute():
    """23:59 must be inside the default window: the day-rollover relaunch
    happens exactly there, and an exclusive bound would skip it."""
    assert in_window(datetime(2026, 8, 4, 23, 59, tzinfo=CENTRAL), "00:00", "23:59")
    assert in_window(datetime(2026, 8, 4, 0, 0, tzinfo=CENTRAL), "00:00", "23:59")


def test_narrow_window_excludes_outside():
    now = datetime(2026, 8, 4, 2, 0, tzinfo=CENTRAL)
    assert not in_window(now, "08:30", "15:05")


# --- liveness --------------------------------------------------------------

def test_no_process_in_window_is_dead():
    h = assess(pids=())
    assert h.status == STATUS_DEAD
    assert h.actionable and not h.ok
    assert "not backfillable" in h.message


def test_no_process_outside_the_window_is_idle():
    h = assess(pids=(), window_start="08:30", window_end="15:05")
    assert h.status == STATUS_IDLE
    assert h.ok and not h.actionable


def test_no_process_with_globex_closed_is_idle():
    sat = datetime(2026, 8, 8, 3, 0, tzinfo=CENTRAL)
    h = assess(sat, pids=())
    assert h.status == STATUS_IDLE
    assert "GLBX closed" in h.message


def test_two_processes_is_duplicate():
    h = assess(pids=(1234, 5678))
    assert h.status == STATUS_DUPLICATE
    assert h.actionable
    assert "double-written" in h.message


# --- staleness: the hard failure -------------------------------------------

def _prev(h):
    return h.to_dict()


def test_advancing_cycles_is_ok():
    first = assess(mf=manifest(1000, 50000))
    later = assess(NIGHT + timedelta(minutes=30), mf=manifest(1200, 60000),
                   prev=_prev(first))
    assert later.status == STATUS_OK
    assert later.stale_streams == []


def test_frozen_cycles_with_a_live_pid_is_stale():
    """The failure a pid check calls healthy: process alive, nothing arriving."""
    first = assess(mf=manifest(1000, 50000))
    later = assess(NIGHT + timedelta(seconds=DEFAULT_STALE_SECS + 60),
                   mf=manifest(1000, 50000), prev=_prev(first))
    assert later.status == STATUS_STALE
    assert later.pids == [1234]                      # alive the whole time
    assert set(later.stale_streams) == {ES, MBP1}
    assert later.all_stale
    assert "ALIVE but not receiving" in later.message


def test_one_frozen_stream_is_stale_but_not_all_stale():
    """A single dead worker is real and alertable; only a total freeze is
    unambiguous enough for the opt-in restart."""
    first = assess(mf=manifest(1000, 50000))
    later = assess(NIGHT + timedelta(seconds=DEFAULT_STALE_SECS + 60),
                   mf=manifest(1000, 99000), prev=_prev(first))
    assert later.status == STATUS_STALE
    assert later.stale_streams == [ES]
    assert not later.all_stale


def test_frozen_cycles_while_globex_is_closed_is_quiet_not_stale():
    """15:15-15:30 CT: a silent tape is correct. Alerting here is how a guard
    trains its reader to ignore it."""
    base = datetime(2026, 8, 4, 15, 5, tzinfo=CENTRAL)
    first = assess(base, mf=manifest(1000, 50000))
    later = assess(datetime(2026, 8, 4, 15, 25, tzinfo=CENTRAL),
                   mf=manifest(1000, 50000), prev=_prev(first))
    assert later.status == STATUS_QUIET
    assert later.ok


def test_missing_stream_counts_as_stale_after_the_quiet_window():
    first = assess(mf={"streams": {}})
    later = assess(NIGHT + timedelta(seconds=DEFAULT_STALE_SECS + 60),
                   mf={"streams": {}}, prev=_prev(first))
    assert later.status == STATUS_STALE
    assert set(later.stale_streams) == {ES, MBP1}


def test_fresh_launch_is_starting_not_stale():
    first = assess(mf={"streams": {}}, age=5.0)
    later = assess(NIGHT + timedelta(seconds=DEFAULT_STALE_SECS + 60),
                   mf={"streams": {}}, prev=_prev(first), age=30.0)
    assert later.status == STATUS_STARTING
    assert later.ok


def test_a_first_observation_never_inherits_staleness():
    """No prev means no knowledge of movement. Reporting stale on the very first
    tick would fire an alert the supervisor has not earned."""
    h = assess(mf=manifest(1000, 50000), prev=None)
    assert h.status == STATUS_OK


def test_a_new_corpus_day_resets_the_quiet_clocks():
    """Cycles restart near zero each day; carrying yesterday's baseline over
    would read the reset as a freeze."""
    yesterday = assess(NIGHT - timedelta(days=1), mf=manifest(400000, 900000))
    today = assess(NIGHT, mf=manifest(12, 340), prev=_prev(yesterday))
    assert today.status == STATUS_OK
    assert today.streams[ES]["quiet_secs"] == 0.0


def test_a_counter_reset_counts_as_movement():
    """A relaunch against a fresh manifest drops cycles. Movement is movement."""
    first = assess(mf=manifest(1000, 50000))
    later = assess(NIGHT + timedelta(seconds=DEFAULT_STALE_SECS + 60),
                   mf=manifest(3, 40), prev=_prev(first))
    assert later.status == STATUS_OK


# --- bookkeeping -----------------------------------------------------------

def test_since_utc_marks_when_the_status_began():
    first = assess(pids=())                    # dead
    assert first.status == STATUS_DEAD
    later = assess(NIGHT + timedelta(minutes=20), pids=(), prev=_prev(first))
    assert later.since_utc == first.since_utc  # still the same outage
    # Relaunched and receiving again: the outage clock restarts from recovery.
    recovered = assess(NIGHT + timedelta(minutes=25), mf=manifest(1400, 70000),
                       prev=_prev(later))
    assert recovered.status == STATUS_OK
    assert recovered.since_utc == utc_iso(NIGHT + timedelta(minutes=25))


def test_restart_counter_resets_on_a_new_day():
    prev = {"day": "2026-08-03", "restarts": 4, "restarts_day": "2026-08-03"}
    h = assess(prev=prev)
    assert h.restarts == 0 and h.restarts_day == "2026-08-04"


def test_restart_counter_carries_within_the_day():
    prev = {"day": "2026-08-04", "restarts": 4, "restarts_day": "2026-08-04",
            "status": STATUS_OK}
    h = assess(prev=prev)
    assert h.restarts == 4


# --- wiring ----------------------------------------------------------------

def test_stream_keys_match_the_streamer():
    """STREAM_KEYS is a copy of the streamer's spec table; assert it cannot
    drift, because a renamed stream would silently watch nothing."""
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "corpus_stream_databento.py"
    spec = importlib.util.spec_from_file_location("_streamer_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: the module defines dataclasses, and @dataclass
    # resolves annotations through sys.modules[cls.__module__].
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(spec.name, None)
    assert {k: s.name for k, s in mod.default_specs().items()} == STREAM_KEYS


def test_resolve_stream_names_accepts_both_spellings():
    assert resolve_stream_names(["es", MBP1, ""]) == [ES, MBP1]


# --- venues [st-p3lv] --------------------------------------------------------
# The GexBot collector reuses this assessor with a different calendar. What must
# hold: the ES tenant's behaviour is untouched, and the cash tenant stands down
# on days the cash market is shut.

GX = "gexbot"
#: Monday inside the GexBot collect window.
GX_OPEN = datetime(2026, 8, 10, 9, 0, tzinfo=CENTRAL)


def gx_manifest(cycles=90):
    return {"date": "2026-08-10", "streams": {
        GX: {"cycles": cycles, "errors": [], "last_pull_utc": "2026-08-10T14:00:00Z"},
    }}


def gx_assess(now, *, pids, manifest=None, prev=None, **kw):
    return assess_capture(
        now, day=now.date(), manifest=manifest, pids=pids, prev=prev,
        streams=(GX,), venue="cash", window_start="07:30", window_end="15:05", **kw)


def test_cash_venue_calls_a_missing_collector_dead_in_session():
    h = gx_assess(GX_OPEN, pids=[])
    assert h.status == STATUS_DEAD
    assert h.expected


def test_cash_venue_is_idle_on_a_saturday():
    """2026-08-08 — the day the ungated poller wrote 58.4 MB."""
    h = gx_assess(datetime(2026, 8, 8, 11, 0, tzinfo=CENTRAL), pids=[])
    assert h.status == STATUS_IDLE
    assert not h.expected


def test_cash_venue_is_idle_on_thanksgiving():
    """A holiday must not be relaunched into every two minutes for seven hours."""
    h = gx_assess(datetime(2026, 11, 26, 10, 0, tzinfo=CENTRAL), pids=[])
    assert h.status == STATUS_IDLE


def test_globex_venue_still_expects_es_on_thanksgiving():
    """The contrast that justifies two venues: CME trades a shortened session on
    most NYSE closures, so an NYSE holiday is NOT evidence ES is quiet."""
    h = assess_capture(
        datetime(2026, 11, 26, 10, 0, tzinfo=CENTRAL),
        day=datetime(2026, 11, 26).date(), manifest=None, pids=[],
        streams=("es",), window_start="00:00", window_end="23:59")
    assert h.status == STATUS_DEAD


def test_cash_venue_is_idle_after_the_window_closes():
    h = gx_assess(datetime(2026, 8, 10, 16, 0, tzinfo=CENTRAL), pids=[])
    assert h.status == STATUS_IDLE


def test_cash_venue_expects_a_collector_during_the_preopen_ramp():
    """07:30-08:30 is the ramp. A cash-open-aware venue predicate would report
    idle here and the supervisor would never start the collector."""
    h = gx_assess(datetime(2026, 8, 10, 7, 45, tzinfo=CENTRAL), pids=[])
    assert h.status == STATUS_DEAD


def test_cash_venue_flags_a_frozen_collector_as_stale():
    prev = gx_assess(GX_OPEN, pids=[4242], manifest=gx_manifest(90)).to_dict()
    later = GX_OPEN + timedelta(seconds=DEFAULT_STALE_SECS + 60)
    h = gx_assess(later, pids=[4242], manifest=gx_manifest(90), prev=prev)
    assert h.status == STATUS_STALE
    assert h.stale_streams == [GX]
    assert "the cash market" in h.message


def test_cash_venue_is_ok_while_cycles_advance():
    prev = gx_assess(GX_OPEN, pids=[4242], manifest=gx_manifest(90)).to_dict()
    later = GX_OPEN + timedelta(seconds=DEFAULT_STALE_SECS + 60)
    h = gx_assess(later, pids=[4242], manifest=gx_manifest(101), prev=prev)
    assert h.status == STATUS_OK


def test_an_unknown_venue_is_an_error_not_a_silent_default():
    with pytest.raises(ValueError, match="unknown venue"):
        assess_capture(GX_OPEN, day=GX_OPEN.date(), manifest=None, pids=[],
                       venue="nasdaq")
