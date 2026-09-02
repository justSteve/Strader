#!/usr/bin/env python3
"""Make gexbot-hist's `.json.gz` files actually gzip. [st-kr4a]

Measured 2026-09-02: **all 270 files under data/corpus/gexbot-hist are plain
JSON named `.json.gz`** — 20.91 GB, not one of them carrying the gzip magic.
Anything that trusts the extension and calls `gzip.open()` fails on every one.
That is the landmine st-kr4a was filed against, and it points at the retro cut.

THIS TOUCHES THE ONE ARCHIVE THAT CANNOT BE REBUILT. `/hist` is Quant-only and
lapses after 2026-09-06, after which no GEX day can ever be backfilled. So the
conversion is verified rather than trusted, per file:

    1. compress the original to a sibling .tmp
    2. read the .tmp back through gzip and assert it is BYTE-IDENTICAL to the
       original
    3. only then os.replace() the temp over the original — atomic, so a crash
       mid-write leaves the original intact
    4. any mismatch or error: delete the temp, leave the original untouched,
       count it as a failure and keep going

At no point is the only copy of a file at risk. A file that fails verification
is left exactly as it was.

Usage:
    fix_gexbot_hist_gzip.py --check              # report, change nothing
    fix_gexbot_hist_gzip.py --day 2026-08-06     # convert one day
    fix_gexbot_hist_gzip.py --all                # convert everything

Exit codes: 0 clean · 1 some files failed verification · 2 usage.
"""

from __future__ import annotations

import argparse
import gzip
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "corpus" / "gexbot-hist"
GZIP_MAGIC = b"\x1f\x8b"
# 6 is gzip's default; measured on one 118 MB file it beats level 9 on wall
# clock by a wide margin for ~1% more bytes, and this runs over 20 GB.
LEVEL = 6


def is_plain_json(path: Path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(2) != GZIP_MAGIC


def convert(path: Path) -> tuple[bool, str]:
    """Compress in place, verified. Returns (ok, message)."""
    original = path.read_bytes()
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with gzip.open(tmp, "wb", compresslevel=LEVEL) as out:
            out.write(original)
        # The whole point: prove the round trip before the original is gone.
        with gzip.open(tmp, "rb") as fh:
            if fh.read() != original:
                tmp.unlink(missing_ok=True)
                return False, "round-trip MISMATCH — original untouched"
        before, after = len(original), tmp.stat().st_size
        os.replace(tmp, path)
        return True, f"{before/1e6:.1f} MB -> {after/1e6:.1f} MB ({before/after:.1f}x)"
    except Exception as exc:  # noqa: BLE001 — never let one file stop the sweep
        tmp.unlink(missing_ok=True)
        return False, f"{type(exc).__name__}: {exc} — original untouched"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="report only, change nothing")
    g.add_argument("--day", help="convert one day directory, e.g. 2026-08-06")
    g.add_argument("--all", action="store_true", help="convert every day")
    args = ap.parse_args(argv)

    if not HIST.exists():
        print(f"no hist tree at {HIST}", file=sys.stderr)
        return 2

    scope = sorted((HIST / args.day).glob("*.gz")) if args.day else sorted(HIST.rglob("*.gz"))
    if args.day and not (HIST / args.day).is_dir():
        print(f"no such day: {args.day}", file=sys.stderr)
        return 2

    plain = [p for p in scope if is_plain_json(p)]
    total = sum(p.stat().st_size for p in plain)
    print(f"{len(scope)} file(s) named .gz in scope; "
          f"{len(plain)} are plain JSON ({total/1e9:.2f} GB)")

    if args.check or not plain:
        return 0

    ok = failed = 0
    saved = 0
    for p in plain:
        before = p.stat().st_size
        good, msg = convert(p)
        if good:
            ok += 1
            saved += before - p.stat().st_size
            print(f"  OK   {p.parent.name}/{p.name}  {msg}", flush=True)
        else:
            failed += 1
            print(f"  FAIL {p.parent.name}/{p.name}  {msg}", file=sys.stderr, flush=True)

    print(f"\nconverted {ok}, failed {failed}, reclaimed {saved/1e9:.2f} GB")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
