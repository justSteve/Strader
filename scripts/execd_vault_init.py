#!/usr/bin/env python3
"""Write (or check) the execution service's credential vault. [st-w2nw, st-p8k8]

The service (``execd``) holds the Schwab credential encrypted at rest under a
passphrase only Steve knows (``execd/vault.py``). This script is how the vault
gets written the first time, from the pieces that exist today:

- the app key and secret from the repo's ``.env`` (validated by
  ``strader.settings`` — the same loader every reader uses);
- the current token file at ``SCHWAB_TOKEN_PATH`` in schwab-py's wrapped shape.

It asks for the passphrase twice, on the terminal, with no echo. Nothing
about the passphrase or the credential is printed, logged, or written
anywhere but the vault file. Steve runs this at stage 3; it needs his
passphrase, so an agent cannot run it for him and must not try.

    .venv/bin/python scripts/execd_vault_init.py --vault /etc/execd/vault.json
    .venv/bin/python scripts/execd_vault_init.py --vault /etc/execd/vault.json --check

``--check`` opens an existing vault with the passphrase and reports the
refresh-token wall and nothing else — the way to confirm a vault before the
plaintext token is retired.

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

from execd.schwab import Credential  # noqa: E402
from execd.vault import BadPassphrase, Vault, VaultError  # noqa: E402
from strader.settings import load_schwab  # noqa: E402


def _token_path(cfg: dict[str, str]) -> Path:
    raw = cfg.get("SCHWAB_TOKEN_PATH") or "./tokens/schwab_token.json"
    p = Path(raw)
    return p if p.is_absolute() else (REPO / raw).resolve()


def _ask(prompt: str) -> str:
    if not sys.stdin.isatty():
        raise SystemExit("this needs a terminal — the passphrase is typed, never piped")
    return getpass.getpass(prompt)


def init(vault_path: Path) -> int:
    cfg = load_schwab()
    tpath = _token_path(cfg)
    if not tpath.exists():
        print(f"no token at {tpath}; run scripts/refresh_schwab_token.py first", file=sys.stderr)
        return 1
    wrapped = json.loads(tpath.read_text(encoding="utf-8"))
    payload = {"app": {"key": cfg["SCHWAB_API_KEY"], "secret": cfg["SCHWAB_APP_SECRET"]},
               "token": wrapped}
    try:
        cred = Credential.from_payload(payload)
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
    first = _ask("passphrase (12+ characters, no leading/trailing space): ")
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
    print("next: python -m execd --schwab --vault", vault_path, "--unlock-stdin")
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
        cred = Credential.from_payload(payload)
    except ValueError as exc:
        print(f"the vault opened but its payload is not a credential: {exc}", file=sys.stderr)
        return 1
    print(f"vault opens; refresh token created {cred.created_at.isoformat()}, "
          f"wall {cred.refresh_wall.isoformat()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--vault", required=True, type=Path)
    p.add_argument("--check", action="store_true", help="open an existing vault and report its wall")
    args = p.parse_args(argv)
    return check(args.vault) if args.check else init(args.vault)


if __name__ == "__main__":
    raise SystemExit(main())
