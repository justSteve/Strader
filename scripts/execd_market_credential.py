#!/usr/bin/env python3
"""Write the execution service's market-data credential file. [st-p9mx, st-p8k8]

Steve has two Schwab registrations. App 2 carries Accounts and Trading and its
credential lives encrypted in the vault, behind his passphrase
(``scripts/execd_vault_init.py``). App 1 carries market data and **cannot
trade**: developer.schwab.com refuses to add the Accounts and Trading product
to it, so every ``/trader/v1`` call on it answers 401 ``no apiproduct match
found``, and Steve confirmed on 2026-09-05 that the refusal is permanent.

That difference is why this file exists, and why it is not in the vault. The
service comes back LOCKED after every restart and holds no vault credential
until Steve types the passphrase — but the 07:00 CT premarket jobs run before
he is awake, and all they do is read. A credential that must load without a
passphrase cannot live behind one. Holding *this* credential that way costs
nothing, because it carries no trading capability to lose (st-p8k8's open
design point, settled on st-p9mx).

So: a plain JSON file, mode 0600, owned by the service user, in the service's
own state directory rather than the repo tree. It holds the same shape the
vault holds — ``{"app": {"key", "secret"}, "token": {schwab-py wrapped}}`` —
assembled from the app key and secret in the credential vault file named by
``.env`` and the current market token at ``SCHWAB_TOKEN_PATH``.

    .venv/bin/python scripts/execd_market_credential.py --out /var/lib/execd/market.json
    .venv/bin/python scripts/execd_market_credential.py --out /var/lib/execd/market.json --check

``--check`` reads an existing file, reports its refresh-token wall and nothing
else. Neither mode prints a key, a secret or any part of a token, and neither
makes a network call.

Composed here rather than inside ``execd`` on purpose: the package is walled
(``tests/execd/test_wall.py``) so that no module in it names a credential file
or reaches the repo's broker library. The service is handed a path and reads
JSON; knowing where a key lives is this script's job, not the service's.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from execd.schwab import Credential  # noqa: E402
from strader.settings import load_schwab_market  # noqa: E402


def _token_path(cfg: dict[str, str]) -> Path:
    raw = cfg.get("SCHWAB_TOKEN_PATH") or "./tokens/schwab_token.json"
    p = Path(raw)
    return p if p.is_absolute() else (REPO / raw).resolve()


def _write_atomic(path: Path, blob: bytes) -> None:
    """Write, fsync, rename, 0600 — the same discipline ``execd/vault.py`` uses,
    for the same reason: a half-written credential file is one the service
    refuses to start with, and this box has been OOM-killed mid-run before."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write(out: Path) -> int:
    cfg = load_schwab_market()
    tpath = _token_path(cfg)
    if not tpath.exists():
        print(f"no market token at {tpath}; run scripts/refresh_schwab_token.py first",
              file=sys.stderr)
        return 1
    try:
        wrapped = json.loads(tpath.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"the market token at {tpath} is not readable JSON: {exc}", file=sys.stderr)
        return 1
    payload = {"app": {"key": cfg["SCHWAB_API_KEY"], "secret": cfg["SCHWAB_APP_SECRET"]},
               "token": wrapped}
    try:
        cred = Credential.from_payload(payload)
    except ValueError as exc:
        print(f"the token file is not usable as a credential: {exc}", file=sys.stderr)
        return 1
    _write_atomic(out, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    print(f"wrote {out} (0600); the refresh token in it expires "
          f"{cred.refresh_wall.isoformat()}")
    print("re-authorise both apps in one sitting so the two walls stay on the same day")
    return 0


def check(out: Path) -> int:
    if not out.is_file():
        print(f"no market credential at {out}", file=sys.stderr)
        return 1
    mode = out.stat().st_mode & 0o777
    if mode != 0o600:
        # Reported, not repaired: a mode that drifted says something happened
        # here, and silently fixing it would hide that.
        print(f"warning: {out} is mode {mode:o}, not 600", file=sys.stderr)
    try:
        payload = json.loads(out.read_text(encoding="utf-8"))
        cred = Credential.from_payload(payload)
    except (OSError, ValueError) as exc:
        print(f"the market credential at {out} is unusable: {exc}", file=sys.stderr)
        return 1
    print(f"market credential opens; refresh token created {cred.created_at.isoformat()}, "
          f"wall {cred.refresh_wall.isoformat()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", required=True, type=Path,
                   help="where the service reads it (python -m execd --market-credential)")
    p.add_argument("--check", action="store_true",
                   help="read an existing file and report its wall")
    args = p.parse_args(argv)
    return check(args.out) if args.check else write(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
