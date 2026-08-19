#!/usr/bin/env python3
"""Regenerate the orderflow parity snapshot — deliberately. [st-bw9]

The parity test (tests/market/orderflow/test_parity_harness.py) fails when
ANY engine change alters the full-stack signal sequence over the committed
fixture. That is the point. When the change is intentional, regenerate:

    .venv/bin/python scripts/regen_parity_snapshot.py \\
        --reason "sweep window widened to 400ms per st-XXXX"

which rewrites the snapshot AND appends the reason to the CHANGES log.
Commit snapshot + CHANGES + the motivating code change together — one
commit, reviewable as a unit. Refusing to run without --reason is the
protocol, not an inconvenience.

Interpreting a parity failure: see tests/market/fixtures/parity/README.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.orderflow.parity import absorption_parity_run, parity_run  # noqa: E402
from market.orderflow.quotes import read_mbp1_day       # noqa: E402
from market.orderflow.replay import read_corpus_day     # noqa: E402

FIXTURE = REPO_ROOT / "tests/market/fixtures/es_ticks_golden_20260702.jsonl"
MBP1_FIXTURE = REPO_ROOT / "tests/market/fixtures/es_mbp1_golden_20260702.jsonl.gz"
PARITY_DIR = REPO_ROOT / "tests/market/fixtures/parity"
SNAPSHOT = PARITY_DIR / "expected_signals_20260702.json"
ABSORPTION_SNAPSHOT = PARITY_DIR / "expected_absorption_20260702.json"
CHANGES = PARITY_DIR / "CHANGES.md"


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate parity snapshot [st-bw9]")
    ap.add_argument("--reason", required=True,
                    help="Why the snapshot legitimately changed (goes in CHANGES.md)")
    args = ap.parse_args()

    events = parity_run(read_corpus_day(FIXTURE))
    PARITY_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(events, indent=1) + "\n", encoding="utf-8")

    reads = absorption_parity_run(read_mbp1_day(MBP1_FIXTURE))
    ABSORPTION_SNAPSHOT.write_text(json.dumps(reads, indent=1) + "\n", encoding="utf-8")

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                          capture_output=True, text=True).stdout.strip() or "unknown"
    stamp = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M CT")   # human-facing: Central
    entry = (f"- **{stamp}** ({len(events)} events + {len(reads)} absorption, "
             f"base {head}): {args.reason}\n")
    if CHANGES.exists():
        CHANGES.write_text(CHANGES.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        CHANGES.write_text("# Parity snapshot change log\n\n"
                           "One entry per deliberate regeneration; commit the entry, the\n"
                           "snapshot, and the motivating change together.\n\n" + entry,
                           encoding="utf-8")
    print(f"snapshot: {len(events)} events -> {SNAPSHOT.relative_to(REPO_ROOT)}")
    print(f"absorption: {len(reads)} reads -> {ABSORPTION_SNAPSHOT.relative_to(REPO_ROOT)}")
    print(f"CHANGES:  {entry.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
