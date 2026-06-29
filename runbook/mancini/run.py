"""Mancini Runbook pilot CLI. [co-7lyf / co-i10h]

Daily run, end to end:

    datastream gate (#1) -> parse (#2, bounded LLM call) -> validate
      -> on pass: write commentary store + last-good ParseResult + print brief
      -> on fail: alert, keep last-good, exit non-zero (never publish suspect levels)

Usage:
    # From the Strader repo root, with the venv active or via ./.venv/bin/python:
    python -m runbook.mancini.run --file /tmp/mancini-latest.txt
    cat newsletter.txt | python -m runbook.mancini.run --date 2026-06-29
    python -m runbook.mancini.run --file nl.txt --no-gate   # offline / no live feeds

The newsletter text comes from --file or stdin. In production the COO
email-ingress blob is fetched first (infra/azure/email-ingress/scripts/
read-latest.sh) and piped in; wiring that fetch into this CLI is the v2 step.

Requires ANTHROPIC_API_KEY_DIRECT for the live parse (see scripts/lux_vision_probe.py).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as date_cls, datetime, timezone
from pathlib import Path

from . import parse as parse_mod
from . import store as store_mod
from .schema import ParseResult

logger = logging.getLogger("runbook.mancini")

# Last-good full ParseResult lands here, for intraday re-emit and recovery.
PARSED_ROOT = Path(__file__).resolve().parent / "parsed"


def _read_newsletter(file_arg: str | None) -> str:
    if file_arg:
        return Path(file_arg).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("ERROR: provide newsletter text via --file or stdin")


def _resolve_day(date_arg: str | None) -> str:
    if date_arg:
        return date_arg
    try:
        from market.corpus.paths import central_date

        return central_date().isoformat()
    except Exception:
        return date_cls.today().isoformat()


def _run_gate(args, day: str) -> bool:
    """Return True if the Runbook may proceed."""
    if args.no_gate:
        logger.warning("datastream gate SKIPPED (--no-gate)")
        return True
    from runbook.datastream import gate

    manifest_path = args.manifest
    day_obj = None
    if manifest_path is None:
        try:
            day_obj = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            day_obj = None
    res = gate.check(manifest_path=manifest_path, day=day_obj)
    if res.ok:
        logger.info("datastream gate OK: %s", res.checked)
        return True
    logger.error("datastream gate FAILED — halting. reasons: %s", res.reasons)
    return False


def _render_brief(result: ParseResult) -> str:
    lines = [
        f"=== MANCINI MORNING BRIEF — {result.instrument or '?'} {result.date or ''} ===",
        f"Bias: {result.session_bias or '(none)'}",
        "",
        "Levels:",
    ]
    for lvl in sorted(result.levels, key=lambda l: l.price, reverse=True):
        label = f" — {lvl.label}" if lvl.label else ""
        lines.append(f"  {lvl.price:>9}  {lvl.kind:<11}{label}")
    if not result.levels:
        lines.append("  (none)")
    lines += ["", "Forward-looking commentary:"]
    for c in result.commentary:
        anchors = ", ".join(str(p) for p in c.trigger.anchor_prices)
        anchor_str = f" [{c.trigger.type}: {anchors}]" if anchors else f" [{c.trigger.type}]"
        lines.append(f"  • {c.text}{anchor_str}")
    if not result.commentary:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"model={result.model} parsed_at={result.parsed_at}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mancini Runbook pilot")
    ap.add_argument("--file", help="newsletter text file (default: stdin)")
    ap.add_argument("--date", help="trading day YYYY-MM-DD (default: today US/Central)")
    ap.add_argument("--no-gate", action="store_true", help="skip the datastream gate")
    ap.add_argument("--manifest", help="explicit manifest.json path for the gate")
    ap.add_argument("--store-root", help="override commentary store root (testing)")
    ap.add_argument("--model", default=None, help="override model id")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    day = _resolve_day(args.date)
    logger.info("Mancini Runbook run for %s", day)

    # 1. Datastream gate.
    if not _run_gate(args, day):
        print("HALTED: datastream gate failed. Keeping last-good artifacts.",
              file=sys.stderr)
        return 2

    raw = _read_newsletter(args.file)
    if not raw.strip():
        logger.error("empty newsletter input")
        return 2

    # 2 + validate. Live LLM call.
    parsed_at = datetime.now(timezone.utc).isoformat()
    kwargs = {"parsed_at": parsed_at}
    if args.model:
        kwargs["model"] = args.model
    try:
        outcome = parse_mod.parse(raw, **kwargs)
    except Exception as e:  # network, refusal, missing tool block
        logger.exception("extraction failed: %s", e)
        print(f"FAILED: extraction error ({e}). Keeping last-good.", file=sys.stderr)
        return 3

    if not outcome.ok:
        logger.error("validation FAILED — not publishing. errors: %s",
                     outcome.validation.errors)
        print("FAILED: validation rejected the parse (possible hallucinated "
              f"levels). Keeping last-good.\n  {outcome.validation.errors}",
              file=sys.stderr)
        return 4

    result = outcome.result
    if not result.date:
        result.date = day

    # 3. Persist: commentary store + last-good full result.
    store_path = store_mod.append(
        result.commentary, result.date or day,
        instrument=result.instrument, ingested_at=parsed_at,
        store_root=args.store_root,
    )
    PARSED_ROOT.mkdir(parents=True, exist_ok=True)
    parsed_path = PARSED_ROOT / f"{result.date or day}.json"
    parsed_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    logger.info("commentary store: %s", store_path)
    logger.info("last-good parse: %s", parsed_path)

    # 4. Brief (mini #9).
    print(_render_brief(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
