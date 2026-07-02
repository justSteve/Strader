"""
Schwab API client factory.

Gate: refuses to create a live client unless ~/.schwab_gate_key exists.
This file is never created by the agent — Steve creates it once on his machine.
Defense in depth behind the PreToolUse hook.

`schwab` here is the upstream schwab-py library (editable-installed from
lib/schwab-py via pip). Pre-rename, this file lived at /schwab/client.py
and shadowed the upstream package — every consumer had to do sys.path
gymnastics to dodge the collision. After st-8cx renamed the local wrapper
to broker_schwab/, the import is unambiguous.
"""
from pathlib import Path

from schwab import auth

from strader.settings import load_schwab

GATE_KEY = Path.home() / '.schwab_gate_key'


def create_client():
    """Create an authenticated Schwab API client.

    Requires:
      1. ~/.schwab_gate_key file exists (Steve creates once, agent never touches)
      2. .env with SCHWAB_API_KEY, SCHWAB_APP_SECRET
      3. Valid token at SCHWAB_TOKEN_PATH
    """
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
