"""Serialize ManciniEmail to JSON for intraday re-emit."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .parser import ManciniEmail, Level, Slide, ReviewStep


def save(email: ManciniEmail, path: str | Path) -> None:
    Path(path).write_text(json.dumps(asdict(email), indent=2))


def load(path: str | Path) -> ManciniEmail:
    raw = json.loads(Path(path).read_text())
    return ManciniEmail(
        date=raw.get("date", ""),
        subject=raw.get("subject", ""),
        slides=[Slide(**s) for s in raw.get("slides", [])],
        review_steps=[ReviewStep(**r) for r in raw.get("review_steps", [])],
        support_levels=[Level(**l) for l in raw.get("support_levels", [])],
        resistance_levels=[Level(**l) for l in raw.get("resistance_levels", [])],
        key_levels=list(raw.get("key_levels", [])),
        basic_themes=raw.get("basic_themes", ""),
        other=raw.get("other", ""),
    )
