#!/usr/bin/env python3
"""
Bullet-proof Schwab OAuth token regeneration.

Schwab refresh tokens expire after 7 days. When that happens, the next API
call fails with `invalid_grant`. This script walks you through the manual
copy-paste OAuth flow and writes a fresh token to SCHWAB_TOKEN_PATH.

USAGE:
    .venv/bin/python scripts/refresh_schwab_token.py

REQUIREMENTS:
    1. `touch ~/.schwab_gate_key` to authorize agent-driven auth flows
    2. .env with SCHWAB_API_KEY, SCHWAB_APP_SECRET,
       SCHWAB_CALLBACK_URL, SCHWAB_TOKEN_PATH

THE FLOW:
    a) Script prints an authorization URL.
    b) You open it in any browser (host browser is fine; WSL doesn't
       need to launch it).
    c) Log in to Schwab. Approve the app.
    d) Schwab redirects to your callback URL with a `code` parameter.
       The page won't actually load (callback is 127.0.0.1) — that's
       expected.
    e) Copy the full URL from the address bar.
    f) Paste it back to this script's prompt.
    g) Script verifies the new token by making a cheap API call.

CADENCE: weekly. Schwab refresh tokens are deliberately short-lived.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Add Strader root for `broker_schwab.*` imports. `schwab` resolves to the
# upstream hobbled fork via site-packages — no sys.path tricks needed since
# the local wrapper was renamed schwab/ → broker_schwab/ (st-8cx).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schwab import auth as schwab_auth  # noqa: E402


GATE_KEY = Path.home() / ".schwab_gate_key"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.split("#", 1)[0].strip()
        if key and val and key not in os.environ:
            os.environ[key] = val


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing {name} in .env (or shell environment).")
    return val


def _backup(token_path: Path) -> Path | None:
    """Copy existing token to .bak. Returns backup path or None if no original."""
    if not token_path.exists():
        return None
    bak = token_path.with_suffix(token_path.suffix + ".bak")
    shutil.copy2(token_path, bak)
    return bak


def _restore(bak: Path | None, token_path: Path) -> None:
    if bak and bak.exists():
        shutil.copy2(bak, token_path)


def _verify_client(client) -> None:
    """Make one cheap MARKET-DATA API call to confirm the new token works.

    Critical: this MUST be a market-data endpoint (marketdata/v1/...) and
    NOT a trader endpoint (trader/v1/...). A token provisioned for
    market-data-only will 401 on trader endpoints even when it is fully
    valid for chains, quotes, and bars — the actual use case of this
    project. Picking the wrong verify endpoint caused a real outage
    2026-05-20: a freshly-issued valid token was restored over because
    the verify check probed /trader/v1/userPreference and 401'd.
    """
    # schwab-py enforces enums by default — pass the enum, not the string.
    from schwab.client.base import BaseClient
    resp = client.get_market_hours([BaseClient.MarketHours.Market.EQUITY])
    resp.raise_for_status()
    return None


def main() -> int:
    if not GATE_KEY.exists():
        print(f"[GATE] {GATE_KEY} not found.", file=sys.stderr)
        print(f"       Authorize this run with:  touch {GATE_KEY}",
              file=sys.stderr)
        return 1

    _load_dotenv()
    try:
        api_key = _require_env("SCHWAB_API_KEY")
        app_secret = _require_env("SCHWAB_APP_SECRET")
        callback_url = _require_env("SCHWAB_CALLBACK_URL")
        token_path_str = os.environ.get(
            "SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    except RuntimeError as e:
        print(f"[ENV] {e}", file=sys.stderr)
        return 2

    token_path = (PROJECT_ROOT / token_path_str).resolve() \
        if not Path(token_path_str).is_absolute() \
        else Path(token_path_str)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Token path:    {token_path}")
    print(f"Callback URL:  {callback_url}")
    print()
    print("─" * 70)
    print("STARTING SCHWAB OAUTH FLOW")
    print("─" * 70)
    print("schwab-py will print an authorization URL. Open it in your browser,")
    print("log in to Schwab, approve the app, then copy the *full* redirect URL")
    print("(starts with your callback URL, has a `code=` parameter) and paste")
    print("it back below.")
    print()
    print("The redirect page WILL NOT actually load — the callback is 127.0.0.1")
    print("with no listener. That's expected. Just grab the URL from your")
    print("address bar.")
    print()

    bak = _backup(token_path)
    if bak:
        print(f"[backup] existing token saved to {bak.name}")
    print()

    try:
        client = schwab_auth.client_from_manual_flow(
            api_key=api_key,
            app_secret=app_secret,
            callback_url=callback_url,
            token_path=str(token_path),
        )
    except KeyboardInterrupt:
        print("\n[abort] interrupted; restoring backup", file=sys.stderr)
        _restore(bak, token_path)
        return 130
    except Exception as e:
        print(f"\n[ERROR] OAuth flow failed: {e}", file=sys.stderr)
        print("[restore] reverting to previous token", file=sys.stderr)
        _restore(bak, token_path)
        return 3

    print()
    print("─" * 70)
    print("VERIFYING NEW TOKEN")
    print("─" * 70)
    try:
        _verify_client(client)
    except Exception as e:
        # IMPORTANT: do NOT auto-restore on verify failure. The freshly
        # issued token may still be valid for the actual use case (market
        # data) even if our verify endpoint refused it. Stash the new
        # token aside, keep .bak intact, and let the operator decide.
        rescue_path = token_path.with_suffix(token_path.suffix + ".new")
        try:
            shutil.copy2(token_path, rescue_path)
        except Exception:
            pass
        print(f"[WARN] verify failed: {e}", file=sys.stderr)
        print(f"[WARN] new token preserved at:  {rescue_path}", file=sys.stderr)
        print(f"[WARN] previous token preserved at:  {bak}",
              file=sys.stderr) if bak else None
        print(f"[WARN] active token at:  {token_path}", file=sys.stderr)
        print(f"[WARN] If your downstream use case is market-data and verify",
              file=sys.stderr)
        print(f"[WARN] hit a trader-namespace 401, the new token is probably",
              file=sys.stderr)
        print(f"[WARN] fine. Try it before restoring the backup.",
              file=sys.stderr)
        return 4

    print(f"✓ New token written to {token_path}")
    print(f"✓ Verified by API call to get_user_preferences")
    if bak:
        print(f"  (backup retained at {bak.name} — delete when satisfied)")
    print()
    print("Refresh again in 7 days (or when you see `invalid_grant` errors).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
