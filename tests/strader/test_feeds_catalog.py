"""The strader.feeds catalog must not lie about what this repo carries. [st-c6ii]

`available()` reports a module that cannot be imported as False, by design: an
optional dep (databento, schwab) missing from an environment is information, not
an error. That design has a cost — a catalogued module that was DELETED reports
False in exactly the same way, so the catalog can go stale and the health map
keeps looking healthy-ish forever.

It went stale on 2026-09-06: the legacy prune removed `market/ingest/mancini.py`
(nothing consumed `session_from_mancini` anywhere in the tree) and the entry
stayed. This test is the difference between "the dep is not installed here" and
"the entry names a file that does not exist", which is the distinction
`available()` structurally cannot make.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from strader.feeds import CARRIED, available, carried

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name,dotted", sorted(CARRIED.items()))
def test_every_catalogued_module_exists_on_disk(name, dotted):
    """Existence, not importability — the one thing available() cannot tell you."""
    rel = dotted.replace(".", "/")
    module = REPO / f"{rel}.py"
    package = REPO / rel / "__init__.py"
    assert module.exists() or package.exists(), (
        f"catalog entry {name!r} names {dotted}, which is not on disk. "
        f"available() would report it False and read as a missing optional dep. "
        f"Fix the catalog or restore the module."
    )


def test_the_catalog_is_not_empty():
    """A catalog that emptied itself would pass every parametrized case above."""
    assert len(CARRIED) >= 8, f"catalog shrank to {len(CARRIED)} entries"


def test_available_reports_one_bool_per_entry():
    status = available()
    assert set(status) == set(CARRIED)
    assert all(isinstance(v, bool) for v in status.values())


def test_an_unknown_name_raises_with_the_known_set():
    """The error has to be actionable — a bare KeyError is not."""
    with pytest.raises(KeyError) as e:
        carried("ingest_mancini")          # the entry pruned 2026-09-06
    assert "unknown carried feed" in str(e.value)
    assert "ingest_databento" in str(e.value), "the message must list what IS known"


def test_importing_the_seam_is_cheap():
    """The lazy contract: importing strader.feeds must not drag in databento."""
    import sys

    for heavy in ("databento", "schwab"):
        if heavy in sys.modules:
            pytest.skip(f"{heavy} already imported by another test in this process")
    spec = importlib.util.find_spec("strader.feeds")
    assert spec is not None
    assert "databento" not in sys.modules
