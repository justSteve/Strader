"""EOD fact-packet tests. [st-z92a]

The packet's job is to make a trading day's facts survive whether or not anyone
is at the desk. What must hold: it never writes on a non-trading day, it splits
GEX rows against the real collect window, it distinguishes a HARD gap (a day's
tape is unusable and cannot be re-collected) from a soft one, and its --audit
recognises a Day Close entry only when one was genuinely written.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load():
    path = REPO / "scripts" / "eod_packet.py"
    spec = importlib.util.spec_from_file_location("_eod_packet_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(spec.name, None)
    return mod


eod = _load()


# --------------------------------------------------------------------------
# GEX window audit — the gate's own witness
# --------------------------------------------------------------------------

def _gex_file(tmp_path: Path, stamps: list[str]) -> Path:
    p = tmp_path / "gexbot.jsonl"
    p.write_text("\n".join(json.dumps({"ts_pull_utc": s}) for s in stamps) + "\n")
    return p


def test_session_rows_count_as_in_window(tmp_path):
    """2026-08-10 14:00Z == 09:00 CT, inside 07:30-15:05."""
    out = eod.gex_window_audit(_gex_file(tmp_path, ["2026-08-10T14:00:00Z"]),
                               date(2026, 8, 10))
    assert out["rows_in_session"] == 1
    assert out["rows_outside_session"] == 0


def test_overnight_rows_count_as_outside(tmp_path):
    """The 2026-08-07 failure: the poller ran to 23:59 CT."""
    out = eod.gex_window_audit(_gex_file(tmp_path, ["2026-08-08T04:30:00Z"]),
                               date(2026, 8, 7))
    assert out["rows_in_session"] == 0
    assert out["rows_outside_session"] == 1


def test_preopen_ramp_rows_are_in_window(tmp_path):
    """12:45Z == 07:45 CT — the ramp is collected on purpose."""
    out = eod.gex_window_audit(_gex_file(tmp_path, ["2026-08-10T12:45:00Z"]),
                               date(2026, 8, 10))
    assert out["rows_in_session"] == 1


def test_rows_just_past_the_window_are_outside(tmp_path):
    """20:30Z == 15:30 CT, past the 15:05 stop."""
    out = eod.gex_window_audit(_gex_file(tmp_path, ["2026-08-10T20:30:00Z"]),
                               date(2026, 8, 10))
    assert out["rows_outside_session"] == 1


def test_early_close_shrinks_the_in_window_span(tmp_path):
    """13:00 CT is inside the window on a normal day and outside on a noon close."""
    stamps = ["2026-11-27T19:00:00Z"]          # 13:00 CT
    out = eod.gex_window_audit(_gex_file(tmp_path, stamps), date(2026, 11, 27))
    assert out["rows_outside_session"] == 1


def test_unparseable_rows_are_counted_not_swallowed(tmp_path):
    p = tmp_path / "gexbot.jsonl"
    p.write_text('{"ts_pull_utc": "2026-08-10T14:00:00Z"}\nnot json\n')
    out = eod.gex_window_audit(p, date(2026, 8, 10))
    assert out["unparseable"] == 1
    assert out["rows_in_session"] == 1


def test_missing_gex_file_is_none_not_a_crash(tmp_path):
    assert eod.gex_window_audit(tmp_path / "nope.jsonl", date(2026, 8, 10)) is None


# --------------------------------------------------------------------------
# Day Close detection — --audit is only as good as this
# --------------------------------------------------------------------------

def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(eod, "DAYS_ACTIVITY", tmp_path / "DaysActivity.md")
    monkeypatch.setattr(eod, "ARCHIVE", tmp_path / "archive")
    (tmp_path / "archive").mkdir(exist_ok=True)


def test_a_day_close_in_the_days_own_file_counts(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "DaysActivity.md").write_text(
        "# DaysActivity - 2026-08-10\n\n## 15:30 - Day Close\n\nstuff\n")
    assert eod.day_close_exists(date(2026, 8, 10))


def test_a_dated_day_close_in_another_days_file_counts(monkeypatch, tmp_path):
    """Closing Friday on a Monday writes a dated heading into Monday's file."""
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "DaysActivity.md").write_text(
        "# DaysActivity - 2026-08-10\n\n## 2026-08-07 09:00 - Day Close [2026-08-07]\n")
    assert eod.day_close_exists(date(2026, 8, 7))


def test_an_archived_day_close_counts(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "archive" / "DaysActivity-2026-08-07.md").write_text(
        "# DaysActivity - 2026-08-07\n\n## 15:30 - Day Close\n")
    assert eod.day_close_exists(date(2026, 8, 7))


def test_merely_mentioning_the_date_in_prose_does_not_count(monkeypatch, tmp_path):
    """The bug this guards: a substring match would score a mention as a record."""
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "DaysActivity.md").write_text(
        "# DaysActivity - 2026-08-10\n\n## 15:30 - Day Close\n\n"
        "We should still close 2026-08-07 at some point.\n")
    assert eod.day_close_exists(date(2026, 8, 10))
    assert not eod.day_close_exists(date(2026, 8, 7))


def test_a_session_handoff_is_not_a_day_close(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "DaysActivity.md").write_text(
        "# DaysActivity - 2026-08-10\n\n## 15:30 - Session Handoff\n")
    assert not eod.day_close_exists(date(2026, 8, 10))


def test_no_file_at_all_is_not_closed(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    assert not eod.day_close_exists(date(2026, 8, 10))


# --------------------------------------------------------------------------
# Audit scope
# --------------------------------------------------------------------------

def test_audit_ignores_days_before_the_ritual_existed(monkeypatch, tmp_path):
    """Without this the audit reports every trading day in repo history."""
    _patch_paths(monkeypatch, tmp_path)
    assert all(date.fromisoformat(r["day"]) >= eod.RITUAL_START
               for r in eod.audit(back=400))


def test_audit_reports_an_unclosed_day_once_the_ritual_is_live(monkeypatch, tmp_path):
    """RITUAL_START is in the future as of this commit, so pin it back to prove
    the audit does find gaps rather than merely returning nothing."""
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(eod, "RITUAL_START", date(2026, 8, 3))
    rows = eod.audit(back=10)
    assert rows, "expected auditable days with the ritual start pinned back"
    assert all(not r["day_close"] for r in rows)


def test_audit_never_lists_a_weekend(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    for r in eod.audit(back=400):
        assert date.fromisoformat(r["day"]).weekday() < 5


# --------------------------------------------------------------------------
# Hard vs soft gaps — what cron is allowed to alert on
# --------------------------------------------------------------------------

def test_expected_stream_at_zero_cycles_is_a_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(eod, "CORPUS", tmp_path)
    d = tmp_path / "2026-08-10"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"streams": {
        "databento_glbx_es": {"cycles": 0, "errors": []},
        "databento_glbx_es_mbp1": {"cycles": 5, "errors": []},
        "gexbot": {"cycles": 400, "errors": []},
    }}))
    _facts, gaps = eod.gather_data(date(2026, 8, 10))
    assert any("databento_glbx_es landed 0 cycles" in g for g in gaps)


def test_a_missing_expected_stream_is_a_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(eod, "CORPUS", tmp_path)
    d = tmp_path / "2026-08-10"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"streams": {}}))
    _facts, gaps = eod.gather_data(date(2026, 8, 10))
    assert len(gaps) == len(eod.EXPECTED_STREAMS)


def test_an_ungraded_call_is_a_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(eod, "CALLS", tmp_path)
    (tmp_path / "2026-08-10-strader-x.json").write_text(
        json.dumps({"by": "strader", "claim": "reversion into the close"}))
    calls, gaps = eod.gather_calls(date(2026, 8, 10))
    assert len(calls) == 1
    assert any("no outcome recorded" in g for g in gaps)


def test_a_graded_call_is_not_a_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(eod, "CALLS", tmp_path)
    (tmp_path / "2026-08-10-strader-x.json").write_text(
        json.dumps({"by": "strader", "claim": "reversion", "outcome": "held to settle"}))
    _calls, gaps = eod.gather_calls(date(2026, 8, 10))
    assert not gaps


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_a_non_trading_day_writes_no_packet(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(eod, "EOD_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["eod_packet.py", "--day", "2026-08-08"])
    assert eod.main() == 0
    assert "Saturday" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.md"))


def test_force_overrides_the_non_trading_day_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(eod, "EOD_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv",
                        ["eod_packet.py", "--day", "2026-08-08", "--force"])
    eod.main()
    assert (tmp_path / "2026-08-08.md").exists()


def test_render_marks_hard_gaps(monkeypatch):
    pk = {
        "day": "2026-08-10", "weekday": "Monday", "day_type": "regular session",
        "close_ct": "15:00", "generated_at_ct": "2026-08-10 15:15",
        "data": {"corpus_dir": None, "streams": [], "files": {}, "notes": [],
                 "gex_window": None},
        "calls": [], "plan": {"mancini_commentary": None, "mancini_entries": 0,
                              "parity_run_log": None},
        "work": {"commits": [], "beads_closed": [], "beads_created": []},
        "gaps": ["soft thing", "gexbot landed 0 cycles"],
        "hard_gaps": ["gexbot landed 0 cycles"],
    }
    text = eod.render(pk)
    assert "- **[HARD]** gexbot landed 0 cycles" in text
    assert "- soft thing" in text


@pytest.mark.parametrize("word", ["Day Close", "draws no conclusions"])
def test_the_packet_says_what_it_is_not(monkeypatch, word):
    """The packet must keep announcing that it is facts only — the whole split
    with /eod falls over if a future reader treats it as the record itself."""
    pk = eod.build(date(2026, 8, 7))
    assert word in eod.render(pk)
