"""The limits Steve removed stay removed. [co-8mb1z]

Steve, 2026-09-17 (st-bafu): "Let's just completely remove that complete
calculation. I don't need that level of hand holding." 2026-09-18 (st-644f):
"remove all aspects of that." 2026-09-24: "never ever place that kind of
restriction on me" (the clock rules), and the same day: "' one open
position, the $500 daily loss limit ' have a sub remove these also ... make
sure they are removed now and not restored in the future."

On 09-17 and 09-18 only the displays went and the bounds stayed. This file
fails if any of them comes back: as a field of ``Bounds``, as a key in the
shipped example, as a refusal keyed on them, or as a clock read in the
service. An old ``/etc`` file that still carries the keys must keep loading.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from execd.bounds import RETIRED_KEYS, Bounds, DayState, check_entry, load_bounds

from .conftest import CT, entry
from .test_bounds import GOOD_QUOTE

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "execd"
EXAMPLE = PACKAGE / "bounds.example.yaml"

#: Every key he removed. Never a bound again.
REMOVED = {"max_open_positions", "daily_loss_ceiling_usd", "max_attempts",
           "open_ct", "close_ct", "no_open_after_ct", "flat_by_close_ct",
           "weekdays_only"}

#: Anything shaped like them, so a rename cannot slip one back in.
SHAPED_LIKE = re.compile(r"loss|ceiling|headroom|attempt|open_positions|max_positions|"
                         r"_ct$|weekday|session|window|hour|flat_by|trades_per|per_day|daily")

#: Names in code that would mean the rule is back.
FORBIDDEN_NAMES = REMOVED | {"check_window", "check_risk_budget", "session_close",
                             "Budget", "CannotFund", "remaining_usd",
                             "budget_total_usd", "budget_attempts", "check_risk",
                             "flat_by_close", "flat_by_close_status", "WINDOW_EXEMPT_ROOTS",
                             "loss_headroom_usd", "attempts_left", "_open_risk_usd"}

#: Refusal names the removed rules used.
FORBIDDEN_BOUNDS = {"ceiling", "positions", "window", "same_contract"}


def modules() -> list[Path]:
    return sorted(p for p in PACKAGE.glob("**/*.py") if "__pycache__" not in p.parts)


def test_bounds_has_none_of_them():
    fields = set(Bounds.__dataclass_fields__)   # type: ignore[attr-defined]
    assert not fields & REMOVED
    assert [f for f in fields if SHAPED_LIKE.search(f)] == []


def test_the_shipped_example_has_none_of_them():
    keys = set(yaml.safe_load(EXAMPLE.read_text()) or {})
    assert not keys & REMOVED
    assert [k for k in keys if SHAPED_LIKE.search(k)] == []


def test_an_old_file_carrying_every_one_of_them_still_loads(tmp_path):
    assert REMOVED <= RETIRED_KEYS
    p = tmp_path / "bounds.yaml"
    p.write_text(yaml.safe_dump({"max_open_positions": 1, "daily_loss_ceiling_usd": 500.0,
                                 "max_attempts": 10, "open_ct": "08:30", "close_ct": "15:00",
                                 "no_open_after_ct": "14:50", "flat_by_close_ct": "14:55",
                                 "weekdays_only": True, "qty_cap": 1}))
    assert load_bounds(p) == Bounds()


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_code_names_a_removed_rule(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            found.add(node.attr)
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in FORBIDDEN_NAMES:
            found.add(node.name)
    assert not found, f"{path.name} names {sorted(found)}"


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_refusal_is_keyed_on_a_removed_rule(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "Refusal" and node.args
                and isinstance(node.args[0], ast.Constant)):
            assert node.args[0].value not in FORBIDDEN_BOUNDS, (path.name, node.args[0].value)


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_nothing_in_the_service_reads_the_hour_or_the_weekday(path: Path):
    """``orderform.next_weekday`` picks tomorrow's expiry for a 1DTE ticket; it
    refuses nothing and is the one allowed use."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("hour", "minute"):
            pytest.fail(f"{path.name} reads .{node.attr}")
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "weekday" and path.name != "orderform.py"):
            pytest.fail(f"{path.name} calls .weekday()")


@pytest.mark.parametrize("when", [datetime(2026, 8, 26, 16, 0, tzinfo=CT),
                                  datetime(2026, 8, 29, 3, 0, tzinfo=CT)])
def test_no_state_of_the_day_refuses_an_entry(when):
    state = DayState(open_positions=99, realized_loss_usd=10_000_000.0, attempts_used=999)
    assert check_entry(entry(), Bounds(), state, GOOD_QUOTE, when) is None


# ── outside execd: FD0 and the runbook (co-8mb1z, 2026-09-25) ────────────

def test_fd0_has_no_day_budget_and_no_attempts():
    """FD0's $100 day over two attempts is gone; each ticket's stop comes from
    its own stop loss, and nothing carries over from one ticket to the next."""
    import dataclasses
    import execd.compose as compose
    from strader.execution.fd0 import Fd0
    assert not hasattr(compose, "Budget") and not hasattr(compose, "CannotFund")
    assert [f.name for f in dataclasses.fields(compose.StopLoss)] == ["usd"]
    fields = {f.name for f in dataclasses.fields(Fd0)}
    assert not {"budget_total_usd", "budget_attempts"} & fields
    assert not hasattr(Fd0, "budget")


@pytest.mark.parametrize("path", [REPO / "strader" / "execution" / "fd0.py",
                                  REPO / "strader" / "execution" / "feed.py",
                                  REPO / "strader" / "intent" / "bracket.py",
                                  REPO / "strader" / "intent" / "session.py",
                                  REPO / "runbook" / "heartbeat.py"],
                         ids=lambda p: p.name)
def test_the_desk_and_the_runbook_name_no_removed_rule(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
            {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not found & FORBIDDEN_NAMES, sorted(found & FORBIDDEN_NAMES)


def test_the_runbook_risk_state_is_gone():
    """A daily loss halt, a position cap and per-strategy trade counts, reset
    at 08:25 every morning. Removed with its config."""
    assert not (REPO / "runbook" / "risk_state.py").exists()
    assert not (REPO / "config" / "risk.yaml").exists()
    wrapper = (REPO / "scripts" / "cron" / "preopen-heartbeat-wrapper.sh").read_text()
    assert "risk_state" not in wrapper
