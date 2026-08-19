#!/usr/bin/env python3
"""Day post-mortem — run it for a day, publish the page, keep the ledger. [co-7kgte]

Spec: docs/superpowers/specs/2026-08-19-day-postmortem-design.md. The measuring
lives in market/orderflow/postmortem.py; this file decides WHICH day, reads
the record, writes the ledger, renders through COO's desk-html.sh, and
registers the stable page once.

PASSES
    same-day      15:30 CT — the feeder's record so far today (the evening
                  session is still being written; the page says so).
    next-morning  08:27 CT — the previous session again, now with the evening
                  bars and Mancini's recap from that evening's letter.
    backfill      --backfill: every corpus day with ES tape, replay path,
                  ledger rows only plus one summary page.

USAGE
    .venv/bin/python scripts/postmortem_day.py                       # same-day, today
    .venv/bin/python scripts/postmortem_day.py --pass next-morning   # previous session
    .venv/bin/python scripts/postmortem_day.py --day 2026-08-18 --pass next-morning
    .venv/bin/python scripts/postmortem_day.py --backfill --workers 6
    .venv/bin/python scripts/postmortem_day.py --dry-run             # nothing written

WHERE IT WRITES
    data/measurement/postmortem/<day>.json, ledger.jsonl, legs.jsonl,
    recaps/<day>.json, pages/postmortem-<day>.md, pages/postmortem-latest.md
    /var/moo/desk/desk-postmortem-<day>.html and desk-postmortem-latest.html
    /root/projects/COO/myDesk/trading/postmortem-latest.md — the copy the
    desk NAV lists (manifest paths are COO-repo-relative), registered once
    under Trading.

EXIT CODES
    0 ran and wrote;  2 no record for the day (page written saying so);
    3 renderer missing (ledger written, page not rendered);  1 anything else.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.corpus.paths import central_date, most_recent_session_day   # noqa: E402
from market.orderflow import postmortem as pm                           # noqa: E402
from market.orderflow.anchors import PARSED as PARSED_DIR, mancini_levels_for  # noqa: E402
from market.orderflow.replay import has_es_day                          # noqa: E402
from market.orderflow.run_log import run_log_path                       # noqa: E402

logger = logging.getLogger("postmortem_day")
CT = ZoneInfo("America/Chicago")

COO_ROOT = Path("/root/projects/COO")
DESK_HTML = COO_ROOT / "tmuxMOO" / "bin" / "desk-html.sh"
DESK_REGISTER = COO_ROOT / "tmuxMOO" / "bin" / "desk-register.sh"
DESK_DIR = Path("/var/moo/desk")
DESK_TRADING_REL = Path("myDesk") / "trading"          # relative to COO_ROOT (the manifest's convention)
DESK_LATEST_NAME = "postmortem-latest.md"
LETTERS_DIR = REPO_ROOT / "data" / "mancini-letters"


# ------------------------------------------------------------------ which day

def resolve_day(arg: str | None, pass_name: str, now: datetime) -> _date:
    if arg:
        return _date.fromisoformat(arg)
    if pass_name == "same-day":
        return central_date(now)
    return most_recent_session_day(now)


# --------------------------------------------------------------------- inputs

def find_letter_for_session(day: _date, *, letters_dir: Path = LETTERS_DIR) -> Path | None:
    """The letter written the evening of ``day`` (it recaps that session).
    Files are <date>-<hhmmss>.txt; take the latest of that date."""
    hits = sorted(letters_dir.glob(f"{day.isoformat()}-*.txt"))
    return hits[-1] if hits else None


def parsed_kinds_for(day: _date, *, parsed_dir: Path = PARSED_DIR) -> dict[float, str]:
    """{price: kind} from the day's Mancini parse (Addendum A1). Empty when the
    parse is absent or unreadable — a missing parse never stops the run."""
    path = parsed_dir / f"{day.isoformat()}.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        out: dict[float, str] = {}
        for lv in doc.get("levels", []) or []:
            if not isinstance(lv, dict) or lv.get("price") is None or not lv.get("kind"):
                continue
            out[round(float(lv["price"]), 2)] = str(lv["kind"])
        return out
    except (OSError, ValueError, TypeError, AttributeError) as e:
        logger.warning("Mancini parse for %s unreadable (%s) — anchor kinds unknown", day, e)
        return {}


def recap_rows_for(day: _date, root: Path, letter: Path | None) -> tuple[str, list[dict]]:
    """(status, rows). Writes recaps/<letter-date>.json when a letter exists."""
    if letter is None:
        return "not-received", []
    from runbook.mancini.clean import html_to_text, looks_like_html
    raw = letter.read_text(encoding="utf-8", errors="replace")
    text = html_to_text(raw) if looks_like_html(raw) else raw
    if pm.RECAP_START not in text:
        return "no-recap-section", []
    rows = pm.extract_recap(text, letter_date=day)
    out = root / "recaps"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{day.isoformat()}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return "received", rows


# -------------------------------------------------------------------- publish

def write_pages(root: Path, day: _date, md: str) -> tuple[Path, Path]:
    pages = root / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    p = pages / f"postmortem-{day.isoformat()}.md"
    latest = pages / DESK_LATEST_NAME
    p.write_text(md, encoding="utf-8")
    shutil.copyfile(p, latest)
    return p, latest


def publish(md_path: Path, html_name: str, *, also_latest: bool) -> int:
    """Render through desk-html.sh to /var/moo/desk/<html_name>; copy to the
    stable 'latest' page; put the .md where the desk NAV lists it
    (COO/myDesk/trading/postmortem-latest.md) and register it once
    (idempotent). Returns 0, or 3 when the renderer is absent/failed (the
    ledger still stands)."""
    if not DESK_HTML.exists():
        logger.warning("desk-html.sh absent at %s — page not rendered", DESK_HTML)
        return 3
    target = DESK_DIR / html_name
    try:
        proc = subprocess.run([str(DESK_HTML), str(md_path), str(target)],
                              capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("desk-html.sh failed to run: %s", e)
        return 3
    if proc.returncode != 0:
        logger.warning("desk-html.sh rc=%d: %s", proc.returncode, proc.stderr.strip()[:300])
        return 3
    logger.info("page: %s", target)
    if also_latest:
        shutil.copyfile(target, DESK_DIR / "desk-postmortem-latest.html")
        desk_md = COO_ROOT / DESK_TRADING_REL / DESK_LATEST_NAME
        try:
            desk_md.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(md_path, desk_md)
            out = subprocess.run([str(DESK_REGISTER), "Trading", str(DESK_TRADING_REL / DESK_LATEST_NAME)],
                                 capture_output=True, text=True, timeout=30)
            if out.returncode:
                logger.warning("desk-register rc=%d: %s", out.returncode, out.stderr.strip()[:200])
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("desk copy/register skipped: %s", e)
    return 0


# ----------------------------------------------------------------- live pass

def run_live_pass(*, day: _date, pass_name: str, record: Path, root: Path,
                  knobs: pm.Knobs, now: datetime, letter: Path | None,
                  publish_pages: bool) -> int:
    if not record.exists():
        md = (f"# Day post-mortem — {day.isoformat()}\n\n"
              f"**No feeder record for {day.isoformat()}** at `{record}`. Nothing to measure. "
              f"If the feeder ran, its run log was disabled (`--no-run-log`) or written elsewhere.\n")
        p, _ = write_pages(root, day, md)
        if publish_pages:
            publish(p, f"desk-postmortem-{day.isoformat()}.html", also_latest=True)
        logger.error("no feeder record for %s at %s", day, record)
        return 2
    segs = pm.load_live_segments(record)
    if pass_name == "next-morning":
        status, rows = recap_rows_for(day, root, letter)
    else:
        status, rows = "not-received", []
    res = pm.analyze_day(segs, knobs, day=day, source="live", pass_name=pass_name, now=now,
                         recap_rows=rows, letter_status=status,
                         parsed_kinds=parsed_kinds_for(day))
    pm.write_ledger(res, root)
    hist = pm.history(root, days=knobs.history_days, before=day.isoformat())
    md = pm.render_page(res, hist)
    p, _ = write_pages(root, day, md)
    logger.info("%s %s: %d calls, %d legs, %d flags, recap %s", day, pass_name,
                len(res["calls"]), len(res["legs"]), len(res["flags"]), status)
    if publish_pages:
        return publish(p, f"desk-postmortem-{day.isoformat()}.html", also_latest=True)
    return 0


# ------------------------------------------------------------------ backfill
# (filled in by Task 12 — leave this comment as the anchor for it)


# ------------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", help="YYYY-MM-DD (default: today for same-day, previous session otherwise)")
    ap.add_argument("--pass", dest="pass_name", default="same-day",
                    choices=("same-day", "next-morning"))
    ap.add_argument("--backfill", action="store_true", help="replay every corpus day with ES tape")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--config", default=str(pm.CONFIG_PATH))
    ap.add_argument("--root", default=str(pm.LEDGER_ROOT))
    ap.add_argument("--no-publish", action="store_true", help="write ledger and .md, no desk page")
    ap.add_argument("--dry-run", action="store_true", help="resolve and report; write nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    knobs = pm.load_knobs(Path(args.config))
    root = Path(args.root)
    now = datetime.now(tz=CT)
    if args.backfill:
        return run_backfill(root=root, knobs=knobs, workers=args.workers,
                            publish_pages=not args.no_publish, dry_run=args.dry_run)
    day = resolve_day(args.day, args.pass_name, now)
    record = run_log_path(day)
    letter = find_letter_for_session(day) if args.pass_name == "next-morning" else None
    if args.dry_run:
        print(f"would run {args.pass_name} for {day}: record {record} "
              f"({'present' if record.exists() else 'ABSENT'}), letter {letter or 'none'}, "
              f"parse kinds {len(parsed_kinds_for(day))}, ledger {root}, knobs {knobs}")
        return 0
    return run_live_pass(day=day, pass_name=args.pass_name, record=record, root=root,
                         knobs=knobs, now=now, letter=letter, publish_pages=not args.no_publish)


if __name__ == "__main__":
    sys.exit(main())
