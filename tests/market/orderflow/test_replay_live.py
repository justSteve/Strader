"""replay_events moved out of the parity checker so the post-mortem can drive
a day's tape the live way without importing a script. [co-7kgte]"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_module_exports_replay_events():
    from market.orderflow import replay_live
    assert callable(replay_live.replay_events)


def test_checker_reexports_the_same_function():
    path = REPO_ROOT / "scripts" / "live_parity_check.py"
    spec = importlib.util.spec_from_file_location("live_parity_check_rl", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    from market.orderflow.replay_live import replay_events
    assert mod.replay_events is replay_events
