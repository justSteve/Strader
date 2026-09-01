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
