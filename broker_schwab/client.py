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
import os
from pathlib import Path

from schwab import auth
from dotenv import load_dotenv

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

    # Load .env from the project root, not cwd — so the client works whether
    # a script is launched from Strader root, /, or anywhere else.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    api_key = os.getenv('SCHWAB_API_KEY')
    app_secret = os.getenv('SCHWAB_APP_SECRET')
    token_path_raw = os.getenv('SCHWAB_TOKEN_PATH', './tokens/schwab_token.json')

    if not api_key or not app_secret:
        raise RuntimeError(
            "Missing SCHWAB_API_KEY or SCHWAB_APP_SECRET in .env"
        )

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
