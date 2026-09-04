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


#: How many error strings a stream's manifest entry keeps. The FIRST ones stay —
#: they say when and how the trouble began — and the rest become a count.
#: Measured 2026-09-04 (co-8b60y): a 42-hour outage appended 6,466 copies of one
#: sentence per stream and a 4.4 MB manifest; the count says the same thing.
MAX_MANIFEST_ERRORS = 50
#: How many notes the day keeps. The LAST ones stay — the newest note is the
#: one that says what finally happened — and older ones become a count.
MAX_MANIFEST_NOTES = 50


def update_manifest(
    d: date | None,
    stream: str,
    *,
    increment_cycles: int = 0,
    errors: list[str] | None = None,
    note: str | None = None,
    resolve_errors: bool = False,
) -> None:
    """Maintain `manifest.json` summarizing what landed in the per-day dir.

    ``resolve_errors=True`` moves the stream's outstanding errors into an
    ``errors_resolved`` record (count, when, a three-line sample) and clears
    the list. The caller that may say this is one that has just replaced the
    stream's rows from a source that does not share the failure — the batch
    pull after a live-capture outage. The history is not lost: the count and
    the sample stay, and the full text is in the journal.

    The file is written to a temporary name and renamed into place, so a kill
    mid-write leaves the previous manifest intact rather than a truncated one.
    """
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
        kept = s.setdefault("errors", [])
        room = MAX_MANIFEST_ERRORS - len(kept)
        if room > 0:
            kept.extend(errors[:room])
        dropped = len(errors) - max(room, 0)
        if dropped > 0:
            s["errors_dropped"] = int(s.get("errors_dropped", 0) or 0) + dropped
    if resolve_errors and (s.get("errors") or s.get("errors_dropped")):
        outstanding = list(s.get("errors") or [])
        total = len(outstanding) + int(s.get("errors_dropped", 0) or 0)
        s["errors_resolved"] = {
            "count": total,
            "resolved_utc": utc_now_iso(),
            "sample": outstanding[:3],
            "note": note or "",
        }
        s["errors"] = []
        s.pop("errors_dropped", None)
    s["last_pull_utc"] = utc_now_iso()

    if note:
        notes = manifest.setdefault("notes", [])
        notes.append({"ts": utc_now_iso(), "stream": stream, "note": note})
        if len(notes) > MAX_MANIFEST_NOTES:
            excess = len(notes) - MAX_MANIFEST_NOTES
            manifest["notes_dropped"] = int(manifest.get("notes_dropped", 0) or 0) + excess
            manifest["notes"] = notes[excess:]

    _write_atomic(path, json.dumps(manifest, indent=2, default=_json_fallback))


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _today_central_iso() -> str:
    from .paths import central_date
    return central_date().isoformat()
