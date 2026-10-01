"""read_mbp1_day opens a compacted (.jsonl.gz-only) day. [st-epa3]

corpus_compact_databento.py packs a finished day and REMOVES the plain file;
read_mbp1_day used ``path.exists()`` on the raw name and raised
FileNotFoundError on every packed day.
"""
from __future__ import annotations

import gzip
import json
from datetime import date

import pytest

from market.orderflow import quotes

ROW = {
    "provenance": {"ts_event": "2026-08-21T13:30:00.000000+00:00"},
    "data": {"symbol": "ESU6", "instrument_id": 1, "action": "T", "side": "A",
             "price": 6400.25, "size": 3, "bid_px": 6400.0, "ask_px": 6400.25,
             "bid_sz": 5, "ask_sz": 7, "sequence": 9},
}


def test_gz_only_day_by_date(tmp_path, monkeypatch):
    monkeypatch.setattr(quotes, "_CORPUS_ROOT", tmp_path)
    d = date(2026, 8, 21)
    plain = quotes.mbp1_day_path(d)
    plain.parent.mkdir(parents=True)
    with gzip.open(str(plain) + ".gz", "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(ROW) + "\n")
    assert not plain.exists()
    (ev,) = list(quotes.read_mbp1_day(d))
    assert (ev.action, ev.price, ev.size) == ("T", 6400.25, 3)


def test_gz_only_day_by_plain_path(tmp_path):
    plain = tmp_path / "databento_glbx_es_mbp1.jsonl"
    with gzip.open(str(plain) + ".gz", "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(ROW) + "\n")
    assert len(list(quotes.read_mbp1_day(plain))) == 1


def test_missing_day_names_both_candidates(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"\.gz"):
        list(quotes.read_mbp1_day(tmp_path / "nope.jsonl"))
