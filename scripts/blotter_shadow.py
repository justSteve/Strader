#!/usr/bin/env python3
"""Blotter shadow — run the registered rules on today's live record, at real time. [st-uaxf]

WHAT
    Hand-run for the session (no systemd unit until a week of clean compares —
    the 08-23 feeder crash, st-wnuk, is why the unit is earned). Waits for
    each rule's fire minute to close on the wall clock, builds the lens state
    from the live corpus files as they stand (read-only; the Databento
    capture owns the feed), calls the rules, records the close-watch Schwab
    snapshot as the entry, and after the close prices every call with the
    replay's own code and writes ``shadow-<day>.jsonl`` beside a journal
    ``shadow-<day>.log.jsonl`` under data/measurement/blotter/. See
    strader/blotter/shadow.py.

    ``--compare`` replays the day afterwards and holds it against the shadow
    rows: rule id, fire minute, call, entry minute and contract must match.
    Exit 0 when clean, 1 when not, naming the row and the key.

RUN
    .venv/bin/python3 scripts/blotter_shadow.py                 # today, wait for 14:45, close at 15:00
    .venv/bin/python3 scripts/blotter_shadow.py --day 2026-09-11 --compare
    nohup .venv/bin/python3 scripts/blotter_shadow.py >> /var/moo/logs/blotter-shadow-$(date +%F).log 2>&1 &

    Started after the close, it prices at once from the finished files — a
    dry run of the close phase. Started before the fire minute, it waits.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strader.blotter import shadow as S                  # noqa: E402
from strader.blotter.rules import load_rules             # noqa: E402
from strader.blotter.state import DEFAULT_CORPUS, DEFAULT_PARSED  # noqa: E402
from strader.marks.estimated import Calibration          # noqa: E402

DEFAULT_CALIBRATION = ROOT / "data" / "measurement" / "estimated-mark-calibration-2026-09-11.json"
DEFAULT_OUT_DIR = ROOT / "data" / "measurement" / "blotter"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", default=None, help="YYYY-MM-DD; default today, Central time")
    ap.add_argument("--rule", action="append", help="rule id (repeatable); default every registered rule")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--parsed", type=Path, default=DEFAULT_PARSED)
    ap.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--no-events", action="store_true")
    ap.add_argument("--compare", action="store_true", help="replay the day and compare with the shadow rows")
    args = ap.parse_args(argv)

    day = args.day or datetime.now(S.CT).strftime("%Y-%m-%d")
    rules = load_rules()
    if args.rule:
        rules = [r for r in rules if r.id in set(args.rule)]
    cal = Calibration.load(args.calibration) if args.calibration.is_file() else None
    if cal is None:
        print(f"calibration {args.calibration} not found; estimated rows will be unpriced", file=sys.stderr)

    if args.compare:
        side = S.read_journal(args.out_dir, day)
        if side is None:
            print(f"no closed shadow journal for {day} at {S.shadow_log_path(args.out_dir, day)} "
                  f"— the day was not shadowed to its close, nothing to compare", file=sys.stderr)
            return 2
        rows, fires = side
        out = S.compare(day, rows, rules, corpus=args.corpus, parsed=args.parsed, cal=cal, shadow_fires=fires)
        print(json.dumps(out, indent=1, sort_keys=True))
        print(f"{day}: {'CLEAN' if out['clean'] else 'MISMATCH'} — {out['n_fires']} answers held, "
              f"{out['n_shadow']} shadow rows, {out['n_replay']} replay rows")
        return 0 if out["clean"] else 1

    print(f"shadowing {day} with {[r.id for r in rules]}; fire minutes {sorted({t for r in rules for t in r.fire_at})} CT", flush=True)
    rep = S.run_shadow(day, rules, corpus=args.corpus, parsed=args.parsed, cal=cal, out_dir=args.out_dir,
                       events=not args.no_events)
    for j in rep.journal:
        print(json.dumps(j, sort_keys=True), flush=True)
    print(f"{day}: {len(rep.rows)} shadow rows, {len(rep.unpriced)} unpriced, "
          f"{sum(1 for f in rep.fires if f['call'])} calls of {len(rep.fires)} -> {S.shadow_rows_path(args.out_dir, day)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
