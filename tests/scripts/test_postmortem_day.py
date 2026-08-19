"""CLI wiring for the day post-mortem: which day, which pass, where it writes,
and that tests never reach the desk. [co-7kgte]"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "postmortem" / "2026-08-18-trimmed.jsonl"
CT = ZoneInfo("America/Chicago")


def _load():
    path = REPO_ROOT / "scripts" / "postmortem_day.py"
    spec = importlib.util.spec_from_file_location("postmortem_day", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_resolve_day_same_day_is_today_next_morning_is_previous_session():
    m = _load()
    now = datetime(2026, 8, 19, 15, 30, tzinfo=CT)            # a Wednesday
    assert m.resolve_day(None, "same-day", now) == date(2026, 8, 19)
    assert m.resolve_day(None, "next-morning", now) == date(2026, 8, 18)
    mon = datetime(2026, 8, 17, 8, 27, tzinfo=CT)
    assert m.resolve_day(None, "next-morning", mon) == date(2026, 8, 14)
    assert m.resolve_day("2026-08-11", "same-day", now) == date(2026, 8, 11)


def test_run_live_pass_writes_ledger_and_page_without_publishing(tmp_path, monkeypatch):
    m = _load()
    published = []
    monkeypatch.setattr(m, "publish", lambda *a, **k: published.append(a) or 0)
    rc = m.run_live_pass(day=date(2026, 8, 18), pass_name="same-day",
                         record=FIXTURE, root=tmp_path, knobs=m.pm.Knobs(),
                         now=datetime(2026, 8, 18, 15, 30, tzinfo=CT),
                         letter=None, publish_pages=False)
    assert rc == 0
    res = json.loads((tmp_path / "2026-08-18.json").read_text())
    assert res["pass"] == "same-day" and res["census"]["n_calls_measured"] >= 1
    assert (tmp_path / "pages" / "postmortem-2026-08-18.md").exists()
    assert (tmp_path / "pages" / "postmortem-latest.md").read_text() == \
        (tmp_path / "pages" / "postmortem-2026-08-18.md").read_text()
    assert published == []


def test_run_live_pass_without_record_writes_a_saying_so_page_and_exits_2(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "publish", lambda *a, **k: 0)
    rc = m.run_live_pass(day=date(2026, 8, 20), pass_name="same-day",
                         record=tmp_path / "absent.jsonl", root=tmp_path, knobs=m.pm.Knobs(),
                         now=datetime(2026, 8, 20, 15, 30, tzinfo=CT),
                         letter=None, publish_pages=False)
    assert rc == 2
    md = (tmp_path / "pages" / "postmortem-2026-08-20.md").read_text()
    assert "No feeder record for 2026-08-20" in md


def test_find_letter_for_session_picks_that_evenings_letter(tmp_path):
    m = _load()
    (tmp_path / "2026-08-18-185443.txt").write_text("<html>x</html>")
    (tmp_path / "2026-08-17-182204.txt").write_text("<html>y</html>")
    assert m.find_letter_for_session(date(2026, 8, 18), letters_dir=tmp_path).name == "2026-08-18-185443.txt"
    assert m.find_letter_for_session(date(2026, 8, 19), letters_dir=tmp_path) is None


def test_parsed_kinds_for_reads_the_parse_and_never_raises(tmp_path):
    m = _load()
    (tmp_path / "2026-08-18.json").write_text(json.dumps(
        {"levels": [{"price": 7742, "kind": "resistance"}, {"price": 7716.0, "kind": "support"},
                    {"price": None, "kind": "support"}]}))
    assert m.parsed_kinds_for(date(2026, 8, 18), parsed_dir=tmp_path) == \
        {7742.0: "resistance", 7716.0: "support"}
    assert m.parsed_kinds_for(date(2026, 8, 19), parsed_dir=tmp_path) == {}
    (tmp_path / "2026-08-20.json").write_text("not json")
    assert m.parsed_kinds_for(date(2026, 8, 20), parsed_dir=tmp_path) == {}


def test_next_morning_pass_reads_recap_from_the_letter(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "publish", lambda *a, **k: 0)
    letter = tmp_path / "2026-08-18-185443.txt"
    letter.write_text("Trade Recap/Daily Summary\nThe first was the Failed Breakdown of 7720 at 2:18PM. "
                      "Then a Level Reclaim of 7797 at 10:15AM.\nTrade Plan Wednesday\n")
    rc = m.run_live_pass(day=date(2026, 8, 18), pass_name="next-morning",
                         record=FIXTURE, root=tmp_path, knobs=m.pm.Knobs(),
                         now=datetime(2026, 8, 19, 8, 27, tzinfo=CT),
                         letter=letter, publish_pages=False)
    assert rc == 0
    res = json.loads((tmp_path / "2026-08-18.json").read_text())
    assert res["recap"]["status"] == "received"
    tiers = {(r["level"], r["tier"]) for r in res["recap"]["rows"]}
    assert (7720.0, "EXACT") in tiers and (7797.0, "MISS") in tiers     # 13:18 CT confirm on 7720 = 2:18PM ET
    assert (tmp_path / "recaps" / "2026-08-18.json").exists()


def test_backfill_one_day_worker_returns_summary_row(tmp_path, monkeypatch):
    m = _load()
    segs = m.pm.load_live_segments(FIXTURE)     # stand in for the replay
    monkeypatch.setattr(m.pm, "segments_from_replay", lambda day, *, bar_n, mancini, kinds=None: segs)
    monkeypatch.setattr(m, "mancini_levels_for", lambda day: [7720.0, 7724.0])
    row = m.backfill_one(date(2026, 8, 18), root=tmp_path, knobs=m.pm.Knobs(),
                         now=datetime(2026, 8, 19, 0, 0, tzinfo=CT))
    assert row["day"] == "2026-08-18" and row["status"] == "ok"
    assert row["n_confirmed"] >= 1 and set(row["legs_at"]) == {"4", "6", "8"}
    assert set(row["by_lid"]) == {"ge3", "lt3"}
    rows = [json.loads(l) for l in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert rows and all(r["pass"] == "backfill" and r["source"] == "replay" for r in rows)


def test_backfill_one_day_never_raises(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "mancini_levels_for", lambda day: (_ for _ in ()).throw(RuntimeError("boom")))
    row = m.backfill_one(date(2026, 8, 18), root=tmp_path, knobs=m.pm.Knobs(),
                         now=datetime(2026, 8, 19, 0, 0, tzinfo=CT))
    assert row["status"].startswith("error: RuntimeError")
