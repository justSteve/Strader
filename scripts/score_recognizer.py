#!/usr/bin/env python3
"""Score the SetupRecognizer against Mancini's ground-truth labels. [st-3vu]

For every labeled session with tick data on disk: anchor the recognizer with
ONLY that day's Mancini levels, replay the bars, and match machine
confirmations to his labels. Match tiers:
  EXACT  — same setup type at a labeled level, |Δt| ≤ 15 min of his timestamp
  FAMILY — confirmed at a labeled level within 30 min but the FBD/reclaim
           sibling of his label (his own letters re-label events across the
           pair, e.g. the 2025-07-22 6323 event)
  LEVEL  — confirmed at a labeled level, but >30 min from his timestamp
  MISS   — no confirmation at any labeled level
  N/A    — label untimed or outside RTH tick coverage

Reruns as the corpus grows; never pulls data (spend stays human-approved).

Usage:  .venv/bin/python scripts/score_recognizer.py
        .venv/bin/python scripts/score_recognizer.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date as _date, time as _time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.orderflow.bars import build_bars                     # noqa: E402
from market.orderflow.recognizer import Anchor, SetupRecognizer  # noqa: E402
from market.orderflow.replay import read_corpus_day, has_es_day  # noqa: E402

logger = logging.getLogger("score_recognizer")

LABELS = REPO_ROOT / "docs/measurement/mancini-setup-labels-2026-07-06.json"
FAMILY = {"failed_breakdown", "level_reclaim"}


def label_minutes_ct(time_et: str | None) -> int | None:
    """Mancini writes ET; corpus clocks are CT (ET − 1h). RTH only."""
    if not time_et:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(AM|PM)", time_et)
    if not m:
        return None
    h, mn, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    h24 = (h % 12) + (12 if ap == "PM" else 0)
    ct = h24 * 60 + mn - 60
    return ct if (8 * 60 + 30) <= ct <= (15 * 60) else None


def score_day(day: _date, labels: list[dict]) -> dict:
    trades = read_corpus_day(day)
    if trades[0].ts.hour >= 9:
        return {"day": day.isoformat(), "verdict": "N/A", "why": "afternoon-only coverage"}
    bars = list(build_bars(trades, n=2000, include_partial=True))
    levels = sorted({float(lv) for e in labels for lv in e["es_levels"] if 5000 < lv < 9000})
    if not levels:
        return {"day": day.isoformat(), "verdict": "N/A", "why": "no labeled level"}
    recs = SetupRecognizer([Anchor(lv, "support", "mancini", mancini=True) for lv in levels]).run(bars)
    confirmed = [r for r in recs if r.state == "confirmed"]

    best = {"verdict": "MISS", "detail": f"{len(confirmed)} confirmations, none at a labeled event"}
    rank = {"EXACT": 3, "FAMILY": 2, "LEVEL": 1, "MISS": 0}
    for e in labels:
        t_ct = label_minutes_ct(e.get("time_et"))
        for r in confirmed:
            if not any(abs(r.anchor_price - lv) <= 2.0 for lv in e["es_levels"]):
                continue
            r_min = r.timestamp.hour * 60 + r.timestamp.minute
            dt = abs(r_min - t_ct) if t_ct is not None else None
            same = r.setup == e["setup"]
            if dt is not None and dt <= 15 and same:
                v = "EXACT"
            elif dt is not None and dt <= 30 and r.setup in FAMILY and e["setup"] in FAMILY:
                v = "FAMILY"
            else:
                v = "LEVEL"
            if rank[v] > rank[best["verdict"]]:
                best = {"verdict": v,
                        "detail": (f"{r.setup} confirmed {r.timestamp.strftime('%H:%M CT')} @ "
                                   f"{r.anchor_price:g} vs label {e['setup']} {e.get('time_et')} ET"
                                   + (f" (Δ {dt} min)" if dt is not None else ""))}
    best["day"] = day.isoformat()
    best["n_confirmed"] = len(confirmed)
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="Recognizer vs Mancini labels [st-3vu]")
    ap.add_argument("--json", help="Write full results JSON here")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    by_day: dict[str, list[dict]] = {}
    for e in json.loads(LABELS.read_text()):
        if e["setup"] in FAMILY and e["es_levels"]:
            by_day.setdefault(e["session_date"], []).append(e)

    results = []
    for day_s in sorted(by_day):
        day = _date.fromisoformat(day_s)
        if not has_es_day(day):
            continue
        try:
            results.append(score_day(day, by_day[day_s]))
        except Exception as exc:  # a bad day must not sink the sweep
            logger.error("%s failed: %s", day_s, exc)
            results.append({"day": day_s, "verdict": "ERROR", "detail": str(exc)})

    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        print(f"{r['day']}  {r['verdict']:<7} {r.get('detail', r.get('why', ''))}")
    testable = sum(v for k, v in counts.items() if k in ("EXACT", "FAMILY", "LEVEL", "MISS"))
    print(f"\n{counts} | agreement (EXACT+FAMILY) "
          f"{counts.get('EXACT', 0) + counts.get('FAMILY', 0)}/{testable} testable days"
          f" — small-N: treat as directional until n grows")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
