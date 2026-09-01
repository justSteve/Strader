"""The vault — the broker credential at rest, under Steve's passphrase. [st-w2nw]

Design §4. Today the Schwab token is a plaintext file that any process on this
box can read, and every agent session here runs as root. After stage 3 the only
copy is this vault: a single file holding the token JSON encrypted with
AES-256-GCM under a key derived from a passphrase Steve types into the
service's page and never writes down. No passphrase on disk. No key file. No
recovery — a forgotten passphrase means re-authorising with Schwab, which is a
five-minute inconvenience and the correct trade for having nothing on disk that
unlocks the credential.

**Payload-agnostic on purpose.** This module knows nothing about Schwab, OAuth
or token shapes; it stores a JSON-able mapping and gives it back. The token's
meaning lives with the client that uses it. That is what lets the whole vault
be tested without a credential anywhere near it.

**What it does not do, deliberately.** It does not log — not the passphrase,
not the payload, not a truncated preview of either. It does not return the
payload from :meth:`info`. It does not cache a derived key between calls, so a
running service that has been locked holds no way back in.

**One honest limit.** Python strings cannot be reliably wiped from memory: the
passphrase you pass in may survive in the interpreter's heap until it is reused.
The derived key is held in a ``bytearray`` and zeroed after use, which is worth
doing and is not the same as a guarantee — in particular, handing the key to
``AESGCM`` requires ``bytes(key)``, an immutable copy the wipe cannot reach, so
what the zeroing buys is one fewer lingering copy, not zero copies (audit
finding, 06 §2). The credential is protected *at rest* here; protecting it in
memory from a root process on the same box is the process boundary the design
already names as a residual (§5).
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

VERSION = 1
CIPHER = "AES-256-GCM"

# scrypt work factors. n=2^15 costs roughly 32 MB and a tenth of a second here,
# which is nothing once a session and expensive per guess. They are written into
# the file rather than assumed, so raising them later does not orphan a vault
# Steve has already stored — his file keeps its own parameters until he rewrites
# it, and a rewrite happens on every re-auth anyway.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12

# The box these parameters must fit. scrypt allocates 128·n·r bytes BEFORE the
# ciphertext can be authenticated — the derivation is what produces the key the
# tag check needs — so the work factors in the file are attacker-writable input
# to an allocation, not yet authenticated data. Finding 7 of the 2026-08-30
# audit (st-5t6z): a file rewritten with n=2^24 asks this box for 16 GB, and
# this box has been OOM-killed twice this month; the tag check never runs
# because the process is dead. The AAD still protects against *lowering* the
# factors (the cheap derivation completes and then fails the tag); these bounds
# are the guard in the other direction, and they are generous — the ceiling is
# 32× the work and 16× the memory of today's defaults. The floor is not a
# security bound — the AAD already catches lowered factors, after a cheap
# derivation — it only rejects nonsense before scrypt sees it.
SCRYPT_N_MIN = 2 ** 10
SCRYPT_N_MAX = 2 ** 20
SCRYPT_R_MAX = 16
SCRYPT_P_MAX = 4
SCRYPT_MEM_CAP_BYTES = 512 * 1024 * 1024   # 128·n·r must stay under this


def _kdf_param_problems(n: int, r: int, p: int, dklen: int) -> list[str]:
    """Why these scrypt parameters will not be run, or an empty list."""
    out: list[str] = []
    if not (SCRYPT_N_MIN <= n <= SCRYPT_N_MAX) or (n & (n - 1)):
        out.append(f"n={n} must be a power of two within "
                   f"[{SCRYPT_N_MIN}, {SCRYPT_N_MAX}]")
    if not (1 <= r <= SCRYPT_R_MAX):
        out.append(f"r={r} must be within [1, {SCRYPT_R_MAX}]")
    if not (1 <= p <= SCRYPT_P_MAX):
        out.append(f"p={p} must be within [1, {SCRYPT_P_MAX}]")
    if dklen != KEY_LEN:
        out.append(f"dklen={dklen} must be {KEY_LEN}")
    if not out and 128 * n * r > SCRYPT_MEM_CAP_BYTES:
        out.append(f"n={n}, r={r} needs {128 * n * r} bytes, over the "
                   f"{SCRYPT_MEM_CAP_BYTES}-byte cap")
    return out

#: Short enough not to be a nuisance he has to type from a phone, long enough
#: that scrypt at these parameters makes guessing pointless. Enforced on write
#: so the refusal arrives when he is choosing, not when he is unlocking.
MIN_PASSPHRASE_LEN = 12


class VaultError(RuntimeError):
    """Anything that stops the vault answering."""


class VaultMissing(VaultError):
    """No vault file. The service has never been given a credential."""


class VaultCorrupt(VaultError):
    """The file is not a vault this version can read."""


class BadPassphrase(VaultError):
    """The passphrase did not decrypt the vault.

    Indistinguishable, on purpose, from a tampered file: AES-GCM authenticates
    the ciphertext, so a wrong key and a modified byte fail the same way. There
    is nothing useful to tell apart and nothing safe to guess."""


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: Any, field: str) -> bytes:
    if not isinstance(text, str):
        raise VaultCorrupt(f"vault field {field!r} is not text")
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, TypeError):
        raise VaultCorrupt(f"vault field {field!r} is not valid base64") from None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class VaultInfo:
    """Everything about the vault that is safe to show on a page."""

    path: str
    exists: bool
    version: int | None = None
    cipher: str | None = None
    kdf: str | None = None
    created: str | None = None
    updated: str | None = None
    size_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "exists": self.exists, "version": self.version,
            "cipher": self.cipher, "kdf": self.kdf, "created": self.created,
            "updated": self.updated, "size_bytes": self.size_bytes,
        }


class Vault:
    def __init__(self, path: str | Path, *, n: int = SCRYPT_N,
                 r: int = SCRYPT_R, p: int = SCRYPT_P) -> None:
        if problems := _kdf_param_problems(n, r, p, KEY_LEN):
            # Refused at construction so a vault this service writes is always
            # one it will be able to open.
            raise VaultError("scrypt parameters refused: " + "; ".join(problems))
        self.path = Path(path)
        self.n, self.r, self.p = n, r, p

    # ── reading the envelope ─────────────────────────────────────────────
    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def _envelope(self) -> dict[str, Any]:
        if not self.exists:
            raise VaultMissing(f"no vault at {self.path}")
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise VaultCorrupt(f"vault at {self.path} is not readable JSON: {exc}") from None
        if not isinstance(loaded, dict):
            raise VaultCorrupt(f"vault at {self.path} is not an object")
        if loaded.get("version") != VERSION:
            raise VaultCorrupt(
                f"vault at {self.path} is version {loaded.get('version')!r}, "
                f"this service reads version {VERSION}"
            )
        for field in ("kdf", "cipher", "nonce", "ciphertext"):
            if field not in loaded:
                raise VaultCorrupt(f"vault at {self.path} has no {field!r}")
        if loaded["cipher"] != CIPHER:
            raise VaultCorrupt(f"vault cipher {loaded['cipher']!r} is not {CIPHER}")
        kdf = loaded["kdf"]
        if not isinstance(kdf, dict) or kdf.get("name") != "scrypt":
            raise VaultCorrupt("vault key derivation is not scrypt")
        return loaded

    def info(self) -> VaultInfo:
        """Metadata only. Never the payload, never anything derived from it."""
        if not self.exists:
            return VaultInfo(path=str(self.path), exists=False)
        try:
            env = self._envelope()
        except VaultCorrupt:
            return VaultInfo(path=str(self.path), exists=True,
                             size_bytes=self.path.stat().st_size)
        kdf = env["kdf"]
        return VaultInfo(
            path=str(self.path), exists=True, version=env["version"],
            cipher=env["cipher"],
            kdf=f"scrypt n={kdf.get('n')} r={kdf.get('r')} p={kdf.get('p')}",
            created=env.get("created"), updated=env.get("updated"),
            size_bytes=self.path.stat().st_size,
        )

    # ── the key ──────────────────────────────────────────────────────────
    def _derive(self, passphrase: str, salt: bytes, *, n: int, r: int,
                p: int) -> bytearray:
        # NFC first: "café" typed on a phone and "café" typed on a keyboard can
        # arrive as different byte sequences for the same characters, and a
        # vault with no recovery path must not care which keyboard he used.
        normalized = unicodedata.normalize("NFC", passphrase)
        kdf = Scrypt(salt=salt, length=KEY_LEN, n=n, r=r, p=p)
        return bytearray(kdf.derive(normalized.encode("utf-8")))

    @staticmethod
    def _wipe(key: bytearray) -> None:
        """Best effort, and only that — see the module docstring."""
        for i in range(len(key)):
            key[i] = 0

    @staticmethod
    def _aad(env: Mapping[str, Any]) -> bytes:
        """The header, authenticated with the ciphertext.

        Without this, the work factors and the version are unauthenticated
        plaintext: someone could rewrite ``n`` down to 1 and the file would
        still decrypt for whoever held the passphrase, having quietly become
        cheap to attack. With it, any edit to the header fails the tag."""
        header = {"version": env["version"], "cipher": env["cipher"], "kdf": env["kdf"]}
        return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")

    # ── writing ──────────────────────────────────────────────────────────
    def store(self, payload: Mapping[str, Any], passphrase: str) -> VaultInfo:
        """Encrypt ``payload`` under ``passphrase`` and replace the vault."""
        if not isinstance(payload, Mapping):
            raise VaultError("the vault stores a mapping")
        self.check_passphrase(passphrase)
        try:
            plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise VaultError(f"payload is not JSON-able: {exc}") from None

        salt = secrets.token_bytes(SALT_LEN)
        nonce = secrets.token_bytes(NONCE_LEN)
        created = self._existing_created() or _now()
        env: dict[str, Any] = {
            "version": VERSION,
            "cipher": CIPHER,
            "kdf": {"name": "scrypt", "n": self.n, "r": self.r, "p": self.p,
                    "dklen": KEY_LEN, "salt": _b64(salt)},
            "created": created,
            "updated": _now(),
        }
        key = self._derive(passphrase, salt, n=self.n, r=self.r, p=self.p)
        try:
            ciphertext = AESGCM(bytes(key)).encrypt(nonce, plaintext, self._aad(env))
        finally:
            self._wipe(key)
        env["nonce"] = _b64(nonce)
        env["ciphertext"] = _b64(ciphertext)
        self._write_atomic(json.dumps(env, indent=1).encode("utf-8"))
        return self.info()

    def _existing_created(self) -> str | None:
        try:
            return self._envelope().get("created")
        except VaultError:
            return None

    def _write_atomic(self, blob: bytes) -> None:
        """Write, fsync, rename. A vault half-written by a crash is a vault
        that cannot be opened, and this box has lost a run to an OOM kill this
        month — so the old file stays intact until the new one is on disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            os.chmod(self.path, 0o600)
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    # ── reading ──────────────────────────────────────────────────────────
    def load(self, passphrase: str) -> dict[str, Any]:
        """Decrypt and return the payload. Raises rather than returning None."""
        env = self._envelope()
        kdf = env["kdf"]
        try:
            n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
            dklen = int(kdf.get("dklen", KEY_LEN))
        except (KeyError, TypeError, ValueError):
            raise VaultCorrupt("vault key-derivation parameters are unreadable") from None
        # Bounded BEFORE the derivation runs. The parameters come out of the
        # file, the file is writable by anything on this box, and scrypt
        # allocates 128·n·r bytes before the AAD can say whether the header is
        # authentic. See the constants above.
        if problems := _kdf_param_problems(n, r, p, dklen):
            raise VaultCorrupt(
                "vault key-derivation parameters are outside what this service "
                "will run: " + "; ".join(problems))
        salt = _unb64(kdf.get("salt"), "kdf.salt")
        nonce = _unb64(env.get("nonce"), "nonce")
        ciphertext = _unb64(env.get("ciphertext"), "ciphertext")

        key = self._derive(passphrase, salt, n=n, r=r, p=p)
        try:
            plaintext = AESGCM(bytes(key)).decrypt(nonce, ciphertext, self._aad(env))
        except InvalidTag:
            raise BadPassphrase(
                "the vault did not open — wrong passphrase, or the file has been altered"
            ) from None
        finally:
            self._wipe(key)

        try:
            payload = json.loads(plaintext)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise VaultCorrupt("the vault opened but its contents are not JSON") from None
        if not isinstance(payload, dict):
            raise VaultCorrupt("the vault opened but does not hold an object")
        return payload

    def verify(self, passphrase: str) -> bool:
        """Does this passphrase open the vault? For the page's 'try again',
        so it does not have to hold a decrypted credential to find out."""
        try:
            self.load(passphrase)
        except BadPassphrase:
            return False
        return True

    def rotate(self, old_passphrase: str, new_passphrase: str) -> VaultInfo:
        """Re-encrypt under a new passphrase. Fails before touching the file if
        the old one is wrong, so a mistyped current passphrase cannot destroy
        the vault."""
        payload = self.load(old_passphrase)
        self.check_passphrase(new_passphrase)
        return self.store(payload, new_passphrase)

    # ── the one policy this module holds ─────────────────────────────────
    @staticmethod
    def check_passphrase(passphrase: str) -> None:
        """Refused on write, not on read: the complaint has to arrive while
        Steve is choosing, never while he is trying to get into a vault he
        already made."""
        if not isinstance(passphrase, str):
            raise VaultError("the passphrase must be text")
        if len(passphrase) < MIN_PASSPHRASE_LEN:
            raise VaultError(
                f"the passphrase must be at least {MIN_PASSPHRASE_LEN} characters — "
                f"this one is {len(passphrase)}. It is the only thing standing "
                f"between a live trading credential and anyone who reads the file."
            )
        if passphrase.strip() != passphrase:
            raise VaultError(
                "the passphrase begins or ends with a space — refused, because a "
                "space that a form silently trims is a vault that stops opening"
            )
