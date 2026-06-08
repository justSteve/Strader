#!/usr/bin/env python3
"""T+1 compaction for the Databento corpus — shrink a finished day. [st-xc9]

The live streamer writes two layers per day (see corpus_stream_databento.py):
a lossless raw-DBN archive and a verbose JSONL working copy. JSONL runs
~250-370 MB/day for OPRA and is ~40% repeated boilerplate; raw DBN is compact
but uncompressed. This compactor, run after the close (T+1), packs both:

  databento_*.{N}.dbn   ->  .dbn.zst   (zstandard — stays DBNStore-readable)
  databento_*.jsonl     ->  .jsonl.gz  (stdlib gzip)

The `.dbn.zst` is the archival source of truth. Idempotent: existing outputs
are skipped unless --force. The uncompressed source is removed after a
verified compress unless --keep.

Usage:
    .venv/bin/python scripts/corpus_compact_databento.py --date 2026-06-08
    .venv/bin/python scripts/corpus_compact_databento.py --date 2026-06-08 --keep
    # T+1 sweep (cron, weekday mornings): compact yesterday
    .venv/bin/python scripts/corpus_compact_databento.py --yesterday
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sys
from datetime import date as _date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import central_date, day_dir  # noqa: E402


def _zstd_compress(src: Path, dst: Path) -> None:
    import zstandard
    cctx = zstandard.ZstdCompressor(level=10)
    with src.open("rb") as fin, dst.open("wb") as fout:
        cctx.copy_stream(fin, fout)


def _gzip_compress(src: Path, dst: Path) -> None:
    with src.open("rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout)


def compact_day(ddir: Path, *, keep: bool = False, force: bool = False) -> list[dict]:
    """Compact every Databento data file in one day-dir. Returns per-file
    {name, dst, before, after} records (sizes in bytes)."""
    jobs = [
        ("databento_*.dbn", ".zst", _zstd_compress),
        ("databento_*.jsonl", ".gz", _gzip_compress),
    ]
    results: list[dict] = []
    for pattern, ext, compress in jobs:
        for src in sorted(ddir.glob(pattern)):
            dst = src.parent / (src.name + ext)
            if dst.exists() and not force:
                continue
            before = src.stat().st_size
            compress(src, dst)
            after = dst.stat().st_size if dst.exists() else 0
            if after > 0 and not keep:
                src.unlink()
            results.append({"name": src.name, "dst": dst.name,
                            "before": before, "after": after})
    return results


def _fmt(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact a day's Databento corpus")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="Day to compact, YYYY-MM-DD (US/Central)")
    g.add_argument("--yesterday", action="store_true",
                   help="Compact the prior Central calendar day (T+1 sweep)")
    parser.add_argument("--keep", action="store_true",
                        help="Keep the uncompressed source files")
    parser.add_argument("--force", action="store_true",
                        help="Recompress even if the output already exists")
    args = parser.parse_args()

    if args.yesterday:
        d = central_date() - timedelta(days=1)
    else:
        d = _date.fromisoformat(args.date)

    ddir = day_dir(d)
    if not ddir.exists():
        print(f"[ALERT] no corpus dir for {d.isoformat()} ({ddir})", file=sys.stderr)
        return 1

    results = compact_day(ddir, keep=args.keep, force=args.force)
    if not results:
        print(f"# {d.isoformat()}: nothing to compact (already packed?)")
        return 0

    tot_before = sum(r["before"] for r in results)
    tot_after = sum(r["after"] for r in results)
    print(f"# Compacted {d.isoformat()} ({ddir})")
    for r in results:
        ratio = r["before"] / r["after"] if r["after"] else 0
        print(f"  {r['name']:<32} {_fmt(r['before']):>9} -> "
              f"{_fmt(r['after']):>9}  ({ratio:.1f}x)  {r['dst']}")
    ratio = tot_before / tot_after if tot_after else 0
    print(f"  {'TOTAL':<32} {_fmt(tot_before):>9} -> {_fmt(tot_after):>9}  "
          f"({ratio:.1f}x)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
