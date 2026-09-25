"""The narrow door — what it answers, and what it does not have. [st-eznu]

``TestTheRoutesThatDoNotExist`` is the load-bearing class in this file. The
design's claim to Steve is that an agent which can reach this API can ask the
service to trade inside his bounds and cannot arm it, cannot clear his STOP,
and never sees the credential. A docstring saying so is worth nothing; the
absence of the routes is asserted against the app's own URL map, so adding one
back breaks the suite.
"""

from __future__ import annotations

import json

import pytest

from execd.api import BIND_HOST, create_app
from execd.service import ExecService

from .conftest import CALL, SPX_NOW, entry


@pytest.fixture
def client(armed: ExecService):
    app = create_app(armed)
    return app.test_client()


@pytest.fixture
def locked_client(service: ExecService):
    return create_app(service).test_client()


def post(client, path, payload=None):
    return client.post(path, data=json.dumps(payload or {}),
                       content_type="application/json")


class TestReads:
    def test_status(self, client):
        r = client.get("/status")
        assert r.status_code == 200
        assert r.json["arming"]["state"] == "ARMED"
        assert r.json["bounds"]["qty_cap"] == 1

    def test_quote(self, client):
        r = client.get(f"/quote?symbol={CALL}")
        assert r.status_code == 200 and r.json["bid"] == 2.00

    def test_quote_without_a_symbol_is_a_bad_request_not_a_refusal(self, client):
        r = client.get("/quote")
        assert r.status_code == 400 and r.json["error"] == "bad_request"

    def test_an_unknown_symbol_is_a_broker_error(self, client):
        r = client.get("/quote?symbol=SPXW  260826C09999000")
        assert r.status_code == 502 and r.json["error"] == "broker"

    def test_chain(self, client):
        r = client.get("/chain?root=SPXW")
        assert r.status_code == 200 and r.json["root"] == "SPXW"


class TestMarketDataPassThrough:
    """Stage 3 (st-p8k8): the repo's readers ask the service for the raw
    market-data bodies they used to fetch with their own copy of the token.
    Answers while LOCKED, because the market credential is outside the lock."""

    def test_quotes_answer_while_locked_in_schwabs_shape(self, locked_client):
        r = locked_client.get("/marketdata/quotes?symbols=$SPX,SPXW  260826C06400000")
        assert r.status_code == 200
        assert r.json["$SPX"]["quote"]["lastPrice"] == SPX_NOW
        assert r.json[CALL]["quote"]["askPrice"] == 2.10

    def test_pricehistory_reports_empty_when_there_is_nothing(self, locked_client):
        r = locked_client.get("/marketdata/pricehistory?symbol=/ES&periodType=day"
                              "&frequencyType=minute&frequency=1")
        assert r.status_code == 200 and r.json == {"symbol": "/ES", "candles": [],
                                                   "empty": True}

    def test_chains_answer_the_two_expiry_maps(self, locked_client):
        r = locked_client.get("/marketdata/chains?symbol=$SPX&strikeCount=20")
        assert r.status_code == 200
        assert set(r.json) >= {"callExpDateMap", "putExpDateMap", "status"}

    def test_an_unknown_resource_is_a_400_not_a_forward(self, locked_client):
        r = locked_client.get("/marketdata/accounts")
        assert r.status_code == 400 and "no such market read" in r.json["detail"]

    def test_a_parameter_schwab_does_not_take_is_refused(self, locked_client):
        r = locked_client.get("/marketdata/quotes?symbols=$SPX&accountNumber=1")
        assert r.status_code == 400 and "accountNumber" in r.json["detail"]

    def test_only_get(self, locked_client):
        assert locked_client.post("/marketdata/quotes").status_code == 405

    def test_a_broker_failure_is_a_502(self, locked_client, broker):
        broker.fail_next = "down"
        r = locked_client.get("/marketdata/quotes?symbols=$SPX")
        assert r.status_code == 502

    def test_orders_and_positions(self, client):
        post(client, "/place", entry().to_dict())
        # entry + the bracket: the resting stop and the resting take-profit (st-fn5y)
        assert len(client.get("/orders").json["orders"]) == 3
        assert client.get("/positions").json["tracked"][0]["symbol"] == CALL

    def test_journal_tail(self, client):
        post(client, "/place", entry().to_dict())
        events = [e["event"] for e in client.get("/journal?n=6").json["entries"]
                  if e["event"] != "order_raw"]      # the broker's own body, beside each leg
        assert events[-4:] == ["placed", "filled", "stop_placed", "target_placed"]


class TestPlacing:
    def test_a_good_intent_is_a_200(self, client):
        r = post(client, "/place", entry().to_dict())
        assert r.status_code == 200
        assert r.json["order"]["status"] == "FILLED"
        assert r.json["stop_order"]["order_type"] == "STOP"

    def test_a_refusal_is_a_409_naming_the_bound(self, client):
        r = post(client, "/place", entry(qty=99).to_dict())
        assert r.status_code == 409
        assert r.json["refused"] == {"bound": "qty",
                                     "reason": "99 contracts is over the 1-contract cap"}

    def test_a_locked_service_refuses_with_409(self, locked_client):
        r = post(locked_client, "/place", entry().to_dict())
        assert r.status_code == 409 and r.json["refused"]["bound"] == "armed"

    def test_a_malformed_intent_is_a_400(self, client):
        r = post(client, "/place", {"intent_id": "x", "symbol": "nope",
                                    "side": "BUY_TO_OPEN", "qty": 1})
        assert r.status_code == 400 and "OCC" in r.json["detail"]

    def test_an_unknown_side_is_a_400(self, client):
        r = post(client, "/place", {"intent_id": "abc", "symbol": CALL,
                                    "side": "SELL_SHORT", "qty": 1})
        assert r.status_code == 400

    def test_an_empty_body_is_a_400(self, client):
        assert post(client, "/place").status_code == 400

    def test_a_json_array_is_a_400(self, client):
        r = client.post("/place", data="[1,2,3]", content_type="application/json")
        assert r.status_code == 400

    def test_preview_does_not_transmit(self, client, broker):
        r = post(client, "/preview", entry().to_dict())
        assert r.status_code == 200 and r.json["preview"]["cost_usd"] == 210.0
        assert broker.calls_to("place") == []

    def test_a_previewed_refusal_is_also_a_409(self, client):
        r = post(client, "/preview", entry(qty=99).to_dict())
        assert r.status_code == 409 and r.json["refused"]["bound"] == "qty"


class TestGettingOut:
    def test_flatten(self, client):
        post(client, "/place", entry().to_dict())
        r = post(client, "/flatten")
        assert r.status_code == 200 and r.json["closed"][0]["closed"] is True

    def test_flatten_works_after_stop(self, client):
        post(client, "/place", entry().to_dict())
        assert post(client, "/stop").status_code == 200
        assert post(client, "/flatten").json["closed"][0]["closed"] is True

    def test_flatten_on_a_locked_service_is_a_409(self, locked_client):
        r = post(locked_client, "/flatten")
        assert r.status_code == 409 and r.json["refused"]["bound"] == "armed"

    def test_cancel_needs_an_order_id(self, client):
        assert post(client, "/cancel").status_code == 400

    def test_cancel(self, client, broker):
        broker.rest_limits = True
        placed = post(client, "/place", entry().to_dict())
        r = post(client, "/cancel", {"order_id": placed.json["order"]["order_id"]})
        assert r.status_code == 200 and r.json["order"]["status"] == "CANCELED"

    def test_stand_down_blocks_entries_and_leaves_exits(self, client):
        assert post(client, "/stand-down").json["arming"]["state"] == "STOOD_DOWN"
        assert post(client, "/place", entry().to_dict()).status_code == 409

    def test_stop_is_reachable_and_ungated(self, client):
        r = post(client, "/stop")
        assert r.status_code == 200 and r.json["arming"]["killed"] is True

    def test_observe_fires_the_exit(self, client):
        post(client, "/place", entry(stop_spx=SPX_NOW - 12).to_dict())
        r = post(client, "/observe", {"spx": SPX_NOW - 12.5})
        assert r.status_code == 200 and r.json["fired"][0]["closed"] is True

    def test_observe_without_a_mark_is_a_400(self, client):
        assert post(client, "/observe").status_code == 400

    def test_poll_fills(self, client):
        assert post(client, "/poll-fills").json == {"picked_up": []}


class TestTheRoutesThatDoNotExist:
    """The design's promise to Steve, asserted against the URL map."""

    @pytest.mark.parametrize("path", [
        "/unlock", "/arm", "/resume", "/reauth", "/re-auth", "/oauth",
        "/token", "/credential", "/passphrase", "/lock", "/bounds",
    ])
    def test_no_route_arms_the_service_or_shows_the_credential(self, client, path):
        assert client.post(path).status_code == 404
        assert client.get(path).status_code == 404

    def test_the_url_map_holds_exactly_the_narrow_door(self, armed):
        app = create_app(armed)
        rules = {r.rule for r in app.url_map.iter_rules() if r.endpoint != "static"}
        assert rules == {
            "/status", "/quote", "/chain", "/orders", "/positions", "/journal",
            # co-8mb1z: the broker's own body for one order, read-only
            "/orders/<order_id>/raw",
            "/preview", "/place", "/cancel", "/flatten", "/stand-down", "/stop",
            "/observe", "/poll-fills",
            # stage 3 (st-p8k8): the raw market-data pass-through for the
            # repo's readers. One rule, three resource names, GET only.
            "/marketdata/<kind>",
            # st-fn5y: the bracket's live editor — move the stop, the target,
            # or both under a live position. Exit-class; arms nothing.
            "/adjust",
        }

    def test_arming_is_reachable_on_the_service_but_not_over_http(self, armed, client):
        """The methods exist — Steve's page will call them in stage 3 — and no
        HTTP route reaches them."""
        assert callable(armed.unlock) and callable(armed.resume)
        app = create_app(armed)
        endpoints = {r.endpoint for r in app.url_map.iter_rules()}
        assert "unlock" not in endpoints and "resume" not in endpoints

    def test_status_does_not_leak_the_credential(self, client, armed):
        armed.unlock({"refresh_token": "sekrit-value"})
        assert "sekrit" not in client.get("/status").get_data(as_text=True)

    def test_the_api_binds_the_loopback(self):
        assert BIND_HOST == "127.0.0.1"


class TestMethodDiscipline:
    @pytest.mark.parametrize("path", ["/status", "/quote", "/orders", "/positions"])
    def test_reads_refuse_a_post(self, client, path):
        assert client.post(path).status_code == 405

    @pytest.mark.parametrize("path", ["/place", "/flatten", "/stop", "/observe"])
    def test_writes_refuse_a_get(self, client, path):
        assert client.get(path).status_code == 405
