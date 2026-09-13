"""
Schwab API client factory.

TWO PATHS, ONE CALLER (stage 3 of the live execution service, st-p8k8).

The readers in this repo — the schwab-stages snapshots, the premarket
profile, the Mancini overnight section, the gauges, the FD0 feed — all call
``create_client()`` and then four ``schwab-py`` read methods on what it
returns. Since stage 3 the one holder of the market token on this box is the
execution service (``execd``), so:

1. **The service path.** When ``execd`` answers on its loopback door, this
   returns :class:`broker_schwab.execd_client.ExecdClient`, which offers the
   same four methods and speaks plain HTTP to ``127.0.0.1:8778`` with no
   credential, no gate key and no ``schwab`` import. The service passes the
   three market-data resources through and nothing else.
2. **The token-file path.** When the service does not answer, this does what
   it did before stage 3: the hobbled ``schwab-py`` library over the token
   file named in ``.env``, gated by ``~/.schwab_gate_key``. It stays until the
   plaintext token is retired, which is the last step of the migration and
   happens only after the service has been seen answering the morning jobs.

``STRADER_MARKET_DATA=execd`` forces the first and fails loudly if the service
is down; ``=legacy`` forces the second; unset or ``auto`` probes. Which path
was taken is logged at INFO on ``broker_schwab``.

`schwab` here is the upstream schwab-py library (editable-installed from
lib/schwab-py via pip). Pre-rename, this file lived at /schwab/client.py
and shadowed the upstream package — every consumer had to do sys.path
gymnastics to dodge the collision. After st-8cx renamed the local wrapper
to broker_schwab/, the import is unambiguous.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("broker_schwab")

GATE_KEY = Path.home() / '.schwab_gate_key'

#: ``execd`` (require the service), ``legacy`` (never probe), ``auto``.
MODE_ENV = "STRADER_MARKET_DATA"


def create_client():
    """Create a read client: the execution service when it answers, else the
    authenticated ``schwab-py`` client over the token file.

    The service path requires only that ``execd`` be up. The token-file path
    requires:
      1. ~/.schwab_gate_key file exists (Steve creates once, agent never touches)
      2. .env with SCHWAB_API_KEY, SCHWAB_APP_SECRET
      3. Valid token at SCHWAB_TOKEN_PATH
    """
    mode = os.environ.get(MODE_ENV, "auto").strip().lower() or "auto"
    if mode not in ("auto", "execd", "legacy"):
        raise RuntimeError(f"{MODE_ENV}={mode!r} is not one of auto, execd, legacy")

    if mode != "legacy":
        from broker_schwab.execd_client import EXECD_URL, ExecdClient, service_status
        status = service_status(EXECD_URL)
        if status is not None:
            log.info("market data via execd at %s (service %s)", EXECD_URL,
                     status.get("sha", "?"))
            return ExecdClient(EXECD_URL)
        if mode == "execd":
            raise RuntimeError(
                f"{MODE_ENV}=execd but the execution service does not answer at "
                f"{EXECD_URL}; is strader-execd.service running?")
        log.info("execd not answering at %s; market data via the token file", EXECD_URL)

    return _legacy_client()


def _legacy_client():
    """The pre-stage-3 client: schwab-py over the token file, behind the gate key."""
    from schwab import auth

    from strader.settings import load_schwab

    if not GATE_KEY.exists():
        raise RuntimeError(
            "SCHWAB GATE: ~/.schwab_gate_key not found. "
            "Live API access requires Steve to create this file: "
            "touch ~/.schwab_gate_key"
        )

    # Authoritative, validated config: the project-root .env wins over any
    # polluted process env (the 2026-06-30 invalid_client incident, where a
    # VS Code-injected inline comment poisoned the client_id), and a malformed
    # key fails fast with a clear message instead of reaching Schwab.
    cfg = load_schwab()

    api_key = cfg['SCHWAB_API_KEY']
    app_secret = cfg['SCHWAB_APP_SECRET']
    token_path_raw = cfg.get('SCHWAB_TOKEN_PATH', './tokens/schwab_token.json')

    # Resolve token path against project root rather than cwd.
    project_root = Path(__file__).resolve().parent.parent
    token_path = Path(token_path_raw)
    if not token_path.is_absolute():
        token_path = (project_root / token_path_raw).resolve()

    if not token_path.exists():
        raise RuntimeError(
            f"Token not found at {token_path}. "
            "Run scripts/refresh_schwab_token.py to authenticate first."
        )

    return auth.client_from_token_file(str(token_path), api_key, app_secret)
