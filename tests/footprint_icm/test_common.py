"""The delivered-wake rule and the scorer-log reader. [st-h0xx]

``derive_wakes`` is the finding the plan turned on: log time is tape time,
the watch starts at the end of the file, so the analyst saw only the alerts
whose minute is at or after the scorer's start and the arm, before the stop.
These pin that rule on synthetic lines so a change to it is a red test, not a
false alarm on a real day.
"""
from datetime import datetime
from pathlib import Path

import pytest

from common import (
    CT, derive_wakes, hhmm, minute_of_line, parse_knobs_line, parse_live_log,
    utc_iso_to_ct,
)

ALERT = "{m} CT  EVENT PLAN-LEVEL REJECTION  sig=alert  level=7747  anchor=resistance  from=below  close=7745.75"
NOTE = "{m} CT  EVENT PLAN-LEVEL TOUCH  sig=note  level=7747  close=7746"
BAR = "{m} CT  F2 (developing, n=768) absorption  ES o7745.75 h7747.5 l7745.75 c7745.75  vol 1808 d+148"


def ct(h, m, s=0, day="2026-08-27"):
    return datetime.fromisoformat(f"{day}T{h:02d}:{m:02d}:{s:02d}").replace(tzinfo=CT)


def lines(*specs):
    out = []
    for kind, m in specs:
        out.append({"a": ALERT, "n": NOTE, "b": BAR}[kind].format(m=m))
    return out


def test_wakes_start_at_the_later_of_scorer_start_and_arm():
    log = lines(("b", "09:53"), ("a", "09:53"), ("a", "09:54"), ("b", "12:30"), ("a", "12:30"),
                ("a", "12:31"), ("b", "12:46"), ("a", "12:47"))
    r = derive_wakes(log, start_ct=ct(9, 54, 47), arm_ct=ct(12, 31, 7), stop_ct=ct(18, 44))
    assert [w.minute for w in r["wakes"]] == ["12:31", "12:47"]
    # 12:30 is the minute before the arm minute: its print may or may not
    # have beaten the arm — listed, never counted.
    assert [l[:5] for l in r["ambiguous"]] == ["12:30"]
    assert [l[:5] for l in r["undelivered"]] == ["09:53", "09:54"]


def test_same_minute_alerts_are_one_wake_and_carry_the_last_bar():
    log = lines(("b", "10:34"), ("b", "10:35"), ("a", "10:35"), ("a", "10:35"), ("n", "10:36"),
                ("a", "10:56"))
    r = derive_wakes(log, start_ct=ct(10, 28), arm_ct=ct(10, 34, 46), stop_ct=None)
    assert len(r["wakes"]) == 2
    assert r["wakes"][0].minute == "10:35" and len(r["wakes"][0].lines) == 2
    assert r["wakes"][0].bar.startswith("10:35 CT  F2")
    assert r["wakes"][1].lines[0].startswith("10:56")


def test_notes_never_wake_anyone():
    log = lines(("n", "12:40"), ("n", "12:41"))
    r = derive_wakes(log, start_ct=None, arm_ct=ct(12, 0), stop_ct=None)
    assert r["wakes"] == [] and r["undelivered"] == [] and r["ambiguous"] == []


def test_stop_minute_is_ambiguous_and_later_alerts_undelivered():
    log = lines(("a", "14:27"), ("a", "14:28"), ("a", "14:29"))
    r = derive_wakes(log, start_ct=None, arm_ct=ct(10, 0), stop_ct=ct(14, 28, 45))
    assert [w.minute for w in r["wakes"]] == ["14:27"]
    assert [l[:5] for l in r["ambiguous"]] == ["14:28"]
    assert [l[:5] for l in r["undelivered"]] == ["14:29"]


def test_no_arm_means_everything_after_start_is_delivered():
    log = lines(("a", "09:00"), ("a", "09:30"))
    r = derive_wakes(log, start_ct=ct(9, 10), arm_ct=None, stop_ct=None)
    assert [w.minute for w in r["wakes"]] == ["09:30"]


def test_minute_of_line_reads_the_three_scorer_shapes_and_nothing_else():
    assert minute_of_line(ALERT.format(m="12:47")) == "12:47"
    assert minute_of_line(BAR.format(m="12:47")) == "12:47"
    assert minute_of_line("12:47:20 CT  partial (20s in, ungraded)  ES 7746  vol 300") == "12:47"
    assert minute_of_line("# knobs: a=1") is None
    assert minute_of_line("Traceback (most recent call last):") is None


def test_parse_knobs_line():
    assert parse_knobs_line("# knobs: absorption_effect_pct=10.0  climax_min_atoms=60  x=y") == {
        "absorption_effect_pct": "10.0", "climax_min_atoms": "60", "x": "y"}


def test_utc_stamp_to_central():
    t = utc_iso_to_ct("2026-08-27T14:54:47")
    assert hhmm(t) == "09:54" and t.tzinfo is not None


def test_parse_live_log_reads_two_joined_runs(tmp_path):
    p = tmp_path / "d.log"
    p.write_text("\n".join([
        "# effort/effect scorer (live F1-F4) — 2026-08-25  near<= 2.0pt @ 10.0s partial  0 levels loaded",
        BAR.format(m="00:00"), BAR.format(m="00:01"),
        "# effort/effect scorer (live F1-F4) — 2026-08-25  near<= 2.0pt @ 10.0s partial  68 levels loaded",
        "# ==== REGIME CHANGE 2026-08-25T15:28:35Z — EVENT-EMISSION ENABLED [st-dgwj] ====",
        "# knobs: climax_min_atoms=60  level_scan_nearest=1",
        "# classes: SUPERLATIVE ABSORPTION-CLUSTER CLIMAX PLAN-LEVEL  (68 anchors)",
        BAR.format(m="00:00"), ALERT.format(m="10:35"), BAR.format(m="10:35"),
        "Traceback (most recent call last):", "", ""]) + "\n")
    ll = parse_live_log(p)
    assert ll.segment_starts == [0, 3]
    assert ll.levels_loaded == 68
    assert ll.start_stamp_utc == "2026-08-25T15:28:35" and hhmm(ll.start_ct) == "10:28"
    assert ll.knobs == {"climax_min_atoms": "60", "level_scan_nearest": "1"}
    assert ll.event_lines == [ALERT.format(m="10:35")]
    assert ll.alert_lines == ll.event_lines
    assert ll.last_closed_minute == "10:35"
    # the body after the last header keeps the traceback line; the inputs
    # stage filters to scorer lines before comparing
    assert "Traceback (most recent call last):" in ll.body_after_last_header
