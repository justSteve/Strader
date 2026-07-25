#!/usr/bin/env python3
"""Corpus day browser — every recorded ES day's price action in one tab. [st-vrs]

Scans data/corpus/ for days with an ES trades file, builds 1-minute candles for
each through the canonical reader (same dedup/sort as the drills), and renders
ONE self-contained HTML page that cycles day-by-day with arrow keys. Purpose:
pinpoint days worth replaying (st-055) — each day is badged with its coverage
window, range, contracts, TPO day-type, and whether MBP-1 book data exists
(= full-precision replay incl. absorption).

Read-only over the corpus; writes only the output HTML.

Usage:
    .venv/bin/python scripts/day_browser.py                    # all corpus days
    .venv/bin/python scripts/day_browser.py --since 2026-07-01
    .venv/bin/python scripts/day_browser.py --no-open -v
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date, time as _time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.replay import read_corpus_day            # noqa: E402
from market.orderflow.tpo import build_tpo, classify_day_type  # noqa: E402
from scripts.orderflow_drill import minute_candles, open_in_browser  # noqa: E402

logger = logging.getLogger("day_browser")

CORPUS = Path(__file__).resolve().parent.parent / "data" / "corpus"
TEMPLATE = Path(__file__).parent / "day_browser_template.html"
ES_FILE = "databento_glbx_es.jsonl"
MBP1_FILE = "databento_glbx_es_mbp1.jsonl"


def day_entry(es_path: Path) -> dict:
    """One corpus ES file -> browser payload entry (candles + stats)."""
    trades = read_corpus_day(es_path)
    if not trades:
        raise ValueError(f"{es_path} parsed to zero trades")
    candles = minute_candles(trades)
    first, last = trades[0].ts, trades[-1].ts
    full_rth = first.time() <= _time(8, 35) and last.time() >= _time(14, 55)
    try:
        day_type, why = classify_day_type(build_tpo(trades))
    except Exception as exc:  # stats must not sink the page
        day_type, why = "?", f"classify failed: {exc}"
    return {
        "date": first.date().isoformat(),
        "candles": candles,
        "o": trades[0].price,
        "h": max(t.price for t in trades),
        "l": min(t.price for t in trades),
        "c": trades[-1].price,
        "contracts": sum(t.size for t in trades),
        "n_trades": len(trades),
        "window": f"{first.strftime('%H:%M')}-{last.strftime('%H:%M')} CT",
        "full_rth": full_rth,
        "day_type": day_type,
        "why": why,
        "mbp1": (es_path.parent / MBP1_FILE).exists(),
    }


def build_payload(since: _date | None = None, root: Path = CORPUS) -> dict:
    days: list[dict] = []
    paths = sorted(root.glob(f"*/{ES_FILE}"))
    for i, p in enumerate(paths, 1):
        try:
            day = _date.fromisoformat(p.parent.name)
        except ValueError:
            logger.warning("skipping non-date corpus dir %s", p.parent.name)
            continue
        if since and day < since:
            continue
        try:
            days.append(day_entry(p))
        except Exception as exc:  # a bad day must not sink the sweep
            logger.warning("%s failed (%s) — skipped", day, exc)
        if i % 10 == 0:
            logger.info("scanned %d/%d corpus dirs", i, len(paths))
    days.sort(key=lambda d: d["date"])
    return {"days": days}


def render(payload: dict, out_path: Path) -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    marker = "/*__BROWSER_DATA__*/null"
    if marker not in template:
        raise SystemExit(f"template {TEMPLATE} missing data marker")
    out_path.write_text(template.replace(marker, json.dumps(payload, separators=(",", ":"))),
                        encoding="utf-8")
    logger.info("wrote %s (%.1f MB)", out_path, out_path.stat().st_size / 1048576)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Corpus day browser [st-vrs]")
    ap.add_argument("--since", help="Only days >= YYYY-MM-DD (default: all)")
    ap.add_argument("--out", help="Output HTML (default /tmp/desk-day-browser.html)")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    since = _date.fromisoformat(args.since) if args.since else None
    payload = build_payload(since=since)
    if not payload["days"]:
        print("no corpus days found", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else Path("/tmp/desk-day-browser.html")
    render(payload, out)
    if not args.no_open:
        open_in_browser(out)
    n_full = sum(1 for d in payload["days"] if d["full_rth"])
    n_mbp = sum(1 for d in payload["days"] if d["mbp1"])
    print(f"day browser ready: {out}  ({len(payload['days'])} days, "
          f"{n_full} full-RTH, {n_mbp} with MBP-1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
