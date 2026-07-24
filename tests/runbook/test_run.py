"""CLI wiring tests for the Mancini Runbook. [co-7lyf / co-i10h]

No live LLM call: the parse step is monkeypatched. These cover the gate, the
halt/keep-last-good error paths, and the brief render.
"""
import json

import pytest

from runbook.mancini import run as run_mod
from runbook.mancini import parse as parse_mod
from runbook.mancini.schema import ParseResult, Level, Commentary, Trigger
from runbook.mancini.validate import ValidationResult

SOURCE = "ES Trade Plan. Supports are: 5800. Holding 5800 targets 5840.\n"


@pytest.fixture(autouse=True)
def _isolate_desk(tmp_path_factory, monkeypatch):
    """Keep every test off the real steves-desk publication paths. [st-eo0]"""
    root = tmp_path_factory.mktemp("desk")
    monkeypatch.setattr(run_mod, "DESK_REPORTS", root / "reports" / "mancini")
    monkeypatch.setattr(run_mod, "DESK_REFRESH", root / "absent-refresh.sh")
    return root


def _good_outcome() -> parse_mod.ParseOutcome:
    result = ParseResult(
        date="2026-06-29", instrument="ES", session_bias="bullish above 5800",
        levels=[Level(price=5800, kind="support", source_quote="5800")],
        commentary=[Commentary(
            text="Holding 5800 targets 5840.",
            trigger=Trigger(type="price_zone", anchor_prices=[5800, 5840]),
            source_quote="Holding 5800 targets 5840.")],
    )
    return parse_mod.ParseOutcome(result=result, validation=ValidationResult(ok=True))


def test_happy_path(tmp_path, monkeypatch, capsys):
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")
    monkeypatch.setattr(parse_mod, "parse", lambda *a, **k: _good_outcome())

    rc = run_mod.main([
        "--file", str(nl), "--no-gate",
        "--store-root", str(tmp_path / "commentary"),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "MANCINI MORNING BRIEF" in out
    assert "5800" in out
    # last-good written
    assert (tmp_path / "parsed" / "2026-06-29.json").exists()
    saved = json.loads((tmp_path / "parsed" / "2026-06-29.json").read_text())
    assert saved["instrument"] == "ES"
    # deterministic chart Pine written
    pine_path = tmp_path / "charts" / "2026-06-29.pine"
    assert pine_path.exists()
    assert "//@version=6" in pine_path.read_text()


def test_gate_failure_halts(tmp_path, monkeypatch):
    # A manifest with zero cycles fails the gate; parse must never run.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "date": "2026-06-29",
        "streams": {
            "databento_glbx_es": {"cycles": 0, "errors": [], "last_pull_utc": ""},
            "databento_opra": {"cycles": 0, "errors": [], "last_pull_utc": ""},
        },
    }))
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)

    def _boom(*a, **k):
        raise AssertionError("parse must not run when the gate fails")

    monkeypatch.setattr(parse_mod, "parse", _boom)
    rc = run_mod.main(["--file", str(nl), "--manifest", str(manifest)])
    assert rc == 2


def test_gate_day_decoupled_from_parse_day(tmp_path, monkeypatch):
    """Decision A (co-i10h): the gate checks the most-recent-completed session,
    while the parse/result carries the plan-day. The two must not cross-wire —
    Databento is T+1, so gating on the plan-day would halt every pre-close run.
    """
    from datetime import date
    from runbook.datastream import gate as gate_mod

    plan_day = "2026-07-01"        # session the letter plans for (--date / result.date)
    gate_day = date(2026, 6, 30)   # most-recent-completed session the gate checks

    captured = {}

    def _fake_check(*, manifest_path=None, day=None, **kw):
        captured["day"] = day
        captured["manifest_path"] = manifest_path
        return gate_mod.GateResult(ok=True, reasons=[], checked={"stub": True})

    # Undated parse result so the plan-day fallback (result.date = day) applies.
    result = ParseResult(
        date="", instrument="ES", session_bias="",
        levels=[Level(price=5800, kind="support", source_quote="5800")],
        commentary=[],
    )
    outcome = parse_mod.ParseOutcome(result=result, validation=ValidationResult(ok=True))

    monkeypatch.setattr(run_mod, "_resolve_gate_day", lambda: gate_day)
    monkeypatch.setattr(gate_mod, "check", _fake_check)
    monkeypatch.setattr(parse_mod, "parse", lambda *a, **k: outcome)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")

    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    rc = run_mod.main([
        "--file", str(nl), "--date", plan_day,
        "--store-root", str(tmp_path / "commentary"),
    ])
    assert rc == 0
    # Gate saw the completed-session day derived by _resolve_gate_day — NOT the plan-day.
    assert captured["day"] == gate_day
    assert captured["manifest_path"] is None
    # The published parse is dated for the plan-day, not the gate day.
    assert (tmp_path / "parsed" / f"{plan_day}.json").exists()
    assert not (tmp_path / "parsed" / f"{gate_day.isoformat()}.json").exists()


def test_validation_failure_keeps_last_good(tmp_path, monkeypatch):
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    bad = parse_mod.ParseOutcome(
        result=_good_outcome().result,
        validation=ValidationResult(ok=False, errors=["price 6100 not found"],
                                    missing_prices=[6100]),
    )
    monkeypatch.setattr(parse_mod, "parse", lambda *a, **k: bad)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    rc = run_mod.main([
        "--file", str(nl), "--no-gate", "--store-root", str(tmp_path / "c"),
    ])
    assert rc == 4
    # nothing published
    assert not (tmp_path / "parsed").exists()


def _raise(*a, **k):
    raise RuntimeError("ANTHROPIC_API_KEY_DIRECT not set")


def test_extraction_error_without_lists_is_graceful(tmp_path, monkeypatch):
    # No Supports/Resistances list sentences -> hybrid impossible -> rc 3.
    nl = tmp_path / "nl.txt"
    nl.write_text("ES Trade Plan. Holding above the pivot targets more.\n")
    monkeypatch.setattr(parse_mod, "parse", _raise)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    rc = run_mod.main(["--file", str(nl), "--no-gate",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 3


def test_extraction_error_with_lists_publishes_hybrid(tmp_path, monkeypatch, capsys):
    # Interpretive leg down + lists present -> deterministic levels publish,
    # commentary flagged pending. [st-ze6 hybrid mode]
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(parse_mod, "parse", _raise)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-06-29",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 0
    saved = json.loads((tmp_path / "parsed" / "2026-06-29.json").read_text())
    assert saved["model"] == "deterministic-lists"
    assert [lv["price"] for lv in saved["levels"]] == [5800.0]
    assert saved["commentary"] == []
    assert "pending" in saved["session_bias"]


def test_hybrid_never_clobbers_richer_parse(tmp_path, monkeypatch):
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    parsed_root = tmp_path / "parsed"
    parsed_root.mkdir()
    richer = {"model": "in-session:claude-fable-5", "levels": [1, 2, 3]}
    (parsed_root / "2026-06-29.json").write_text(json.dumps(richer))
    monkeypatch.setattr(parse_mod, "parse", _raise)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", parsed_root)
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-06-29",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 0
    # untouched
    assert json.loads((parsed_root / "2026-06-29.json").read_text()) == richer


def test_desk_plan_renders_bias_notes_and_bolded_majors():
    result = ParseResult(
        date="2026-07-24", instrument="ES", session_bias="bears control below 7474",
        levels=[Level(price=7474, kind="resistance", label="major"),
                Level(price=7459, kind="resistance"),
                Level(price=7412, kind="support", label="major")],
        commentary=[Commentary(
            text="Flush and recovery of 7412 is actionable.",
            trigger=Trigger(type="price_zone", anchor_prices=[7412]))],
        model="in-session:test", parsed_at="2026-07-24T12:00:00+00:00")
    doc = run_mod._render_desk_plan(result)
    assert "# Mancini — ES — 2026-07-24 (Friday) plan" in doc
    assert "bears control below 7474" in doc
    assert "Flush and recovery of 7412 is actionable." in doc
    assert "**7474** · 7459" in doc      # major bolded, minor not
    assert "**7412**" in doc


def test_desk_doc_written_on_publish(tmp_path, monkeypatch, _isolate_desk):
    # Hybrid publish path also lands the desk doc; missing refresh script is
    # non-fatal (logged, doc still written).
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(parse_mod, "parse", _raise)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-06-29",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 0
    doc = run_mod.DESK_REPORTS / "mancini-es-2026-06-29.md"
    assert doc.exists()
    assert "commentary pending" in doc.read_text()


def test_no_desk_flag_suppresses_publication(tmp_path, monkeypatch, _isolate_desk):
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(parse_mod, "parse", lambda raw, **kw: _good_outcome())
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-06-29",
                       "--store-root", str(tmp_path / "c"), "--no-desk"])
    assert rc == 0
    assert not (run_mod.DESK_REPORTS / "mancini-es-2026-06-29.md").exists()
