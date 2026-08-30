"""Arming — the three states, and the asymmetry between getting in and out. [st-eznu]

Steve's control model (design §3, from intent v2): *code owns tempo inside the
bounds, he owns the kill switch, the ceiling holds when he is not watching.*

Three states:

``LOCKED``
    No credential in memory. This is the state after every restart, which is
    the point: a service that comes back from a reboot armed would be a service
    that arms itself. Nothing transmits from here — not even an exit, because
    there is nothing to transmit *with*.
``ARMED``
    Steve entered the passphrase on the page. Armed until the session close he
    chose, or until he stands down. Only here do entries transmit.
``STOOD_DOWN``
    He is finished for the day but the credential is still in memory. No new
    positions; exits still work, because a stood-down service that could not
    close an open position would be worse than no service.

Crossed with that is the **STOP file** — one ``touch`` from anywhere, including
Steve's phone. It blocks entries in every state and blocks no exit in any.

The rule the whole module exists to hold: *nothing here may ever refuse an
exit for a risk reason.* Window, ceiling, STOP, stand-down — all of them stop
him taking on risk; none of them may strand him in it. The one thing that
refuses an exit is LOCKED, and that is a statement about capability, not policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .bounds import CT, Refusal


class ArmState(str, Enum):
    LOCKED = "LOCKED"
    ARMED = "ARMED"
    STOOD_DOWN = "STOOD_DOWN"


class Locked(RuntimeError):
    """Raised when something asks for the credential and there is none."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Arming:
    """The service's arming state. One per process; not thread-safe by design —
    the service serialises calls through it."""

    kill_file: Path
    clock: Callable[[], datetime] = _utcnow

    def __post_init__(self) -> None:
        self.kill_file = Path(self.kill_file)
        self._credential: Any | None = None
        self._until: datetime | None = None
        self._stood_down: bool = False
        self._unlocked_at: datetime | None = None

    # ── transitions ──────────────────────────────────────────────────────
    def unlock(self, credential: Any, until: datetime) -> ArmState:
        """Steve entered the passphrase. Page-only: there is no API route here,
        and ``tests/execd/test_api.py`` asserts that."""
        if credential is None:
            raise ValueError("unlock needs a credential")
        if until.tzinfo is None:
            raise ValueError("unlock 'until' must be timezone-aware")
        self._credential = credential
        self._until = until
        self._stood_down = False
        self._unlocked_at = self.clock()
        return self.state

    def stand_down(self) -> ArmState:
        """Done for the day. The credential stays in memory so exits and
        flatten still work; nothing new opens."""
        self._stood_down = True
        return self.state

    def lock(self) -> ArmState:
        """Forget the credential. After this only a passphrase brings it back."""
        self._credential = None
        self._until = None
        self._stood_down = False
        self._unlocked_at = None
        return self.state

    # ── the kill file ────────────────────────────────────────────────────
    def stop(self) -> bool:
        """Turn STOP on. Idempotent, and it must work from a phone with one
        request, so it takes no argument and cannot fail on an existing file."""
        self.kill_file.parent.mkdir(parents=True, exist_ok=True)
        self.kill_file.touch()
        return True

    def resume(self) -> bool:
        """Clear STOP. Page-only, like unlock — an agent must not be able to
        undo Steve's kill switch."""
        try:
            self.kill_file.unlink()
        except FileNotFoundError:
            pass
        return True

    @property
    def killed(self) -> bool:
        return self.kill_file.exists()

    # ── state ────────────────────────────────────────────────────────────
    @property
    def state(self) -> ArmState:
        if self._credential is None:
            return ArmState.LOCKED
        if self._stood_down:
            return ArmState.STOOD_DOWN
        if self._until is not None and self.clock() >= self._until:
            # Expiry stands down rather than locking: the credential stays
            # available to close whatever is still open at the bell.
            return ArmState.STOOD_DOWN
        return ArmState.ARMED

    @property
    def expires_at(self) -> datetime | None:
        return self._until

    def credential(self) -> Any:
        if self._credential is None:
            raise Locked("the service is locked — Steve has not entered the passphrase")
        return self._credential

    # ── permissions ──────────────────────────────────────────────────────
    def permits_entry(self) -> Refusal | None:
        state = self.state
        if state is ArmState.LOCKED:
            return Refusal("armed", "the service is locked — no credential in memory")
        if state is ArmState.STOOD_DOWN:
            expired = self._until is not None and self.clock() >= self._until
            return Refusal(
                "armed",
                "the session has ended — arming expired" if expired
                else "stood down for the day — nothing new opens",
            )
        if self.killed:
            return Refusal("stop", "STOP is on — no new positions until it is cleared")
        return None

    def permits_exit(self) -> Refusal | None:
        """Only LOCKED refuses. Read the module docstring before changing this."""
        if self._credential is None:
            return Refusal("armed", "the service is locked — nothing to transmit with")
        return None

    # ── reporting ────────────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        until = self._until
        return {
            "state": self.state.value,
            "killed": self.killed,
            "kill_file": str(self.kill_file),
            "unlocked_at": self._unlocked_at.isoformat() if self._unlocked_at else None,
            "expires_at": until.isoformat() if until else None,
            "expires_at_ct": until.astimezone(CT).strftime("%H:%M CT") if until else None,
            "permits_entry": self.permits_entry() is None,
            "permits_exit": self.permits_exit() is None,
        }
