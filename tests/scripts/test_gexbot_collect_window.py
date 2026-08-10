"""Pin the GexBot collect window to the MEASURED feed boundary. [st-a6zm]

On 2026-08-09 this window was set to open at 07:30 CT "for the pre-open ramp",
on a belief about the feed that was never checked and was wrong. The measurement
that settles it, from 2026-08-07's own capture:

    00:00-08:29 CT   spot_at_gamma_zero frozen at ONE value for 8 hours
    08:30:02 CT      first new value — the cash open, to the second
    15:00:33 CT      last live update
    Sat 2026-08-08   1153 polls, ONE distinct value, all day

This test exists so the window is not widened back on a hunch. If you have a
reason to move it, bring a measurement, then change the number here too.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: First second the feed carries information, measured 2026-08-07.
FEED_FIRST_TICK_CT = "08:30"


def _load():
    path = REPO / "scripts" / "corpus_poll_gexbot.py"
    spec = importlib.util.spec_from_file_location("_gexbot_poller_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(spec.name, None)
    return mod


poller = _load()


def test_window_opens_when_the_feed_does_not_before():
    assert poller.DEFAULT_START_CT == FEED_FIRST_TICK_CT, (
        "the GexBot feed is frozen until 08:30:02 CT; an earlier start collects "
        "only duplicate rows"
    )


def test_window_holds_past_the_last_live_tick():
    """15:00:33 is the last update; the tail must not clip it."""
    assert poller.DEFAULT_UNTIL_CT > "15:00"


def test_the_tail_is_short_enough_to_stay_deliberate():
    """A long tail is how 'a few frozen rows' becomes another silent hour."""
    assert poller.DEFAULT_UNTIL_CT <= "15:15"


def test_the_supervisor_agrees_with_the_collector():
    """Two windows that disagree mean the supervisor relaunches a collector that
    immediately exits on its own gate, every two minutes."""
    wrapper = (REPO / "scripts" / "cron" / "gexbot-supervisor-session.sh").read_text()
    assert f"STRADER_CAPTURE_START_CT:-{poller.DEFAULT_START_CT}" in wrapper
    assert f"STRADER_CAPTURE_UNTIL_CT:-{poller.DEFAULT_UNTIL_CT}" in wrapper
