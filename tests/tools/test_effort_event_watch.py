"""The wake tier of the two-tier emitter. [st-85dv]

EVERY STDOUT LINE THIS SCRIPT PRINTS IS A MODEL WAKE, so what is being protected
here is a budget. The watch it replaced woke on a 300-second clock — about 276
wakes a day, almost all of them reporting "nothing happened" — while the events
that mattered went unremarked because noticing depended on model attention.

The properties that make the replacement worth having, each pinned below:

  - a quiet tape wakes NOBODY. Graded bars and sig=note events must produce no
    output at all. If this regresses, the clock is back with extra steps.
  - alerts arriving together are ONE wake. A climax and the level rejection it
    caused are one situation; two wakes for it is the old waste in a new shape.
  - a wake carries the graded bar that caused it, so the analyst does not have
    to go read the log to know what the tape was doing.
  - a fault goes out immediately, alone, and is never batched behind tape
    events — a crashing scorer is not a market event.
  - SILENCE IS NOT SUCCESS: a dead scorer looks exactly like a quiet tape, so
    liveness is asserted on its own timer regardless of event flow.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "tools" / "effort_event_watch.sh"

BAR = ("08:43 CT  F1 (developing, n=524) conviction  ES o7695.75 h7696 l7692 "
       "c7693.75  vol 4004 d-676  net -2.00 rng 4.00   dev: effort_pct 99 "
       "effect_pct 95 grade 0.90   smax: vol 8752@08:30 d-676@08:43")
ALERT_SUP = ("08:43 CT  EVENT SUPERLATIVE MAX-SELL-DELTA  sig=alert  delta=-676 "
             " prev=-551@06:51  vol=4004  net=-2.00  close=7693.75")
ALERT_LVL = ("08:43 CT  EVENT PLAN-LEVEL REJECTION  sig=alert  level=7692  "
             "anchor=resistance  from=above  close=7693.75  back=1.75")
NOTE_LVL = ("09:51 CT  EVENT PLAN-LEVEL TOUCH  sig=note  level=7692  "
            "anchor=resistance  close=7691  high=7692  low=7689")


class Watch:
    """Runs the real script against a temp log and collects its stdout."""

    def __init__(self, tmp_path: Path, batch_gap: int = 3, liveness: int = 600):
        self.log = tmp_path / "tape.log"
        self.log.write_text("")
        self.out = tmp_path / "watch.out"
        self._fh = self.out.open("w")
        self.proc = subprocess.Popen(
            ["bash", str(SCRIPT), str(self.log), str(liveness), str(batch_gap)],
            stdout=self._fh, stderr=subprocess.STDOUT)
        self._await_arm()

    def _await_arm(self, timeout: float = 10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if "armed on" in self.read():
                return
            time.sleep(0.1)
        raise AssertionError(f"watch never armed: {self.read()!r}")

    def append(self, *lines: str):
        with self.log.open("a") as fh:
            for ln in lines:
                fh.write(ln + "\n")
            fh.flush()

    def read(self) -> str:
        self._fh.flush()
        return self.out.read_text()

    def wakes(self) -> list[str]:
        """Lines that would reach a model, minus the arming banner and the
        indented continuation lines that belong to a wake above them."""
        return [ln for ln in self.read().splitlines()
                if ln and not ln.startswith("event watch armed")
                and not ln.startswith(" ")]

    def settle(self, seconds: float = 8.0):
        time.sleep(seconds)

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._fh.close()


@pytest.fixture
def watch(tmp_path):
    w = Watch(tmp_path)
    yield w
    w.stop()


def test_a_quiet_tape_wakes_nobody(watch):
    """Graded bars and note-grade events are the overwhelming majority of a
    session. None of them may cost a wake."""
    watch.append(BAR, NOTE_LVL, BAR)
    watch.settle()
    assert watch.wakes() == [], watch.read()


def test_an_alert_wakes_once_and_carries_its_bar(watch):
    watch.append(BAR, ALERT_SUP)
    watch.settle()
    wakes = watch.wakes()
    assert len(wakes) == 1, watch.read()
    assert "MAX-SELL-DELTA" in wakes[0]
    assert "bar: 08:43 CT  F1" in watch.read(), (
        "a wake must carry the graded bar that caused it")


def test_alerts_arriving_together_are_one_wake(watch):
    """A climax and the level rejection it caused are one situation."""
    watch.append(BAR, ALERT_SUP, ALERT_LVL)
    watch.settle()
    wakes = watch.wakes()
    assert len(wakes) == 1, watch.read()
    assert wakes[0].startswith("[TAPE] 2 events:")
    assert "PLAN-LEVEL REJECTION" in watch.read()


def test_alerts_far_apart_are_separate_wakes(tmp_path):
    w = Watch(tmp_path, batch_gap=2)
    try:
        w.append(BAR, ALERT_SUP)
        w.settle(6)
        w.append(ALERT_LVL)
        w.settle(6)
        assert len(w.wakes()) == 2, w.read()
    finally:
        w.stop()


def test_a_fault_is_immediate_and_not_batched_behind_tape_events(watch):
    watch.append(BAR, ALERT_SUP,
                 "2026-08-25 09:55 ERROR effort_effect: Traceback (most recent call last):")
    watch.settle()
    wakes = watch.wakes()
    assert any(w.startswith("[ALERT] scorer:") for w in wakes), watch.read()
    # The fault must not be swallowed into the tape batch.
    assert any("Traceback" in w for w in wakes)


def test_a_stalled_tape_is_reported_even_though_no_event_fired(tmp_path):
    """The failure this exists for: a dead scorer and a quiet tape look
    identical from the log alone, so a watch that only reports market events
    would stay silent through a crash.

    Which liveness alarm fires depends on the box — "NOT RUNNING" when no
    scorer process exists, "log has not been written" when one is alive but
    stalled. A real scorer is usually running on this machine, so asserting the
    exact wording made this test pass or fail on the environment rather than on
    the behaviour. What must hold either way is that SOMETHING is said."""
    w = Watch(tmp_path, liveness=5)
    try:
        w.settle(14)
        alerts = [ln for ln in w.wakes() if ln.startswith("[ALERT]")]
        assert alerts, f"a stalled tape produced no liveness alarm:\n{w.read()}"
        assert any("NOT RUNNING" in ln or "not been written" in ln
                   for ln in alerts), w.read()
    finally:
        w.stop()


def test_note_grade_events_never_wake_even_beside_an_alert(watch):
    watch.append(BAR, NOTE_LVL, ALERT_SUP, NOTE_LVL)
    watch.settle()
    text = watch.read()
    assert "sig=note" not in text, "a note-grade event reached a wake"
    assert len(watch.wakes()) == 1
