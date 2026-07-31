"""Repo-wide test isolation from Steve's live surfaces. [st-0x9]

Some of this codebase's outputs are not files — they are Steve's desktop. The
Mancini chain writes a browser page he keeps a tab parked on, publishes into
COO's steves-desk Trading window, and pushes the day's Pine payload to the
Windows clipboard so his morning routine is Ctrl+A / Ctrl+V. A test that
exercises those code paths reaches the real surfaces unless something stops it.

On 2026-07-30 that bill came due: three pytest runs during unrelated cron work
replaced the day's 60-level payload in Steve's clipboard with the two-line
test_run fixture, fifteen minutes of confusion before the open. test_run.py had
an autouse fixture guarding the desk paths for exactly this reason and simply
did not know about the fourth surface.

The guard lives HERE, at repo level, rather than in the one module that has been
bitten. A new test that calls runbook.mancini.run.main() inherits it instead of
rediscovering the hazard the same way.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_clipboard(monkeypatch):
    """Sever every path from the test suite to the real Windows clipboard.

    Patched at the emitter rather than at subprocess.run: the point is that no
    test EVER shells out to clip.exe, and a test that wants to assert on the
    push should assert against this recorder. Returns the list of payloads a
    test pushed, so a caller can `def test_x(_no_clipboard)` and inspect it.
    """
    pushed: list[str] = []

    def _fake_push(payload: str, **_kwargs) -> int:
        pushed.append(payload)
        return 0

    try:
        from runbook.mancini import payload_emitter
    except ImportError:  # pragma: no cover — emitter absent in a partial checkout
        return pushed

    monkeypatch.setattr(payload_emitter, "push_clipboard", _fake_push)
    # run.py does `from . import payload_emitter` inside the function body, so
    # patching the module attribute above is sufficient and there is no stale
    # from-import binding to chase. Guard the transport too, in case some other
    # caller reaches for it directly.
    monkeypatch.setattr(payload_emitter, "_default_run",
                        lambda cmd, text: pushed.append(text) or 0)
    return pushed
