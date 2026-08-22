"""The verbs over a day: read, arm/yes, price, go, stand down, persistence. [st-79z.3]"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from strader.intent.cli import load_chain, main
from strader.intent.session import Session
from strader.intent.tos import fixture_status, occ_symbols, tos_string

FIX = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "intent"
DAY = dt.date(2026, 8, 22)


def _session(tmp_path: Path) -> Session:
    return Session(plan_dir=tmp_path, day=DAY)


def _chain():
    return load_chain(FIX / "chain-6320.json")


def test_read_stages_the_intent_and_persists(tmp_path):
    s = _session(tmp_path)
    out = s.read((FIX / "constructed-day-read.txt").read_text())
    assert "Levels (ES unless said)" in out and "First move down" in out
    assert s.pending is not None and s.plan.intents == []          # staged, not armed
    again = Session(plan_dir=tmp_path, day=DAY)
    assert len(again.plan.levels) == 3 and again.plan.regime.day_type == "b-day"
    assert (tmp_path / "2026-08-22.json").is_file()
    # the staged intent survives a restart (a one-line-per-process pane says yes next)
    assert again.pending is not None and "Waiting for a yes or no" in again.show()
    assert "waiting for a yes or no" in again.go()                  # and go refuses meanwhile
    again.yes()
    assert again.plan.intents and again.plan.intents[0].confirmed and again.pending is None


def test_stale_pending_is_refused_not_armed(tmp_path):
    s = _session(tmp_path)
    s.arm("the failed breakdown at sixty-four twelve, long on the reclaim")
    s.plan.pending_at = "2026-08-22T09:00:00-05:00"                 # long ago
    out = s.yes()
    assert "tape has moved" in out and s.pending is None and s.plan.intents == []


def test_go_refuses_until_priced_and_confirmed(tmp_path):
    s = _session(tmp_path)
    s.read((FIX / "constructed-day-read.txt").read_text())
    assert "waiting for a yes or no" in s.go()                        # the staged branch comes first
    out = s.price(_chain())
    assert "Buying 2 butterfly calls, 6300 / 6320 / 6340" in out and "0.55 debit" in out and "$110 total" in out
    assert "inferred" in out                                          # no TOS fixture yet
    assert "waiting for a yes or no" in s.go()
    s.yes()
    assert s.plan.intents and s.plan.intents[0].confirmed
    out = s.go()
    assert "Staged, nothing sent" in out
    assert "BUY +2 BUTTERFLY SPX 100 (Weeklys) 22 AUG 26 6300/6320/6340 CALL @.55 LMT" in out
    staged = list((tmp_path / "staged").glob("*-butterfly.json"))
    assert len(staged) == 1
    rec = json.loads(staged[0].read_text())
    assert rec["tos_status"] == "inferred" and rec["occ"] == [
        "SPXW  260822C06300000", "SPXW  260822C06320000", "SPXW  260822C06320000", "SPXW  260822C06340000"]


def test_no_drops_the_pending_intent(tmp_path):
    s = _session(tmp_path)
    s.arm("the failed breakdown at sixty-four twelve, short on the reclaim")
    assert s.pending is not None and s.pending.looks_inverted
    assert "Dropped" in s.no() and s.pending is None and s.plan.intents == []
    assert "Nothing priced" in s.go()                                  # nothing waiting, nothing priced


def test_es_center_needs_a_basis(tmp_path):
    s = _session(tmp_path)
    s.mark("sixty-four twelve is the magnet, mancini")
    s.fly("on the magnet, twenty wide, zero dte calls")
    assert "no basis" in s.price(_chain())
    assert "Basis 92" in s.basis("92")
    out = s.price(_chain())
    assert "6300 / 6320 / 6340" in out                                 # 6412 − 92 = 6320


def test_single_first_itm(tmp_path):
    s = _session(tmp_path)
    s.single("first strike in the money, calls, two lots")
    out = s.price(_chain())
    assert "Buying 2 call, 6320" in out and "1.55 debit" in out         # spot 6321.5 → 6320 call at the ask
    o = s.plan.orders[0]
    assert tos_string(o) == "BUY +2 SPX 100 (Weeklys) 22 AUG 26 6320 CALL @1.55 LMT"
    assert occ_symbols(o) == ["SPXW  260822C06320000"]


def test_stand_down_and_frame(tmp_path):
    s = _session(tmp_path)
    s.single("calls")
    s.price(_chain())
    assert "Standing down" in s.stand_down() and s.plan.orders == []
    assert "SPX from here on" in s.frame("spx") and s.plan.frame_default == "SPX"
    assert "ES or SPX" in s.frame("nope")


def test_handle_routes_verbs_and_falls_back_to_read(tmp_path):
    s = _session(tmp_path)
    assert "No level in" in s.handle("mark nothing here")
    assert "Nothing is waiting" in s.handle("yes")
    out = s.handle("b-day so far, bears control below sixty-four seventy-four")
    assert "Bears control below 6474 ES" in out
    assert "did not understand" in s.handle("the cat sat on the mat")


def test_fixture_status_tracks_the_tos_pass():
    assert fixture_status("BUTTERFLY") in ("inferred", "verified")


def test_cli_once(tmp_path, capsys):
    rc = main(["--once", "call b-day, bears control below sixty-four seventy-four",
               "--plan-dir", str(tmp_path), "--day", "2026-08-22"])
    assert rc == 0
    assert "Day type b-day" in capsys.readouterr().out
    rc = main(["--once", "price", "--plan-dir", str(tmp_path), "--day", "2026-08-22"])
    assert "No chain loaded" in capsys.readouterr().out
    rc = main(["--once", "show", "--chain", str(tmp_path / "missing.json"), "--plan-dir", str(tmp_path)])
    assert rc == 2
