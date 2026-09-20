#!/usr/bin/env python3
"""The weekly Schwab re-authorisation, run from Steve's own terminal.

This is what ``reauthData`` and ``reauthAccount`` reach once the execution
service is installed. Between stage 3 and 2026-09-20 they reached nothing:
they printed the page's address and exited 3, because the grant they used to
mint went into a token file under ``tokens/`` that nothing reads any more.
Steve asked for the handles back (st-bd2g), so they re-authorise the thing
that is actually used — the service's own credential stores.

Same flow as the page, from :mod:`execd.reauth`: a login link, a paste, an
exchange proved against the app's own endpoint family, and a store into the
vault (trading) or the market credential file. The difference is only who is
running it, and that difference has two consequences this module is here to
handle honestly:

* **Ownership.** The page writes as the service user; this writes as root.
  Every write — the credential store and the journal line beside it — is
  bracketed by :func:`execd.reauth.preserve_owner`, so each file keeps the
  owner the service reads and appends to it as, and a journal file this run
  created is put back to owner-only.
* **The running process holds its own copy.** The market credential re-reads
  itself when the file moves, so a market re-auth lands without a restart —
  but only on a build that carries that change, so this asks the service for a
  live quote afterwards and reports what it actually got rather than assuming.
  The trading credential cannot re-read itself: the service does not keep the
  passphrase. While it is LOCKED — the ordinary case, weekday morning, before
  the first unlock — the next unlock reads the new grant and there is nothing
  to do. While it is armed, this says so in plain words instead of leaving him
  with a stored grant and a process still using the old one.

Nothing here prints, logs or journals a token value — ``tests/scripts/
test_execd_reauth.py`` asserts that against the output of a full run.
"""
from __future__ import annotations

import getpass
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx                                                    # noqa: E402

from execd.bounds import CT                                     # noqa: E402
from execd.broker import BrokerError                            # noqa: E402
from execd.journal import Journal                               # noqa: E402
from execd.reauth import (CredentialFile, ReauthRefused, app_credential,     # noqa: E402
                          exchange_and_verify, login_link, new_state,
                          preserve_owner, store_grant)
from execd.schwab import App, new_client                        # noqa: E402
from execd.vault import BadPassphrase, Vault, VaultError        # noqa: E402

#: Where the installed service keeps its state. The install writes all three.
DEFAULT_STATE_DIR = "/var/lib/execd"
DEFAULT_VAULT = f"{DEFAULT_STATE_DIR}/vault.json"
DEFAULT_MARKET = f"{DEFAULT_STATE_DIR}/market.json"

#: The service's own API, on the loopback. Read-only here: the walls it is
#: serving, the arming state, and one quote to prove the new market grant
#: actually reached the running process.
DEFAULT_API = "http://127.0.0.1:8778"

#: The OAuth callback both Schwab apps are registered with.
DEFAULT_CALLBACK_URL = "https://127.0.0.1:8182"

#: The handle that runs each app, for the closing "do the other one" line.
HANDLE = {App.MARKET: "reauthData", App.TRADING: "reauthAccount"}
IN_WORDS = {App.MARKET: "app 1, market data", App.TRADING: "app 2, Accounts and Trading"}

#: Exit codes. **Zero means the grant was stored**, notes on the screen or not:
#: the shell wrapper around these handles reads any non-zero code as "token
#: regeneration failed — the old token is untouched", and a stored grant
#: reported that way would be the opposite of the truth. What is left to do
#: about the running service is said in words, in the last lines of the run,
#: where the operator is already looking.
OK, REFUSED, FAILED = 0, 1, 2


def _wall_in_words(wall: datetime) -> str:
    return wall.astimezone(CT).strftime("%a %Y-%m-%d %H:%M CT")


class _Service:
    """What the running service will tell a reader on the loopback. Every
    answer is optional: the handles must work with the service stopped."""

    def __init__(self, base: str, client: Any | None = None) -> None:
        self.base = base.rstrip("/")
        self._client = client

    def _get(self, path: str, **params: str) -> dict[str, Any] | None:
        try:
            if self._client is not None:
                r = self._client.get(f"{self.base}{path}", params=params or None)
            else:
                r = httpx.get(f"{self.base}{path}", params=params or None, timeout=8.0)
            if r.status_code != 200:
                return None
            body = r.json()
            return body if isinstance(body, dict) else None
        except Exception:
            return None

    def status(self) -> dict[str, Any] | None:
        return self._get("/status")

    def market_reads(self) -> bool:
        """One quote through the service. The proof that a new market grant
        reached the running process, rather than only the disk — the running
        process makes a live market call with whatever grant it is holding,
        and a dead one cannot answer. ``$SPX`` is the index symbol the service
        and its readers use (``ExecService.index_symbol``)."""
        return self._get("/quote", symbol="$SPX") is not None


def _read_market(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _journal(state_dir: Path, mode: str) -> Journal | None:
    """The service reads its own journal for the trading wall while it is
    LOCKED (``ExecService._last_known_trading_wall``), and the 06:30 token-age
    heartbeat reads that. A re-auth this flow did not record is a wall the
    heartbeat goes on alerting about all week."""
    try:
        return Journal(state_dir / "journal", sha="terminal", mode=mode)
    except OSError:
        return None


def reauthorise(target: App, *,
                vault_path: str | Path = DEFAULT_VAULT,
                market_path: str | Path = DEFAULT_MARKET,
                state_dir: str | Path = DEFAULT_STATE_DIR,
                callback_url: str = DEFAULT_CALLBACK_URL,
                api_base: str = DEFAULT_API,
                http_client: Any | None = None,
                api_client: Any | None = None,
                ask_passphrase: Callable[[str], str] = getpass.getpass,
                ask_line: Callable[[str], str] = input,
                out: TextIO | None = None) -> int:
    """Run one app's re-authorisation. Returns an exit code, not a raise: the
    caller is a shell handle and the operator is reading the screen."""
    say = (out or sys.stdout).write
    vault_path, market_path = Path(vault_path), Path(market_path)
    service = _Service(api_base, api_client)
    status = service.status()

    say(f"\n── re-authorising {IN_WORDS[target]} ──\n")
    say(f"Reading the execution service's credential store at {state_dir}.\n")
    if status is None:
        say("The service is not answering on the loopback. The store is still "
            "written; it is read at the next start.\n")
    else:
        say(f"The service is {status.get('arming', {}).get('state', '?')}, "
            f"mode {status.get('mode', '?')}.\n")

    # ── the app's own key and secret, from where that app's credential lives ──
    passphrase: str | None = None
    vault: Vault | None = None
    vault_payload: Mapping[str, Any] | None = None
    market_file: CredentialFile | None = None
    market_payload: Mapping[str, Any] | None = None
    try:
        if target is App.TRADING:
            vault = Vault(vault_path)
            if not vault.exists:
                say(f"\nThere is no vault at {vault_path}. Nothing to re-authorise.\n")
                return REFUSED
            passphrase = ask_passphrase("execd vault passphrase: ")
            vault_payload = vault.load(passphrase)
        else:
            market_payload = _read_market(market_path)
            if market_payload is None:
                say(f"\nThere is no usable market credential at {market_path}.\n")
                return REFUSED
            market_file = CredentialFile(market_path)
        source = app_credential(target, vault_payload, market_payload)
    except BadPassphrase:
        say("\nThe vault did not open. Nothing was sent and nothing was stored.\n")
        return REFUSED
    except VaultError as exc:
        say(f"\nThe vault could not be read: {exc}\n")
        return REFUSED
    except ReauthRefused as exc:
        say(f"\n{exc}\n")
        return REFUSED

    # ── the login, and the paste ──────────────────────────────────────────
    state = new_state()
    say("\n1. Open this link, log in to Schwab and approve the app:\n\n")
    say(f"   {login_link(source, callback_url, state)}\n\n")
    say("2. Schwab sends your browser to an address that will not load. That is\n"
        "   expected — only the address matters. Copy the whole thing out of the\n"
        "   address bar and paste it here. Paste it straight away: Schwab's code\n"
        "   dies within seconds.\n\n")
    try:
        received = ask_line("Landing address> ")
    except (EOFError, KeyboardInterrupt):
        say("\nNothing pasted. Nothing was stored.\n")
        return REFUSED

    # ── exchange, proved before anything is written ───────────────────────
    say("\nExchanging the code and proving the grant against this app's own "
        "endpoints…\n")
    client = http_client if http_client is not None else new_client()
    try:
        wrapped = exchange_and_verify(client, target, source, callback_url, state, received)
    except ValueError as exc:
        say(f"\nThe pasted address was not usable: {exc}. Nothing stored.\n")
        return FAILED
    except BrokerError as exc:
        say(f"\n{exc}\n")
        return FAILED
    finally:
        if http_client is None:
            try:
                client.close()
            except Exception:
                pass

    # ── the store, with the owner the service reads it as ─────────────────
    written = market_path if target is App.MARKET else vault_path
    restore = preserve_owner(written)
    try:
        if target is App.TRADING:
            stored = store_grant(target, wrapped, vault=vault,
                                 vault_payload=vault_payload, passphrase=passphrase)
        else:
            assert market_file is not None and market_payload is not None
            stored = store_grant(target, wrapped, market_payload=market_payload,
                                 market_save=market_file.save)
    except (ReauthRefused, VaultError, ValueError) as exc:
        say(f"\nThe grant was good but could not be stored: {exc}\n")
        return FAILED
    finally:
        if passphrase is not None:
            del passphrase
    ownership = restore()

    # Asked before the journal line is written, because the line carries the
    # answer: whether the running process is now serving this grant is
    # measured, not assumed from a version number.
    in_memory, running_notes = _what_the_running_service_holds(target, service, status)

    journal = _journal(Path(state_dir), str((status or {}).get("mode") or "live"))
    if journal is not None:
        line = journal.path_for()
        existed, keep_owner = line.exists(), preserve_owner(line)
        try:
            journal.record("reauth", app=target.value, refresh_wall=stored.wall,
                           in_memory=in_memory, by="terminal")
        except OSError as exc:                      # a wall unrecorded is worth saying
            say(f"\nStored, but the journal line could not be written: {exc}\n")
        else:
            if not existed:
                # Created by root at the default umask; the service's own
                # journal files are owner-only, and it appends to this one
                # every day it runs.
                try:
                    line.chmod(0o600)
                except OSError:
                    pass
            note = keep_owner()
            if note:
                say(f"\n{note}\n")

    # ── what is true now ──────────────────────────────────────────────────
    say(f"\nStored. The {target.value} app's new wall is {_wall_in_words(stored.wall)}.\n")
    for note in ([ownership] if ownership else []) + running_notes:
        say(f"\n{note}\n")
    other = HANDLE[App.MARKET if target is App.TRADING else App.TRADING]
    say(f"\nDo the other app in this sitting so the two walls stay on the same "
        f"day. The other handle is: {other}\n")
    return OK


def _what_the_running_service_holds(target: App, service: _Service,
                                    status: Mapping[str, Any] | None
                                    ) -> tuple[bool, list[str]]:
    """Whether the running process is serving the grant just stored, and what
    to say when it is not. Measured, not assumed.

    The market credential re-reads itself when the file moves, so one live
    quote answers it — on a build that carries that change it succeeds, and on
    one that does not it fails on the grant that just expired. The trading
    credential cannot re-read itself at all: the service does not keep the
    passphrase. While LOCKED that costs nothing, because the next unlock opens
    the vault this run just rewrote."""
    if status is None:
        return False, []
    if target is App.MARKET:
        if service.market_reads():
            return True, []
        return False, ["The service is still serving the old market grant — it holds "
                       "its start-up copy on this build. Pick the new one up with:\n"
                       "    systemctl restart strader-execd"]
    state = str(status.get("arming", {}).get("state", ""))
    if state in ("", "LOCKED"):
        return False, []
    return False, [f"The service is {state} and is still holding the old trading grant "
                   f"in memory — it does not keep your passphrase, so it cannot re-read "
                   f"the vault on its own. LOCK and then UNLOCK on the page to swap it "
                   f"in."]


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Re-authorise a Schwab app against the "
                                            "execution service's own credential store.")
    p.add_argument("--trading", action="store_true",
                   help="app 2, Accounts and Trading (the default is app 1, market data)")
    p.add_argument("--vault", default=DEFAULT_VAULT)
    p.add_argument("--market-credential", default=DEFAULT_MARKET)
    p.add_argument("--state-dir", default=DEFAULT_STATE_DIR)
    p.add_argument("--callback-url", default=DEFAULT_CALLBACK_URL)
    p.add_argument("--api", default=DEFAULT_API)
    args = p.parse_args(argv)
    return reauthorise(App.TRADING if args.trading else App.MARKET,
                       vault_path=args.vault, market_path=args.market_credential,
                       state_dir=args.state_dir, callback_url=args.callback_url,
                       api_base=args.api)


if __name__ == "__main__":
    raise SystemExit(main())
