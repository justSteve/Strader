#!/usr/bin/env python3
"""End-of-day fact packet — the mechanical half of the EOD ritual. [st-z92a]

    .venv/bin/python scripts/eod_packet.py                  # today
    .venv/bin/python scripts/eod_packet.py --day 2026-08-07
    .venv/bin/python scripts/eod_packet.py --audit          # days missing a Day Close
    .venv/bin/python scripts/eod_packet.py --stdout         # don't write, just print

WHAT PROBLEM THIS SOLVES. DaysActivity.md is created lazily by /handoff and
rolled lazily by /tap-in, so nothing in the record is anchored to the trading
day. On 2026-08-08 five commits landed, no handoff ran, and the day got no entry
at all — its one substantive result survived only inside a commit message.
Sessions are allowed to span midnight (Steve, 2026-08-09), which makes the
session an even worse unit for a record whose neighbours — data/corpus/<date>/,
the Mancini parse, the level states, the parity run log — are all day-keyed.

THE DIVISION OF LABOUR IS THE SAME ONE /mancini-parse USES, and for the same
reason: cron prepares and alerts, the skill interprets. This script gathers
facts and writes them to data/eod/<date>.md; it draws no conclusions, grades no
calls and writes nothing to DaysActivity.md. The Day Close entry is written by
the /eod skill, by an agent, reading this packet.

WHY THE PACKET IS DURABLE ON DISK rather than piped straight into a session:
the failure being fixed is a day whose facts evaporated because nobody was
around to write them down. A packet that only exists inside a session that may
never happen reproduces the bug. Written to disk, the facts survive; only the
narrative waits for an agent. A day with a packet and no Day Close entry is then
a VISIBLE gap (`--audit`, surfaced at tap-in), not a silent one.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from strader.market_calendar import (  # noqa: E402
    CENTRAL,
    GEX_COLLECT_START_CT,
    GEX_COLLECT_UNTIL_CT,
    collect_window,
    describe,
    is_trading_day,
    session_close_ct,
)

EOD_DIR = REPO / "data" / "eod"
CORPUS = REPO / "data" / "corpus"
CALLS = REPO / "data" / "calls"
MANCINI = REPO / "runbook" / "mancini" / "commentary"
PARITY = REPO / "data" / "derived" / "live-parity"
DAYS_ACTIVITY = REPO / "DaysActivity.md"
ARCHIVE = REPO / "archive"

#: Streams whose absence on a trading day is worth saying out loud. Anything
#: else in the manifest is reported but not judged.
EXPECTED_STREAMS = ("databento_glbx_es", "databento_glbx_es_mbp1", "gexbot")

#: The heading the /eod skill writes. `--audit` looks for exactly this.
DAY_CLOSE_MARK = "Day Close"

#: First day the ritual is expected to have run. Everything before this predates
#: st-z92a and is not a gap — without this the audit reports every trading day
#: in repo history as missing, which is a nag, and a nag gets ignored.
RITUAL_START = _date(2026, 8, 10)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _sh(*args: str) -> str:
    """Run a command in the repo, return stdout, never raise."""
    try:
        p = subprocess.run(args, cwd=REPO, capture_output=True, text=True, timeout=30)
        return p.stdout.strip()
    except Exception as e:                       # noqa: BLE001 — a packet is
        return f"<{type(e).__name__}: {e}>"      # best-effort by design


def _mb(p: Path) -> str:
    if not p.exists():
        return "absent"
    n = p.stat().st_size
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


def _rel(p: Path) -> str:
    """Repo-relative when it can be, absolute otherwise — paths are redirected
    under test and a bare relative_to() would raise instead of reporting."""
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except Exception:                            # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# fact gathering — one function per section, each returns (facts, gaps)
# --------------------------------------------------------------------------

def gather_data(day: _date) -> tuple[dict, list[str]]:
    """What the collectors actually landed. This is the section that decides
    whether the day's tape is usable tomorrow, so it leads the packet."""
    d = CORPUS / day.isoformat()
    manifest = _read_json(d / "manifest.json") or {}
    streams = manifest.get("streams") or {}
    gaps: list[str] = []

    rows = []
    for name, entry in sorted(streams.items()):
        errs = entry.get("errors") or []
        rows.append({
            "stream": name,
            "cycles": entry.get("cycles"),
            "errors": len(errs),
            "first_error": errs[0].splitlines()[0] if errs else None,
            "last_pull_utc": entry.get("last_pull_utc"),
        })
    for name in EXPECTED_STREAMS:
        entry = streams.get(name)
        if not entry:
            gaps.append(f"{name} is absent from the manifest — nothing collected")
        elif not entry.get("cycles"):
            gaps.append(f"{name} landed 0 cycles")

    files = {p.name: _mb(p) for p in sorted(d.glob("*")) if p.is_file()}

    return {
        "corpus_dir": _rel(d) if d.exists() else None,
        "streams": rows,
        "files": files,
        "notes": manifest.get("notes") or [],
        "gex_window": gex_window_audit(d / "gexbot.jsonl", day),
    }, gaps


def gex_window_audit(path: Path, day: _date) -> dict | None:
    """Split GEX rows into in-session and out-of-session by their own timestamps.

    The session gate landed 2026-08-09 [st-a6zm]; before it, this file could hold
    a full weekend of frozen snapshots wearing the same shape as session rows.
    Reporting the split each day is how we watch the gate keep holding, and how a
    consumer of an older day learns it must filter by timestamp.
    """
    if not path.exists():
        return None
    start, until = collect_window(day, GEX_COLLECT_START_CT, GEX_COLLECT_UNTIL_CT)
    inside = outside = bad = 0
    first = last = None
    for line in path.read_text(errors="replace").splitlines():
        try:
            ts = json.loads(line).get("ts_pull_utc")
            when = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(CENTRAL)
        except Exception:                        # noqa: BLE001
            bad += 1
            continue
        first = first or when
        last = when
        if when.date() == day and start <= when.time() <= until:
            inside += 1
        else:
            outside += 1
    return {
        "rows_in_session": inside,
        "rows_outside_session": outside,
        "unparseable": bad,
        "first_ct": first.strftime("%Y-%m-%d %H:%M") if first else None,
        "last_ct": last.strftime("%Y-%m-%d %H:%M") if last else None,
    }


def gather_calls(day: _date) -> tuple[list[dict], list[str]]:
    """Calls made on the record. Hindsight measurement holds confirmation
    authority here, so an ungraded call is a gap, not a formality."""
    out, gaps = [], []
    for p in sorted(CALLS.glob(f"{day.isoformat()}-*.json")):
        rec = _read_json(p) or {}
        out.append({
            "file": p.name,
            "by": rec.get("by") or rec.get("author"),
            "claim": rec.get("claim") or rec.get("call") or rec.get("summary"),
            "outcome": rec.get("outcome") or rec.get("result"),
        })
    if not out:
        gaps.append("no calls recorded — either none were made or none were written down")
    for c in out:
        if not c["outcome"]:
            gaps.append(f"{c['file']} has no outcome recorded yet")
    return out, gaps


def gather_plan(day: _date) -> tuple[dict, list[str]]:
    """The plan of record: the morning Mancini read and the level states."""
    gaps = []
    commentary = MANCINI / f"{day.isoformat()}.jsonl"
    lines = []
    if commentary.exists():
        for line in commentary.read_text(errors="replace").splitlines():
            rec = _read_json_line(line)
            if rec:
                lines.append(rec)
    else:
        gaps.append("no Mancini commentary for the day — the morning plan is unrecorded")

    parity = PARITY / f"{day.isoformat()}.jsonl"
    return {
        "mancini_commentary": _rel(commentary) if commentary.exists() else None,
        "mancini_entries": len(lines),
        "parity_run_log": _rel(parity) if parity.exists() else None,
    }, gaps


def _read_json_line(line: str) -> dict | None:
    try:
        return json.loads(line)
    except Exception:                            # noqa: BLE001
        return None


def gather_work(day: _date) -> tuple[dict, list[str]]:
    """Commits and bead movement. This is the half that survived 2026-08-08 —
    the packet's job is to stop it being the ONLY thing that survives."""
    nxt = (day + timedelta(days=1)).isoformat()
    log = _sh("git", "log", "--no-merges",
              f"--since={day.isoformat()} 00:00", f"--until={nxt} 00:00",
              "--pretty=format:%h|%s")
    commits = []
    for line in log.splitlines():
        if "|" not in line:
            continue
        sha, subject = line.split("|", 1)
        commits.append({
            "sha": sha,
            "subject": subject,
            "beads": re.findall(r"\bst-[a-z0-9]+\b", subject),
        })
    closed = _sh("bd", "list", "--all", "--closed-after", day.isoformat(),
                 "--closed-before", nxt, "--flat")
    created = _sh("bd", "list", "--all", "--created-after", day.isoformat(),
                  "--created-before", nxt, "--flat")
    gaps = []
    if commits and not any(c["beads"] for c in commits):
        gaps.append(f"{len(commits)} commit(s) and not one bead reference — "
                    "the beads gate did not bind")
    return {
        "commits": commits,
        "beads_closed": closed.splitlines()[:20],
        "beads_created": created.splitlines()[:20],
    }, gaps


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def build(day: _date) -> dict:
    data, g1 = gather_data(day)
    calls, g2 = gather_calls(day)
    plan, g3 = gather_plan(day)
    work, g4 = gather_work(day)
    # HARD gaps are the ones worth waking someone for: a stream that collected
    # nothing (the day's tape is unusable and cannot be re-collected) or GEX rows
    # outside the session window (the gate has stopped holding). Everything else
    # — an ungraded call, a missing Mancini entry — is for the /eod skill to
    # notice, not for cron to alert on. An alert that fires most days is noise.
    gw = data.get("gex_window") or {}
    hard = list(g1)
    if gw.get("rows_outside_session"):
        hard.append(f"{gw['rows_outside_session']} GEX rows outside the collect "
                    "window — the session gate is not holding [st-a6zm]")
    return {
        "day": day.isoformat(),
        "weekday": day.strftime("%A"),
        "day_type": describe(day),
        "trading_day": is_trading_day(day),
        "close_ct": session_close_ct(day).strftime("%H:%M"),
        "generated_at_ct": datetime.now(CENTRAL).strftime("%Y-%m-%d %H:%M"),
        "data": data,
        "calls": calls,
        "plan": plan,
        "work": work,
        "gaps": g1 + g2 + g3 + g4,
        "hard_gaps": hard,
    }


def render(pk: dict) -> str:
    L: list[str] = []
    a = L.append
    a(f"# EOD packet — {pk['day']} ({pk['weekday']})")
    a("")
    a(f"*{pk['day_type']}; cash close {pk['close_ct']} CT. "
      f"Packet generated {pk['generated_at_ct']} CT.*")
    a("")
    a("> Facts only. This packet draws no conclusions and grades no calls — that")
    a("> is the /eod skill's job, and its output is a **Day Close** entry in")
    a("> DaysActivity.md. If you are reading this and no Day Close exists for")
    a("> this day, the ritual did not finish.")
    a("")

    a("## Data landed")
    a("")
    if not pk["data"]["corpus_dir"]:
        a("**No corpus directory for this day.** Nothing was collected.")
    else:
        a("| stream | cycles | errors | last pull (UTC) |")
        a("|---|---:|---:|---|")
        for r in pk["data"]["streams"]:
            a(f"| {r['stream']} | {r['cycles']} | {r['errors']} | {r['last_pull_utc']} |")
        a("")
        for r in pk["data"]["streams"]:
            if r["first_error"]:
                a(f"- `{r['stream']}` first error: {r['first_error']}")
        a("")
        a("Files: " + ", ".join(f"{k} {v}" for k, v in pk["data"]["files"].items()))
    gw = pk["data"].get("gex_window")
    if gw:
        a("")
        a(f"GEX rows: **{gw['rows_in_session']} in session**, "
          f"{gw['rows_outside_session']} outside "
          f"({gw['first_ct']} → {gw['last_ct']} CT). "
          + ("Gate holding." if not gw["rows_outside_session"]
             else "**Out-of-session rows present — the gate is not holding.**"))
    a("")

    a("## Plan of record")
    a("")
    a(f"- Mancini commentary: {pk['plan']['mancini_commentary'] or '**none**'} "
      f"({pk['plan']['mancini_entries']} entries)")
    a(f"- Live/replay parity run log: {pk['plan']['parity_run_log'] or 'none'}")
    a("")

    a("## Calls")
    a("")
    if not pk["calls"]:
        a("None recorded.")
    for c in pk["calls"]:
        a(f"- `{c['file']}` — {c['by'] or 'unattributed'}: {c['claim'] or '(no claim field)'}")
        a(f"  - outcome: {c['outcome'] or '**not yet recorded**'}")
    a("")

    a("## Work")
    a("")
    if not pk["work"]["commits"]:
        a("No commits.")
    for c in pk["work"]["commits"]:
        a(f"- `{c['sha']}` {c['subject']}")
    if pk["work"]["beads_closed"]:
        a("")
        a("Beads closed:")
        for b in pk["work"]["beads_closed"]:
            a(f"- {b}")
    if pk["work"]["beads_created"]:
        a("")
        a("Beads created:")
        for b in pk["work"]["beads_created"]:
            a(f"- {b}")
    a("")

    a("## Gaps")
    a("")
    if not pk["gaps"]:
        a("None detected.")
    hard = set(pk.get("hard_gaps") or [])
    for g in pk["gaps"]:
        a(f"- {'**[HARD]** ' if g in hard else ''}{g}")
    for g in pk.get("hard_gaps") or []:
        if g not in pk["gaps"]:
            a(f"- **[HARD]** {g}")
    a("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# audit — which trading days have a packet but no Day Close entry
# --------------------------------------------------------------------------

def day_close_exists(day: _date) -> bool:
    """True when a Day Close entry for `day` is on the record.

    Looks in the live DaysActivity.md and the archived per-day file, because
    /tap-in rolls the live file on the next session start and a day closed on
    Friday is archived by Monday.
    """
    iso = day.isoformat()
    for p in (DAYS_ACTIVITY, ARCHIVE / f"DaysActivity-{iso}.md"):
        if not p.exists():
            continue
        lines = p.read_text(errors="replace").splitlines()
        # The file belongs to `day` only if its own header says so — otherwise a
        # Day Close heading in it is some other day's, and a bare date match
        # anywhere in the prose would count a mention as a record.
        file_is_for_day = bool(lines) and iso in lines[0]
        for line in lines:
            if not line.startswith("## ") or DAY_CLOSE_MARK not in line:
                continue
            if file_is_for_day or iso in line:
                return True
    return False


def audit(back: int) -> list[dict]:
    today = datetime.now(CENTRAL).date()
    out = []
    for i in range(1, back + 1):
        d = today - timedelta(days=i)
        if not is_trading_day(d) or d < RITUAL_START:
            continue
        out.append({
            "day": d.isoformat(),
            "packet": (EOD_DIR / f"{d.isoformat()}.md").exists(),
            "day_close": day_close_exists(d),
        })
    return out


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Gather the trading day's facts [st-z92a]")
    ap.add_argument("--day", default=None, help="YYYY-MM-DD (default: today, US/Central)")
    ap.add_argument("--stdout", action="store_true", help="Print; write nothing")
    ap.add_argument("--json", action="store_true", help="Emit the JSON packet instead of markdown")
    ap.add_argument("--audit", action="store_true",
                    help="List recent trading days and whether each has a packet "
                         "and a Day Close entry")
    ap.add_argument("--back", type=int, default=10, help="--audit lookback in days (default 10)")
    ap.add_argument("--force", action="store_true",
                    help="Build a packet even for a non-trading day")
    args = ap.parse_args()

    if args.audit:
        rows = audit(args.back)
        missing = [r for r in rows if not r["day_close"]]
        for r in rows:
            mark = "ok " if r["day_close"] else "GAP"
            print(f"{mark} {r['day']}  packet={'yes' if r['packet'] else 'no '}  "
                  f"day_close={'yes' if r['day_close'] else 'NO'}")
        if missing:
            print(f"\n{len(missing)} trading day(s) with no Day Close entry: "
                  + ", ".join(r["day"] for r in missing))
        return 1 if missing else 0

    day = (_date.fromisoformat(args.day) if args.day
           else datetime.now(CENTRAL).date())
    if not is_trading_day(day) and not args.force:
        print(f"{describe(day)} — no packet. Use --force to build one anyway.")
        return 0

    pk = build(day)
    text = json.dumps(pk, indent=2) if args.json else render(pk)
    if args.stdout:
        print(text)
        return 0

    EOD_DIR.mkdir(parents=True, exist_ok=True)
    md = EOD_DIR / f"{day.isoformat()}.md"
    md.write_text(render(pk))
    (EOD_DIR / f"{day.isoformat()}.json").write_text(json.dumps(pk, indent=2))
    print(f"wrote {_rel(md)} ({len(pk['gaps'])} gap(s), "
          f"{len(pk['hard_gaps'])} hard)")
    for g in pk["gaps"]:
        print(f"  gap: {g}")
    for g in pk["hard_gaps"]:
        print(f"  HARD: {g}")
    # rc 3 = packet written, but something in it needs a human. The cron wrapper
    # alerts on 3 and stays silent on 0, which is what keeps the alert credible.
    return 3 if pk["hard_gaps"] else 0


if __name__ == "__main__":
    sys.exit(main())
