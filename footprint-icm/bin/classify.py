#!/usr/bin/env python3
"""Stage 20 — the model labels what the scorer saw, bounded to its folder. [st-h0xx]

For each delivered wake, and once for the whole cash-session window, this
assembles the model's entire input from files in the run folder — the
generated excerpts (SOURCES) and the event slice (EVENTS) — copies
``20-classify/prompt.md`` beside it, calls ``run_stage.sh`` (no tools, no
settings, parent scan) and runs the checker over the output. A checker
failure stops the run: the folder is not bounding the model, and nothing
downstream is worth reading.

Per-wake runs see ONLY the alert lines the watch had delivered up to that
wake (the slice stage 10 wrote), so a disagreement with the live analyst is
not hindsight — in time or in content. The window run sees every cash-session
EVENT line, alerts and notes, and is coverage: the labels for the minutes the
live analyst was never shown.

Writes ``<run>/20-classify/<wake-HHMM|window>/{prompt.md,input.txt,output.md,
usage.json,check.json}`` and the ``classify`` section of ``run.json`` with the
calls, tokens and list-price cost.

Usage: classify.py <YYYY-MM-DD> [--only window|wake-HHMM] [--model MODEL]
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

PROMPT = LANE / "20-classify" / "prompt.md"
# ICM_RUN_STAGE is a test seam: a script that writes output.md and usage.json
# without calling a model.
RUN_STAGE = Path(os.environ.get("ICM_RUN_STAGE", HERE / "run_stage.sh"))


def sources_text(ctx: Path) -> str:
    idx = read_json(ctx / "index.json")
    parts = [(ctx / r["file"]).read_text(encoding="utf-8").rstrip() for r in idx["rows"]]
    return "\n\n".join(parts) + "\n"


def assemble(day: _date, slice_name: str, slice_text: str, sources: str) -> str:
    what = ("every cash-session EVENT line, alerts and notes" if slice_name == "window"
            else f"the alert lines the watch had delivered to the live analyst up to "
                 f"{slice_name[5:7]}:{slice_name[7:9]}, each with the graded bar it carried")
    return (f"# Footprint audit lane — classify — {day.isoformat()} — {slice_name}\n\n"
            f"EVENTS below are {what}. Times are Central. SOURCES are the only material a "
            f"label may rest on.\n\n"
            f"## SOURCES\n\n{sources}\n"
            f"## EVENTS\n\n{slice_text.rstrip()}\n\n"
            f"## ANSWER\n\nWrite the LABEL and IMPLICATION lines now.\n")


def call_stage(stage_dir: Path, model: str | None) -> dict:
    env = {**os.environ}
    if model:
        env["ICM_MODEL"] = model
    proc = subprocess.run(["bash", str(RUN_STAGE), str(stage_dir)], capture_output=True,
                          text=True, env=env, timeout=900)
    if proc.returncode != 0:
        raise LaneError(f"run_stage.sh rc={proc.returncode} for {stage_dir.name}: "
                        f"{(proc.stderr or proc.stdout).strip()[-400:]}")
    log.info(proc.stdout.strip())
    usage = read_json(stage_dir / "usage.json")
    u = usage.get("usage") or {}
    return {"cost_usd_list": usage.get("total_cost_usd"), "duration_ms": usage.get("duration_ms"),
            "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
            "cache_read": u.get("cache_read_input_tokens"),
            "cache_write": u.get("cache_creation_input_tokens"),
            "models": sorted((usage.get("modelUsage") or {}).keys())}


def run_slice(day: _date, name: str, slice_path: Path, model: str | None) -> dict:
    rd = run_dir(day, create=False)
    ctx = rd / "20-classify" / "context"
    strays = excerpts.verify(rd)
    if strays:
        raise LaneError(f"context/ is not what excerpts.py generated: {strays}")
    stage = rd / "20-classify" / name
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROMPT, stage / "prompt.md")
    (stage / "input.txt").write_text(
        assemble(day, name, slice_path.read_text(encoding="utf-8"), sources_text(ctx)),
        encoding="utf-8")
    meter = call_stage(stage, model)
    verdict = checker.check_lines((stage / "output.md").read_text(encoding="utf-8").splitlines(),
                                  checker.load_context(ctx))
    (stage / "check.json").write_text(json.dumps(verdict, indent=1) + "\n", encoding="utf-8")
    rec = {"slice": name, "input_chars": len((stage / "input.txt").read_text()),
           "labels": verdict["counts"]["LABEL"], "implications": verdict["counts"]["IMPLICATION"],
           "unsourced": verdict["unsourced"], "ok": verdict["ok"],
           "failures": len(verdict["failures"]), **meter}
    if not verdict["ok"]:
        for f in verdict["failures"]:
            log.error("[FAIL] %s line %d: %s — %s", name, f["line_no"], f["reason"], f["line"])
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("day", type=_date.fromisoformat)
    ap.add_argument("--only", help="run one slice: window or wake-HHMM")
    ap.add_argument("--model", help="override the model (default run_stage.sh's, claude-opus-5)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    day: _date = args.day
    rd = run_dir(day, create=False)
    tr = rd / "10-transcribe"
    if not (tr / "window.txt").exists():
        raise LaneError(f"no {tr}/window.txt — run render_events.py first")
    if not PROMPT.exists():
        raise LaneError(f"no prompt at {PROMPT}")
    slices = sorted(p for p in tr.glob("wake-*.txt")) + [tr / "window.txt"]
    if args.only:
        slices = [p for p in slices if p.stem == args.only]
        if not slices:
            raise LaneError(f"no slice named {args.only}")
    results = []
    t0 = datetime.now(CT)
    for p in slices:
        results.append(run_slice(day, p.stem, p, args.model))
    rec = {"produced_at": datetime.now(CT).isoformat(timespec="seconds"),
           "prompt": str(PROMPT), "calls": len(results),
           "cost_usd_list": round(sum(r["cost_usd_list"] or 0 for r in results), 4),
           "seconds": round((datetime.now(CT) - t0).total_seconds(), 1),
           "output_tokens": sum(r["output_tokens"] or 0 for r in results),
           "labels": sum(r["labels"] for r in results),
           "implications": sum(r["implications"] for r in results),
           "unsourced": sum(r["unsourced"] for r in results),
           "all_ok": all(r["ok"] for r in results), "slices": results}
    update_run_json(day, "classify", rec)
    bad = [r["slice"] for r in results if not r["ok"]]
    print(f"20-classify {day}: {rec['calls']} call(s), {rec['labels']} labels, "
          f"{rec['implications']} implications, {rec['unsourced']} unsourced, "
          f"${rec['cost_usd_list']:.3f} list, {rec['seconds']} s"
          + (f"; CHECKER FAILED on {bad}" if bad else "; checker passed"))
    if bad:
        raise LaneError(f"checker failed on {bad} — the folder is not bounding the model")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaneError as e:
        print(f"[REFUSED] 20-classify: {e}", file=sys.stderr)
        raise SystemExit(2)
