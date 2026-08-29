"""Stage 10 renders by code and renames the colliding percentile keys. [st-h0xx]"""
import json
from datetime import date

import common
import render_events

DAY = date(2026, 8, 27)

RECS = [
    {"day": "2026-08-27", "ts": "2026-08-27T09:04:00-05:00", "path": "tape", "kind": "ABSORPTION-CLUSTER",
     "subtype": "START", "sig": "alert", "fields": {"bars": 2, "effort_pct": "82+", "effect_pct": "7-"},
     "line": "09:04 CT  EVENT ABSORPTION-CLUSTER START  sig=alert  bars=2  effort_pct=82+  effect_pct=7-"},
    {"day": "2026-08-27", "ts": "2026-08-27T10:56:00-05:00", "path": "tape", "kind": "CLIMAX",
     "subtype": "BUY", "sig": "alert", "fields": {"delta": 721, "pctl": 99.5},
     "line": "10:56 CT  EVENT CLIMAX BUY  sig=alert  delta=+721  pctl=99.5  vol=3603"},
    {"day": "2026-08-27", "ts": "2026-08-27T12:40:00-05:00", "path": "tape", "kind": "PLAN-LEVEL",
     "subtype": "TOUCH", "sig": "note", "fields": {"level": 7747},
     "line": "12:40 CT  EVENT PLAN-LEVEL TOUCH  sig=note  level=7747  close=7746"},
    {"day": "2026-08-27", "ts": "2026-08-27T12:47:00-05:00", "path": "tape", "kind": "PLAN-LEVEL",
     "subtype": "REJECTION", "sig": "alert", "fields": {"level": 7747},
     "line": "12:47 CT  EVENT PLAN-LEVEL REJECTION  sig=alert  level=7747  anchor=resistance"},
]


def test_render_renames_only_the_colliding_keys_and_slices_per_wake(state_dir):
    rd = common.run_dir(DAY)
    (rd / "00-inputs").mkdir()
    (rd / "00-inputs/events.rth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in RECS))
    (rd / "live-lane").mkdir()
    common.write_json(rd / "live-lane/session.json", {"sessions": [{"derived": {"wakes": [
        {"minute": "10:56", "lines": [RECS[1]["line"]], "bar": "10:56 CT  F1 (developing, n=1) conviction"},
        {"minute": "12:47", "lines": [RECS[3]["line"]], "bar": "12:47 CT  F2 (developing, n=2) absorption"},
    ]}}]})
    assert render_events.main([DAY.isoformat()]) == 0
    out = rd / "10-transcribe"
    window = (out / "window.txt").read_text().splitlines()
    assert window[0] == "09:04 CT  EVENT ABSORPTION-CLUSTER START  sig=alert  bars=2  effort_pct_dev=82+  effect_pct_dev=7-"
    assert window[1] == "10:56 CT  EVENT CLIMAX BUY  sig=alert  delta=+721  pctl_dev=99.5  vol=3603"
    assert window[2] == RECS[2]["line"] and window[3] == RECS[3]["line"]
    md = (out / "events.md").read_text()
    assert "| 10:56 | CLIMAX | BUY | alert | delta=721  pctl_dev=99.5 |" in md
    assert "**PLAN-LEVEL** —" in md and "The 4 events" in md
    # slice 1 holds only wake 1; slice 2 holds wake 1 and wake 2 — never the note
    s1 = (out / "wake-1056.txt").read_text().splitlines()
    s2 = (out / "wake-1247.txt").read_text().splitlines()
    assert s1 == [window[1], "bar: 10:56 CT  F1 (developing, n=1) conviction"]
    assert s2 == s1 + [window[3], "bar: 12:47 CT  F2 (developing, n=2) absorption"]
    assert not any("TOUCH" in ln for ln in s2)
    run = common.read_json(rd / "run.json")["render"]
    assert run["window_events"] == 4 and run["window_alerts"] == 3
    assert [s["wake"] for s in run["slices"]] == ["10:56", "12:47"]
    assert run["renamed_keys"] == ["effect_pct->effect_pct_dev", "effort_pct->effort_pct_dev", "pctl->pctl_dev"]


def test_render_without_a_live_session_writes_the_window_only(state_dir):
    rd = common.run_dir(DAY)
    (rd / "00-inputs").mkdir()
    (rd / "00-inputs/events.rth.jsonl").write_text(json.dumps(RECS[0]) + "\n")
    assert render_events.main([DAY.isoformat()]) == 0
    assert (rd / "10-transcribe/window.txt").exists()
    assert not list((rd / "10-transcribe").glob("wake-*.txt"))
