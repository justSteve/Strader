"""local_chart reads the tape through the shared trade seam. [st-epa3]

It used to ``path.exists()`` the raw ``.jsonl`` (every compacted day raised
FileNotFoundError) and read rows in file order with no dedup.
"""
from __future__ import annotations

import gzip
import json

import pytest

from tools import local_chart


def _row(ts: str, seq: int, price: float, size: int = 1, side: str = "B",
         pulled: str = "2026-08-21T13:31:05Z") -> str:
    return json.dumps({
        "ts_pull_utc": pulled,
        "provenance": {"ts_event": ts},
        "data": {"symbol": "ESU6", "instrument_id": 1, "price": price,
                 "size": size, "side": side, "sequence": seq},
    }) + "\n"


def _write_gz_day(root, day, rows):
    d = root / day
    d.mkdir(parents=True)
    with gzip.open(d / "databento_glbx_es.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.writelines(rows)


def test_gz_only_day_sorted_and_deduped(tmp_path, monkeypatch):
    monkeypatch.setattr(local_chart, "CORPUS_ROOT", tmp_path)
    rows = [
        _row("2026-08-21T13:31:00+00:00", 2, 6402.0),
        _row("2026-08-21T13:30:00+00:00", 1, 6400.0),   # out of order
        _row("2026-08-21T13:31:00+00:00", 2, 6402.0,   # re-delivered by a later pull
             pulled="2026-08-21T13:40:00Z"),
    ]
    _write_gz_day(tmp_path, "2026-08-21", rows)
    ticks = local_chart._load_ticks("2026-08-21")
    assert [p for _, p in ticks] == [6400.0, 6402.0]
    assert ticks[0][0].utcoffset().total_seconds() == -5 * 3600  # CT


def test_bar_close_follows_time_not_file_order(tmp_path, monkeypatch):
    monkeypatch.setattr(local_chart, "CORPUS_ROOT", tmp_path)
    _write_gz_day(tmp_path, "2026-08-21", [
        _row("2026-08-21T13:30:50+00:00", 2, 6401.0),
        _row("2026-08-21T13:30:10+00:00", 1, 6399.0),
    ])
    ticks = local_chart._load_ticks("2026-08-21")
    bars = local_chart._aggregate_ohlc(ticks, 1, local_chart._ct_time("08:30"),
                                       local_chart._ct_time("15:00"))
    assert (bars[0]["open"], bars[0]["close"]) == (6399.0, 6401.0)


def test_missing_day_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(local_chart, "CORPUS_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError, match="2026-08-22"):
        local_chart._load_ticks("2026-08-22")
