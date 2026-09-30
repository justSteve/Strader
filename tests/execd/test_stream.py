"""The ACCT_ACTIVITY doorbell: the stream rings the watcher, never books. [st-8bls]

Frames are the shapes Steve's 2026-09-30 probe captured against the live
streamer (a TOS order placed and cancelled with the stream held open).
"""
from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from execd.broker import BrokerError
from execd.schwab import AccountStream, StreamError, activity_types
from execd.watch import RECONCILE_MIN_GAP_S, RING_RECONCILE_GAP_S, Watcher

INFO = {"streamerSocketUrl": "wss://streamer-api.schwab.com/ws",
        "schwabClientCustomerId": "cust", "schwabClientCorrelId": "corr",
        "schwabClientChannel": "N9", "schwabClientFunctionId": "APIAPP"}


def ok(command: str) -> str:
    return json.dumps({"response": [{"service": "ADMIN" if command in ("LOGIN", "LOGOUT")
                                     else "ACCT_ACTIVITY", "command": command,
                                     "content": {"code": 0, "msg": ""}}]})


def activity(*types: str) -> str:
    return json.dumps({"data": [{"service": "ACCT_ACTIVITY", "command": "SUBS", "content": [
        {"seq": i, "key": "k", "1": "<acct>", "2": t, "3": "{}"} for i, t in enumerate(types)]}]})


HEARTBEAT = json.dumps({"notify": [{"heartbeat": "1790790771689"}]})


class FakeWS:
    """Plays a script of frames; a TimeoutError once the script runs out,
    which the stream reads as a silent socket and ends the session on."""

    def __init__(self, frames: list[str], stop: threading.Event | None = None):
        self.frames = list(frames)
        self.sent: list[dict[str, Any]] = []
        self.stop = stop

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    def recv(self, timeout: float | None = None) -> str:
        if not self.frames:
            if self.stop is not None:
                self.stop.set()
            raise TimeoutError
        return self.frames.pop(0)


class FakeBroker:
    def __init__(self, locked: bool = False):
        self.locked = locked

    def _credential(self, app):
        if self.locked:
            raise BrokerError("the service is locked — no trading credential in memory")
        return object()

    def _bearer(self, app, cred, force=False):
        return "ACCESS"

    def _request(self, method, path, **kw):
        assert (method, path) == ("GET", "/trader/v1/userPreference")
        return SimpleNamespace(json=lambda: {"streamerInfo": [INFO]})


def make(frames, *, broker=None, record=None):
    rung: list[list[str]] = []
    ws = FakeWS(frames)
    stream = AccountStream(broker or FakeBroker(), rung.append, record=record,
                           connect=lambda url, **kw: ws, sleep=lambda s: None)
    ws.stop = stream._stop
    return stream, ws, rung


# ── frames ───────────────────────────────────────────────────────────────

def test_activity_types_skip_subscribed_and_heartbeats():
    assert activity_types(json.loads(activity("SUBSCRIBED"))) == []
    assert activity_types(json.loads(HEARTBEAT)) == []
    assert activity_types(json.loads(activity("OrderCreated", "OrderAccepted"))) == \
        ["OrderCreated", "OrderAccepted"]


def test_a_closing_notice_raises_so_the_loop_reconnects():
    with pytest.raises(StreamError, match="code 12"):
        activity_types({"notify": [{"service": "ADMIN", "content": {"code": 12, "msg": "x"}}]})


# ── a session ────────────────────────────────────────────────────────────

def test_session_logs_in_subscribes_and_rings_on_account_events():
    stream, ws, rung = make([ok("LOGIN"), ok("SUBS"), activity("SUBSCRIBED"), HEARTBEAT,
                             activity("OrderCreated"), activity("ExecutionCreated")])
    with pytest.raises(StreamError, match="not even a heartbeat"):
        stream.session()
    assert rung == [["OrderCreated"], ["ExecutionCreated"]]
    assert stream.events == 2
    commands = [f["requests"][0]["command"] for f in ws.sent]
    assert commands == ["LOGIN", "SUBS", "LOGOUT"]


def test_the_only_frames_sent_are_login_subs_and_logout():
    """Receive-only is the whole of the permission (Steve, 2026-09-30)."""
    stream, ws, _ = make([ok("LOGIN"), ok("SUBS"), activity("OrderCreated")])
    with pytest.raises(StreamError):
        stream.session()
    sent = {(f["requests"][0]["service"], f["requests"][0]["command"]) for f in ws.sent}
    assert sent <= {("ADMIN", "LOGIN"), ("ACCT_ACTIVITY", "SUBS"), ("ADMIN", "LOGOUT")}
    login = ws.sent[0]["requests"][0]
    assert login["parameters"]["Authorization"] == "ACCESS"
    assert login["SchwabClientCorrelId"] == "corr"


def test_a_refused_login_is_an_outage_journaled_once():
    records: list[tuple] = []
    stream, ws, rung = make([json.dumps({"response": [{"command": "LOGIN",
                                                       "content": {"code": 3, "msg": "no"}}]})],
                            record=lambda *a, **k: records.append((a, k)))
    stream._down_journaled = False
    attempts = {"n": 0}

    def once_then_stop(s):
        attempts["n"] += 1
        if attempts["n"] >= 3:
            stream._stop.set()
    stream._sleep = once_then_stop
    ws_frames = ws.frames[:]
    stream._connect = lambda url, **kw: FakeWS(list(ws_frames))
    stream.run()
    downs = [r for r in records if r[1].get("kind") == "stream"]
    assert len(downs) == 1, "an outage is journaled once, not once per retry"
    assert "fall back to the poll" in downs[0][1]["detail"]
    assert stream.state == "down" and "code 3" in stream.last_error
    assert rung == []


def test_locked_is_not_an_outage_and_opens_no_socket():
    records: list[tuple] = []
    opened: list[str] = []
    stream = AccountStream(FakeBroker(locked=True), lambda t: None,
                           record=lambda *a, **k: records.append((a, k)),
                           connect=lambda url, **kw: opened.append(url))
    stream._sleep = lambda s: stream._stop.set()
    stream.run()
    assert stream.state == "locked"
    assert opened == [] and records == []


def test_up_after_down_is_journaled():
    records: list[tuple] = []
    stream, ws, _ = make([ok("LOGIN"), ok("SUBS")],
                         record=lambda *a, **k: records.append((a, k)))
    stream._down("earlier drop")
    with pytest.raises(StreamError):
        stream.session()
    assert any(r[0] == ("stream",) for r in records)
    assert stream._down_journaled is False


# ── the watcher's doorbell ───────────────────────────────────────────────

class FakeService:
    def __init__(self):
        self.arming = SimpleNamespace(state="ARMED")
        self.gaps: list[float] = []
        self.journal = SimpleNamespace(record=lambda *a, **k: None)

    def has_exposure(self):
        return True

    def reconcile_if_stale(self, gap):
        self.gaps.append(gap)
        return {}

    def spx_mark(self):
        return 7600.0

    def observe(self, spx):
        return {}


def test_a_ring_reconciles_on_the_short_gap_and_a_beat_on_the_long():
    svc = FakeService()
    w = Watcher(svc, sleep=lambda s: None)
    w.once()
    w.ring(["OrderCreated"])
    out = w.once()
    w.once()
    assert svc.gaps == [RECONCILE_MIN_GAP_S, RING_RECONCILE_GAP_S, RECONCILE_MIN_GAP_S]
    assert out.get("rung") is True


def test_a_ring_ends_the_wait_early():
    w = Watcher(FakeService())
    t = threading.Timer(0.05, w.ring)
    t.start()
    import time
    start = time.monotonic()
    w._wait(5.0)
    assert time.monotonic() - start < 1.0
