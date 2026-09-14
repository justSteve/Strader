"""One engine: ``strader.execution.compose`` is ``execd.compose``. [st-k6gl]"""

from __future__ import annotations

import importlib

import execd.compose as engine

# `strader.execution` re-exports the compose() function under the same name, so
# attribute access would hand back the function; ask sys.modules for the module.
shim = importlib.import_module("strader.execution.compose")


def test_every_public_name_is_the_same_object():
    assert shim.__all__ == engine.__all__
    for name in engine.__all__:
        assert getattr(shim, name) is getattr(engine, name), name


def test_the_private_names_tests_use_are_carried():
    assert shim._round_limit_up is engine._round_limit_up
    assert shim.PREMIUM_TICK_PTS is engine.PREMIUM_TICK_PTS


def test_the_engine_stays_stdlib_only():
    """The install copies execd/ alone; the engine must need nothing else."""
    import ast
    from pathlib import Path
    src = Path(engine.__file__).read_text(encoding="utf-8")
    roots = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= {"logging", "math", "statistics", "dataclasses", "datetime", "typing",
                     "__future__"}, roots
