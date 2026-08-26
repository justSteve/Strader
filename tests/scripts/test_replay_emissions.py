"""The re-emission harness: determinism first, everything else second. [co-b18wf]

Ruling 9 makes a replay diff the review artifact for any emission or detection
change. That is worth exactly nothing unless two runs over one region are
identical when nothing changed — a flaky runner turns every review into a
false positive and the rule gets abandoned within a week. So determinism is
the first test here and the one to fix first if it ever goes red.

The corpus tests are marked ``corpus``: they read real archived days from
``data/corpus`` and are skipped where that is absent, which keeps a clone
without the archive green rather than red-for-the-wrong-reason.
"""
import collections
import re
from datetime import date, time
from pathlib import Path

import pytest

from market.orderflow.replay import has_es_day
from scripts.replay_emissions import (
    Filter, RTH_WINDOW, Region, _key, diff, render_diff, replay, replay_day,
)
from market.orderflow.tape_events import KIND_PLAN_LEVEL, load_knobs

# The one day with both a live emitter log and a full archive.
DAY = date(2026, 8, 25)

corpus = pytest.mark.skipif(not has_es_day(DAY),
                            reason=f"{DAY} not in data/corpus")

# The live scorer's own log for that day, written by scripts/live_effort_effect.py.
# It lives outside the repo (it is operational output, not source), so the one
# test that compares against it skips where the box does not have it.
LIVE_LOG = Path(f"/var/moo/logs/effort-effect/{DAY}.log")
EVENT_LINE = re.compile(r"^\d{2}:\d{2} CT\s+EVENT ")
live_log = pytest.mark.skipif(not LIVE_LOG.exists(),
                              reason=f"{LIVE_LOG} not on this box")


@pytest.fixture(scope="module")
def knobs():
    return load_knobs()


# ── determinism ────────────────────────────────────────────────────────────

@corpus
def test_two_runs_of_one_region_are_identical(knobs):
    """THE load-bearing property. Every diff this tool produces is evidence
    only because this holds."""
    region = Region(start=DAY, end=DAY)
    a = replay_day(DAY, region, Filter(), knobs)
    b = replay_day(DAY, region, Filter(), knobs)
    assert a == b
    assert diff(a, b)["identical"]


@corpus
@live_log
def test_replay_reproduces_the_live_emitter_log(knobs):
    """THE OTHER load-bearing property, and the one st-v3wj was opened to
    doubt: a replay says what the live emitter actually said.

    Determinism above makes a BEFORE/AFTER diff trustworthy. This makes a
    historical audit trustworthy — it is what co-j9t1g's learning surface
    rests on, because a view that quietly differs from what happened teaches
    the difference.

    2026-08-25 is the only day with both a full live log and an archive. The
    scorer restarted at 10:28 CT and re-read the day's corpus from 00:00, so
    the log covers the whole Globex session and is comparable end to end.

    If this goes red, the emission path moved and the log did not — read the
    diff before touching the test. st-v3wj's own failure was the reverse: the
    baseline was a partial-day count read at lunchtime, so make sure any new
    baseline carries the clock time it was taken at.
    """
    live = [ln.rstrip() for ln in LIVE_LOG.read_text(errors="replace").splitlines()
            if EVENT_LINE.match(ln)]
    replayed = [r["line"].rstrip()
                for r in replay_day(DAY, Region(start=DAY, end=DAY), Filter(), knobs)]
    assert replayed == live


@corpus
def test_diff_reports_identical_runs_as_such(knobs):
    region = Region(start=DAY, end=DAY)
    recs = replay_day(DAY, region, Filter(), knobs)
    rendered = render_diff(diff(recs, recs))
    assert "BYTE-IDENTICAL" in rendered


# ── the region narrows reporting, never detection ──────────────────────────

@corpus
def test_a_window_narrows_what_is_reported_not_what_fires(knobs):
    """Extrema, cooldowns and cluster runs are path-dependent, so a detector
    fed only a window would fire differently inside it. The window is applied
    after detection, and this pins that: every windowed event is present,
    unchanged, in the full-day run."""
    full = replay_day(DAY, Region(start=DAY, end=DAY), Filter(), knobs)
    windowed = replay_day(
        DAY, Region(start=DAY, end=DAY, between=RTH_WINDOW), Filter(), knobs)

    assert len(windowed) < len(full), "RTH should be a strict subset of the day"
    for rec in windowed:
        assert rec in full, f"{rec['line']} fired in the window but not in the full day"


@corpus
def test_one_minute_can_carry_two_events_of_one_kind_and_the_key_separates_them(knobs):
    """2026-08-25 09:30 fires PLAN-LEVEL TOUCH against both 7665 (support) and
    7667 (resistance) — one bar, two levels. A diff key of (ts, kind, subtype)
    collapses them, which would silently drop half of every such minute. This
    is the measured case that put `level` in SUBJECT_FIELDS."""
    recs = replay_day(DAY, Region(start=DAY, end=DAY), Filter(), knobs)
    keys = [_key(r) for r in recs]
    assert len(keys) == len(set(keys)), "the diff key is not unique per event"

    # Find the collision rather than hardcode its timestamp — the point is
    # that the naive key collides at all, not that it collides at 09:30.
    naive = collections.Counter(
        (r["ts"], r["kind"], r["subtype"]) for r in recs)
    collided = [k for k, n in naive.items() if n > 1]
    assert collided, (
        "no minute carries two events of one kind any more — either the "
        "anchor set moved or the detector changed. Check which before "
        "deleting this test: it is the reason `level` is a subject field.")

    for ts, kind, subtype in collided:
        same = [r for r in recs
                if (r["ts"], r["kind"], r["subtype"]) == (ts, kind, subtype)]
        levels = {r["fields"].get("level") for r in same}
        assert len(levels) == len(same), (
            f"{kind} {subtype} at {ts} repeats without a distinct level — "
            "SUBJECT_FIELDS does not separate these and the diff will hide one")


@corpus
def test_window_bounds_are_inclusive_and_actually_bind(knobs):
    windowed = replay_day(
        DAY, Region(start=DAY, end=DAY, between=RTH_WINDOW), Filter(), knobs)
    assert windowed, "the cash session produced no events at all — suspicious"
    for rec in windowed:
        t = time.fromisoformat(rec["ts"][11:19])
        assert RTH_WINDOW[0] <= t <= RTH_WINDOW[1]


# ── the filter ─────────────────────────────────────────────────────────────

@corpus
def test_kind_filter_keeps_only_that_kind(knobs):
    region = Region(start=DAY, end=DAY)
    only = replay_day(DAY, region, Filter(kinds=frozenset({KIND_PLAN_LEVEL})), knobs)
    assert only
    assert {r["kind"] for r in only} == {KIND_PLAN_LEVEL}


@corpus
def test_filtering_does_not_change_the_events_themselves(knobs):
    """A filter is a view. If scoping altered an event, the learning surface
    (co-j9t1g) would teach something the instrument never said."""
    region = Region(start=DAY, end=DAY)
    full = replay_day(DAY, region, Filter(), knobs)
    only = replay_day(DAY, region, Filter(kinds=frozenset({KIND_PLAN_LEVEL})), knobs)
    assert only == [r for r in full if r["kind"] == KIND_PLAN_LEVEL]


@corpus
def test_sig_filter_binds(knobs):
    region = Region(start=DAY, end=DAY)
    alerts = replay_day(DAY, region, Filter(sigs=frozenset({"alert"})), knobs)
    assert alerts
    assert {r["sig"] for r in alerts} == {"alert"}


# ── diff semantics ─────────────────────────────────────────────────────────

def _rec(ts, kind="CLIMAX", subtype="BUY", line="x"):
    return {"day": "2026-08-25", "ts": ts, "kind": kind, "subtype": subtype,
            "sig": "alert", "fields": {}, "line": line}


def test_a_changed_value_reads_as_modified_not_as_add_plus_remove():
    """The diff keys on when-and-what, deliberately excluding the rendered
    line, so a moved number is one modification rather than two entries a
    reader has to pair up themselves."""
    before = [_rec("2026-08-25T09:30:00", line="d=-1240")]
    after = [_rec("2026-08-25T09:30:00", line="d=-1250")]
    d = diff(before, after)
    assert not d["identical"]
    assert len(d["changed"]) == 1 and not d["added"] and not d["removed"]


def test_added_and_removed_are_reported_separately():
    d = diff([_rec("2026-08-25T09:30:00")], [_rec("2026-08-25T10:00:00")])
    assert len(d["added"]) == 1 and len(d["removed"]) == 1 and not d["changed"]


def test_empty_against_empty_is_identical():
    assert diff([], [])["identical"]


def test_render_names_counts_when_not_identical():
    out = render_diff(diff([_rec("2026-08-25T09:30:00")], []))
    assert "NOT identical" in out and "-1" in out


# ── the region's own arithmetic ────────────────────────────────────────────

def test_days_is_inclusive_of_both_ends():
    r = Region(start=date(2026, 8, 24), end=date(2026, 8, 26))
    assert list(r.days()) == [date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26)]


def test_a_single_day_region_yields_one_day():
    assert list(Region(start=DAY, end=DAY).days()) == [DAY]


def test_missing_archive_days_are_skipped_not_fabricated(knobs, caplog):
    """A region whose archive has holes must not quietly report a smaller
    count — Ruling 9 turns on counts, so a hole has to be visible."""
    far = date(1999, 1, 4)
    recs = replay(Region(start=far, end=far), Filter(), knobs)
    assert recs == []
    assert any("NOT replayed" in m for m in caplog.messages)
