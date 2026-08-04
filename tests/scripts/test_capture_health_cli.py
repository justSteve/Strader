"""capture_health CLI — process discovery, day resolution, state and alerts. [st-6qx4]

The assessor's logic is covered in strader/tests/test_capture_health.py. What is
tested here is everything the pure function cannot see: that liveness comes from
a real /proc scan filtered on `comm`, that a capture writing into yesterday's
day-dir is still watched correctly after midnight, and that a bad verdict lands
on the shared corpus health log with the same record shape corpus_daily.py uses.

Every case runs against a FAKE /proc tree and a tmp corpus root — no streamer, no
Databento connection, nothing that could touch a live capture.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import scripts.capture_health as ch

ES = "databento_glbx_es"
MBP1 = "databento_glbx_es_mbp1"
STREAMER = "/root/projects/Strader/scripts/corpus_stream_databento.py"

NIGHT = "2026-08-04T02:00"          # Tuesday overnight — GLBX open
SATURDAY = "2026-08-08T02:00"       # GLBX closed all day


def fake_proc(tmp_path: Path, procs: dict[int, tuple[str, str]],
              age_secs: float = 9999.0) -> Path:
    """procs: pid -> (comm, cmdline). Dir mtime backdated so age is controllable."""
    root = tmp_path / "proc"
    root.mkdir(exist_ok=True)
    for pid, (comm, cmdline) in procs.items():
        d = root / str(pid)
        d.mkdir(exist_ok=True)
        (d / "comm").write_text(comm + "\n")
        (d / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode() + b"\0")
        stamp = time.time() - age_secs
        os.utime(d, (stamp, stamp))
    (root / "self").mkdir(exist_ok=True)          # non-numeric entry, must be skipped
    return root


def write_manifest(corpus: Path, day: date, es=1000, mbp1=50000, pull="2026-08-04T07:00:00Z"):
    d = corpus / day.isoformat()
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"date": day.isoformat(), "streams": {
        ES: {"cycles": es, "errors": [], "last_pull_utc": pull},
        MBP1: {"cycles": mbp1, "errors": [], "last_pull_utc": pull},
    }}))


def run(tmp_path, proc_root, *, now=NIGHT, extra=()):
    argv = ["--corpus-root", str(tmp_path / "corpus"),
            "--proc-root", str(proc_root),
            "--now", now, *extra]
    return ch.main(argv)


def state_of(tmp_path) -> dict:
    return json.loads((tmp_path / "corpus" / ch.STATE_NAME).read_text())


def health_lines(tmp_path) -> list[dict]:
    p = tmp_path / "corpus" / ch.HEALTH_LOG_NAME
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


# --- process discovery: the st-cm5 lesson ----------------------------------

def test_finds_the_python_capture(tmp_path):
    root = fake_proc(tmp_path, {4242: ("python", f"/x/python {STREAMER} --streams es")})
    found = ch.find_capture_pids(proc_root=root)
    assert [p for p, _ in found] == [4242]


def test_ignores_non_python_processes_that_merely_mention_it(tmp_path):
    """A grep, an editor or the cron shell all carry the string on their command
    line. Counting one of those as a live capture is how the guard reports
    healthy while the tape goes missing."""
    root = fake_proc(tmp_path, {
        11: ("grep", f"grep -f {STREAMER}"),
        12: ("bash", f"bash -c 'tail {STREAMER}'"),
        13: ("nvim", f"nvim {STREAMER}"),
    })
    assert ch.find_capture_pids(proc_root=root) == []


def test_ignores_other_python_processes(tmp_path):
    root = fake_proc(tmp_path, {
        21: ("python", "/x/python /root/projects/Strader/scripts/live_footprint_feed.py"),
        22: ("python", "/x/python /root/projects/Strader/scripts/drill_bridge.py"),
    })
    assert ch.find_capture_pids(proc_root=root) == []


def test_never_counts_itself(tmp_path):
    """The checker's own command line carries the match string whenever --match
    is passed. Counting it reports a live capture when none is running — the
    inverse of the failure this whole thing exists to catch."""
    root = fake_proc(tmp_path, {
        51: ("python", f"/x/python {ch.__file__} --match {STREAMER}"),
    })
    assert ch.find_capture_pids(proc_root=root) == []


def test_age_comes_from_the_proc_dir(tmp_path):
    root = fake_proc(tmp_path, {31: ("python", f"/x/python {STREAMER}")}, age_secs=42.0)
    (_pid, age), = ch.find_capture_pids(proc_root=root)
    assert 35 < age < 60


# --- verdicts end to end ---------------------------------------------------

def test_healthy_capture_exits_zero_and_writes_state(tmp_path, capsys):
    root = fake_proc(tmp_path, {4242: ("python", f"/x/python {STREAMER}")})
    write_manifest(tmp_path / "corpus", date(2026, 8, 4))
    assert run(tmp_path, root) == 0
    assert state_of(tmp_path)["status"] == "ok"
    assert health_lines(tmp_path) == []          # healthy runs never alert
    assert "OK" in capsys.readouterr().out


def test_dead_capture_exits_one_and_alerts(tmp_path, capsys):
    root = fake_proc(tmp_path, {})
    write_manifest(tmp_path / "corpus", date(2026, 8, 4))
    assert run(tmp_path, root) == 1
    rec, = health_lines(tmp_path)
    # Same record shape corpus_daily.emit_alert writes — one log, one reader.
    assert rec["level"] == "alert" and rec["kind"] == "capture_dead"
    assert rec["ts"].endswith("Z") and "not backfillable" in rec["message"]
    assert "CAPTURE ALERT" in capsys.readouterr().err


def test_dead_outside_the_configured_window_is_idle(tmp_path):
    root = fake_proc(tmp_path, {})
    assert run(tmp_path, root, extra=["--window-start", "08:30",
                                      "--window-end", "15:05"]) == 0
    assert state_of(tmp_path)["status"] == "idle"
    assert health_lines(tmp_path) == []


def test_dead_with_globex_closed_is_idle(tmp_path):
    root = fake_proc(tmp_path, {})
    assert run(tmp_path, root, now=SATURDAY) == 0
    assert state_of(tmp_path)["status"] == "idle"


def test_stale_needs_two_observations(tmp_path):
    """One manifest read cannot tell you a number has stopped moving."""
    root = fake_proc(tmp_path, {4242: ("python", f"/x/python {STREAMER}")})
    write_manifest(tmp_path / "corpus", date(2026, 8, 4))
    assert run(tmp_path, root) == 0                       # first look: no baseline
    later = (datetime.fromisoformat(NIGHT) + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M")
    assert run(tmp_path, root, now=later) == 1            # frozen for 20 min
    assert state_of(tmp_path)["status"] == "stale"
    assert health_lines(tmp_path)[-1]["kind"] == "capture_stale"


def test_duplicate_capture_is_flagged(tmp_path):
    root = fake_proc(tmp_path, {1: ("python", f"/x/python {STREAMER}"),
                                2: ("python", f"/x/python {STREAMER}")})
    write_manifest(tmp_path / "corpus", date(2026, 8, 4))
    assert run(tmp_path, root) == 1
    assert state_of(tmp_path)["status"] == "duplicate"


def test_no_alert_flag_records_without_shouting(tmp_path):
    root = fake_proc(tmp_path, {})
    assert run(tmp_path, root, extra=["--no-alert"]) == 1
    assert state_of(tmp_path)["status"] == "dead"
    assert health_lines(tmp_path) == []


# --- the midnight case -----------------------------------------------------

def test_watches_the_day_the_capture_actually_writes_to(tmp_path):
    """The streamer fixes its corpus day at startup. Just after midnight it is
    still appending to yesterday's dir; reading today's empty manifest would
    report a healthy capture as stale at every rollover."""
    corpus = tmp_path / "corpus"
    write_manifest(corpus, date(2026, 8, 3), es=99000, mbp1=880000,
                   pull="2026-08-04T05:03:00Z")
    (corpus / "2026-08-04").mkdir(parents=True, exist_ok=True)   # today, empty
    root = fake_proc(tmp_path, {4242: ("python", f"/x/python {STREAMER}")},
                     age_secs=3 * 3600)                          # started 21:05 CT
    assert run(tmp_path, root, now="2026-08-04T00:05") == 0
    st = state_of(tmp_path)
    assert st["day"] == "2026-08-03"
    assert st["streams"][ES]["cycles"] == 99000


# --- restart bookkeeping ---------------------------------------------------

def test_record_restart_counts_and_logs(tmp_path):
    root = fake_proc(tmp_path, {})
    run(tmp_path, root)                                   # seeds state with a day
    assert ch.main(["--corpus-root", str(tmp_path / "corpus"),
                    "--record-restart", "was dead; relaunched pid 77"]) == 0
    st = state_of(tmp_path)
    assert st["restarts"] == 1 and st["last_restart_detail"].startswith("was dead")
    rec = health_lines(tmp_path)[-1]
    assert rec["kind"] == "capture_restarted" and rec["restarts_today"] == 1


def test_restart_counter_survives_the_next_check(tmp_path):
    root = fake_proc(tmp_path, {4242: ("python", f"/x/python {STREAMER}")})
    write_manifest(tmp_path / "corpus", date(2026, 8, 4))
    run(tmp_path, root)
    ch.main(["--corpus-root", str(tmp_path / "corpus"), "--record-restart", "x"])
    run(tmp_path, root)
    assert state_of(tmp_path)["restarts"] == 1


# --- shell contract --------------------------------------------------------

def test_porcelain_is_parseable(tmp_path, capsys):
    root = fake_proc(tmp_path, {4242: ("python", f"/x/python {STREAMER}")})
    write_manifest(tmp_path / "corpus", date(2026, 8, 4))
    run(tmp_path, root, extra=["--porcelain"])
    kv = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    assert kv == {"status": "ok", "expected": "1", "pids": "4242",
                  "all_stale": "0", "actionable": "0", "day": "2026-08-04"}


def test_internal_error_exits_two(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ch, "find_capture_pids",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    assert run(tmp_path, tmp_path / "proc") == 2
    assert "INTERNAL ERROR" in capsys.readouterr().err
