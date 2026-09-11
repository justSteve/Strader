#!/usr/bin/env python3
"""Blotter page — the replay rows as a desk page, sortable, each row opening onto
what it read and what it cites. [st-08ru]

WHAT
    Reads every ``replay-<day>.jsonl`` under the rows directory (the output of
    ``scripts/measurement/blotter_replay.py``) and the latest run manifest
    beside them, joins each row's rule to its entity (the Statement verbatim,
    with the file's last commit) through the registry, computes the aggregates
    the write-up uses (``strader.blotter.report`` — split by mark path, never
    pooled), and embeds it all in ``scripts/blotter_page_template.html`` at the
    ``/*__BLOTTER_DATA__*/null`` marker. The page is self-contained: no network,
    nothing fetched, so it renders from a parked browser tab and on the
    tailnet alike. No model rewrites a rule's words — the Statement is embedded
    verbatim from the bundle.

    Rows are sortable by any column and filterable by rule, mark path and
    exit; a row opens an in-page panel with the lens fields the rule read at
    the fire minute (never the outcome), the tape events in the half hour
    before it, the declared exit and the premium grid (printed rows), what the
    proxy would have resolved (estimated rows), the Statement it cites, and
    links to the day's drill page and the region replay on the bridge. Each
    row's id is on the panel and is speakable.

    Estimated rows are shown in their own face and labelled; extrapolated
    marks carry a warning tag; nothing is hidden.

RUN
    .venv/bin/python3 scripts/blotter_page.py                    # -> COO/myDesk/trading/blotter.html
    .venv/bin/python3 scripts/blotter_page.py --register         # ... and register under Trading
    .venv/bin/python3 scripts/blotter_page.py --rows-dir data/measurement/blotter --out /tmp/x.html

    Regenerate after a replay run; the page carries the rows directory and
    the manifest's range so a reader can tell which run it shows.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strader.blotter.report import aggregate, grid_table          # noqa: E402
from strader.blotter.rules import RegistryError, load_rules      # noqa: E402

logger = logging.getLogger("blotter_page")
CT = ZoneInfo("America/Chicago")

TEMPLATE = Path(__file__).parent / "blotter_page_template.html"
MARKER = "/*__BLOTTER_DATA__*/null"
DEFAULT_ROWS_DIR = ROOT / "data" / "measurement" / "blotter"
DESK_TRADING = Path("/root/projects/COO/myDesk/trading")
PAGE = DESK_TRADING / "blotter.html"
DESK_REGISTER = Path("/root/projects/COO/tmuxMOO/bin/desk-register.sh")


def read_rows(rows_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(Path(rows_dir).glob("replay-*.jsonl")):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    rows.sort(key=lambda r: (r["day"], r["rule_id"], r["id"]))
    return rows


def read_manifest(rows_dir: Path) -> dict:
    """The latest ``replay-run-<from>-<to>.json`` by its range end, or {}."""
    best: tuple[str, Path] | None = None
    for p in Path(rows_dir).glob("replay-run-*.json"):
        try:
            rng = json.loads(p.read_text(encoding="utf-8")).get("range") or ["", ""]
        except (OSError, ValueError):
            continue
        key = str(rng[1]) + str(rng[0])
        if best is None or key > best[0]:
            best = (key, p)
    if best is None:
        return {}
    return json.loads(best[1].read_text(encoding="utf-8"))


def _last_commit(path: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%h", "--", str(path)],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def rules_meta(*, with_commit: bool = True) -> dict[str, dict]:
    """Every registered rule: the page's copy of its declaration and Statement."""
    out: dict[str, dict] = {}
    for r in load_rules():
        e = r.entity
        rel = e.path.relative_to(ROOT) if e.path.is_relative_to(ROOT) else e.path
        out[r.id] = {
            "id": r.id, "title": e.title, "status": e.status, "type": e.type,
            "path": str(rel), "commit": _last_commit(rel) if with_commit else None,
            "fire_at": list(r.fire_at), "instrument": r.instrument, "entry": r.entry,
            "exit": r.exit.to_dict(), "registered": r.registered,
            "statement": e.statement(), "sources": list(e.sources),
        }
    return out


def build(rows_dir: Path, *, rules: dict[str, dict] | None = None, built: str | None = None) -> dict:
    """The page's data payload — JSON-serialisable, renderer-independent."""
    rows = read_rows(rows_dir)
    manifest = read_manifest(rows_dir)
    unpriced = [{"day": d["day"], **u} for d in manifest.get("days", []) for u in d.get("unpriced", [])]
    rel = rows_dir.relative_to(ROOT) if rows_dir.is_relative_to(ROOT) else rows_dir
    return {
        "built": built or datetime.now(CT).strftime("%Y-%m-%d %H:%M CT"),
        "rows_dir": str(rel),
        "manifest": {k: manifest.get(k) for k in ("range", "n_days", "n_rows", "n_unpriced", "calibration", "events")},
        "rows": rows,
        "unpriced": unpriced,
        "aggregate": aggregate(rows),
        "grid": grid_table(rows),
        "rules": rules if rules is not None else rules_meta(),
    }


def render_html(payload: dict, template: Path = TEMPLATE) -> str:
    tpl = template.read_text(encoding="utf-8")
    if MARKER not in tpl:
        raise SystemExit(f"template {template} missing data marker {MARKER}")
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True).replace("</", "<\\/")
    return tpl.replace(MARKER, blob)


def publish(page_html: str, out: Path, *, register: bool = False) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page_html, encoding="utf-8")
    logger.info("page: %s (%d bytes)", out, len(page_html))
    if not register:
        return
    try:
        r = subprocess.run([str(DESK_REGISTER), "Trading", f"myDesk/trading/{out.name}"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode:
            logger.warning("desk-register failed (rc=%d): %s", r.returncode, r.stderr.strip()[:200])
        else:
            logger.info("registered in Trading window: %s", out.name)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("desk-register skipped: %s", e)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows-dir", type=Path, default=DEFAULT_ROWS_DIR)
    ap.add_argument("--out", type=Path, default=PAGE)
    ap.add_argument("--register", action="store_true", help="register the page under the desk's Trading window")
    ap.add_argument("--built", default=None, help="the build stamp shown on the page (default: now, CT)")
    ap.add_argument("--no-commit", action="store_true", help="do not ask git for each entity's last commit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not args.rows_dir.is_dir():
        print(f"rows directory {args.rows_dir} not found; run scripts/measurement/blotter_replay.py first", file=sys.stderr)
        return 1
    try:
        rules = rules_meta(with_commit=not args.no_commit)
    except RegistryError as e:
        print(str(e), file=sys.stderr)
        return 1
    payload = build(args.rows_dir, rules=rules, built=args.built)
    if not payload["rows"]:
        print(f"no replay-<day>.jsonl rows under {args.rows_dir}", file=sys.stderr)
        return 1
    publish(render_html(payload), args.out, register=args.register)
    est = sum(1 for r in payload["rows"] if r.get("estimated"))
    print(f"{len(payload['rows'])} rows ({len(payload['rows']) - est} printed, {est} estimated), "
          f"{len(payload['unpriced'])} unpriced, {len(payload['rules'])} rules -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
