"""The two-app credential split, from the outside. [st-p9mx]

Steve has two Schwab registrations. App 1 carries market data and cannot trade
— developer.schwab.com refuses to add the Accounts and Trading product to it,
so every ``/trader/v1`` call on it answers 401 — and app 2 carries trading.
That difference is what lets the two live at different tiers: the trading
credential goes in the encrypted vault behind Steve's passphrase, and the
market credential is a plain 0600 file the service can read at start-up,
because the 07:00 premarket jobs run before he is awake to type anything
(st-p8k8's open design point).

These tests cover the two scripts that write those files and the reader in
``execd/__main__.py``. The routing itself — which credential reaches which
endpoint family — is pinned behaviourally in ``tests/execd/test_schwab.py``.

Nothing here opens a socket or touches a real credential.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import scripts.execd_market_credential as emc
import scripts.execd_vault_init as evi
from execd.__main__ import load_market_credential
from execd.schwab import VAULT_VERSION, Credential, trading_payload
from execd.vault import Vault

PASSPHRASE = "a-long-enough-passphrase"


def wrapped_token(*, access: str = "ACCESS", refresh: str = "REFRESH") -> dict:
    now = int(time.time())
    return {"creation_timestamp": now - 3600,
            "token": {"access_token": access, "refresh_token": refresh,
                      "expires_at": now + 1500, "token_type": "Bearer"}}


@pytest.fixture
def market_rig(tmp_path, monkeypatch):
    """A token file and a config, with no real vault or .env in reach."""
    token = tmp_path / "market_token.json"
    token.write_text(json.dumps(wrapped_token(access="M-ACCESS", refresh="M-REFRESH")))
    monkeypatch.setattr(emc, "load_schwab_market", lambda: {
        "SCHWAB_API_KEY": "MARKET-KEY", "SCHWAB_APP_SECRET": "MARKET-SECRET",
        "SCHWAB_TOKEN_PATH": str(token)})
    return token


class TestMarketCredentialFile:
    def test_it_writes_the_vault_payload_shape(self, market_rig, tmp_path, capsys):
        out = tmp_path / "state" / "market.json"
        assert emc.write(out) == 0
        payload = json.loads(out.read_text())
        assert payload["app"] == {"key": "MARKET-KEY", "secret": "MARKET-SECRET"}
        assert Credential.from_payload(payload).refresh_token == "M-REFRESH"

    def test_the_file_is_0600(self, market_rig, tmp_path):
        """It holds a live credential in the clear. The mode is the only thing
        standing between it and every other account on the box."""
        out = tmp_path / "market.json"
        emc.write(out)
        assert out.stat().st_mode & 0o777 == 0o600

    def test_it_prints_no_secret(self, market_rig, tmp_path, capsys):
        out = tmp_path / "market.json"
        emc.write(out)
        printed = capsys.readouterr()
        for secret in ("MARKET-KEY", "MARKET-SECRET", "M-ACCESS", "M-REFRESH"):
            assert secret not in printed.out + printed.err

    def test_a_missing_token_is_refused_and_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(emc, "load_schwab_market", lambda: {
            "SCHWAB_API_KEY": "K", "SCHWAB_APP_SECRET": "S",
            "SCHWAB_TOKEN_PATH": str(tmp_path / "absent.json")})
        out = tmp_path / "market.json"
        assert emc.write(out) == 1
        assert not out.exists()

    def test_a_token_with_no_refresh_token_is_refused(self, tmp_path, monkeypatch):
        """The st-r1b5 failure: a 181-byte grant with no refresh token answered
        HTTP 200 for thirty minutes before going silent."""
        token = tmp_path / "t.json"
        token.write_text(json.dumps({"creation_timestamp": int(time.time()),
                                     "token": {"access_token": "A"}}))
        monkeypatch.setattr(emc, "load_schwab_market", lambda: {
            "SCHWAB_API_KEY": "K", "SCHWAB_APP_SECRET": "S",
            "SCHWAB_TOKEN_PATH": str(token)})
        out = tmp_path / "market.json"
        assert emc.write(out) == 1
        assert not out.exists()

    def test_check_reads_back_what_write_wrote(self, market_rig, tmp_path):
        out = tmp_path / "market.json"
        emc.write(out)
        assert emc.check(out) == 0

    def test_check_on_a_missing_file_is_an_error_not_a_crash(self, tmp_path):
        assert emc.check(tmp_path / "nothing.json") == 1

    def test_a_half_written_file_is_never_left_behind(self, market_rig, tmp_path, monkeypatch):
        """Atomic write: the service must not start against a truncated
        credential, and this box has been OOM-killed mid-run before."""
        def boom(*_a, **_k):
            raise OSError("disk full")
        monkeypatch.setattr(emc.os, "replace", boom)
        out = tmp_path / "market.json"
        with pytest.raises(OSError):
            emc.write(out)
        assert not out.exists()
        assert not list(tmp_path.glob(".market.json.*.tmp"))


class TestTheServiceReadsIt:
    def test_load_market_credential_shape_checks_at_start_not_on_first_quote(
            self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"app": {"key": "k"}}))   # no secret
        with pytest.raises(ValueError):
            load_market_credential(bad)

    def test_load_market_credential_returns_the_payload(self, market_rig, tmp_path):
        out = tmp_path / "market.json"
        emc.write(out)
        assert load_market_credential(out)["app"]["key"] == "MARKET-KEY"


class TestVaultPayloadVersions:
    def test_a_v1_vault_still_opens_as_the_trading_credential(self):
        """A vault written before the split had exactly one credential in it,
        and it was the trading one. It must keep working."""
        v1 = {"app": {"key": "K", "secret": "S"}, "token": wrapped_token()}
        assert trading_payload(v1) is v1
        assert Credential.from_payload(trading_payload(v1)).refresh_token == "REFRESH"

    def test_a_v2_vault_yields_the_trading_half(self):
        trading = {"app": {"key": "T", "secret": "TS"},
                   "token": wrapped_token(refresh="T-REFRESH")}
        v2 = {"version": VAULT_VERSION, "trading": trading}
        assert trading_payload(v2) == trading
        assert Credential.from_payload(trading_payload(v2)).refresh_token == "T-REFRESH"

    def test_the_market_credential_is_not_in_the_vault(self, tmp_path):
        """By design, not by omission: a credential that must load before the
        passphrase is typed cannot live behind the passphrase."""
        trading = {"app": {"key": "T", "secret": "TS"}, "token": wrapped_token()}
        vault = Vault(tmp_path / "v.json")
        vault.store({"version": VAULT_VERSION, "trading": trading}, PASSPHRASE)
        assert set(vault.load(PASSPHRASE)) == {"version", "trading"}

    def test_vault_init_writes_version_2(self, tmp_path, monkeypatch):
        token = tmp_path / "trading_token.json"
        token.write_text(json.dumps(wrapped_token(refresh="T-REFRESH")))
        monkeypatch.setattr(evi, "load_schwab_trading", lambda: {
            "SCHWAB_TRADING_API_KEY": "T-KEY", "SCHWAB_TRADING_APP_SECRET": "T-SECRET",
            "SCHWAB_TRADING_TOKEN_PATH": str(token)})
        monkeypatch.setattr(evi, "_ask", lambda _prompt: PASSPHRASE)
        out = tmp_path / "vault.json"
        assert evi.init(out) == 0
        payload = Vault(out).load(PASSPHRASE)
        assert payload["version"] == VAULT_VERSION
        assert payload["trading"]["app"]["key"] == "T-KEY"
        assert Credential.from_payload(trading_payload(payload)).refresh_token == "T-REFRESH"

    def test_vault_init_takes_the_trading_token_not_the_market_one(
            self, tmp_path, monkeypatch, capsys):
        """It must read SCHWAB_TRADING_TOKEN_PATH. Reading the market token
        here would put a credential that cannot trade into the vault the
        service sends orders with — and it would fail live, not at start-up.

        The missing token is named under ``tmp_path``. Until st-ilp9's session this
        test left the path out and relied on the default not existing on the
        box; Steve authorised app 2 on 09-05, the real token appeared, and the
        test went red asking for a passphrase. A test whose result depends on
        whether a live credential happens to exist is not testing the code."""
        absent = tmp_path / "gone" / "schwab_trading_token.json"
        monkeypatch.setattr(evi, "load_schwab_trading", lambda: {
            "SCHWAB_TRADING_API_KEY": "T-KEY", "SCHWAB_TRADING_APP_SECRET": "T-SECRET",
            "SCHWAB_TRADING_TOKEN_PATH": str(absent)})
        assert evi.init(tmp_path / "vault.json") == 1
        assert str(absent) in capsys.readouterr().err

    def test_the_token_path_falls_back_to_the_trading_token_not_the_market_one(self):
        """The half of the above that the filesystem used to prove."""
        assert evi._token_path({}).name == "schwab_trading_token.json"
