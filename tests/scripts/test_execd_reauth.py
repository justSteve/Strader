"""``reauthData`` and ``reauthAccount``, end to end. [st-bd2g]

Steve types one word, opens a link, pastes an address, and the grant the
execution service actually reads is the one that changes. The whole flow runs
here against an ``httpx.MockTransport`` standing in for Schwab, a real vault in
a temp directory and a fake loopback for the service's own API — no network, no
credential in the room, and nothing that touches ``/var/lib/execd``.

What is asserted beyond behaviour: that a refused or failed run stores nothing,
that the journal carries the new wall (the service reads its own journal for
that while it is LOCKED, and the 06:30 heartbeat reads the service), and that
no token value reaches the screen.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import httpx
import pytest

from execd.journal import Journal
from execd.schwab import App
from execd.vault import Vault
from scripts import execd_reauth

PASS = "correct horse battery"
CALLBACK = "https://127.0.0.1:8182"
NEW_REFRESH = "new-refresh-value-nobody-should-see"


def wrapped(refresh: str, created: int = 1_757_000_000) -> dict:
    return {"creation_timestamp": created,
            "token": {"access_token": "acc", "refresh_token": refresh,
                      "expires_at": created + 1800, "token_type": "Bearer"}}


def vault_payload(refresh: str = "trading-refresh-old") -> dict:
    return {"version": 2, "trading": {"app": {"key": "TKEY", "secret": "TSECRET"},
                                      "token": wrapped(refresh)}}


def market_payload(refresh: str = "market-refresh-old") -> dict:
    return {"app": {"key": "MKEY", "secret": "MSECRET"}, "token": wrapped(refresh)}


def refresh_of(payload: dict) -> str:
    return payload["token"]["token"]["refresh_token"]


class Schwab:
    """The two OAuth calls and the two verify calls, and nothing else."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.refresh_token_in_grant = True
        self.verify_status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        if request.url.path == "/v1/oauth/token":
            body = {"access_token": "new-access", "expires_in": 1800, "token_type": "Bearer"}
            if self.refresh_token_in_grant:
                body["refresh_token"] = NEW_REFRESH
            return httpx.Response(200, json=body)
        if request.url.path == "/trader/v1/accounts/accountNumbers":
            return httpx.Response(self.verify_status, json=[{"accountNumber": "1"}])
        if request.url.path == "/marketdata/v1/quotes":
            return httpx.Response(self.verify_status, json={"$SPX": {"quote": {}}})
        return httpx.Response(404, json={})


class Loopback:
    """The service's own API as this flow reads it: a status, and one quote
    that says whether a new market grant reached the running process."""

    def __init__(self, state: str | None = "LOCKED", quote_ok: bool = True) -> None:
        self.state, self.quote_ok = state, quote_ok
        self.asked: list[tuple[str, dict]] = []

    def get(self, url: str, params=None):
        self.asked.append((url, dict(params or {})))
        if self.state is None:
            raise httpx.ConnectError("nothing is listening")
        if url.endswith("/status"):
            return httpx.Response(200, json={"arming": {"state": self.state}, "mode": "paper"})
        if url.endswith("/quote"):
            return httpx.Response(200 if self.quote_ok else 502, json={"symbol": "$SPX"})
        return httpx.Response(404, json={})


@pytest.fixture
def state_dir(tmp_path) -> Path:
    (tmp_path / "journal").mkdir()
    Vault(tmp_path / "vault.json").store(vault_payload(), PASS)
    (tmp_path / "market.json").write_text(json.dumps(market_payload()))
    return tmp_path


@pytest.fixture
def schwab() -> Schwab:
    return Schwab()


def run(target: App, state_dir: Path, schwab: Schwab, *,
        passphrase: str = PASS,
        pasted: str = "https://127.0.0.1:8182/?code=THE-CODE%40&state={state}",
        loopback: Loopback | None = None) -> tuple[int, str]:
    """One console run. ``pasted`` is formatted with the state carried by the
    link the flow just printed — which is exactly how a real paste carries it
    back, and means the link on the screen is what is under test."""
    out = io.StringIO()

    def ask_line(prompt: str) -> str:
        shown = re.search(r"[?&]state=([A-Za-z0-9_-]+)", out.getvalue())
        return pasted.format(state=shown.group(1) if shown else "")

    return execd_reauth.reauthorise(
        target,
        vault_path=state_dir / "vault.json",
        market_path=state_dir / "market.json",
        state_dir=state_dir,
        callback_url=CALLBACK,
        http_client=httpx.Client(base_url="https://api.schwabapi.com",
                                 transport=httpx.MockTransport(schwab)),
        api_client=loopback if loopback is not None else Loopback(),
        ask_passphrase=lambda _p: passphrase,
        ask_line=ask_line,
        out=out), out.getvalue()


def journal_lines(state_dir: Path) -> list[dict]:
    j = Journal(state_dir / "journal")
    return [e for day in j.days() for e in j.read(day)]


# ── the market app: reauthData ────────────────────────────────────────────


class TestMarketApp:
    def test_the_grant_lands_in_the_file_the_service_reads(self, state_dir, schwab):
        rc, out = run(App.MARKET, state_dir, schwab)
        assert rc == execd_reauth.OK, out
        on_disk = json.loads((state_dir / "market.json").read_text())
        assert refresh_of(on_disk) == NEW_REFRESH
        assert on_disk["app"] == {"key": "MKEY", "secret": "MSECRET"}

    def test_it_is_proved_against_its_own_family_before_it_is_stored(self, state_dir, schwab):
        run(App.MARKET, state_dir, schwab)
        assert ("GET", "/marketdata/v1/quotes") in schwab.calls
        assert ("GET", "/trader/v1/accounts/accountNumbers") not in schwab.calls

    def test_the_file_keeps_owner_only_mode(self, state_dir, schwab):
        run(App.MARKET, state_dir, schwab)
        assert ((state_dir / "market.json").stat().st_mode & 0o777) == 0o600

    def test_the_wall_reaches_the_journal(self, state_dir, schwab):
        run(App.MARKET, state_dir, schwab)
        lines = [e for e in journal_lines(state_dir) if e["event"] == "reauth"]
        assert len(lines) == 1
        assert lines[0]["app"] == "market" and lines[0]["refresh_wall"]
        assert lines[0]["by"] == "terminal"

    def test_the_journal_line_says_whether_the_service_is_serving_it(self, state_dir, schwab):
        """Measured with a live quote, not assumed: on a build that re-reads
        the file the running process has it, on one that does not it has not."""
        run(App.MARKET, state_dir, schwab, loopback=Loopback(quote_ok=True))
        assert journal_lines(state_dir)[-1]["in_memory"] is True
        run(App.MARKET, state_dir, schwab, loopback=Loopback(quote_ok=False))
        assert journal_lines(state_dir)[-1]["in_memory"] is False

    def test_a_journal_file_this_run_created_is_owner_only(self, state_dir, schwab):
        """Written as root at the default umask; the service's own journal
        files are owner-only, and it appends to this one every day it runs."""
        run(App.MARKET, state_dir, schwab)
        created = list((state_dir / "journal").glob("*.jsonl"))
        assert created and all((p.stat().st_mode & 0o777) == 0o600 for p in created)

    def test_a_service_that_cannot_read_a_quote_is_told_to_restart(self, state_dir, schwab):
        """The running process holds its start-up copy on a build without the
        re-read. Measured with one quote, not assumed from a version."""
        rc, out = run(App.MARKET, state_dir, schwab, loopback=Loopback(quote_ok=False))
        assert rc == execd_reauth.OK
        assert "systemctl restart strader-execd" in out

    def test_a_service_that_picked_it_up_is_not_told_to_restart(self, state_dir, schwab):
        rc, out = run(App.MARKET, state_dir, schwab, loopback=Loopback(quote_ok=True))
        assert rc == execd_reauth.OK
        assert "restart" not in out

    def test_the_proof_is_the_index_symbol_the_service_itself_uses(self, state_dir, schwab):
        """A symbol the service does not know would fail for a reason that has
        nothing to do with the grant, and send him to restart for nothing."""
        from execd.service import ServiceConfig
        loopback = Loopback()
        run(App.MARKET, state_dir, schwab, loopback=loopback)
        quotes = [p for url, p in loopback.asked if url.endswith("/quote")]
        assert quotes == [{"symbol": ServiceConfig.index_symbol}]

    def test_it_works_with_the_service_stopped(self, state_dir, schwab):
        rc, out = run(App.MARKET, state_dir, schwab, loopback=Loopback(state=None))
        assert rc == execd_reauth.OK, out
        assert "not answering" in out
        assert refresh_of(json.loads((state_dir / "market.json").read_text())) == NEW_REFRESH

    def test_a_missing_market_credential_is_refused_before_anything_is_sent(
            self, state_dir, schwab):
        (state_dir / "market.json").unlink()
        rc, out = run(App.MARKET, state_dir, schwab)
        assert rc == execd_reauth.REFUSED
        assert schwab.calls == []


# ── the trading app: reauthAccount ────────────────────────────────────────


class TestTradingApp:
    def test_the_vault_is_re_encrypted_under_the_same_passphrase(self, state_dir, schwab):
        rc, out = run(App.TRADING, state_dir, schwab)
        assert rc == execd_reauth.OK, out
        assert refresh_of(Vault(state_dir / "vault.json").load(PASS)["trading"]) == NEW_REFRESH

    def test_it_is_proved_against_its_own_family(self, state_dir, schwab):
        run(App.TRADING, state_dir, schwab)
        assert ("GET", "/trader/v1/accounts/accountNumbers") in schwab.calls
        assert ("GET", "/marketdata/v1/quotes") not in schwab.calls

    def test_a_locked_service_needs_nothing_further(self, state_dir, schwab):
        rc, out = run(App.TRADING, state_dir, schwab, loopback=Loopback("LOCKED"))
        assert rc == execd_reauth.OK
        assert "UNLOCK" not in out

    def test_an_armed_service_is_told_it_still_holds_the_old_one(self, state_dir, schwab):
        """It does not keep the passphrase, so it cannot re-read the vault on
        its own. Saying so is the whole difference between a stored grant and
        a working one."""
        rc, out = run(App.TRADING, state_dir, schwab, loopback=Loopback("ARMED"))
        assert rc == execd_reauth.OK
        assert "LOCK and then UNLOCK" in out

    def test_a_wrong_passphrase_sends_nothing_and_stores_nothing(self, state_dir, schwab):
        before = (state_dir / "vault.json").read_bytes()
        rc, out = run(App.TRADING, state_dir, schwab, passphrase="wrong horse battery")
        assert rc == execd_reauth.REFUSED
        assert schwab.calls == []
        assert (state_dir / "vault.json").read_bytes() == before

    def test_a_missing_vault_says_so(self, state_dir, schwab):
        (state_dir / "vault.json").unlink()
        rc, out = run(App.TRADING, state_dir, schwab)
        assert rc == execd_reauth.REFUSED and "no vault" in out

    def test_the_wall_reaches_the_journal_where_the_service_reads_it(self, state_dir, schwab):
        """``ExecService._last_known_trading_wall`` reads exactly this line to
        answer ``/status`` while LOCKED, and the token-age heartbeat reads
        that. A re-auth it never sees is a week of false alerts."""
        run(App.TRADING, state_dir, schwab)
        line = [e for e in journal_lines(state_dir) if e["event"] == "reauth"][0]
        assert line["app"] == "trading" and line["refresh_wall"]


# ── what a failure must not do ────────────────────────────────────────────


class TestFailuresStoreNothing:
    def test_a_grant_with_no_refresh_token_is_refused_and_nothing_is_written(
            self, state_dir, schwab):
        """The 2026-08-12 shape: 200 on the next call, dead thirty minutes
        later. Nothing is stored, so the old grant is still there to retry."""
        schwab.refresh_token_in_grant = False
        before = (state_dir / "market.json").read_text()
        rc, out = run(App.MARKET, state_dir, schwab)
        assert rc == execd_reauth.FAILED
        assert "refresh_token" in out
        assert (state_dir / "market.json").read_text() == before

    def test_a_live_check_that_fails_stores_nothing(self, state_dir, schwab):
        schwab.verify_status = 401
        before = (state_dir / "market.json").read_text()
        rc, out = run(App.MARKET, state_dir, schwab)
        assert rc == execd_reauth.FAILED
        assert (state_dir / "market.json").read_text() == before

    def test_an_address_from_somewhere_else_is_refused(self, state_dir, schwab):
        before = (state_dir / "market.json").read_text()
        rc, out = run(App.MARKET, state_dir, schwab,
                      pasted="https://127.0.0.1:8182/?code=X%40&state=not-the-state")
        assert rc == execd_reauth.FAILED
        assert "state" in out
        assert (state_dir / "market.json").read_text() == before

    def test_an_address_with_no_code_is_refused(self, state_dir, schwab):
        rc, out = run(App.MARKET, state_dir, schwab, pasted="https://127.0.0.1:8182/")
        assert rc == execd_reauth.FAILED and "code=" in out

    def test_nothing_pasted_stores_nothing(self, state_dir, schwab):
        out = io.StringIO()

        def nothing(_p):
            raise EOFError
        rc = execd_reauth.reauthorise(
            App.MARKET, vault_path=state_dir / "vault.json",
            market_path=state_dir / "market.json", state_dir=state_dir,
            http_client=httpx.Client(base_url="https://api.schwabapi.com",
                                     transport=httpx.MockTransport(schwab)),
            api_client=Loopback(), ask_line=nothing, out=out)
        assert rc == execd_reauth.REFUSED
        assert schwab.calls == []


# ── what never reaches the screen ─────────────────────────────────────────


class TestNoValueIsPrinted:
    @pytest.mark.parametrize("target", [App.MARKET, App.TRADING])
    def test_no_token_value_and_no_secret_reaches_the_output(self, state_dir, schwab, target):
        rc, out = run(target, state_dir, schwab)
        assert rc == execd_reauth.OK, out
        for value in (NEW_REFRESH, "new-access", "TSECRET", "MSECRET", PASS,
                      "trading-refresh-old", "market-refresh-old"):
            assert value not in out, f"{value!r} reached the screen"

    def test_no_token_value_reaches_the_journal(self, state_dir, schwab):
        run(App.TRADING, state_dir, schwab)
        blob = "".join(p.read_text() for p in (state_dir / "journal").glob("*.jsonl"))
        for value in (NEW_REFRESH, "new-access", "TSECRET", PASS):
            assert value not in blob

    def test_the_link_carries_the_key_but_never_the_secret(self, state_dir, schwab):
        _, out = run(App.MARKET, state_dir, schwab)
        assert "client_id=MKEY" in out and "MSECRET" not in out


# ── the handle that reaches it ────────────────────────────────────────────


class TestTheHandleDispatches:
    def test_the_refresh_script_hands_over_once_the_service_is_installed(self, monkeypatch,
                                                                        tmp_path):
        """``reauthData`` / ``reauthAccount`` / ``reauthTrade`` all end here.
        Before st-bd2g this printed the page's address and returned 3."""
        import scripts.refresh_schwab_token as rst
        stamp = tmp_path / "INSTALLED"
        stamp.write_text("sha\n")
        monkeypatch.setattr(rst, "EXECD_INSTALLED", stamp)
        monkeypatch.setattr(rst, "GATE_KEY", stamp)
        called: list = []
        monkeypatch.setattr(execd_reauth, "reauthorise",
                            lambda target, **kw: called.append(target) or 0)
        assert rst.main([]) == 0
        assert rst.main(["--trading"]) == 0
        assert called == [App.MARKET, App.TRADING]

    def test_a_closed_gate_still_refuses_before_any_flow_runs(self, monkeypatch, tmp_path):
        import scripts.refresh_schwab_token as rst
        stamp = tmp_path / "INSTALLED"
        stamp.write_text("sha\n")
        monkeypatch.setattr(rst, "EXECD_INSTALLED", stamp)
        monkeypatch.setattr(rst, "GATE_KEY", tmp_path / "absent")
        monkeypatch.setattr(execd_reauth, "reauthorise",
                            lambda *a, **k: pytest.fail("the gate was skipped"))
        assert rst.main([]) == 1

    def test_the_old_file_flow_is_still_reachable_on_purpose(self, monkeypatch, tmp_path):
        import scripts.refresh_schwab_token as rst
        stamp = tmp_path / "INSTALLED"
        stamp.write_text("sha\n")
        monkeypatch.setattr(rst, "EXECD_INSTALLED", stamp)
        monkeypatch.setenv("SCHWAB_REAUTH_FORCE_FILE", "1")
        assert rst._the_service_holds_the_grants() is False

    def test_without_the_service_the_script_is_unchanged(self, monkeypatch, tmp_path):
        import scripts.refresh_schwab_token as rst
        monkeypatch.setattr(rst, "EXECD_INSTALLED", tmp_path / "absent")
        assert rst._the_service_holds_the_grants() is False
