"""Every script under scripts/ must parse. [st-r17u]

On 2026-09-12 the execd stage-3 commit (5db5a88) left a stray `else:` in the
Schwab token-health heartbeat script. It failed to parse, corpus_daily's 06:30
run logged the SyntaxError as a WARNING and carried on, and the heartbeat
silently stopped rewriting for two sessions until the 09-14 tap-in found the
state file 45h stale. Nothing in pytest imported the script, so nothing caught
it.

This test parses each scripts/*.py with `ast` — no imports, no network, no
Schwab reach — so a syntax break in any operator script fails the suite.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((REPO_ROOT / "scripts").rglob("*.py"))
TOKEN_HEALTH = REPO_ROOT / "scripts" / ("schwab_token" + "_health.py")


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_script_parses(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_token_health_is_covered() -> None:
    """The script that broke is in the set this test walks."""
    assert TOKEN_HEALTH in SCRIPTS


def test_detects_the_09_12_shape(tmp_path: Path) -> None:
    """The exact break: an assignment wedged between an `if` block and its `else`."""
    broken = tmp_path / "broken.py"
    broken.write_text("if x:\n    y = 1\nz = 2\nelse:\n    y = 0\n", encoding="utf-8")
    with pytest.raises(SyntaxError):
        ast.parse(broken.read_text(encoding="utf-8"), filename=str(broken))
