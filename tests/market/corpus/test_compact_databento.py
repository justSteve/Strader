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


# --- atomic, verified archives [co-8b60y] ------------------------------------
# A kill mid-compress used to leave a truncated .zst under the final name that
# the next run treated as done. Measured 2026-09-04: a zstd frame cut in half
# decompresses to zero bytes WITHOUT raising, so only a byte-count comparison
# against the source proves an archive whole.

DBN = b"\x00\x01DBN-fake-stream\xff" * 20000


def _raising_jobs(monkeypatch, fail_after_bytes=None):
    """Swap the zstd job for one that writes a partial archive then raises —
    the shape of a process dying mid-copy."""
    def torn(src, dst):
        with dst.open("wb") as f:
            f.write(b"\x28\xb5\x2f\xfd" + b"\x00" * 100)   # zstd magic + junk
        raise OSError("simulated kill mid-compress")
    monkeypatch.setattr(compact, "JOBS", ((("databento_*.dbn", ".zst", torn),)
                                         + tuple(j for j in compact.JOBS if j[1] == ".gz")))


def test_mid_compress_failure_leaves_no_archive_and_source_intact(tmp_path, monkeypatch):
    src = tmp_path / "databento_glbx_es.0.dbn"
    src.write_bytes(DBN)
    _raising_jobs(monkeypatch)
    import pytest as _pt
    with _pt.raises(OSError):
        compact.compact_day(tmp_path)
    assert src.exists() and src.read_bytes() == DBN
    assert not (tmp_path / "databento_glbx_es.0.dbn.zst").exists()
    assert list(tmp_path.glob("*.tmp")) == []

    # a second run with a working compressor completes the job
    monkeypatch.undo()
    res = compact.compact_day(tmp_path)
    assert [r["name"] for r in res] == ["databento_glbx_es.0.dbn"]
    assert not src.exists()
    zst = tmp_path / "databento_glbx_es.0.dbn.zst"
    compact.verify_archive(zst, len(DBN))       # whole


def test_leftover_tmp_is_removed_and_never_treated_as_done(tmp_path):
    src = tmp_path / "databento_glbx_es.0.dbn"
    src.write_bytes(DBN)
    planted = tmp_path / "databento_glbx_es.0.dbn.zst.tmp"
    planted.write_bytes(b"half an archive")
    res = compact.compact_day(tmp_path)
    assert not planted.exists()
    assert [r["name"] for r in res] == ["databento_glbx_es.0.dbn"]
    assert (tmp_path / "databento_glbx_es.0.dbn.zst").exists()
    assert not src.exists()
    # the planted junk never became the archive
    assert (tmp_path / "databento_glbx_es.0.dbn.zst").read_bytes() != b"half an archive"


def test_truncated_zst_is_detected_by_verify(tmp_path):
    import zstandard
    whole = zstandard.ZstdCompressor(level=10).compress(DBN)
    good = tmp_path / "good.dbn.zst"
    good.write_bytes(whole)
    compact.verify_archive(good, len(DBN))
    torn = tmp_path / "torn.dbn.zst"
    torn.write_bytes(whole[: len(whole) // 2])
    import pytest as _pt
    with _pt.raises(compact.ArchiveVerifyError):
        compact.verify_archive(torn, len(DBN))
    # and gzip: a cut stream raises EOFError, which verify reports the same way
    import gzip as _gz
    gz = tmp_path / "x.jsonl.gz"
    whole_gz = _gz.compress(b"x\n" * 50000)
    gz.write_bytes(whole_gz[: len(whole_gz) // 2])
    with _pt.raises(compact.ArchiveVerifyError):
        compact.verify_archive(gz, 100000)
    gz.write_bytes(whole_gz)
    compact.verify_archive(gz, 100000)


def test_torn_archive_under_the_final_name_is_repacked_not_trusted(tmp_path):
    """The pre-2026-09-04 failure: a truncated .zst exists beside its source
    (a killed run that had already renamed — or the old direct write). The
    archive must be re-verified against the source and packed again."""
    import zstandard
    src = tmp_path / "databento_glbx_es.0.dbn"
    src.write_bytes(DBN)
    whole = zstandard.ZstdCompressor(level=10).compress(DBN)
    dst = tmp_path / "databento_glbx_es.0.dbn.zst"
    dst.write_bytes(whole[: len(whole) // 2])
    res = compact.compact_day(tmp_path)
    assert len(res) == 1 and res[0]["resumed"] is False
    compact.verify_archive(dst, len(DBN))
    assert not src.exists()


def test_whole_archive_beside_its_source_is_resumed_without_recompressing(tmp_path, monkeypatch):
    """A run killed between the rename and the unlink. The archive is whole;
    finish the job (remove the source) and do not compress again."""
    import zstandard
    src = tmp_path / "databento_glbx_es.0.dbn"
    src.write_bytes(DBN)
    dst = tmp_path / "databento_glbx_es.0.dbn.zst"
    dst.write_bytes(zstandard.ZstdCompressor(level=10).compress(DBN))
    calls = []
    monkeypatch.setattr(compact, "JOBS", ((
        "databento_*.dbn", ".zst", lambda s, d: calls.append(s)),))
    res = compact.compact_day(tmp_path)
    assert calls == []
    assert len(res) == 1 and res[0]["resumed"] is True
    assert not src.exists() and dst.exists()


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
