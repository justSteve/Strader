#!/usr/bin/env python3
"""Hindsight annotations for replayed days — append-only. [st-055]

Steve dictates; the agent appends. Each annotation is one JSONL row next to
the day's signal record (data/measurement/replay/annotations_<date>.jsonl),
keyed to CT event time (--time) and/or bar index (--bar). Never rewritten.

Usage:
    .venv/bin/python scripts/replay_annotate.py --date 2026-07-13 \
        --time 09:14 --text "flush into 6212 was the real one"
    .venv/bin/python scripts/replay_annotate.py --date 2026-07-13 --bar 140 \
        --text "chop after lunch, recognizer rightly quiet"
    .venv/bin/python scripts/replay_annotate.py --date 2026-07-13 --list
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.session_record import annotations_path  # noqa: E402


def append_annotation(day: _date, text: str, *, time_ct: str | None = None,
                      bar_i: int | None = None, path: Path | None = None) -> dict:
    if not text.strip():
        raise ValueError("annotation text is empty")
    if time_ct is not None:
        try:
            datetime.strptime(time_ct, "%H:%M")
        except ValueError as e:
            raise ValueError(f"--time must be HH:MM CT ({time_ct!r})") from e
    row = {"type": "Annotation", "date": day.isoformat(),
           "time_ct": time_ct, "bar_i": bar_i, "text": text.strip(),
           "logged_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    p = path or annotations_path(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:  # append-only: "a", never "w"
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    return row


def read_annotations(day: _date, path: Path | None = None) -> list[dict]:
    p = path or annotations_path(day)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]


def _where(r: dict) -> str:
    if r.get("time_ct"):
        return f"{r['time_ct']} CT"
    if r.get("bar_i") is not None:
        return f"bar {r['bar_i']}"
    return "day"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Append a hindsight annotation [st-055]")
    ap.add_argument("--date", required=True, help="Replayed day YYYY-MM-DD")
    ap.add_argument("--text", help="The annotation (required unless --list)")
    ap.add_argument("--time", help="CT event time HH:MM the note refers to")
    ap.add_argument("--bar", type=int, help="Bar index the note refers to")
    ap.add_argument("--list", action="store_true", help="Print the day's annotations")
    args = ap.parse_args(argv)

    day = _date.fromisoformat(args.date)
    if args.list:
        for r in read_annotations(day):
            print(f"[{_where(r)}] {r['text']}")
        return 0
    if not args.text:
        ap.error("--text is required unless --list")
    row = append_annotation(day, args.text, time_ct=args.time, bar_i=args.bar)
    print(f"noted [{_where(row)}] {row['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
