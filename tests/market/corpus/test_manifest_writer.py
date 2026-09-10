"""The manifest writer: bounded lists, atomic writes, resolved errors. [co-8b60y]

Measured 2026-09-04: a 42-hour network outage appended 6,466 copies of one
reconnect sentence per stream to the 2026-09-03 manifest (4.4 MB), and the
file was rewritten in place on every attempt. These tests pin the three
changes that followed.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from market.corpus import paths, writer

DAY = date(2026, 9, 3)
STREAM = "databento_glbx_es"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CORPUS_ROOT", tmp_path)
    return tmp_path


def _stream() -> dict:
    return json.loads(paths.manifest_path(DAY).read_text())["streams"][STREAM]


def _manifest() -> dict:
    return json.loads(paths.manifest_path(DAY).read_text())


class TestKeyedNotes:
    """One line per outage, rewritten in place [co-8b60y a1]."""

    def test_a_keyed_note_is_rewritten_not_appended(self, corpus):
        writer.update_manifest(DAY, STREAM, note="outage since T, 1 attempt(s)",
                               note_key="outage:T")
        writer.update_manifest(DAY, STREAM, note="outage since T, 2 attempt(s)",
                               note_key="outage:T")
        writer.update_manifest(DAY, STREAM, note="outage T–U, 2 attempt(s), reconnected",
                               note_key="outage:T")
        notes = _manifest()["notes"]
        assert len(notes) == 1
        assert notes[0]["note"] == "outage T–U, 2 attempt(s), reconnected"
        assert notes[0]["key"] == "outage:T"
        assert notes[0]["stream"] == STREAM

    def test_the_key_is_scoped_to_the_stream(self, corpus):
        writer.update_manifest(DAY, STREAM, note="a", note_key="outage:T")
        writer.update_manifest(DAY, "databento_glbx_es_mbp1", note="b", note_key="outage:T")
        notes = _manifest()["notes"]
        assert [n["note"] for n in notes] == ["a", "b"]

    def test_different_keys_and_plain_notes_still_append(self, corpus):
        writer.update_manifest(DAY, STREAM, note="a", note_key="outage:T1")
        writer.update_manifest(DAY, STREAM, note="b", note_key="outage:T2")
        writer.update_manifest(DAY, STREAM, note="plain")
        writer.update_manifest(DAY, STREAM, note="plain")
        notes = _manifest()["notes"]
        assert [n["note"] for n in notes] == ["a", "b", "plain", "plain"]
        assert "key" not in notes[2]

    def test_a_rewritten_note_keeps_the_list_under_the_cap(self, corpus):
        for i in range(200):
            writer.update_manifest(DAY, STREAM, note=f"attempt {i}", note_key="outage:T")
        m = _manifest()
        assert len(m["notes"]) == 1
        assert m.get("notes_dropped") is None


class TestLastPull:
    """last_pull_utc means 'the tape reaches here' [co-8b60y a1]."""

    def test_a_bookkeeping_call_does_not_advance_it(self, corpus, monkeypatch):
        stamps = iter(["2026-09-03T18:00:00Z", "2026-09-03T18:00:00Z",
                       "2026-09-03T20:05:00Z", "2026-09-03T20:05:00Z"])
        monkeypatch.setattr(writer, "utc_now_iso", lambda: next(stamps))
        writer.update_manifest(DAY, STREAM, increment_cycles=5)
        assert _stream()["last_pull_utc"] == "2026-09-03T18:00:00Z"
        writer.update_manifest(DAY, STREAM, note="reconnect attempt", touch_last_pull=False)
        assert _stream()["last_pull_utc"] == "2026-09-03T18:00:00Z"

    def test_a_new_entry_always_gets_the_field(self, corpus):
        writer.update_manifest(DAY, STREAM, note="live stream start", touch_last_pull=False)
        assert _stream()["last_pull_utc"]


class TestBoundedLists:
    def test_errors_keep_the_first_fifty_and_count_the_rest(self, corpus):
        for i in range(1, 6467):
            writer.update_manifest(DAY, STREAM, errors=[f"reconnect #{i}: timed out (possible gap)"])
        st = _stream()
        assert len(st["errors"]) == writer.MAX_MANIFEST_ERRORS == 50
        assert st["errors"][0].startswith("reconnect #1:")
        assert st["errors"][-1].startswith("reconnect #50:")
        assert st["errors_dropped"] == 6416

    def test_a_single_call_with_many_errors_is_bounded_too(self, corpus):
        writer.update_manifest(DAY, STREAM, errors=[f"e{i}" for i in range(120)])
        st = _stream()
        assert len(st["errors"]) == 50 and st["errors_dropped"] == 70

    def test_the_manifest_stays_small_under_a_storm(self, corpus):
        for i in range(1, 3001):
            writer.update_manifest(DAY, STREAM, errors=[f"reconnect #{i}: timed out"],
                                   note=f"reconnect #{i}")
        assert paths.manifest_path(DAY).stat().st_size < 20_000

    def test_notes_keep_the_last_fifty_and_count_the_rest(self, corpus):
        for i in range(1, 121):
            writer.update_manifest(DAY, STREAM, note=f"note {i}")
        m = _manifest()
        assert len(m["notes"]) == writer.MAX_MANIFEST_NOTES == 50
        assert m["notes"][0]["note"] == "note 71" and m["notes"][-1]["note"] == "note 120"
        assert m["notes_dropped"] == 70

    def test_below_the_caps_nothing_changes_shape(self, corpus):
        writer.update_manifest(DAY, STREAM, increment_cycles=3, errors=["one"], note="a")
        st, m = _stream(), _manifest()
        assert st == {"cycles": 3, "errors": ["one"], "last_pull_utc": st["last_pull_utc"]}
        assert "notes_dropped" not in m and len(m["notes"]) == 1


class TestAtomicWrite:
    def test_the_file_is_renamed_into_place_and_no_temp_survives(self, corpus):
        writer.update_manifest(DAY, STREAM, increment_cycles=1)
        p = paths.manifest_path(DAY)
        assert p.exists() and not p.with_name(p.name + ".tmp").exists()

    def test_a_failure_mid_write_leaves_the_previous_manifest_intact(self, corpus, monkeypatch):
        writer.update_manifest(DAY, STREAM, increment_cycles=5)
        before = paths.manifest_path(DAY).read_text()

        def boom(fd):
            raise OSError("disk full")
        with monkeypatch.context() as m:
            m.setattr(writer.os, "fsync", boom)
            with pytest.raises(OSError):
                writer.update_manifest(DAY, STREAM, increment_cycles=1)
        assert paths.manifest_path(DAY).read_text() == before
        assert json.loads(before)["streams"][STREAM]["cycles"] == 5
        # the private temp file does not survive the failure either [st-5oli]
        assert [q.name for q in paths.day_dir(DAY).iterdir() if ".tmp" in q.name] == []


class TestResolveErrors:
    def test_resolving_moves_the_list_into_a_record_with_the_full_count(self, corpus):
        for i in range(1, 8):
            writer.update_manifest(DAY, STREAM, errors=[f"reconnect #{i}: gap"])
        st = _stream()
        st_dropped = st.get("errors_dropped", 0)
        assert st_dropped == 0 and len(st["errors"]) == 7
        writer.update_manifest(DAY, STREAM, resolve_errors=True, note="batch pull complete")
        st = _stream()
        assert st["errors"] == [] and "errors_dropped" not in st
        assert st["errors_resolved"]["count"] == 7
        assert st["errors_resolved"]["sample"] == ["reconnect #1: gap", "reconnect #2: gap",
                                                   "reconnect #3: gap"]
        assert st["errors_resolved"]["note"] == "batch pull complete"
        assert st["errors_resolved"]["resolved_utc"].endswith("Z")

    def test_the_dropped_count_is_part_of_the_resolved_total(self, corpus):
        for i in range(1, 6467):
            writer.update_manifest(DAY, STREAM, errors=[f"reconnect #{i}: gap"])
        writer.update_manifest(DAY, STREAM, resolve_errors=True)
        assert _stream()["errors_resolved"]["count"] == 6466

    def test_resolving_with_nothing_outstanding_writes_no_record(self, corpus):
        writer.update_manifest(DAY, STREAM, increment_cycles=1)
        writer.update_manifest(DAY, STREAM, resolve_errors=True)
        assert "errors_resolved" not in _stream()

    def test_new_errors_after_a_resolve_start_a_fresh_list(self, corpus):
        writer.update_manifest(DAY, STREAM, errors=["reconnect #1: gap"])
        writer.update_manifest(DAY, STREAM, resolve_errors=True)
        writer.update_manifest(DAY, STREAM, errors=["reconnect #1: gap again"])
        st = _stream()
        assert st["errors"] == ["reconnect #1: gap again"]
        assert st["errors_resolved"]["count"] == 1


# --- st-5oli: two writers on one day --------------------------------------
# Measured 2026-09-08: 2026-09-06 and 09-07 manifests failed json.loads with
# 'Extra data' — a complete document followed by the tail of a longer one.
# The temp name was one shared manifest.json.tmp per day, so two writers
# truncated and wrote the same inode, then both renamed it. These pin the
# lock, the private temp name, and the salvage of what the old shape left.

import multiprocessing as _mp
import os as _os

_N_WRITERS = 4
_N_UPDATES = 25


def _hammer(root: str, idx: int) -> None:
    paths.CORPUS_ROOT = type(paths.CORPUS_ROOT)(root)
    for i in range(_N_UPDATES):
        writer.update_manifest(DAY, f"stream{idx}", increment_cycles=1,
                               note=f"w{idx} n{i}", note_key=f"w{idx}:{i}")


class TestConcurrentWriters:
    def test_parallel_writers_leave_one_parseable_manifest_with_every_update(self, corpus):
        ctx = _mp.get_context("fork")
        procs = [ctx.Process(target=_hammer, args=(str(corpus), k)) for k in range(_N_WRITERS)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(60)
        assert all(p.exitcode == 0 for p in procs), [p.exitcode for p in procs]
        m = _manifest()  # json.loads — the file parses
        assert {k: v["cycles"] for k, v in m["streams"].items()} == {
            f"stream{k}": _N_UPDATES for k in range(_N_WRITERS)}
        # 100 keyed notes were written; the cap keeps the last 50 and counts the rest
        assert len(m["notes"]) == writer.MAX_MANIFEST_NOTES
        assert m["notes_dropped"] == _N_WRITERS * _N_UPDATES - writer.MAX_MANIFEST_NOTES
        leftovers = [p.name for p in paths.day_dir(DAY).iterdir() if ".tmp" in p.name]
        assert leftovers == []

    def test_temp_name_is_private_per_write_and_lock_stays(self, corpus):
        seen = []
        real = writer.tempfile.mkstemp

        def spy(**kw):
            fd, name = real(**kw)
            seen.append(name)
            return fd, name

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(writer.tempfile, "mkstemp", spy)
            writer.update_manifest(DAY, STREAM, increment_cycles=1)
            writer.update_manifest(DAY, STREAM, increment_cycles=1)
        assert len(seen) == 2 and seen[0] != seen[1]
        assert all(_os.path.basename(n).startswith("manifest.json.") for n in seen)
        assert not any(_os.path.exists(n) for n in seen)
        assert writer.lock_path(paths.manifest_path(DAY)).exists()
        assert _stream()["cycles"] == 2

    def test_the_manifest_is_world_readable_not_mkstemp_0600(self, corpus):
        writer.update_manifest(DAY, STREAM, increment_cycles=1)
        p = paths.manifest_path(DAY)
        assert p.stat().st_mode & 0o777 == 0o644
        p.chmod(0o640)
        writer.update_manifest(DAY, STREAM, increment_cycles=1)
        assert p.stat().st_mode & 0o777 == 0o640  # an existing mode is kept


def _interleaved(corpus) -> str:
    """Rebuild the measured 09-07 shape: a valid doc, then a longer doc's tail."""
    writer.update_manifest(DAY, STREAM, increment_cycles=7, note="first")
    good = paths.manifest_path(DAY).read_text()
    tail = ',\n      "key": "outage:73:2026-09-07T06:55:24Z"\n    }\n  ],\n  "notes_dropped": 178\n}\n'
    paths.manifest_path(DAY).write_text(good + tail)
    with pytest.raises(json.JSONDecodeError):
        json.loads(paths.manifest_path(DAY).read_text())
    return good


class TestSalvage:
    def test_a_writer_meeting_an_interleaved_manifest_salvages_and_continues(self, corpus, caplog):
        _interleaved(corpus)
        with caplog.at_level("WARNING", logger="market.corpus.writer"):
            writer.update_manifest(DAY, STREAM, increment_cycles=1)
        m = _manifest()
        assert m["streams"][STREAM]["cycles"] == 8
        repair = [n for n in m["notes"] if n.get("key", "").startswith("repair:")]
        assert len(repair) == 1
        assert "outage:73" in repair[0]["note"] and "notes_dropped\": 178" in repair[0]["note"]
        kept = [p for p in paths.day_dir(DAY).iterdir() if ".corrupt-" in p.name]
        assert len(kept) == 1
        with pytest.raises(json.JSONDecodeError):
            json.loads(kept[0].read_text())  # the original is preserved verbatim
        assert "salvaged" in caplog.text

    def test_salvage_is_callable_on_its_own_for_the_two_measured_days(self, corpus):
        good = _interleaved(corpus)
        m, report = writer.salvage(paths.manifest_path(DAY))
        assert m["streams"][STREAM]["cycles"] == 7
        assert report.startswith(f"salvaged {len(good)} of ")
        assert json.loads(paths.manifest_path(DAY).read_text())["notes"][-1]["key"].startswith("repair:")

    def test_nothing_to_salvage_raises(self, corpus):
        paths.day_dir(DAY, create=True)
        paths.manifest_path(DAY).write_text("{ this is not json")
        with pytest.raises(ValueError, match="no leading JSON document"):
            writer.salvage(paths.manifest_path(DAY))
        with pytest.raises(ValueError):
            writer.update_manifest(DAY, STREAM, increment_cycles=1)
