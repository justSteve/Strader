"""The FD0 engine lives in ``execd/compose.py`` since 2026-09-14 [st-k6gl].

This path is kept so every importer — the dictation desk, the FD0 state
machine, the feed, the tests — keeps working unchanged, and so there is one
engine: the installed execution service serves an order form that prices a
ticket with the same code the desk uses, and the install carries only
``execd/``. Nothing is defined here; every name is the ``execd.compose``
object itself, so ``isinstance`` and identity hold across the two paths.
"""

from execd.compose import *  # noqa: F401,F403 — the public surface, by design
from execd.compose import (  # noqa: F401 — names tests reach for by hand
    PREMIUM_TICK_PTS, __all__, _round_limit_up, log,
)
