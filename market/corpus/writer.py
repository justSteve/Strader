"""JSONL append + manifest update for the three-stream corpus. [st-1yp]

Each record is a typed dict shaped as:

    {
        "ts_pull_utc":  "2026-05-22T14:30:00Z",   # when the script polled
        "stream":       "schwab" | "gexbot" | "databento_opra",
        "provenance":   {                          # what was pulled
            "endpoints":  ["..."],
            "ts_response": int_or_iso_per_endpoint,
        },
        "data":         { ... raw response payload(s) ... },
        "errors":       [ ... per-endpoint error strings ... ],
    }

Append-only by design: history is the value. No row is ever modified or
removed. Corpus consumers diff against earlier rows to study trajectory.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .paths import day_dir, manifest_path


def utc_now_iso() -> str:
    """Return UTC now as ISO-8601 with Z suffix — corpus timestamp convention."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Atomic-ish JSONL append. Parent dir is created if missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record, default=_json_fallback) + "\n")


def _json_fallback(o: Any) -> Any:
    """Coerce non-JSON-serializable types we might encounter."""
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if hasattr(o, "__dict__"):
        return o.__dict__
    return str(o)


def update_manifest(
    d: date | None,
    stream: str,
    *,
    increment_cycles: int = 0,
    errors: list[str] | None = None,
    note: str | None = None,
) -> None:
    """Maintain `manifest.json` summarizing what landed in the per-day dir."""
    path = manifest_path(d)
    if path.exists():
        manifest = json.loads(path.read_text())
    else:
        manifest = {
            "date": (d or _today_central_iso()),
            "streams": {},
            "notes": [],
        }
        day_dir(d, create=True)

    s = manifest["streams"].setdefault(stream, {"cycles": 0, "errors": []})
    s["cycles"] += increment_cycles
    if errors:
        s["errors"].extend(errors)
    s["last_pull_utc"] = utc_now_iso()

    if note:
        manifest["notes"].append({"ts": utc_now_iso(), "stream": stream, "note": note})

    path.write_text(json.dumps(manifest, indent=2, default=_json_fallback))


def _today_central_iso() -> str:
    from .paths import central_date
    return central_date().isoformat()
