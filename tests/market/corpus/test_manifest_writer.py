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

        def boom(self, text):
            raise OSError("disk full")
        with monkeypatch.context() as m:
            m.setattr(type(paths.manifest_path(DAY)), "write_text", boom)
            with pytest.raises(OSError):
                writer.update_manifest(DAY, STREAM, increment_cycles=1)
        assert paths.manifest_path(DAY).read_text() == before
        assert json.loads(before)["streams"][STREAM]["cycles"] == 5


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
