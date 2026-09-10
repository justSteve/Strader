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

import fcntl
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .paths import day_dir, manifest_path

log = logging.getLogger(__name__)


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
    note_key: str | None = None,
    touch_last_pull: bool = True,
) -> None:
    """Maintain `manifest.json` summarizing what landed in the per-day dir.

    ``resolve_errors=True`` moves the stream's outstanding errors into an
    ``errors_resolved`` record (count, when, a three-line sample) and clears
    the list. The caller that may say this is one that has just replaced the
    stream's rows from a source that does not share the failure — the batch
    pull after a live-capture outage. The history is not lost: the count and
    the sample stay, and the full text is in the journal.

    ``note_key`` makes the note a keyed line: the first call with a given
    (stream, key) appends it, every later call rewrites that line in place —
    the live streamer keeps one line per outage this way, rewritten with the
    attempt count, instead of one line per attempt. (co-8b60y)

    ``touch_last_pull=False`` leaves ``last_pull_utc`` where it was. The gate
    reads that field as "the tape reaches here"; a bookkeeping call that
    landed no rows must not advance it. The field is still set the first time
    a stream's entry is created, so readers never meet an entry without it.

    Concurrency [st-5oli]: the read-modify-write runs under an exclusive
    ``flock`` on ``manifest.lock`` in the day dir, so two writers (the trades
    and depth streamers, a collector, the outage-note path) serialize instead
    of racing; the file is written to a *private* temp name (``mkstemp`` in the
    same dir) and renamed into place, so a kill mid-write leaves the previous
    manifest intact rather than a truncated one. Until 2026-09-08 the temp name
    was one shared ``manifest.json.tmp`` per day, two writers interleaved on
    one inode, and the rename was atomic over a file that was never private —
    2026-09-06 and 09-07 were left unparseable that way.

    A manifest that does not parse — the shape that collision left behind: a
    complete document with a second writer's tail after it — is salvaged
    rather than raised on: the original is kept beside it as
    ``manifest.json.corrupt-<utc>``, the valid prefix becomes the manifest, and
    a keyed note records what was discarded. A writer that raises here takes
    the collector's bookkeeping down for the rest of the day; on 09-07 the
    orderflow poller logged 'manifest update failed' and exited 0.
    """
    path = manifest_path(d)
    day_dir(d, create=True)
    with _manifest_lock(path):
        _update_manifest_locked(path, d, stream,
                                increment_cycles=increment_cycles, errors=errors,
                                note=note, resolve_errors=resolve_errors,
                                note_key=note_key, touch_last_pull=touch_last_pull)


def _update_manifest_locked(
    path: Path, d: date | None, stream: str, *, increment_cycles: int,
    errors: list[str] | None, note: str | None, resolve_errors: bool,
    note_key: str | None, touch_last_pull: bool,
) -> None:
    if path.exists():
        manifest = _load_or_salvage(path)
    else:
        manifest = {
            "date": (d or _today_central_iso()),
            "streams": {},
            "notes": [],
        }

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
    if touch_last_pull or "last_pull_utc" not in s:
        s["last_pull_utc"] = utc_now_iso()

    if note:
        notes = manifest.setdefault("notes", [])
        entry: dict[str, Any] = {"ts": utc_now_iso(), "stream": stream, "note": note}
        if note_key:
            entry["key"] = note_key
        existing = next(
            (i for i, n in enumerate(notes)
             if note_key and n.get("stream") == stream and n.get("key") == note_key),
            None,
        )
        if existing is None:
            notes.append(entry)
        else:
            notes[existing] = entry
        if len(notes) > MAX_MANIFEST_NOTES:
            excess = len(notes) - MAX_MANIFEST_NOTES
            manifest["notes_dropped"] = int(manifest.get("notes_dropped", 0) or 0) + excess
            manifest["notes"] = notes[excess:]

    _write_atomic(path, json.dumps(manifest, indent=2, default=_json_fallback))


def rewrite_manifest(d: date | None, edit: "Callable[[dict[str, Any]], None]",
                     *, path: Path | None = None) -> dict[str, Any]:
    """Apply ``edit`` to the day's manifest under the same lock and atomic
    rename ``update_manifest`` uses, and return the result. For the repair
    tools, whose edits (SET a cycle count, add a repair record) the increment
    API cannot express — before [st-5oli] they wrote the file directly and
    outside the lock. A missing manifest is created; an unparseable one is
    salvaged first. ``path`` overrides the corpus location (the repair tools
    resolve their own, so a test can point them at a fixture)."""
    path = path or manifest_path(d)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _manifest_lock(path):
        if path.exists():
            manifest = _load_or_salvage(path)
        else:
            manifest = {"date": (d or _today_central_iso()), "streams": {}, "notes": []}
        edit(manifest)
        _write_atomic(path, json.dumps(manifest, indent=2, default=_json_fallback))
    return manifest


def lock_path(path: Path) -> Path:
    """The advisory lock guarding ``path``'s read-modify-write: ``manifest.lock``
    beside it. It is never removed — an unlinked lock file is a lock two
    processes can hold at once."""
    return path.with_name("manifest.lock")


@contextmanager
def _manifest_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # releases the flock


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to a private temp file in ``path``'s directory, fsync,
    and rename over ``path``. The temp name is unique per call (``mkstemp``),
    which is what makes the rename mean anything [st-5oli]."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp creates 0600; the manifest is a shared read surface — keep the
        # mode the file already had (0644 for a new one, the umask default).
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _load_or_salvage(path: Path) -> dict[str, Any]:
    """Parse the manifest; if it does not parse, salvage it (see ``salvage``)."""
    text = path.read_text()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        manifest, report = salvage(path, text, str(e))
        log.warning("manifest %s salvaged: %s", path, report)
        return manifest


def salvage(path: Path, text: str | None = None, reason: str = "") -> tuple[dict[str, Any], str]:
    """Recover a manifest that has a complete JSON document followed by junk —
    the shape two interleaved writers leave [st-5oli]. The original is
    preserved as ``manifest.json.corrupt-<utc>``; the valid prefix is written
    back as the manifest with a keyed ``repair`` note saying how many trailing
    bytes were discarded and the tail they ended with, so the discarded write
    stays legible in the file it was lost from. Returns (manifest, report).

    Raises ``ValueError`` if no leading document parses — there is nothing to
    salvage then, and a human has to look.
    """
    if text is None:
        text = path.read_text()
    try:
        manifest, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: no leading JSON document to salvage ({e})") from e
    if not isinstance(manifest, dict):
        raise ValueError(f"{path}: leading document is not an object")
    junk = text[end:].strip()
    stamp = utc_now_iso()
    keep = path.with_name(path.name + ".corrupt-" + stamp.replace(":", ""))
    keep.write_text(text)
    tail = junk[-160:].replace("\n", " ")
    report = (f"salvaged {end} of {len(text)} bytes; {len(text) - end} trailing bytes "
              f"of a second interleaved write discarded (tail: {tail!r}); "
              f"original kept as {keep.name}"
              + (f"; parse error: {reason}" if reason else ""))
    notes = manifest.setdefault("notes", [])
    notes.append({"ts": stamp, "stream": "manifest", "key": "repair:" + stamp,
                  "note": "[st-5oli] " + report})
    _write_atomic(path, json.dumps(manifest, indent=2, default=_json_fallback))
    return manifest, report


def _today_central_iso() -> str:
    from .paths import central_date
    return central_date().isoformat()
