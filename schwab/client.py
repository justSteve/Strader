"""
Schwab API client factory.

Gate: refuses to create a live client unless ~/.schwab_gate_key exists.
This file is never created by the agent — Steve creates it once on his machine.
Defense in depth behind the PreToolUse hook.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'lib' / 'schwab-py'))

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

    load_dotenv()

    api_key = os.getenv('SCHWAB_API_KEY')
    app_secret = os.getenv('SCHWAB_APP_SECRET')
    token_path = os.getenv('SCHWAB_TOKEN_PATH', './tokens/schwab_token.json')

    if not api_key or not app_secret:
        raise RuntimeError(
            "Missing SCHWAB_API_KEY or SCHWAB_APP_SECRET in .env"
        )

    if not Path(token_path).exists():
        raise RuntimeError(
            f"Token not found at {token_path}. "
            "Run schwab-generate-token.py to authenticate first."
        )

    return auth.client_from_token_file(token_path, api_key, app_secret)
