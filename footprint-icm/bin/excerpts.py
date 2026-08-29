#!/usr/bin/env python3
"""Build stage 20's context folder from the source list. [st-h0xx]

The classify stage may cite only what is in its own folder, and its folder
holds only what this script generated from ``20-classify/context/manifest.yaml``:
one excerpt file per row, cut from ``git show <commit>:<path>`` at the row's
lines. Nothing is hand-copied, so nothing drifts silently.

REFUSALS (exit 2, the row named):
  * the path is outside ``allowed_paths``, or in ``refused_files``
  * the status is one the lane does not admit (``refused_statuses``), or not
    a known word at all
  * the lines at HEAD differ from the lines at the pinned commit — "canon
    moved, re-pin": the bundle's own log records in-place rewrites, and a pin
    that went stale quietly would be the first stale cite in the estate
  * the row's ``quote`` is not in its own excerpt word for word — the row is
    wrong about its own lines
  * the code row reaches past the recognizer's docstring (lines 1-38)

Also written: ``context/index.json`` (every row with the excerpt's
fingerprint) and ``40-compare/tripwire.json`` — the rule-shaped words the
compare stage watches for, DERIVED from the rows' quotes plus the two planted
sentences rather than kept by hand (Desk Ruling 13: a hand-maintained site
list is the same defect as a hand-maintained token list).

``--verify <run>`` checks a run folder's context/ holds exactly the files the
index names and nothing else — a hand-added file fails.

Usage: excerpts.py <YYYY-MM-DD> [--manifest PATH]
       excerpts.py --verify <run-folder>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import date as _date, datetime
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import (  # noqa: E402
    CT, LANE, LaneError, ROOT, contains_verbatim, git_short, log, normalize, run_dir,
    update_run_json, write_json,
)

MANIFEST = LANE / "20-classify/context/manifest.yaml"
STATUSES = ("trusted", "exploratory", "code", "under-review", "tabled", "withdrawn")
CODE_ROW_MAX_LINE = 38            # recognizer.py's docstring; decision 1's carve-out

# The two sentences the trial plants: the withdrawn phrasing (commit 3697dbf,
# withdrawn in 2ad27bd) and the uncited generalisation that replaced it
# (docs/playbooks/emitter-two-tier.md:150-152). Their words join the tripwire.
PLANTED = (
    "fade/skip context per the playbook",
    "regime changes a setup's management and expectancy, not its validity",
)
STOPWORDS = set("""a an and are as at be but by for from has have if in into is it its not of on or
per that the their then this to was were what where which who will with your
here there nothing still never changes happened holding tell""".split())


def load_manifest(path: Path = MANIFEST) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("allowed_paths", "refused_files", "refused_statuses", "rows"):
        if key not in doc:
            raise LaneError(f"manifest {path}: missing '{key}'")
    ids = [r.get("id") for r in doc["rows"]]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise LaneError(f"manifest: duplicate row ids {sorted(dupes)}")
    return doc


def git_lines(ref: str, path: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{path}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise LaneError(f"git show {ref}:{path} failed: {out.stderr.strip()[-200:]}")
    return out.stdout.splitlines()


def cut(lines: list[str], ranges: list[list[int]]) -> list[str]:
    out: list[str] = []
    for lo, hi in ranges:
        if lo < 1 or hi < lo or hi > len(lines):
            raise LaneError(f"line range {lo}-{hi} outside the file's {len(lines)} lines")
        out.extend(lines[lo - 1:hi])
    return out


def check_row(row: dict, manifest: dict) -> None:
    rid = row.get("id") or "?"
    for key in ("id", "path", "commit", "lines", "status", "quote"):
        if key not in row:
            raise LaneError(f"row {rid}: missing '{key}'")
    path = str(row["path"])
    if not any(path == a or (a.endswith("/") and path.startswith(a)) for a in manifest["allowed_paths"]):
        raise LaneError(f"row {rid}: path {path} is outside allowed_paths {manifest['allowed_paths']}")
    if path in manifest["refused_files"]:
        raise LaneError(f"row {rid}: {path} is a refused file (withdrawn-class source)")
    if row["status"] not in STATUSES:
        raise LaneError(f"row {rid}: unknown status {row['status']!r}; one of {STATUSES}")
    if row["status"] in manifest["refused_statuses"]:
        raise LaneError(f"row {rid}: status {row['status']!r} is refused")
    if not path.startswith("knowledge/") and row["status"] != "code":
        raise LaneError(f"row {rid}: a source outside knowledge/ must carry status 'code'")
    if row["status"] == "code" and any(hi > CODE_ROW_MAX_LINE for _, hi in row["lines"]):
        raise LaneError(f"row {rid}: a code row may cite lines 1-{CODE_ROW_MAX_LINE} only "
                        f"(decision 1); got {row['lines']}")
    if ".." in path or path.startswith("/"):
        raise LaneError(f"row {rid}: path {path!r} is not repo-relative")


def build_row(row: dict, head_ref: str = "HEAD") -> dict:
    """The excerpt for one row, after every check. Returns the record for
    index.json with the excerpt text under 'text'."""
    rid = row["id"]
    ranges = [[int(a), int(b)] for a, b in row["lines"]]
    pinned = cut(git_lines(str(row["commit"]), row["path"]), ranges)
    head = cut(git_lines(head_ref, row["path"]), ranges)
    if pinned != head:
        changed = sum(1 for a, b in zip(pinned, head) if a != b) + abs(len(pinned) - len(head))
        raise LaneError(f"row {rid}: canon moved, re-pin — {row['path']} lines {ranges} differ "
                        f"between {row['commit']} and HEAD ({changed} line(s)); last commit "
                        f"touching the file is {git_short(Path(row['path']))}")
    text = "\n".join(pinned)
    if not contains_verbatim(text, str(row["quote"])):
        raise LaneError(f"row {rid}: its quote is not in its own lines word for word: "
                        f"{row['quote']!r}")
    span = ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in ranges)
    header = f"{rid}: {row['path']}:{span} @ {row['commit']} ({row['status']})"
    body = f"{header}\n{'=' * len(header)}\n{text}\n"
    return {"id": rid, "path": row["path"], "commit": str(row["commit"]), "lines": ranges,
            "status": row["status"], "quote": row["quote"], "note": row.get("note", ""),
            "file": f"{rid}.md", "sha256": hashlib.sha256(body.encode()).hexdigest(),
            "text": body}


def derived_words(rows: list[dict]) -> list[str]:
    """The compare stage's tripwire: every word of five letters or more in
    the rows' quotes and the planted sentences (identifiers like
    failed_breakdown and compounds like fade/skip stay whole), minus a short
    list of function words. A rule, not a hand list — it changes only when a
    row does."""
    words: set[str] = set()
    for src in [r["quote"] for r in rows] + list(PLANTED):
        for w in re.findall(r"[a-z][a-z'/_-]{4,}", normalize(src)):
            if w not in STOPWORDS:
                words.add(w)
    return sorted(words)


def build(day: _date, manifest_path: Path = MANIFEST) -> dict:
    manifest = load_manifest(manifest_path)
    rd = run_dir(day)
    ctx = rd / "20-classify" / "context"
    ctx.mkdir(parents=True, exist_ok=True)
    for old in ctx.iterdir():
        if old.is_file():
            old.unlink()
    index = []
    for row in manifest["rows"]:
        check_row(row, manifest)
        rec = build_row(row)
        (ctx / rec["file"]).write_text(rec.pop("text"), encoding="utf-8")
        index.append(rec)
    write_json(ctx / "index.json", {"manifest": str(manifest_path), "built_at":
                                    datetime.now(CT).isoformat(timespec="seconds"),
                                    "strader_head": git_short(), "rows": index})
    trip = derived_words(manifest["rows"])
    write_json(rd / "40-compare" / "tripwire.json",
               {"words": trip, "derived_from": "manifest quotes + the two planted sentences",
                "planted": list(PLANTED)})
    rec = {"produced_at": datetime.now(CT).isoformat(timespec="seconds"), "rows": len(index),
           "lines": sum(hi - lo + 1 for r in index for lo, hi in r["lines"]),
           "statuses": {s: sum(1 for r in index if r["status"] == s) for s in STATUSES
                        if any(r["status"] == s for r in index)},
           "tripwire_words": len(trip), "manifest": str(manifest_path)}
    update_run_json(day, "excerpts", rec)
    return rec


def verify(run: Path) -> list[str]:
    """Names of files in context/ that the index did not generate."""
    ctx = run / "20-classify" / "context"
    idx = ctx / "index.json"
    if not idx.exists():
        raise LaneError(f"{ctx}: no index.json — run excerpts.py first")
    doc = json.loads(idx.read_text(encoding="utf-8"))
    expected = {r["file"] for r in doc["rows"]} | {"index.json"}
    strays = sorted(p.name for p in ctx.iterdir() if p.name not in expected)
    for r in doc["rows"]:
        p = ctx / r["file"]
        if not p.exists():
            strays.append(f"MISSING {r['file']}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            strays.append(f"EDITED {r['file']}")
    return strays


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("day", nargs="?", type=_date.fromisoformat)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--verify", type=Path, metavar="RUN", help="check a run's context/ is exactly what the index names")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    if args.verify:
        strays = verify(args.verify)
        if strays:
            raise LaneError(f"context/ is not what excerpts.py generated: {strays}")
        print(f"context/ verified: {args.verify}")
        return 0
    if not args.day:
        ap.error("a day or --verify is required")
    rec = build(args.day, args.manifest)
    print(f"excerpts {args.day}: {rec['rows']} rows, {rec['lines']} lines, statuses {rec['statuses']}, "
          f"tripwire {rec['tripwire_words']} words")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaneError as e:
        print(f"[REFUSED] excerpts: {e}", file=sys.stderr)
        raise SystemExit(2)
