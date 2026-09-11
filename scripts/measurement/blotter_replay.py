#!/usr/bin/env python3
"""Blotter replay — score the registered rules as trades over the corpus. [st-uc23]

WHY
    A pre-registered rule was scored as a direction call (final_hour_lens.py,
    final_hour_combo.py, 2026-08-29). The brief's ruling is to re-score AS
    TRADES: one row per call, the declared exit resolved on the instrument's
    own marks, the stop x target grid beside it, P&L in premium points and
    dollars — split by mark path, never pooled.

WHAT
    For every day in --from..--to with an ES file: the lens state at each
    rule's fire minute (data before T only), the rule's call, the ~10-ITM
    0DTE single priced from its prints (or from the 14:45 Schwab ask plus the
    ES->premium proxy on OPRA-less days; see strader/blotter/legs.py), the
    row written to data/measurement/blotter/replay-<day>.jsonl. A run
    manifest (replay-run-<from>-<to>.json) records every day, skip, call and
    unpriced call. --doc renders the aggregate write-up.

    Byte-identical across runs with unchanged code and files: days sorted,
    ordered pool, sorted keys, no clock.

RUN
    .venv/bin/python3 scripts/measurement/blotter_replay.py --from 2025-05-27 --to 2026-08-31 \\
        --doc docs/measurement/blotter-replay-<date>.md --as-of <date> --workers 6
    .venv/bin/python3 scripts/measurement/blotter_replay.py --from 2026-08-28 --rule launch-into-no-lid-1445

    --calibration defaults to the operative estimated-mark calibration named
    below; pass --no-estimated to price from prints only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strader.blotter import replay as R          # noqa: E402
from strader.blotter.report import render_markdown  # noqa: E402
from strader.blotter.rules import load_rules     # noqa: E402
from strader.blotter.state import DEFAULT_CORPUS, DEFAULT_PARSED  # noqa: E402

#: The operative estimated-mark calibration (all corpus days through
#: 2026-08-14, fitted 2026-09-11). Regenerate with estimated_mark_calibrate.py.
DEFAULT_CALIBRATION = ROOT / "data" / "measurement" / "estimated-mark-calibration-2026-09-11.json"
DEFAULT_OUT_DIR = ROOT / "data" / "measurement" / "blotter"
ESTIMATED_MARK_DOC = "docs/measurement/estimated-mark-path-2026-09-11.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="day_from", required=True, metavar="YYYY-MM-DD")
    ap.add_argument("--to", dest="day_to", metavar="YYYY-MM-DD", help="defaults to --from")
    ap.add_argument("--rule", action="append", help="rule id (repeatable); default every registered rule")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--parsed", type=Path, default=DEFAULT_PARSED, help="parsed Mancini letters root")
    ap.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    ap.add_argument("--no-estimated", action="store_true", help="price from prints only; no proxy rows")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--no-events", action="store_true", help="skip the tape emissions on each row")
    ap.add_argument("--doc", type=Path, help="write the aggregate write-up here (Markdown)")
    ap.add_argument("--as-of", default=None, help="the date named in the write-up (no clock is read)")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--stdout", action="store_true", help="also print every row as JSON")
    args = ap.parse_args(argv)

    day_to = args.day_to or args.day_from
    rules = load_rules()
    if args.rule:
        wanted = set(args.rule)
        unknown = wanted - {r.id for r in rules}
        if unknown:
            ap.error(f"unknown rule id(s): {sorted(unknown)}; registered: {[r.id for r in rules]}")
        rules = [r for r in rules if r.id in wanted]
    cal_path = None if args.no_estimated else args.calibration
    if cal_path is not None and not cal_path.is_file():
        ap.error(f"calibration {cal_path} not found; run estimated_mark_calibrate.py or pass --no-estimated")
    days = R.corpus_days_in(args.corpus, args.day_from, day_to)
    if not days:
        print(f"no corpus days with an ES file in {args.day_from}..{day_to} under {args.corpus}", file=sys.stderr)
        return 1
    reports = R.replay_range(days, rule_ids=[r.id for r in rules], corpus=args.corpus, parsed=args.parsed,
                             cal_path=cal_path, events=not args.no_events, workers=args.workers)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    written = 0
    for rep in reports:
        if R.write_day_rows(args.out_dir, rep):
            written += 1
        rows.extend(rep.rows)
        if args.stdout:
            for r in rep.rows:
                print(json.dumps(r, sort_keys=True))
    manifest = {
        "range": [args.day_from, day_to], "corpus": str(args.corpus), "parsed": str(args.parsed),
        "calibration": str(cal_path) if cal_path else None, "events": not args.no_events,
        "rules": [{"id": r.id, "registered": r.registered, "fire_at": list(r.fire_at),
                   "exit": r.exit.to_dict(), "instrument": r.instrument} for r in rules],
        "days": [{k: v for k, v in rep.to_dict().items() if k != "rows"} | {"n_rows": len(rep.rows)}
                 for rep in reports],
        "n_days": len(reports), "n_rows": len(rows),
        "n_unpriced": sum(len(rep.unpriced) for rep in reports),
    }
    mpath = args.out_dir / f"replay-run-{args.day_from}-{day_to}.json"
    mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if args.doc:
        doc = render_markdown(rows, [rep.to_dict() for rep in reports], as_of=args.as_of or day_to,
                              day_from=args.day_from, day_to=day_to, rules_meta=manifest["rules"],
                              calibration=(str(cal_path.relative_to(ROOT)) if cal_path and cal_path.is_relative_to(ROOT)
                                           else (str(cal_path) if cal_path else None)),
                              estimated_mark_doc=ESTIMATED_MARK_DOC)
        args.doc.parent.mkdir(parents=True, exist_ok=True)
        args.doc.write_text(doc, encoding="utf-8")
    est = sum(1 for r in rows if r["estimated"])
    print(f"{len(reports)} days, {len(rows)} rows ({len(rows) - est} printed, {est} estimated) on {written} days, "
          f"{manifest['n_unpriced']} unpriced calls -> {args.out_dir} (manifest {mpath.name})"
          + (f"; write-up {args.doc}" if args.doc else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
