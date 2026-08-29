#!/usr/bin/env python3
"""Stage 40, the model half — transcribe the live replies into CLAIM lines. [st-h0xx]

The live lane's words must not reach the classify stage, so they enter here
and only here. The model's input is the SOURCES, the AUDIT LABELS the classify
stage wrote for the delivered wakes, and the REPLIES verbatim. It writes CLAIM
lines; the checker fails the run when a quote is not in the reply word for
word or a because is not in its SOURCE word for word. Code (compare.py) then
assigns the classes — the model transcribes, it does not judge.

Two runs: ``claims`` over the day's real replies, and ``planted`` over
``40-compare/fixtures/withdrawn-phrasing.md`` in place of the replies — the
two sentences the trial exists to catch. Stop condition 1 in run form.

Writes ``<run>/40-compare/{claims,planted}/{prompt.md,input.txt,live.txt,
output.md,usage.json,check.json}`` and the ``claims`` section of ``run.json``.

Usage: claims.py <YYYY-MM-DD> [--only claims|planted] [--model MODEL]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import date as _date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import CT, LANE, LaneError, log, read_json, run_dir, update_run_json  # noqa: E402
import checker  # noqa: E402
import excerpts  # noqa: E402
from classify import RUN_STAGE, call_stage, sources_text  # noqa: E402

PROMPT = LANE / "40-compare" / "prompt.md"
FIXTURE = LANE / "40-compare" / "fixtures" / "withdrawn-phrasing.md"


def audit_labels_text(rd: Path) -> str:
    parts = []
    for d in sorted((rd / "20-classify").glob("wake-*")):
        out = d / "output.md"
        if out.exists():
            minute = f"{d.name[5:7]}:{d.name[7:9]}"
            parts.append(f"### Wake {minute}\n\n{out.read_text(encoding='utf-8').strip()}\n")
    return "\n".join(parts) if parts else "(no audit labels — no delivered wakes)\n"


def replies_text(rd: Path) -> tuple[str, str]:
    """The REPLIES section and the flat live text the checker quotes from."""
    wp = rd / "live-lane" / "wakes.jsonl"
    if not wp.exists():
        return "", ""
    sections, flat = [], []
    for ln in wp.read_text(encoding="utf-8").splitlines():
        if not ln:
            continue
        w = json.loads(ln)
        minute = w["lines"][0][:5] if w["lines"] else "??:??"
        text = (w["reply"].get("text") or "").strip()
        pushes = w["reply"].get("pushes") or []
        body = text or "(no prose reply)"
        for p in pushes:
            body += f"\n\nPush to the trader's phone: {p}"
        sections.append(f"### Wake {minute}\n\n{body}\n")
        flat.append(body)
    return "\n".join(sections), "\n\n".join(flat)


def assemble(day: _date, sources: str, labels: str, replies: str, planted: bool) -> str:
    note = ("REPLIES below are a planted test text, not a real session." if planted else
            "REPLIES below are what the live analyst wrote after each wake, verbatim.")
    return (f"# Footprint audit lane — claims — {day.isoformat()}"
            f"{' — planted fixture' if planted else ''}\n\n{note} Times are Central.\n\n"
            f"## SOURCES\n\n{sources}\n"
            f"## AUDIT LABELS\n\n{labels}\n"
            f"## REPLIES\n\n{replies.rstrip()}\n\n"
            f"## ANSWER\n\nWrite the CLAIM lines now.\n")


def run_one(day: _date, name: str, replies: str, live: str, model: str | None) -> dict:
    rd = run_dir(day, create=False)
    ctx = rd / "20-classify" / "context"
    strays = excerpts.verify(rd)
    if strays:
        raise LaneError(f"context/ is not what excerpts.py generated: {strays}")
    stage = rd / "40-compare" / name
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROMPT, stage / "prompt.md")
    (stage / "live.txt").write_text(live, encoding="utf-8")
    (stage / "input.txt").write_text(
        assemble(day, sources_text(ctx), audit_labels_text(rd), replies, name == "planted"),
        encoding="utf-8")
    meter = call_stage(stage, model)
    verdict = checker.check_lines((stage / "output.md").read_text(encoding="utf-8").splitlines(),
                                  checker.load_context(ctx), live)
    (stage / "check.json").write_text(json.dumps(verdict, indent=1) + "\n", encoding="utf-8")
    if not verdict["ok"]:
        for f in verdict["failures"]:
            log.error("[FAIL] %s line %d: %s — %s", name, f["line_no"], f["reason"], f["line"])
    return {"run": name, "claims": verdict["counts"]["CLAIM"], "unsourced": verdict["unsourced"],
            "ok": verdict["ok"], "failures": len(verdict["failures"]), **meter}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("day", type=_date.fromisoformat)
    ap.add_argument("--only", choices=["claims", "planted"])
    ap.add_argument("--model")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    day: _date = args.day
    rd = run_dir(day, create=False)
    if not (rd / "20-classify" / "context" / "index.json").exists():
        raise LaneError("no context — run excerpts.py first")
    if not PROMPT.exists() or not FIXTURE.exists():
        raise LaneError(f"missing {PROMPT} or {FIXTURE}")
    results = []
    t0 = datetime.now(CT)
    replies, live = replies_text(rd)
    if args.only in (None, "claims"):
        if replies:
            results.append(run_one(day, "claims", replies, live, args.model))
        else:
            log.info("no live replies for %s — claims run skipped (labelling-only day)", day)
    if args.only in (None, "planted"):
        fx = FIXTURE.read_text(encoding="utf-8")
        results.append(run_one(day, "planted", fx, fx, args.model))
    rec = {"produced_at": datetime.now(CT).isoformat(timespec="seconds"), "prompt": str(PROMPT),
           "calls": len(results),
           "cost_usd_list": round(sum(r["cost_usd_list"] or 0 for r in results), 4),
           "seconds": round((datetime.now(CT) - t0).total_seconds(), 1),
           "all_ok": all(r["ok"] for r in results), "runs": results}
    update_run_json(day, "claims", rec)
    bad = [r["run"] for r in results if not r["ok"]]
    print(f"40-claims {day}: {rec['calls']} call(s), "
          + ", ".join(f"{r['run']} {r['claims']} claims/{r['unsourced']} unsourced" for r in results)
          + f", ${rec['cost_usd_list']:.3f} list, {rec['seconds']} s"
          + (f"; CHECKER FAILED on {bad}" if bad else "; checker passed"))
    if bad:
        raise LaneError(f"checker failed on {bad}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaneError as e:
        print(f"[REFUSED] 40-claims: {e}", file=sys.stderr)
        raise SystemExit(2)
