"""Arming — three states, one kill file, and the asymmetry. [st-eznu]

The class under test exists to hold one invariant: *nothing may refuse an exit
for a risk reason.* ``TestExitsAreNeverRefusedForRisk`` is that invariant
written down. If a future bound needs to gate exits, it needs Steve's ruling
first, not a green suite.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from execd.arming import ArmState, Arming, Locked

from .conftest import Clock

CRED = {"token": "not-a-real-credential"}


@pytest.fixture
def arming(tmp_path, clock: Clock) -> Arming:
    return Arming(kill_file=tmp_path / "STOP", clock=clock)


def until(clock: Clock, minutes: int = 300) -> datetime:
    return clock() + timedelta(minutes=minutes)


class TestTheThreeStates:
    def test_a_fresh_service_is_locked(self, arming):
        assert arming.state is ArmState.LOCKED
        assert arming.permits_entry().bound == "armed"
        assert arming.permits_exit().bound == "armed"

    def test_unlock_arms_it(self, arming, clock):
        assert arming.unlock(CRED, until(clock)) is ArmState.ARMED
        assert arming.permits_entry() is None and arming.permits_exit() is None

    def test_stand_down_stops_entries_and_leaves_exits_alone(self, arming, clock):
        arming.unlock(CRED, until(clock))
        assert arming.stand_down() is ArmState.STOOD_DOWN
        assert arming.permits_entry().bound == "armed"
        assert "stood down" in arming.permits_entry().reason
        assert arming.permits_exit() is None

    def test_lock_forgets_the_credential(self, arming, clock):
        arming.unlock(CRED, until(clock))
        assert arming.lock() is ArmState.LOCKED
        with pytest.raises(Locked):
            arming.credential()

    def test_unlock_after_stand_down_arms_it_again(self, arming, clock):
        arming.unlock(CRED, until(clock))
        arming.stand_down()
        assert arming.unlock(CRED, until(clock)) is ArmState.ARMED


class TestExpiry:
    def test_arming_expires_at_the_session_close(self, arming, clock):
        arming.unlock(CRED, until(clock, minutes=60))
        clock.advance(minutes=61)
        assert arming.state is ArmState.STOOD_DOWN
        assert "expired" in arming.permits_entry().reason

    def test_expiry_stands_down_rather_than_locking(self, arming, clock):
        """The credential stays available to close what is still open at the bell."""
        arming.unlock(CRED, until(clock, minutes=60))
        clock.advance(minutes=61)
        assert arming.permits_exit() is None
        assert arming.credential() == CRED

    def test_unlock_requires_an_aware_expiry(self, arming):
        with pytest.raises(ValueError, match="timezone-aware"):
            arming.unlock(CRED, datetime(2026, 8, 26, 15, 0))

    def test_unlock_requires_a_credential(self, arming, clock):
        with pytest.raises(ValueError, match="credential"):
            arming.unlock(None, until(clock))


class TestTheKillFile:
    def test_stop_blocks_entries_while_armed(self, arming, clock):
        arming.unlock(CRED, until(clock))
        arming.stop()
        assert arming.killed
        assert arming.permits_entry().bound == "stop"

    def test_stop_is_idempotent(self, arming, clock):
        arming.unlock(CRED, until(clock))
        arming.stop()
        arming.stop()
        assert arming.killed

    def test_resume_clears_it_and_tolerates_an_absent_file(self, arming, clock):
        arming.unlock(CRED, until(clock))
        arming.resume()          # nothing to clear yet
        arming.stop()
        arming.resume()
        assert not arming.killed
        assert arming.permits_entry() is None

    def test_stop_creates_the_directory_it_needs(self, tmp_path, clock):
        deep = Arming(kill_file=tmp_path / "not" / "yet" / "STOP", clock=clock)
        deep.stop()
        assert deep.killed

    def test_a_kill_file_left_by_a_previous_process_is_still_in_force(self, tmp_path, clock):
        (tmp_path / "STOP").touch()
        fresh = Arming(kill_file=tmp_path / "STOP", clock=clock)
        fresh.unlock(CRED, until(clock))
        assert fresh.permits_entry().bound == "stop"


class TestExitsAreNeverRefusedForRisk:
    """The invariant. See the module docstring."""

    @pytest.mark.parametrize("arrange", [
        pytest.param(lambda a: a.stop(), id="STOP is on"),
        pytest.param(lambda a: a.stand_down(), id="stood down"),
        pytest.param(lambda a: (a.stop(), a.stand_down()), id="both"),
    ])
    def test_exits_pass(self, arming, clock, arrange):
        arming.unlock(CRED, until(clock))
        arrange(arming)
        assert arming.permits_exit() is None

    def test_exits_pass_after_the_session_expired(self, arming, clock):
        arming.unlock(CRED, until(clock, minutes=1))
        clock.advance(minutes=120)
        arming.stop()
        assert arming.permits_exit() is None

    def test_the_one_thing_that_refuses_an_exit_is_having_no_credential(self, arming):
        r = arming.permits_exit()
        assert r.bound == "armed" and "nothing to transmit with" in r.reason


class TestStatus:
    def test_status_reports_what_the_page_needs(self, arming, clock):
        arming.unlock(CRED, until(clock, minutes=300))
        s = arming.status()
        assert s["state"] == "ARMED"
        assert s["killed"] is False
        assert s["permits_entry"] is True and s["permits_exit"] is True
        assert s["expires_at_ct"].endswith("CT")

    def test_status_never_carries_the_credential(self, arming, clock):
        arming.unlock({"token": "sekrit-refresh-token"}, until(clock))
        assert "sekrit" not in repr(arming.status())
