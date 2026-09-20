"""The weekly Schwab re-authorisation, in one place — and the market
credential file it writes.

Schwab's refresh tokens die after seven days and only a browser login brings
one back, so this flow runs every week for both of Steve's apps. It has two
front doors and they must not drift apart:

* **the page** (:mod:`execd.page`), which runs the flow inside the service's
  own process, so a new grant reaches the running transport in the same step
  it reaches disk;
* **his terminal handles** — ``reauthData`` and ``reauthAccount``, through
  ``scripts/execd_reauth.py`` — which run it in a process of his own.

Both end at the same three steps: a login link, an exchange proved against the
app's own endpoint family before anything is stored, and a store into whichever
home that app's credential lives in. Everything either door needs beyond that
lives here, so a fix to the flow cannot land in one and miss the other.

**The terminal door writes the service's stores from outside it.** That is
Steve's own act, as root, the same way ``deploy/install.sh --execd`` mints
those files — not an agent reaching past the wall; the gate keeps agent shells
off the page port and out of the installed tree, and this module adds nothing
they can reach. Two consequences are handled rather than hoped away: the files
must keep the owner the service reads them as (:func:`preserve_owner`), and
the running process holds its own copy of each credential — the market one
re-reads itself when the file moves (:class:`CredentialFile`), the trading one
cannot, because the service does not keep the passphrase, so a re-auth while it
is armed is *reported* instead of being silently half-done.

Nothing here prints, logs or journals a token value. [st-bd2g]
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .broker import BrokerError
from .schwab import (VAULT_VERSION, App, Credential, authorize_url, code_from_received_url,
                     exchange, trading_payload, verify_grant)
from .vault import Vault

#: How long a login link is good for on the page. The terminal flow has no
#: nonce store — the operator is standing at the prompt — but Schwab's own
#: authorisation code dies in seconds either way.
REAUTH_TTL_S = 10 * 60.0


class ReauthRefused(RuntimeError):
    """A refusal shown to Steve in plain words. Never carries a value."""


# ── the market credential file ────────────────────────────────────────────


class CredentialFile:
    """The market-data app's credential on disk, and its in-memory copy.

    Loaded once at start (``python -m execd --market-credential FILE``) and
    handed to the transport as a callable, so a re-authorisation on the page
    can replace both the file and what the transport sees, atomically, without
    a restart. Plain JSON, mode 0600, owned by the service user — outside the
    vault by design (st-p9mx: this app cannot trade, so a credential that must
    load before Steve types anything costs nothing to hold that way)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._payload: dict[str, Any] | None = None
        self._stamp: tuple[int, int, int] | None = None

    def _current_stamp(self) -> tuple[int, int, int] | None:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    def load(self) -> dict[str, Any]:
        stamp = self._current_stamp()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        Credential.from_payload(raw)      # shape-checked here, not on the first quote
        with self._lock:
            self._payload = raw
            self._stamp = stamp
        return raw

    def current(self) -> dict[str, Any]:
        """What the transport calls on every market read.

        Re-read when the file has moved underneath us. A re-authorisation on
        the page replaces both copies in one step, but one run of ``reauthData``
        in Steve's terminal writes only the file, and a service still serving
        its start-up copy would go on presenting a grant that is dead — which
        is exactly the failure the handle was run to fix. The cost is one
        ``stat`` per market call; the file is parsed again only when the stamp
        moves, and a file caught mid-replace leaves the good copy in place
        rather than taking the service down. [st-bd2g]"""
        with self._lock:
            stamp = self._current_stamp()
            if stamp is not None and stamp != self._stamp:
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    Credential.from_payload(raw)
                except (OSError, ValueError):
                    pass                  # keep what works; the stamp stays unclaimed
                else:
                    self._payload = raw
                    self._stamp = stamp
            if self._payload is None:
                raise BrokerError("no market credential is loaded")
            return self._payload

    def save(self, payload: Mapping[str, Any]) -> None:
        """Write, fsync, rename, 0600 — the vault's discipline, for the same
        reason: a half-written credential is one the service will not start
        with, and this box has been OOM-killed mid-run before."""
        Credential.from_payload(payload)
        blob = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
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
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        with self._lock:
            self._payload = dict(payload)
            self._stamp = self._current_stamp()


# ── ownership, when the writer is not the reader ──────────────────────────


def _owner_of(path: Path) -> tuple[int, int] | None:
    for candidate in (path, path.parent):
        try:
            st = candidate.stat()
        except OSError:
            continue
        return (st.st_uid, st.st_gid)
    return None


def preserve_owner(path: str | Path) -> Callable[[], str | None]:
    """Remember who owns a file, and hand back the call that puts them back.

    The page writes these files as the service user and this never fires. The
    terminal handles write them as root, and ``os.replace`` of a temporary file
    leaves the new inode owned by whoever wrote it: a vault owned by ``root``
    is a service that cannot read its own credential after the next restart.
    The returned callable answers ``None`` when the owner is right and a
    sentence naming the repair when it could not set it."""
    p = Path(path)
    before = _owner_of(p)

    def restore() -> str | None:
        if before is None:
            return None
        try:
            st = p.stat()
        except OSError as exc:
            return f"{p} could not be read back after the write: {exc}"
        if (st.st_uid, st.st_gid) == before:
            return None
        try:
            os.chown(p, before[0], before[1])
        except OSError as exc:
            return (f"{p} is now owned by uid {st.st_uid}:{st.st_gid} and the service "
                    f"reads it as uid {before[0]}:{before[1]} ({exc}). Repair it with: "
                    f"chown {before[0]}:{before[1]} {p}")
        return None

    return restore


# ── the flow ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Source:
    """The app key and secret the OAuth calls need, and where Schwab is
    registered to send the browser back."""

    app_key: str
    secret: str
    callback_url: str | None


@dataclass(frozen=True)
class Stored:
    """What a store produced: the new seven-day wall, and — for the trading
    app — the payload the caller may put into a running service's memory."""

    wall: datetime
    trading: dict[str, Any] | None = None


def new_state() -> str:
    """The ``state`` parameter, echoed back in the pasted address. It is the
    one defence the flow has against a URL that came from somewhere else."""
    return secrets.token_urlsafe(16)


def app_credential(target: App, vault_payload: Mapping[str, Any] | None,
                   market_payload: Mapping[str, Any] | None) -> Source:
    """The app key and secret the OAuth calls need, from where each lives:
    the trading app's in the vault (already open, or we would not be here);
    the market app's in its file. The passphrase gates both — a market
    re-auth cannot leak trading capability, but every credential write is
    Steve's act, and the vault opening is how the flow knows."""
    if target is App.TRADING:
        trading = trading_payload(vault_payload)
        try:
            cred = Credential.from_payload(trading)
        except ValueError as exc:
            raise ReauthRefused(f"The vault holds no usable trading credential: {exc}")
        return Source(cred.app_key, cred.secret, trading.get("callback_url"))
    if market_payload is None:
        raise ReauthRefused("There is no market credential here; there is nothing to "
                            "re-authorise for the market app.")
    try:
        cred = Credential.from_payload(market_payload)
    except (BrokerError, ValueError) as exc:
        raise ReauthRefused(f"The market credential is not usable: {exc}")
    return Source(cred.app_key, cred.secret, market_payload.get("callback_url"))


def callback_for(source: Source, default: str) -> str:
    return source.callback_url or default


def login_link(source: Source, default_callback: str, state: str) -> str:
    """The link Steve opens. Schwab sends his browser back to the callback
    with a code on the query string."""
    return authorize_url(source.app_key, callback_for(source, default_callback), state)


def exchange_and_verify(client: Any, target: App, source: Source, default_callback: str,
                        state: str, received_url: str) -> dict[str, Any]:
    """Pasted address in, a proved grant out. The verification is the whole
    point of doing it here rather than at the store: a grant with no refresh
    token answers 200 to the next call and is dead half an hour later (the
    2026-08-12 shape), so nothing is written until the live check reaches the
    family this app is registered for."""
    code = code_from_received_url(received_url, state)
    wrapped = exchange(client, source.app_key, source.secret,
                       callback_for(source, default_callback), code)
    verify_grant(client, target, wrapped)
    return wrapped


def store_grant(target: App, wrapped: Mapping[str, Any], *,
                vault: Vault | None = None,
                vault_payload: Mapping[str, Any] | None = None,
                passphrase: str | None = None,
                market_payload: Mapping[str, Any] | None = None,
                market_save: Callable[[Mapping[str, Any]], None] | None = None) -> Stored:
    """Store a verified grant where its app's credential lives.

    Returns the new refresh wall, and for the trading app the payload a caller
    inside the service puts into memory. Putting it there — and journalling the
    event — belongs to the caller, because only one of the two doors has a
    running service to hand."""
    if target is App.TRADING:
        if vault is None or passphrase is None:
            raise ReauthRefused("A trading grant cannot be stored without the vault "
                                "and its passphrase.")
        trading = dict(trading_payload(vault_payload))
        trading["token"] = dict(wrapped)
        envelope: dict[str, Any] = dict(vault_payload or {}) \
            if isinstance(vault_payload, Mapping) and "trading" in vault_payload else {}
        envelope["version"] = VAULT_VERSION
        envelope["trading"] = trading
        vault.store(envelope, passphrase)
        return Stored(Credential.from_payload(trading).refresh_wall, trading)
    if market_payload is None or market_save is None:
        raise ReauthRefused("There is no market credential here to replace.")
    payload = dict(market_payload)
    payload["token"] = dict(wrapped)
    market_save(payload)
    return Stored(Credential.from_payload(payload).refresh_wall, None)
