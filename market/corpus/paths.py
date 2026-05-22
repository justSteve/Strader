"""Per-day directory layout for the three-stream corpus. [st-1yp]

Corpus root is `data/corpus/`. Each trading day gets its own subdirectory
keyed by US/Central calendar date — `data/corpus/YYYY-MM-DD/`. Inside:

    schwab.jsonl            append-only, one row per intraday cycle
    gexbot.jsonl            append-only, one row per intraday cycle
    databento_opra.jsonl    written once per day by the T+1 batch
    manifest.json           collection summary, errors, cycle counts

Date keying uses US/Central because that's the convention the rest of the
Strader codebase already uses (see gex_series.py date rollover logic) and
it lines up with the cash session boundary at 15:00 CT.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_ROOT = PROJECT_ROOT / "data" / "corpus"


def central_date(now: datetime | None = None) -> date:
    """Return today's US/Central calendar date."""
    now = now or datetime.now(CENTRAL)
    return now.astimezone(CENTRAL).date() if now.tzinfo else now.date()


def day_dir(d: date | None = None, *, create: bool = False) -> Path:
    """Return the per-day directory path."""
    d = d or central_date()
    p = CORPUS_ROOT / d.isoformat()
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def schwab_path(d: date | None = None) -> Path:
    return day_dir(d) / "schwab.jsonl"


def gexbot_path(d: date | None = None) -> Path:
    return day_dir(d) / "gexbot.jsonl"


def databento_path(d: date | None = None) -> Path:
    return day_dir(d) / "databento_opra.jsonl"


def manifest_path(d: date | None = None) -> Path:
    return day_dir(d) / "manifest.json"
