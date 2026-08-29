"""The audit lane's tests. [st-h0xx]

The lane's code lives under ``footprint-icm/bin`` (a hyphenated folder, so not
a package); tests import it by path, so the path goes on at import time —
collection imports the test modules before any fixture runs. Every test that
writes a run folder does so under a temporary ``ICM_STATE_DIR``: the contract
address ``/var/moo/state/footprint-icm`` is never touched by the suite.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "footprint-icm" / "bin"

# Before any lane module is imported: a throwaway state root, and the bin
# folder importable.
os.environ["ICM_STATE_DIR"] = tempfile.mkdtemp(prefix="icm-state-")
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """A fresh run root for one test; ``common.STATE`` is re-pointed too,
    because the module read the env var at import time."""
    import common
    monkeypatch.setattr(common, "STATE", tmp_path / "state")
    return tmp_path / "state"
