"""Append-only JSONL commentary store. [co-7lyf]

Each trading day's forward-looking commentary lands in one file:

    runbook/mancini/commentary/YYYY-MM-DD.jsonl

One structured commentary item per line. Append-only and git-tracked: trivially
inspectable, diff-able, and resilient to any service outage (vs. routing into a
memory service). Each line carries a machine-evaluable ``trigger`` so the
intraday highlighter (#10, co-3qrw) can later ask "does live price/time/regime
satisfy any trigger right now?" without re-parsing prose.

At a few notes a day no database is needed; if volume ever justifies it the same
per-line schema promotes to SQLite unchanged.

Design ref: spec section 7.3.
"""
from __future__ import annotations

import json
from datetime import date as date_cls
from pathlib import Path
from typing import Any, Iterable

from .schema import Commentary

# Default store root: runbook/mancini/commentary/ next to this file.
DEFAULT_STORE_ROOT = Path(__file__).resolve().parent / "commentary"


def _day_path(day: str, store_root: Path) -> Path:
    return store_root / f"{day}.jsonl"


def _identity(record: dict[str, Any]) -> str:
    """What makes two stored commentary rows the same note. [st-psoj]

    The note's own content — text plus the trigger it fires on — and nothing
    from the envelope. Two extractions of the same paragraph on the same day are
    the same note however many times the parse ran.
    """
    return json.dumps(
        {"text": record.get("text", ""), "trigger": record.get("trigger")},
        sort_keys=True, ensure_ascii=False,
    )


def append(
    items: Iterable[Commentary],
    day: str,
    *,
    instrument: str = "",
    ingested_at: str = "",
    store_root: Path | str | None = None,
) -> Path:
    """Append commentary items to the day's JSONL file, skipping ones it holds.

    Returns the path written. Creates the store directory if needed. Each line
    is a JSON object: the commentary fields plus ``date``/``instrument``/
    ``ingested_at`` envelope metadata so a single line is self-describing.

    Appending is **idempotent** [st-psoj]. A re-parse of a day the store already
    holds — a correction run of /mancini-parse, most often — used to write every
    item a second time, and three days in the store were doubled and one tripled
    before anyone looked. `parsed/<day>.json` is written with replace semantics
    and stayed correct throughout, so the two artifacts silently disagreed about
    how many forward notes a day had. Genuinely new items still append, which is
    what makes this a dedupe and not a truncate.

    Identity is ``(text, trigger)``. Deliberately NOT the whole record: a
    re-parse stamps a fresh ``ingested_at``, so including the envelope would
    make every item look new and restore the bug.
    """
    root = Path(store_root) if store_root is not None else DEFAULT_STORE_ROOT
    root.mkdir(parents=True, exist_ok=True)
    path = _day_path(day, root)

    seen = {_identity(rec) for rec in load(day, store_root=root)}

    lines: list[str] = []
    for item in items:
        record: dict[str, Any] = {
            "date": day,
            "instrument": instrument,
            "ingested_at": ingested_at,
            **item.to_dict(),
        }
        ident = _identity(record)
        if ident in seen:
            continue
        seen.add(ident)
        # sort_keys for deterministic, diff-friendly output.
        lines.append(json.dumps(record, sort_keys=True, ensure_ascii=False))

    if lines:
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return path


def load(day: str, *, store_root: Path | str | None = None) -> list[dict[str, Any]]:
    """Load all commentary records for a day. Returns raw dicts (envelope +
    commentary fields). Missing file -> empty list."""
    root = Path(store_root) if store_root is not None else DEFAULT_STORE_ROOT
    path = _day_path(day, root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def today_key() -> str:
    """US/Central trading-day key, matching the corpus convention.

    Imported lazily so the store module has no hard dependency on the market
    package for the common (explicit-day) path.
    """
    try:
        from market.corpus.paths import central_date

        return central_date().isoformat()
    except Exception:
        return date_cls.today().isoformat()
