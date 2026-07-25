"""Hindsight-annotation append/read tests. [st-055]"""
from datetime import date

import pytest

from scripts.replay_annotate import append_annotation, read_annotations

DAY = date(2026, 7, 13)


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "annotations_test.jsonl"
    append_annotation(DAY, "flush into 6212 was the real one", time_ct="09:14", path=p)
    append_annotation(DAY, "chop after lunch, recognizer rightly quiet", bar_i=140, path=p)
    rows = read_annotations(DAY, path=p)
    assert [r["text"] for r in rows] == [
        "flush into 6212 was the real one",
        "chop after lunch, recognizer rightly quiet",
    ]
    assert rows[0]["time_ct"] == "09:14" and rows[0]["bar_i"] is None
    assert rows[1]["bar_i"] == 140 and rows[1]["time_ct"] is None
    assert all(r["type"] == "Annotation" and r["date"] == "2026-07-13" for r in rows)


def test_append_is_append_only(tmp_path):
    p = tmp_path / "annotations_test.jsonl"
    append_annotation(DAY, "first", path=p)
    before = p.read_text()
    append_annotation(DAY, "second", path=p)
    assert p.read_text().startswith(before)


def test_rejects_empty_text_and_bad_time(tmp_path):
    p = tmp_path / "annotations_test.jsonl"
    with pytest.raises(ValueError):
        append_annotation(DAY, "   ", path=p)
    with pytest.raises(ValueError):
        append_annotation(DAY, "note", time_ct="25:99", path=p)
    assert not p.exists()


def test_read_missing_file_is_empty(tmp_path):
    assert read_annotations(DAY, path=tmp_path / "nope.jsonl") == []
