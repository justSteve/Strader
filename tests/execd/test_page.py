"""The page — Steve's surface, and the one rule it holds. [st-p8k8]

Every action that ADDS capability takes the passphrase (unlock, clear STOP,
store a re-authorised grant); every action that REDUCES it does not (STOP,
stand down, lock, flatten). The tests below drive the page with Flask's test
client against the mock broker, a real vault in a temp dir, and — for the
re-authorisation — an ``httpx.MockTransport`` standing in for Schwab, so the
whole flow runs with no network and no credential in the room.

What is asserted beyond behaviour: that no passphrase and no token value ever
reaches the journal or a rendered page, and that the page's URL map holds
exactly the routes the design names.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from execd.arming import ArmState
from execd.page import (CONFIRM_TTL_S, REAUTH_TTL_S, CredentialFile, PageRefused,
                        create_page)
from execd.service import ExecService
from execd.vault import Vault

from .conftest import CALL, Clock, entry

PASS = "correct horse battery"
WRONG = "wrong horse battery"
CALLBACK = "https://127.0.0.1:8182"


def wrapped(refresh: str, access: str = "acc", created: int = 1_757_000_000) -> dict:
    return {"creation_timestamp": created,
            "token": {"access_token": access, "refresh_token": refresh,
                      "expires_at": created + 1800, "token_type": "Bearer"}}


def vault_payload(refresh: str = "trading-refresh-old") -> dict:
    return {"version": 2, "trading": {"app": {"key": "TKEY", "secret": "TSECRET"},
                                      "token": wrapped(refresh)}}


def market_payload(refresh: str = "market-refresh-old") -> dict:
    return {"app": {"key": "MKEY", "secret": "MSECRET"}, "token": wrapped(refresh)}


class Schwab:
    """A stand-in for the two OAuth calls and the two verify calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.refresh_token_in_grant = True
        self.verify_status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        if request.url.path == "/v1/oauth/token":
            body = {"access_token": "new-access", "expires_in": 1800, "token_type": "Bearer"}
            if self.refresh_token_in_grant:
                body["refresh_token"] = "new-refresh"
            return httpx.Response(200, json=body)
        if request.url.path == "/trader/v1/accounts/accountNumbers":
            return httpx.Response(self.verify_status,
                                  json=[{"accountNumber": "1", "hashValue": "h"}])
        if request.url.path == "/marketdata/v1/quotes":
            return httpx.Response(self.verify_status, json={"$SPX": {"quote": {}}})
        return httpx.Response(404, json={})


@pytest.fixture
def vault(tmp_path) -> Vault:
    v = Vault(tmp_path / "vault.json")
    v.store(vault_payload(), PASS)
    return v


@pytest.fixture
def market(tmp_path) -> CredentialFile:
    path = tmp_path / "market.json"
    path.write_text(json.dumps(market_payload()))
    holder = CredentialFile(path)
    holder.load()
    return holder


@pytest.fixture
def schwab() -> Schwab:
    return Schwab()


@pytest.fixture
def mono():
    class Mono:
        t = 1000.0

        def __call__(self) -> float:
            return self.t

    return Mono()


@pytest.fixture
def page(service: ExecService, vault: Vault, market: CredentialFile, schwab: Schwab,
         clock: Clock, mono):
    app = create_page(service, vault=vault, market=market, callback_url=CALLBACK,
                      http_client=httpx.Client(base_url="https://api.schwabapi.com",
                                               transport=httpx.MockTransport(schwab)),
                      clock=clock, monotonic=mono)
    app.config["TESTING"] = True
    return app.test_client()


def text(r) -> str:
    return r.get_data(as_text=True)


def landing(client, r) -> str:
    """Follow the 303 and return the index page's text."""
    assert r.status_code == 303, (r.status_code, text(r))
    return text(client.get(r.headers["Location"]))


# ── unlock ────────────────────────────────────────────────────────────────

class TestUnlock:
    def test_the_right_passphrase_arms_until_the_close(self, page, service):
        body = landing(page, page.post("/exec/unlock", data={"passphrase": PASS}))
        assert service.arming.state is ArmState.ARMED
        assert "Armed until 15:00 CT" in body
        assert service.arming.credential()["app"]["key"] == "TKEY"

    def test_the_wrong_passphrase_leaves_it_locked_and_journals_no_value(
            self, page, service, monkeypatch):
        monkeypatch.setattr("execd.page.time.sleep", lambda s: None)
        body = landing(page, page.post("/exec/unlock", data={"passphrase": WRONG}))
        assert service.arming.state is ArmState.LOCKED
        assert "did not open" in body
        refused = [e for e in service.journal.read() if e["event"] == "refused"]
        assert refused and refused[-1]["refused"]["bound"] == "passphrase"
        raw = service.journal.path_for().read_text()
        assert WRONG not in raw and PASS not in raw

    def test_no_vault_says_so_in_plain_words(self, service, market, tmp_path, clock, mono):
        app = create_page(service, vault=tmp_path / "absent.json", market=market,
                          clock=clock, monotonic=mono)
        c = app.test_client()
        body = landing(c, c.post("/exec/unlock", data={"passphrase": PASS}))
        assert "no vault" in body and "execd_vault_init" in body
        assert service.arming.state is ArmState.LOCKED

    def test_after_the_close_an_unlock_arms_until_the_end_of_the_day(self, page, service, clock):
        clock.set_ct(15, 30)
        body = landing(page, page.post("/exec/unlock", data={"passphrase": PASS}))
        assert "Armed until 23:59 CT" in body and service.arming.state is ArmState.ARMED

    def test_the_page_never_shows_a_passphrase_or_token(self, page, service):
        landing(page, page.post("/exec/unlock", data={"passphrase": PASS}))
        body = text(page.get("/exec/"))
        for secret in (PASS, "trading-refresh-old", "TSECRET", "MSECRET", "acc"):
            assert secret not in body.replace("access", "")  # 'acc' is a prefix of that word


# ── stop / resume ─────────────────────────────────────────────────────────

class TestStop:
    def test_stop_needs_nothing(self, page, service):
        assert not service.arming.killed
        body = landing(page, page.post("/exec/stop"))
        assert service.arming.killed and "STOP is on" in body

    def test_resume_needs_the_passphrase(self, page, service, monkeypatch):
        monkeypatch.setattr("execd.page.time.sleep", lambda s: None)
        page.post("/exec/stop")
        landing(page, page.post("/exec/resume", data={"passphrase": WRONG}))
        assert service.arming.killed, "a wrong passphrase must not clear STOP"
        landing(page, page.post("/exec/resume", data={"passphrase": PASS}))
        assert not service.arming.killed

    def test_resume_without_a_passphrase_field_is_refused(self, page, service, monkeypatch):
        monkeypatch.setattr("execd.page.time.sleep", lambda s: None)
        page.post("/exec/stop")
        landing(page, page.post("/exec/resume"))
        assert service.arming.killed


# ── stand down, lock, flatten ─────────────────────────────────────────────

class TestReduceCapability:
    def test_stand_down_and_lock_need_nothing(self, page, service):
        page.post("/exec/unlock", data={"passphrase": PASS})
        page.post("/exec/stand-down")
        assert service.arming.state is ArmState.STOOD_DOWN
        page.post("/exec/lock")
        assert service.arming.state is ArmState.LOCKED

    def test_flatten_asks_once_more_and_the_confirm_is_single_use(
            self, page, service, broker, mono):
        service.unlock({"t": 1})
        service.place(entry())
        assert service.status()["day"]["open_positions"] == 1
        r = page.post("/exec/flatten")
        assert r.status_code == 200 and "CONFIRM" in text(r)
        nonce = text(r).split("name=nonce value='")[1].split("'")[0]
        assert service.status()["day"]["open_positions"] == 1, "nothing sent yet"
        body = landing(page, page.post("/exec/flatten/confirm", data={"nonce": nonce}))
        assert "Flatten sent" in body
        assert service.status()["day"]["open_positions"] == 0
        body = landing(page, page.post("/exec/flatten/confirm", data={"nonce": nonce}))
        assert "used already" in body

    def test_a_stale_confirm_sends_nothing(self, page, service, mono):
        service.unlock({"t": 1})
        service.place(entry())
        nonce = text(page.post("/exec/flatten")).split("name=nonce value='")[1].split("'")[0]
        mono.t += CONFIRM_TTL_S + 1
        body = landing(page, page.post("/exec/flatten/confirm", data={"nonce": nonce}))
        assert "Nothing was sent" in body
        assert service.status()["day"]["open_positions"] == 1

    def test_flatten_while_locked_is_a_refusal_not_a_crash(self, page, service, mono):
        nonce = text(page.post("/exec/flatten")).split("name=nonce value='")[1].split("'")[0]
        body = landing(page, page.post("/exec/flatten/confirm", data={"nonce": nonce}))
        assert "Flatten refused" in body


# ── re-authorisation ──────────────────────────────────────────────────────

def start_reauth(page, app: str, passphrase: str = PASS) -> tuple[int, str, str]:
    r = page.post("/exec/reauth/link", data={"app": app, "passphrase": passphrase})
    body = text(r)
    state = body.split("name=state value='")[1].split("'")[0] if "name=state" in body else ""
    link = body.split("href='")[1].split("'")[0] if "href='" in body else ""
    return r.status_code, state, link


class TestReauth:
    def test_the_link_names_the_apps_key_and_the_callback(self, page):
        code, state, link = start_reauth(page, "trading")
        assert code == 200 and state and link.startswith("https://api.schwabapi.com/v1/oauth/authorize")
        assert "client_id=TKEY" in link and f"state={state}" in link
        assert "127.0.0.1%3A8182" in link or "127.0.0.1:8182" in link
        _, _, mlink = start_reauth(page, "market")
        assert "client_id=MKEY" in mlink

    def test_the_link_needs_the_passphrase(self, page, monkeypatch):
        monkeypatch.setattr("execd.page.time.sleep", lambda s: None)
        r = page.post("/exec/reauth/link", data={"app": "trading", "passphrase": WRONG})
        assert r.status_code == 303 and "did+not+open" in r.headers["Location"]

    def test_trading_grant_is_verified_then_stored_in_the_vault(
            self, page, service, vault, schwab):
        _, state, _ = start_reauth(page, "trading")
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE%40&state={state}&session=x"}))
        assert "trading app is re-authorised" in body, body
        assert ("POST", "/v1/oauth/token") in schwab.calls
        assert ("GET", "/trader/v1/accounts/accountNumbers") in schwab.calls
        stored = vault.load(PASS)
        assert stored["trading"]["token"]["token"]["refresh_token"] == "new-refresh"
        assert stored["trading"]["app"]["key"] == "TKEY", "the app pair is kept"
        assert stored["version"] == 2
        events = [e for e in service.journal.read() if e["event"] == "reauth"]
        assert events and events[-1]["app"] == "trading" and events[-1]["in_memory"] is False
        raw = service.journal.path_for().read_text()
        assert "new-refresh" not in raw and "new-access" not in raw and PASS not in raw

    def test_while_armed_the_credential_in_memory_is_swapped(self, page, service, schwab):
        page.post("/exec/unlock", data={"passphrase": PASS})
        assert service.arming.credential()["token"]["token"]["refresh_token"] == "trading-refresh-old"
        _, state, _ = start_reauth(page, "trading")
        landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state}"}))
        assert service.arming.state is ArmState.ARMED
        assert service.arming.credential()["token"]["token"]["refresh_token"] == "new-refresh"

    def test_market_grant_is_verified_against_its_own_family_and_written_to_its_file(
            self, page, service, market, schwab):
        _, state, _ = start_reauth(page, "market")
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state}"}))
        assert "market app is re-authorised" in body, body
        assert ("GET", "/marketdata/v1/quotes") in schwab.calls
        assert ("GET", "/trader/v1/accounts/accountNumbers") not in schwab.calls
        on_disk = json.loads(Path(market.path).read_text())
        assert on_disk["token"]["token"]["refresh_token"] == "new-refresh"
        assert on_disk["app"]["key"] == "MKEY"
        assert market.current()["token"]["token"]["refresh_token"] == "new-refresh"
        assert (market.path.stat().st_mode & 0o777) == 0o600

    def test_a_grant_with_no_refresh_token_is_not_stored(self, page, vault, schwab):
        schwab.refresh_token_in_grant = False
        _, state, _ = start_reauth(page, "trading")
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state}"}))
        assert "refresh_token" in body and "failed" in body
        assert vault.load(PASS)["trading"]["token"]["token"]["refresh_token"] == "trading-refresh-old"

    def test_a_grant_that_fails_the_live_check_is_not_stored(self, page, vault, schwab):
        schwab.verify_status = 401
        _, state, _ = start_reauth(page, "trading")
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state}"}))
        assert "HTTP 401" in body and "nothing stored" in body
        assert vault.load(PASS)["trading"]["token"]["token"]["refresh_token"] == "trading-refresh-old"

    def test_a_pasted_url_from_another_link_is_refused(self, page, vault, schwab):
        _, state, _ = start_reauth(page, "trading")
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state=someone-elses"}))
        assert "not usable" in body and "state" in body
        assert ("POST", "/v1/oauth/token") not in schwab.calls

    def test_the_state_is_single_use_and_expires(self, page, schwab, mono):
        _, state, _ = start_reauth(page, "trading")
        landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state}"}))
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state}"}))
        assert "used already" in body
        _, state2, _ = start_reauth(page, "trading")
        mono.t += REAUTH_TTL_S + 1
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state2, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state2}"}))
        assert "older than" in body

    def test_a_wrong_passphrase_at_store_time_does_not_spend_the_link(
            self, page, schwab, monkeypatch):
        monkeypatch.setattr("execd.page.time.sleep", lambda s: None)
        _, state, _ = start_reauth(page, "trading")
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": WRONG,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state}"}))
        assert "did not open" in body
        body = landing(page, page.post("/exec/reauth/store", data={
            "state": state, "passphrase": PASS,
            "received_url": f"{CALLBACK}/?code=C0DE&state={state}"}))
        assert "re-authorised" in body

    def test_market_reauth_without_a_market_file_says_so(self, service, vault, clock, mono):
        app = create_page(service, vault=vault, market=None, clock=clock, monotonic=mono)
        c = app.test_client()
        r = c.post("/exec/reauth/link", data={"app": "market", "passphrase": PASS})
        assert r.status_code == 303 and "without+a+market+credential" in r.headers["Location"]


# ── the surface itself ────────────────────────────────────────────────────

class TestSurface:
    def test_the_index_reads_while_locked_and_offers_unlock(self, page):
        body = text(page.get("/exec/"))
        assert "LOCKED" in body and "UNLOCK" in body and "name=passphrase" in body
        assert "FLATTEN" not in body, "nothing to flatten with while locked"

    def test_the_index_armed_offers_stop_flatten_stand_down(self, page):
        page.post("/exec/unlock", data={"passphrase": PASS})
        body = text(page.get("/exec/"))
        assert "ARMED" in body and ">STOP<" in body and "FLATTEN" in body
        assert "stand down" in body and "lock — forget" in body

    def test_the_index_shows_the_journal_tail(self, page):
        page.post("/exec/unlock", data={"passphrase": PASS})
        body = text(page.get("/exec/"))
        assert "Journal" in body and "unlock" in body

    def test_root_redirects_to_the_page(self, page):
        r = page.get("/")
        assert r.status_code == 302 and r.headers["Location"].endswith("/exec/")

    def test_the_url_map_is_exactly_the_design(self, service, vault, market, clock, mono):
        app = create_page(service, vault=vault, market=market, clock=clock, monotonic=mono)
        rules = {r.rule for r in app.url_map.iter_rules() if r.endpoint != "static"}
        assert rules == {
            "/", "/exec/", "/exec/unlock", "/exec/stop", "/exec/resume",
            "/exec/stand-down", "/exec/lock", "/exec/flatten", "/exec/flatten/confirm",
            "/exec/reauth/link", "/exec/reauth/store",
            "/exec/order", "/exec/order/price", "/exec/order/state",
            "/exec/order/preview", "/exec/order/send",
            # st-fn5y: the bracket's UPDATE and the working entry's CANCEL AND RE-PRICE
            "/exec/order/adjust", "/exec/order/cancel",
        }

    def test_every_form_posts_to_an_absolute_exec_path(self, page):
        page.post("/exec/unlock", data={"passphrase": PASS})
        for body in (text(page.get("/exec/")), text(page.post("/exec/flatten")),
                     text(page.get("/exec/order")),
                     text(page.post("/exec/reauth/link",
                                    data={"app": "trading", "passphrase": PASS}))):
            actions = [a.split("'")[0] for a in body.split("action='")[1:]]
            assert actions, "a page with no form"
            assert all(a.startswith("/exec/") for a in actions), actions


class TestCredentialFile:
    def test_save_is_atomic_and_0600(self, tmp_path):
        f = CredentialFile(tmp_path / "m.json")
        f.save(market_payload("r1"))
        assert (f.path.stat().st_mode & 0o777) == 0o600
        assert f.current()["token"]["token"]["refresh_token"] == "r1"
        assert not list(tmp_path.glob(".m.json.*"))

    def test_save_refuses_a_non_credential(self, tmp_path):
        f = CredentialFile(tmp_path / "m.json")
        with pytest.raises(ValueError):
            f.save({"nope": 1})
        assert not f.path.exists()

    def test_current_before_load_is_a_broker_error(self, tmp_path):
        from execd.broker import BrokerError
        with pytest.raises(BrokerError):
            CredentialFile(tmp_path / "m.json").current()


def test_page_refused_is_plain():
    assert issubclass(PageRefused, RuntimeError)
