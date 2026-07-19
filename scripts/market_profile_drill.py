#!/usr/bin/env python3
"""Market Profile drill generator — TPO reading reps on real corpus days. [st-3zh]

Turns one corpus day of ES trades into a self-contained interactive HTML
drill: the session's TPO profile builds bracket by bracket (A, B, C, ...)
and the trainee makes mid-flight reads — day-type calls, POC calls,
single-print flags, Initial Balance checks — scored against the computed
truth and logged in-page (localStorage + JSON export).

Same replay-exact stance as the orderflow drill: trades come from
read_corpus_day, so the profile is built from the canonical stream.
Deterministic: same day = same drill.

Usage:
    .venv/bin/python scripts/market_profile_drill.py --date 2026-07-02
    .venv/bin/python scripts/market_profile_drill.py --date 2026-07-02 \\
        --day-type P --out /tmp/my-mp-drill.html --no-open
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.replay import read_corpus_day                    # noqa: E402
from market.orderflow.tpo import (                                     # noqa: E402
    RTH_END,
    RTH_START,
    TPO_ROW_TICKS,
    build_tpo,
    classify_day_type,
    initial_balance,
    poc_row,
    single_print_rows,
    value_area,
)
from market.signals.orderflow_config import TICK                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orderflow_drill import open_in_browser                            # noqa: E402

logger = logging.getLogger("market_profile_drill")

TEMPLATE = Path(__file__).parent / "market_profile_drill_template.html"
MARKER = "/*__MP_DRILL_DATA__*/null"
CHECKPOINTS = ["C", "F", "I", "M"]      # ~10:00 / 11:30 / 13:00 CT / close


def payload_for(day: _date, day_type: str | None = None) -> dict:
    trades = read_corpus_day(day)
    profile = build_tpo(trades)
    n = len(profile.brackets)
    logger.info("%s: %d trades -> %d brackets, %d rows (%.2f-pt)",
                day, len(trades), n, len(profile.prices), profile.row_pts)

    snapshots = []
    for k in range(1, n + 1):
        counts = profile.counts(k)
        printed = [i for i, c in enumerate(counts) if c > 0]
        val, vah = value_area(profile, k)
        snapshots.append({
            "poc": poc_row(profile, k), "vah": vah, "val": val,
            "singles": single_print_rows(profile, k),
            "hi": printed[-1], "lo": printed[0],
        })

    # volume twin — same rows, contracts instead of letters (doc 03's
    # "time is not volume" contrast). Lower-price tie-break, matching the
    # VolumeProfile convention.
    lo_key = int(profile.prices[0] // profile.row_pts)
    vols = [0] * len(profile.prices)
    for t in trades:
        tt = t.ts.time()
        if RTH_START <= tt < RTH_END:
            i = int(t.price // profile.row_pts) - lo_key
            if 0 <= i < len(vols):
                vols[i] += t.size
    vpoc = max(range(len(vols)), key=lambda i: (vols[i], -i))

    truth_label, truth_why = classify_day_type(profile)
    if day_type and day_type != truth_label:
        logger.info("day-type override: heuristic said %s, deck says %s",
                    truth_label, day_type)
        truth_label, truth_why = day_type, f"deck label (heuristic read: {truth_why})"

    ib = initial_balance(profile)
    have = {b.letter for b in profile.brackets}
    last = profile.brackets[-1].letter
    checkpoints = [c for c in CHECKPOINTS if c in have and c != last] + [last]

    return {
        "meta": {
            "symbol": profile.symbol or "ES.c.0",
            "date": day.isoformat(),
            "row_pts": profile.row_pts,
            "n_brackets": n,
            "tick": TICK,
        },
        "rows": list(profile.prices),
        "brackets": [{
            "letter": b.letter,
            "t0": b.start_ts.isoformat(), "t1": b.end_ts.isoformat(),
            "touched": list(b.row_indices),
            "close": b.close,
        } for b in profile.brackets],
        "snapshots": snapshots,
        "ib": {"low": ib[0], "high": ib[1]} if ib else None,
        "volume": vols,
        "vpoc": vpoc,
        "checkpoints": checkpoints,
        "truth": {"day_type": truth_label, "why": truth_why},
    }


def render(payload: dict, out_path: Path) -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    if MARKER not in template:
        raise SystemExit(f"template {TEMPLATE} missing data marker")
    out_path.write_text(template.replace(MARKER, json.dumps(payload, separators=(",", ":"))),
                        encoding="utf-8")
    logger.info("wrote %s (%.1f KB)", out_path, out_path.stat().st_size / 1024)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a Market Profile TPO drill [st-3zh]")
    ap.add_argument("--date", required=True, help="Corpus day YYYY-MM-DD")
    ap.add_argument("--day-type", choices=["D", "P", "b", "trend"],
                    help="Hand-reviewed deck label (overrides the heuristic)")
    ap.add_argument("--out", help="Output HTML path (default /tmp/desk-mp-drill-<date>.html)")
    ap.add_argument("--no-open", action="store_true", help="Skip auto-opening the browser")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date)
    out = Path(args.out) if args.out else Path(f"/tmp/desk-mp-drill-{day.isoformat()}.html")
    payload = payload_for(day, day_type=args.day_type)
    render(payload, out)
    if not args.no_open:
        open_in_browser(out)
    print(f"drill ready: {out}  ({payload['meta']['n_brackets']} brackets, "
          f"{len(payload['rows'])} rows, checkpoints {','.join(payload['checkpoints'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
