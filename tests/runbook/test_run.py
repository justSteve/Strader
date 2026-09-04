"""CLI wiring tests for the Mancini Runbook. [co-7lyf / co-i10h / st-26q5]

The runbook calls no model — the interpretive leg is an in-session extraction
handed in via --extraction-json. Tests that mean to exercise that leg must pass
the flag (``_extraction()`` writes a stub file); the parse step itself is
monkeypatched. Without the flag the run takes the hybrid branch by design, and
``parse()`` is never called at all. These cover the gate, the
halt/keep-last-good error paths, hybrid mode, and the brief render.
"""
import json
import os
import shutil
import time

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
    # Without this a test run overwrites the browser page Steve keeps open. [st-lo2]
    monkeypatch.setattr(run_mod, "DESK_HTML", root / "desk-plan.html")
    return root


def _extraction(tmp_path, payload=None) -> str:
    """Write a stub in-session extraction and return its path. [st-26q5]

    Content only has to be loadable JSON — every test that uses this also
    monkeypatches parse_mod.parse, so the dict never reaches ParseResult. What
    it exercises is the CLI taking the interpretive branch rather than hybrid.
    """
    p = tmp_path / "extraction.json"
    p.write_text(json.dumps(payload if payload is not None else {
        "date": "2026-06-29", "instrument": "ES", "session_bias": "bullish above 5800",
        "levels": [{"price": 5800, "kind": "support", "source_quote": "5800"}],
        "commentary": [],
    }))
    return str(p)


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
        "--extraction-json", _extraction(tmp_path),
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
        "--extraction-json", _extraction(tmp_path),
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
        "--file", str(nl), "--no-gate",
        "--extraction-json", _extraction(tmp_path),
        "--store-root", str(tmp_path / "c"),
    ])
    assert rc == 4
    # nothing published
    assert not (tmp_path / "parsed").exists()


def _raise(*a, **k):
    raise RuntimeError("malformed extraction")


def test_no_extraction_without_lists_is_graceful(tmp_path, monkeypatch):
    # No extraction supplied and no Supports/Resistances list sentences to fall
    # back on -> hybrid impossible -> rc 3.
    nl = tmp_path / "nl.txt"
    nl.write_text("ES Trade Plan. Holding above the pivot targets more.\n")
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    rc = run_mod.main(["--file", str(nl), "--no-gate",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 3


def test_bad_extraction_json_keeps_last_good(tmp_path, monkeypatch):
    # An extraction WAS supplied but does not survive parse -> never silently
    # demote to hybrid; halt and keep last-good. [st-26q5]
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(parse_mod, "parse", _raise)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    rc = run_mod.main(["--file", str(nl), "--no-gate",
                       "--extraction-json", _extraction(tmp_path),
                       "--store-root", str(tmp_path / "c")])
    assert rc == 3
    assert not (tmp_path / "parsed").exists()


def test_no_extraction_with_lists_publishes_hybrid(tmp_path, monkeypatch, capsys):
    # No in-session extraction + lists present -> deterministic levels publish,
    # commentary flagged pending. [st-ze6 hybrid mode]
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
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


@pytest.mark.skipif(shutil.which("marked") is None or not run_mod.DESK_HTML_SCRIPT.exists(),
                    reason="needs marked on PATH and COO's desk-html.sh")
def test_desk_html_written_on_publish(tmp_path, monkeypatch, _isolate_desk):
    # The browser page Steve refreshes is regenerated by the parse itself. [st-lo2]
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(parse_mod, "parse", lambda raw, **kw: _good_outcome())
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-06-29",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 0
    page = run_mod.DESK_HTML.read_text()
    assert page.startswith("<!DOCTYPE html>")
    assert page.rstrip().endswith("</body></html>")
    assert "Mancini — ES — 2026-06-29" in page


def test_desk_html_absent_renderer_is_non_fatal(monkeypatch, _isolate_desk, tmp_path):
    # No fallback renderer by design — the whole point of co-wp0db was to stop
    # Strader carrying its own stylesheet. Missing script means no page. [st-qx4]
    doc = tmp_path / "plan.md"
    doc.write_text("# plan\n")
    monkeypatch.setattr(run_mod, "DESK_HTML_SCRIPT", tmp_path / "absent-desk-html.sh")
    assert run_mod._render_desk_html(doc) is None
    assert not run_mod.DESK_HTML.exists()


def test_desk_html_exit_3_is_quiet(monkeypatch, _isolate_desk, tmp_path, caplog):
    # Exit 3 = no marked on PATH, routine under a bare cron. Degrade at info,
    # not warning — but keep stderr, because desk-html.sh also exits 3 on a real
    # marked failure and the text is all that separates them. [st-qx4]
    doc = tmp_path / "plan.md"
    doc.write_text("# plan\n")
    stub = tmp_path / "desk-html.sh"
    stub.write_text("#!/usr/bin/env bash\necho 'marked not found on PATH' >&2\nexit 3\n")
    stub.chmod(0o755)
    monkeypatch.setattr(run_mod, "DESK_HTML_SCRIPT", stub)
    with caplog.at_level("INFO", logger="runbook.mancini"):
        assert run_mod._render_desk_html(doc) is None
    assert not run_mod.DESK_HTML.exists()
    rec = [r for r in caplog.records if "desk html skipped" in r.message]
    assert rec and rec[0].levelname == "INFO"
    assert "marked not found on PATH" in rec[0].getMessage()


def test_desk_html_real_failure_warns(monkeypatch, _isolate_desk, tmp_path, caplog):
    doc = tmp_path / "plan.md"
    doc.write_text("# plan\n")
    stub = tmp_path / "desk-html.sh"
    stub.write_text("#!/usr/bin/env bash\necho 'no such file' >&2\nexit 2\n")
    stub.chmod(0o755)
    monkeypatch.setattr(run_mod, "DESK_HTML_SCRIPT", stub)
    with caplog.at_level("INFO", logger="runbook.mancini"):
        assert run_mod._render_desk_html(doc) is None
    assert any(r.levelname == "WARNING" and "rc=2" in r.getMessage()
               for r in caplog.records)


def test_desk_html_deadline_kills_the_renderer_and_everything_under_it(monkeypatch, _isolate_desk,
                                                                        tmp_path, caplog):
    """The renderer's real work is a grandchild (marked, the plain-words model
    pass). Before 2026-09-04 the 60 s timeout killed the shell and left it
    running — the orphan shape the ICM lane showed on 09-02/03. [co-8b60y]"""
    doc = tmp_path / "plan.md"
    doc.write_text("# plan\n")
    marker, pidfile = tmp_path / "orphan-marker", tmp_path / "gc.pid"
    stub = tmp_path / "desk-html.sh"
    stub.write_text(f'#!/usr/bin/env bash\n( echo $BASHPID > "{pidfile}"; sleep 3; '
                    f'touch "{marker}" ) &\nsleep 60\n')
    stub.chmod(0o755)
    monkeypatch.setattr(run_mod, "DESK_HTML_SCRIPT", stub)
    monkeypatch.setattr(run_mod, "DESK_RENDER_TIMEOUT_S", 1)
    t0 = time.monotonic()
    with caplog.at_level("INFO", logger="runbook.mancini"):
        assert run_mod._render_desk_html(doc) is None
    assert time.monotonic() - t0 < 15
    assert any(r.levelname == "WARNING" and "timed out after 1 s" in r.getMessage()
               for r in caplog.records)
    deadline = time.monotonic() + 5
    gc = int(pidfile.read_text())
    while time.monotonic() < deadline:
        try:
            os.kill(gc, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("the grandchild survived the deadline")
    time.sleep(3.5)
    assert not marker.exists()


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


# --- clipboard policy [st-0x9, refined by st-llor] --------------------------
# Regression pair for 2026-07-30, when three pytest runs during unrelated work
# replaced the day's 60-level payload in Steve's clipboard with the two-line
# _good_outcome fixture. Two independent things have to hold: the suite can
# never reach clip.exe (tests/conftest.py, which is what `_no_clipboard` is),
# and a HYBRID/diagnostic parse must not even attempt the push.
#
# st-llor then made a completed INTERPRETIVE parse push by default — that run is
# the Mancini Parse procedure and loading the payload is its last step. The
# distinction under test is therefore extraction-vs-no-extraction, not flag
# presence; both halves of it matter.

def _run_for_payload(tmp_path, monkeypatch, extra_args):
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(parse_mod, "parse", lambda raw, **kw: _good_outcome())
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-06-29",
                       "--store-root", str(tmp_path / "c"), "--no-desk",
                       *extra_args])
    assert rc == 0
    return tmp_path / "charts" / "2026-06-29.payload.txt"


def test_payload_file_written_but_clipboard_untouched_by_default(
        tmp_path, monkeypatch, _no_clipboard):
    # Hybrid run (no --extraction-json): file yes, clipboard no.
    payload_path = _run_for_payload(tmp_path, monkeypatch, [])
    # The file is the durable artifact and is always produced...
    assert payload_path.exists()
    assert "5800" in payload_path.read_text()
    # ...but nothing was pushed. This is the assertion that matters.
    assert _no_clipboard == []


def test_clip_flag_pushes_the_payload(tmp_path, monkeypatch, _no_clipboard):
    payload_path = _run_for_payload(tmp_path, monkeypatch, ["--clip"])
    assert _no_clipboard == [payload_path.read_text()]


def test_interpretive_parse_pushes_payload_by_default(
        tmp_path, monkeypatch, _no_clipboard):
    # The procedure concludes by loading the Daily Payload — no flag needed.
    payload_path = _run_for_payload(
        tmp_path, monkeypatch, ["--extraction-json", _extraction(tmp_path)])
    assert _no_clipboard == [payload_path.read_text()]


def test_no_clip_suppresses_the_interpretive_push(
        tmp_path, monkeypatch, _no_clipboard):
    # Backfill / renderer check: interpretive, but hands off the clipboard.
    payload_path = _run_for_payload(
        tmp_path, monkeypatch,
        ["--extraction-json", _extraction(tmp_path), "--no-clip"])
    assert payload_path.exists()
    assert _no_clipboard == []


def test_clip_and_no_clip_are_mutually_exclusive(tmp_path, monkeypatch):
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    with pytest.raises(SystemExit):
        run_mod.main(["--file", str(nl), "--no-gate", "--clip", "--no-clip"])


def test_hybrid_skip_still_reloads_the_richer_payload(
        tmp_path, monkeypatch, _no_clipboard):
    """The 08:15 pre-open job's real work when an in-session parse ran overnight.

    The parse is a no-op — it must not clobber the richer stored result — but the
    clipboard is hours stale by then, so --clip must still reload the payload
    built from the RICHER parse, not from the deterministic lists. [st-llor]
    """
    parsed_root = tmp_path / "parsed"
    parsed_root.mkdir()
    rich = _good_outcome().result
    rich.model = "in-session:opus-5"
    (parsed_root / "2026-06-29.json").write_text(json.dumps(rich.to_dict()))

    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", parsed_root)
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")
    # No --extraction-json: the cron is always hybrid. --clip is what it passes.
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--date", "2026-06-29",
                       "--no-desk", "--clip",
                       "--store-root", str(tmp_path / "c")])
    assert rc == 0
    # The richer parse survived untouched...
    kept = json.loads((parsed_root / "2026-06-29.json").read_text())
    assert kept["model"] == "in-session:opus-5"
    # ...and the clipboard was reloaded from it anyway.
    assert len(_no_clipboard) == 1
    assert "5800" in _no_clipboard[0]


def test_failed_parse_never_loads_the_clipboard(tmp_path, monkeypatch, _no_clipboard):
    # An extraction was supplied but did not survive parse -> rc 3. The payload
    # push is the LAST step precisely so a halted run leaves the clipboard
    # holding whatever it held before. [st-llor]
    nl = tmp_path / "nl.txt"
    nl.write_text(SOURCE)
    monkeypatch.setattr(parse_mod, "parse", _raise)
    monkeypatch.setattr(run_mod, "PARSED_ROOT", tmp_path / "parsed")
    monkeypatch.setattr(run_mod, "CHARTS_ROOT", tmp_path / "charts")
    rc = run_mod.main(["--file", str(nl), "--no-gate", "--no-desk",
                       "--extraction-json", _extraction(tmp_path),
                       "--store-root", str(tmp_path / "c")])
    assert rc == 3
    assert _no_clipboard == []


def test_human_surfaces_show_central_time_not_utc():
    """Steve, 2026-08-18: 'anytime we come across a timestamp written in UTC we
    need to update it to CT' — the desk header, brief and Pine header render
    parsed_at in Central; the stored ISO UTC value is untouched."""
    assert run_mod._ct("2026-08-18T06:28:35.070186+00:00") == "2026-08-18 01:28 CT"
    assert run_mod._ct("2026-08-18T06:28:35Z") == "2026-08-18 01:28 CT"
    assert run_mod._ct("") == ""
    assert run_mod._ct("not-a-time") == "not-a-time"
    result = _good_outcome().result
    result.parsed_at = "2026-08-18T06:28:35+00:00"
    doc = run_mod._render_desk_plan(result)
    assert "parsed 2026-08-18 01:28 CT" in doc
    assert "06:28Z" not in doc
    brief = run_mod._render_brief(result)
    assert "parsed 2026-08-18 01:28 CT" in brief
    assert result.parsed_at == "2026-08-18T06:28:35+00:00"
