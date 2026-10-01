"""PAPER/LIVE from the account page, no installer; no STAND DOWN; FLATTEN only
with a position. [co-8mb1z]

Steve, 2026-09-25: "i would like the form to support moving between paper
and live without need to re-run the installer. The UI already renders a label
showing Paper - we just want to ensure that 'Live' is displayed when it is.
Place the toggle on the account page. Remove the 'Stand Down' button. Don't
render the 'Flatten' button unless there is an open position."

What is asserted: the precedence of the mode files; that after a flip every
path follows it (the broker the orders reach, the paper book, the journal's
mode, /status, the badge on both pages and in the poll); that it survives a
restart; that going live takes the passphrase and going back does not; the
one correctness refusal (something open or working); Alpaca without live keys
stays on paper in words; and the two buttons.
"""

from __future__ import annotations

import json

import pytest

from execd.alpaca import alpaca_payloads
from execd.page import create_page
from execd.paper import ModeSwitch, PaperBroker, current_mode, write_mode
from execd.service import ExecService, Refused, ServiceConfig
from execd.vault import Vault

from .conftest import CALL, Clock, entry, page_send, same_origin, schwab_chain_maps
from .test_page import PASS, WRONG, vault_payload


def make_service(broker, clock, tmp_path, mode="paper"):
    paper = PaperBroker(broker, book_path=tmp_path / "execd" / "paper-book.json", clock=clock)
    config = ServiceConfig(state_dir=tmp_path / "execd", sha="t", mode=mode, broker="schwab")
    return ExecService(ModeSwitch(paper, broker, mode), config, clock=clock)


@pytest.fixture
def svc(broker, clock, tmp_path):
    s = make_service(broker, clock, tmp_path)
    s.unlock({"token": "x"})
    return s


@pytest.fixture
def page(svc, broker, clock, tmp_path):
    broker.set_chain("SPXW", schwab_chain_maps())
    vault = Vault(tmp_path / "vault.json")
    vault.store(vault_payload(), PASS)
    app = create_page(svc, vault=vault, clock=clock)
    app.config["TESTING"] = True
    return same_origin(app.test_client())


def text(r) -> str:
    return r.get_data(as_text=True)


class TestPrecedence:
    def test_state_file_then_seed_then_paper(self, tmp_path):
        seed, state = tmp_path / "seed", tmp_path / "state"
        assert current_mode(seed, state) == "paper"             # neither
        seed.write_text("live\n")
        assert current_mode(seed, state) == "live"              # the seed
        write_mode(state, "paper")
        assert current_mode(seed, state) == "paper"             # the page's switch wins

    def test_a_garbled_state_file_falls_back_to_the_seed(self, tmp_path):
        (tmp_path / "seed").write_text("live\n")
        (tmp_path / "state").mkdir()
        (tmp_path / "state" / "mode").write_text("maybe\n")
        assert current_mode(tmp_path / "seed", tmp_path / "state") == "live"


class TestEveryPathFollowsTheFlip:
    def test_paper_orders_stay_in_the_book(self, svc, broker):
        svc.place(entry(intent_id="p-1"))
        assert broker.calls_to("place") == []                  # nothing reached the broker
        svc.flatten()

    def test_after_the_flip_orders_reach_the_broker_and_every_label_says_live(
            self, svc, broker, tmp_path):
        out = svc.set_mode("live")
        assert out["mode"] == "live" and svc.config.mode == "live"
        assert (tmp_path / "execd" / "mode").read_text().strip() == "live"
        placed = svc.place(entry(intent_id="l-1"))
        assert placed["mode"] == "live"
        assert [c["intent_id"] for c in broker.calls_to("place")][0] == "l-1"
        # the live journal holds live lines only; the switch itself is
        # recorded in the (now archived) paper journal, never in live (st-n4tr)
        lines = svc.journal.read()
        assert lines and {e["mode"] for e in lines} == {"live"}
        assert "mode_changed" not in [e["event"] for e in lines]
        assert svc.status()["mode"] == "live"

    def test_the_flip_survives_a_restart(self, svc, broker, clock, tmp_path):
        svc.set_mode("live")
        mode = current_mode(tmp_path / "no-seed", tmp_path / "execd")
        again = make_service(broker, clock, tmp_path, mode=mode)
        assert again.config.mode == "live" and again.broker.mode == "live"

    def test_back_to_paper(self, svc, broker):
        svc.set_mode("live")
        svc.set_mode("paper")
        svc.place(entry(intent_id="p-2"))
        assert broker.calls_to("place") == []

    def test_a_contract_opened_in_paper_is_not_ours_in_live(self, svc, broker):
        svc.place(entry(intent_id="p-3"))
        svc.flatten()
        svc.set_mode("live")
        assert CALL not in svc._owned_symbols()


class TestTheOneRefusal:
    def test_a_flip_with_a_position_open_is_refused_in_words(self, svc):
        svc.place(entry(intent_id="o-1"))
        with pytest.raises(Refused) as exc:
            svc.set_mode("live")
        assert exc.value.refusal.bound == "mode" and "FLATTEN" in exc.value.refusal.reason
        assert svc.config.mode == "paper"
        svc.flatten()
        assert svc.set_mode("live")["mode"] == "live"

    def test_a_working_order_holds_the_flip_too(self, svc, broker, clock, tmp_path):
        broker.rest_limits = True
        live = make_service(broker, clock, tmp_path / "b", mode="live")
        live.unlock({"token": "x"})
        live.place(entry(intent_id="w-1"))
        with pytest.raises(Refused):
            live.set_mode("paper")


class TestThePage:
    def test_the_switch_is_on_the_account_page_and_live_needs_the_passphrase(
            self, page, svc, monkeypatch):
        monkeypatch.setattr("execd.page.time.sleep", lambda s: None)
        body = text(page.get("/exec/account"))
        assert "switch to LIVE" in body and "name=passphrase" in body
        r = page.post("/exec/mode", data={"to": "live", "passphrase": WRONG})
        assert r.status_code == 303 and svc.config.mode == "paper"
        page.post("/exec/mode", data={"to": "live", "passphrase": PASS})
        assert svc.config.mode == "live"

    def test_live_reads_live_on_every_page_and_in_the_poll(self, page, svc):
        page.post("/exec/mode", data={"to": "live", "passphrase": PASS})
        acct = text(page.get("/exec/account"))
        order = text(page.get("/exec/order"))
        for body in (acct, order):
            assert "<span class='badge live'>LIVE</span>" in body
            assert "badge paper" not in body
        assert "id=strip" in order and "getElementById('strip')" in order
        polled = page.get("/exec/order/state").json
        assert polled["mode"] == "live" and "badge live" in polled["state_html"]

    def test_back_to_paper_is_one_tap(self, page, svc):
        page.post("/exec/mode", data={"to": "live", "passphrase": PASS})
        body = text(page.get("/exec/account"))
        assert "switch to PAPER" in body
        page.post("/exec/mode", data={"to": "paper"})
        assert svc.config.mode == "paper"

    def test_a_refused_flip_says_why(self, page, svc):
        svc.place(entry(intent_id="o-2"))
        r = page.post("/exec/mode", data={"to": "live", "passphrase": PASS})
        assert "FLATTEN" in r.headers["Location"].replace("+", " ")
        assert svc.config.mode == "paper"


class TestAlpacaLiveKeys:
    def test_no_live_keys_stays_on_paper_in_words(self):
        env = {"alpaca": {"paper": {"key_id": "PK", "secret_key": "S"}}}
        assert set(alpaca_payloads(env)["venues"]) == {"paper"}
        with pytest.raises(ValueError, match="no Alpaca live keys"):
            alpaca_payloads(env, need="live")

    def test_the_envelope_serves_each_venue_its_own_keys(self):
        import httpx
        from execd.alpaca import AlpacaBroker
        env = alpaca_payloads({"alpaca": {"paper": {"key_id": "PK", "secret_key": "S"},
                                          "live": {"key_id": "AK", "secret_key": "T"}}})
        seen = {}

        def handler(request):
            seen[request.url.host] = request.headers["APCA-API-KEY-ID"]
            return httpx.Response(200, json=[])

        for venue in ("paper", "live"):
            AlpacaBroker(venue, lambda: env, transport=httpx.MockTransport(handler)).orders()
        assert seen == {"paper-api.alpaca.markets": "PK", "api.alpaca.markets": "AK"}

    def test_the_page_refuses_live_without_the_keys(self, broker, clock, tmp_path):
        svc = make_service(broker, clock, tmp_path)
        svc.unlock({"token": "x"})
        vault = Vault(tmp_path / "v.json")
        vault.store({"alpaca": {"paper": {"key_id": "PK", "secret_key": "S"}}}, PASS)
        app = create_page(svc, vault=vault, clock=clock,
                          mode_credential=lambda vp, to: alpaca_payloads(vp, need=to))
        app.config["TESTING"] = True
        client = same_origin(app.test_client())
        r = client.post("/exec/mode", data={"to": "live", "passphrase": PASS})
        assert "no Alpaca live keys" in r.headers["Location"].replace("+", " ")
        assert svc.config.mode == "paper"


class TestButtons:
    def test_no_stand_down_on_any_screen(self, page, svc):
        page_send(page, {"side": "call", "strike": "6400"})
        for path in ("/exec/", "/exec/order", "/exec/account"):
            body = text(page.get(path)).lower()
            assert "stand down" not in body and "stand_down" not in body, path
        polled = page.get("/exec/order/state").json
        for key in ("panel_body_html", "state_html", "position_html"):
            assert "stand" not in str(polled.get(key) or "").lower(), key

    def test_flatten_only_while_a_position_is_open(self, page, svc):
        for path in ("/exec/account", "/exec/order"):
            assert ">FLATTEN<" not in text(page.get(path)), path
        assert ">FLATTEN<" not in page.get("/exec/order/state").json["panel_body_html"]
        page_send(page, {"side": "call", "strike": "6400"})
        assert svc.status()["positions"]
        assert ">FLATTEN<" in text(page.get("/exec/account"))
        assert ">FLATTEN<" in page.get("/exec/order/state").json["panel_body_html"]
        svc.flatten()
        assert ">FLATTEN<" not in text(page.get("/exec/account"))
        assert ">FLATTEN<" not in page.get("/exec/order/state").json["panel_body_html"]


class TestPaperAndLiveNeverMix:
    """Steve, 2026-10-01 (st-n4tr): "Switching between paper and live should
    re-set the paper-side journal and P&L. Live should never see paper's
    trades and vice versa." """

    @staticmethod
    def closes(svc):
        return [e for e in svc.journal.read() if e.get("event") == "closed"]

    def test_paper_trades_then_live_sees_none_then_paper_is_fresh_and_archived(
            self, svc, broker, tmp_path):
        from execd.panel import journal_facts
        svc.place(entry(intent_id="p-1"))
        svc.flatten()
        assert self.closes(svc) and svc.status()["pnl"]["realized_usd"] != 0
        paper_file = svc.journal.path_for()
        assert paper_file.parent.name == "paper"
        svc.set_mode("live")
        st = svc.status()
        assert st["pnl"]["realized_usd"] == 0 and st["positions"] == [] and st["working"] == []
        assert journal_facts(svc)["closes"] == [] and svc.journal.read() == []
        assert not paper_file.exists()                       # moved aside, not deleted
        archived = list((tmp_path / "execd" / "journal" / "paper-archive").rglob("*.jsonl"))
        assert archived and any('"p-1"' in f.read_text() for f in archived)
        assert list((tmp_path / "execd" / "journal" / "paper-archive").rglob("paper-book.json"))
        # a live trade: live's own P&L, and the live journal holds only it
        svc.place(entry(intent_id="l-1"))
        svc.flatten()
        live_closes = self.closes(svc)
        assert [c["intent_id"] for c in live_closes] == ["l-1"]
        live_file = svc.journal.path_for()
        live_bytes = live_file.read_bytes()
        # back to paper: fresh, $0, no live fills, the live journal untouched
        svc.set_mode("paper")
        st = svc.status()
        assert st["pnl"]["realized_usd"] == 0 and journal_facts(svc)["closes"] == []
        assert [e["event"] for e in svc.journal.read()] == ["mode_changed"]
        assert live_file.read_bytes() == live_bytes
        assert all(e.get("intent_id") != "l-1" for e in svc.journal.read())

    def test_live_then_paper_shows_no_live_fill(self, broker, clock, tmp_path):
        from execd.panel import journal_facts
        live = make_service(broker, clock, tmp_path, mode="live")
        live.unlock({"token": "x"})
        live.place(entry(intent_id="l-9"))
        live.flatten()
        assert [c["intent_id"] for c in self.closes(live)] == ["l-9"]
        live.set_mode("paper")
        assert live.status()["pnl"]["realized_usd"] == 0
        assert journal_facts(live)["closes"] == [] and journal_facts(live)["filled"] == {}
        live.place(entry(intent_id="p-9"))
        assert [p["intent_id"] for p in live.status()["positions"]] == ["p-9"]

    def test_paper_lines_written_into_the_shared_file_before_the_split_are_not_live(
            self, broker, clock, tmp_path):
        """Until st-n4tr both sides wrote one file a day; the paper lines
        already in it must never be read back as live."""
        live = make_service(broker, clock, tmp_path, mode="live")
        f = live.journal.path_for()
        f.write_text('{"event":"closed","mode":"paper","intent_id":"old-p","pnl_usd":-50}\n'
                     '{"event":"closed","mode":"live","intent_id":"old-l","pnl_usd":20}\n')
        assert [e["intent_id"] for e in live.journal.read()] == ["old-l"]
        assert live.status()["pnl"]["realized_gross_usd"] == 20

    def test_an_open_paper_position_refuses_the_switch_and_never_reaches_live(self, svc):
        svc.place(entry(intent_id="p-open"))
        with pytest.raises(Refused, match="FLATTEN or cancel first"):
            svc.set_mode("live")
        assert svc.config.mode == "paper" and svc.status()["positions"]
        assert svc.journal.path_for().exists()               # nothing archived

    def test_the_traffic_buffer_is_tagged_and_cleared_by_a_switch(self, page, svc):
        page_send(page, {"side": "call", "strike": "6400"})
        h = page.get("/exec/order/state?side=call").json["traffic_html"]
        assert "PAPER BUY 1 SPX 6400C" in h
        svc.flatten()
        svc.set_mode("live")
        h = page.get("/exec/order/state?side=call").json["traffic_html"]
        assert "PAPER" not in h and "no SEND yet" in h


def test_the_view_log_names_the_side(tmp_path):
    from execd.viewlog import ViewLog, order_record
    vl = ViewLog(tmp_path, start=False)
    for mode in ("paper", "paper", "live"):
        rec, disp = order_record(sel=None, priced=None, st={"mode": mode}, sendable=None)
        vl.offer("d", rec, disp)
        vl.drain(force=True)
    got = [json.loads(x)["mode"] for f in tmp_path.glob("*.jsonl") for x in f.read_text().splitlines()]
    assert got == ["paper", "live"]
