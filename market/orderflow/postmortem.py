"""Day post-mortem — what the recognizer called, what followed, what it missed. [co-7kgte]

Spec: docs/superpowers/specs/2026-08-19-day-postmortem-design.md.

Pure module. Takes Segments (one feeder run each: bars + events), returns a
day result dict, ledger rows and page markdown. Knows nothing about the desk,
cron, or which day is "today" — scripts/postmortem_day.py does. Every number
here is a rule with its threshold in ``Knobs``; nothing judges.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from dataclasses import asdict, dataclass, fields, replace
from datetime import date as _date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "postmortem.yaml"
LEDGER_ROOT = REPO_ROOT / "data" / "measurement" / "postmortem"


@dataclass(frozen=True)
class Knobs:
    """Every threshold on the page. Steve owns the numbers (config/postmortem.yaml)."""
    x_pts: float = 6.0            # leg size
    y_min: int = 15               # leg must reach x_pts inside this many minutes
    z_pts: float = 3.0            # "near a level" distance
    w_min: int = 10               # look-back for calls before a leg
    windows_min: tuple = (5, 15, 30)
    target_pts: float = 5.0       # first-touch grade
    dense_anchor_fires: int = 5
    late_confirm_bars: int = 2
    late_confirm_pts: float = 3.0
    breakout_pts: float = 10.0
    grid_density: float = 8.0     # confirms per 10 pts of session range
    history_days: int = 20
    lid_ticks: int = 8            # Addendum A3: a high this close under the level is a lid rejection
    lid_window_min: int = 30      # Addendum A3: look-back for lid rejections and window delta


def knobs_to_dict(k: Knobs) -> dict:
    d = asdict(k)
    d["windows_min"] = list(d["windows_min"])
    return d


def knobs_from_dict(d: dict) -> Knobs:
    d = dict(d)
    if "windows_min" in d:
        d["windows_min"] = tuple(int(w) for w in d["windows_min"])
    return Knobs(**d)


def load_knobs(path: Path = CONFIG_PATH) -> Knobs:
    """Knobs from yaml over the defaults. Unknown keys are an error — a typo
    that silently kept the default is the failure this guards."""
    if not path.exists():
        return Knobs()
    import yaml
    doc = yaml.safe_load(path.read_text()) or {}
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: expected a mapping")
    known = {f.name for f in fields(Knobs)}
    bad = sorted(set(doc) - known)
    if bad:
        raise ValueError(f"{path}: unknown knob(s) {bad}; known: {sorted(known)}")
    if "windows_min" in doc:
        doc["windows_min"] = tuple(int(w) for w in doc["windows_min"])
    return replace(Knobs(), **doc)
