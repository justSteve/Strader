"""The desk meets the service: go → POST /preview, over the real API. [st-k6gl]

Stage 4's rehearsal path, end to end, with the mock broker standing in for
Schwab: the desk fetches its chain through the service's market door, prices
a single, and ``go`` hands the intent to the same Flask app the installed
service runs. What is asserted is the wire: the intent the service accepted,
the journal lines it wrote under the desk's id, the cost line that came back,
and — the load-bearing one — that the broker was asked to preview and never
to place.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from execd.api import create_app
from execd.service import ExecService
from strader.intent.execd import DeskExecd, live_chain
from strader.intent.session import Session

from .conftest import CALL, PUT, SPX_NOW

DAY = dt.date(2026, 8, 26)          # the conftest clock's day; CALL/PUT expire then


def _schwab_maps() -> dict:
    """The mock's chain body, in Schwab's shape, for the two contracts the
    conftest broker quotes. Strikes 6400 (call) and 6300 (put) around SPX 6380."""
    return {
        "calls": {"2026-08-26:0": {"6400.0": [{
            "symbol": CALL, "strikePrice": 6400.0, "expirationDate": "2026-08-26T15:00:00-05:00",
            "bid": 2.00, "ask": 2.10, "last": 2.05, "delta": 0.30}]}},
        "puts": {"2026-08-26:0": {"6300.0": [{
            "symbol": PUT, "strikePrice": 6300.0, "expirationDate": "2026-08-26T15:00:00-05:00",
            "bid": 1.80, "ask": 1.90, "last": 1.85, "delta": -0.28}]}},
    }


@pytest.fixture
def door(armed: ExecService, broker):
    """A DeskExecd whose transport is the Flask test client — the real routes,
    no socket."""
    broker.set_chain("SPXW", _schwab_maps())
    client = create_app(armed).test_client()
    base = "http://execd.test"

    def transport(method, url, body, timeout):
        assert url.startswith(base)
        r = client.open(url[len(base):], method=method, data=body,
                        content_type="application/json" if body is not None else None)
        return r.status_code, r.data

    return DeskExecd(base, transport=transport)


def _placed(broker) -> list:
    return [c for c in broker.calls if c[0] == "place"]


def test_the_rehearsal_path_live_chain_price_go_preview(door, armed, broker, tmp_path):
    chain = live_chain(door, DAY)
    assert chain.underlying_price == SPX_NOW and chain.call(6400).ask == 2.10

    s = Session(plan_dir=tmp_path, day=DAY, execd=door)
    s.single("one call, 0DTE")
    out = s.price(chain)
    assert "6400" in out and "FD0 stop" in out
    out = s.go()

    # the read-back: the paste line, then the service's cost line
    assert "Staged, nothing sent" in out
    assert "Execd preview, nothing sent: SPXW  260826C06400000 BUY_TO_OPEN x1 LIMIT at 2.10" in out
    assert "cost $210.00, commission $0.65, total $210.65; the broker accepts it." in out

    # the broker was asked to preview, and never to place
    assert [c[0] for c in broker.calls if c[0] in ("preview", "place")] == ["preview"]
    assert _placed(broker) == []

    # the service journaled the request and the preview under the desk's id
    rec = json.loads(next((tmp_path / "staged").glob("*-single.json")).read_text())
    intent_id = rec["execd"]["intent"]["intent_id"]
    lines = [e for e in armed.journal.read(DAY) if e.get("intent_id") == intent_id]
    assert [e["event"] for e in lines] == ["request", "preview"]
    assert lines[0]["kind"] == "preview" and lines[0]["intent"]["source"] == "intent-desk"
    assert lines[0]["intent"]["stop_spx"] == rec["fd0"]["stop_trigger_spx"]
    assert lines[1]["preview"]["total_usd"] == 210.65
    assert armed.status()["positions"] == [] and armed.status()["working"] == []


def test_stop_on_means_the_service_refuses_the_rehearsal_too(door, armed, broker, tmp_path):
    s = Session(plan_dir=tmp_path, day=DAY, execd=door)
    s.single("one call, 0DTE")
    s.price(live_chain(door, DAY))
    armed.stop()
    out = s.go()
    assert "Execd refused (" in out and "Nothing sent." in out
    assert [c[0] for c in broker.calls if c[0] in ("preview", "place")] == []
    rec = json.loads(next((tmp_path / "staged").glob("*-single.json")).read_text())
    assert rec["execd"]["status"] == 409


def test_locked_service_refuses_and_the_paste_line_stands(service, broker, tmp_path):
    """Before Steve unlocks, the market door answers (the chain comes back)
    and the entry door refuses — the desk says both plainly."""
    broker.set_chain("SPXW", _schwab_maps())
    client = create_app(service).test_client()

    def transport(method, url, body, timeout):
        r = client.open(url[len("http://t"):], method=method, data=body,
                        content_type="application/json" if body is not None else None)
        return r.status_code, r.data

    door = DeskExecd("http://t", transport=transport)
    s = Session(plan_dir=tmp_path, day=DAY, execd=door)
    s.single("one put, 0DTE")
    out = s.price(live_chain(door, DAY))
    assert "6300" in out
    out = s.go()
    assert "BUY +1 SPX 100 (Weeklys) 26 AUG 26 6300 PUT @1.90 LMT" in out
    assert "Execd refused (" in out and "Nothing sent." in out
    assert not any(c[0] in ("preview", "place") for c in broker.calls)


def test_a_transport_that_keeps_the_raw_body_gets_it_journaled(armed, broker, tmp_path):
    """The mock keeps no raw body (there is none), so the line is absent; a
    transport that does — Schwab's — gets a ``preview_raw`` line under the
    same intent id, and the API's answer stays the shaped dict."""
    from dataclasses import replace
    from .conftest import entry

    plain = armed.preview(entry("t-plain"))
    assert "raw" not in plain["preview"]
    assert [e["event"] for e in armed.journal.find("t-plain")] == ["request", "preview"]

    real_preview = broker.preview
    body = {"orderStrategy": {"orderBalance": {"orderValue": 210.0, "projectedCommission": 0.65}},
            "orderValidationResult": {"rejects": []}}
    broker.preview = lambda i: replace(real_preview(i), raw=body)
    out = armed.preview(entry("t-raw"))
    assert "raw" not in out["preview"]
    lines = armed.journal.find("t-raw")
    assert [e["event"] for e in lines] == ["request", "preview", "preview_raw"]
    assert lines[2]["body"] == body


def test_the_desk_has_no_way_to_place():
    """The wall, asserted: the desk's client cannot be asked to send."""
    assert not hasattr(DeskExecd, "place")
    assert not hasattr(DeskExecd, "cancel")
    assert not hasattr(DeskExecd, "flatten")
