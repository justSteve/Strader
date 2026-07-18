"""Schwab OAuth token-age health assessment. [st-e2f / st-096 AC4]

Schwab *refresh* tokens hard-expire 7 days after they are minted, regardless of
use. When that wall is hit the next API call fails with ``invalid_grant`` and the
feed goes dark. On 2026-07-08 exactly this happened and nothing noticed until the
data was needed — a silent death, the same failure class as the letter trigger.

This module is the *proactive* guard: a pure, side-effect-free assessor that
answers "will this token still be alive tomorrow?" so a daily heartbeat can alarm
*before* expiry rather than discovering it after a pull already failed. It asserts
the OUTCOME (token still fresh) instead of the PROCESS (a pull happened to work).

Design anchor — ``creation_timestamp``:
    schwab-py stamps ``creation_timestamp`` once at mint and, per its own
    ``TokenMetadata`` docstring, "this timestamp does not change when the token is
    updated" (access-token refreshes preserve it; only a full manual re-auth
    resets it). So it is the correct anchor for the 7-day refresh-token clock —
    file mtime is NOT (a refresh rewrites the file without resetting the wall).

It also catches the *defective grant* failure mode observed 2026-07-17: a token
whose grant came back with no ``refresh_token`` (the 181-byte file). Such a token
cannot be refreshed and dies at the end of its ~30-minute access-token life, so it
is treated as an immediate alarm regardless of age.

Pure by design: no logging, no file writes, no network. The CLI
(``scripts/schwab_token_health.py``) owns all I/O, alerting, and transports so this
core stays trivially unit-testable with an injected ``now``.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# Schwab refresh-token lifetime. Fixed 7 days from mint, not extended by use.
REFRESH_TOKEN_LIFETIME_S: int = 7 * 24 * 3600

# Default lead thresholds, expressed in *days remaining* before the 7-day wall.
# The scheduler that drives this runs weekday mornings only (COO corpus-daily
# wrapper), so a 2-day first-warning survives a Fri-mint / weekend-gap and still
# leaves a weekday check in the token's final 24h. Tune via the CLI.
DEFAULT_WARN_DAYS_LEFT: float = 2.0
DEFAULT_CRITICAL_DAYS_LEFT: float = 1.0

# Status values, ordered by escalating concern. ``ok`` is the only healthy one.
STATUS_OK = "ok"
STATUS_WARN = "warn"          # aging — re-auth soon
STATUS_CRITICAL = "critical"  # <=1 day left — re-auth now
STATUS_EXPIRED = "expired"    # past the 7-day wall — feed already dead/dying
STATUS_DEFECTIVE = "defective"  # grant has no refresh_token (181-byte failure)
STATUS_MISSING = "missing"    # token file absent
STATUS_MALFORMED = "malformed"  # unreadable / missing creation_timestamp

# Statuses that require operator action (anything but a fresh, healthy token).
ACTIONABLE = frozenset(
    {STATUS_WARN, STATUS_CRITICAL, STATUS_EXPIRED,
     STATUS_DEFECTIVE, STATUS_MISSING, STATUS_MALFORMED}
)


@dataclass(frozen=True)
class TokenHealth:
    """Result of assessing a Schwab token file. Serializable via ``to_dict``."""
    status: str
    message: str
    path: str
    has_refresh_token: bool
    creation_ts: int | None      # epoch seconds, None when unknown
    age_seconds: int | None      # None when unknown
    days_left: float | None      # to the 7-day wall; None when unknown
    reauth_by_ts: int | None     # creation_ts + 7d; None when unknown
    reauth_by_iso: str | None    # UTC ISO of reauth_by_ts

    @property
    def actionable(self) -> bool:
        return self.status in ACTIONABLE

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def to_dict(self) -> dict:
        d = asdict(self)
        d["actionable"] = self.actionable
        return d


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def assess_token(
    token_path: str | Path,
    now: int | None = None,
    warn_days_left: float = DEFAULT_WARN_DAYS_LEFT,
    critical_days_left: float = DEFAULT_CRITICAL_DAYS_LEFT,
) -> TokenHealth:
    """Assess a Schwab token file's freshness. Pure: reads the file, returns a
    verdict, never raises for the ordinary failure modes (missing/malformed are
    returned as statuses, not exceptions).

    :param token_path: path to schwab_token.json (schwab-py metadata-wrapped shape:
        ``{"creation_timestamp": <epoch>, "token": {..., "refresh_token": ...}}``).
    :param now: epoch seconds to evaluate against; defaults to real time. Injected
        by tests to exercise every age branch deterministically.
    :param warn_days_left / critical_days_left: escalation thresholds in days
        remaining before the 7-day wall.
    """
    import time

    now = int(time.time()) if now is None else int(now)
    path = Path(token_path)
    spath = str(path)

    if not path.exists():
        return TokenHealth(
            status=STATUS_MISSING,
            message=f"Schwab token file not found at {spath}. Run scripts/refresh_schwab_token.py.",
            path=spath, has_refresh_token=False, creation_ts=None,
            age_seconds=None, days_left=None, reauth_by_ts=None, reauth_by_iso=None,
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        return TokenHealth(
            status=STATUS_MALFORMED,
            message=f"Schwab token file at {spath} is unreadable ({type(e).__name__}). Re-mint via scripts/refresh_schwab_token.py.",
            path=spath, has_refresh_token=False, creation_ts=None,
            age_seconds=None, days_left=None, reauth_by_ts=None, reauth_by_iso=None,
        )

    creation_ts = raw.get("creation_timestamp")
    inner = raw.get("token") or {}
    refresh = inner.get("refresh_token")
    has_refresh = bool(refresh)

    if not isinstance(creation_ts, (int, float)):
        return TokenHealth(
            status=STATUS_MALFORMED,
            message=f"Schwab token at {spath} has no numeric 'creation_timestamp'. Re-mint via scripts/refresh_schwab_token.py.",
            path=spath, has_refresh_token=has_refresh, creation_ts=None,
            age_seconds=None, days_left=None, reauth_by_ts=None, reauth_by_iso=None,
        )

    creation_ts = int(creation_ts)
    age_seconds = now - creation_ts
    reauth_by_ts = creation_ts + REFRESH_TOKEN_LIFETIME_S
    days_left = (reauth_by_ts - now) / 86400.0
    reauth_by_iso = _iso(reauth_by_ts)

    # A grant with no refresh_token cannot be refreshed — it dies at the end of
    # its short access-token life no matter how "young" it looks. Alarm now.
    if not has_refresh:
        return TokenHealth(
            status=STATUS_DEFECTIVE,
            message=(f"Schwab token at {spath} has NO refresh_token (defective grant — "
                     f"the 181-byte failure). It cannot refresh and will die within the "
                     f"hour. Re-mint via scripts/refresh_schwab_token.py."),
            path=spath, has_refresh_token=False, creation_ts=creation_ts,
            age_seconds=age_seconds, days_left=days_left,
            reauth_by_ts=reauth_by_ts, reauth_by_iso=reauth_by_iso,
        )

    if days_left <= 0:
        status = STATUS_EXPIRED
        message = (f"Schwab refresh token EXPIRED {abs(days_left):.1f}d ago "
                   f"(minted {_iso(creation_ts)}, wall {reauth_by_iso}). Feed is dead. "
                   f"Re-auth now: scripts/refresh_schwab_token.py.")
    elif days_left <= critical_days_left:
        status = STATUS_CRITICAL
        message = (f"Schwab refresh token expires in {days_left:.1f}d ({reauth_by_iso}). "
                   f"Re-auth today: scripts/refresh_schwab_token.py.")
    elif days_left <= warn_days_left:
        status = STATUS_WARN
        message = (f"Schwab refresh token expires in {days_left:.1f}d ({reauth_by_iso}). "
                   f"Re-auth soon: scripts/refresh_schwab_token.py.")
    else:
        status = STATUS_OK
        message = f"Schwab refresh token healthy — {days_left:.1f}d left (wall {reauth_by_iso})."

    return TokenHealth(
        status=status, message=message, path=spath, has_refresh_token=True,
        creation_ts=creation_ts, age_seconds=age_seconds, days_left=days_left,
        reauth_by_ts=reauth_by_ts, reauth_by_iso=reauth_by_iso,
    )
