#!/usr/bin/env python3
"""Stage 00, live side — what the live analyst was shown and said. [st-h0xx]

The live analyst has no output file. It is a Claude Code session holding a
Monitor whose command is ``tools/effort_event_watch.sh``; each wake arrives as
a task-notification and the reply is the session's next prose. The only
record is the raw transcript under ``~/.claude/projects/<project>/<session>.jsonl``
— the session database (claude-monitor) stores user and assistant rows only
and misses a wake absorbed mid-turn (finding archive-1), so this reads the
transcript itself.

WHAT IT FINDS, in order:
  1. the arm: an assistant ``tool_use`` named Monitor whose command contains
     the watch script, dated ``<day>`` in Central time; its ``tool_result``
     row carries the task id the wakes are keyed on
  2. the stop: a TaskStop on that task id, else the last row of the transcript
  3. the wakes: ``queue-operation`` enqueue rows carrying that task id and a
     ``[TAPE]`` event — one per delivery, whether or not a user row followed
  4. each reply: the assistant text after the wake row up to the next prompt
     or the next wake; pushes (PushNotification calls) and token usage in
     that span
  5. whether the runbook (emitter-two-tier.md) was read before the first wake

THE ASSERTION. The wake set the transcript shows must equal the wake set
``derive_wakes`` computes from the log by rule (scorer start, arm, stop,
same-minute batching). A mismatch is a refusal: scoring the analyst for
silence on alerts it never saw would be a false alarm, and a rule that does
not reproduce the transcript is a rule the lane cannot use on a day with no
transcript.

Writes ``live-lane/session.json``, ``live-lane/wakes.jsonl`` and the
``live_lane`` section of ``run.json``. A day with no arm is recorded as
"no live session" and exits 0 — that day gets labels, not a comparison.

Usage: live_lane.py <YYYY-MM-DD> [--transcript PATH ...]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import (  # noqa: E402
    BATCH_GAP_S, CT, LaneError, WATCH_SCRIPT, derive_wakes, log, read_json, run_dir,
    update_run_json, utc_iso_to_ct, wake_records, write_json,
)

TRANSCRIPT_ROOT = Path(os.environ.get("CLAUDE_PROJECTS_DIR", Path.home() / ".claude/projects"))
RUNBOOK = "emitter-two-tier.md"
TAPE_LINE_RE = re.compile(r"^(?:\[TAPE\] (?:\d+ events: )?|\s+\+ )(.+)$")
EVENT_TAG_RE = re.compile(r"<event>(.*?)</event>", re.S)
TASK_ID_RE = re.compile(r"<task-id>(\S+)</task-id>")


# ── transcript reading ─────────────────────────────────────────────────────

def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for i, ln in enumerate(fh, 1):
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                log.warning("%s:%d unreadable row skipped", path.name, i)
                continue
            r["_row"] = i
            rows.append(r)
    return rows


def _content(r: dict):
    return (r.get("message") or {}).get("content")


def _blocks(r: dict, kind: str) -> list[dict]:
    c = _content(r)
    return [b for b in c if isinstance(b, dict) and b.get("type") == kind] if isinstance(c, list) else []


def _ts(r: dict) -> datetime | None:
    t = r.get("timestamp")
    return utc_iso_to_ct(t) if t else None


def discover_transcripts(day: _date) -> list[Path]:
    """Transcripts that mention the watch script and were written on or after
    ``day``. Scans ``~/.claude/projects/*/*.jsonl`` by mtime first so the
    substring test touches only recent files."""
    lo = datetime.combine(day, datetime.min.time(), CT).timestamp()
    hi = lo + 4 * 86400
    found: list[Path] = []
    for p in sorted(TRANSCRIPT_ROOT.glob("*/*.jsonl")):
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if mt < lo or mt > hi:
            continue
        with p.open("rb") as fh:
            if WATCH_SCRIPT.encode() in fh.read():
                found.append(p)
    return found


def find_arms(rows: list[dict], day: _date) -> list[dict]:
    """Every Monitor arm of the watch script dated ``day`` (CT), with the task
    id from its result row and the stop time from a later TaskStop."""
    arms = []
    for i, r in enumerate(rows):
        if r.get("type") != "assistant":
            continue
        for b in _blocks(r, "tool_use"):
            if b.get("name") != "Monitor":
                continue
            cmd = str((b.get("input") or {}).get("command", ""))
            if WATCH_SCRIPT not in cmd:
                continue
            ts = _ts(r)
            if ts is None or ts.date() != day:
                continue
            task_id = None
            for r2 in rows[i + 1:i + 6]:
                for tr in _blocks(r2, "tool_result"):
                    if tr.get("tool_use_id") == b.get("id"):
                        task_id = (r2.get("toolUseResult") or {}).get("taskId")
                        if not task_id:
                            m = re.search(r"task (\S+?)[,)]", str(tr.get("content")))
                            task_id = m.group(1) if m else None
            arms.append({"row": r["_row"], "index": i, "armed_ct": ts, "task_id": task_id,
                         "command": cmd,
                         "description": (b.get("input") or {}).get("description"),
                         "cwd": r.get("cwd"), "session_id": r.get("sessionId") or r.get("session_id"),
                         "model": (r.get("message") or {}).get("model"),
                         "version": r.get("version")})
    return arms


def find_stop(rows: list[dict], task_id: str | None, after: int) -> tuple[datetime | None, str, int]:
    """When the watch stopped: a TaskStop naming the task, else the last row.
    Returns (time, how, row index) — the index bounds the last wake's reply
    span and the arm-to-stop usage."""
    if task_id:
        for i in range(after, len(rows)):
            r = rows[i]
            for b in _blocks(r, "tool_use"):
                if b.get("name") == "TaskStop" and task_id in json.dumps(b.get("input") or {}):
                    return _ts(r), f"TaskStop row {r['_row']}", i
    last_i = next((i for i in range(len(rows) - 1, -1, -1) if rows[i].get("timestamp")), None)
    if last_i is None:
        return None, "unknown", len(rows)
    return _ts(rows[last_i]), f"session end row {rows[last_i]['_row']}", last_i


def _tape_lines(notification: str) -> tuple[list[str], str | None]:
    """The EVENT lines inside a wake's ``<event>…</event>`` block, without
    the ``[TAPE]``, ``N events:``, ``+`` and ``bar:`` dressing."""
    m = EVENT_TAG_RE.search(notification)
    body = m.group(1) if m else notification
    out, bar = [], None
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("bar:"):
            bar = s[4:].strip()
            continue
        mm = TAPE_LINE_RE.match(ln)
        if mm and " EVENT " in mm.group(1):
            out.append(mm.group(1).rstrip())
    return out, bar


def find_wakes(rows: list[dict], task_id: str, start: int, end_ts: datetime | None) -> list[dict]:
    wakes = []
    for i, r in enumerate(rows):
        if i <= start or r.get("type") != "queue-operation" or r.get("operation") != "enqueue":
            continue
        content = str(r.get("content") or "")
        if f"<task-id>{task_id}</task-id>" not in content or "[TAPE]" not in content:
            continue
        ts = _ts(r)
        if end_ts is not None and ts is not None and ts > end_ts + timedelta(seconds=1):
            continue
        lines, bar = _tape_lines(content)
        wakes.append({"row": r["_row"], "index": i, "delivered_ct": ts, "lines": lines,
                      "bar": bar, "notification": content})
    return wakes


def _is_prompt_row(r: dict, task_id: str) -> bool:
    """A user row that starts a new turn (a human prompt or a different
    notification) — the reply span ends here. Tool results do not count."""
    if r.get("type") != "user":
        return False
    c = _content(r)
    if isinstance(c, str):
        return not (f"<task-id>{task_id}</task-id>" in c and "[TAPE]" in c)
    if isinstance(c, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in c)
    return False


def collect_reply(rows: list[dict], start: int, stop: int, task_id: str) -> dict:
    """Assistant text, pushes and usage from the wake row to the next prompt
    or the next wake (``stop``)."""
    texts, pushes, tool_uses = [], [], []
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0, "assistant_rows": 0}
    first_ts = last_ts = None
    end_row = None
    for i in range(start + 1, stop):
        r = rows[i]
        if _is_prompt_row(r, task_id):
            end_row = r["_row"]
            break
        if r.get("type") != "assistant":
            continue
        ts = _ts(r)
        first_ts = first_ts or ts
        last_ts = ts or last_ts
        for b in _blocks(r, "text"):
            if b.get("text", "").strip():
                texts.append(b["text"].rstrip())
        for b in _blocks(r, "tool_use"):
            tool_uses.append(b.get("name"))
            if b.get("name") == "PushNotification":
                pushes.append((b.get("input") or {}).get("message"))
        u = (r.get("message") or {}).get("usage") or {}
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                  "cache_creation_input_tokens"):
            usage[k] += int(u.get(k) or 0)
        usage["assistant_rows"] += 1
    return {"text": "\n\n".join(texts), "pushes": pushes, "tool_uses": tool_uses,
            "usage": usage, "first_reply_ct": first_ts, "last_reply_ct": last_ts,
            "ended_at_row": end_row}


def runbook_read_before(rows: list[dict], upto: int) -> bool:
    for r in rows[:upto]:
        for b in _blocks(r, "tool_use"):
            if RUNBOOK in json.dumps(b.get("input") or {}):
                return True
    return False


def usage_from(rows: list[dict], start: int, stop: int | None = None) -> dict:
    tot = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
           "cache_creation_input_tokens": 0, "assistant_rows": 0, "models": {}}
    for r in rows[start:stop]:
        if r.get("type") != "assistant":
            continue
        m = r.get("message") or {}
        u = m.get("usage") or {}
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                  "cache_creation_input_tokens"):
            tot[k] += int(u.get(k) or 0)
        tot["assistant_rows"] += 1
        tot["models"][m.get("model") or "?"] = tot["models"].get(m.get("model") or "?", 0) + 1
    return tot


# ── main ───────────────────────────────────────────────────────────────────

def extract(day: _date, transcripts: list[Path]) -> dict:
    sessions = []
    for path in transcripts:
        rows = load_rows(path)
        for arm in find_arms(rows, day):
            tid = arm["task_id"]
            if not tid:
                log.warning("%s row %d: arm with no task id — skipped", path.name, arm["row"])
                continue
            stop_ts, stop_how, stop_idx = find_stop(rows, tid, arm["index"])
            wakes = find_wakes(rows, tid, arm["index"], stop_ts)
            for n, w in enumerate(wakes):
                nxt = wakes[n + 1]["index"] if n + 1 < len(wakes) else stop_idx + 1
                w["reply"] = collect_reply(rows, w["index"], nxt, tid)
            sessions.append({
                "transcript": str(path), "project": path.parent.name, "cwd": arm["cwd"],
                "session_id": arm["session_id"], "model": arm["model"],
                "claude_code_version": arm["version"], "task_id": tid,
                "description": arm["description"], "command": arm["command"],
                "armed_ct": arm["armed_ct"], "armed_row": arm["row"],
                "stopped_ct": stop_ts, "stopped_how": stop_how,
                "runbook_read_before_first_wake": runbook_read_before(
                    rows, wakes[0]["index"] if wakes else len(rows)),
                "usage_from_arm": usage_from(rows, arm["index"], stop_idx + 1),
                "wakes": wakes,
            })
    return {"day": day.isoformat(), "sessions": sessions}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("day", type=_date.fromisoformat)
    ap.add_argument("--transcript", type=Path, action="append", default=[],
                    help="transcript JSONL to read (default: discover under ~/.claude/projects)")
    ap.add_argument("--no-assert", action="store_true",
                    help="record a wake-set mismatch instead of refusing (diagnosis only)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    day: _date = args.day
    rd = run_dir(day)
    out = rd / "live-lane"
    out.mkdir(exist_ok=True)

    paths = args.transcript or discover_transcripts(day)
    result = extract(day, paths)
    sessions = result["sessions"]
    rec: dict = {"produced_at": datetime.now(CT).isoformat(timespec="seconds"),
                 "transcripts_scanned": [str(p) for p in paths],
                 "sessions": len(sessions)}

    if not sessions:
        rec["status"] = "no live session"
        write_json(out / "session.json", {**result, **rec})
        (out / "wakes.jsonl").write_text("", encoding="utf-8")
        update_run_json(day, "live_lane", rec)
        print(f"live-lane {day}: no live session found in {len(paths)} transcript(s) — "
              f"labelling-only day")
        return 0

    # The rule-derived wake set, from the day's inputs.
    inputs = read_json(rd / "run.json").get("inputs") or {}
    live_log = inputs.get("live_log") or {}
    start_ct = utc_iso_to_ct(live_log["start_ct"]) if live_log.get("start_ct") else None
    log_lines = (rd / "00-inputs/log.txt").read_text(encoding="utf-8").splitlines() \
        if (rd / "00-inputs/log.txt").exists() else \
        [json.loads(l)["line"] for l in (rd / "00-inputs/events.jsonl").read_text().splitlines() if l]

    all_wakes = []
    for s in sessions:
        derived = derive_wakes(log_lines, start_ct=start_ct, arm_ct=s["armed_ct"],
                               stop_ct=s["stopped_ct"])
        s["derived"] = {"wakes": wake_records(derived["wakes"]),
                        "ambiguous": derived["ambiguous"],
                        "undelivered": derived["undelivered"]}
        got = [w["lines"][0][:5] if w["lines"] else "?" for w in s["wakes"]]
        exp = [w.minute for w in derived["wakes"]]
        s["wake_sets_match"] = got == exp
        s["wake_set_transcript"] = got
        s["wake_set_derived"] = exp
        log.info("session %s (%s): armed %s, stopped %s (%s); transcript wakes %s; derived %s",
                 s["task_id"], s["project"], s["armed_ct"].strftime("%H:%M:%S"),
                 s["stopped_ct"].strftime("%H:%M:%S") if s["stopped_ct"] else "?",
                 s["stopped_how"], got, exp)
        if got != exp and not args.no_assert:
            update_run_json(day, "live_lane", {**rec, "refused": "wake sets differ",
                                               "transcript": got, "derived": exp})
            raise LaneError(
                f"wake set in the transcript {got} != wake set derived from the log {exp} "
                f"(task {s['task_id']}, armed {s['armed_ct']:%H:%M:%S}, stopped "
                f"{s['stopped_ct']:%H:%M:%S} by {s['stopped_how']}). Ambiguous minutes: "
                f"{[l[:5] for l in derived['ambiguous']]}")
        for w in s["wakes"]:
            all_wakes.append({"task_id": s["task_id"], "session_id": s["session_id"],
                              "project": s["project"], **w})

    # session.json without the full wake bodies; wakes.jsonl carries them.
    slim = []
    for s in sessions:
        d = {k: v for k, v in s.items() if k != "wakes"}
        d["wake_count"] = len(s["wakes"])
        d["push_count"] = sum(len(w["reply"]["pushes"]) for w in s["wakes"])
        slim.append(d)
    write_json(out / "session.json", {"day": day.isoformat(), **rec, "sessions": slim})
    with (out / "wakes.jsonl").open("w", encoding="utf-8") as fh:
        for w in all_wakes:
            fh.write(json.dumps(w, sort_keys=True, default=str) + "\n")
    rec.update({"status": "ok", "wakes": len(all_wakes),
                "pushes": sum(len(w["reply"]["pushes"]) for w in all_wakes),
                "sessions_detail": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                                     for k, v in s.items()
                                     if k in ("task_id", "project", "cwd", "model", "armed_ct",
                                              "stopped_ct", "stopped_how", "wake_count",
                                              "push_count", "wake_sets_match",
                                              "runbook_read_before_first_wake",
                                              "usage_from_arm", "transcript")}
                                    for s in slim]})
    update_run_json(day, "live_lane", rec)
    print(f"live-lane {day}: {len(sessions)} session(s), {len(all_wakes)} wake(s), "
          f"{rec['pushes']} push(es); wake sets "
          f"{'match' if all(s['wake_sets_match'] for s in sessions) else 'DIFFER'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LaneError as e:
        print(f"[REFUSED] live-lane: {e}", file=sys.stderr)
        raise SystemExit(2)
