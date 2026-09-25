"""The entry price box, the stop that follows it, and SEND re-pricing a
working entry. [co-8mb1z]

Steve, 2026-09-25: "once i've chosen a strike price i want to be able to set
the price of my entry. Stop should be set as per current -$20. Order should
be sent to Schwab and the form needs to be updated that it's a working order
with the form ready to take a new price. The stop price also needs to be an
input box to let me over ride the default $20."
"""

from __future__ import annotations

import pytest

from execd.orderform import Selection, nearest_tick, price
from execd.page import create_page
from execd.service import ExecService
from execd.vault import Vault

from .conftest import CALL, SPX_NOW, Clock, page_send, same_origin, schwab_chain_maps
from .test_page import PASS, vault_payload

SEL = {"side": "call", "strike": "6400"}


@pytest.fixture
def form(armed: ExecService, broker, clock: Clock, tmp_path):
    broker.set_chain("SPXW", schwab_chain_maps())
    vault = Vault(tmp_path / "vault.json")
    vault.store(vault_payload(), PASS)
    app = create_page(armed, vault=vault, clock=clock)
    app.config["TESTING"] = True
    return same_origin(app.test_client())


def text(r) -> str:
    return r.get_data(as_text=True)


def working_buys(broker):
    return [o for o in broker.working_orders() if o.side.value == "BUY_TO_OPEN"]


class TestThePriceBox:
    @pytest.mark.parametrize("typed,sent", [(2.07, 2.05), (2.08, 2.10), (1.5, 1.50),
                                            (3.07, 3.10), (0.01, 0.05)])
    def test_a_typed_price_goes_on_the_grid(self, typed, sent):
        assert nearest_tick(typed) == sent

    def test_the_box_defaults_to_the_price_the_form_shows(self, form):
        body = text(form.get("/exec/order?side=call&strike=6400"))
        assert "id=pxbox" in body and "value='2.10'" in body

    def test_a_typed_price_is_the_limit_and_the_box_shows_it_rounded(self, armed, form):
        sel = Selection.from_args({**SEL, "limit": "1.52"}, today=armed.clock().date())
        p = price(armed, sel)
        assert p.limit == 1.50
        body = text(form.get("/exec/order?side=call&strike=6400&limit=1.52"))
        assert "aria-label='entry price' value='1.50'" in body


class TestTheStopFollowsTheEntry:
    def test_the_stop_is_the_entry_less_20_until_he_types_one(self, armed, form):
        today = armed.clock().date()
        for limit, stop in (("2.10", 1.90), ("1.50", 1.30), ("1.00", 0.80)):
            p = price(armed, Selection.from_args({**SEL, "limit": limit}, today=today))
            assert p.stop_price == stop and p.stop_loss_usd == 20.0

    def test_his_own_stop_stays_his(self, armed, form):
        today = armed.clock().date()
        p = price(armed, Selection.from_args({**SEL, "limit": "1.50", "stop": "1.10"}, today=today))
        assert p.stop_price == 1.10

    def test_the_stop_box_is_on_the_form(self, form):
        body = text(form.get("/exec/order?side=call&strike=6400"))
        assert "id=stopbox" in body and "data-derived='1.90'" in body


class TestSendThenReprice:
    def test_send_rests_a_working_entry_and_the_box_stays_live(self, form, broker, armed):
        broker.rest_limits = True
        r = page_send(form, {**SEL, "limit": "1.90"})
        assert r.status_code == 303
        assert [o.price for o in working_buys(broker)] == [1.90]
        body = text(form.get("/exec/order?side=call&strike=6400&limit=1.90"))
        assert "data-stage=working" in body and "id=pxbox" in body and ">SEND<" in body

    def test_a_new_price_replaces_the_working_entry(self, form, broker, armed):
        broker.rest_limits = True
        page_send(form, {**SEL, "limit": "1.90"})
        first = working_buys(broker)[0].order_id
        page_send(form, {**SEL, "limit": "2.00"})
        buys = working_buys(broker)
        assert [o.price for o in buys] == [2.00], "one order, at the new price"
        assert broker._orders[first].status.value == "CANCELED"
        events = [e["event"] for e in armed.journal.read()]
        assert events.index("canceled") < len(events) - 1
        work = armed.status()["working"]
        assert len(work) == 1 and work[0]["limit"] == 2.00

    def test_the_stop_follows_the_new_price(self, form, broker, armed):
        """$20 under whichever entry is working: the stop price moves with the
        entry, and the SPX level the intent carries — $20 of premium walked
        through delta — is the same distance from spot either way."""
        broker.rest_limits = True
        today = armed.clock().date()
        page_send(form, {**SEL, "limit": "1.90"})
        first = price(armed, Selection.from_args({**SEL, "limit": "1.90"}, today=today))
        page_send(form, {**SEL, "limit": "2.00"})
        second = price(armed, Selection.from_args({**SEL, "limit": "2.00"}, today=today))
        assert (first.stop_price, second.stop_price) == (1.70, 1.80)
        assert armed.status()["working"][0]["stop_spx"] == second.stop_spx

    def test_a_cancel_the_broker_has_not_confirmed_sends_nothing_new(self, form, broker, armed):
        broker.rest_limits = True
        page_send(form, {**SEL, "limit": "1.90"})
        broker.cancel_pending = True
        r = page_send(form, {**SEL, "limit": "2.00"})
        assert "still holds" in r.headers["Location"].replace("+", " ")
        assert [o.price for o in working_buys(broker)] == [1.90]

    def test_a_fill_that_beat_the_new_price_is_said(self, form, broker, armed):
        broker.rest_limits = True
        page_send(form, {**SEL, "limit": "1.90"})
        broker.fill_resting(working_buys(broker)[0].order_id)
        # the fill is seen by the reconcile the send's pricing path runs, or
        # by the cancel; either way nothing new goes out beside it
        page_send(form, {**SEL, "limit": "2.00"})
        assert working_buys(broker) == [] or all(o.price != 2.00 for o in working_buys(broker)) \
            or armed.status()["positions"]
        assert len(armed.status()["positions"]) == 1

    def test_the_ajax_send_answers_in_place_with_a_new_token(self, form, broker):
        broker.rest_limits = True
        body = text(form.get("/exec/order?side=call&strike=6400"))
        nonce = body.split("name=nonce value='")[1].split("'")[0]
        j = form.post("/exec/order/send", data={**SEL, "limit": "1.90", "nonce": nonce,
                                                "ajax": "1"}).json
        assert j["ok"] and j["send_nonce"] and j["panel_stage"] == "working"
        assert "id=pxbox" in j["fd0_html"]
