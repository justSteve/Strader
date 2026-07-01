"""Per-day directory layout for the three-stream corpus. [st-1yp]

Corpus root is `data/corpus/`. Each trading day gets its own subdirectory
keyed by US/Central calendar date — `data/corpus/YYYY-MM-DD/`. Inside:

    schwab.jsonl            append-only, one row per intraday cycle
    gexbot.jsonl            append-only, one row per intraday cycle
    databento_opra.jsonl    SPXW option trade ticks — T+1 batch and/or live
                            stream (rows tagged provenance.source)
    databento_glbx_es.jsonl ES front-month trade ticks — same two sources
    manifest.json           collection summary, errors, cycle counts

Date keying uses US/Central because that's the convention the rest of the
Strader codebase already uses (see gex_series.py date rollover logic) and
it lines up with the cash session boundary at 15:00 CT.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_ROOT = PROJECT_ROOT / "data" / "corpus"


def central_date(now: datetime | None = None) -> date:
    """Return today's US/Central calendar date."""
    now = now or datetime.now(CENTRAL)
    return now.astimezone(CENTRAL).date() if now.tzinfo else now.date()


def most_recent_session_day(now: datetime | None = None) -> date:
    """Most-recent-completed trading session, US/Central.

    Default: the previous weekday, walking back over Sat/Sun. Databento
    historical is T+1, so *today* has no complete manifest before the cash
    close — the corpus (and therefore the datastream gate) targets the last
    session that actually finished. Holidays are NOT modeled: a holiday yields
    an empty/0-tick day that the gate flags, which is the safe failure (an
    alert, not silent stale data).

    This is the single source of truth for "which day's data is current",
    shared by scripts/corpus_daily.py (ingestion) and the datastream gate
    (consumption) so the two cannot drift onto different days. [co-i10h]
    """
    d = central_date(now) - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


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


def databento_glbx_es_path(d: date | None = None) -> Path:
    """Per-day Databento GLBX.MDP3 ES.c.0 trades stream. [st-xc9]"""
    return day_dir(d) / "databento_glbx_es.jsonl"


def manifest_path(d: date | None = None) -> Path:
    return day_dir(d) / "manifest.json"
