"""corpus_daily: never append the session batch onto a live-captured tape.
[Watcher V2 plan Risk 15; Phase 4]

Measured 2026-08-11: the live ES capture logged one reconnect note, the
healthy-check called the stream unhealthy, the 08:30-15:00 CT batch appended,
and the day closed at 496,011 cycles against ~260k on its neighbours — a
doubled tape under the prior-day profile seed.
"""
import json
from datetime import date
from pathlib import Path

import scripts.corpus_daily as cd


def _manifest(tmp_path: Path, monkeypatch, streams: dict, day=date(2026, 8, 11)) -> date:
    d = tmp_path / day.isoformat()
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"streams": streams}), encoding="utf-8")
    monkeypatch.setattr(cd, "manifest_path", lambda dd: tmp_path / dd.isoformat() / "manifest.json")
    return day


def test_live_rows_with_a_reconnect_note_are_not_healthy_but_do_have_rows(tmp_path, monkeypatch):
    day = _manifest(tmp_path, monkeypatch, {"databento_glbx_es": {
        "cycles": 496011,
        "errors": ["reconnect #1: BentoError: Gateway timeout: 40 second(s) since last message (possible gap)"],
        "last_pull_utc": "2026-08-12T11:30:34Z"}})
    assert cd.stream_healthy_in_manifest(day, "databento_glbx_es") is False
    has, errs = cd.stream_has_rows_in_manifest(day, "databento_glbx_es")
    assert has is True and len(errs) == 1 and "reconnect" in errs[0]


def test_absent_or_empty_stream_has_no_rows(tmp_path, monkeypatch):
    day = _manifest(tmp_path, monkeypatch, {"databento_opra": {"cycles": 0, "errors": []}})
    assert cd.stream_has_rows_in_manifest(day, "databento_glbx_es") == (False, [])
    assert cd.stream_has_rows_in_manifest(day, "databento_opra") == (False, [])
    assert cd.stream_has_rows_in_manifest(date(2026, 8, 12), "databento_glbx_es") == (False, [])


def test_main_skips_the_batch_when_live_rows_exist(tmp_path, monkeypatch, caplog):
    """The orchestrator path: rows + an error note → the ES pull is SKIPPED with
    a warning naming the errors; --force still pulls."""
    day = _manifest(tmp_path, monkeypatch, {
        "databento_glbx_es": {"cycles": 496011, "errors": ["reconnect #1: gap"]},
        "databento_opra": {"cycles": 5, "errors": []}})
    calls = []
    monkeypatch.setattr(cd, "run_pull", lambda script, d, extra=None, pass_date=True: (calls.append(script), (0, ""))[1])
    monkeypatch.setattr(cd, "run_token_health", lambda: None)
    monkeypatch.setattr(cd, "mbp1_authorization", lambda: (False, "test"))
    for name in ("run_gexbot_hist", "run_internals", "run_schwab_batch", "run_gate", "write_health"):
        if hasattr(cd, name):
            monkeypatch.setattr(cd, name, lambda *a, **k: None)
    caplog.set_level("INFO")
    rc = cd.main(["--date", day.isoformat(), "--dry-run"])
    assert "corpus_pull_databento_es.py" not in calls
    assert any("would double the tape" in r.getMessage() and "reconnect #1: gap" in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]
