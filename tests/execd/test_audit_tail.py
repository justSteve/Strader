"""Three smaller findings from the 2026-08-30 audit, fixed together. [st-kh0l]

**Finding 16** — unlocking after 15:00 CT armed the service until 15:00 the
*next* day, because ``session_close`` rolls forward when the close has passed.
An arming expiry must never outlive the session it was granted for.

**Finding 15** — four POST routes acted on a body-less request. A cross-origin
HTML form post needs no CORS preflight, so any page rendered by a browser on
this box could fire ``/flatten``, ``/stand-down`` or ``/poll-fills``. A form
cannot send ``application/json`` without triggering a preflight the loopback
server never answers, so those routes now require the JSON content type.
``/stop`` stays reachable by anything on purpose: a hostile page firing it can
only stop new risk, and Steve's phone must not need a header to reach it.

**Finding 5 (the rest)** — ``/cancel`` would cancel the resting stop under a
live position on an exit-class permission. The silent half was fixed with
st-v7oa (it journaled); this is the other half: it is now refused outright,
because stripping a live position's only protection opens risk, and the real
ways out — an exit, flatten — take the stop off in the same motion they close
the position it protects.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from execd.api import create_app
from execd.broker import MockBroker
from execd.service import Refused

from .conftest import CALL, SPX_NOW, entry, exit_intent

TRIGGER = SPX_NOW - 12.5


class TestUnlockCannotOutliveTheSession:
    def test_an_unlock_after_the_close_is_refused(self, service, clock):
        clock.set_ct(15, 30)
        with pytest.raises(Refused) as exc:
            service.unlock({"token": "x"})
        assert exc.value.refusal.bound == "window"
        assert "tomorrow" in exc.value.refusal.reason
        refused = service.journal.events("refused")[-1]
        assert refused["kind"] == "unlock"

    def test_an_unlock_before_the_open_arms_until_todays_close(self, service, clock):
        clock.set_ct(7, 0)
        service.unlock({"token": "x"})
        assert service.arming.expires_at.astimezone(
            service.journal.clock().astimezone().tzinfo) is not None
        expires = service.arming.status()["expires_at_ct"]
        assert expires == "15:00 CT"

    def test_an_explicit_until_is_capped_at_todays_close(self, service, clock):
        service.unlock({"token": "x"}, until=clock() + timedelta(days=2))
        assert service.arming.status()["expires_at_ct"] == "15:00 CT"
        assert service.journal.events("unlock")[-1]["capped"] is True

    def test_exits_still_need_no_window(self, armed, clock, broker):
        """The finding is about arming for entries; getting out after the bell
        was legal before and stays legal."""
        armed.place(entry(intent_id="late-1"))
        clock.set_ct(15, 30)
        out = armed.flatten(reason="after-bell")
        assert out["errors"] == []
        assert armed.status()["positions"] == []


class TestFormPostsCannotChangeState:
    @pytest.fixture
    def client(self, armed):
        app = create_app(armed)
        app.config["TESTING"] = True
        return app.test_client()

    @pytest.mark.parametrize("route", ["/flatten", "/stand-down", "/poll-fills"])
    def test_a_form_post_is_refused(self, client, route):
        r = client.post(route, data={"reason": "hostile"},
                        content_type="application/x-www-form-urlencoded")
        assert r.status_code == 400
        assert "JSON" in r.json["detail"]

    @pytest.mark.parametrize("route", ["/flatten", "/stand-down", "/poll-fills"])
    def test_the_same_route_works_as_json(self, client, route):
        r = client.post(route, json={})
        assert r.status_code == 200

    def test_a_body_less_post_is_refused_too(self, client):
        assert client.post("/flatten").status_code == 400

    def test_stop_stays_reachable_with_no_body_at_all(self, client, armed):
        """The deliberate exemption: the kill switch answers anything."""
        r = client.post("/stop")
        assert r.status_code == 200
        assert armed.arming.killed


class TestCancelGuardsTheStop:
    def test_cancelling_a_live_positions_stop_is_refused(self, armed, broker):
        armed.place(entry(intent_id="guard-1"))
        stop_id = armed.status()["positions"][0]["stop_order_id"]
        with pytest.raises(Refused) as exc:
            armed.cancel(stop_id)
        assert exc.value.refusal.bound == "protective_stop"
        assert broker._orders[stop_id].is_working    # still standing

    def test_the_refusal_is_journaled_with_the_order_named(self, armed):
        armed.place(entry(intent_id="guard-2"))
        stop_id = armed.status()["positions"][0]["stop_order_id"]
        with pytest.raises(Refused):
            armed.cancel(stop_id)
        refused = armed.journal.events("refused")[-1]
        assert refused["order_id"] == stop_id

    def test_cancelling_an_in_flight_close_restores_the_protection(
            self, armed, broker):
        """Pulling a close by hand is legal — the position is live again, so
        the stop goes straight back on and the loop may fire anew."""
        armed.place(entry(intent_id="guard-3"))
        broker.rest_market = True
        out = armed.observe(TRIGGER)
        exit_id = out["fired"][0]["order_id"]
        armed.cancel(exit_id)
        pos = armed.status()["positions"][0]
        assert pos["exit_order_id"] is None
        assert pos["stop_order_id"] is not None
        assert broker._orders[pos["stop_order_id"]].is_working

    def test_a_working_entry_can_still_be_cancelled(self, armed, broker):
        """The refusal is scoped to the protective stop, nothing wider."""
        broker.rest_limits = True
        out = armed.place(entry(intent_id="guard-4"))
        result = armed.cancel(out["order"]["order_id"])
        assert result["order"]["status"] == "CANCELED"
        assert armed.status()["day"]["attempts_used"] == 0


class TestStopHasTheLastLook:
    """Finding 10: the STOP file was checked when the bounds ran, then the
    entry spent three broker round-trips being priced. A touch that lands
    during the pricing must win — it is re-checked immediately before the
    send, and nothing is transmitted."""

    def test_a_stop_touched_during_pricing_blocks_the_send(self, armed, broker):
        real_preview = broker.preview

        def touch_and_preview(intent):
            armed.arming.stop()          # the phone touch, mid-pricing
            return real_preview(intent)

        broker.preview = touch_and_preview
        out = armed.place(entry(intent_id="lastlook-1"))
        assert out["refused"]["bound"] == "stop"
        assert "while this entry was being priced" in out["refused"]["reason"]
        assert [kw for kw in broker.calls_to("place")] == []


class TestMidnightDoesNotFreeASlot:
    """Finding 9, the rollover half: the day's count is rebuilt from today's
    journal file, so a position carried past midnight fell out of it and its
    slot came free while it was still open. The service now takes the larger
    of the journal's count and what it is actually holding."""

    def test_yesterdays_open_position_still_holds_its_slot(self, armed, clock):
        armed.place(entry(intent_id="wed-1"))
        clock.set_ct(10, 0, day=27)                  # Thursday, new journal file
        assert armed.day_state().open_positions == 0  # the journal's honest count
        armed.unlock({"token": "x"})                  # re-arm for the new session
        out = armed.place(entry(intent_id="thu-1", symbol=CALL))
        assert out["refused"]["bound"] == "positions"

    def test_a_fresh_day_with_nothing_held_is_unaffected(self, armed, clock, broker):
        armed.place(entry(intent_id="wed-2"))
        armed.flatten(reason="eod")
        clock.set_ct(10, 0, day=27)
        broker.set_quote(CALL, bid=2.00, ask=2.10)   # yesterday's quote is stale
        broker.set_quote("$SPX", bid=SPX_NOW - 0.25, ask=SPX_NOW + 0.25, last=SPX_NOW)
        armed.unlock({"token": "x"})
        assert armed.place(entry(intent_id="thu-2"))["refused"] is None


class TestMockUnlockIsStructural:
    """Finding 17: --mock-unlock was safe only because --mock was required,
    and stage 2 removes that requirement. The guard is now on the broker
    object itself, so reordering main() cannot quietly widen it."""

    def test_only_the_mock_broker_may_be_flag_armed(self):
        from execd.__main__ import may_mock_unlock

        assert may_mock_unlock(MockBroker()) is True
        assert may_mock_unlock(object()) is False


class TestTheShaTellsTheTruth:
    """Finding 22: a dirty working tree was stamped with a clean sha, so a
    journal line could attribute an order to code that was never committed."""

    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        import subprocess

        def git(*args):
            subprocess.run(["git", "-C", str(tmp_path), *args],
                           check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
        (tmp_path / "f.txt").write_text("clean\n")
        git("add", "f.txt")
        git("commit", "-qm", "init")
        import execd.__main__ as main_mod
        monkeypatch.setattr(main_mod, "REPO", tmp_path)
        return tmp_path

    def test_a_clean_tree_stamps_a_bare_sha(self, repo):
        from execd.__main__ import installed_sha

        sha = installed_sha()
        assert sha != "unknown" and "-" not in sha

    def test_a_dirty_tree_says_so(self, repo):
        from execd.__main__ import installed_sha

        (repo / "f.txt").write_text("edited, never committed\n")
        assert installed_sha().endswith("-dirty")
