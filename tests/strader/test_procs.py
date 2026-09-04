"""strader.procs — a deadline kills the whole process group, never just the
shell. [co-8b60y]

The shape under test is the one measured on 2026-09-02/03: a bash child whose
real work is a grandchild. ``subprocess.run(timeout=)`` killed bash and left
the grandchild running to completion; ``run_bounded`` must leave nothing.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from strader import procs

ROOT = Path(__file__).resolve().parents[2]


def _grandchild_script(pidfile: Path, marker: Path, work_s: float = 3.0) -> str:
    """bash -c body: a background subshell records its pid, works for
    ``work_s`` and then writes the marker; the foreground sleeps far past any
    deadline the test sets."""
    return (f'( echo $BASHPID > "{pidfile}"; sleep {work_s}; touch "{marker}" ) & '
            f'sleep 60')


def _wait_for(path: Path, secs: float = 5.0) -> None:
    deadline = time.monotonic() + secs
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert path.exists(), f"{path} never appeared"


def _gone(pid: int, secs: float = 5.0) -> bool:
    deadline = time.monotonic() + secs
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_a_finished_child_comes_back_like_subprocess_run():
    r = procs.run_bounded(["bash", "-c", "echo hi; echo err >&2; exit 4"],
                          timeout=10, capture_output=True, text=True)
    assert r.returncode == 4 and r.stdout == "hi\n" and r.stderr == "err\n"


def test_the_deadline_kills_the_grandchild_and_raises_the_standard_exception(tmp_path):
    marker, pidfile = tmp_path / "marker", tmp_path / "gc.pid"
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as ei:
        procs.run_bounded(["bash", "-c", _grandchild_script(pidfile, marker)],
                          timeout=1, grace=2, capture_output=True, text=True)
    assert time.monotonic() - t0 < 10          # not the 60 s the foreground sleep asked for
    assert ei.value.timeout == 1
    _wait_for(pidfile)
    assert _gone(int(pidfile.read_text()))     # the grandchild died with the group
    time.sleep(3.5)                            # past the grandchild's own finish line
    assert not marker.exists()                 # it never got to write


def test_a_signal_to_the_parent_is_forwarded_to_the_group(tmp_path):
    """The outer `timeout` in the ICM wrapper sends SIGTERM to the python
    stage; the stage must take its child's group down with it, or the fix
    would only move the orphan one level up."""
    marker, pidfile = tmp_path / "marker", tmp_path / "gc.pid"
    body = _grandchild_script(pidfile, marker)
    child_code = (
        f"import sys; sys.path.insert(0, {str(ROOT)!r})\n"
        "from strader import procs\n"
        f"procs.run_bounded(['bash', '-c', {body!r}], timeout=60, capture_output=True)\n")
    parent = subprocess.Popen([sys.executable, "-c", child_code])
    try:
        _wait_for(pidfile)
        os.kill(parent.pid, signal.SIGTERM)
        rc = parent.wait(timeout=15)
    finally:
        if parent.poll() is None:
            parent.kill()
    assert rc == -signal.SIGTERM               # the signal took its normal course afterwards
    assert _gone(int(pidfile.read_text()))
    time.sleep(3.5)
    assert not marker.exists()


def test_forwarding_chains_a_handler_the_program_already_had(tmp_path):
    """A caller's own SIGTERM handler still runs after the groups are killed."""
    marker, pidfile = tmp_path / "marker", tmp_path / "gc.pid"
    seen = tmp_path / "handler-ran"
    body = _grandchild_script(pidfile, marker)
    child_code = (
        f"import sys, signal, pathlib; sys.path.insert(0, {str(ROOT)!r})\n"
        "from strader import procs\n"
        f"def h(s, f): pathlib.Path({str(seen)!r}).write_text('yes'); raise SystemExit(7)\n"
        "signal.signal(signal.SIGTERM, h)\n"
        f"procs.run_bounded(['bash', '-c', {body!r}], timeout=60, capture_output=True)\n")
    parent = subprocess.Popen([sys.executable, "-c", child_code])
    try:
        _wait_for(pidfile)
        os.kill(parent.pid, signal.SIGTERM)
        rc = parent.wait(timeout=15)
    finally:
        if parent.poll() is None:
            parent.kill()
    assert rc == 7 and seen.read_text() == "yes"
    assert _gone(int(pidfile.read_text()))
