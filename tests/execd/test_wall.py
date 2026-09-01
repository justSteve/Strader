"""The wall — nothing under ``execd/`` can reach the repo's broker library. [st-eznu]

The repo's copy of schwab-py is hobbled: every order call was removed from
``lib/schwab-py/schwab/client/base.py``, and a PreToolUse hook stops agent
shells from running anything that imports it (``tests/test_schwab_gate_hook.py``).
That arrangement is what makes it true that *nothing in this repo can transmit*.

``execd`` is the exception to that sentence, and the exception has to be
narrow, or the sentence stops being worth saying. So:

- The service speaks to the broker over plain HTTPS in stage 2 and never
  imports the hobbled library. The hook keeps its meaning unchanged.
- **There is still no transport at all** — no ``httpx``, no ``requests``, no
  socket. The only broker in the package is the mock. ``execd/vault.py`` is
  stage 2's first piece and carries no transport of its own; the Trader API
  client (``execd/schwab.py``) is what adds one, and the commit that lands it
  updates ``FORBIDDEN_TRANSPORTS`` below, deliberately and visibly.
- No module here names a **plaintext** credential file. The vault owns the
  encrypted store, which is the point of it; what must never appear is a path
  to a credential anyone can read.

Every claim above is asserted by reading the source and by watching what a
full import actually loads, because a claim about what code does not do is
exactly the kind that rots quietly.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "execd"

#: Import roots that would put a transmitting broker library inside the service.
FORBIDDEN_ROOTS = {"schwab", "broker_schwab", "schwab_py"}

#: The service has no transport yet. Stage 2's Trader API client adds exactly
#: one (httpx) in a new module and drops it from this set in the same commit —
#: deliberately and visibly, not as a side effect of an import someone added.
#: ``urllib`` and ``http`` are the whole stdlib roots, not just the submodules:
#: the audit (finding 13, st-kh0l) showed ``from http import client`` arrives
#: at the AST as root ``http`` and sailed past a set that only named
#: ``http.client``, and ``urllib.request`` was not named at all.
FORBIDDEN_TRANSPORTS = {"httpx", "requests", "urllib3", "socket", "aiohttp",
                        "urllib", "http", "http.client", "ftplib", "telnetlib",
                        "xmlrpc"}


def modules() -> list[Path]:
    # Recursive on purpose: a module in a subdirectory is still inside the
    # wall. The non-recursive glob was finding 13 of the 2026-08-30 audit —
    # a subpackage would have escaped every static check in this file.
    return sorted(p for p in PACKAGE.glob("**/*.py") if "__pycache__" not in p.parts)


def imported_roots(path: Path) -> set[str]:
    """Every module this file imports, by top-level name, from the AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
                roots.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:          # a relative import stays inside execd
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
                roots.add(node.module)
    return roots


def test_the_package_has_modules_to_check():
    """A wall test that silently checked nothing would pass forever."""
    names = {p.name for p in modules()}
    assert {"__init__.py", "service.py", "bounds.py", "broker.py"} <= names


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_imports_the_hobbled_broker_library(path: Path):
    assert not (imported_roots(path) & FORBIDDEN_ROOTS), (
        f"{path.name} imports the repo's broker library. execd speaks to the "
        f"broker over HTTPS in stage 2 and never through schwab-py — that is "
        f"what keeps the import hook meaningful."
    )


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_the_service_still_has_no_transport(path: Path):
    found = imported_roots(path) & FORBIDDEN_TRANSPORTS
    assert not found, (
        f"{path.name} imports {sorted(found)}. The service runs against "
        f"MockBroker only; the Schwab transport is st-w2nw and lands with this "
        f"list updated in the same commit."
    )


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_names_a_credential_file(path: Path):
    source = path.read_text(encoding="utf-8")
    for needle in ("schwab_token", "token.json", ".schwab_fire_key", "api_key",
                   "app_secret", "client_secret"):
        assert needle not in source, (
            f"{path.name} names {needle!r}. The credential reaches this service "
            f"decrypted in memory at stage 2 and has no path on disk here."
        )


def test_importing_the_whole_package_loads_no_broker_library():
    """The static check above reads the source; this one watches what actually
    loads, so a dynamic import (``importlib``, a late ``__getattr__``) cannot
    slip past it."""
    # The module list is derived from the files on disk, not maintained by
    # hand: the audit found the hand-kept list had drifted (vault.py was never
    # probed — finding 13). A module added tomorrow is probed tomorrow.
    names = sorted(
        "execd" + str(p.relative_to(PACKAGE))[:-3].replace("/", ".").replace("\\", ".")
        .replace("__init__", "").rstrip(".")
        for p in modules()
    )
    module_names = sorted({("execd." + n.removeprefix("execd")).rstrip(".").replace("..", ".")
                           for n in names})
    probe = (
        "import importlib, sys, json\n"
        f"for name in {module_names!r}:\n"
        "    importlib.import_module(name)\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
        f"{sorted(FORBIDDEN_ROOTS)!r})))\n"
    )
    out = subprocess.run([sys.executable, "-c", probe], cwd=REPO,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("[]"), (
        f"importing execd loaded a broker library: {out.stdout.strip()}"
    )


def test_the_mock_is_the_only_broker_in_stage_one():
    from execd import broker

    concrete = [name for name, obj in vars(broker).items()
                if isinstance(obj, type) and name.endswith("Broker")
                and name not in ("Broker",)]
    assert concrete == ["MockBroker"]


def test_the_service_refuses_to_start_without_the_mock_flag(tmp_path):
    """``python -m execd`` with no broker must not start quietly."""
    from execd.__main__ import main

    assert main(["--state-dir", str(tmp_path)]) == 2


def test_the_service_refuses_to_bind_anything_but_the_loopback(tmp_path):
    from execd.__main__ import main

    assert main(["--mock", "--host", "0.0.0.0", "--state-dir", str(tmp_path)]) == 2
