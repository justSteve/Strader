"""The one playback engine behind the region replay surface. [co-j9t1g, co-b18wf]

Two families. The synthetic tests pin the region/filter arithmetic and the
vocabulary without a corpus. The ``corpus`` tests read the one archived day
that also has a live scorer log (2026-08-25) and pin the properties the
learning surface rests on: determinism, the engine path following the LIVE
anchor rule, both paths in one time-ordered stream, and the day cache never
changing an answer.
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from market.orderflow import region_replay as rr
from market.orderflow.replay import has_es_day
from market.orderflow.tape_events import KIND_PLAN_LEVEL, load_knobs

CT = ZoneInfo("America/Chicago")
DAY = date(2026, 8, 25)
corpus = pytest.mark.skipif(not has_es_day(DAY), reason=f"{DAY} not in data/corpus")


def _em(hhmm: str, kind: str, low=7680.0, high=7690.0, path=None, **fields) -> rr.Emission:
    h, m = hhmm.split(":")
    ts = datetime(2026, 8, 25, int(h), int(m), tzinfo=CT)
    path = path or rr.PATH_OF[kind]
    rec = {"day": "2026-08-25", "ts": ts.isoformat(), "path": path, "kind": kind,
           "subtype": fields.pop("subtype", "X"), "sig": fields.pop("sig", "note" if path == "tape" else None),
           "fields": fields, "line": f"{hhmm} {kind}"}
    return rr.Emission(ts, low, high, rec)


# ── vocabulary ─────────────────────────────────────────────────────────────

def test_every_known_kind_has_a_path_a_label_and_a_word():
    v = rr.vocabulary()
    ids = {k["id"] for k in v["kinds"]}
    assert ids == set(rr.KNOWN_KINDS)
    named = {k for ks in v["words"].values() for k in ks}
    assert ids <= named, f"kinds no word names: {ids - named}"
    assert all(k["path"] in rr.PATHS for k in v["kinds"])


def test_resolve_kinds_takes_words_and_ids_and_reports_the_rest():
    kinds, unknown = rr.resolve_kinds(["sweeps", "PLAN-LEVEL", "absorption", "bananas"])
    assert kinds == {rr.KIND_SWEEP, KIND_PLAN_LEVEL, rr.KIND_ABSORPTION, rr.KIND_ABSORPTION_READ}
    assert unknown == ["bananas"]


# ── region and filter arithmetic ───────────────────────────────────────────

def test_window_is_inclusive_and_binds_on_the_emission_time():
    r = rr.Region(DAY, DAY, between=(time(13, 30), time(14, 10)))
    assert r.covers(datetime(2026, 8, 25, 13, 30, tzinfo=CT), 1, 2)
    assert r.covers(datetime(2026, 8, 25, 14, 10, tzinfo=CT), 1, 2)
    assert not r.covers(datetime(2026, 8, 25, 14, 11, tzinfo=CT), 1, 2)


def test_price_band_is_touched_by_the_bars_range_not_its_close():
    r = rr.Region(DAY, DAY, price_band=(7690.0, 7695.0))
    ts = datetime(2026, 8, 25, 10, tzinfo=CT)
    assert r.covers(ts, 7680.0, 7690.0)        # touched the bottom of the band
    assert not r.covers(ts, 7680.0, 7689.75)   # a tick short of it
    assert r.covers(ts, None, None)            # an end-of-stream emission places by time only


def test_filter_paths_names_only_what_the_kinds_can_come_from():
    assert rr.Filter().paths() == rr.PATHS
    assert rr.Filter(kinds=frozenset({rr.KIND_SWEEP})).paths() == (rr.PATH_ENGINE,)
    assert rr.Filter(kinds=frozenset({KIND_PLAN_LEVEL})).paths() == (rr.PATH_TAPE,)
    assert set(rr.Filter(kinds=frozenset({KIND_PLAN_LEVEL, rr.KIND_SWEEP})).paths()) == set(rr.PATHS)
    # a sig is a question only the tape path can answer
    assert rr.Filter(sigs=frozenset({"alert"})).paths() == (rr.PATH_TAPE,)


def test_select_is_a_view_records_come_back_unchanged():
    ems = [_em("13:31", KIND_PLAN_LEVEL, level="7692"), _em("13:35", rr.KIND_SWEEP, start_price=7691.0),
           _em("14:20", rr.KIND_SWEEP, start_price=7700.0)]
    r = rr.Region(DAY, DAY, between=(time(13, 30), time(14, 10)))
    got = rr.select(ems, r, rr.Filter(kinds=frozenset({rr.KIND_SWEEP})))
    assert got == [ems[1].record]
    assert got[0] is ems[1].record


def test_sig_filter_excludes_engine_records_which_carry_none():
    ems = [_em("13:31", KIND_PLAN_LEVEL, sig="alert"), _em("13:35", rr.KIND_SWEEP)]
    got = rr.select(ems, rr.Region(DAY, DAY), rr.Filter(sigs=frozenset({"alert"})))
    assert [g["kind"] for g in got] == [KIND_PLAN_LEVEL]


def test_diff_key_separates_two_sweeps_in_one_bar_by_start_price():
    a = _em("13:35", rr.KIND_SWEEP, subtype="sell", start_price=7691.0).record
    b = _em("13:35", rr.KIND_SWEEP, subtype="sell", start_price=7688.0).record
    assert rr._key(a) != rr._key(b)
    assert rr.diff([a, b], [a, b])["identical"]


def test_diff_key_tolerates_list_valued_subject_fields():
    a = _em("15:00", rr.KIND_STACK, prices=[7690.5, 7690.75]).record
    hash(rr._key(a))     # a list in the key would raise here


# ── corpus: the properties the surface rests on ────────────────────────────

@pytest.fixture(scope="module")
def knobs():
    return load_knobs()


@corpus
def test_tape_path_reproduces_the_harness_count(knobs):
    """102 is the 2026-08-25 live scorer log, line for line (st-v3wj). The
    tape path here IS scripts/replay_emissions.py's, so the count must hold."""
    assert len(rr.tape_path(DAY, knobs)) == 102


@corpus
def test_engine_path_follows_the_live_anchor_rule_not_the_drill_pages(knobs):
    """The drill page batches the day with the FINISHED session's extremes as
    anchors from bar 0 — lookahead a live session cannot have. The engine path
    here drives the feeder's loop (live_drive + LiveAnchors), so it can differ
    from the page's per-bar `ev` only where an extreme had not printed yet.
    Pin the direction of the difference: never MORE recognitions than the
    hindsight run, because the live rule can only ever know less."""
    from scripts.orderflow_drill import bars_payload
    live = [e.record for e in rr.engine_path(DAY)]
    page = bars_payload(DAY, 2000)
    hindsight = [e for b in page["bars"] for e in b["ev"]] + page["final"]
    n_live = sum(1 for e in live if e["kind"] == rr.KIND_SETUP)
    n_hind = sum(1 for e in hindsight if e.get("type") == rr.KIND_SETUP)
    assert 0 < n_live <= n_hind
    # Sweeps do not depend on anchors at all: identical either way.
    assert (sum(1 for e in live if e["kind"] == rr.KIND_SWEEP)
            == sum(1 for e in hindsight if e.get("type") == rr.KIND_SWEEP))


@corpus
def test_both_paths_arrive_in_one_time_ordered_stream(knobs):
    ems = rr.emit_day(DAY, knobs)
    assert {e.record["path"] for e in ems} == set(rr.PATHS)
    assert [e.ts for e in ems] == sorted(e.ts for e in ems)


@corpus
def test_two_runs_over_one_region_are_identical_with_or_without_the_cache(knobs):
    region = rr.Region(DAY, DAY, between=rr.RTH_WINDOW)
    rr.clear_cache()
    cold = rr.replay_day(DAY, region, rr.Filter(), knobs)
    warm = rr.replay_day(DAY, region, rr.Filter(), knobs)
    assert cold == warm and cold
    assert rr.diff(cold, warm)["identical"]


@corpus
def test_a_window_is_a_strict_subset_of_the_full_day_on_both_paths(knobs):
    full = rr.replay_day(DAY, rr.Region(DAY, DAY), rr.Filter(), knobs)
    windowed = rr.replay_day(DAY, rr.Region(DAY, DAY, between=rr.RTH_WINDOW), rr.Filter(), knobs)
    assert 0 < len(windowed) < len(full)
    for rec in windowed:
        assert rec in full


@corpus
def test_sweeps_only_runs_the_engine_path_alone(knobs):
    rr.clear_cache()
    only = rr.replay_day(DAY, rr.Region(DAY, DAY), rr.Filter(kinds=frozenset({rr.KIND_SWEEP})), knobs)
    assert only and {r["kind"] for r in only} == {rr.KIND_SWEEP}
    assert not any(k[1] == rr.PATH_TAPE for k in rr._CACHE), "the tape path ran for a sweeps-only ask"
