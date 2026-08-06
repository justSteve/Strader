r"""Migrate gexbot-hist raw day-dirs to the Z: archive. [st-me3z]

Moves data/corpus/gexbot-hist/<date>/ trees to /mnt/z/Harvest/gexbot-hist/<date>/
(Z:\Harvest is the canonical harvest archive per the backup-estate ruling,
co-5yxi). Every file is stream-copied with a sha256 of the source, then the
destination is re-read and re-hashed; the local day-dir is deleted only after
every file in it verifies. A day that fails verification keeps its local copy,
keeps whatever landed on Z: for inspection, and fails the run.

Safety properties:
- Idempotent: a day already fully verified on Z: is re-verified cheaply
  (size check) and the local copy removed; partial prior copies are
  re-copied file by file.
- In-flight guard: day-dirs with any file modified in the last --active-window
  minutes are skipped, so a concurrently running backfill is never raced.
- The fetch manifest (manifest.jsonl) stays local — the backfill appends to
  it. A snapshot is copied to Z: each run for provenance.
- Companion change: gexbot_hist_backfill.py treats a non-empty archived copy
  as already-present, so re-runs do not re-fetch migrated days.

Usage:
    .venv/bin/python scripts/gexbot_hist_migrate.py [--dry-run]
        [--active-window 30] [--dest /mnt/z/Harvest/gexbot-hist]

Migration log: gexbot-hist/migrate-manifest.jsonl (local) mirrored to the
destination root. Exit 0 = every eligible day migrated and verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HIST_ROOT = REPO / "data" / "corpus" / "gexbot-hist"
DEFAULT_DEST = Path("/mnt/z/Harvest/gexbot-hist")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHUNK = 4 * 1024 * 1024


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def copy_with_hash(src: Path, dst: Path) -> tuple[str, int]:
    """Stream src → dst, returning (sha256_of_source, bytes)."""
    h = hashlib.sha256()
    size = 0
    with src.open("rb") as fin, dst.open("wb") as fout:
        while chunk := fin.read(CHUNK):
            h.update(chunk)
            fout.write(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def migrate_day(day_dir: Path, dest_root: Path, dry_run: bool) -> dict:
    dest_dir = dest_root / day_dir.name
    files = sorted(p for p in day_dir.iterdir() if p.is_file())
    entry = {
        "date": day_dir.name,
        "files": len(files),
        "bytes": sum(p.stat().st_size for p in files),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if dry_run:
        entry["status"] = "dry-run"
        return entry

    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in files:
        dst = dest_dir / src.name
        src_size = src.stat().st_size
        if dst.exists() and dst.stat().st_size == src_size:
            src_sha, _ = sha256_file(src)
            dst_sha, _ = sha256_file(dst)
            if src_sha == dst_sha:
                continue  # already migrated and intact
        src_sha, nbytes = copy_with_hash(src, dst)
        dst_sha, dst_bytes = sha256_file(dst)
        if src_sha != dst_sha or nbytes != dst_bytes:
            entry.update(status="verify-failed", file=src.name,
                         src_sha=src_sha, dst_sha=dst_sha)
            return entry

    shutil.rmtree(day_dir)
    entry["status"] = "migrated"
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate gexbot-hist days to Z: archive")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--active-window", type=int, default=30,
                    help="Skip day-dirs written within this many minutes (default 30)")
    args = ap.parse_args()

    if not HIST_ROOT.is_dir():
        log(f"ERROR: {HIST_ROOT} does not exist; nothing to migrate")
        return 1
    # /mnt/z must actually be the mounted archive drive, not a stray local dir.
    if not args.dest.parent.is_dir():
        log(f"ERROR: destination root {args.dest.parent} unavailable — is Z: mounted?")
        return 1

    day_dirs = sorted(p for p in HIST_ROOT.iterdir()
                      if p.is_dir() and DAY_RE.match(p.name))
    now = time.time()
    migrated = skipped_active = failed = 0
    manifest_local = HIST_ROOT / "migrate-manifest.jsonl"

    for day_dir in day_dirs:
        newest = max((p.stat().st_mtime for p in day_dir.iterdir()), default=0)
        if now - newest < args.active_window * 60:
            log(f"{day_dir.name}  SKIP (written {int((now - newest) / 60)}m ago; "
                f"possibly in-flight)")
            skipped_active += 1
            continue
        entry = migrate_day(day_dir, args.dest, args.dry_run)
        log(f"{day_dir.name}  {entry['status']}  "
            f"({entry['files']} files, {entry['bytes'] / 1e9:.2f} GB)")
        if not args.dry_run:
            with manifest_local.open("a") as f:
                f.write(json.dumps(entry) + "\n")
            with (args.dest / "migrate-manifest.jsonl").open("a") as f:
                f.write(json.dumps(entry) + "\n")
        if entry["status"] == "migrated":
            migrated += 1
        elif entry["status"] == "verify-failed":
            failed += 1
            log(f"ERROR: verification failed on {entry.get('file')} — "
                f"local copy retained")

    fetch_manifest = HIST_ROOT / "manifest.jsonl"
    if fetch_manifest.exists() and not args.dry_run:
        shutil.copy2(fetch_manifest, args.dest / "fetch-manifest-snapshot.jsonl")

    log(f"DONE: {migrated} migrated, {skipped_active} skipped as active, "
        f"{failed} failed, {len(day_dirs)} day-dirs seen")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
