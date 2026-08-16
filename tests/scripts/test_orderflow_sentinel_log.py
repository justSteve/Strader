"""Sentinel daily log rolling. [co-03ojd.7 — enterprise-audit sweep J, F11]

The defect this covers: the sentinel was hand-launched under a `tee` to a
filename fixed at launch, so four days of heartbeats accumulated in
`/var/moo/logs/orderflow-sentinel-2026-08-12.log`. Asking "what did the
sentinel do on 08-14?" by filename returned nothing, and the newest file read
as four days stale — absence-shaped evidence for a process that was running
fine. Every other per-job log under /var/moo/logs rolls daily; this makes the
sentinel do the same, on the CT boundary it already turns the feed path on.

No feed, no network, no sleeping loop: DailyLog is exercised directly.
"""
from __future__ import annotations

import datetime as dt

import scripts.orderflow_sentinel as ofs


def _pin(monkeypatch, iso: str) -> None:
    monkeypatch.setattr(ofs, "central_date", lambda: dt.date.fromisoformat(iso))


def test_writes_todays_file_and_mirrors_stdout(tmp_path, monkeypatch, capsys):
    _pin(monkeypatch, "2026-08-16")
    log = ofs.DailyLog(tmp_path)
    log.write("sentinel up")
    assert (tmp_path / "2026-08-16.log").read_text() == "sentinel up\n"
    assert capsys.readouterr().out == "sentinel up\n"


def test_rolls_on_the_ct_day_boundary(tmp_path, monkeypatch):
    """The whole finding: day two must not land in day one's file."""
    _pin(monkeypatch, "2026-08-16")
    log = ofs.DailyLog(tmp_path)
    log.write("heartbeat rows=1")
    _pin(monkeypatch, "2026-08-17")
    log.write("heartbeat rows=2")
    assert (tmp_path / "2026-08-16.log").read_text() == "heartbeat rows=1\n"
    assert (tmp_path / "2026-08-17.log").read_text() == "heartbeat rows=2\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == \
        ["2026-08-16.log", "2026-08-17.log"]


def test_appends_across_a_restart_rather_than_truncating(tmp_path, monkeypatch):
    """Restart=always means several processes share a day. The second must not
    erase the first — that would make a crash-loop look like a quiet day."""
    _pin(monkeypatch, "2026-08-16")
    ofs.DailyLog(tmp_path).write("first process")
    ofs.DailyLog(tmp_path).write("second process")
    assert (tmp_path / "2026-08-16.log").read_text() == \
        "first process\nsecond process\n"


def test_flushes_every_line(tmp_path, monkeypatch):
    """The log IS the liveness evidence (the sentinel writes no heartbeat file),
    so a buffered line is an invisible one."""
    _pin(monkeypatch, "2026-08-16")
    log = ofs.DailyLog(tmp_path)
    log.write("heartbeat rows=40828")
    assert (tmp_path / "2026-08-16.log").read_text().endswith("rows=40828\n")


def test_no_directory_means_stdout_only(tmp_path, capsys):
    ofs.DailyLog(None).write("stdout only")
    assert capsys.readouterr().out == "stdout only\n"
    assert list(tmp_path.iterdir()) == []


def test_unwritable_directory_degrades_to_stdout_instead_of_dying(tmp_path,
                                                                 monkeypatch,
                                                                 capsys):
    """A watcher that exits because it could not open a log file has removed
    the thing it was there to provide."""
    _pin(monkeypatch, "2026-08-16")
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("this is a file, so mkdir(parents) under it fails")
    log = ofs.DailyLog(blocked / "sub")
    log.write("first")
    log.write("second")          # must not raise on the second call either
    captured = capsys.readouterr()
    assert "first" in captured.out and "second" in captured.out
    assert "log file unavailable" in captured.err
    assert log.dir is None       # gave up on the file, kept running
