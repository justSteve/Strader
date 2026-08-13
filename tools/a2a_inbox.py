#!/usr/bin/env python3
"""Read docs/a2a/inbox.md and print what a tap-in briefing needs.

Two questions, both computed rather than remembered:

  1. What landed here from a peer agent since my last session?
  2. Which memos are still waiting on a receipt, and which are stale?

Definitions live in docs/a2a/receipt-protocol.md and are implemented here so a
skill step never has to reimplement them:

  OPEN   a MEMO line whose REF has no later ACK or SERVICED line with that REF
  STALE  OPEN, and >= 3 session handoffs have been written since the memo

"Session" is one `## HH:MM - Session Handoff` heading in DaysActivity.md or
archive/DaysActivity-YYYY-MM-DD.md — the only durable per-session timestamped
artifact this repo writes.

Authorizing bead: st-75z0.  Read-only: this never writes to the ledger.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "docs" / "a2a" / "inbox.md"

STALE_SESSIONS = 3
SELF = "strader"

WHEN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) CT$")
DAY_HEADER_RE = re.compile(r"^# DaysActivity - (\d{4}-\d{2}-\d{2})")
HANDOFF_RE = re.compile(r"^## (\d{2}):(\d{2}) - Session Handoff")
ARCHIVE_RE = re.compile(r"^DaysActivity-(\d{4}-\d{2}-\d{2})\.md$")

FIELDS = ("when", "actor", "kind", "bead", "ref", "paths", "why")
KINDS = {"COMMIT", "MEMO", "ACK", "SERVICED", "DIGEST"}


class Event:
    def __init__(self, lineno: int, when: datetime, cells: list[str]):
        self.lineno = lineno
        for name, value in zip(FIELDS, cells):
            setattr(self, name, value)
        self.when = when  # parsed datetime replaces the raw cell text

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Event {self.when:%Y-%m-%d %H:%M} {self.actor} {self.kind} {self.ref}>"


def parse_when(text: str) -> datetime | None:
    m = WHEN_RE.match(text.strip())
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}", "%Y-%m-%d %H:%M")


def parse_inbox(path: Path) -> tuple[list[Event], list[str]]:
    """Return (events, problems). Only rows below the `## Ledger` heading count."""
    problems: list[str] = []
    if not path.exists():
        return [], [f"{path} does not exist"]

    events: list[Event] = []
    in_ledger = False
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if line.startswith("## "):
            in_ledger = line.lower().startswith("## ledger")
            continue
        if not in_ledger or not line.startswith("|"):
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0].upper() == "WHEN":
            continue  # table header
        if all(set(c) <= {"-", ":"} for c in cells if c):
            continue  # table separator

        if len(cells) != len(FIELDS):
            problems.append(f"line {lineno}: {len(cells)} fields, expected {len(FIELDS)}")
            continue
        when = parse_when(cells[0])
        if when is None:
            problems.append(f"line {lineno}: bad timestamp {cells[0]!r} (want 'YYYY-MM-DD HH:MM CT')")
            continue
        if cells[2] not in KINDS:
            problems.append(f"line {lineno}: unknown KIND {cells[2]!r}")
            continue
        events.append(Event(lineno, when, cells))

    events.sort(key=lambda e: e.when)
    return events, problems


def session_times(repo: Path) -> list[datetime]:
    """Every session-handoff timestamp, oldest first."""
    stamps: list[datetime] = []

    def scan(path: Path, day: str | None) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            header = DAY_HEADER_RE.match(line)
            if header:
                day = header.group(1)
                continue
            entry = HANDOFF_RE.match(line)
            if entry and day:
                stamps.append(
                    datetime.strptime(f"{day} {entry.group(1)}:{entry.group(2)}", "%Y-%m-%d %H:%M")
                )

    scan(repo / "DaysActivity.md", None)
    archive = repo / "archive"
    if archive.is_dir():
        for f in sorted(archive.iterdir()):
            m = ARCHIVE_RE.match(f.name)
            if m:
                scan(f, m.group(1))

    stamps.sort()
    return stamps


def sessions_since(when: datetime, stamps: list[datetime]) -> int:
    return sum(1 for s in stamps if s > when)


def open_memos(events: list[Event]) -> list[Event]:
    """MEMOs with no later ACK/SERVICED carrying the same REF."""
    answered: dict[str, datetime] = {}
    for e in events:
        if e.kind in ("ACK", "SERVICED") and e.ref and e.ref != "-":
            answered.setdefault(e.ref, e.when)
            answered[e.ref] = min(answered[e.ref], e.when)
    out = []
    for e in events:
        if e.kind != "MEMO":
            continue
        replied = answered.get(e.ref)
        if replied is None or replied < e.when:
            out.append(e)
    return out


def fmt_event(e: Event) -> str:
    head = f"  {e.when:%Y-%m-%d %H:%M} CT  {e.actor}  {e.kind}  {e.bead}"
    if e.paths and e.paths != "-":
        head += f"  {e.paths}"
    return f"{head}\n      {e.why}"


def fmt_memo(e: Event, stamps: list[datetime]) -> str:
    n = sessions_since(e.when, stamps)
    flag = "[ALERT] " if n >= STALE_SESSIONS else ""
    plural = "session" if n == 1 else "sessions"
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", e.ref)  # date already shown
    return f"  {flag}{e.when:%Y-%m-%d} {slug} — OPEN {n} {plural} ({e.actor})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=str(INBOX), help="inbox ledger to read (default: Strader's)")
    ap.add_argument("--since", help="cutoff YYYY-MM-DD or 'YYYY-MM-DD HH:MM' (default: last session handoff)")
    ap.add_argument("--landed", action="store_true", help="only the landed-since section")
    ap.add_argument("--open", dest="open_only", action="store_true", help="only the receipts sections")
    args = ap.parse_args()

    events, problems = parse_inbox(Path(args.file))
    stamps = session_times(REPO)

    if args.since:
        text = args.since.strip()
        cutoff = datetime.strptime(text, "%Y-%m-%d %H:%M" if " " in text else "%Y-%m-%d")
    elif stamps:
        cutoff = stamps[-1]
    else:
        cutoff = datetime.min

    show_landed = args.landed or not args.open_only
    show_open = args.open_only or not args.landed

    if show_landed:
        landed = [e for e in events if e.when > cutoff and e.actor.lower() != SELF]
        label = "the beginning" if cutoff == datetime.min else f"{cutoff:%Y-%m-%d %H:%M} CT"
        print(f"LANDED SINCE {label} ({len(landed)} events)")
        if not landed:
            print("  nothing from a peer agent")
        for e in landed:
            print(fmt_event(e))
        print()

    if show_open:
        pending = open_memos(events)
        owed = [e for e in pending if e.actor.lower() != SELF]
        awaited = [e for e in pending if e.actor.lower() == SELF]

        print(f"RECEIPTS OWED BY STRADER ({len(owed)})")
        if not owed:
            print("  none — every memo received has an ACK or SERVICED line")
        for e in sorted(owed, key=lambda x: x.when):
            print(fmt_memo(e, stamps))
        print()

        print(f"RECEIPTS AWAITED FROM PEERS ({len(awaited)})")
        if not awaited:
            print("  none — every memo sent has been answered")
        for e in sorted(awaited, key=lambda x: x.when):
            print(fmt_memo(e, stamps))
        print()

    if problems:
        print(f"[ALERT] inbox.md has {len(problems)} malformed line(s) — they are NOT counted above:")
        for p in problems:
            print(f"  {p}")
        print("  format: | WHEN | ACTOR | KIND | BEAD | REF | PATHS | WHY |  (docs/a2a/inbox.md)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
