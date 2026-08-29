"""The live-lane extractor against a transcript built to the real shapes. [st-h0xx]

The fixture mirrors what the 2026-08-25 and 2026-08-27 transcripts actually
hold (probed 2026-08-28): an assistant ``tool_use`` Monitor row, its
``tool_result`` row with ``toolUseResult.taskId``, ``queue-operation`` enqueue
rows carrying the task-notification, a paired ``user`` row for one wake and
none for another (absorbed mid-turn), assistant text and a PushNotification in
the reply span, a human prompt that ends a span, a TaskStop. Timestamps are
UTC in the file, as they are in the real thing.
"""
import json
from datetime import date
from pathlib import Path

import pytest

import live_lane
from common import CT, hhmm

DAY = date(2026, 8, 27)
TID = "task0001"


def notif(line, bar):
    return (f"<task-notification>\n<task-id>{TID}</task-id>\n<summary>Monitor event: "
            f"\"Tier 2 wake channel\"</summary>\n<event>[TAPE] {line}\n        bar: {bar}</event>\n"
            f"If this event is something the user would act on now, send a PushNotification."
            f"\n</task-notification>")


A1 = "12:47 CT  EVENT PLAN-LEVEL REJECTION  sig=alert  level=7747  anchor=resistance  from=below  close=7745.75  vol=1808  delta=+148"
A2 = "13:00 CT  EVENT PLAN-LEVEL REJECTION  sig=alert  level=7745  anchor=resistance  from=below  close=7743.75  vol=900  delta=-40"
BAR1 = "12:47 CT  F2 (developing, n=768) absorption  ES o7745.75 h7747.5 l7745.75 c7745.75  vol 1808 d+148"
BAR2 = "13:00 CT  F1 (developing, n=781) conviction  ES o7744 h7745 l7743.5 c7743.75  vol 900 d-40"


def asst(ts, blocks, out=100, cr=1000, cw=10):
    return {"type": "assistant", "timestamp": ts, "cwd": "/root/projects/Strader",
            "sessionId": "sess1", "version": "2.1.247",
            "message": {"model": "claude-opus-5", "role": "assistant", "content": blocks,
                        "usage": {"input_tokens": 2, "output_tokens": out,
                                  "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}}}


def user_tool_result(ts, tool_use_id, content, extra=None):
    r = {"type": "user", "timestamp": ts,
         "message": {"role": "user", "content": [{"tool_use_id": tool_use_id,
                                                  "type": "tool_result", "content": content}]}}
    r.update(extra or {})
    return r


def rows_fixture():
    return [
        {"type": "user", "timestamp": "2026-08-27T17:00:00.000Z",
         "message": {"role": "user", "content": "please arm the watch"}},
        asst("2026-08-27T17:00:05.000Z", [{"type": "tool_use", "id": "t-read", "name": "Read",
                                            "input": {"file_path": "/root/projects/Strader/docs/playbooks/emitter-two-tier.md"}}]),
        user_tool_result("2026-08-27T17:00:06.000Z", "t-read", "…runbook…"),
        asst("2026-08-27T17:31:07.398Z", [{"type": "tool_use", "id": "t-mon", "name": "Monitor",
                                            "input": {"command": "bash /root/projects/Strader/tools/effort_event_watch.sh /var/moo/logs/effort-effect/2026-08-27.log",
                                                      "description": "Tier 2 wake channel", "persistent": True}}]),
        user_tool_result("2026-08-27T17:31:08.096Z", "t-mon", f"Monitor started (task {TID}, persistent)",
                         {"toolUseResult": {"taskId": TID, "persistent": True}}),
        asst("2026-08-27T17:31:20.000Z", [{"type": "text", "text": "Armed. Carrying on with other work."}]),
        # wake 1: absorbed mid-turn — enqueue, remove, attachment, no user row
        {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-08-27T17:48:22.355Z",
         "sessionId": "sess1", "content": notif(A1, BAR1)},
        {"type": "queue-operation", "operation": "remove", "timestamp": "2026-08-27T17:48:36.778Z",
         "sessionId": "sess1", "content": notif(A1, BAR1), "reason": "absorbed_mid_turn"},
        {"type": "attachment", "timestamp": "2026-08-27T17:48:22.355Z",
         "attachment": {"type": "queued_command", "prompt": notif(A1, BAR1), "commandMode": "task-notification"}},
        asst("2026-08-27T17:48:40.000Z", [{"type": "tool_use", "id": "t-tail", "name": "Bash",
                                            "input": {"command": "tail -3 /var/moo/logs/effort-effect/2026-08-27.log"}}]),
        user_tool_result("2026-08-27T17:48:41.000Z", "t-tail", BAR1),
        asst("2026-08-27T17:48:50.000Z", [{"type": "tool_use", "id": "t-push", "name": "PushNotification",
                                            "input": {"message": "[ALERT] 7747 rejected from below, vol 1808"}}]),
        user_tool_result("2026-08-27T17:48:51.000Z", "t-push", "sent"),
        asst("2026-08-27T17:49:16.987Z", [{"type": "text", "text": "First alert, 12:47: rejection at 7747, vol 1808, delta +148."}],
             out=500),
        # a human prompt ends the span
        {"type": "user", "timestamp": "2026-08-27T17:55:00.000Z",
         "message": {"role": "user", "content": "unrelated question"}},
        asst("2026-08-27T17:55:10.000Z", [{"type": "text", "text": "unrelated answer"}]),
        # wake 2: enqueue + paired user row
        {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-08-27T18:01:25.466Z",
         "sessionId": "sess1", "content": notif(A2, BAR2)},
        {"type": "user", "timestamp": "2026-08-27T18:01:25.476Z", "origin": {"kind": "task-notification"},
         "message": {"role": "user", "content": notif(A2, BAR2)}},
        asst("2026-08-27T18:01:40.000Z", [{"type": "text", "text": "Second alert, 13:00, 7745 held."}], out=300),
        asst("2026-08-27T18:02:00.000Z", [{"type": "tool_use", "id": "t-stop", "name": "TaskStop",
                                            "input": {"task_id": TID}}]),
        user_tool_result("2026-08-27T18:02:01.000Z", "t-stop", "stopped"),
        asst("2026-08-27T18:05:00.000Z", [{"type": "text", "text": "after the stop"}]),
    ]


@pytest.fixture
def transcript(tmp_path):
    p = tmp_path / "-root-projects-Strader" / "sess1.jsonl"
    p.parent.mkdir()
    p.write_text("".join(json.dumps(r) + "\n" for r in rows_fixture()), encoding="utf-8")
    return p


def test_extract_finds_arm_task_stop_wakes_replies_pushes_and_usage(transcript):
    res = live_lane.extract(DAY, [transcript])
    assert len(res["sessions"]) == 1
    s = res["sessions"][0]
    assert s["task_id"] == TID
    assert hhmm(s["armed_ct"]) == "12:31" and s["armed_ct"].tzinfo is not None
    assert hhmm(s["stopped_ct"]) == "13:02" and s["stopped_how"].startswith("TaskStop")
    assert s["runbook_read_before_first_wake"] is True
    assert s["project"] == "-root-projects-Strader" and s["model"] == "claude-opus-5"
    w1, w2 = s["wakes"]
    assert w1["lines"] == [A1] and w1["bar"] == BAR1
    assert hhmm(w1["delivered_ct"]) == "12:48"
    # the absorbed wake still gets its reply: the text after the attachment,
    # up to the human prompt; the push and the Bash tail are in the span
    assert w1["reply"]["text"] == "First alert, 12:47: rejection at 7747, vol 1808, delta +148."
    assert w1["reply"]["pushes"] == ["[ALERT] 7747 rejected from below, vol 1808"]
    assert w1["reply"]["tool_uses"] == ["Bash", "PushNotification"]
    assert w1["reply"]["usage"]["output_tokens"] == 100 + 100 + 500
    assert w1["reply"]["usage"]["assistant_rows"] == 3
    # the paired user row of wake 2 does not end its own span
    assert w2["lines"] == [A2]
    assert w2["reply"]["text"] == "Second alert, 13:00, 7745 held."
    assert w2["reply"]["pushes"] == []
    # nothing after the TaskStop is a wake, and the arm-to-end usage counts every assistant row
    assert s["usage_from_arm"]["assistant_rows"] == 8
    assert s["usage_from_arm"]["models"] == {"claude-opus-5": 8}


def test_arm_on_another_day_is_ignored(transcript):
    assert live_lane.extract(date(2026, 8, 26), [transcript])["sessions"] == []


def test_tape_lines_parse_single_and_batched_wakes():
    single = notif(A1, BAR1)
    assert live_lane._tape_lines(single) == ([A1], BAR1)
    batched = (f"<event>[TAPE] 2 events: {A1}\n        + {A2}\n        bar: {BAR2}</event>")
    assert live_lane._tape_lines(batched) == ([A1, A2], BAR2)


def test_discover_transcripts_by_mtime_and_content(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    (root / "p1").mkdir(parents=True)
    (root / "p2").mkdir(parents=True)
    hit = root / "p1" / "a.jsonl"
    miss = root / "p2" / "b.jsonl"
    hit.write_text('{"x": "bash tools/effort_event_watch.sh log"}\n')
    miss.write_text('{"x": "nothing here"}\n')
    monkeypatch.setattr(live_lane, "TRANSCRIPT_ROOT", root)
    import os, time
    day = date.today()
    found = live_lane.discover_transcripts(day)
    assert found == [hit]
    # an old file is not scanned even if it mentions the script
    old = time.time() - 30 * 86400
    os.utime(hit, (old, old))
    assert live_lane.discover_transcripts(day) == []


def test_main_refuses_when_transcript_and_rule_disagree(transcript, state_dir, monkeypatch, capsys):
    """A log whose alerts do not match the transcript's wakes is a refusal,
    not a page: the comparison would score the analyst on lines it never saw."""
    import common
    rd = common.run_dir(DAY)
    (rd / "00-inputs").mkdir()
    # the rule will derive 12:47 and 13:00 from these lines, plus a 12:55 the
    # transcript never received (it sits between the wakes, before the stop)
    lines = [BAR1, A1, "12:55 CT  EVENT CLIMAX BUY  sig=alert  delta=+700  pctl=99.6  vol=3000", BAR2, A2]
    (rd / "00-inputs" / "log.txt").write_text("\n".join(lines) + "\n")
    common.update_run_json(DAY, "inputs", {"live_log": {"present": True,
                                                        "start_ct": "2026-08-27T09:54:47-05:00"}})
    with pytest.raises(common.LaneError, match=r"wake set in the transcript .* != wake set derived"):
        live_lane.main([DAY.isoformat(), "--transcript", str(transcript)])
    run = common.read_json(rd / "run.json")
    assert run["live_lane"]["refused"] == "wake sets differ"
    assert run["live_lane"]["derived"] == ["12:47", "12:55", "13:00"]
    # --no-assert records the mismatch instead, for diagnosis
    assert live_lane.main([DAY.isoformat(), "--transcript", str(transcript), "--no-assert"]) == 0
    assert common.read_json(rd / "run.json")["live_lane"]["sessions_detail"][0]["wake_sets_match"] is False


def test_main_writes_session_and_wakes_when_sets_agree(transcript, state_dir):
    import common
    rd = common.run_dir(DAY)
    (rd / "00-inputs").mkdir()
    (rd / "00-inputs" / "log.txt").write_text("\n".join([BAR1, A1, BAR2, A2]) + "\n")
    common.update_run_json(DAY, "inputs", {"live_log": {"present": True,
                                                        "start_ct": "2026-08-27T09:54:47-05:00"}})
    rc = live_lane.main([DAY.isoformat(), "--transcript", str(transcript)])
    assert rc == 0
    wakes = [json.loads(l) for l in (rd / "live-lane/wakes.jsonl").read_text().splitlines()]
    assert [w["lines"][0][:5] for w in wakes] == ["12:47", "13:00"]
    run = common.read_json(rd / "run.json")
    assert run["live_lane"]["wakes"] == 2 and run["live_lane"]["pushes"] == 1
    assert run["live_lane"]["sessions_detail"][0]["wake_sets_match"] is True
    sess = common.read_json(rd / "live-lane/session.json")
    assert sess["sessions"][0]["derived"]["wakes"][0]["minute"] == "12:47"


def test_main_records_a_day_with_no_live_session(tmp_path, state_dir, monkeypatch):
    import common
    monkeypatch.setattr(live_lane, "TRANSCRIPT_ROOT", tmp_path / "none")
    (tmp_path / "none").mkdir()
    rd = common.run_dir(DAY)
    rc = live_lane.main([DAY.isoformat()])
    assert rc == 0
    assert common.read_json(rd / "run.json")["live_lane"]["status"] == "no live session"
    assert (rd / "live-lane/wakes.jsonl").read_text() == ""
