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
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict

log = logging.getLogger(__name__)
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER = REPO_ROOT / "docs/a2a/inbox.md"
DEFAULT_BRIDGE = "/mnt/c/Users/steve/zgent-bridge"
ME = "Strader"
# Bridge filename stamps are Central, like every human-facing stamp here.
_CT = ZoneInfo("America/Chicago")

# Append-only record of when this observer FIRST SAW each memo. [st-w87l]
#
# WHY THIS EXISTS RATHER THAN stat(). An mtime is not a durable arrival mark.
# Measured 2026-08-26: four Desk memos had their arrival mtimes overwritten to
# 00:36:40 when the Drive sync re-delivered edited-in-place copies — the same
# run that logged "base64 content corruption in transit" and a context-limit
# truncation. The one memo in that batch which was NOT edited in place kept its
# true 15:49:53 mark. Thirteen such conflicts stand permanently and cannot be
# resolved by the sync, so this class of loss is not rare and not fixable
# downstream. The observer writing what it saw, when it saw it, is immune.
#
# The whole st-92m7 re-diagnosis turned on being able to say when things
# arrived, and two of its three latency claims survived audit only because
# bridge-check.jsonl happened to be sampling independently. This makes that
# deliberate rather than lucky.
SEEN_LEDGER = Path(os.environ.get(
    "BRIDGE_SEEN_LEDGER", "/var/moo/state/bridge-inbox-seen.jsonl"))

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
    first_seen_ts: float
    first_seen_source: str        # ledger | mtime  — see first_seen()
    sent_ts: float | None
    sent_source: str              # git | stamp | none — see sent_at()

    @property
    def transit_s(self) -> int | None:
        """Send-to-arrival seconds, or None when send time is unknown.

        This is the leg st-92m7 is about. It is only as good as ``sent_source``
        — a ``stamp``-sourced transit inherits the stamp's uncertainty and must
        carry the label wherever it is quoted.
        """
        if self.sent_ts is None:
            return None
        return int(self.first_seen_ts - self.sent_ts)

    @property
    def age_human(self) -> str:
        h, rem = divmod(max(self.age_s, 0), 3600)
        return f"{h}h{rem // 60:02d}m" if h else f"{rem // 60}m"


def _git_authored(path: Path) -> float | None:
    """Commit time of ``path``'s last change, or None if it is not in a repo.

    Ruling 12a: the bridge becomes a git repository and Drive retires. The
    moment that lands, mtime becomes CHECKOUT time — actively wrong, and wrong
    silently, since a fresh clone stamps every memo with the clone. Commit time
    is the durable answer and carries provenance for free, which is the
    stamp-trust property Steve asked for. Wired now so the cutover needs no
    second pass through this module.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", path.name],
            cwd=path.parent, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = out.stdout.strip()
    if out.returncode != 0 or not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return None


def _ledger_first_seen() -> dict[str, float]:
    """{stem: epoch} from the append-only seen ledger. First write wins."""
    first: dict[str, float] = {}
    try:
        text = SEEN_LEDGER.read_text(encoding="utf-8")
    except OSError:
        return first
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            stem, ts = row["stem"], row["ts"]
        except (ValueError, KeyError, TypeError):
            continue          # a torn line is not a reason to lose the rest
        try:
            epoch = datetime.fromisoformat(ts).timestamp()
        except ValueError:
            continue
        first.setdefault(stem, epoch)
    return first


# TWO QUANTITIES, NOT ONE. [st-w87l, COO 2026-08-26]
#
# An earlier version of this module had a single ``arrival()`` that would fall
# back from ledger to git commit time to mtime, as though the three answered
# the same question. They do not, and the conflation would have been invisible
# until it produced a wrong number:
#
#   FIRST SEEN — when this observer saw the memo. Ledger, else mtime.
#   SENT       — when the author dispatched it. Git author date, else the
#                filename stamp, which is a CLAIM and labelled as one.
#
# Why it matters concretely: st-92m7's subject is "this ruling sat unread for
# 9h35m", which is a SEND-to-read measurement. After the Ruling 12a cutover a
# single ``git pull`` lands a whole backlog at one instant, so first-seen is
# honestly identical for all of it and the send time is gone unless git
# supplies it. Keeping only arrival would answer the question we do not ask and
# lose the one we keep asking.


def first_seen(path: Path, stem: str, seen: dict[str, float]) -> tuple[float, str]:
    """When THIS OBSERVER saw the memo, and which source said so.

      ``ledger`` — recorded on first sight; nothing downstream can rewrite it.
      ``mtime``  — the floor, true only until something re-delivers or
                   re-checks-out the file. That is exactly what happened to
                   four memos on 2026-08-25.
    """
    if stem in seen:
        return seen[stem], "ledger"
    try:
        return path.stat().st_mtime, "mtime"
    except OSError:
        return time.time(), "mtime"


def sent_at(path: Path, stem: str) -> tuple[float | None, str]:
    """When the AUTHOR dispatched it, and how good that answer is.

      ``git``   — author date of the commit carrying it. Authoritative and
                  provenanced; the post-cutover answer.
      ``stamp`` — the filename's own timestamp. A CLAIM, not a measurement:
                  Desk stamps were estimates until 2026-08-26 (one was wrong by
                  three hours and a date line), two older memos carry literal
                  noon placeholders, and even a direct local write can miss its
                  own mtime by ~43s because the rename follows the write.
                  Usable, never quotable without the label.
      ``none``  — no answer. Say so rather than substituting arrival.
    """
    git_ts = _git_authored(path)
    if git_ts is not None:
        return git_ts, "git"
    m = _NAME.match(path.name)
    if m:
        try:
            naive = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S")
            return naive.replace(tzinfo=_CT).timestamp(), "stamp"
        except ValueError:
            pass
    return None, "none"


def record_first_seen(memos: list["Memo"]) -> int:
    """Append a row for every memo not already in the ledger. Never rewrites.

    Best-effort: /var/moo may be absent or read-only, and a bridge poll must
    not die because its bookkeeping could not be written.
    """
    fresh = [m for m in memos if m.first_seen_source != "ledger"]
    if not fresh:
        return 0
    try:
        SEEN_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with SEEN_LEDGER.open("a", encoding="utf-8") as fh:
            for m in fresh:
                fh.write(json.dumps({
                    "ts": datetime.fromtimestamp(m.first_seen_ts,
                                                 timezone.utc).isoformat(),
                    "stem": m.stem,
                    "participant": ME,
                    "sender": m.sender,
                    "observed_source": m.first_seen_source,
                    # Recorded beside arrival because after the git cutover a
                    # pull delivers a backlog at one instant and send time is
                    # the only thing that still separates the memos in it.
                    "sent": (None if m.sent_ts is None else
                             datetime.fromtimestamp(m.sent_ts,
                                                    timezone.utc).isoformat()),
                    "sent_source": m.sent_source,
                }) + "\n")
    except OSError as exc:
        log.warning("bridge_inbox: could not write %s (%s)", SEEN_LEDGER, exc)
        return 0
    return len(fresh)


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


def read_memo(path: Path, ledger_text: str, now: float | None = None,
              seen: dict[str, float] | None = None) -> Memo:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    fields = _header(text)
    m = _NAME.match(path.name)
    sender = fields.get("from") or (m.group(2) if m else "?")
    stem = path.name[:-3] if path.name.endswith(".md") else path.name
    seen_ts, seen_src = first_seen(path, stem, seen or {})
    sent_ts, sent_src = sent_at(path, stem)
    return Memo(
        path=str(path),
        stem=stem,
        sender=sender,
        klass=fields.get("class", "?"),
        addressed_to=fields.get("for", "?"),
        age_s=int((now if now is not None else time.time()) - seen_ts),
        first_seen_ts=seen_ts,
        first_seen_source=seen_src,
        sent_ts=sent_ts,
        sent_source=sent_src,
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
    seen = _ledger_first_seen()
    memos = [read_memo(p, ledger_text, now, seen) for p in sorted(d.glob("*.md"))]
    memos.sort(key=lambda m: -m.age_s)
    record_first_seen(memos)
    return memos


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
        # An mtime-sourced age is the weakest of the three and says so, because
        # the difference between "recorded on sight" and "whatever stat() says
        # now" has already changed a diagnosis once. [st-w87l]
        src = "" if m.first_seen_source == "ledger" else f" ({m.first_seen_source})"
        lines.append(
            f"  {m.age_human:>7}{src:<8} {m.sender:<10} {m.klass:<12} "
            f"{m.stem}{flag}")
        t = m.transit_s
        if t is not None and t >= 60:
            lines.append(
                f"           transit {t // 60}m from send "
                f"({m.sent_source}{', a claim' if m.sent_source == 'stamp' else ''})")
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
