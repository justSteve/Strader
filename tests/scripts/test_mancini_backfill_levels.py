"""scripts/mancini_backfill_levels.py — letters in, parse artifacts out. [co-vp45h]"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "mancini_backfill_levels.py"


@pytest.fixture(scope="module")
def mb():
    spec = importlib.util.spec_from_file_location("mancini_backfill_levels", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mancini_backfill_levels"] = mod
    spec.loader.exec_module(mod)
    return mod


LINK = '<a href="https://substack.com/pub/tradecompanion/p/x">View in browser</a>'


def _html(title, header, supports, resistances, note=""):
    return (f"<html><body><p>{note}Preview.</p>{LINK}<h1>{title}</h1>"
            f"<p>Recap.</p><p>{header}</p>"
            f"<p>Supports are: {supports}.</p><p>Resistances are: {resistances}.</p>"
            "</body></html>")


def _write(dirp: Path, name: str, html: str) -> Path:
    p = dirp / name
    p.write_text(html, encoding="utf-8")
    return p


NOW = datetime(2026, 8, 19, 23, 0, tzinfo=timezone.utc)          # 18:00 CT 08-19


@pytest.fixture
def letters(tmp_path):
    d = tmp_path / "letters"
    d.mkdir()
    # Tue 08-11 evening -> Wed 08-12
    _write(d, "2026-08-11-191358.txt",
           _html("Bulls Keep Buying. August 12 Plan", "Trade Plan Wednesday",
                 "7783, 7777 (major), 7767", "7800 (Major), 7810-15"))
    # Wed 08-12 evening -> Thu 08-13
    _write(d, "2026-08-12-191542.txt",
           _html("Can It Continue? August 13 Plan", "Trade Plan Thursday",
                 "7790, 7780 (major)", "7820, 7830 (major)"))
    # Fri 08-14 evening with a typo title (a Saturday) -> Mon 08-17 via header,
    # and its Monday-noon resend (identical levels) clusters onto it
    monday = _html("Will The Trend Continue? August 15 Plan", "Trade Plan Monday",
                   "7750, 7740 (major)", "7800, 7815 (major)")
    _write(d, "2026-08-14-183405.txt", monday)
    _write(d, "2026-08-17-165100.txt", monday.replace("Preview.", "NOTE: This is a resend. Preview."))
    # a newsletter from someone else
    _write(d, "2026-08-13-090000.txt", "<html><body><p>55% off swim.</p></body></html>")
    # a truncated letter (no list sentences)
    _write(d, "2026-08-13-193226.txt",
           f"<html><body>{LINK}<h1>Too Long For Email. August 14 Plan</h1><p>Continue reading</p></body></html>")
    return d


def test_sent_at_from_blob_name(mb):
    assert mb.sent_at_from_blob_name("2025-06-24-202425.txt") == datetime(2025, 6, 24, 20, 24, 25, tzinfo=timezone.utc)


def test_is_mancini_by_link_or_by_list_sentences(mb):
    assert mb.is_mancini(LINK, "")
    assert mb.is_mancini("", "Supports are: 1. Resistances are: 2.")
    assert not mb.is_mancini("<p>Receipt from Adam Mancini's Trade Companion</p>", "Thank you")


def test_run_writes_one_artifact_per_session_and_a_manifest(mb, letters, tmp_path):
    parsed = tmp_path / "parsed"
    manifest = tmp_path / "manifest.jsonl"
    summary = mb.run(letters_dir=letters, parsed_dir=parsed, manifest=manifest,
                     force=False, dry_run=False, now=NOW)
    assert sorted(p.name for p in parsed.glob("*.json")) == [
        "2026-08-12.json", "2026-08-13.json", "2026-08-17.json"]
    doc = json.loads((parsed / "2026-08-12.json").read_text())
    assert doc["model"] == mb.BACKFILL_MODEL
    assert doc["date"] == "2026-08-12" and doc["instrument"] == "ES"
    prices = [(l["price"], l["kind"], l["label"]) for l in doc["levels"]]
    assert prices == [(7783.0, "support", ""), (7777.0, "support", "major"), (7767.0, "support", ""),
                      (7800.0, "resistance", "major"), (7810.0, "resistance", ""), (7815.0, "resistance", "")]
    assert doc["backfill"]["source_blob"] == "2026-08-11-191358.txt"
    assert doc["backfill"]["plan_day_rule"] == "title"
    assert doc["session_bias"] == "" and doc["commentary"] == []
    # the typo-titled Friday letter landed on Monday; the resend is a duplicate
    mon = json.loads((parsed / "2026-08-17.json").read_text())
    assert mon["backfill"]["plan_day_rule"] in ("weekday-header", "resend→weekday-header")
    rows = {json.loads(l)["blob"]: json.loads(l) for l in manifest.read_text().splitlines()}
    assert rows["2026-08-13-090000.txt"]["status"] == "skipped"
    assert rows["2026-08-13-193226.txt"]["status"] == "no-levels"
    statuses = sorted(r["status"] for b, r in rows.items()
                      if b in ("2026-08-14-183405.txt", "2026-08-17-165100.txt"))
    assert statuses == ["duplicate", "written"]
    assert summary["by_status"]["written"] == 3 and summary["errors"] == 0
    assert summary["by_status"]["duplicate"] == 1


def test_run_never_overwrites_an_in_session_parse(mb, letters, tmp_path):
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    rich = {"date": "2026-08-12", "instrument": "ES", "session_bias": "Bullish.",
            "levels": [{"price": 7783.0, "kind": "support", "label": "major · shelf", "source_quote": "7783"}],
            "commentary": [], "raw_excerpt": "", "model": "in-session", "parsed_at": "x"}
    (parsed / "2026-08-12.json").write_text(json.dumps(rich))
    summary = mb.run(letters_dir=letters, parsed_dir=parsed, manifest=None,
                     force=True, dry_run=False, now=NOW)
    assert json.loads((parsed / "2026-08-12.json").read_text()) == rich
    assert summary["by_status"]["kept-existing"] == 1


def test_run_fills_an_in_session_parse_that_has_no_levels(mb, letters, tmp_path):
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    empty = {"date": "2026-08-12", "instrument": "ES", "session_bias": "Bears in control.",
             "levels": [], "commentary": [], "raw_excerpt": "r", "model": "claude-opus-4-8", "parsed_at": "x"}
    (parsed / "2026-08-12.json").write_text(json.dumps(empty))
    summary = mb.run(letters_dir=letters, parsed_dir=parsed, manifest=None,
                     force=False, dry_run=False, now=NOW)
    doc = json.loads((parsed / "2026-08-12.json").read_text())
    assert doc["session_bias"] == "Bears in control." and doc["model"] == "claude-opus-4-8"
    assert len(doc["levels"]) == 6
    assert doc["backfill"]["filled_empty_levels_of"] == "claude-opus-4-8"
    assert json.loads((parsed / "2026-08-12.json.pre-backfill").read_text()) == empty
    assert summary["by_status"]["filled-empty"] == 1


def test_run_rewrites_backfill_artifacts_only_with_force(mb, letters, tmp_path):
    parsed = tmp_path / "parsed"
    mb.run(letters_dir=letters, parsed_dir=parsed, manifest=None, force=False, dry_run=False, now=NOW)
    first = (parsed / "2026-08-12.json").read_text()
    later = NOW.replace(hour=23, minute=30)
    s2 = mb.run(letters_dir=letters, parsed_dir=parsed, manifest=None, force=False, dry_run=False, now=later)
    assert s2["by_status"]["kept-backfill"] == 3
    assert (parsed / "2026-08-12.json").read_text() == first
    s3 = mb.run(letters_dir=letters, parsed_dir=parsed, manifest=None, force=True, dry_run=False, now=later)
    assert s3["by_status"]["rewritten"] == 3
    assert json.loads((parsed / "2026-08-12.json").read_text())["parsed_at"] == later.isoformat()


def test_run_stays_out_of_today_and_the_future(mb, letters, tmp_path):
    parsed = tmp_path / "parsed"
    # pretend it is the evening of 08-16: 08-17's letter is not a completed session
    summary = mb.run(letters_dir=letters, parsed_dir=parsed, manifest=None, force=False,
                     dry_run=False, now=datetime(2026, 8, 16, 23, 0, tzinfo=timezone.utc))
    assert sorted(p.name for p in parsed.glob("*.json")) == ["2026-08-12.json", "2026-08-13.json"]
    assert summary["by_status"]["not-yet"] == 1
    # an explicit --until wins over the clock
    summary = mb.run(letters_dir=letters, parsed_dir=parsed, manifest=None, force=False,
                     dry_run=False, now=NOW, until=date(2026, 8, 12))
    assert summary["by_status"]["not-yet"] == 2


def test_dry_run_writes_nothing(mb, letters, tmp_path):
    parsed = tmp_path / "parsed"
    manifest = tmp_path / "m.jsonl"
    summary = mb.run(letters_dir=letters, parsed_dir=parsed, manifest=manifest,
                     force=False, dry_run=True, now=NOW)
    assert not list(parsed.glob("*.json")) and not manifest.exists()
    assert summary["by_status"]["would-write"] == 3


def test_later_letter_for_the_same_day_supersedes(mb, tmp_path):
    d = tmp_path / "letters"
    d.mkdir()
    early = _html("Early Release. August 12 Plan", "Trade Plan Wednesday", "7700, 7690", "7750")
    update = _html("Updated After The Bell. August 12 Plan", "Trade Plan Wednesday", "7700, 7690, 7680", "7750, 7760")
    _write(d, "2026-08-11-183000.txt", early)
    _write(d, "2026-08-11-223000.txt", update)
    parsed = tmp_path / "parsed"
    summary = mb.run(letters_dir=d, parsed_dir=parsed, manifest=None, force=False, dry_run=False, now=NOW)
    doc = json.loads((parsed / "2026-08-12.json").read_text())
    assert doc["backfill"]["source_blob"] == "2026-08-11-223000.txt" and len(doc["levels"]) == 5
    assert summary["by_status"] == {"written": 1, "superseded": 1}


def test_pair_title_files_the_letter_for_both_sessions_unless_one_has_its_own(mb, tmp_path):
    d = tmp_path / "letters"
    d.mkdir()
    _write(d, "2026-07-02-193000.txt",
           _html("Dip Bought Next Week? July 3rd/6th Plan", "Trade Plan Monday", "7400, 7390", "7450"))
    parsed = tmp_path / "parsed"
    mb.run(letters_dir=d, parsed_dir=parsed, manifest=None, force=False, dry_run=False, now=NOW,
           has_session=lambda day: True)
    names = sorted(p.name for p in parsed.glob("*.json"))
    assert names == ["2026-07-03.json", "2026-07-06.json"]
    assert json.loads((parsed / "2026-07-06.json").read_text())["backfill"]["plan_day_rule"] == "title-pair-second"
    # a letter of Monday's own beats the shadow, whatever was sent when
    _write(d, "2026-07-05-150000.txt",
           _html("Fresh Plan. July 6 Plan", "Trade Plan Monday", "7410, 7395", "7460"))
    mb.run(letters_dir=d, parsed_dir=parsed, manifest=None, force=True, dry_run=False, now=NOW,
           has_session=lambda day: True)
    assert json.loads((parsed / "2026-07-06.json").read_text())["backfill"]["source_blob"] == "2026-07-05-150000.txt"
