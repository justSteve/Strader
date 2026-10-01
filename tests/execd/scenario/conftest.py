"""Fixtures and the two modes of the scenario suite. [st-ug1h]

**Fast** (the default, part of the normal ``tests/execd`` run): every named
sequence, the 09-30 seed cases, the page flows, a handful of generated tapes
and a slice of the recorded half hour.

**Wide** (``--scenario-wide``, or ``EXECD_SCENARIO_WIDE=1`` in the
environment): hundreds of generated tapes with gaps, stale stretches and
resting entries, and the whole recorded 13:15–13:45 CT tape with an entry
every few minutes. Tests marked ``scenario_wide`` run only here; the
``walk_seed`` parameter widens from ``FAST_SEEDS`` to ``WIDE_SEEDS``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import pytest

from .harness import Scenario
from .tape import Tape

FAST_SEEDS = 12
WIDE_SEEDS = 400


def wide_mode(config: pytest.Config) -> bool:
    try:
        opt = bool(config.getoption("--scenario-wide"))
    except ValueError:          # the option is registered in tests/conftest.py
        opt = False
    return opt or os.environ.get("EXECD_SCENARIO_WIDE") == "1"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "scenario_wide: execd scenario harness, wide mode only "
                                       "(--scenario-wide) [st-ug1h]")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if wide_mode(config):
        return
    skip = pytest.mark.skip(reason="wide mode only — run with --scenario-wide")
    for item in items:
        if "scenario_wide" in item.keywords:
            item.add_marker(skip)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "walk_seed" in metafunc.fixturenames:
        n = WIDE_SEEDS if wide_mode(metafunc.config) else FAST_SEEDS
        metafunc.parametrize("walk_seed", range(n))


@pytest.fixture
def make(tmp_path: Path) -> Callable[..., Scenario]:
    """``make(tape, **kw)`` → a :class:`Scenario` in its own state directory."""
    count = {"n": 0}

    def build(tape: Tape, **kw: Any) -> Scenario:
        count["n"] += 1
        return Scenario(tape, tmp_path / f"scn{count['n']}", **kw)
    return build
