#!/usr/bin/env python3
"""
Bullet-proof Schwab OAuth token regeneration.

Schwab refresh tokens expire after 7 days. When that happens, the next API
call fails with `invalid_grant`. This script walks you through the manual
copy-paste OAuth flow and writes a fresh token.

TWO APPS (st-p9mx). Steve has two Schwab registrations and each carries its own
grant with its own seven-day wall. Without --trading this mints app 1's, the
market-data app; with --trading it mints app 2's, the Accounts and Trading app
that execd sends orders through. Each is verified against the endpoint family
it exists for — probing the wrong family is the 2026-05-20 outage, in which a
perfectly good market-data token was restored over because the check hit
/trader/v1. Re-authorise BOTH in one sitting: a still-valid grant costs nothing
to renew, and renewing them together keeps the two walls on the same day rather
than giving Steve two re-auth days a week.

USAGE:
    .venv/bin/python scripts/refresh_schwab_token.py              # app 1, market data
    .venv/bin/python scripts/refresh_schwab_token.py --trading    # app 2, trading

REQUIREMENTS:
    1. `touch ~/.schwab_gate_key` to authorize agent-driven auth flows
    2. .env pointing at the credential vault file, which holds
       SCHWAB_API_KEY, SCHWAB_APP_SECRET and — for --trading —
       SCHWAB_TRADING_API_KEY, SCHWAB_TRADING_APP_SECRET;
       .env itself carries SCHWAB_CALLBACK_URL, SCHWAB_TOKEN_PATH and
       optionally SCHWAB_TRADING_CALLBACK_URL, SCHWAB_TRADING_TOKEN_PATH

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

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add Strader root for `broker_schwab.*` / `strader.*` imports. `schwab`
# resolves to the upstream hobbled fork via site-packages — no sys.path tricks
# needed since the local wrapper was renamed schwab/ → broker_schwab/ (st-8cx).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# NOTE: `schwab` is imported INSIDE main(), at its single use site, not here.
# It is the
# only symbol in this file that needs the broker lib, and importing it at
# module level made the whole module — grant gate, backup hygiene, token
# assessment — unimportable anywhere the lib is absent. CI is exactly such a
# box (it installs neither databento nor schwab-py, by design), so
# tests/scripts/test_refresh_schwab_token.py could not even be collected and
# master was red from 2026-08-12. Nothing about the re-auth flow changes: the
# lib is imported before it is used, on the one path that uses it. [st-v55j]

from strader.config import ConfigError  # noqa: E402
from strader.schwab_token import STATUS_OK, assess_token  # noqa: E402
from strader.settings import (load_schwab_auth,  # noqa: E402
                              load_schwab_trading_auth)


GATE_KEY = Path.home() / ".schwab_gate_key"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: How many timestamped backups may exist WHILE re-auths are failing. On a
#: successful re-auth every backup is swept (``_sweep_rescues``): the grant it
#: holds is superseded, and a superseded Schwab grant is still a live refresh
#: token for up to seven days — a credential nobody tracks, sitting in the
#: tree. Credential estate convention 2026-08-25, point 3 (co-4q6cg). Two is
#: enough to survive st-r1b5's failure (a defective mint overwriting the only
#: backup) without growing a pile.
KEEP_BACKUPS = 2


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


def _prune_copies(token_path: Path, kind: str, keep: int = KEEP_BACKUPS) -> None:
    """Keep the newest ``keep`` copies of one ``kind`` (``bak`` / ``new`` /
    ``rejected``); drop the rest.

    The stamp is lexically sortable (UTC ``%Y%m%dT%H%M%SZ``), so name order is
    time order — no stat calls, and no dependence on mtimes that a copy or a
    restore would have rewritten. The glob is anchored on ``.<kind>-`` so it can
    never reach the live token or a sibling of another kind.
    """
    olds = sorted(token_path.parent.glob(f"{token_path.name}.{kind}-*"))
    for stale in olds[:-keep] if len(olds) > keep else []:
        try:
            stale.unlink()
        except OSError:
            pass  # a backup we cannot prune is not worth failing a re-auth over


def _prune_backups(token_path: Path, keep: int = KEEP_BACKUPS) -> None:
    """Keep the newest ``keep`` timestamped backups; drop the rest."""
    _prune_copies(token_path, "bak", keep)


def _restore(bak: Path | None, token_path: Path) -> None:
    if bak and bak.exists():
        shutil.copy2(bak, token_path)


def _stash(token_path: Path, suffix: str) -> Path | None:
    """Copy the current token aside for the operator, under a TIMESTAMPED name.
    None if the copy fails.

    Timestamped for the same reason ``_backup`` is (st-r1b5): a bare ``.new`` or
    ``.rejected`` is a single slot, so a second failure silently destroys the
    evidence from the first.

    It also stops the copy reading as an atomic-write temp. The 2026-08-15
    enterprise audit (sweep J finding F10, co-03ojd.7) found a three-month-old
    ``schwab_token.json.new`` holding a full 140-char refresh token and
    classified it as "a leftover from an atomic-write path (`.new` → rename)",
    recommending the writer ``rm -f`` its temp on every path. It is not a temp —
    it is the rescue copy this function makes when the post-mint verify call
    fails, and deleting it on the failure path would remove the operator's only
    copy of a grant that is probably fine. The name was the misleading part, so
    the name is what changed; the superseded copies are swept on the SUCCESS
    path instead (``_sweep_rescues``).
    """
    if not token_path.exists():
        return None
    kind = suffix.lstrip(".")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = token_path.with_suffix(f"{token_path.suffix}.{kind}-{stamp}")
    dup = 1
    while dest.exists():
        dest = token_path.with_suffix(f"{token_path.suffix}.{kind}-{stamp}.{dup}")
        dup += 1
    try:
        shutil.copy2(token_path, dest)
    except OSError:
        return None
    _prune_copies(token_path, kind)
    return dest


def _shred(path: Path) -> None:
    """Overwrite then unlink. Best effort — a journaling filesystem may keep a
    copy of the old blocks — but it is strictly better than unlink alone for a
    file whose whole content is a credential."""
    try:
        size = path.stat().st_size
        with open(path, "r+b") as fh:
            fh.write(b"\0" * size)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass
    path.unlink()


def _sweep_rescues(token_path: Path) -> list[Path]:
    """Remove superseded copies once a re-auth has SUCCEEDED.

    Two kinds are swept. A ``.new`` rescue holds the grant from an earlier
    attempt whose probe call failed. A ``.bak`` holds the grant that was live
    before this run — the restore path if THIS run had failed. The moment a run
    mints a grant that passes both the shape gate and the live call, every such
    copy is superseded by definition, and a superseded Schwab grant is still a
    usable refresh token for up to seven days: a credential nobody tracks,
    sitting at 0600 in the tokens directory. Rotation hygiene (credential estate
    convention 2026-08-25, point 3) says shred it here, on the success path —
    the only place where "this copy is definitely stale" is a fact rather than a
    guess. Rejected copies are deliberately NOT swept: those are forensic
    evidence of a defective mint (st-r1b5), hold no working grant, and are few.
    """
    removed: list[Path] = []
    stale = sorted(token_path.parent.glob(f"{token_path.name}.new-*"))
    stale += sorted(token_path.parent.glob(f"{token_path.name}.bak-*"))
    legacy = token_path.with_suffix(token_path.suffix + ".new")  # pre-2026-08-16 name
    if legacy.exists():
        stale.append(legacy)
    for path in stale:
        try:
            _shred(path)
            removed.append(path)
        except OSError:
            pass  # a copy we cannot remove is not worth failing a good re-auth
    return removed


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


def _verify_trading_grant(token_path: Path) -> None:
    """One cheap TRADER API call, for app 2 (st-p9mx).

    The mirror image of :func:`_verify_client`, and it must be a trader
    endpoint for exactly the reason that one must be a market-data endpoint: a
    probe against the wrong family proves nothing about the grant just written.
    App 2 exists to reach ``/trader/v1``; if that family answers, the grant is
    good, and if it does not, no market-data 200 would redeem it.

    It goes over ``httpx`` rather than through the client above because the
    repo's schwab-py fork is hobbled — the account and order methods are
    physically removed (``lib/schwab-py`` DEFENSE NOTE), so the library cannot
    make this call at all. Read-only, and it prints no part of the token.
    """
    import httpx

    wrapped = json.loads(Path(token_path).read_text(encoding="utf-8"))
    access = (wrapped.get("token") or {}).get("access_token")
    if not access:
        raise RuntimeError("the written grant carries no access token")
    r = httpx.get("https://api.schwabapi.com/trader/v1/accounts/accountNumbers",
                  headers={"Authorization": f"Bearer {access}",
                           "Accept": "application/json"}, timeout=15.0)
    if r.status_code != 200:
        raise RuntimeError(f"trader/v1 accountNumbers answered HTTP {r.status_code} "
                           f"— the Accounts and Trading product is not on this app")
    return None


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


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    args.add_argument("--trading", action="store_true",
                      help="mint the TRADING app's grant (app 2, Accounts and "
                           "Trading) instead of the market-data app's")
    opts = args.parse_args(argv)
    trading = opts.trading

    if not GATE_KEY.exists():
        print(f"[GATE] {GATE_KEY} not found.", file=sys.stderr)
        print(f"       Authorize this run with:  touch {GATE_KEY}",
              file=sys.stderr)
        return 1

    try:
        cfg = load_schwab_trading_auth() if trading else load_schwab_auth()
    except ConfigError as e:
        print(f"[ENV] {e}", file=sys.stderr)
        return 2
    if trading:
        api_key = cfg["SCHWAB_TRADING_API_KEY"]
        app_secret = cfg["SCHWAB_TRADING_APP_SECRET"]
        callback_url = cfg["SCHWAB_TRADING_CALLBACK_URL"]
        token_path_str = cfg.get("SCHWAB_TRADING_TOKEN_PATH",
                                 "./tokens/schwab_trading_token.json")
    else:
        api_key = cfg["SCHWAB_API_KEY"]
        app_secret = cfg["SCHWAB_APP_SECRET"]
        callback_url = cfg["SCHWAB_CALLBACK_URL"]
        token_path_str = cfg.get("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")

    print(f"App:           {'trading (app 2)' if trading else 'market data (app 1)'}")

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

    from schwab import auth as schwab_auth  # deferred: see the note by the imports

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
        # Each app is probed against the family it exists for. Probing the
        # wrong one is the 2026-05-20 outage: a good market-data token was
        # restored over because the check hit /trader/v1 and 401'd.
        if trading:
            _verify_trading_grant(token_path)
        else:
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

    # Both gates passed, so any rescue copy from an earlier verify failure is a
    # superseded credential. Sweep it here — the success path is the only place
    # where "this copy is definitely stale" is a fact rather than a guess.
    swept = _sweep_rescues(token_path)

    print(f"✓ New token written to {token_path}")
    print(f"✓ Grant is complete — refresh token present, "
          f"{health.days_left:.1f}d to the wall")
    print("✓ Live API call to trader/v1 accountNumbers returned 200" if trading
          else "✓ Live API call to marketdata/v1 get_market_hours returned 200")
    for path in swept:
        print(f"  (shredded superseded copy {path.name})")
    print()
    print(f"Re-auth by {health.reauth_by_iso} — the Schwab refresh token hard-")
    print("expires 7 days after mint whether or not it is used.")
    print("Re-authorise BOTH apps in this sitting (the other one is "
          f"{'market data: run without --trading' if trading else 'trading: run with --trading'})"
          " so the two walls stay on the same day.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
