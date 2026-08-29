"""Shared pieces of the footprint ICM audit lane. [st-h0xx]

The lane re-reads a day's archived EVENT stream after the close, has a
folder-bounded model label what it sees, and compares that with what the live
analyst said in real time. Everything the stages share — where a run lives,
how a live scorer log is read, how the set of wakes the live analyst was
actually shown is derived — is here so no stage carries its own copy.

WHERE A RUN LIVES. ``/var/moo/state/footprint-icm/<day>/``: outside every
repo (a model's output and a transcript's prose do not belong in the trading
repo), backed up nightly by the memory-core bundle, and with no CLAUDE.md in
any parent so a stage run from there loads no project instructions.

TAPE TIME, NOT PRINT TIME. Every HH:MM on a scorer line is the trade minute,
never the wall clock. The scorer prints a minute's lines when the next
minute's first trade arrives, and a restart prints the whole morning in one
burst. So "the alerts the analyst was shown" is not "the alerts in the log":
it is the alerts whose tape minute is at or after the scorer's start and at
or after the moment the watch was armed, before the watch stopped. That rule
is ``derive_wakes`` and it is the blocker finding the plan turned on
(determinism-3).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date as _date, datetime, time as _time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
ROOT = Path(__file__).resolve().parents[2]            # /root/projects/Strader
LANE = ROOT / "footprint-icm"
# ICM_STATE_DIR is a test seam only: the contract address is /var/moo/state.
STATE = Path(os.environ.get("ICM_STATE_DIR", "/var/moo/state/footprint-icm"))
LOG_DIR = Path("/var/moo/logs/effort-effect")
PARSED = ROOT / "runbook/mancini/parsed"
DESK_DIR = Path("/var/moo/desk")
COO_ROOT = Path("/root/projects/COO")
DESK_HTML = COO_ROOT / "tmuxMOO/bin/desk-html.sh"
DESK_REGISTER = COO_ROOT / "tmuxMOO/bin/desk-register.sh"
WATCH_SCRIPT = "effort_event_watch.sh"
BATCH_GAP_S = 20          # tools/effort_event_watch.sh BATCH_GAP: alerts within it are one wake

# The scorer's line shapes (docs/playbooks/emitter-two-tier.md "Reading an EVENT line";
# scripts/live_effort_effect.py header section).
EVENT_RE = re.compile(r"^(\d{2}):(\d{2}) CT\s+EVENT (\S+) (\S+)\s+sig=(alert|note)\b")
GRADED_RE = re.compile(r"^(\d{2}):(\d{2}) CT\s+F[1-4] \(developing")
PARTIAL_RE = re.compile(r"^(\d{2}):(\d{2}):\d{2} CT\s+partial \(")
SCORER_HEADER = "# effort/effect scorer"
REGIME_RE = re.compile(r"^# ==== REGIME CHANGE (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z")
KNOBS_PREFIX = "# knobs: "
LEVELS_RE = re.compile(r"(\d+) levels loaded")

log = logging.getLogger("footprint-icm")


class LaneError(Exception):
    """A check the lane refuses to continue past. ``run_day.sh`` stops at the
    first one; the message names the check and the numbers."""


# ── run folder and run.json ────────────────────────────────────────────────

def run_dir(day: _date, create: bool = True) -> Path:
    p = STATE / day.isoformat()
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str) + "\n",
                    encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def update_run_json(day: _date, section: str, obj) -> Path:
    """Merge one stage's record into ``<run>/run.json`` under ``section``.
    Each stage owns its own key; nothing overwrites another stage's."""
    p = run_dir(day) / "run.json"
    doc = read_json(p) if p.exists() else {"day": day.isoformat()}
    doc[section] = obj
    doc["updated_at"] = datetime.now(CT).isoformat(timespec="seconds")
    write_json(p, doc)
    return p


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_short(path: Path | None = None) -> str:
    """Short SHA of the last commit touching ``path`` (repo-relative or
    absolute under ROOT), or HEAD when ``path`` is None."""
    cmd = ["git", "-C", str(ROOT), "log", "-1", "--format=%h"]
    if path is not None:
        cmd += ["--", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


# ── time helpers ───────────────────────────────────────────────────────────

def utc_iso_to_ct(stamp: str) -> datetime:
    """``2026-08-27T14:54:47`` (Z implied) or any ISO with offset → CT-aware."""
    s = stamp.rstrip("Z")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CT)


def hhmm(t: _time | datetime) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def minute_of_line(line: str) -> str | None:
    """The tape minute ``HH:MM`` of a graded, partial or EVENT line; None for
    a header or anything else."""
    m = EVENT_RE.match(line) or GRADED_RE.match(line) or PARTIAL_RE.match(line)
    return f"{m.group(1)}:{m.group(2)}" if m else None


# ── the live scorer log ────────────────────────────────────────────────────

@dataclass
class LiveLog:
    path: Path
    lines: list[str]
    segment_starts: list[int]                 # indices of '# effort/effect scorer' headers
    start_stamp_utc: str | None               # last REGIME CHANGE stamp
    start_ct: datetime | None
    knobs: dict[str, str]                     # last '# knobs:' line, values as printed
    levels_loaded: int | None                 # from the last scorer header
    event_lines: list[str] = field(default_factory=list)
    body_after_last_header: list[str] = field(default_factory=list)
    last_closed_minute: str | None = None

    @property
    def alert_lines(self) -> list[str]:
        return [ln for ln in self.event_lines if " sig=alert" in ln]


def parse_knobs_line(line: str) -> dict[str, str]:
    body = line[len(KNOBS_PREFIX):] if line.startswith(KNOBS_PREFIX) else line
    out: dict[str, str] = {}
    for tok in body.split("  "):
        tok = tok.strip()
        if not tok or "=" not in tok:
            continue
        k, _, v = tok.partition("=")
        out[k] = v
    return out


def parse_live_log(path: Path) -> LiveLog:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    seg = [i for i, ln in enumerate(lines) if ln.startswith(SCORER_HEADER)]
    stamp = None
    knobs: dict[str, str] = {}
    levels = None
    for ln in lines:
        m = REGIME_RE.match(ln)
        if m:
            stamp = m.group(1)
        if ln.startswith(KNOBS_PREFIX):
            knobs = parse_knobs_line(ln)
        if ln.startswith(SCORER_HEADER):
            lm = LEVELS_RE.search(ln)
            levels = int(lm.group(1)) if lm else None
    events = [ln.rstrip() for ln in lines if EVENT_RE.match(ln)]
    last_hdr = seg[-1] if seg else -1
    body = [ln.rstrip() for ln in lines[last_hdr + 1:] if not ln.startswith("#")]
    graded = [ln for ln in lines if GRADED_RE.match(ln)]
    last_closed = minute_of_line(graded[-1]) if graded else None
    return LiveLog(path=path, lines=lines, segment_starts=seg, start_stamp_utc=stamp,
                   start_ct=utc_iso_to_ct(stamp) if stamp else None, knobs=knobs,
                   levels_loaded=levels, event_lines=events, body_after_last_header=body,
                   last_closed_minute=last_closed)


def live_log_path(day: _date) -> Path:
    return LOG_DIR / f"{day.isoformat()}.log"


# ── the delivered wake set ─────────────────────────────────────────────────

@dataclass
class Wake:
    minute: str                 # tape minute of the batch, HH:MM
    lines: list[str]            # the sig=alert EVENT lines in it, log order
    bar: str | None = None      # the last graded line before the first alert


def derive_wakes(log_lines: list[str], *, start_ct: datetime | None,
                 arm_ct: datetime | None, stop_ct: datetime | None) -> dict:
    """Which alerts the watch actually delivered, by rule.

    An alert is delivered when its tape minute is at or after the scorer's
    start minute (everything earlier was printed in the restart burst, and
    the watch starts at the end of the file), at or after the arm minute, and
    before the minute the watch stopped. Alerts in one tape minute print
    within the same second and are one wake (BATCH_GAP is 20 s; consecutive
    minutes are 60 s apart). The graded bar the watch attaches is the last
    graded line printed before the batch.

    Returns ``{"wakes": [Wake…], "ambiguous": [lines], "undelivered": [lines]}``.
    Ambiguous: the tape minute is one before the arm minute or equal to the
    stop minute — whether the print beat the arm/stop is not decidable from
    the log. They are listed, never counted.
    """
    lo_candidates = [t for t in (start_ct, arm_ct) if t is not None]
    lo = max(hhmm(t) for t in lo_candidates) if lo_candidates else "00:00"
    arm_m = hhmm(arm_ct) if arm_ct else None
    stop_m = hhmm(stop_ct) if stop_ct else None
    wakes: list[Wake] = []
    ambiguous: list[str] = []
    undelivered: list[str] = []
    last_bar: str | None = None
    for ln in log_lines:
        if GRADED_RE.match(ln):
            last_bar = ln.rstrip()
            continue
        m = EVENT_RE.match(ln)
        if not m or m.group(5) != "alert":
            continue
        minute = f"{m.group(1)}:{m.group(2)}"
        line = ln.rstrip()
        if arm_m and _prev_minute(arm_m) == minute and minute < lo:
            ambiguous.append(line)
            continue
        if minute < lo:
            undelivered.append(line)
            continue
        if stop_m is not None:
            if minute == stop_m:
                ambiguous.append(line)
                continue
            if minute > stop_m:
                undelivered.append(line)
                continue
        if wakes and wakes[-1].minute == minute:
            wakes[-1].lines.append(line)
        else:
            wakes.append(Wake(minute=minute, lines=[line], bar=last_bar))
    return {"wakes": wakes, "ambiguous": ambiguous, "undelivered": undelivered}


def _prev_minute(m: str) -> str:
    h, mm = (int(x) for x in m.split(":"))
    mm -= 1
    if mm < 0:
        mm, h = 59, (h - 1) % 24
    return f"{h:02d}:{mm:02d}"


def wake_records(wakes: list[Wake]) -> list[dict]:
    return [{"minute": w.minute, "lines": w.lines, "bar": w.bar} for w in wakes]


# ── word-for-word matching ─────────────────────────────────────────────────
# A quote is verbatim when its words are the excerpt's words. Markdown
# emphasis marks, line breaks and curly quotes are not words: the
# trapped-seller sentence the runbook cites runs across two lines with **
# inside it, and a rule that failed on that would fail a true citation.

_QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                            "–": "-", "—": "-", " ": " "})


def normalize(text: str) -> str:
    t = text.translate(_QUOTE_MAP)
    t = re.sub(r"[*`]+", "", t)
    # _emphasis_ marks go; the underscore inside failed_breakdown stays.
    t = re.sub(r"(?<!\w)_+|_+(?!\w)", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


def contains_verbatim(haystack: str, needle: str) -> bool:
    n = normalize(needle)
    return bool(n) and n in normalize(haystack)
