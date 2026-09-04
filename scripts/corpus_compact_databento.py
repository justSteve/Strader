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

Atomic and verified [co-8b60y, 2026-09-04]
------------------------------------------
Until 2026-09-04 the archive was written straight to its final name and the
source unlinked as soon as the output had a non-zero size. A kill mid-compress
(a reboot, a unit stop, an OOM) therefore left a truncated `.dbn.zst` that the
next run treated as done, and readers that resolve the packed form first
(market.corpus.paths.resolve_existing) would have opened it. Measured while
writing this: a zstd frame cut in half decompresses to ZERO bytes without
raising — the stream reader simply stops — so "the file exists" and even "it
decompresses" prove nothing. The archive is now written to `<dst>.tmp`,
decompressed end to end and its byte count compared with the source, renamed
into place only when that matches, and the source is unlinked only after the
rename. A leftover `.tmp` from a killed run is removed at the start of the next
run and is never treated as an archive. An archive that already exists beside
its source (a run killed between the rename and the unlink) is re-verified and,
if whole, the source is removed without recompressing.

Usage:
    .venv/bin/python scripts/corpus_compact_databento.py --date 2026-06-08
    .venv/bin/python scripts/corpus_compact_databento.py --date 2026-06-08 --keep
    # T+1 sweep (cron, weekday mornings): compact yesterday
    .venv/bin/python scripts/corpus_compact_databento.py --yesterday
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sys
from datetime import date as _date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import central_date, day_dir  # noqa: E402

#: Suffix of an archive still being written. Never read as data.
TMP_SUFFIX = ".tmp"

_CHUNK = 1 << 20


class ArchiveVerifyError(RuntimeError):
    """The archive does not decompress back to exactly the source's bytes."""


def _zstd_compress(src: Path, dst: Path) -> None:
    import zstandard
    cctx = zstandard.ZstdCompressor(level=10)
    with src.open("rb") as fin, dst.open("wb") as fout:
        cctx.copy_stream(fin, fout)


def _gzip_compress(src: Path, dst: Path) -> None:
    with src.open("rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout)


def _count_stream(reader) -> int:
    n = 0
    while True:
        chunk = reader.read(_CHUNK)
        if not chunk:
            return n
        n += len(chunk)


def _verify_zst(path: Path, expected: int) -> None:
    """Decompress ``path`` end to end and require exactly ``expected`` bytes.
    A truncated frame yields fewer bytes (measured: zero) without raising."""
    import zstandard
    try:
        with path.open("rb") as f:
            got = _count_stream(zstandard.ZstdDecompressor().stream_reader(f))
    except (zstandard.ZstdError, OSError) as e:
        raise ArchiveVerifyError(f"{path.name}: {type(e).__name__}: {e}") from e
    if got != expected:
        raise ArchiveVerifyError(
            f"{path.name}: decompressed to {got} bytes, source was {expected}")


def _verify_gz(path: Path, expected: int) -> None:
    try:
        with gzip.open(path, "rb") as f:
            got = _count_stream(f)
    except (EOFError, gzip.BadGzipFile, OSError) as e:
        raise ArchiveVerifyError(f"{path.name}: {type(e).__name__}: {e}") from e
    if got != expected:
        raise ArchiveVerifyError(
            f"{path.name}: decompressed to {got} bytes, source was {expected}")


def verify_archive(dst: Path, expected: int, *, kind: str | None = None) -> None:
    """Raise ArchiveVerifyError unless ``dst`` is a whole archive of exactly
    ``expected`` source bytes. ``kind`` is the archive format (".zst" or
    ".gz"); it defaults to the file's suffix and is passed explicitly for a
    temp file whose suffix is ``.tmp``."""
    kind = kind or dst.suffix
    if dst.stat().st_size <= 0:
        raise ArchiveVerifyError(f"{dst.name}: empty archive")
    if kind == ".zst":
        _verify_zst(dst, expected)
    elif kind == ".gz":
        _verify_gz(dst, expected)
    else:
        raise ArchiveVerifyError(f"{dst.name}: unknown archive kind {kind!r}")


def _archive_is_whole(dst: Path, expected: int) -> bool:
    try:
        verify_archive(dst, expected)
        return True
    except ArchiveVerifyError:
        return False


JOBS = (
    ("databento_*.dbn", ".zst", _zstd_compress),
    ("databento_*.jsonl", ".gz", _gzip_compress),
)


def remove_leftover_tmp(ddir: Path) -> list[Path]:
    """Delete archives a killed run left half-written. Returns what went."""
    gone: list[Path] = []
    for pattern, ext, _ in JOBS:
        for t in sorted(ddir.glob(pattern + ext + TMP_SUFFIX)):
            t.unlink()
            gone.append(t)
    return gone


def compact_day(ddir: Path, *, keep: bool = False, force: bool = False,
                log=None) -> list[dict]:
    """Compact every Databento data file in one day-dir. Returns per-file
    {name, dst, before, after, resumed} records (sizes in bytes).

    Every archive is verified against the source's byte count before it is
    renamed into place, and the source is unlinked only after the rename.
    Raises on a compress or verify failure with the temp file already removed
    and the source untouched, so a second run starts clean.
    """
    say = log or (lambda msg: print(msg, file=sys.stderr))
    for t in remove_leftover_tmp(ddir):
        say(f"[compact] removed half-written archive from an earlier run: {t.name}")

    results: list[dict] = []
    for pattern, ext, compress in JOBS:
        for src in sorted(ddir.glob(pattern)):
            dst = src.parent / (src.name + ext)
            tmp = src.parent / (dst.name + TMP_SUFFIX)
            before = src.stat().st_size

            if dst.exists() and not force:
                # A run killed between the rename and the unlink leaves both.
                # Re-verify the archive against the source that is still here;
                # whole means finish the job, torn means pack again.
                if _archive_is_whole(dst, before):
                    if not keep:
                        src.unlink()
                    results.append({"name": src.name, "dst": dst.name,
                                    "before": before, "after": dst.stat().st_size,
                                    "resumed": True})
                    continue
                say(f"[compact] {dst.name} exists beside its source but does not "
                    f"verify — packing again")

            try:
                compress(src, tmp)
                verify_archive(tmp, before, kind=ext)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
            os.replace(tmp, dst)
            after = dst.stat().st_size
            if not keep:
                src.unlink()
            results.append({"name": src.name, "dst": dst.name,
                            "before": before, "after": after, "resumed": False})
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

    try:
        results = compact_day(ddir, keep=args.keep, force=args.force)
    except ArchiveVerifyError as e:
        print(f"[ALERT] {d.isoformat()}: archive failed verification, source kept: {e}",
              file=sys.stderr)
        return 3
    except OSError as e:
        print(f"[ALERT] {d.isoformat()}: compress failed, source kept: {e}",
              file=sys.stderr)
        return 3
    if not results:
        print(f"# {d.isoformat()}: nothing to compact (already packed?)")
        return 0

    tot_before = sum(r["before"] for r in results)
    tot_after = sum(r["after"] for r in results)
    print(f"# Compacted {d.isoformat()} ({ddir})")
    for r in results:
        ratio = r["before"] / r["after"] if r["after"] else 0
        tag = "  (resumed: archive was whole, source removed)" if r.get("resumed") else ""
        print(f"  {r['name']:<32} {_fmt(r['before']):>9} -> "
              f"{_fmt(r['after']):>9}  ({ratio:.1f}x)  {r['dst']}{tag}")
    ratio = tot_before / tot_after if tot_after else 0
    print(f"  {'TOTAL':<32} {_fmt(tot_before):>9} -> {_fmt(tot_after):>9}  "
          f"({ratio:.1f}x)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
