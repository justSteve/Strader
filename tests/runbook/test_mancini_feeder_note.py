"""The parse says whether the LIVE feeder holds the levels it just published.

st-kxnv: the footprint feeder reads mancini_levels_for(day) once at start and
nothing re-reads it. Its unit restarts at midnight; the parse lands hours
later. Measured anchor counts at process start were 0 on 08-21, 08-22, 08-23,
08-25 and 08-26, and non-zero on 08-24 only because someone restarted it by
hand — and the page looks completely normal the whole time. On 2026-08-26 the
live page served 0 levels for 65 minutes of the open session while the parsed
plan sat on the desk and the clipboard.

The parse is the last thing that knows the levels changed, so it is where the
check belongs.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from runbook.mancini import run as run_mod


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_page(monkeypatch, payload=None, boom=None):
    import urllib.request

    def urlopen(*a, **k):
        if boom is not None:
            raise boom
        return _Resp(payload)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_zero_anchors_is_an_alert_naming_the_fix(monkeypatch):
    """THE 08-26 CASE. The plan is published and the live page does not have
    it — the one state that looks identical to success from the desk."""
    _patch_page(monkeypatch, {"meta": {"mancini": []}})
    note = run_mod._feeder_anchor_note(date.today())
    assert "[ALERT]" in note
    assert "0 mancini levels" in note
    assert "systemctl restart strader-footprint-feed.service" in note, \
        "an alert without the command is a puzzle, not a fix"


def test_loaded_anchors_are_confirmed_not_silent(monkeypatch):
    """Silence would leave the reader unable to tell 'checked and fine' from
    'never checked' — the same conflation as an absent-vs-drained inbox."""
    _patch_page(monkeypatch, {"meta": {"mancini": [7516.0, 7526.0, 7538.0]}})
    note = run_mod._feeder_anchor_note(date.today())
    assert "holding 3 mancini level(s)" in note
    assert "[ALERT]" not in note


def test_a_backfill_says_nothing_about_the_live_feed(monkeypatch):
    """Re-parsing an old day tells you nothing about today's feeder, and an
    alert fired from a backfill would train the reader to ignore it."""
    _patch_page(monkeypatch, {"meta": {"mancini": []}})
    assert run_mod._feeder_anchor_note(date.today() - timedelta(days=3)) == ""


def test_an_unreachable_page_says_unknown_not_fine(monkeypatch):
    """A bridge that cannot be reached is not a bridge holding zero levels and
    is not a bridge holding them. Three states, three answers."""
    _patch_page(monkeypatch, boom=OSError("refused"))
    note = run_mod._feeder_anchor_note(date.today())
    assert "unknown" in note and "[ALERT]" not in note


def test_the_check_never_breaks_the_parse(monkeypatch):
    """A briefing line is not worth failing a publish over — the parse has
    already written the desk, the chart and the clipboard by this point."""
    _patch_page(monkeypatch, boom=RuntimeError("something exotic"))
    assert isinstance(run_mod._feeder_anchor_note(date.today()), str)
