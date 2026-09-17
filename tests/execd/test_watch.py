"""The watcher — the loop nothing ran before stage 4. [st-k6gl]

Locked: nothing. Flat: nothing. Exposed: reconcile, read the mark, observe —
and the SPX-level exit fires when the mark crosses. A broker outage is one
journal line, not one per pass, and the loop outlives any single failure.
"""

from __future__ import annotations

from execd.broker import BrokerError
from execd.service import ExecService
from execd.watch import Watcher

from .conftest import CALL, SPX_NOW, entry


def test_locked_does_nothing(service: ExecService, broker):
    w = Watcher(service)
    before = len(broker.calls)                                      # construction reconciles
    assert w.once() == {"skipped": "locked"}
    assert len(broker.calls) == before


def test_flat_does_nothing(armed: ExecService, broker):
    w = Watcher(armed)
    before = len(broker.calls)
    assert w.once() == {"skipped": "flat"}
    assert len(broker.calls) == before


def test_exposed_reconciles_and_observes_and_fires_the_exit(armed: ExecService, broker):
    out = armed.place(entry("w-1"))
    assert out["order"]["status"] == "FILLED" and out["stop_order"]
    stop_spx = armed.status()["positions"][0]["stop_spx"]

    w = Watcher(armed)
    r = w.once()
    assert r["spx"] == SPX_NOW and r["observe"]["fired"] == [] and "reconcile" in r

    broker.set_quote("$SPX", bid=stop_spx - 1.0, ask=stop_spx - 0.5, last=stop_spx - 0.75)
    r = w.once()
    assert r["observe"]["fired"][0]["symbol"] == CALL
    events = [e["event"] for e in armed.journal.find("w-1")]
    assert "exit_triggered" in events


def test_a_broker_outage_is_journaled_once_and_retried(armed: ExecService, broker):
    armed.place(entry("w-2"))
    w = Watcher(armed)
    broker.fail_next = "down"
    r1 = w.once()
    assert "error" in r1
    broker.fail_next = "still down"
    r2 = w.once()
    assert "error" in r2
    lines = [e for e in armed.journal.read() if e.get("event") == "error" and e.get("kind") == "watch"]
    assert len(lines) == 1                                          # one line per outage
    r3 = w.once()
    assert "error" not in r3
    assert [e for e in armed.journal.read() if e.get("event") == "watch"][-1]["detail"] == "broker back"


def test_a_dead_mark_is_a_broker_outage_not_an_exit(armed: ExecService, broker):
    """An index quote with no price in it used to reach observe() as 0.0 and
    fire every long call's stop (finding 32, st-xv5e). Now it is no mark:
    one watch error line, the position untouched, the resting stop the exit."""
    armed.place(entry("w-3", stop_spx=SPX_NOW - 12))
    sent = len(broker.calls_to("place"))
    w = Watcher(armed)
    broker.set_quote("$SPX", bid=0.0, ask=0.0, last=0.0)
    r = w.once()
    assert "error" in r and "no usable" in r["error"]
    assert len(broker.calls_to("place")) == sent
    assert len(armed.status()["positions"]) == 1
    assert not [e for e in armed.journal.read() if e.get("event") == "exit_triggered"]


def test_the_loop_survives_a_pass_that_raises(armed: ExecService, monkeypatch):
    calls = []

    def boom():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("unexpected")
        return {"skipped": "flat"}

    naps = []

    def sleep(s):
        naps.append(s)
        if len(naps) >= 3:
            w.stop()

    w = Watcher(armed, interval_s=5, idle_interval_s=30, sleep=sleep)
    monkeypatch.setattr(w, "once", boom)
    w.run()
    assert len(calls) == 3 and naps == [5, 30, 30]                 # an error pass is not "idle"


def test_start_returns_a_daemon_thread(armed: ExecService):
    naps = []

    def sleep(s):
        naps.append(s)
        w.stop()

    w = Watcher(armed, sleep=sleep)
    t = w.start()
    t.join(timeout=5)
    assert not t.is_alive() and t.daemon and naps == [30.0]
