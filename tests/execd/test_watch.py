"""The watcher — the loop nothing ran before stage 4. [st-k6gl]

Locked: nothing. Flat: nothing. Exposed: reconcile, read the mark, observe —
and the SPX-level exit fires when the mark crosses. A broker outage is one
journal line, not one per pass, and the loop outlives any single failure.
"""

from __future__ import annotations

from contextlib import contextmanager

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


class TestFlatByClose:
    """Steve's ruling, 2026-09-18, on st-9j8e: "9j8e is flat". The bracket's
    legs are DAY orders and a position is not, so at 14:55 CT the watcher
    cancels what is working and sells what is held. Nothing is carried past
    the bell; nothing is held overnight."""

    def test_mid_session_it_is_not_due_and_does_nothing(self, armed: ExecService, broker):
        armed.place(entry("f-1"))
        sent = len(broker.calls_to("place"))
        w = Watcher(armed)
        r = w.once()
        assert "flat_by_close" not in r
        assert armed.flat_by_close() == {"due": False, "why": "before 14:55 CT",
                                         "acted": False}
        assert len(broker.calls_to("place")) == sent
        assert len(armed.status()["positions"]) == 1

    def test_at_the_hour_the_position_is_sold(self, armed: ExecService, broker, clock):
        armed.place(entry("f-2"))
        assert len(armed.status()["positions"]) == 1
        clock.set_ct(14, 55)
        r = Watcher(armed).once()
        assert r["flat_by_close"]["acted"] and r["flat_by_close"]["flat"]
        assert armed.status()["positions"] == []
        events = [e["event"] for e in armed.journal.read()]
        assert "flat_by_close" in events and "flattened" in events
        assert any(e.get("reason") == "flat-by-close"
                   for e in armed.journal.read() if e.get("event") == "flattened")

    def test_a_working_entry_is_cancelled_so_it_cannot_fill_at_the_bell(
            self, armed: ExecService, broker, clock):
        """The entries go first. One still working at 14:55 could fill at
        14:59 and hand back the overnight position this exists to prevent."""
        broker.rest_limits = True
        armed.place(entry("f-3"))
        assert armed.status()["working"]
        clock.set_ct(14, 56)
        r = Watcher(armed).once()
        assert r["flat_by_close"]["cancelled"] and r["flat_by_close"]["flat"]
        assert armed.status()["working"] == []

    def test_it_runs_once_a_day_and_not_again(self, armed: ExecService, broker, clock):
        armed.place(entry("f-4"))
        clock.set_ct(14, 55)
        assert Watcher(armed).once()["flat_by_close"]["flat"]
        clock.set_ct(14, 56)
        assert armed.flat_by_close() == {"due": False, "why": "already flat for the day",
                                         "acted": False}

    def test_stop_and_stand_down_do_not_hold_it(self, armed: ExecService, broker, clock):
        """Nothing that exists to keep him out of risk may keep him in it —
        flatten is legal while STOPped and while stood down, and so is this."""
        armed.place(entry("f-5"))
        armed.stop()
        armed.stand_down()
        clock.set_ct(14, 55)
        assert Watcher(armed).once()["flat_by_close"]["flat"]
        assert armed.status()["positions"] == []

    def test_a_broker_that_cannot_be_reached_is_retried_not_abandoned(
            self, armed: ExecService, broker, clock, monkeypatch):
        armed.place(entry("f-6"))
        clock.set_ct(14, 55)
        with no_exits(broker, monkeypatch):
            r = armed.flat_by_close()
            assert r["acted"] and not r["flat"] and r["errors"]
            assert len(armed.status()["positions"]) == 1

            # inside the retry window it holds off rather than hammering
            clock.advance(seconds=5)
            assert armed.flat_by_close() == {"due": True, "why": "waiting to retry",
                                             "acted": False}
        # past it, with the broker back, it tries again and gets out
        clock.advance(seconds=40)
        assert armed.flat_by_close()["flat"]
        assert armed.status()["positions"] == []

    def test_a_weekend_pass_is_never_due(self, armed: ExecService, clock):
        armed.place(entry("f-7"))
        clock.set_ct(14, 55, day=29)                       # Saturday 2026-08-29
        r = armed.flat_by_close()
        assert r["due"] is False and "not a trading day" in r["why"]
        assert len(armed.status()["positions"]) == 1

    def test_still_held_past_the_hour_is_never_silent(
            self, armed: ExecService, broker, clock, monkeypatch):
        """The status body carries it and the card says it in red, because a
        position held past the close-out with nothing said is the failure
        this whole ruling exists to prevent."""
        from execd.panel import flat_by_close_alert

        armed.place(entry("f-8"))
        clock.set_ct(14, 55)
        with no_exits(broker, monkeypatch):
            armed.flat_by_close()
        st = armed.status()
        f = st["flat_by_close"]
        assert f["due"] and not f["done"] and f["still_held"] == [CALL]
        alert = flat_by_close_alert(st)
        assert "past 14:55 CT and still here" in alert and "C6400" in alert
        assert flat_by_close_alert({"flat_by_close": {"due": False}}) == ""

    def test_an_entry_sent_after_the_sweep_is_his_and_is_left_alone(
            self, armed: ExecService, broker, clock):
        """The other half of the same day's ruling: Steve also accepted
        after-hours sends (st-hlah), and in paper they fill. The sweep is ONE
        event — reaching 14:55 marks the day whether or not there was
        anything to close — so a position opened at 15:30 to exercise the
        pipe is not sold the moment it fills."""
        clock.set_ct(14, 55)
        assert Watcher(armed).once()["skipped"] == "flat"     # nothing held
        assert armed.flat_by_close_status()["done"] is True   # the day is marked

        clock.set_ct(15, 30)
        refresh_quotes(armed, broker)
        # the morning's arming ended at the close; he arms again to test
        armed.unlock({"token": "x"})
        armed.place(entry("f-10"))
        assert len(armed.status()["positions"]) == 1
        r = Watcher(armed).once()
        assert "flat_by_close" not in r
        assert len(armed.status()["positions"]) == 1, "his after-hours entry was swept"

    def test_an_unlock_after_the_hour_marks_the_day_and_closes_what_survived(
            self, service: ExecService, broker, clock):
        """Unlocking is the first moment a LOCKED service can close anything,
        so the close-out runs there too — and when there is nothing to close
        it marks the day, so the entry he unlocked in order to send is
        safe."""
        clock.set_ct(15, 30)
        refresh_quotes(service, broker)
        service.unlock({"token": "x"})
        assert service.flat_by_close_status()["done"] is True
        service.place(entry("f-11"))
        assert len(service.status()["positions"]) == 1
        assert service.flat_by_close()["acted"] is False
        assert len(service.status()["positions"]) == 1

    def test_locked_says_so_and_leaves_the_position_alone(
            self, armed: ExecService, clock):
        """With no credential in memory there is nothing to transmit with.
        The watcher skips the pass entirely; asked directly, the service says
        why and does not mark the day done."""
        armed.place(entry("f-9"))
        armed.arming.lock()
        clock.set_ct(14, 55)
        assert Watcher(armed).once() == {"skipped": "locked"}
        r = armed.flat_by_close()
        assert r["acted"] is False and "locked" in r["why"]
        assert armed.flat_by_close_status()["done"] is False


def test_start_returns_a_daemon_thread(armed: ExecService):
    naps = []

    def sleep(s):
        naps.append(s)
        w.stop()

    w = Watcher(armed, sleep=sleep)
    t = w.start()
    t.join(timeout=5)
    assert not t.is_alive() and t.daemon and naps == [30.0]
