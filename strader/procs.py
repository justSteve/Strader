"""Bounded subprocesses that cannot leave a grandchild behind. [co-8b60y]

WHY. ``subprocess.run(cmd, timeout=N)`` kills only the direct child when the
deadline passes. When that child is a shell whose real work is a grandchild
— the ICM stages run ``bash run_stage.sh`` around ``claude -p``; the
post-mortem and Mancini runners run ``desk-html.sh`` around node and a model
call — the grandchild survives, keeps the pipe open, and finishes on its own
long after the caller reported a failure. Measured on 2026-09-02 and 09-03:
the classify stage's ``claude -p`` ran 12-13 minutes past the 900 s cap on
both days (usage.json written 16:08:01 and 16:07:45 against a wrapper end of
15:55:02), and the run was reported as "unexpected failure".

HOW. The child starts as the leader of its own session, so of its own
process group; on timeout the whole group gets SIGTERM, a short grace, then
SIGKILL, and the pipes are drained before ``subprocess.TimeoutExpired`` is
re-raised — the standard exception, so callers that already catch it keep
working. A signal to this process (SIGTERM from an outer ``timeout``, SIGINT,
SIGHUP) is forwarded to every live group first, because a group of its own
is also outside the outer ``timeout``'s reach: without the forwarding the
fix would move the orphan one level up.

Use ``run_bounded`` exactly like ``subprocess.run`` for the keywords the
callers use (``capture_output``, ``text``, ``env``, ``cwd``, ``timeout``);
``input`` and ``check`` are not supported.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from typing import Sequence

DEFAULT_GRACE_S = 10.0

_LIVE: dict[int, subprocess.Popen] = {}          # pgid (== child pid) -> the child
_LIVE_LOCK = threading.Lock()
_PREVIOUS: dict[int, object] = {}               # signum -> handler before ours


def _kill_group(pgid: int, sig: int) -> bool:
    """Signal a process group; False when no member exists any more."""
    try:
        os.killpg(pgid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:      # a member changed uid — nothing we can do
        return False


def _group_alive(pgid: int, proc: subprocess.Popen) -> bool:
    proc.poll()                  # reap the leader if it is a zombie
    return _kill_group(pgid, 0)


def terminate_group(proc: subprocess.Popen, *, grace: float = DEFAULT_GRACE_S):
    """SIGTERM the child's group, wait up to ``grace`` for the child, then
    SIGKILL whatever is left in the group and drain the pipes. Returns
    ``(stdout, stderr)`` as ``communicate`` would."""
    pgid = proc.pid
    _kill_group(pgid, signal.SIGTERM)
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    _kill_group(pgid, signal.SIGKILL)
    try:
        return proc.communicate(timeout=grace)
    except subprocess.TimeoutExpired:
        # Something outside the group still holds a pipe (a double-forked
        # daemon). Let go of the pipes; the child itself is dead.
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        proc.wait()
        return None, None


def _forward(signum, frame):
    """Kill every live group, then let the signal take its previous course."""
    with _LIVE_LOCK:
        live = dict(_LIVE)
    for pgid in live:
        _kill_group(pgid, signal.SIGTERM)
    deadline = time.monotonic() + min(DEFAULT_GRACE_S, 5.0)
    while live and time.monotonic() < deadline:
        live = {g: p for g, p in live.items() if _group_alive(g, p)}
        if live:
            time.sleep(0.1)
    for pgid in live:
        _kill_group(pgid, signal.SIGKILL)
    prev = _PREVIOUS.get(signum)
    if callable(prev):
        prev(signum, frame)
        return
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _install_forwarding() -> None:
    """Once per process, main thread only. A handler the program already
    installed is chained, not replaced; SIG_IGN is left alone."""
    if _PREVIOUS or threading.current_thread() is not threading.main_thread():
        return
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        prev = signal.getsignal(sig)
        if prev is signal.SIG_IGN:
            continue
        _PREVIOUS[sig] = prev
        signal.signal(sig, _forward)


def run_bounded(cmd: Sequence[str], *, timeout: float, grace: float = DEFAULT_GRACE_S,
                capture_output: bool = False, **popen_kw) -> subprocess.CompletedProcess:
    """``subprocess.run(cmd, timeout=timeout, ...)`` whose timeout kills the
    child's whole process group. Raises ``subprocess.TimeoutExpired`` after
    the group is dead, with whatever output was captured."""
    if capture_output:
        popen_kw["stdout"] = subprocess.PIPE
        popen_kw["stderr"] = subprocess.PIPE
    popen_kw.pop("start_new_session", None)
    _install_forwarding()
    proc = subprocess.Popen(cmd, start_new_session=True, **popen_kw)
    with _LIVE_LOCK:
        _LIVE[proc.pid] = proc
    try:
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            out, err = terminate_group(proc, grace=grace)
            raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err) from None
    finally:
        with _LIVE_LOCK:
            _LIVE.pop(proc.pid, None)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
