#!/usr/bin/env python3
"""Entitlements probe — report subscription state at statement time. [st-g0or / st-aski Phase 1.4]

Reads the registry (``config/entitlements.yaml``), runs the probeable checks
against LOCAL state files, and prints one observation report:

    .venv/bin/python3 scripts/entitlements_probe.py            # the report
    .venv/bin/python3 scripts/entitlements_probe.py --verbose  # + what each plan buys
    .venv/bin/python3 scripts/entitlements_probe.py --json     # machine-readable
    .venv/bin/python3 scripts/entitlements_probe.py --dated-only   # Steve-only facts
    .venv/bin/python3 scripts/entitlements_probe.py --strict   # never-confirmed also exits 1

Exit codes:
    0  nothing needs a human right now
    1  something does — a probe alarmed, a dated fact aged out, or a review date hit
    2  the probe itself failed (registry missing or unparseable)

WHAT THIS DOES NOT DO. It calls no vendor API — not Schwab, not Databento, not
GexBot. Every line comes from a local JSON state file or a corpus directory
listing. That is deliberate twice over: the agent is barred from executing
live-API code (``.claude/rules/schwab-api-gate.md``), and a probe that needed
credentials to answer "what are we entitled to" would be unrunnable exactly when
the answer matters. The registry holds no credentials and never will.

Consequently a green OBSERVED line proves the data is landing, not that the bill
is paid — a cancelled plan keeps delivering until its period ends. The contract
half of the truth is the DATED section, and only Steve can move those dates.

Logic lives in ``strader/entitlements.py``; this file is the CLI and its exit
codes, matching the schwab_token.py / schwab_token_health.py split.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from strader.entitlements import build_report, render  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Entitlements registry probe [st-g0or]")
    ap.add_argument("--registry", default=None, help="Path to the registry (default config/entitlements.yaml)")
    ap.add_argument("--corpus-root", default=None, help="Override the corpus root (tests)")
    ap.add_argument("--repo-root", default=None,
                    help="Override the root that probed file paths resolve against (tests)")
    ap.add_argument("--json", action="store_true", help="Emit the report as JSON")
    ap.add_argument("--verbose", action="store_true", help="Include what each plan buys")
    ap.add_argument("--dated-only", action="store_true",
                    help="Print only the Steve-confirmed lines and their ages")
    ap.add_argument("--strict", action="store_true",
                    help="Treat never-confirmed entries as actionable too")
    args = ap.parse_args(argv)

    try:
        report = build_report(args.registry,
                              repo_root=Path(args.repo_root) if args.repo_root else None,
                              corpus_root=Path(args.corpus_root) if args.corpus_root else None)
    except Exception as e:
        print(f"[entitlements] INTERNAL ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        print("[entitlements] The registry is config/entitlements.yaml — if it is gone, "
              "say so out loud rather than reporting no entitlements.", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(strict=args.strict), indent=2))
    elif args.dated_only:
        print(f"DATED ASSERTIONS — as-of facts, not observations "
              f"(registry {report.registry_path.name})")
        for d in report.dated:
            age = f"{d.age_days:.0f}d ago" if d.age_days is not None else "never confirmed"
            flag = "" if d.verdict == "DATED" else f"  [{d.verdict}]"
            print(f"  {d.label}: {d.state} — as of {d.confirmed_on or 'never'} ({age}), "
                  f"{d.confirmed_by or 'nobody'} via {d.source}{flag}")
    else:
        print(render(report, verbose=args.verbose))

    return 1 if report.actionable(strict=args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
