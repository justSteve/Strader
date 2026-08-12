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
    g) Script checks the SHAPE of the written grant, then makes a cheap
       market-data API call. Both must pass before it reports success.

CADENCE: weekly. Schwab refresh tokens are deliberately short-lived.

WHY TWO CHECKS AND NOT ONE [st-r1b5]. A live API call proves the 30-minute
*access* token works. It cannot prove the *refresh* token exists, and the
refresh token is the entire point of this weekly ritual. On 2026-08-12 a
mistyped redirect URL produced a defective grant — 28-char access token, no
refresh_token, the 181-byte file — that returned HTTP 200 from
marketdata/v1/markets while being dead on arrival: it would have expired 30
minutes later, 2.5 hours before the open, with the operator holding a green
check. Shape is therefore asserted separately, against the same assessor the
daily health check uses.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add Strader root for `broker_schwab.*` / `strader.*` imports. `schwab`
# resolves to the upstream hobbled fork via site-packages — no sys.path tricks
# needed since the local wrapper was renamed schwab/ → broker_schwab/ (st-8cx).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schwab import auth as schwab_auth  # noqa: E402

from strader.config import ConfigError  # noqa: E402
from strader.schwab_token import STATUS_OK, assess_token  # noqa: E402
from strader.settings import load_schwab_auth  # noqa: E402


GATE_KEY = Path.home() / ".schwab_gate_key"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: How many timestamped backups to keep. Ten weekly re-auths is roughly two
#: months of history — enough to reach back past a bad patch, small enough that
#: the directory stays readable.
KEEP_BACKUPS = 10


class DefectiveGrant(Exception):
    """The written token is structurally unusable — no API call changes that.

    Distinct from a verify-call failure on purpose: a 401 from a probe endpoint
    is ambiguous (see ``_verify_client``), whereas a grant with no refresh_token
    has no reading under which it is fine.
    """

    def __init__(self, health):
        super().__init__(health.message)
        self.health = health


def _backup(token_path: Path) -> Path | None:
    """Snapshot the existing token to a *timestamped* sibling.

    Timestamped rather than a single ``.bak`` because of st-r1b5: on 2026-08-12
    a defective grant overwrote the one backup slot, and only a same-minute
    retry kept a good token in existence at all. A run that mints garbage must
    not be able to destroy the last good token.
    """
    if not token_path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = token_path.with_suffix(token_path.suffix + f".bak-{stamp}")
    # Second-resolution stamps collide when a failed re-auth is retried
    # immediately, and a colliding copy would silently destroy the earlier
    # backup — the exact hazard this function exists to remove. Disambiguate
    # instead of overwriting. The suffix sorts after the bare stamp, so name
    # order stays time order for _prune_backups.
    dup = 1
    while bak.exists():
        bak = token_path.with_suffix(token_path.suffix + f".bak-{stamp}.{dup}")
        dup += 1
    shutil.copy2(token_path, bak)
    _prune_backups(token_path)
    return bak


def _prune_backups(token_path: Path, keep: int = KEEP_BACKUPS) -> None:
    """Keep the newest ``keep`` timestamped backups; drop the rest.

    The stamp is lexically sortable (UTC ``%Y%m%dT%H%M%SZ``), so name order is
    time order — no stat calls, and no dependence on mtimes that a copy or a
    restore would have rewritten.
    """
    pattern = token_path.name + ".bak-*"
    olds = sorted(token_path.parent.glob(pattern))
    for stale in olds[:-keep] if len(olds) > keep else []:
        try:
            stale.unlink()
        except OSError:
            pass  # a backup we cannot prune is not worth failing a re-auth over


def _restore(bak: Path | None, token_path: Path) -> None:
    if bak and bak.exists():
        shutil.copy2(bak, token_path)


def _stash(token_path: Path, suffix: str) -> Path | None:
    """Copy the current token aside for the operator. None if the copy fails."""
    dest = token_path.with_suffix(token_path.suffix + suffix)
    try:
        shutil.copy2(token_path, dest)
        return dest
    except OSError:
        return None


def _grant_gate(token_path: Path):
    """Assert the WRITTEN token is a usable grant, not merely a working one.

    ``assess_token`` already owns the verdict for every bad shape, including the
    one seen here — ``STATUS_DEFECTIVE``, commented in that module as "the
    181-byte failure" (first observed 2026-07-17). Re-auth is the one moment
    this can be caught while the operator is still sitting in front of it, so
    this is where the assessor gets called. Raises ``DefectiveGrant`` on any
    verdict other than ok.
    """
    health = assess_token(token_path)
    if health.status != STATUS_OK:
        raise DefectiveGrant(health)
    return health


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

    try:
        cfg = load_schwab_auth()
    except ConfigError as e:
        print(f"[ENV] {e}", file=sys.stderr)
        return 2
    api_key = cfg["SCHWAB_API_KEY"]
    app_secret = cfg["SCHWAB_APP_SECRET"]
    callback_url = cfg["SCHWAB_CALLBACK_URL"]
    token_path_str = cfg.get("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")

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

    # Shape before behaviour. This check is free, deterministic, and catches the
    # failure the live call provably cannot see [st-r1b5].
    try:
        health = _grant_gate(token_path)
    except DefectiveGrant as e:
        rejected = _stash(token_path, ".rejected")
        # Unlike a verify-call failure, this one is unambiguous, so leaving the
        # bad token in place would be actively harmful: the collectors would
        # pick it up and die mid-session. Put the previous token back, provided
        # it is itself better than what just arrived.
        restored = False
        if bak:
            prior = assess_token(bak)
            if prior.has_refresh_token:
                _restore(bak, token_path)
                restored = True

        print(f"\n[FATAL] {e}", file=sys.stderr)
        print("[FATAL] The OAuth exchange returned a token that CANNOT be refreshed.",
              file=sys.stderr)
        print("[FATAL] It would work for about 30 minutes and then go silent.",
              file=sys.stderr)
        print("[FATAL] Most likely cause: a mistyped or truncated redirect URL at",
              file=sys.stderr)
        print("[FATAL] the 'Redirect URL>' prompt. Re-run and paste the ENTIRE URL.",
              file=sys.stderr)
        if rejected:
            print(f"[FATAL] rejected token kept for inspection: {rejected}",
                  file=sys.stderr)
        if restored:
            print(f"[FATAL] previous token RESTORED to {token_path} "
                  f"({prior.message})", file=sys.stderr)
        elif bak:
            print(f"[FATAL] previous token is also unusable ({prior.status}); "
                  f"left at {bak}", file=sys.stderr)
            print("[FATAL] There is no good token on disk. Re-run this script.",
                  file=sys.stderr)
        else:
            print("[FATAL] No previous token existed to fall back to. Re-run "
                  "this script.", file=sys.stderr)
        return 5

    try:
        _verify_client(client)
    except Exception as e:
        # IMPORTANT: do NOT auto-restore on verify failure. The freshly
        # issued token may still be valid for the actual use case (market
        # data) even if our verify endpoint refused it. Stash the new
        # token aside, keep .bak intact, and let the operator decide.
        rescue_path = _stash(token_path, ".new")
        print(f"[WARN] verify failed: {e}", file=sys.stderr)
        print(f"[WARN] the grant itself is well-formed (refresh token present, "
              f"wall {health.reauth_by_iso}) — only the probe call failed.",
              file=sys.stderr)
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
    print(f"✓ Grant is complete — refresh token present, "
          f"{health.days_left:.1f}d to the wall")
    print(f"✓ Live API call to marketdata/v1 get_market_hours returned 200")
    if bak:
        print(f"  (backup retained at {bak.name} — pruned to the last "
              f"{KEEP_BACKUPS})")
    print()
    print(f"Re-auth by {health.reauth_by_iso} — the Schwab refresh token hard-")
    print("expires 7 days after mint whether or not it is used.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
