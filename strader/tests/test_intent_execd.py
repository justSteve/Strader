"""The desk's door to the execution service — preview only. [st-k6gl, stage 4]

What ``go`` hands the service, what it says back, and the three ways the
service can fail to answer — each one leaving the paste line standing and
sending nothing. The service itself is a fake here; ``tests/execd/
test_desk_join.py`` runs the same path through the real API over the mock
broker.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from strader.execution.compose import Ticket
from strader.intent.cli import load_chain, main
from strader.intent.execd import (
    Answer, DeskExecd, ExecdUnreachable, describe, intent_for, live_chain,
)
from strader.intent.session import Session

FIX = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "intent"
DAY = dt.date(2026, 8, 22)


def _chain():
    return load_chain(FIX / "chain-6320.json")


class FakeExecd:
    """Answers with whatever it was told; remembers what it was asked."""

    def __init__(self, answer: Answer | Exception) -> None:
        self.answer = answer
        self.intents: list[dict] = []

    def preview(self, intent: dict) -> Answer:
        self.intents.append(intent)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _accepted(cost=155.0, commission=0.65) -> Answer:
    return Answer(200, {"refused": None, "would_send": True, "preview": {
        "symbol": "SPXW  260822C06320000", "side": "BUY_TO_OPEN", "qty": 1,
        "order_type": "LIMIT", "price": 1.55, "cost_usd": cost,
        "commission_usd": commission, "total_usd": round(cost + commission, 2),
        "accepted": True, "messages": []}})


def _priced_single(tmp_path, execd) -> Session:
    s = Session(plan_dir=tmp_path, day=DAY, execd=execd)
    s.single("one 6320 call, 0DTE")
    s.price(_chain())
    assert s.plan.bracket is not None
    return s


# ── what go hands the service ────────────────────────────────────────────

def test_go_previews_a_single_through_execd(tmp_path):
    fake = FakeExecd(_accepted())
    s = _priced_single(tmp_path, fake)
    out = s.go()

    # the paste line stands, and the service's answer follows it
    assert "Staged, nothing sent" in out
    assert "Execd preview, nothing sent" in out and "$155.00" in out and "$0.65" in out
    assert "the broker accepts it" in out

    # the intent is the priced order as data, with the stop's two inputs
    assert len(fake.intents) == 1
    i = fake.intents[0]
    t = Ticket.from_dict(s.plan.bracket)
    assert i["symbol"] == "SPXW  260822C06320000"
    assert i["side"] == "BUY_TO_OPEN" and i["qty"] == 1 and i["order_type"] == "LIMIT"
    assert i["limit"] == 1.55                                   # the ask, as priced
    assert i["stop_spx"] == t.stop_trigger_spx
    assert i["delta"] == pytest.approx(abs(t.derivation.delta_live), abs=1e-4)
    assert i["source"] == "intent-desk"
    assert i["intent_id"].startswith("desk-")

    # the staged record carries the intent and the answer, under the same id
    rec = json.loads(next((tmp_path / "staged").glob("*-single.json")).read_text())
    assert rec["execd"]["routed"] is True
    assert rec["execd"]["intent"] == i
    assert rec["execd"]["status"] == 200
    assert rec["execd"]["answer"]["preview"]["total_usd"] == 155.65
    assert any("execd desk-" in line and "HTTP 200" in line for line in s.plan.log)


def test_the_intent_id_is_the_staged_files_stamp(tmp_path):
    """One name across the desk's record, the service's journal and, later,
    the live ticket."""
    fake = FakeExecd(_accepted())
    s = _priced_single(tmp_path, fake)
    s.go()
    staged = next((tmp_path / "staged").glob("*-single.json"))
    stamp = staged.name.split("-single")[0]
    assert fake.intents[0]["intent_id"] == f"desk-{stamp}"


def test_a_refusal_is_named_and_nothing_is_sent(tmp_path):
    fake = FakeExecd(Answer(409, {"refused": {"bound": "window",
                                              "reason": "nothing opens after 14:50 CT"},
                                  "order": None}))
    s = _priced_single(tmp_path, fake)
    out = s.go()
    assert "Staged, nothing sent" in out
    assert "Execd refused (window): nothing opens after 14:50 CT. Nothing sent." in out
    rec = json.loads(next((tmp_path / "staged").glob("*-single.json")).read_text())
    assert rec["execd"]["status"] == 409 and rec["execd"]["answer"]["refused"]["bound"] == "window"


def test_an_unreachable_service_leaves_the_paste_line_standing(tmp_path):
    fake = FakeExecd(ExecdUnreachable("execd unreachable at http://127.0.0.1:8778: "
                                      "URLError: connection refused"))
    s = _priced_single(tmp_path, fake)
    out = s.go()
    assert "Staged, nothing sent" in out
    assert "Execd not reachable" in out and "Staged only, nothing sent." in out
    assert "BUY +1 SPX 100 (Weeklys) 22 AUG 26 6320 CALL @1.55 LMT" in out
    rec = json.loads(next((tmp_path / "staged").glob("*-single.json")).read_text())
    assert rec["execd"]["routed"] is True and "unreachable" in rec["execd"]["error"]
    assert "intent" in rec["execd"]                              # what would have gone


def test_a_fly_is_not_routed(tmp_path):
    """The service sends single legs only; a fly stays on the paste line and
    the record says why."""
    fake = FakeExecd(_accepted())
    s = Session(plan_dir=tmp_path, day=DAY, execd=fake)
    s.fly("6320, twenty wide, 0DTE calls, two lots")
    s.price(_chain())
    out = s.go()
    assert fake.intents == []
    assert "Not previewed through execd: the service sends single legs only" in out
    rec = json.loads(next((tmp_path / "staged").glob("*-butterfly.json")).read_text())
    assert rec["execd"]["routed"] is False and "single legs" in rec["execd"]["reason"]


def test_no_service_wired_means_the_desk_as_before(tmp_path):
    s = Session(plan_dir=tmp_path, day=DAY)                     # execd=None
    s.single("one 6320 call, 0DTE")
    s.price(_chain())
    out = s.go()
    assert "Execd" not in out
    rec = json.loads(next((tmp_path / "staged").glob("*-single.json")).read_text())
    assert "execd" not in rec


def test_a_single_without_a_bracket_still_goes_and_the_service_judges(tmp_path):
    """FD0 could not fund a stop → no bracket → the intent carries no stop
    inputs. It still goes: the service's own bound refuses it, and that
    refusal is the record, not a quiet skip at the desk."""
    fake = FakeExecd(Answer(409, {"refused": {"bound": "protective_stop",
                                              "reason": "an entry must carry stop_spx and delta"},
                                  "order": None}))
    s = Session(plan_dir=tmp_path, day=DAY, execd=fake)
    s.single("one 6320 call, 0DTE")
    s.price(_chain())
    s.plan.bracket = None                                       # as CannotFund leaves it
    out = s.go()
    assert fake.intents and "stop_spx" not in fake.intents[0]
    assert "Execd refused (protective_stop)" in out


# ── intent_for and describe on their own ─────────────────────────────────

def test_intent_for_applies_the_services_own_rules():
    from strader.intent.entities import Order
    o = Order(action="BUY", quantity=1, spread_type="SINGLE", expiry=DAY, strikes=(6320.0,),
              right="CALL", price=1.55)
    d = intent_for(o, None, intent_id="desk-20260822T101500", engine_sha="abc1234")
    assert d == {"intent_id": "desk-20260822T101500", "symbol": "SPXW  260822C06320000",
                 "side": "BUY_TO_OPEN", "qty": 1, "order_type": "LIMIT", "limit": 1.55,
                 "source": "intent-desk", "engine_sha": "abc1234"}
    with pytest.raises(ValueError, match="intent_id"):
        intent_for(o, None, intent_id="x")                      # too short for the service


def test_describe_every_branch_says_nothing_was_sent():
    assert "Nothing sent" in describe(Answer(400, {"error": "bad_request",
                                                   "detail": "qty must be a positive integer"}))
    assert "malformed" in describe(Answer(400, {"error": "bad_request", "detail": "x"}))
    assert "could not reach the broker" in describe(Answer(502, {"error": "broker", "detail": "down"}))
    assert "HTTP 500" in describe(Answer(500, {"detail": "boom"}))
    rejected = _accepted()
    rejected.body["preview"]["accepted"] = False
    rejected.body["preview"]["messages"] = ["reject: insufficient buying power"]
    text = describe(rejected)
    assert "would REJECT" in text and "broker: reject: insufficient buying power" in text


# ── the live chain through the door ──────────────────────────────────────

def _schwab_chain_body() -> dict:
    return {"symbol": "$SPX", "status": "SUCCESS", "underlyingPrice": 6321.5,
            "callExpDateMap": {"2026-08-22:0": {"6320.0": [{
                "symbol": "SPXW  260822C06320000", "strikePrice": 6320.0,
                "expirationDate": "2026-08-22T15:00:00-05:00", "bid": 1.45, "ask": 1.55,
                "last": 1.5, "delta": 0.52, "totalVolume": 10, "openInterest": 5}]}},
            "putExpDateMap": {"2026-08-22:0": {"6320.0": [{
                "symbol": "SPXW  260822P06320000", "strikePrice": 6320.0,
                "expirationDate": "2026-08-22T15:00:00-05:00", "bid": 1.60, "ask": 1.70,
                "delta": -0.48}]}}}


def test_live_chain_asks_the_market_door_for_one_expiry():
    seen = []

    def transport(method, url, body, timeout):
        seen.append((method, url, body))
        return 200, json.dumps(_schwab_chain_body()).encode()

    chain = live_chain(DeskExecd("http://x", transport=transport), DAY)
    method, url, body = seen[0]
    assert method == "GET" and body is None
    assert url.startswith("http://x/marketdata/chains?")
    assert "symbol=%24SPX" in url and "fromDate=2026-08-22" in url and "toDate=2026-08-22" in url
    assert "contractType=ALL" in url and "includeUnderlyingQuote=true" in url
    assert chain.underlying_price == 6321.5 and chain.expiry == DAY
    assert chain.call(6320).ask == 1.55 and chain.call(6320).symbol == "SPXW  260822C06320000"
    assert chain.put(6320).delta == -0.48


def test_live_chain_refuses_an_empty_answer():
    def transport(method, url, body, timeout):
        return 200, json.dumps({"symbol": "$SPX", "status": "FAILED",
                                "callExpDateMap": {}, "putExpDateMap": {}}).encode()
    with pytest.raises(ValueError, match="no \\$SPX contracts expiring 2026-08-22"):
        live_chain(DeskExecd("http://x", transport=transport), DAY)


def test_live_chain_reports_a_non_200_as_unreachable():
    def transport(method, url, body, timeout):
        return 502, json.dumps({"error": "broker", "detail": "schwab down"}).encode()
    with pytest.raises(ExecdUnreachable, match="HTTP 502"):
        live_chain(DeskExecd("http://x", transport=transport), DAY)


def test_preview_posts_json_and_returns_the_status_and_body():
    seen = []

    def transport(method, url, body, timeout):
        seen.append((method, url, body))
        return 409, json.dumps({"refused": {"bound": "stop", "reason": "STOP is on"}}).encode()

    ans = DeskExecd("http://x/", transport=transport).preview({"intent_id": "desk-1"})
    assert seen[0][0] == "POST" and seen[0][1] == "http://x/preview"
    assert json.loads(seen[0][2]) == {"intent_id": "desk-1"}
    assert ans.status == 409 and ans.refused == {"bound": "stop", "reason": "STOP is on"}


def test_a_dead_socket_is_unreachable_not_a_crash():
    with pytest.raises(ExecdUnreachable, match="unreachable"):
        DeskExecd("http://127.0.0.1:1", timeout_s=2).preview({"intent_id": "desk-1"})


# ── the command line ─────────────────────────────────────────────────────

def test_cli_chain_live_says_so_when_the_service_is_down(tmp_path, capsys):
    rc = main(["--once", "price", "--chain", "live", "--execd", "http://127.0.0.1:1",
               "--plan-dir", str(tmp_path), "--day", "2026-08-22"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Could not fetch the live chain" in out and "unreachable" in out


def test_cli_no_execd_unwires_the_service(tmp_path, capsys):
    rc = main(["--once", "single one 6320 call, 0DTE", "--no-execd",
               "--plan-dir", str(tmp_path), "--day", "2026-08-22"])
    assert rc == 0
    rc = main(["--once", "price", "--chain", str(FIX / "chain-6320.json"), "--no-execd",
               "--plan-dir", str(tmp_path), "--day", "2026-08-22"])
    assert rc == 0 and "FD0 stop" in capsys.readouterr().out
    rc = main(["--once", "go", "--no-execd", "--plan-dir", str(tmp_path), "--day", "2026-08-22"])
    out = capsys.readouterr().out
    assert rc == 0 and "Staged, nothing sent" in out and "Execd" not in out


def test_cli_without_a_chain_names_both_doors(tmp_path, capsys):
    main(["--once", "price", "--no-execd", "--plan-dir", str(tmp_path), "--day", "2026-08-22"])
    assert "--chain live" in capsys.readouterr().out
