#!/usr/bin/env python3
"""Live-capture supervisor check — liveness, staleness, and the alert. [st-6qx4]

The side-effecting half of `strader/capture_health.py`. It gathers the three
inputs the pure assessor needs (live processes, the day's manifest, the previous
verdict), writes the verdict back to a state file, and — only when something is
actually wrong — appends a durable line to the corpus health log and prints a
loud banner. Assert the outcome, not the process: this is the same division
`strader/schwab_token.py` / `scripts/schwab_token_health.py` uses.

    .venv/bin/python scripts/capture_health.py              # verdict + exit code
    .venv/bin/python scripts/capture_health.py --json
    .venv/bin/python scripts/capture_health.py --porcelain  # key=value, for bash

Exit codes:
    0  healthy (ok / starting / quiet / idle)
    1  action needed (dead / stale / duplicate) — alert emitted
    2  internal error (this checker itself broke)

LIVENESS IS BY PROCESS. `pgrep -f corpus_stream_databento.py` alone also matches
the editor, the `less`, and the cron shell that merely mention the string; a
false positive there tells the supervisor everything is fine while the tape goes
missing, which is the exact failure it exists to prevent. Every candidate is
therefore filtered on `comm` being a python, the same guard
`gauge-preopen-wrapper.sh` learned to apply after 2026-07-23 [st-cm5].

WHICH DAY. The streamer resolves its corpus day ONCE at startup, so a process
launched at 23:50 is still writing into yesterday's directory at 00:05. Reading
today's manifest then would show nothing advancing and cry stale at every
midnight. We consider both candidate days and take whichever manifest was
written most recently, which needs no precise process clock — process start time
under WSL is only good to a couple of minutes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from strader.capture_health import (  # noqa: E402
    ACTIONABLE,
    CENTRAL,
    DEFAULT_GRACE_SECS,
    DEFAULT_STALE_SECS,
    DEFAULT_STREAMS,
    assess_capture,
    resolve_stream_names,
    utc_iso,
)

DEFAULT_MATCH = "corpus_stream_databento.py"
DEFAULT_CORPUS_ROOT = REPO_ROOT / "data" / "corpus"
#: Shared append-only alert audit — the same log corpus_daily.py, the pre-open
#: heartbeat and schwab_token_health.py write to. One log, one morning surface.
HEALTH_LOG_NAME = "_health.jsonl"
#: Last-check state for THIS checker, mirroring _schwab_token_health.json. Its
#: own staleness is a signal: if checked_at stops moving, the supervisor died.
STATE_NAME = "_capture_health.json"


# --------------------------------------------------------------------------
# Process discovery
# --------------------------------------------------------------------------

def find_capture_pids(match: str = DEFAULT_MATCH,
                      proc_root: str | Path = "/proc") -> list[tuple[int, float]]:
    """Live capture processes as (pid, age_seconds).

    Reads /proc directly rather than shelling out to pgrep: no external binary,
    no PATH question under cron, and a fake tree makes it trivially testable.
    A candidate must BOTH carry the match string in its command line AND have a
    python `comm` — see the module docstring for why the second half matters.

    This checker excludes ITSELF. Its own command line carries the match string
    whenever --match is passed explicitly, and counting that would report a
    healthy capture while nothing is running — precisely inverted from the
    failure it is here to catch.

    Age comes from the /proc/<pid> directory mtime, which is set at process
    creation. It is approximate (WSL clock adjustments move it by a minute or
    two) and is used only for the launch grace period, where that is harmless.
    """
    root = Path(proc_root)
    out: list[tuple[int, float]] = []
    now = datetime.now().timestamp()
    self_pid = os.getpid()
    self_marker = Path(__file__).name
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return out
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == self_pid:
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", "replace")
        except OSError:
            continue
        if match not in cmdline or self_marker in cmdline:
            continue
        try:
            comm = (entry / "comm").read_text().strip()
        except OSError:
            comm = ""
        if not (comm.startswith("python") or comm.endswith("python")):
            continue
        try:
            age = max(now - entry.stat().st_mtime, 0.0)
        except OSError:
            age = 0.0
        out.append((int(entry.name), age))
    return out


# --------------------------------------------------------------------------
# Corpus I/O
# --------------------------------------------------------------------------

def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _manifest_for(corpus_root: Path, day: _date) -> dict | None:
    return _read_json(corpus_root / day.isoformat() / "manifest.json")


def _newest_pull(manifest: dict | None, names: list[str]) -> str:
    if not manifest:
        return ""
    streams = manifest.get("streams") or {}
    return max((str((streams.get(n) or {}).get("last_pull_utc") or "")
                for n in names), default="")


def resolve_day(corpus_root: Path, now_ct: datetime, pid_ages: list[tuple[int, float]],
                names: list[str]) -> _date:
    """The corpus day the RUNNING capture is writing into (see module docstring).

    Candidates are today and the day the oldest live process started on; the one
    whose manifest was touched most recently wins, falling back to today.
    """
    today = now_ct.date()
    candidates = {today}
    for _pid, age in pid_ages:
        candidates.add((now_ct - timedelta(seconds=age)).date())
    if len(candidates) == 1:
        return today
    best, best_key = today, ""
    for cand in sorted(candidates):
        key = _newest_pull(_manifest_for(corpus_root, cand), names)
        if key > best_key:
            best, best_key = cand, key
    return best


def _write_state(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic


def _append_health(path: Path, record: dict) -> None:
    """One line on the shared corpus health log. Record shape matches
    scripts/corpus_daily.py `emit_alert` / `_append_health` exactly — same log,
    same reader, no new format to learn."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def emit_alert(health_log: Path, kind: str, message: str, detail: dict) -> None:
    record = {"ts": utc_iso(datetime.now(CENTRAL)), "level": "alert",
              "kind": kind, "message": message, **detail}
    _append_health(health_log, record)
    print(f"\n{'!' * 72}\nCAPTURE ALERT [{kind}]: {message}\n{'!' * 72}",
          file=sys.stderr)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--streams", default=",".join(DEFAULT_STREAMS),
                    help="Streams to watch: streamer keys (es,es-mbp1) or "
                         "manifest names (default: es,es-mbp1)")
    ap.add_argument("--stale-secs", type=float, default=DEFAULT_STALE_SECS,
                    help=f"Quiet seconds before a stream is stale (default {DEFAULT_STALE_SECS:.0f})")
    ap.add_argument("--grace-secs", type=float, default=DEFAULT_GRACE_SECS,
                    help=f"Post-launch grace before an empty manifest counts (default {DEFAULT_GRACE_SECS:.0f})")
    ap.add_argument("--window-start", default="00:00",
                    help="CT clock time a capture is expected from (default 00:00)")
    ap.add_argument("--window-end", default="23:59",
                    help="CT clock time a capture is expected until (default 23:59)")
    ap.add_argument("--corpus-root", default=str(DEFAULT_CORPUS_ROOT))
    ap.add_argument("--state", default=None, help=f"State file (default <corpus-root>/{STATE_NAME})")
    ap.add_argument("--health-log", default=None,
                    help=f"Alert log (default <corpus-root>/{HEALTH_LOG_NAME})")
    ap.add_argument("--proc-root", default="/proc")
    ap.add_argument("--match", default=DEFAULT_MATCH,
                    help="Command-line substring identifying the capture process")
    ap.add_argument("--now", default=None,
                    help="Pin the clock to 'YYYY-MM-DDTHH:MM' Central (tests)")
    ap.add_argument("--no-alert", action="store_true",
                    help="Assess and record, but emit no alert (quiet probe)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--porcelain", action="store_true",
                    help="key=value lines for shell callers")
    ap.add_argument("--record-restart", metavar="DETAIL", default=None,
                    help="Log that the supervisor relaunched the capture, bump "
                         "the day's restart counter, and exit (no assessment)")


def _paths(args) -> tuple[Path, Path, Path]:
    corpus_root = Path(args.corpus_root)
    state = Path(args.state) if args.state else corpus_root / STATE_NAME
    health = Path(args.health_log) if args.health_log else corpus_root / HEALTH_LOG_NAME
    return corpus_root, state, health


def _record_restart(args) -> int:
    """Append the restart to the audit log and bump the counter in state."""
    _corpus_root, state_path, health_path = _paths(args)
    now_ct = (datetime.fromisoformat(args.now).replace(tzinfo=CENTRAL)
              if args.now else datetime.now(CENTRAL))
    state = _read_json(state_path) or {}
    day_iso = state.get("day") or now_ct.date().isoformat()
    count = int(state.get("restarts") or 0) if state.get("restarts_day") == day_iso else 0
    state["restarts"] = count + 1
    state["restarts_day"] = day_iso
    state["last_restart_utc"] = utc_iso(now_ct)
    state["last_restart_detail"] = args.record_restart
    _write_state(state_path, state)
    emit_alert(health_path, "capture_restarted",
               f"Live capture was relaunched by the supervisor: {args.record_restart}",
               {"day": day_iso, "restarts_today": count + 1})
    print(f"capture restart recorded (#{count + 1} on {day_iso})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live-capture supervisor check [st-6qx4]")
    _add_args(ap)
    args = ap.parse_args(argv)

    try:
        if args.record_restart is not None:
            return _record_restart(args)

        corpus_root, state_path, health_path = _paths(args)
        now_ct = (datetime.fromisoformat(args.now).replace(tzinfo=CENTRAL)
                  if args.now else datetime.now(CENTRAL))
        names = resolve_stream_names(args.streams.split(","))

        pid_ages = find_capture_pids(args.match, args.proc_root)
        day = resolve_day(corpus_root, now_ct, pid_ages, names)

        health = assess_capture(
            now_ct,
            day=day,
            manifest=_manifest_for(corpus_root, day),
            pids=[p for p, _ in pid_ages],
            capture_age_secs=min((a for _, a in pid_ages), default=None),
            prev=_read_json(state_path),
            streams=names,
            stale_secs=args.stale_secs,
            grace_secs=args.grace_secs,
            window_start=args.window_start,
            window_end=args.window_end,
        )
        _write_state(state_path, health.to_dict())
    except Exception as e:  # the checker itself broke — distinct from a bad verdict
        print(f"[capture-health] INTERNAL ERROR: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(health.to_dict(), indent=2))
    elif args.porcelain:
        print(f"status={health.status}")
        print(f"expected={int(health.expected)}")
        print(f"pids={' '.join(str(p) for p in health.pids)}")
        print(f"all_stale={int(health.all_stale)}")
        print(f"actionable={int(health.actionable)}")
        print(f"day={health.day}")
    else:
        print(f"capture: {health.status.upper()} — {health.message}")
        for name, obs in health.streams.items():
            print(f"  {name}: cycles={obs['cycles']} quiet={obs['quiet_secs']:.0f}s"
                  + (" STALE" if obs["stale"] else ""))

    if health.actionable and not args.no_alert:
        emit_alert(health_path, f"capture_{health.status}", health.message,
                   {"day": health.day, "pids": health.pids,
                    "since_utc": health.since_utc,
                    "stale_streams": health.stale_streams})
    return 1 if health.status in ACTIONABLE else 0


if __name__ == "__main__":
    sys.exit(main())
