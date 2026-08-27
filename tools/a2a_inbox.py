#!/usr/bin/env python3
"""Read docs/a2a/inbox.md and print what a tap-in briefing needs.

Two questions, both computed rather than remembered:

  1. What landed here from a peer agent since my last session?
  2. Which memos are still waiting on a receipt, and which are stale?

Definitions live in docs/a2a/receipt-protocol.md and are implemented here so a
skill step never has to reimplement them:

  OPEN   a MEMO line whose REF has no later ACK or SERVICED line with that REF,
         in this ledger OR in a peer's own ledger (see PEER_LEDGERS)
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

# Peer ledgers, read for RECEIPTS ONLY [st-1eaw].
#
# WHY: receipt-protocol.md §2 puts the ACK/SERVICED row in the SENDER's inbox,
# because the party waiting on the answer is the one who needs to see it. On
# 2026-08-25 both of Strader's open memos turned out to have been serviced by COO
# within a day of being sent — code-estate-plan on 08-13 (COO 25a02f1), claudemd-
# scope on 08-14 (COO cfa18f7) — with both SERVICED rows logged in COO's own
# ledger. This tool read only the file above, so it printed [ALERT] OPEN for 12
# and 9 sessions against finished work, and a receipt nudge went out on that
# false read. A tracker that a peer's filing habit can silently starve of
# receipts is the defect; reading the peer ledger as a BACKSTOP fixes it without
# depending on anyone remembering the protocol.
#
# Receipts only. Peer rows never become "landed here" events, and a malformed
# line in a peer's file is never reported as this ledger's problem — this repo's
# suite must not go red for someone else's typo.
PEER_LEDGERS = {"COO": REPO.parent / "COO" / "docs" / "a2a" / "inbox.md"}

STALE_SESSIONS = 3
SELF = "strader"

WHEN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) CT$")
DAY_HEADER_RE = re.compile(r"^# DaysActivity - (\d{4}-\d{2}-\d{2})")
HANDOFF_RE = re.compile(r"^## (\d{2}):(\d{2}) - Session Handoff")
ARCHIVE_RE = re.compile(r"^DaysActivity-(\d{4}-\d{2}-\d{2})\.md$")

FIELDS = ("when", "actor", "kind", "bead", "ref", "paths", "why")
# The ledger vocabulary, reconciled with COO 2026-08-13 [st-qfsz].
#
# WHY IT NEEDED RECONCILING: on 08-13 four correctly-announced COO rows parsed as
# malformed, because this set had no word for events .claude/rules/zgent-
# permissions.md already REQUIRES a peer to announce. They went invisible to
# every tool that reads parsed events — on the day one of them was reporting a
# live risk to the corpus. A vocabulary narrower than the obligations it records
# does not enforce anything; it just loses rows.
#
#   WRITE     a peer wrote into this repo (the same-commit announce obligation)
#   FILED     a peer filed a bead here
#   STATUS    a peer reporting a state change on shared infrastructure
#   SERVICED  a request completed
#   ACK       read and understood, not doing it yet
#   MEMO      FYI, no action owed
#   DIGEST    a peer's handoff summary; owes no reply
#   DIRECTIVE an order relayed from Steve; owes no reply
#
# COMMIT is RETIRED in favour of WRITE (COO's ruling, 2026-08-13). One word per
# event, and WRITE is the word zgent-permissions.md itself uses, so the
# permission rule and the ledger vocabulary now say the same thing. It stays
# READABLE so the historical rows above it still parse — retiring a word must
# not rewrite history — but it is refused for new rows.
# NOTE is RETIRED in favour of STATUS (st-xa5p, 2026-08-20). It was never a
# writable kind, but COO wrote three of them on 2026-08-18/19 and the parser
# dropped all three rows on the floor — one of them announcing the plain-words
# gate on the shared desk renderer, which is precisely the class of event this
# ledger exists to make visible. STATUS already means what those rows meant: a
# peer reporting on work already announced, owing no reply. Same treatment as
# COMMIT — readable so the rows count as history, refused for new ones.
# DIRECTIVE is ADMITTED (Desk Ruling 15, 2026-08-27, st-l711). A directive is
# not a memo: it starts no receipt clock, expects no reply, and its authority
# derives from the AUTHOR rather than the content. Folding it into MEMO would
# erase the one distinction this ledger exists to preserve — what Steve ORDERED
# versus what anyone SAID. The distinction is already load-bearing on two rows
# in COO's ledger, one of them carrying the credential-estate convention; those
# rows stand as written, and admitting the word is what makes them parse.
# Rewriting ratified history as MEMO plus correction rows would trade two
# accurate rows for four rows and a lie about what happened.
WRITABLE_KINDS = {"WRITE", "MEMO", "ACK", "SERVICED", "DIGEST", "FILED", "STATUS", "DIRECTIVE"}
RETIRED_KINDS = {"COMMIT": "WRITE", "NOTE": "STATUS"}
KINDS = WRITABLE_KINDS | set(RETIRED_KINDS)
# Retirement is enforced by DATE, not by deletion, and the date is PER WORD —
# each retirement starts its own clock, so retiring a second word cannot
# retroactively make the first one's history dirty. This tool only reads, so the
# parse is the only place a rule can bite: a retired KIND dated on or after its
# own ruling is a problem, the same rows dated before it are clean history. That
# makes test_real_inbox_has_no_malformed_lines the enforcement mechanism — the
# suite goes red the first time anyone writes a retired word, which is the only
# kind of rule that survives nobody remembering it.
RETIRED_FROM = {
    "COMMIT": datetime(2026, 8, 13, 18, 0),
    "NOTE": datetime(2026, 8, 20, 14, 0),
}


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
        if cells[2] in RETIRED_KINDS and when >= RETIRED_FROM[cells[2]]:
            # Flagged but still recorded: the event is real and belongs in the
            # ledger whatever it was called. Losing a row to a vocabulary
            # complaint is the failure this whole reconciliation came from.
            problems.append(
                f"line {lineno}: KIND {cells[2]!r} is retired — use "
                f"{RETIRED_KINDS[cells[2]]!r}")
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


def receipt_index(events: list[Event]) -> dict[str, datetime]:
    """REF -> the earliest ACK/SERVICED time carrying it."""
    answered: dict[str, datetime] = {}
    for e in events:
        if e.kind in ("ACK", "SERVICED") and e.ref and e.ref != "-":
            prior = answered.get(e.ref)
            answered[e.ref] = e.when if prior is None else min(prior, e.when)
    return answered


def peer_receipts(ledgers: dict[str, Path] | None = None) -> dict[str, tuple[datetime, str]]:
    """REF -> (earliest receipt time, peer name), read from the peers' own ledgers.

    A missing or unreadable peer repo is not an error here: the backstop degrades
    to the old behaviour rather than taking the briefing down with it.
    """
    out: dict[str, tuple[datetime, str]] = {}
    for name, path in (PEER_LEDGERS if ledgers is None else ledgers).items():
        try:
            events, _ = parse_inbox(Path(path))
        except OSError:
            continue
        for ref, when in receipt_index(events).items():
            prior = out.get(ref)
            if prior is None or when < prior[0]:
                out[ref] = (when, name)
    return out


def open_memos(
    events: list[Event],
    extra: dict[str, tuple[datetime, str]] | None = None,
) -> list[Event]:
    """MEMOs with no later ACK/SERVICED carrying the same REF.

    `extra` is the peer-ledger backstop: REF -> (when, peer). A memo answered
    only there is genuinely answered, so it does not belong on the alert list —
    but main() prints it in its own section, because a receipt filed in the wrong
    ledger is the defect that produced the 08-25 false alerts [st-1eaw].
    """
    answered = receipt_index(events)
    for ref, (when, _peer) in (extra or {}).items():
        prior = answered.get(ref)
        if prior is None or when < prior:
            answered[ref] = when
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
    ap.add_argument("--no-peers", action="store_true",
                    help="do not read peer ledgers for receipts (backstop off)")
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
        local = receipt_index(events)
        extra = {} if args.no_peers else peer_receipts()
        pending = open_memos(events, extra)
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

        # Answered, but the row is in the wrong ledger. Not an alert — the work
        # is done — and not silence either, because silence is how 08-25 happened.
        peer_only = [
            e for e in events
            if e.kind == "MEMO" and e.ref in extra and extra[e.ref][0] >= e.when
            and not (e.ref in local and local[e.ref] >= e.when)
        ]
        if peer_only:
            print(f"RECEIPTS FILED PEER-SIDE ONLY ({len(peer_only)}) — answered, wrong ledger [st-1eaw]")
            for e in sorted(peer_only, key=lambda x: x.when):
                when, peer = extra[e.ref]
                slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", e.ref)
                print(f"  {e.when:%Y-%m-%d} {slug} — receipt sits in {peer}'s ledger "
                      f"({when:%Y-%m-%d}); receipt-protocol §2 wants it here")
            print()

    if problems:
        print(f"[ALERT] inbox.md has {len(problems)} malformed line(s) — they are NOT counted above:")
        for p in problems:
            print(f"  {p}")
        print("  format: | WHEN | ACTOR | KIND | BEAD | REF | PATHS | WHY |  (docs/a2a/inbox.md)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
