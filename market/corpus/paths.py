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
Strader codebase already uses (central_date below is the one definition) and
it lines up with the cash session boundary at 15:00 CT.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# STRADER_CORPUS_ROOT relocates the whole corpus tree — a replay box, a
# harvest copy on Z:, a test fixture — without touching every consumer
# [Watcher V2 plan §2 seam (e), Phase 4]. Every path helper below derives from
# this one name; scripts/drill_bridge.py (dependency-light, no market import)
# reads the same variable itself. Read once at import: a process pins one
# corpus for its life, which is the behaviour a feeder or a sentinel wants.
CORPUS_ROOT = Path(os.environ.get("STRADER_CORPUS_ROOT") or (PROJECT_ROOT / "data" / "corpus"))


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


def schwab_late_chain_path(d: date | None = None) -> Path:
    """The last-hour 0DTE chain series (30s cadence, 14:00-15:01 CT) that gives
    a late-day singleton a mark PATH instead of one 14:45 snapshot [st-9dyz]."""
    return day_dir(d) / "schwab_late_chain.jsonl"


def gexbot_path(d: date | None = None) -> Path:
    return day_dir(d) / "gexbot.jsonl"


def gexbot_orderflow_1s_path(d: date | None = None) -> Path:
    """The 1 Hz orderflow file the sentinel watches and the basis estimator
    reads [st-n0qm.8]."""
    return day_dir(d) / "gexbot_orderflow_1s.jsonl"


def databento_path(d: date | None = None) -> Path:
    return day_dir(d) / "databento_opra.jsonl"


def databento_glbx_es_path(d: date | None = None) -> Path:
    """Per-day Databento GLBX.MDP3 ES.c.0 trades stream. [st-xc9]"""
    return day_dir(d) / "databento_glbx_es.jsonl"


def databento_glbx_es_mbp1_path(d: date | None = None) -> Path:
    """Per-day Databento GLBX.MDP3 ES.c.0 MBP-1 (top-of-book) stream. [st-9vl]"""
    return day_dir(d) / "databento_glbx_es_mbp1.jsonl"


def internals_path(d: date | None = None) -> Path:
    """Per-day NYSE internals minute candles ($TICK/$TRIN/$ADD/$VOLD). [st-3fr]"""
    return day_dir(d) / "internals.jsonl"


def manifest_path(d: date | None = None) -> Path:
    return day_dir(d) / "manifest.json"


# --------------------------------------------------------------------------
# Compaction-aware reading [st-itky]
#
# The path helpers above are the canonical WRITE locations and always name the
# uncompressed file — a writer must never be handed a .gz. Reading is the
# asymmetric half: corpus_compact_databento.py packs a finished day's JSONL to
# .jsonl.gz and REMOVES the source, so from a reader's side a day's data may
# live under either name. Every reader must therefore go through these two
# helpers rather than touching the raw path, or it will silently treat a
# compacted day as a missing one.
# --------------------------------------------------------------------------

def resolve_existing(p: Path) -> Path | None:
    """The readable file for ``p``: itself, its .gz, or None.

    Prefers the uncompressed file when both exist (a --keep compaction, or a
    re-pull landing beside an older archive).
    """
    if p.exists():
        return p
    gz = p.with_suffix(p.suffix + ".gz")
    return gz if gz.exists() else None


def open_corpus_text(p: Path):
    """Open a corpus JSONL for reading, transparently handling .jsonl.gz.

    Raises FileNotFoundError naming BOTH candidates, so a missing day never
    reads as "the compactor ate it" or vice versa.
    """
    resolved = resolve_existing(p)
    if resolved is None:
        raise FileNotFoundError(f"no corpus file at {p} (nor {p}.gz)")
    if resolved.suffix == ".gz":
        import gzip
        return gzip.open(resolved, "rt", encoding="utf-8")
    return resolved.open(encoding="utf-8")
