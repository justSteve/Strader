#!/usr/bin/env python3
"""Surface zgent-bridge memos addressed to Strader, in-session. [st-92m7]

WHY THIS EXISTS. On 2026-08-25 a Desk ruling addressed to Strader sat unread
for 9h35m while Strader independently re-derived it and wrote the duplicate
into the file Desk had just made the sole authority. The post-mortem blamed a
missing path. Measured 2026-08-26, that was wrong twice over:

  * The memos landed in ``Strader/inbox`` — the right folder. ``bridge-check.sh``
    counted them there. Nothing was mis-routed.
  * They were invisible because Strader's ONLY surfacing is ``bridge-check.sh``
    at tap-in, once per session. COO's 5-minute ``bridge-notify.sh`` hardcodes
    ``COO/inbox`` (line 29) and watches nothing else. The 08-25 session tapped
    in at 14:33 and handed off at 00:36, so every memo arriving in between was
    invisible BY CONSTRUCTION. 9h35m is not a missed check. It is the designed
    interval between checks.

So this is not another poller. It is the missing in-session hop: a watch that
wakes a RUNNING session when a memo lands, and a ledger writer that makes
``docs/a2a/inbox.md`` true rather than merely well-maintained.

It deliberately reads only ``Strader/inbox``. An earlier fix proposed scanning
peer OUTBOX and ``_archive`` folders for a ``for:`` naming Strader; that
addresses a failure that did not happen and would have us reading other
agents' mail to solve a problem in our own delivery.

The other half of the 08-25 delay — 79m53s of Desk-to-local sync latency — is
COO's ``bridge-drive-sync`` (co-2fa6a) and is not reachable from this repo.
This tool cannot make a memo arrive sooner. It makes one that HAS arrived stop
waiting for a session boundary.

USAGE

    .venv/bin/python3 tools/bridge_inbox.py                 # report, exit 1 if waiting
    .venv/bin/python3 tools/bridge_inbox.py --json
    .venv/bin/python3 tools/bridge_inbox.py --ledger        # append MEMO rows
    .venv/bin/python3 tools/bridge_inbox.py --watch         # block; one line per arrival

``--watch`` is the Monitor command: it prints ONLY on arrival, so a quiet
bridge produces no output and wakes nobody. Same discipline as COO's
``effort_event_watch.sh`` (st-85dv) — every line it prints is a model wake.

ENV
    BRIDGE_DIR   default /mnt/c/Users/steve/zgent-bridge
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER = REPO_ROOT / "docs/a2a/inbox.md"
DEFAULT_BRIDGE = "/mnt/c/Users/steve/zgent-bridge"
ME = "Strader"

# `**class:** ruling · **from:** Desk · **for:** COO, Strader · **written:** ...`
_FIELD = re.compile(r"\*\*(class|from|for|written):\*\*\s*([^·\n]+)")
# `20260825T143000__Desk__lexicon-ruling-scope-boundary.md`
_NAME = re.compile(r"^(\d{8}T\d{6})__([^_]+)__(.+)\.md$")


@dataclass
class Memo:
    path: str
    stem: str
    sender: str
    klass: str
    addressed_to: str
    age_s: int
    in_ledger: bool

    @property
    def age_human(self) -> str:
        h, rem = divmod(max(self.age_s, 0), 3600)
        return f"{h}h{rem // 60:02d}m" if h else f"{rem // 60}m"


def inbox_dir(bridge: str | None = None) -> Path:
    root = bridge or os.environ.get("BRIDGE_DIR", DEFAULT_BRIDGE)
    return Path(root) / ME / "inbox"


def _header(text: str) -> dict[str, str]:
    """Fields from the memo header, or {} for the pre-2026-08 format.

    Older memos carry no header at all. That is not an error and must not
    become one: the filename convention still identifies the sender, and a
    parser that refused them would silence exactly the backlog this exists to
    surface.
    """
    head = text[:4000]
    return {k: v.strip() for k, v in _FIELD.findall(head)}


def read_memo(path: Path, ledger_text: str, now: float | None = None) -> Memo:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    fields = _header(text)
    m = _NAME.match(path.name)
    sender = fields.get("from") or (m.group(2) if m else "?")
    stem = path.name[:-3] if path.name.endswith(".md") else path.name
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = time.time()
    return Memo(
        path=str(path),
        stem=stem,
        sender=sender,
        klass=fields.get("class", "?"),
        addressed_to=fields.get("for", "?"),
        age_s=int((now if now is not None else time.time()) - mtime),
        # The REF column of a MEMO/ACK row carries the memo filename without
        # `.md`, so the stem IS the join key between bridge and ledger.
        in_ledger=stem in ledger_text,
    )


def scan(bridge: str | None = None, now: float | None = None) -> list[Memo]:
    """Every memo waiting in Strader/inbox, oldest first.

    An absent bridge mount is normal — the Windows host is often away — and
    returns [] rather than raising, so a caller in a start-up path never dies
    on it.
    """
    d = inbox_dir(bridge)
    if not d.is_dir():
        return []
    try:
        ledger_text = LEDGER.read_text(encoding="utf-8")
    except OSError:
        ledger_text = ""
    memos = [read_memo(p, ledger_text, now) for p in sorted(d.glob("*.md"))]
    return sorted(memos, key=lambda m: -m.age_s)


def ledger_rows(memos: list[Memo], when: str) -> list[str]:
    """One MEMO row per memo not already referenced in the ledger."""
    rows = []
    for m in memos:
        if m.in_ledger:
            continue
        why = (f"Inbound {m.klass} from {m.sender} waiting in the bridge inbox "
               f"({m.age_human}); surfaced by bridge_inbox, not by a tap-in.")
        rows.append(
            f"| {when} | {ME} | MEMO | st-92m7 | {m.stem} | - | {why} |")
    return rows


def append_rows(rows: list[str]) -> int:
    if not rows:
        return 0
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    return len(rows)


def _now_ct() -> str:
    """The ledger's WHEN format. Central always — never UTC on a human line."""
    os.environ.setdefault("TZ", "America/Chicago")
    time.tzset()
    return datetime.now().strftime("%Y-%m-%d %H:%M CT")


def render(memos: list[Memo]) -> str:
    if not memos:
        return f"bridge: {ME}/inbox empty"
    lines = [f"bridge: {len(memos)} waiting for {ME}"]
    for m in memos:
        flag = "" if m.in_ledger else "  [NOT IN LEDGER]"
        lines.append(
            f"  {m.age_human:>7}  {m.sender:<10} {m.klass:<12} {m.stem}{flag}")
        if m.addressed_to != "?":
            lines.append(f"           for: {m.addressed_to}")
    return "\n".join(lines)


def watch(interval: int, bridge: str | None = None, once: bool = False) -> int:
    """Block, reporting ONLY new arrivals. A quiet bridge prints nothing.

    Seeded with what is already there, so arming mid-session does not replay
    the backlog as though it just landed — tap-in has already reported that.
    """
    seen = {m.stem for m in scan(bridge)}
    while True:
        time.sleep(max(interval, 1))
        for m in scan(bridge):
            if m.stem in seen:
                continue
            seen.add(m.stem)
            print(f"[BRIDGE] {m.sender} {m.klass} for {ME}: {m.stem}",
                  flush=True)
            if m.addressed_to != "?":
                print(f"         for: {m.addressed_to}", flush=True)
        if once:
            return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ledger", action="store_true",
                    help="append a MEMO row for each memo not already there")
    ap.add_argument("--watch", action="store_true",
                    help="block and print one line per NEW arrival")
    ap.add_argument("--interval", type=int, default=60,
                    help="--watch poll seconds (default 60)")
    ap.add_argument("--bridge", default=None)
    args = ap.parse_args(argv)

    if args.watch:
        return watch(args.interval, args.bridge)

    memos = scan(args.bridge)

    if args.ledger:
        n = append_rows(ledger_rows(memos, _now_ct()))
        print(f"bridge: {n} ledger row(s) appended")
        return 0

    if args.json:
        print(json.dumps({"count": len(memos),
                          "memos": [asdict(m) for m in memos]}, indent=2))
    else:
        print(render(memos))
    return 1 if memos else 0


if __name__ == "__main__":
    sys.exit(main())
