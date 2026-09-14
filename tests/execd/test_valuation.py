"""The position's money, on the status body and the page. [st-k6gl]

Steve, 2026-09-14: "the unrealized pnl including all aspects of the order
needs to display on the page." Every part: cost, value at the bid, the
commissions both ways, the net if closed now, the net at the stop, and the
day's realized beside it.
"""

from __future__ import annotations

import pytest

from execd.service import ExecService

from .conftest import CALL, SPX_NOW, entry


def test_valuation_counts_every_part_of_the_order(armed: ExecService, broker):
    out = armed.place(entry("v-1", stop_spx=SPX_NOW - 3.0))     # fills at 2.10, stop rests at 1.20
    assert out["order"]["fill_price"] == 2.10
    broker.set_quote(CALL, bid=2.00, ask=2.10)
    st = armed.status()
    p = st["positions"][0]
    v = p["valuation"]
    assert p["entry_commission_usd"] == 0.65                      # from the broker's preview
    assert v["cost_usd"] == 210.0
    assert (v["bid"], v["ask"]) == (2.00, 2.10)
    assert v["value_usd"] == 200.0                                # at the bid, not the mid
    assert v["unrealized_usd"] == -10.0
    assert v["commissions_usd"] == 1.30 and v["exit_commission_usd"] == 0.65
    assert v["net_if_closed_usd"] == -11.30
    assert v["at_stop_usd"] == pytest.approx((1.20 - 2.10) * 100 - 1.30)
    assert v["error"] is None

    # the day: nothing realized yet, unrealized net carried up
    assert st["pnl"] == {"realized_usd": 0.0, "closes": 0,
                         "unrealized_net_usd": -11.30, "day_usd": -11.30}


def test_one_status_call_strikes_the_position_and_the_day_at_one_quote(armed: ExecService, broker):
    """14:37 CT, 2026-09-14: the position row said -6.30 and the day row
    -1.30 on the same page — two quote reads inside one status call."""
    armed.place(entry("v-5"))
    reads = []
    real_quote = broker.quote

    def moving(symbol):
        q = real_quote(symbol)
        if symbol == CALL:
            reads.append(1)
            broker.set_quote(CALL, bid=2.00 - 0.05 * len(reads), ask=2.10)   # moves after every read
        return q

    broker.quote = moving
    st = armed.status()
    assert reads.count(1) == 1                                    # one read for the position
    assert st["pnl"]["unrealized_net_usd"] == st["positions"][0]["valuation"]["net_if_closed_usd"]


def test_a_quote_that_cannot_be_read_leaves_the_money_blank_not_wrong(armed: ExecService, broker):
    armed.place(entry("v-2"))
    broker.fail_next = "down"
    v = armed.status()["positions"][0]["valuation"]
    assert v["value_usd"] is None and v["net_if_closed_usd"] is None
    assert "down" in v["error"]
    assert v["cost_usd"] == 210.0 and v["commissions_usd"] == 1.30   # what needs no quote


def test_realized_comes_from_the_journal_and_gains_are_positive(armed: ExecService, broker):
    armed.place(entry("v-3"))
    broker.set_quote(CALL, bid=2.60, ask=2.70)
    armed.flatten(reason="page")                                  # sells at the bid, 2.60
    pnl = armed.status()["pnl"]
    assert pnl == {"realized_usd": 50.0, "closes": 1, "unrealized_net_usd": 0.0, "day_usd": 50.0}


def test_the_page_shows_the_position_and_refreshes_only_while_it_is_open(armed: ExecService, broker, tmp_path):
    import json
    import httpx
    from execd.page import CredentialFile, create_page
    from execd.vault import Vault
    from .test_page import CALLBACK, PASS, Schwab, market_payload, vault_payload

    vault = Vault(tmp_path / "vault.json")
    vault.store(vault_payload(), PASS)
    mfile = tmp_path / "market.json"
    mfile.write_text(json.dumps(market_payload()))
    market = CredentialFile(mfile)
    market.load()
    app = create_page(armed, vault=vault, market=market, callback_url=CALLBACK,
                      http_client=httpx.Client(base_url="https://api.schwabapi.com",
                                               transport=httpx.MockTransport(Schwab())))
    app.config["TESTING"] = True
    client = app.test_client()

    quiet = client.get("/exec/").get_data(as_text=True)
    assert "http-equiv=refresh" not in quiet and "Open position" not in quiet

    armed.place(entry("v-4", stop_spx=SPX_NOW - 3.0))
    broker.set_quote(CALL, bid=2.00, ask=2.10)
    body = client.get("/exec/").get_data(as_text=True)
    assert "http-equiv=refresh content=5" in body
    assert "Open position" in body and "SPXW  260914C06400000".replace("260914", "260826") in body
    assert "value at the bid" in body and "$200.00" in body
    assert "NET IF CLOSED NOW" in body and "-$11.30" in body
    assert "commissions, in and out" in body and "$1.30" in body
    assert "at the stop" in body and "stop 1.20" in body
    assert "unrealized, net if closed now" in body
    assert "pos-down" in body
