"""The number check and the page. [st-h0xx]"""
import json
from datetime import date

import compare
import common

BAR = "12:47 CT  F2 (developing, n=768) absorption  ES o7745.75 h7747.5 l7745.75 c7745.75  vol 1808 d+148  net +0.00 rng 1.75"
ALERT = "12:47 CT  EVENT PLAN-LEVEL REJECTION  sig=alert  level=7747  anchor=resistance  from=below  close=7745.75  extreme=7747.5  through=0.50  back=1.25  vol=1808  delta=+148"
LATER = "13:00 CT  EVENT SUPERLATIVE MAX-VOL  sig=alert  vol=60323  prev=13156@08:30  delta=-317"


def test_numbers_in_skips_clock_times_and_small_counts_and_normalises():
    text = ("Rejection at 7747.50 on vol 1,808 with delta +148 at 12:47; three bars later "
            "the day max 60,323 printed, -317 delta, 21pt drop in 6 min.")
    assert compare.numbers_in(text) == ["7747.50", "1808", "148", "60323", "-317"]


def test_number_check_finds_values_not_strings_and_respects_the_minute():
    reply = "7747.5 rejected, vol 1808, delta 148; then max vol 60323 later."
    c = compare.number_check(reply, [ALERT], BAR, [BAR, ALERT, LATER], "12:47")
    assert c["found"] == ["7747.5", "1808", "148"]
    assert c["not_found"] == ["60323"]           # printed at 13:00, after the wake's minute
    c2 = compare.number_check(reply, [ALERT], BAR, [BAR, ALERT, LATER], "13:00")
    assert c2["not_found"] == []
    assert "7747.50" in compare.numbers_in("close 7747.50")
    assert compare.number_check("close 7747.50", [ALERT], None, [], "12:47")["found"] == ["7747.50"]


def test_derived_sums_are_reported_not_found():
    c = compare.number_check("about 1,500 of buying delta over the hour", [ALERT], BAR, [BAR], "12:47")
    assert c["not_found"] == ["1500"]


def test_page_renders_wakes_coverage_and_provenance(state_dir):
    day = date(2026, 8, 27)
    rd = common.run_dir(day)
    (rd / "00-inputs").mkdir()
    (rd / "00-inputs/log.txt").write_text(BAR + "\n" + ALERT + "\n")
    (rd / "live-lane").mkdir()
    wake = {"task_id": "t", "session_id": "s", "project": "-root-projects-COO", "row": 1, "index": 1,
            "delivered_ct": "2026-08-27T12:48:22-05:00", "lines": [ALERT], "bar": BAR,
            "reply": {"text": "Rejection at 7747.5, vol 1808, delta 148, and about 2,000 more.",
                      "pushes": ["[ALERT] 7747 held"], "tool_uses": [],
                      "usage": {"output_tokens": 5, "cache_read_input_tokens": 6,
                                "cache_creation_input_tokens": 7, "input_tokens": 8, "assistant_rows": 1},
                      "first_reply_ct": "2026-08-27T12:48:36-05:00",
                      "last_reply_ct": "2026-08-27T12:49:16-05:00"}}
    (rd / "live-lane/wakes.jsonl").write_text(json.dumps(wake) + "\n")
    common.write_json(rd / "live-lane/session.json", {"sessions": [{"derived": {
        "wakes": [{"minute": "12:47"}], "undelivered": ["09:53 CT  EVENT CLIMAX BUY  sig=alert  delta=+700"],
        "ambiguous": []}}]})
    common.update_run_json(day, "inputs", {
        "strader_head": "abc1234", "commits": {"scripts/live_effort_effect.py": "c1",
                                               "market/orderflow/tape_events.py": "c2",
                                               "config/tape_events.yaml": "c3"},
        "knobs": {"climax_min_atoms": "60"},
        "events": {"total": 113, "alerts": 29, "rth_total": 52, "rth_alerts": 16, "rth_notes": 36},
        "live_log": {"present": True, "event_lines": 113, "event_lines_equal_replay": True,
                     "last_closed_minute": "18:43", "segments": 1,
                     "start_ct": "2026-08-27T09:54:47-05:00"},
        "levels": {"loaded": 59, "source": "letter", "parsed_at": "2026-08-27T08:47:04Z",
                   "sha256": "deadbeefcafe0000", "raw_rows": 59},
        "log_body": {"lines": 4357, "seconds": 9.0, "equal_live_last_segment": True}})
    common.update_run_json(day, "live_lane", {"sessions_detail": [{
        "project": "-root-projects-COO", "cwd": "/root/projects/COO", "model": "claude-opus-5",
        "task_id": "t", "armed_ct": "2026-08-27T12:31:07-05:00", "stopped_ct": "2026-08-27T18:44:13-05:00",
        "stopped_how": "session end", "runbook_read_before_first_wake": False,
        "wake_sets_match": True, "usage_from_arm": {"output_tokens": 1, "assistant_rows": 2}}]})
    rc = compare.main([day.isoformat(), "--no-publish"])
    assert rc == 0
    md = (rd / "page.md").read_text()
    assert "1 wake(s) delivered of 16 cash-session alerts (29 in the whole day); 1 push(es); 1 figure(s)" in md
    assert "not operating under the analyst contract" in md
    assert "**not found: 2000**" in md
    assert "Pushed to Steve's phone" in md and "[ALERT] 7747 held" in md
    assert "Undelivered alert lines" in md and "09:53 CT  EVENT CLIMAX BUY" in md
    assert "Scorer started 09:54:47" in md
    assert "fingerprint `deadbeefcafe`" in md
    assert "climax_min_atoms=60" in md
    run = common.read_json(rd / "run.json")
    assert run["compare"]["figures_not_found"] == 1
    assert run["coverage"] == {"delivered": 1, "undelivered": 1, "ambiguous": 0}


def test_page_for_a_day_with_no_live_session(state_dir):
    day = date(2026, 8, 26)
    common.update_run_json(day, "inputs", {"events": {"alerts": 41, "rth_alerts": 20}})
    common.update_run_json(day, "live_lane", {"status": "no live session"})
    rc = compare.main([day.isoformat(), "--no-publish"])
    assert rc == 0
    md = (common.run_dir(day) / "page.md").read_text()
    assert "no live session. 20 cash-session alerts (41 in the whole day). A labelling-only day." in md
    assert "every one of the 41 alerts is coverage" in md
