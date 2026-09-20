"""The re-authorisation flow, shared by the page and the terminal handles.
[st-bd2g]

``execd/reauth.py`` was carved out of ``execd/page.py`` so Steve's
``reauthData`` / ``reauthAccount`` write the same stores the page writes, the
same way. What is asserted here is what the two doors have in common and what
only the terminal door needs: the market file notices a write it did not make,
and a file rewritten by root goes back to the owner the service reads it as.

The page's own behaviour is unchanged and stays asserted in ``test_page.py``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from execd.broker import BrokerError
from execd.reauth import (CredentialFile, ReauthRefused, Source, app_credential,
                          callback_for, login_link, new_state, preserve_owner,
                          store_grant)
from execd.schwab import App, Credential
from execd.vault import Vault

PASS = "correct horse battery"


def wrapped(refresh: str, access: str = "acc", created: int = 1_757_000_000) -> dict:
    return {"creation_timestamp": created,
            "token": {"access_token": access, "refresh_token": refresh,
                      "expires_at": created + 1800, "token_type": "Bearer"}}


def vault_payload(refresh: str = "trading-refresh-old") -> dict:
    return {"version": 2, "trading": {"app": {"key": "TKEY", "secret": "TSECRET"},
                                      "token": wrapped(refresh)}}


def market_payload(refresh: str = "market-refresh-old") -> dict:
    return {"app": {"key": "MKEY", "secret": "MSECRET"}, "token": wrapped(refresh)}


def refresh_of(payload: dict) -> str:
    return payload["token"]["token"]["refresh_token"]


# ── the market credential file ────────────────────────────────────────────


class TestCredentialFile:
    def test_current_picks_up_a_write_from_outside_the_process(self, tmp_path):
        """The terminal handle writes the file; the running service is holding
        its start-up copy. Without this it would go on serving a dead grant —
        the exact failure the handle was run to fix."""
        path = tmp_path / "market.json"
        path.write_text(json.dumps(market_payload("old")))
        f = CredentialFile(path)
        f.load()
        assert refresh_of(f.current()) == "old"

        CredentialFile(path).save(market_payload("written-elsewhere"))
        assert refresh_of(f.current()) == "written-elsewhere"

    def test_an_unchanged_file_is_not_parsed_again(self, tmp_path, monkeypatch):
        path = tmp_path / "market.json"
        path.write_text(json.dumps(market_payload()))
        f = CredentialFile(path)
        f.load()
        reads = []
        real = Path.read_text
        monkeypatch.setattr(Path, "read_text",
                            lambda self, **kw: (reads.append(self), real(self, **kw))[1])
        for _ in range(5):
            f.current()
        assert reads == []

    def test_a_file_caught_mid_replace_leaves_the_working_copy_alone(self, tmp_path):
        path = tmp_path / "market.json"
        path.write_text(json.dumps(market_payload("good")))
        f = CredentialFile(path)
        f.load()
        path.write_text("{ this is not json")
        assert refresh_of(f.current()) == "good"

    def test_garbage_that_later_becomes_a_credential_is_picked_up(self, tmp_path):
        path = tmp_path / "market.json"
        path.write_text(json.dumps(market_payload("good")))
        f = CredentialFile(path)
        f.load()
        path.write_text("{ this is not json")
        assert refresh_of(f.current()) == "good"
        CredentialFile(path).save(market_payload("repaired"))
        assert refresh_of(f.current()) == "repaired"

    def test_saving_through_this_object_needs_no_re_read(self, tmp_path):
        path = tmp_path / "market.json"
        f = CredentialFile(path)
        f.save(market_payload("first"))
        assert refresh_of(f.current()) == "first"
        assert (path.stat().st_mode & 0o777) == 0o600

    def test_nothing_loaded_is_a_refusal_not_an_empty_answer(self, tmp_path):
        with pytest.raises(BrokerError):
            CredentialFile(tmp_path / "absent.json").current()


# ── ownership, when root writes what the service reads ────────────────────


class TestPreserveOwner:
    def test_an_unchanged_owner_needs_no_repair(self, tmp_path):
        path = tmp_path / "vault.json"
        path.write_text("{}")
        restore = preserve_owner(path)
        path.write_text('{"changed": true}')
        assert restore() is None

    def test_a_new_inode_owned_by_the_writer_is_given_back(self, tmp_path, monkeypatch):
        """``os.replace`` of a temp file leaves the new inode owned by whoever
        wrote it. As root that is root, and a root-owned vault is a service
        that cannot read its own credential after a restart."""
        path = tmp_path / "vault.json"
        path.write_text("{}")
        before = path.stat()
        restore = preserve_owner(path)

        chowned: list[tuple] = []
        monkeypatch.setattr(os, "chown", lambda p, uid, gid: chowned.append((str(p), uid, gid)))

        class Stat:
            st_uid, st_gid = before.st_uid + 1, before.st_gid + 1
        monkeypatch.setattr(Path, "stat", lambda self, **kw: Stat())

        assert restore() is None
        assert chowned == [(str(path), before.st_uid, before.st_gid)]

    def test_a_chown_that_fails_names_the_repair_instead_of_going_quiet(
            self, tmp_path, monkeypatch):
        path = tmp_path / "vault.json"
        path.write_text("{}")
        before = path.stat()
        restore = preserve_owner(path)

        def refuse(*_a, **_k):
            raise PermissionError("not permitted")
        monkeypatch.setattr(os, "chown", refuse)

        class Stat:
            st_uid, st_gid = before.st_uid + 1, before.st_gid + 1
        monkeypatch.setattr(Path, "stat", lambda self, **kw: Stat())

        note = restore()
        assert note and "chown" in note and str(path) in note

    def test_a_file_that_does_not_exist_yet_borrows_its_directory(self, tmp_path):
        """A first write has no previous owner to remember, so the directory's
        is the one the service will read it as."""
        path = tmp_path / "not-yet.json"
        restore = preserve_owner(path)
        path.write_text("{}")
        assert restore() is None

    def test_a_write_that_left_no_file_is_reported_not_swallowed(self, tmp_path):
        path = tmp_path / "vault.json"
        path.write_text("{}")
        restore = preserve_owner(path)
        path.unlink()
        assert "could not be read back" in (restore() or "")


# ── which app's key and secret ────────────────────────────────────────────


class TestAppCredential:
    def test_trading_comes_out_of_the_open_vault(self):
        s = app_credential(App.TRADING, vault_payload(), None)
        assert (s.app_key, s.secret) == ("TKEY", "TSECRET")

    def test_a_pre_split_vault_still_answers(self):
        """v1 had exactly one credential and it was the trading one."""
        s = app_credential(App.TRADING, vault_payload()["trading"], None)
        assert s.app_key == "TKEY"

    def test_market_comes_out_of_its_own_file(self):
        s = app_credential(App.MARKET, None, market_payload())
        assert (s.app_key, s.secret) == ("MKEY", "MSECRET")

    def test_a_vault_with_no_usable_trading_credential_is_refused(self):
        with pytest.raises(ReauthRefused, match="no usable trading credential"):
            app_credential(App.TRADING, {"version": 2, "trading": {"app": {}}}, None)

    def test_no_market_credential_is_refused(self):
        with pytest.raises(ReauthRefused, match="nothing to re-authorise"):
            app_credential(App.MARKET, None, None)

    def test_an_unusable_market_credential_says_so(self):
        with pytest.raises(ReauthRefused, match="not usable"):
            app_credential(App.MARKET, None, {"app": {"key": "K"}})

    def test_the_app_s_own_callback_wins_over_the_default(self):
        payload = market_payload()
        payload["callback_url"] = "https://127.0.0.1:9999"
        s = app_credential(App.MARKET, None, payload)
        assert callback_for(s, "https://default") == "https://127.0.0.1:9999"

    def test_the_default_callback_is_used_when_the_credential_names_none(self):
        s = app_credential(App.MARKET, None, market_payload())
        assert callback_for(s, "https://default") == "https://default"


class TestLoginLink:
    def test_the_link_carries_the_key_the_callback_and_the_state(self):
        link = login_link(Source("KEY", "SECRET", None), "https://cb", "st4te")
        assert "client_id=KEY" in link and "st4te" in link and "response_type=code" in link
        assert "SECRET" not in link

    def test_two_states_are_not_the_same_state(self):
        assert new_state() != new_state()


# ── storing ───────────────────────────────────────────────────────────────


class TestStoreGrant:
    def test_a_trading_grant_is_re_encrypted_under_the_same_passphrase(self, tmp_path):
        v = Vault(tmp_path / "vault.json")
        v.store(vault_payload("old"), PASS)
        stored = store_grant(App.TRADING, wrapped("new-refresh"), vault=v,
                             vault_payload=v.load(PASS), passphrase=PASS)
        assert stored.trading is not None
        assert refresh_of(stored.trading) == "new-refresh"
        assert refresh_of(v.load(PASS)["trading"]) == "new-refresh"
        assert stored.wall == Credential.from_payload(stored.trading).refresh_wall

    def test_the_rest_of_the_envelope_survives(self, tmp_path):
        v = Vault(tmp_path / "vault.json")
        payload = vault_payload()
        payload["kept"] = "a key some later stage added"
        v.store(payload, PASS)
        store_grant(App.TRADING, wrapped("new-refresh"), vault=v,
                    vault_payload=v.load(PASS), passphrase=PASS)
        assert v.load(PASS)["kept"] == "a key some later stage added"

    def test_the_app_key_and_secret_are_carried_forward_untouched(self, tmp_path):
        v = Vault(tmp_path / "vault.json")
        v.store(vault_payload(), PASS)
        store_grant(App.TRADING, wrapped("new-refresh"), vault=v,
                    vault_payload=v.load(PASS), passphrase=PASS)
        assert v.load(PASS)["trading"]["app"] == {"key": "TKEY", "secret": "TSECRET"}

    def test_a_market_grant_goes_to_its_file_and_reports_no_memory_payload(self, tmp_path):
        f = CredentialFile(tmp_path / "market.json")
        f.save(market_payload("old"))
        stored = store_grant(App.MARKET, wrapped("new-refresh"),
                             market_payload=f.current(), market_save=f.save)
        assert stored.trading is None
        assert refresh_of(f.current()) == "new-refresh"
        assert refresh_of(json.loads((tmp_path / "market.json").read_text())) == "new-refresh"

    def test_a_trading_store_without_the_passphrase_is_refused(self, tmp_path):
        with pytest.raises(ReauthRefused, match="passphrase"):
            store_grant(App.TRADING, wrapped("new"), vault=Vault(tmp_path / "v.json"),
                        vault_payload=vault_payload())

    def test_a_market_store_with_nothing_to_replace_is_refused(self):
        with pytest.raises(ReauthRefused, match="no market credential"):
            store_grant(App.MARKET, wrapped("new"))
