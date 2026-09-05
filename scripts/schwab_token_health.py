#!/usr/bin/env python3
"""Schwab token-age heartbeat — proactive alarm before the 7-day refresh wall. [st-e2f / st-096 AC4]

Runs the pure assessor (strader/schwab_token.py) against the live token file and
owns every side effect: a heartbeat state file written EVERY run (so the check's
own liveness is observable), and — only when the token needs attention — a durable
health-log line, a loud stderr banner, a best-effort idempotent bead, and a
best-effort operator push. Assert the outcome, not the process.

Rides the existing daily cadence: corpus_daily.py invokes this unconditionally, so
no new cron is needed. It can also be run standalone at any time:

    .venv/bin/python scripts/schwab_token_health.py            # check + alarm if needed
    .venv/bin/python scripts/schwab_token_health.py --json     # machine-readable verdict
    .venv/bin/python scripts/schwab_token_health.py --force-alert   # exercise transports
    .venv/bin/python scripts/schwab_token_health.py --no-bead --no-push  # quiet check

Exit codes:
    0  token healthy (ok)
    1  action needed (warn / critical / expired / defective / missing / malformed)
    2  internal error (this checker itself failed)

Recovery when it alarms: run scripts/refresh_schwab_token.py (interactive browser
OAuth, zero-relay — operator pastes the redirect URL directly; ~30s code life).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from strader.schwab_token import assess_token, TokenHealth  # noqa: E402
from strader.config import ConfigError  # noqa: E402
from strader.settings import (load_schwab_market,  # noqa: E402
                              load_schwab_trading)

# Health/heartbeat live next to the corpus, unified with corpus_daily.py's stream.
CORPUS_ROOT = REPO_ROOT / "data" / "corpus"          # == market.corpus.paths.CORPUS_ROOT
HEALTH_LOG = CORPUS_ROOT / "_health.jsonl"           # shared append-only alert audit
HEARTBEAT = CORPUS_ROOT / "_schwab_token_health.json"  # last-check state (this checker)

# Idempotency sentinel: one open re-auth bead at a time, matched by this marker.
BEAD_SENTINEL = "[schwab-token-reauth]"
BD_BIN = "/usr/local/bin/bd"
CLAUDECLAW_ENV = Path("/root/projects/claudeclaw/.env")
CLAUDECLAW_URL = "http://localhost:3141/api/chat/send"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def _resolve_token_path() -> Path:
    """Same resolution refresh_schwab_token.py uses: SCHWAB_TOKEN_PATH from the
    validated config, resolved relative to the repo root when not absolute.

    This is app 1, the market-data app — the one every reader and cron uses."""
    cfg = load_schwab_market()
    return _resolve(cfg.get("SCHWAB_TOKEN_PATH") or "./tokens/schwab_token.json")


def _trading_token_state() -> tuple[Path | None, str]:
    """App 2's token path, with a word for why there is none.

    Three states, and they are not the same thing. No credentials means the
    second registration has not reached the vault yet. Credentials but no token
    means they have, and nobody has done the browser login that mints the first
    grant — which is a thing to go and do, not a thing to wait for. Neither is
    a fault, and saying "not configured" for both would tell Steve the wrong one
    (st-p9mx)."""
    try:
        cfg = load_schwab_trading()
    except ConfigError:
        return None, "no credentials in the vault"
    path = _resolve(cfg.get("SCHWAB_TRADING_TOKEN_PATH")
                    or "./tokens/schwab_trading_token.json")
    if not path.exists():
        return None, "credentials present, no grant yet — run reauthAccount"
    return path, "ok"


def _write_heartbeat(health: TokenHealth) -> None:
    """Overwrite the heartbeat state file on every run. A stale heartbeat is itself
    a signal that the checker stopped running."""
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    record = {"checked_at": _utc_now_iso(), **health.to_dict()}
    tmp = HEARTBEAT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(HEARTBEAT)  # atomic


def _append_health(record: dict) -> None:
    HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with HEALTH_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _emit_banner(health: TokenHealth) -> None:
    banner = (f"\n{'!' * 72}\n"
              f"SCHWAB TOKEN ALERT [{health.status}]: {health.message}\n"
              f"{'!' * 72}")
    print(banner, file=sys.stderr)


def _open_reauth_bead_exists() -> bool | None:
    """True/False if we could determine it; None if bd was unavailable."""
    try:
        out = subprocess.run(
            [BD_BIN, "list", "--status", "open,in_progress", "--json"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=20,
        )
        if out.returncode != 0:
            return None
        issues = json.loads(out.stdout or "[]")
        for it in issues:
            if BEAD_SENTINEL in (it.get("title") or ""):
                return True
        return False
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None


def _create_reauth_bead(health: TokenHealth) -> str:
    """Best-effort idempotent bead so the reminder surfaces in Strader's ready
    queue / tap-in. Returns a short status string for logging; never raises."""
    exists = _open_reauth_bead_exists()
    if exists is None:
        return "bead: skipped (bd unavailable)"
    if exists:
        return "bead: skipped (open re-auth bead already exists)"
    title = f"{BEAD_SENTINEL} Re-auth Schwab token — {health.status} ({health.message.split('.')[0]})"
    desc = (f"Proactive alarm from scripts/schwab_token_health.py.\n\n{health.message}\n\n"
            f"Recovery: run scripts/refresh_schwab_token.py (interactive OAuth, zero-relay).\n"
            f"re-auth by: {health.reauth_by_iso}\n\n"
            f"## Acceptance Criteria\n- Fresh token minted with refresh_token present; "
            f"heartbeat status returns to ok.")
    try:
        out = subprocess.run(
            [BD_BIN, "create", "--type", "task", "--priority", "1",
             "--title", title, "--description", desc],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=20,
        )
        if out.returncode == 0:
            return f"bead: created ({(out.stdout or '').strip().splitlines()[0] if out.stdout else 'ok'})"
        return f"bead: create failed rc={out.returncode}"
    except (OSError, subprocess.SubprocessError) as e:
        return f"bead: create errored ({type(e).__name__})"


def _push_relay(health: TokenHealth) -> str:
    """Best-effort operator push via ClaudeClaw (Telegram). No-op when the service
    or its token is absent — never blocks the alarm. Returns a log string."""
    try:
        if not CLAUDECLAW_ENV.exists():
            return "push: skipped (claudeclaw .env absent)"
        token = ""
        for line in CLAUDECLAW_ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("DASHBOARD_TOKEN"):
                token = line.split("=", 1)[1].strip()
                break
        if not token:
            return "push: skipped (no DASHBOARD_TOKEN)"
        msg = f"⚠ Schwab token {health.status}: {health.message}"
        payload = json.dumps({"message": msg})
        out = subprocess.run(
            ["curl", "-s", "-m", "5", "-X", "POST",
             f"{CLAUDECLAW_URL}?token={token}",
             "-H", "Content-Type: application/json", "-d", payload],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and '"ok":true' in (out.stdout or "").replace(" ", ""):
            return "push: sent"
        return "push: not delivered (claudeclaw down/unreachable)"
    except (OSError, subprocess.SubprocessError) as e:
        return f"push: errored ({type(e).__name__})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Schwab token-age heartbeat alarm [st-e2f]")
    ap.add_argument("--warn-days-left", type=float, default=None,
                    help="Days-remaining threshold for a WARN alarm (default 2.0)")
    ap.add_argument("--critical-days-left", type=float, default=None,
                    help="Days-remaining threshold for a CRITICAL alarm (default 1.0)")
    ap.add_argument("--json", action="store_true", help="Emit the verdict as JSON to stdout")
    ap.add_argument("--no-bead", action="store_true", help="Do not file a re-auth bead")
    ap.add_argument("--no-push", action="store_true", help="Do not attempt the relay push")
    ap.add_argument("--force-alert", action="store_true",
                    help="Run the alert path even when status is ok (transport smoke test)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    from strader.schwab_token import DEFAULT_WARN_DAYS_LEFT, DEFAULT_CRITICAL_DAYS_LEFT
    warn = args.warn_days_left if args.warn_days_left is not None else DEFAULT_WARN_DAYS_LEFT
    crit = args.critical_days_left if args.critical_days_left is not None else DEFAULT_CRITICAL_DAYS_LEFT

    try:
        token_path = _resolve_token_path()
        health = assess_token(token_path, warn_days_left=warn, critical_days_left=crit)
        # Two apps mean two grants and two independent seven-day walls
        # (st-p9mx). The verdict is the NEARER wall, because that is the one
        # that ends a trading day, and the discipline is to re-authorise both
        # in one sitting so they land on the same day anyway.
        trading_path, trading_note = _trading_token_state()
        trading_health = None
        if trading_path is not None:
            trading_health = assess_token(trading_path, warn_days_left=warn,
                                          critical_days_left=crit)
            if (trading_health.days_left is not None and health.days_left is not None
                    and trading_health.days_left < health.days_left):
                health = trading_health
            elif not trading_health.ok and health.ok:
                health = trading_health
        _write_heartbeat(health)
    except Exception as e:  # this checker itself failed — infra error, exit 2
        print(f"[schwab-token-health] INTERNAL ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if args.json:
        out = health.to_dict()
        if trading_health is not None:
            out["apps"] = {"market": assess_token(
                               token_path, warn_days_left=warn,
                               critical_days_left=crit).to_dict(),
                           "trading": trading_health.to_dict()}
        else:
            out["trading_note"] = trading_note
        print(json.dumps(out, indent=2))
    else:
        print(f"schwab token: {health.status.upper()} — {health.message}")
        if trading_health is not None:
            print("  (nearer of two walls: app 1 market data, app 2 trading — "
                  "re-authorise both in one sitting)")
        else:
            print(f"  (app 2, Accounts and Trading: {trading_note})")

    if health.actionable or args.force_alert:
        _emit_banner(health)
        _append_health({"ts": _utc_now_iso(), "level": "alert", "kind": "schwab_token_age",
                        "status": health.status, "message": health.message,
                        "days_left": health.days_left, "reauth_by": health.reauth_by_iso})
        notes = []
        if not args.no_bead:
            notes.append(_create_reauth_bead(health))
        if not args.no_push:
            notes.append(_push_relay(health))
        for n in notes:
            print(f"[schwab-token-health] {n}", file=sys.stderr)

    return 0 if health.ok else 1


if __name__ == "__main__":
    sys.exit(main())
