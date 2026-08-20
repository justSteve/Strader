"""Running session extrema on the live tape scorer. [st-z19p]

The failure this pins: a watch resumed mid-session has no view of the morning,
so a superlative read off the emission ("largest delta of the day") scopes to
the watcher's uptime rather than to the session. On 2026-08-20 that produced
three wrong day-scope calls in the 14:50s — the day's real deltas were -1501 at
07:06, -1200 at 09:19 and +1040 at 11:34, against which 14:58's +1201 was
second and 14:55's -891 fourth.

The extrema track the atom list, which is backfilled from the session open, so
the scope is the session and not the process lifetime.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from live_effort_effect import LiveScorer  # noqa: E402


def _atom(hhmm: str, volume: int, delta: int):
    h, m = hhmm.split(":")
    return SimpleNamespace(ts=datetime(2026, 8, 20, int(h), int(m)),
                           volume=volume, delta=delta)


def _scorer() -> LiveScorer:
    return LiveScorer(near_band=2.0, partial_interval=10.0, levels=[], kinds={})


def test_first_atom_sets_both_records():
    s = _scorer()
    flags = s._update_extrema(_atom("07:06", 3839, -1501))
    assert "NEW-MAX-VOL" in flags and "NEW-MAX-DELTA" in flags
    assert s._max_vol[0] == 3839
    assert s._max_delta[0] == -1501


def test_delta_ranks_on_magnitude_but_reports_signed():
    """-1501 must outrank +1201: the record is |delta|, the display is signed."""
    s = _scorer()
    s._update_extrema(_atom("07:06", 3839, -1501))
    flags = s._update_extrema(_atom("14:58", 9541, +1201))
    assert "NEW-MAX-DELTA" not in flags, "+1201 is smaller in magnitude than -1501"
    assert "NEW-MAX-VOL" in flags, "9541 lots is a volume record even so"
    assert s._max_delta[0] == -1501
    assert "d-1501@07:06" in s._extrema_text()


def test_afternoon_bar_does_not_claim_a_day_record_it_lacks():
    """The 2026-08-20 regression, end to end."""
    s = _scorer()
    for a in (_atom("07:06", 3839, -1501), _atom("09:19", 3880, -1200),
              _atom("11:34", 3630, +1040)):
        s._update_extrema(a)
    flags = s._update_extrema(_atom("14:55", 12777, -891))
    assert "NEW-MAX-DELTA" not in flags
    assert "NEW-MAX-VOL" in flags
    text = s._extrema_text()
    assert "vol 12777@14:55" in text
    assert "d-1501@07:06" in text


def test_extrema_carry_the_setting_timestamp_not_the_current_one():
    s = _scorer()
    s._update_extrema(_atom("07:06", 3839, -1501))
    s._update_extrema(_atom("15:07", 693, +67))
    assert "vol 3839@07:06" in s._extrema_text()
    assert "d-1501@07:06" in s._extrema_text()


def test_no_flag_when_nothing_is_a_record():
    s = _scorer()
    s._update_extrema(_atom("07:06", 3839, -1501))
    assert s._update_extrema(_atom("15:07", 693, +67)) == ""
