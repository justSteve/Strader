"""Overnight refresh — re-render the plan doc from the full window. [st-vxbw]"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from runbook.mancini import refresh as refresh_mod
from runbook.mancini import run as run_mod
from runbook.mancini.schema import Commentary, Level, ParseResult, Trigger

CT = ZoneInfo("America/Chicago")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Off the real desk and the real parsed/ store; never open a browser."""
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "DESK_REPORTS", tmp_path / "myDesk" / "reports" / "mancini")
    monkeypatch.setattr(run_mod, "DESK_REFRESH", tmp_path / "absent-refresh.sh")
    monkeypatch.setattr(run_mod, "DESK_HTML", tmp_path / "desk-plan.html")
    monkeypatch.setattr(run_mod, "DESK_HTML_SCRIPT", tmp_path / "absent-desk-html.sh")
    monkeypatch.setattr(refresh_mod, "DESK_PAGE", tmp_path / "desk-page.html")
    monkeypatch.setattr(refresh_mod, "POWERSHELL", tmp_path / "absent-powershell.exe")
    (tmp_path / "myDesk").mkdir()  # desk_root must exist for _emit_desk_plan
    return tmp_path


def _parse(model="in-session:test") -> ParseResult:
    r = ParseResult(
        date="2026-08-18", instrument="ES", session_bias="bullish above 7797",
        levels=[Level(price=7797, kind="resistance", label="major", source_quote="7797 (major)"),
                Level(price=7724, kind="support", label="major", source_quote="7724 (major)"),
                Level(price=7695, kind="support", source_quote="7695")],
        commentary=[Commentary(text="Reclaims of 7797 remain of interest.",
                               trigger=Trigger(type="price_cross", anchor_prices=[7797]),
                               source_quote="Reclaims of 7797 remain of interest.")],
    )
    r.model = model
    r.parsed_at = "2026-08-18T06:28:35+00:00"
    return r


def _store(tmp_path, result: ParseResult) -> Path:
    root = run_mod.PARSED_ROOT
    root.mkdir(parents=True, exist_ok=True)
    p = root / f"{result.date}.json"
    p.write_text(json.dumps(result.to_dict()))
    return p


def _ms(y, m, d, hh, mm) -> int:
    return int(datetime(y, m, d, hh, mm, tzinfo=CT).astimezone(timezone.utc)
               .timestamp() * 1000)


def _candles():
    # 7724 support: closes 3 pts through (broken), then closes back above
    # (reclaimed). 7797 resistance: touched and held (close below). 7695: never.
    return [
        {"datetime": _ms(2026, 8, 17, 15, 0), "open": 7790, "high": 7799, "low": 7788, "close": 7792},
        {"datetime": _ms(2026, 8, 17, 21, 0), "open": 7730, "high": 7732, "low": 7718, "close": 7720},
        {"datetime": _ms(2026, 8, 18, 4, 0),  "open": 7720, "high": 7735, "low": 7719, "close": 7731},
        {"datetime": _ms(2026, 8, 18, 8, 10), "open": 7731, "high": 7760, "low": 7730, "close": 7758},
    ]


def test_no_parse_is_rc3_and_writes_nothing(tmp_path, capsys):
    out = refresh_mod.refresh("2026-08-18", fetch=lambda *a, **k: _candles())
    assert out.rc == 3
    assert "run /mancini-parse" in out.summary
    assert not (run_mod.DESK_REPORTS / "mancini-es-2026-08-18.md").exists()
    assert "nothing refreshed" in capsys.readouterr().out


def test_lists_only_parse_is_not_refreshed(tmp_path):
    _store(tmp_path, _parse(model="deterministic-lists"))
    out = refresh_mod.refresh("2026-08-18", fetch=lambda *a, **k: _candles())
    assert out.rc == 3
    assert not (run_mod.DESK_REPORTS / "mancini-es-2026-08-18.md").exists()


def test_refresh_rerenders_the_same_doc_from_the_full_window(tmp_path, capsys):
    stored = _store(tmp_path, _parse())
    before = stored.read_text()
    now = datetime(2026, 8, 18, 8, 15, tzinfo=CT)
    out = refresh_mod.refresh("2026-08-18", fetch=lambda *a, **k: _candles(), now=now)
    assert out.rc == 0
    doc = run_mod.DESK_REPORTS / "mancini-es-2026-08-18.md"
    assert out.doc == doc and doc.exists()
    text = doc.read_text()
    # Same plan doc: bias and notes are still there, levels untouched on disk.
    assert "bullish above 7797" in text
    assert "Reclaims of 7797 remain of interest." in text
    assert stored.read_text() == before
    # The interaction section is the full window, titled honestly and stamped.
    assert "Level interaction since the letter" in text
    assert "refreshed Tue 08:15 CT" in text
    assert "Interaction section refreshed Tue 08:15 CT." in text
    assert "Mon 15:00 CT → Tue 08:10 CT (4 candles)" in text
    assert "**7724 major support: RECLAIMED**" in text
    assert "7797 major resistance: tested and held" in text
    assert out.counts == {"broken": 0, "reclaimed": 1, "held": 1, "untouched": 1}
    printed = capsys.readouterr().out
    assert "1 reclaimed, 1 tested-held, 1 untouched of 3" in printed
    assert "mancini-es-2026-08-18.md" in printed


def test_fetch_failure_degrades_to_a_note_not_an_error(tmp_path):
    _store(tmp_path, _parse())

    def _dead(*a, **k):
        raise RuntimeError("Schwab price history HTTP 401")

    out = refresh_mod.refresh("2026-08-18", fetch=_dead, quiet=True)
    assert out.rc == 0
    text = (run_mod.DESK_REPORTS / "mancini-es-2026-08-18.md").read_text()
    assert "Overnight data unavailable (Schwab price history HTTP 401)" in text
    assert "window unavailable" in out.summary


def test_open_browser_is_best_effort_without_powershell(tmp_path):
    (tmp_path / "desk-page.html").write_text("<p>x</p>")
    assert refresh_mod.open_in_browser(tmp_path / "desk-page.html") is False
    assert refresh_mod.open_in_browser(tmp_path / "missing.html") is False


def test_prepare_only_good_case_runs_the_refresh(tmp_path, monkeypatch, capsys):
    """The 08:15 cron's good case (a real parse exists) re-renders the doc. [st-vxbw]"""
    _store(tmp_path, _parse())
    calls = []

    def _fake_refresh(day, **kw):
        calls.append((day, kw))
        return refresh_mod.RefreshOutcome(rc=0, day=day, summary="overnight refresh: ok")

    monkeypatch.setattr(refresh_mod, "refresh", _fake_refresh)
    nl = tmp_path / "nl.txt"
    nl.write_text("ES Trade Plan. Supports are: 7724. Resistances are: 7797.\n")
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-08-18",
                       "--prepare-only", "--no-clip",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 0
    assert calls == [("2026-08-18", {"open_browser": False, "quiet": True})]
    assert "overnight refresh: ok" in capsys.readouterr().out


def test_prepare_only_no_desk_skips_the_refresh(tmp_path, monkeypatch):
    _store(tmp_path, _parse())
    monkeypatch.setattr(refresh_mod, "refresh",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    nl = tmp_path / "nl.txt"
    nl.write_text("ES Trade Plan. Supports are: 7724. Resistances are: 7797.\n")
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-08-18",
                       "--prepare-only", "--no-clip", "--no-desk",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 0
