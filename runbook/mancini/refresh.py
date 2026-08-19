"""Overnight refresh — re-render the plan doc from the full interaction window. [st-vxbw]

Steve, 2026-08-18: "Do we have a timer that fires at 8:15 to provide an update
to Mancini's levels based on overnight PA?" The measurement existed twice and
was published once, at the wrong time: ``overnight.build_overnight_section``
runs at PARSE time (today's parse ran 01:28 CT, so the desk doc's section
covered 17:00 → 01:28), the 08:15 pre-open cron is prepare-only (st-lw58) and
never touches price, and the 08:20 level tracker computes the full window all
session long into ``data/level_state/`` that no surface reads.

This module is the missing re-render step. It:

  1. loads the day's EXISTING in-session parse (``parsed/<day>.json``) — it
     never re-parses and never alters a level; the parse stays skill-owned;
  2. rebuilds the interaction section from the letter's write-time (4pm ET
     the day before plan-day) to NOW via the same ``compute_interactions``
     the chart and the tracker use;
  3. re-emits the same plan doc under the same stable title and desk page
     (``run._emit_desk_plan``), with the header stamped "refreshed HH:MM CT";
  4. optionally opens the desk page in the Windows browser (``--open``) —
     the manual path Steve fires "so we can review the output". The 08:15
     cron calls ``refresh()`` with ``open_browser=False``: producers must not
     spawn windows on his screen (desk-html.sh's contract); the parked tab
     refreshes in place.

Run it by hand::

    PYTHONPATH=. .venv/bin/python -m runbook.mancini.refresh --open
    PYTHONPATH=. .venv/bin/python -m runbook.mancini.refresh --date 2026-08-18

Exit codes: 0 refreshed · 3 no in-session parse for the day (nothing to
refresh — run /mancini-parse) · 4 desk publish unavailable. The candle fetch
degrades inside ``build_overnight_report`` (Schwab down → one-line section,
rc 0) so a dead token never leaves the doc half-written.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from . import overnight
from .schema import ParseResult, is_levels_only

logger = logging.getLogger("runbook.mancini")

CENTRAL = ZoneInfo("America/Chicago")

# The parked-tab address (desk-html.sh contract). run.DESK_HTML is the /tmp
# twin the run writes directly; trading-desk-refresh.sh renders this one.
DESK_PAGE = Path("/var/moo/desk/desk-mancini-latest-es-plan.html")
POWERSHELL = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")


@dataclass
class RefreshOutcome:
    rc: int
    day: str
    summary: str
    doc: Path | None = None
    section: str = ""
    counts: dict = field(default_factory=dict)


def _now_ct() -> datetime:
    return datetime.now(tz=CENTRAL)


def _counts(report: overnight.OvernightReport) -> dict:
    c = {"broken": 0, "reclaimed": 0, "held": 0, "untouched": 0}
    for it in report.interactions:
        if it.state == "broken":
            c["broken"] += 1
        elif it.state == "reclaimed":
            c["reclaimed"] += 1
        elif it.state == "tested-held":
            c["held"] += 1
        else:
            c["untouched"] += 1
    return c


def _load_parse(day: str):
    """The day's in-session parse, or None. Imported lazily: run imports us."""
    from . import run as run_mod

    path = run_mod.PARSED_ROOT / f"{day}.json"
    if not path.exists():
        return None, path
    data = json.loads(path.read_text(encoding="utf-8"))
    if is_levels_only(data.get("model", "")):
        # A levels-only artifact (the old hybrid parse, or a backfill row) is
        # not the plan Steve reads; refreshing it would put a commentary-free
        # doc on the desk. Same rule as _prepare_only: only a real parse is
        # worth re-rendering.
        return None, path
    return ParseResult.from_dict(data), path


def open_in_browser(page: Path = DESK_PAGE) -> bool:
    """Start-Process the desk page on the Windows side. Best-effort."""
    if not page.exists():
        logger.warning("browser open skipped: %s not present", page)
        return False
    if not POWERSHELL.exists():
        logger.warning("browser open skipped: powershell.exe not at %s", POWERSHELL)
        return False
    try:
        win = subprocess.run(["wslpath", "-w", str(page)], capture_output=True,
                             text=True, timeout=10, check=True).stdout.strip()
        subprocess.Popen([str(POWERSHELL), "-NoProfile", "-Command",
                          f"Start-Process '{win}'"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("browser: opened %s", win)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("browser open failed (non-fatal): %s", e)
        return False


def refresh(day: str | None = None, *, open_browser: bool = False,
            quiet: bool = False,
            fetch: Callable[..., list[dict]] | None = None,
            now: datetime | None = None) -> RefreshOutcome:
    """Re-render the day's plan doc with the interaction window brought to now.

    ``fetch`` and ``now`` exist for tests. ``quiet`` suppresses printing the
    section (the 08:15 cron folds our summary into its own line)."""
    from . import run as run_mod

    day = day or run_mod._resolve_day(None)
    result, path = _load_parse(day)
    if result is None:
        summary = (f"overnight refresh: no in-session parse for {day} "
                   f"({path.name} absent or lists-only) — run /mancini-parse; "
                   "nothing refreshed")
        logger.info(summary)
        if not quiet:
            print(summary)
        return RefreshOutcome(rc=3, day=day, summary=summary)

    stamp = (now or _now_ct()).strftime("%a %H:%M CT")
    report = overnight.build_overnight_report(result, fetch=fetch)
    title = ("Level interaction since the letter — what has already happened "
             f"to these levels (refreshed {stamp})")
    section = overnight.render_section(report, title)
    doc = run_mod._emit_desk_plan(
        result, overnight_section=section,
        header_note=f"Interaction section refreshed {stamp}.")
    if doc is None:
        summary = "overnight refresh: desk publish unavailable — nothing written"
        if not quiet:
            print(summary)
        return RefreshOutcome(rc=4, day=day, summary=summary, section=section)

    counts = _counts(report)
    if report.error:
        window = f"window unavailable ({report.error})"
    else:
        window = (f"{report.window_start} → {report.window_end}, "
                  f"{report.candle_count} candles, last {report.last_close:g}")
    summary = (f"overnight refresh: {day} re-rendered {stamp} — {window}; "
               f"{counts['broken']} broken, {counts['reclaimed']} reclaimed, "
               f"{counts['held']} tested-held, {counts['untouched']} untouched "
               f"of {len(report.interactions)} → {doc.name}")
    logger.info(summary)
    if not quiet:
        print(section)
        print()
        print(summary)
        print(f"desk: {DESK_PAGE if DESK_PAGE.exists() else run_mod.DESK_HTML}")
    if open_browser:
        open_in_browser()
    return RefreshOutcome(rc=0, day=day, summary=summary, doc=doc,
                          section=section, counts=counts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Re-render the Mancini plan doc with the level-interaction "
                    "window brought to now (never re-parses). [st-vxbw]")
    ap.add_argument("--date", help="plan-day YYYY-MM-DD (default: today CT)")
    ap.add_argument("--open", action="store_true",
                    help="open the desk page in the Windows browser afterwards")
    ap.add_argument("--quiet", action="store_true",
                    help="summary line only (no section dump)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return refresh(args.date, open_browser=args.open, quiet=args.quiet).rc


if __name__ == "__main__":
    sys.exit(main())
