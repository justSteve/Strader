#!/usr/bin/env python3
"""Hindsight review page for a replayed day. [st-055]

Reads the LATEST recorded run (data/measurement/replay/signals_<date>.jsonl)
plus the day's annotations and renders one self-contained HTML page:
day type, every recognition with its stages, emission counts, and Steve's
hindsight notes — the 20/20 record to audit the recognizer against.

Usage:
    .venv/bin/python scripts/replay_review.py --date 2026-07-13
    .venv/bin/python scripts/replay_review.py --date 2026-07-13 --no-open
"""
from __future__ import annotations

import argparse
import html as _html
import logging
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.session_record import (annotations_path,        # noqa: E402
                                             read_latest_run, signals_path)
from scripts.orderflow_drill import open_in_browser                   # noqa: E402
from scripts.replay_annotate import read_annotations                  # noqa: E402

logger = logging.getLogger("replay_review")


def review_payload(rows: list[dict], annotations: list[dict]) -> dict:
    """Latest-run record rows + annotation rows -> one review dict."""
    meta = next((r for r in rows if r.get("type") == "RunMeta"), {})
    day_type = next((r for r in rows if r.get("type") == "DayType"), {})
    events = [r for r in rows if r.get("type") not in ("RunMeta", "DayType")]
    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    recs = [e for e in events if e["type"] == "SetupRecognition"]
    return {"meta": meta, "day_type": day_type, "counts": counts,
            "recognitions": recs,
            "confirmed": [r for r in recs if r.get("state") == "confirmed"],
            "annotations": annotations}


def render_html(p: dict) -> str:
    def esc(x) -> str:
        return _html.escape(str(x))

    def _ann_where(a: dict) -> str:
        if a.get("time_ct"):
            return f"{a['time_ct']} CT"
        if a.get("bar_i") is not None:
            return f"bar {a['bar_i']}"
        return "day"

    meta, dt = p["meta"], p["day_type"]
    rec_rows = "".join(
        f"<tr><td>{esc(r.get('timestamp', ''))[11:19]}</td><td>{esc(r.get('setup', ''))}</td>"
        f"<td>{esc(r.get('bias', ''))}</td><td>{esc(r.get('anchor_price', ''))}</td>"
        f"<td>{esc(r.get('state', ''))}</td>"
        f"<td>{esc(' > '.join(r.get('beats', [])))}</td>"
        f"<td>{esc(r.get('bar_i', ''))}</td></tr>"
        for r in p["recognitions"])
    ann_rows = "".join(
        f"<tr><td>{esc(_ann_where(a))}</td><td>{esc(a.get('text', ''))}</td></tr>"
        for a in p["annotations"])
    count_rows = "".join(f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
                         for k, v in sorted(p["counts"].items()))
    return f"""<!doctype html><meta charset="utf-8">
<title>Replay review {esc(meta.get('date', ''))}</title>
<style>
body{{font:14px/1.5 system-ui;margin:2rem;max-width:70rem}}
table{{border-collapse:collapse;margin:1rem 0;width:100%}}
td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
th{{background:#f2f2f2}} h1,h2{{font-weight:600}}
</style>
<h1>Replay review — {esc(meta.get('date', ''))} <small>(run {esc(meta.get('run', ''))})</small></h1>
<p>Day type: <b>{esc(dt.get('day_type', '?'))}</b> — {esc(dt.get('why', ''))}<br>
{meta.get('n_trades', 0):,} trades · {meta.get('n_bars', 0)} bars · bar N {esc(meta.get('bar_n', ''))}</p>
<h2>Recognitions ({len(p['confirmed'])} confirmed / {len(p['recognitions'])} total)</h2>
<table><tr><th>CT</th><th>setup</th><th>bias</th><th>anchor</th><th>state</th><th>stages</th><th>bar</th></tr>
{rec_rows or '<tr><td colspan=7>none</td></tr>'}</table>
<h2>Hindsight annotations ({len(p['annotations'])})</h2>
<table><tr><th>where</th><th>note</th></tr>
{ann_rows or '<tr><td colspan=2>none yet — scripts/replay_annotate.py</td></tr>'}</table>
<h2>Emission counts (latest run)</h2>
<table><tr><th>type</th><th>count</th></tr>{count_rows or '<tr><td colspan=2>none</td></tr>'}</table>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render the replay review page [st-055]")
    ap.add_argument("--date", required=True, help="Replayed day YYYY-MM-DD")
    ap.add_argument("--out", help="Output HTML (default /tmp/desk-replay-review-<date>.html)")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date)
    spath = signals_path(day)
    if not spath.exists():
        print(f"no record for {day} at {spath} — run scripts/replay_day.py first",
              file=sys.stderr)
        return 1
    payload = review_payload(read_latest_run(spath), read_annotations(day))
    out = Path(args.out) if args.out else Path(f"/tmp/desk-replay-review-{day.isoformat()}.html")
    out.write_text(render_html(payload), encoding="utf-8")
    logger.info("wrote %s", out)
    if not args.no_open:
        open_in_browser(out)
    print(f"review ready: {out}  ({len(payload['confirmed'])} confirmed recognitions, "
          f"{len(payload['annotations'])} annotations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
