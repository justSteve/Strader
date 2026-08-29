#!/usr/bin/env python3
"""Stage 10 — the day's events in plain words, by code. [st-h0xx]

Desk's sketch had a model here. The replay record already carries kind,
subtype, signal and a parsed field dictionary, and the 08-24 audit put
numerical accuracy on the scorer's side; a model would add nothing but the
chance to misremember. So this stage is a renderer.

It writes, under ``<run>/10-transcribe/``:

  events.md          every cash-session EVENT as a table, with the kind
                     glossary from the runbook on top
  window.txt         the same lines, raw, for the whole-window classify run
  wake-<HH:MM>.txt   one slice per delivered wake: ONLY the alert lines the
                     watch had delivered up to and including that wake, each
                     with its bar — what the live analyst had been shown, in
                     time and in content (notes never wake anyone)

and renames the three colliding percentile keys as it renders: the scorer
prints session-so-far percentiles under the names the finished-day fields
use (vocabulary review finding 3, rename not landed). ``effort_pct`` and
``effect_pct`` on ABSORPTION-CLUSTER lines and ``pctl`` on CLIMAX lines
become ``effort_pct_dev``, ``effect_pct_dev`` and ``pctl_dev`` here, so the
model never sees a developing number under a hindsight name.

Usage: render_events.py <YYYY-MM-DD>
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import CT, LaneError, read_json, run_dir, update_run_json  # noqa: E402

# docs/playbooks/emitter-two-tier.md "Reading an EVENT line", in plain words.
GLOSSARY = {
    "SUPERLATIVE": "a new session record — most volume, most buying delta, or most selling delta "
                   "in one minute so far; prev= is the record it displaced; rth_min= is minutes "
                   "since the 08:30 open (a record sixty minutes in is a weak claim)",
    "ABSORPTION-CLUSTER": "two or more minutes in a row of heavy effort with almost no price "
                          "movement; START is the alarm, END says how it resolved",
    "CLIMAX": "one minute whose delta ranks at the top of the session so far; the percentile "
              "is against the session up to that minute, never the finished day",
    "PLAN-LEVEL": "price at one of the letter's levels — TOUCH (near it), ACCEPTANCE (closed "
                  "beyond it, twice), REJECTION (went through and came back); through= is how "
                  "far price actually went",
}
RENAME = {
    ("ABSORPTION-CLUSTER", "effort_pct"): "effort_pct_dev",
    ("ABSORPTION-CLUSTER", "effect_pct"): "effect_pct_dev",
    ("CLIMAX", "pctl"): "pctl_dev",
}


def fields_of(rec: dict) -> dict:
    out = {}
    for k, v in (rec.get("fields") or {}).items():
        out[RENAME.get((rec["kind"], k), k)] = v
    return out


def render_line(rec: dict) -> str:
    """The scorer's line with the colliding keys renamed; everything else
    byte for byte."""
    line = rec["line"]
    for (kind, old), new in RENAME.items():
        if rec["kind"] == kind:
            line = line.replace(f"  {old}=", f"  {new}=")
    return line


def table(recs: list[dict]) -> str:
    out = ["| time | kind | subtype | wakes? | fields |", "|---|---|---|---|---|"]
    for r in recs:
        f = "  ".join(f"{k}={v}" for k, v in fields_of(r).items())
        out.append(f"| {r['line'][:5]} | {r['kind']} | {r['subtype']} | "
                   f"{'alert' if r['sig'] == 'alert' else 'note'} | {f} |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("day", type=_date.fromisoformat)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    day: _date = args.day
    rd = run_dir(day, create=False)
    src = rd / "00-inputs/events.rth.jsonl"
    if not src.exists():
        raise LaneError(f"no {src} — run inputs.py first")
    recs = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l]
    out = rd / "10-transcribe"
    out.mkdir(exist_ok=True)

    # The whole window
    md = [f"# Events, cash session {day.isoformat()} (08:30-15:00 CT)\n",
          "One line per event the scorer detected. 'alert' lines wake the live analyst; "
          "'note' lines stay in the log. Percentiles marked _dev are against the session so "
          "far, never the finished day.\n", "## What the kinds mean\n"]
    md += [f"- **{k}** — {v}" for k, v in GLOSSARY.items()]
    md += ["", f"## The {len(recs)} events\n", table(recs), ""]
    (out / "events.md").write_text("\n".join(md), encoding="utf-8")
    (out / "window.txt").write_text("".join(render_line(r) + "\n" for r in recs), encoding="utf-8")

    # Per-wake slices: the delivered alerts up to and including each wake.
    slices = []
    sess = rd / "live-lane/session.json"
    derived = []
    if sess.exists():
        for s in (read_json(sess).get("sessions") or []):
            derived = (s.get("derived") or {}).get("wakes") or []
            break
    shown: list[str] = []
    for w in derived:
        for ln in w["lines"]:
            rec = next((r for r in recs if r["line"].rstrip() == ln.rstrip()), None)
            shown.append(render_line(rec) if rec else ln)
        if w.get("bar"):
            shown.append(f"bar: {w['bar']}")
        name = f"wake-{w['minute'].replace(':', '')}.txt"
        (out / name).write_text("\n".join(shown) + "\n", encoding="utf-8")
        slices.append({"wake": w["minute"], "file": name, "lines": len(shown)})

    rec = {"produced_at": datetime.now(CT).isoformat(timespec="seconds"),
           "window_events": len(recs), "window_alerts": sum(1 for r in recs if r["sig"] == "alert"),
           "slices": slices,
           "renamed_keys": sorted({f"{k}->{v}" for (_, k), v in RENAME.items()})}
    update_run_json(day, "render", rec)
    print(f"10-transcribe {day}: {len(recs)} events ({rec['window_alerts']} alerts) in the window; "
          f"{len(slices)} wake slice(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaneError as e:
        print(f"[REFUSED] 10-transcribe: {e}", file=sys.stderr)
        raise SystemExit(2)
