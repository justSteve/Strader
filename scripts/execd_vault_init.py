#!/usr/bin/env python3
"""Write (or check) the execution service's credential vault. [st-w2nw, st-p8k8]

The service (``execd``) holds the **trading** Schwab credential encrypted at
rest under a passphrase only Steve knows (``execd/vault.py``). This script is
how the vault gets written the first time, from the pieces that exist today:

- the trading app's key and secret from the vault file named by the repo's
  ``.env`` (validated by ``strader.settings`` — the same loader every reader
  uses);
- its token at ``SCHWAB_TRADING_TOKEN_PATH`` in schwab-py's wrapped shape.

This is app 2 of two (st-p9mx). App 1 carries market data, cannot trade —
Schwab refuses the ``/trader/v1`` family on it — and is deliberately **not** in
this vault: the service must be able to read quotes before Steve has typed
anything, because the 07:00 premarket jobs run before he is awake.
``scripts/execd_market_credential.py`` writes that one, unencrypted and 0600,
and the split is what makes that safe.

It asks for the passphrase twice, on the terminal, with no echo. Nothing
about the passphrase or the credential is printed, logged, or written
anywhere but the vault file. Steve runs this at stage 3 (the install script
calls it); it needs his passphrase, so an agent cannot run it for him and
must not try. The floor is 8 characters and spaces inside are allowed
(Steve, 2026-09-10, co-ofzol).

    .venv/bin/python scripts/execd_vault_init.py --vault /var/lib/execd/vault.json
    .venv/bin/python scripts/execd_vault_init.py --vault /var/lib/execd/vault.json --check

``bash deploy/install.sh --execd`` runs this for Steve when no vault exists yet
(stage 3, st-p8k8) and sets the file's owner to the service user afterwards.

``--check`` opens an existing vault with the passphrase and reports the
refresh-token wall and nothing else — the way to confirm a vault before the
plaintext token is retired.

``--add-alpaca`` (co-8mb1z) opens an existing vault with the passphrase and
adds or replaces its ``alpaca`` section from the ``ALPACA_PAPER_*`` and
``ALPACA_LIVE_*`` pairs in the vault file ``.env`` points at (put there by
``vault-set.py Strader <NAME>``). The Schwab section is left exactly as it
was. It says which venues it found — never a value.

    .venv/bin/python scripts/execd_vault_init.py --vault /var/lib/execd/vault.json --add-alpaca

This script imports ``execd.vault`` and ``execd.schwab`` for the payload shape.
It imports neither ``schwab`` nor ``broker_schwab``; the gate hook does not
apply to it, and it makes no network call.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from execd.schwab import VAULT_VERSION, Credential, trading_payload  # noqa: E402
from execd.vault import BadPassphrase, Vault, VaultError  # noqa: E402
from strader.settings import load_alpaca, load_schwab_trading  # noqa: E402

#: vault-file names → the venue they belong to, in the vault's alpaca section.
ALPACA_NAMES = {
    "paper": ("ALPACA_PAPER_API_KEY_ID", "ALPACA_PAPER_API_SECRET_KEY"),
    "live": ("ALPACA_LIVE_API_KEY_ID", "ALPACA_LIVE_API_SECRET_KEY"),
}


def _token_path(cfg: dict[str, str]) -> Path:
    raw = cfg.get("SCHWAB_TRADING_TOKEN_PATH") or "./tokens/schwab_trading_token.json"
    p = Path(raw)
    return p if p.is_absolute() else (REPO / raw).resolve()


def _ask(prompt: str) -> str:
    if not sys.stdin.isatty():
        raise SystemExit("this needs a terminal — the passphrase is typed, never piped")
    return getpass.getpass(prompt)


def init(vault_path: Path) -> int:
    cfg = load_schwab_trading()
    tpath = _token_path(cfg)
    if not tpath.exists():
        print(f"no token at {tpath}; run scripts/refresh_schwab_token.py --trading first",
              file=sys.stderr)
        return 1
    wrapped = json.loads(tpath.read_text(encoding="utf-8"))
    trading = {"app": {"key": cfg["SCHWAB_TRADING_API_KEY"],
                       "secret": cfg["SCHWAB_TRADING_APP_SECRET"]},
               "token": wrapped}
    payload = {"version": VAULT_VERSION, "trading": trading}
    try:
        cred = Credential.from_payload(trading)
    except ValueError as exc:
        print(f"the token file is not usable as a credential: {exc}", file=sys.stderr)
        return 1

    vault = Vault(vault_path)
    if vault.exists:
        print(f"a vault already exists at {vault_path}; remove it first if you mean to replace it",
              file=sys.stderr)
        return 1
    print(f"writing {vault_path}")
    print(f"the refresh token in it expires {cred.refresh_wall.isoformat()} — "
          f"re-authorise on the page before then")
    first = _ask("passphrase (8+ characters, spaces inside allowed, none at the ends): ")
    second = _ask("again: ")
    if first != second:
        print("the two entries differ; nothing written", file=sys.stderr)
        return 1
    try:
        info = vault.store(payload, first)
    except VaultError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    finally:
        del first, second
    os.chmod(vault_path, 0o600)
    print(f"vault written: version {info.version}, {info.size_bytes} bytes, "
          f"{info.updated or info.created}")
    print("next: if the service is installed, open its page and unlock; otherwise "
          "bash deploy/install.sh --execd")
    return 0


def check(vault_path: Path) -> int:
    vault = Vault(vault_path)
    if not vault.exists:
        print(f"no vault at {vault_path}", file=sys.stderr)
        return 1
    try:
        payload = vault.load(_ask("passphrase: "))
    except BadPassphrase:
        print("the vault did not open", file=sys.stderr)
        return 3
    except VaultError as exc:
        print(f"the vault is not readable: {exc}", file=sys.stderr)
        return 1
    try:
        cred = Credential.from_payload(trading_payload(payload))
    except ValueError as exc:
        print(f"the vault opened but its payload is not a credential: {exc}", file=sys.stderr)
        return 1
    print(f"vault opens; refresh token created {cred.created_at.isoformat()}, "
          f"wall {cred.refresh_wall.isoformat()}")
    return 0


def alpaca_section(cfg: dict[str, str]) -> dict[str, dict[str, str]]:
    """The venues whose key pair is complete in ``cfg``. A half pair is an
    error, not a venue: it would arm a service that cannot authenticate."""
    out: dict[str, dict[str, str]] = {}
    for venue, (kid, secret) in ALPACA_NAMES.items():
        have = [n for n in (kid, secret) if cfg.get(n)]
        if len(have) == 1:
            raise ValueError(f"only {have[0]} is in the vault file; {venue} needs both "
                             f"{kid} and {secret}")
        if have:
            out[venue] = {"key_id": cfg[kid], "secret_key": cfg[secret]}
    return out


def add_alpaca(vault_path: Path) -> int:
    vault = Vault(vault_path)
    if not vault.exists:
        print(f"no vault at {vault_path}; write it first (this script without --add-alpaca)",
              file=sys.stderr)
        return 1
    try:
        section = alpaca_section(load_alpaca())
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    if not section:
        print("no Alpaca keys in the vault file — run vault-set.py Strader "
              "ALPACA_PAPER_API_KEY_ID (and its secret) first", file=sys.stderr)
        return 1
    # The installed vault belongs to the service user; this runs as root, and
    # the atomic rename would otherwise hand the file to root and lock the
    # service out of its own credential.
    before = vault_path.stat()
    pw = _ask("passphrase: ")
    try:
        payload = vault.load(pw)
        envelope = dict(payload)
        if "trading" not in envelope:
            # a v1 vault: the whole payload is the Schwab credential
            envelope = {"version": VAULT_VERSION, "trading": payload}
        envelope["alpaca"] = section
        info = vault.store(envelope, pw)
    except BadPassphrase:
        print("the vault did not open; nothing changed", file=sys.stderr)
        return 3
    except VaultError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    finally:
        del pw
    os.chmod(vault_path, 0o600)
    try:
        os.chown(vault_path, before.st_uid, before.st_gid)
    except PermissionError:
        print(f"could not restore the vault's owner ({before.st_uid}:{before.st_gid}); "
              f"chown it back before the service restarts", file=sys.stderr)
    print(f"alpaca section written: {', '.join(sorted(section))}; vault {info.size_bytes} bytes")
    missing = sorted(set(ALPACA_NAMES) - set(section))
    if missing:
        print(f"not in the vault file, so not added: {', '.join(missing)}")
    print("next: installExecd, then UNLOCK on the page")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--vault", required=True, type=Path)
    which = p.add_mutually_exclusive_group()
    which.add_argument("--check", action="store_true",
                       help="open an existing vault and report its wall")
    which.add_argument("--add-alpaca", action="store_true",
                       help="add Alpaca's paper/live keys from the vault file to this vault")
    args = p.parse_args(argv)
    if args.add_alpaca:
        return add_alpaca(args.vault)
    return check(args.vault) if args.check else init(args.vault)


if __name__ == "__main__":
    raise SystemExit(main())
