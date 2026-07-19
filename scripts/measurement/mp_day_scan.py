#!/usr/bin/env python3
"""Scan corpus days through the TPO day-type heuristic — deck seeding. [st-3zh]

Prints one line per corpus day: heuristic day type, IB extension, POC
position, longest row. Used to shortlist archetypal days for the MP drill
deck (docs/drills/mp-deck.json); labels are hand-reviewed before a day
enters the deck — the heuristic nominates, it does not ratify.

Usage:
    .venv/bin/python scripts/measurement/mp_day_scan.py                # all days
    .venv/bin/python scripts/measurement/mp_day_scan.py --since 2026-06-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from market.orderflow.replay import es_day_path, read_corpus_day       # noqa: E402
from market.orderflow.tpo import (                                     # noqa: E402
    build_tpo,
    classify_day_type,
    initial_balance,
    poc_row,
)

CORPUS = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"


def scan_day(day: _date) -> str | None:
    try:
        profile = build_tpo(read_corpus_day(day))
    except (FileNotFoundError, ValueError) as e:
        return f"{day}  —  skip ({e.__class__.__name__})"
    n = len(profile.brackets)
    if n < 6:
        return f"{day}  —  skip (only {n} brackets)"
    counts = profile.counts()
    printed = [i for i, c in enumerate(counts) if c > 0]
    lo, hi = printed[0], printed[-1]
    rng_pts = (hi - lo + 1) * profile.row_pts
    poc = poc_row(profile)
    poc_pos = (poc - lo) / max(1, hi - lo)
    ib = initial_balance(profile)
    ext = rng_pts / max(profile.row_pts, (ib[1] - ib[0] + profile.row_pts)) if ib else 0
    label, _ = classify_day_type(profile)
    return (f"{day}  {label:>5}  range {rng_pts:5.1f}p  IBx {ext:4.1f}  "
            f"POC@{poc_pos:4.0%}  longest {max(counts):2d}/{n}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TPO day-type scan over the corpus [st-3zh]")
    ap.add_argument("--since", help="Only days >= YYYY-MM-DD")
    args = ap.parse_args(argv)
    since = _date.fromisoformat(args.since) if args.since else None

    days = []
    if CORPUS.exists():
        for p in sorted(CORPUS.iterdir()):
            try:
                day = _date.fromisoformat(p.name)     # skips _health.jsonl etc.
            except ValueError:
                continue
            if p.is_dir() and es_day_path(day).exists():
                days.append(day)
    tally: dict[str, int] = {}
    for day in days:
        if since and day < since:
            continue
        line = scan_day(day)
        if line:
            print(line)
            if "skip" not in line:
                tally[line.split()[1]] = tally.get(line.split()[1], 0) + 1
    print("\n" + "  ".join(f"{k}:{v}" for k, v in sorted(tally.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
