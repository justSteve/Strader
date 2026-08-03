"""Offline tests for the Databento corpus compactor.

Verifies that compact_day packs .dbn -> .dbn.zst (zstandard) and
.jsonl -> .jsonl.gz (gzip), removes the sources, and that both compressed
outputs round-trip back to the original bytes.
"""
from __future__ import annotations

import gzip
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_compactor():
    path = REPO_ROOT / "scripts" / "corpus_compact_databento.py"
    spec = importlib.util.spec_from_file_location("corpus_compact_databento", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


compact = _load_compactor()


def test_compact_day_packs_and_roundtrips(tmp_path):
    dbn_bytes = b"\x00\x01DBN-fake-stream\xff" * 2000
    jsonl_text = '{"stream":"databento_opra","data":{"price":2.35}}\n' * 2000
    (tmp_path / "databento_opra.0.dbn").write_bytes(dbn_bytes)
    (tmp_path / "databento_opra.jsonl").write_text(jsonl_text)

    results = compact.compact_day(tmp_path, keep=False)

    zst = tmp_path / "databento_opra.0.dbn.zst"
    gz = tmp_path / "databento_opra.jsonl.gz"
    assert zst.exists() and gz.exists()
    # sources removed after verified compress
    assert not (tmp_path / "databento_opra.0.dbn").exists()
    assert not (tmp_path / "databento_opra.jsonl").exists()
    # compression actually shrank the highly-repetitive inputs
    assert zst.stat().st_size < len(dbn_bytes)
    assert gz.stat().st_size < len(jsonl_text)

    # round-trip fidelity
    import zstandard
    with zst.open("rb") as f:
        assert zstandard.ZstdDecompressor().stream_reader(f).read() == dbn_bytes
    assert gzip.decompress(gz.read_bytes()) == jsonl_text.encode()

    # summary covers both files
    names = {r["name"] for r in results}
    assert names == {"databento_opra.0.dbn", "databento_opra.jsonl"}


def test_compact_day_idempotent(tmp_path):
    (tmp_path / "databento_opra.jsonl").write_text("x\n" * 100)
    compact.compact_day(tmp_path, keep=False)
    # second pass: source already gone, output exists -> nothing to do
    second = compact.compact_day(tmp_path, keep=False)
    assert second == []


# --- readers survive compaction [st-itky] -----------------------------------
# The compactor REMOVES the uncompressed source unless --keep. Before this,
# read_corpus_day opened the plain path directly and every es_day_path().exists()
# guard read a compacted day as an absent one — so scheduling compaction would
# have silently made finished days invisible to replay, drills and measurement.

import gzip as _gzip
import json
from datetime import date

import pytest

from market.corpus.paths import open_corpus_text, resolve_existing
from market.orderflow import replay as _replay


def _write_es_day(root, day, rows):
    ddir = root / day.isoformat()
    ddir.mkdir(parents=True, exist_ok=True)
    p = ddir / "databento_glbx_es.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _es_row(price, size, ts_event, seq):
    return {
        "ts_pull_utc": "2026-06-08T18:00:00+00:00",
        "stream": "databento_glbx_es",
        "provenance": {"dataset": "GLBX.MDP3", "schema": "trades",
                       "ts_event": ts_event, "source": "batch"},
        "data": {"symbol": "ESU6", "instrument_id": 7, "price": price,
                 "size": size, "side": "B", "action": "T", "sequence": seq,
                 "flags": None},
    }


def test_resolve_existing_prefers_plain_then_falls_back_to_gz(tmp_path):
    p = tmp_path / "x.jsonl"
    assert resolve_existing(p) is None            # neither form present
    gz = tmp_path / "x.jsonl.gz"
    gz.write_bytes(_gzip.compress(b"{}\n"))
    assert resolve_existing(p) == gz              # compacted only
    p.write_text("{}\n", encoding="utf-8")
    assert resolve_existing(p) == p               # both -> plain wins


def test_open_corpus_text_names_both_candidates_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        open_corpus_text(tmp_path / "gone.jsonl")
    assert "gone.jsonl" in str(e.value) and ".gz" in str(e.value)


def test_read_corpus_day_reads_a_compacted_day(tmp_path, monkeypatch):
    day = date(2026, 6, 8)
    rows = [_es_row(5512.25, 3, "2026-06-08T14:30:00+00:00", 1),
            _es_row(5512.50, 1, "2026-06-08T14:30:01+00:00", 2)]
    _write_es_day(tmp_path, day, rows)
    monkeypatch.setattr(_replay, "_CORPUS_ROOT", tmp_path)

    before = _replay.read_corpus_day(day)
    assert [t.price for t in before] == [5512.25, 5512.50]
    assert _replay.has_es_day(day)

    # Compact the day exactly as the cron will — source removed, not kept.
    compact.compact_day(tmp_path / day.isoformat())
    assert not (tmp_path / day.isoformat() / "databento_glbx_es.jsonl").exists()
    assert (tmp_path / day.isoformat() / "databento_glbx_es.jsonl.gz").exists()

    # The day must still be both visible and byte-identical after the round trip.
    assert _replay.has_es_day(day), "compacted day read as absent"
    after = _replay.read_corpus_day(day)
    assert [(t.price, t.size, t.sequence) for t in after] == \
           [(t.price, t.size, t.sequence) for t in before]
