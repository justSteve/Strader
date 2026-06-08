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
