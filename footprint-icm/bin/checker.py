#!/usr/bin/env python3
"""The check that makes an unsupported cite fail by code. [st-h0xx]

A model stage may emit only these line shapes, one per line, nothing else:

  LABEL <HH:MM> <setup|none> regime=<trending|rotation|unstated> cite=<row-id> because="<words>"
  LABEL <HH:MM> <setup|none> regime=<trending|rotation|unstated> cite=UNSOURCED
  IMPLICATION <HH:MM> cite=<row-id> because="<words>" text="<one sentence>"
  IMPLICATION <HH:MM> cite=NO-RULE-IN-CANON text="<one sentence>"
  CLAIM <HH:MM> kind=<setup|regime|rule|implication|number> quote="<live words>" cite=<row-id> because="<words>"
  CLAIM <HH:MM> kind=<...> quote="<live words>" cite=UNSOURCED

The run fails, naming the line, when:
  * a line matches no shape (a blank line or a '#' comment is allowed)
  * the setup name is not one of the recognizer's six, or none
  * the cite id is not in the context index
  * the ``because`` words do not appear word for word in the cited excerpt
    (markdown emphasis, line breaks and curly quotes are not words —
    ``common.normalize``)
  * an UNSOURCED or NO-RULE-IN-CANON line carries ``because`` words
  * a CLAIM's ``quote`` does not appear word for word in the live reply
  * ``require`` names a line type (LABEL or CLAIM) and the output holds none —
    the caller says the input carried work for it (alert minutes, replies), so
    an empty, refused or truncated reply is a failed run, never a clean run
    with zero labels [st-k75z]

What this cannot decide: whether the quoted words support the label. That
is what a reader opening the cite verifies; the trial's stop condition 3
asks for at least one such row.

Usage: checker.py --context <run>/20-classify/context <stage-output.md> [--live <reply.txt>]
Exit 0 when every line passes; 2 when any fails. Verdict as JSON on stdout
with --json, one line per failure on stderr always.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import LaneError, contains_verbatim  # noqa: E402

SETUPS = ("failed_breakdown", "level_reclaim", "failed_breakout", "level_reject",
          "return_to_lvn", "range_trap", "none")
REGIMES = ("trending", "rotation", "unstated")
KINDS = ("setup", "regime", "rule", "implication", "number")
UNSOURCED = "UNSOURCED"
NO_RULE = "NO-RULE-IN-CANON"

_T = r"(?P<t>\d{2}:\d{2})"
_Q = r'"(?P<{name}>[^"]*)"'
LABEL_RE = re.compile(
    rf"^LABEL {_T} (?P<setup>\S+) regime=(?P<regime>\S+) cite=(?P<cite>\S+)"
    rf"(?: because={_Q.format(name='because')})?\s*$")
IMPL_RE = re.compile(
    rf"^IMPLICATION {_T} cite=(?P<cite>\S+)(?: because={_Q.format(name='because')})?"
    rf" text={_Q.format(name='text')}\s*$")
CLAIM_RE = re.compile(
    rf"^CLAIM {_T} kind=(?P<kind>\S+) quote={_Q.format(name='quote')} cite=(?P<cite>\S+)"
    rf"(?: because={_Q.format(name='because')})?\s*$")


def load_context(ctx: Path) -> dict[str, dict]:
    idx = ctx / "index.json"
    if not idx.exists():
        raise LaneError(f"{ctx}: no index.json — run excerpts.py first")
    rows = {}
    for r in json.loads(idx.read_text(encoding="utf-8"))["rows"]:
        rows[r["id"]] = {**r, "text": (ctx / r["file"]).read_text(encoding="utf-8")}
    return rows


def check_lines(lines: list[str], context: dict[str, dict], live: str | None = None,
                *, require: str | None = None) -> dict:
    """Every line judged. Returns {"ok", "lines", "failures": [...]}.

    ``require="LABEL"`` / ``"CLAIM"``: at least one such line must be present,
    else the verdict fails on line 0. Pass it when the input carried work for
    that line type; leave it None for a slice with nothing to label."""
    failures: list[dict] = []
    parsed: list[dict] = []

    def fail(n: int, line: str, why: str) -> None:
        failures.append({"line_no": n, "line": line, "reason": why})

    def check_cite(n: int, line: str, cite: str, because: str | None, sentinel: str) -> None:
        if cite == sentinel:
            if because:
                fail(n, line, f"{sentinel} line carries quoted words — it must stand alone")
            return
        if cite not in context:
            fail(n, line, f"cite {cite!r} is not in the context index")
            return
        if not because:
            fail(n, line, f"cite {cite} without because=\"<words>\" — a cite must quote its lines")
            return
        if not contains_verbatim(context[cite]["text"], because):
            fail(n, line, f"the quoted words are not in {cite} word for word: {because!r}")

    for n, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = LABEL_RE.match(line)
        if m:
            d = m.groupdict()
            if d["setup"] not in SETUPS:
                fail(n, line, f"setup {d['setup']!r} is not one of {SETUPS}")
            if d["regime"] not in REGIMES:
                fail(n, line, f"regime {d['regime']!r} is not one of {REGIMES}")
            check_cite(n, line, d["cite"], d.get("because"), UNSOURCED)
            parsed.append({"type": "LABEL", **d})
            continue
        m = IMPL_RE.match(line)
        if m:
            d = m.groupdict()
            check_cite(n, line, d["cite"], d.get("because"), NO_RULE)
            if not d["text"].strip():
                fail(n, line, "empty text")
            parsed.append({"type": "IMPLICATION", **d})
            continue
        m = CLAIM_RE.match(line)
        if m:
            d = m.groupdict()
            if d["kind"] not in KINDS:
                fail(n, line, f"kind {d['kind']!r} is not one of {KINDS}")
            if live is None:
                fail(n, line, "a CLAIM needs the live reply to check its quote against")
            elif not contains_verbatim(live, d["quote"]):
                fail(n, line, f"the quoted live words are not in the reply word for word: {d['quote']!r}")
            check_cite(n, line, d["cite"], d.get("because"), UNSOURCED)
            parsed.append({"type": "CLAIM", **d})
            continue
        fail(n, line, "matches no line shape (LABEL / IMPLICATION / CLAIM)")
    counts = {t: sum(1 for p in parsed if p["type"] == t) for t in ("LABEL", "IMPLICATION", "CLAIM")}
    if require is not None:
        if require not in counts:
            raise LaneError(f"require={require!r} is not one of {tuple(counts)}")
        if counts[require] == 0:
            fail(0, "", f"no {require} line in the output — the input carried work for it, so an "
                        f"empty, refused or truncated reply is not a clean run [st-k75z]")
    return {"ok": not failures, "lines": parsed, "failures": failures, "counts": counts,
            "unsourced": sum(1 for p in parsed if p.get("cite") in (UNSOURCED, NO_RULE))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("output", type=Path, help="the stage's output.md")
    ap.add_argument("--context", type=Path, required=True)
    ap.add_argument("--live", type=Path, help="the live reply a CLAIM quotes from")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require", choices=("LABEL", "CLAIM"),
                    help="fail unless at least one line of this type is present [st-k75z]")
    args = ap.parse_args(argv)
    context = load_context(args.context)
    live = args.live.read_text(encoding="utf-8") if args.live else None
    verdict = check_lines(args.output.read_text(encoding="utf-8").splitlines(), context, live,
                          require=args.require)
    (args.output.parent / "check.json").write_text(json.dumps(verdict, indent=1) + "\n",
                                                    encoding="utf-8")
    for f in verdict["failures"]:
        print(f"[FAIL] line {f['line_no']}: {f['reason']}\n       {f['line']}", file=sys.stderr)
    if args.json:
        print(json.dumps(verdict, sort_keys=True))
    else:
        c = verdict["counts"]
        print(f"checker {args.output}: {'PASS' if verdict['ok'] else 'FAIL'} — "
              f"{c['LABEL']} labels, {c['IMPLICATION']} implications, {c['CLAIM']} claims, "
              f"{verdict['unsourced']} unsourced, {len(verdict['failures'])} failure(s)")
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaneError as e:
        print(f"[REFUSED] checker: {e}", file=sys.stderr)
        raise SystemExit(2)
