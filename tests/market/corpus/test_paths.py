"""Corpus day-resolution tests. [co-i10h]

most_recent_session_day is the single source of truth for "which day's data is
current", shared by the ingestion orchestrator (scripts/corpus_daily.py) and the
datastream gate. Databento is T+1, so it must resolve to the last *completed*
session (prev weekday), never today.
"""
from datetime import date, datetime

from market.corpus.paths import CENTRAL, most_recent_session_day


def _ct(iso: str) -> datetime:
    """A US/Central-aware datetime from a bare 'YYYY-MM-DDTHH:MM' string."""
    return datetime.fromisoformat(iso).replace(tzinfo=CENTRAL)


def test_weekday_returns_previous_day():
    # Tue -> Mon.
    assert most_recent_session_day(_ct("2026-06-30T08:00")) == date(2026, 6, 29)
    # Wed -> Tue.
    assert most_recent_session_day(_ct("2026-07-01T12:00")) == date(2026, 6, 30)


def test_monday_walks_back_over_weekend_to_friday():
    assert most_recent_session_day(_ct("2026-06-29T08:00")) == date(2026, 6, 26)


def test_saturday_and_sunday_resolve_to_friday():
    assert most_recent_session_day(_ct("2026-06-27T09:00")) == date(2026, 6, 26)
    assert most_recent_session_day(_ct("2026-06-28T09:00")) == date(2026, 6, 26)


def test_never_returns_today():
    # Whatever "now" is, the resolved day is strictly earlier — today's Databento
    # batch is not yet complete, so gating on it would be a false halt.
    now = _ct("2026-07-01T23:59")
    assert most_recent_session_day(now) < now.date()


def test_corpus_root_honours_the_env_override(tmp_path, monkeypatch):
    """STRADER_CORPUS_ROOT relocates the corpus tree for every helper (Phase 4
    seam). Read at import, so exercise it through a fresh import."""
    import importlib
    import sys
    monkeypatch.setenv("STRADER_CORPUS_ROOT", str(tmp_path / "corpus-elsewhere"))
    sys.modules.pop("market.corpus.paths", None)
    try:
        mod = importlib.import_module("market.corpus.paths")
        assert mod.CORPUS_ROOT == tmp_path / "corpus-elsewhere"
        assert mod.gexbot_orderflow_1s_path(date(2026, 8, 14)) == \
            tmp_path / "corpus-elsewhere" / "2026-08-14" / "gexbot_orderflow_1s.jsonl"
    finally:
        monkeypatch.delenv("STRADER_CORPUS_ROOT")
        sys.modules.pop("market.corpus.paths", None)
        importlib.import_module("market.corpus.paths")     # restore the real one for later tests
