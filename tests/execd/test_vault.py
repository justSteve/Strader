"""The vault — round trip, refusal, and the things it must never do. [st-w2nw]

The credential this will hold is the one that can move Steve's money, so the
tests are not only "does it come back out". They are: a wrong passphrase is
refused and says nothing useful; an edited file fails the same way as a wrong
passphrase; the work factors cannot be quietly weakened; nothing readable
without the passphrase appears anywhere in the file or in what the page can
show; and a crash mid-write leaves the old vault intact.
"""

from __future__ import annotations

import json
import os

import pytest

from execd.vault import (
    BadPassphrase, MIN_PASSPHRASE_LEN, Vault, VaultCorrupt, VaultError,
    VaultMissing, VERSION,
)

PASS = "correct horse battery staple"
OTHER = "incorrect horse battery staple"

#: The shape the Schwab token file has today (strader/schwab_token.py).
TOKEN = {
    "creation_timestamp": 1788100000,
    "token": {
        "access_token": "ACCESS-not-a-real-token",
        "refresh_token": "REFRESH-not-a-real-token",
        "expires_in": 1800,
        "expires_at": 1788101800,
        "token_type": "Bearer",
        "scope": "api",
    },
}


@pytest.fixture
def vault(tmp_path) -> Vault:
    # Deliberately weak work factors: the production values cost ~0.1s each and
    # this file opens a vault dozens of times. The parameters are read from the
    # file, so this exercises the same code path.
    return Vault(tmp_path / "token.enc", n=2 ** 10, r=8, p=1)


class TestRoundTrip:
    def test_what_goes_in_comes_out(self, vault):
        vault.store(TOKEN, PASS)
        assert vault.load(PASS) == TOKEN

    def test_the_vault_does_not_exist_until_it_is_written(self, vault):
        assert vault.exists is False
        vault.store(TOKEN, PASS)
        assert vault.exists is True

    def test_loading_a_vault_that_was_never_made(self, vault):
        with pytest.raises(VaultMissing):
            vault.load(PASS)

    def test_a_second_store_replaces_the_first(self, vault):
        vault.store(TOKEN, PASS)
        vault.store({"token": {"refresh_token": "SECOND"}}, PASS)
        assert vault.load(PASS)["token"]["refresh_token"] == "SECOND"

    def test_a_rewrite_keeps_the_original_creation_time(self, vault):
        first = vault.store(TOKEN, PASS)
        second = vault.store(TOKEN, PASS)
        assert second.created == first.created
        assert second.updated >= first.updated

    def test_each_write_uses_a_fresh_salt_and_nonce(self, vault):
        vault.store(TOKEN, PASS)
        one = json.loads(vault.path.read_text())
        vault.store(TOKEN, PASS)
        two = json.loads(vault.path.read_text())
        assert one["kdf"]["salt"] != two["kdf"]["salt"]
        assert one["nonce"] != two["nonce"]
        assert one["ciphertext"] != two["ciphertext"]

    def test_a_payload_that_is_not_json_able_is_refused(self, vault):
        with pytest.raises(VaultError, match="JSON-able"):
            vault.store({"when": object()}, PASS)

    def test_the_payload_must_be_a_mapping(self, vault):
        with pytest.raises(VaultError, match="mapping"):
            vault.store(["not", "a", "mapping"], PASS)


class TestTheWrongPassphrase:
    def test_it_is_refused(self, vault):
        vault.store(TOKEN, PASS)
        with pytest.raises(BadPassphrase):
            vault.load(OTHER)

    def test_the_refusal_says_nothing_useful_about_the_passphrase(self, vault):
        vault.store(TOKEN, PASS)
        with pytest.raises(BadPassphrase) as exc:
            vault.load(OTHER)
        message = str(exc.value)
        assert PASS not in message and OTHER not in message
        assert "character" not in message and "length" not in message

    def test_verify_answers_without_handing_back_the_credential(self, vault):
        vault.store(TOKEN, PASS)
        assert vault.verify(PASS) is True
        assert vault.verify(OTHER) is False

    def test_a_wrong_passphrase_does_not_damage_the_vault(self, vault):
        vault.store(TOKEN, PASS)
        for _ in range(3):
            with pytest.raises(BadPassphrase):
                vault.load(OTHER)
        assert vault.load(PASS) == TOKEN


class TestTamperingWithTheFile:
    def test_a_flipped_ciphertext_byte_fails(self, vault):
        vault.store(TOKEN, PASS)
        env = json.loads(vault.path.read_text())
        ct = list(env["ciphertext"])
        ct[5] = "A" if ct[5] != "A" else "B"
        env["ciphertext"] = "".join(ct)
        vault.path.write_text(json.dumps(env))
        with pytest.raises((BadPassphrase, VaultCorrupt)):
            vault.load(PASS)

    def test_the_work_factors_cannot_be_quietly_weakened(self, vault):
        """Without the header in the authenticated data, someone could rewrite
        n down to 1 and the vault would still open for whoever held the
        passphrase — having silently become cheap to attack."""
        vault.store(TOKEN, PASS)
        env = json.loads(vault.path.read_text())
        env["kdf"]["n"] = 2
        vault.path.write_text(json.dumps(env))
        with pytest.raises(BadPassphrase):
            vault.load(PASS)

    def test_the_version_cannot_be_rewritten(self, vault):
        vault.store(TOKEN, PASS)
        env = json.loads(vault.path.read_text())
        env["version"] = 99
        vault.path.write_text(json.dumps(env))
        with pytest.raises(VaultCorrupt, match="version"):
            vault.load(PASS)

    def test_a_swapped_nonce_fails(self, vault):
        vault.store(TOKEN, PASS)
        env = json.loads(vault.path.read_text())
        env["nonce"] = "AAAAAAAAAAAAAAAA"
        vault.path.write_text(json.dumps(env))
        with pytest.raises(BadPassphrase):
            vault.load(PASS)

    @pytest.mark.parametrize("mangle,match", [
        (lambda e: e.pop("ciphertext"), "ciphertext"),
        (lambda e: e.pop("nonce"), "nonce"),
        (lambda e: e.pop("kdf"), "kdf"),
        (lambda e: e.update(cipher="ROT13"), "cipher"),
        (lambda e: e.update(kdf={"name": "pbkdf2"}), "scrypt"),
        (lambda e: e.update(nonce=["not", "text"]), "nonce"),
        (lambda e: e.update(ciphertext="not base64!!"), "ciphertext"),
    ])
    def test_a_malformed_envelope_is_corrupt_not_a_crash(self, vault, mangle, match):
        vault.store(TOKEN, PASS)
        env = json.loads(vault.path.read_text())
        mangle(env)
        vault.path.write_text(json.dumps(env))
        with pytest.raises(VaultCorrupt, match=match):
            vault.load(PASS)

    def test_a_file_that_is_not_json_at_all(self, vault):
        vault.path.parent.mkdir(parents=True, exist_ok=True)
        vault.path.write_text("this is not a vault")
        with pytest.raises(VaultCorrupt, match="readable JSON"):
            vault.load(PASS)

    def test_a_json_array_is_not_a_vault(self, vault):
        vault.path.parent.mkdir(parents=True, exist_ok=True)
        vault.path.write_text("[1, 2, 3]")
        with pytest.raises(VaultCorrupt, match="object"):
            vault.load(PASS)


class TestNothingLeaksToDisk:
    def test_the_credential_is_not_in_the_file(self, vault):
        vault.store(TOKEN, PASS)
        raw = vault.path.read_text()
        for secret in ("ACCESS-not-a-real-token", "REFRESH-not-a-real-token",
                       "Bearer", "creation_timestamp"):
            assert secret not in raw

    def test_the_passphrase_is_not_in_the_file(self, vault):
        vault.store(TOKEN, PASS)
        assert PASS not in vault.path.read_text()

    def test_the_file_is_readable_only_by_its_owner(self, vault):
        vault.store(TOKEN, PASS)
        assert oct(os.stat(vault.path).st_mode & 0o777) == "0o600"

    def test_no_temporary_file_is_left_behind(self, vault):
        vault.store(TOKEN, PASS)
        leftovers = [p.name for p in vault.path.parent.iterdir()
                     if p.name != vault.path.name]
        assert leftovers == []

    def test_a_failed_write_leaves_the_previous_vault_intact(self, vault, monkeypatch):
        vault.store(TOKEN, PASS)
        original = vault.path.read_bytes()

        def boom(*_a, **_kw):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            vault.store({"token": {"refresh_token": "NEWER"}}, PASS)
        assert vault.path.read_bytes() == original
        assert vault.load(PASS) == TOKEN
        assert [p.name for p in vault.path.parent.iterdir()] == [vault.path.name]


class TestWhatThePageMaySee:
    def test_info_on_a_vault_that_does_not_exist(self, vault):
        info = vault.info()
        assert info.exists is False and info.version is None

    def test_info_carries_metadata_and_no_payload(self, vault):
        vault.store(TOKEN, PASS)
        d = vault.info().to_dict()
        assert d["exists"] is True and d["version"] == VERSION
        assert d["cipher"] == "AES-256-GCM" and d["kdf"].startswith("scrypt n=")
        blob = json.dumps(d)
        assert "ACCESS-not-a-real-token" not in blob and PASS not in blob
        assert "salt" not in blob and "ciphertext" not in blob

    def test_info_on_a_corrupt_file_still_answers(self, vault):
        vault.path.parent.mkdir(parents=True, exist_ok=True)
        vault.path.write_text("garbage")
        info = vault.info()
        assert info.exists is True and info.version is None
        assert info.size_bytes == len("garbage")


class TestChoosingAPassphrase:
    def test_a_short_one_is_refused_when_it_is_chosen(self, vault):
        with pytest.raises(VaultError, match=str(MIN_PASSPHRASE_LEN)):
            vault.store(TOKEN, "short")

    def test_exactly_the_minimum_is_accepted(self, vault):
        vault.store(TOKEN, "a" * MIN_PASSPHRASE_LEN)
        assert vault.load("a" * MIN_PASSPHRASE_LEN) == TOKEN

    def test_a_passphrase_with_edge_whitespace_is_refused(self, vault):
        """A form that trims a trailing space is a vault that stops opening."""
        with pytest.raises(VaultError, match="space"):
            vault.store(TOKEN, PASS + " ")

    def test_the_length_rule_does_not_apply_to_opening_an_existing_vault(self, vault):
        """The complaint belongs where he is choosing, not where he is trying
        to get in. A vault made under older rules must still open."""
        vault.store(TOKEN, PASS)
        assert vault.verify("short") is False   # refused as wrong, not as short

    def test_a_non_string_passphrase_is_refused(self, vault):
        with pytest.raises(VaultError, match="text"):
            vault.store(TOKEN, 12345678901234)

    def test_unicode_passphrases_work(self, vault):
        phrase = "correct·horse·battery·staple·日本語"
        vault.store(TOKEN, phrase)
        assert vault.load(phrase) == TOKEN


class TestRotation:
    def test_the_new_passphrase_opens_it_and_the_old_one_does_not(self, vault):
        vault.store(TOKEN, PASS)
        vault.rotate(PASS, OTHER)
        assert vault.load(OTHER) == TOKEN
        with pytest.raises(BadPassphrase):
            vault.load(PASS)

    def test_a_wrong_current_passphrase_cannot_destroy_the_vault(self, vault):
        vault.store(TOKEN, PASS)
        with pytest.raises(BadPassphrase):
            vault.rotate("not the one", "a brand new passphrase")
        assert vault.load(PASS) == TOKEN

    def test_a_weak_new_passphrase_is_refused_before_the_rewrite(self, vault):
        vault.store(TOKEN, PASS)
        with pytest.raises(VaultError, match=str(MIN_PASSPHRASE_LEN)):
            vault.rotate(PASS, "short")
        assert vault.load(PASS) == TOKEN


class TestTheParametersTravelWithTheFile:
    def test_a_vault_written_with_one_cost_opens_under_a_reader_set_to_another(
            self, tmp_path):
        """Raising the work factors later must not orphan a vault Steve
        already has: the parameters are read from his file, not assumed."""
        path = tmp_path / "token.enc"
        Vault(path, n=2 ** 10).store(TOKEN, PASS)
        assert Vault(path, n=2 ** 14).load(PASS) == TOKEN

    def test_the_file_records_the_parameters_it_was_written_with(self, tmp_path):
        path = tmp_path / "token.enc"
        Vault(path, n=2 ** 10, r=8, p=1).store(TOKEN, PASS)
        kdf = json.loads(path.read_text())["kdf"]
        assert (kdf["name"], kdf["n"], kdf["r"], kdf["p"]) == ("scrypt", 2 ** 10, 8, 1)
