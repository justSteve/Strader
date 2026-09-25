"""The watcher — the loop nothing ran before stage 4. [st-k6gl]

Locked: nothing. Flat: nothing. Exposed: reconcile, read the mark, observe —
and the SPX-level exit fires when the mark crosses. A broker outage is one
journal line, not one per pass, and the loop outlives any single failure.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from execd.broker import BrokerError
from execd.intent import Side
from execd.service import ExecService
from execd.watch import Watcher

from .conftest import CALL, SPX_NOW, entry


def refresh_quotes(service, broker):
    """Re-stamp the mock's quotes at the clock's current reading. Moving the
    test clock forward hours makes every quote stale, and the price band
    refuses to price against a stale quote — which is correct, and not what
    an after-hours test is about."""
    broker.set_quote(CALL, bid=2.00, ask=2.10)
    broker.set_quote("$SPX", bid=SPX_NOW - 0.25, ask=SPX_NOW + 0.25, last=SPX_NOW)


@contextmanager
def no_exits(broker, monkeypatch):
    """A broker that takes everything except a close — the shape of an outage
    that leaves a position on the books. ``fail_next`` is one-shot and the
    reconcile inside ``flatten`` swallows the first failure, so a standing
    refusal of the sell is what a held-past-the-close test actually needs."""
    real = broker.place

    def refuse_exit(intent):
        if intent.side is Side.SELL_TO_CLOSE:
            raise BrokerError("down")
        return real(intent)

    monkeypatch.setattr(broker, "place", refuse_exit)
    try:
        yield
    finally:
        monkeypatch.setattr(broker, "place", real)


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


class TestNoClockAction:
    """Steve, 2026-09-24: "omg - never ever place that kind of restriction on
    me ... As 0DTE trades, if i don't close them, they expire. flat. But I
    will _never ask that you do it automatically." The 14:55 close-out is
    gone; nothing the watcher or the service does is driven by the hour or
    the day. [co-8mb1z]"""

    @pytest.mark.parametrize("hour,minute,day", [
        (14, 55, 26), (15, 0, 26), (15, 30, 26), (23, 0, 26), (10, 0, 29)])
    def test_a_held_position_is_untouched_at_any_hour(self, armed: ExecService, broker,
                                                      clock, hour, minute, day):
        armed.place(entry("n-1"))
        sent = len(broker.calls_to("place"))
        clock.set_ct(hour, minute, day=day)
        refresh_quotes(armed, broker)
        r = Watcher(armed).once()
        assert "flat_by_close" not in r
        assert len(armed.status()["positions"]) == 1
        # the bracket rested at the fill is all that was sent; nothing since
        assert len(broker.calls_to("place")) == sent
        assert not any(e.get("event") in ("flattened", "flat_by_close")
                       for e in armed.journal.read())

    def test_a_working_entry_is_not_cancelled_by_the_clock(self, armed: ExecService,
                                                          broker, clock):
        broker.rest_limits = True
        armed.place(entry("n-2"))
        clock.set_ct(14, 56)
        refresh_quotes(armed, broker)
        Watcher(armed).once()
        assert armed.status()["working"]
        assert broker.calls_to("cancel") == []

    def test_the_service_has_no_close_out_to_call(self, armed: ExecService):
        assert not hasattr(armed, "flat_by_close")
        assert not hasattr(armed, "flat_by_close_status")
        assert "flat_by_close" not in armed.status()

    @pytest.mark.parametrize("hour,day", [(16, 26), (10, 29)])   # after the bell; Saturday
    def test_an_entry_at_any_hour_is_not_refused_and_is_left_alone(
            self, service: ExecService, broker, clock, hour, day):
        clock.set_ct(hour, 0, day=day)
        refresh_quotes(service, broker)
        service.unlock({"token": "x"})
        out = service.place(entry("n-3"))
        assert out.get("refused") is None, out
        assert len(service.status()["positions"]) == 1
        clock.advance(minutes=60 * 5)
        refresh_quotes(service, broker)
        Watcher(service).once()
        assert len(service.status()["positions"]) == 1
        assert service.arming.state.value == "ARMED"


def test_start_returns_a_daemon_thread(armed: ExecService):
    naps = []

    def sleep(s):
        naps.append(s)
        w.stop()

    w = Watcher(armed, sleep=sleep)
    t = w.start()
    t.join(timeout=5)
    assert not t.is_alive() and t.daemon and naps == [30.0]
