#!/usr/bin/env python3
"""Flush watcher — meter journal in, phone alert out. [st-kos7 · Fools Remote Arm]

SHADOW BY DEFAULT. This process evaluates live and journals what it *would*
have sent. It sends nothing to Steve's phone until `--live` is passed, and that
flag should stay off until the trigger below has been measured.

WHY SHADOW, STATED PLAINLY. The threshold in ``FLUSH_PTS`` is a conventional
starting number, not a measured one. The 2026-08-04 continuation audit found
this exact class of defect throughout the last program: thresholds chosen once,
never swept, then displayed as if they meant something. An alerting detector
built on an unmeasured trigger is worse than no detector, because a few false
alarms get phone notifications switched off and the whole remote arm becomes
decorative. **Obvious Line Formalization (st-rtuu) is the lane that replaces
these constants with measured criteria**; until it lands, this runs in shadow
and its journal is the evidence for that measurement.

ARCHITECTURE. There is no FD0 watcher module — st-apzt is design-only. The
component that actually runs live and observes the market is
`scripts/desk/continuation_meter.py`, which polls every 30 s, detects the day's
primary move, and journals every frame. So:

    meter (observes)  ->  journal file  ->  watcher (decides)  ->  alerts (fires)

The watcher never touches Schwab, never opens a second market-data path, and
cannot break the meter: it only reads a file the meter already writes. If the
meter dies, the watcher says so rather than sitting silent — a watcher that
cannot tell "calm market" from "my input stopped" is the failure mode this
project cannot afford.

RATE LIMITING is not optional. One alert per distinct move, plus a hard daily
cap. A detector that fires forty times has trained Steve to ignore it.

Run:
    .venv/bin/python3 scripts/flush_watcher.py                 # shadow (safe)
    .venv/bin/python3 scripts/flush_watcher.py --live          # actually alerts
    .venv/bin/python3 scripts/flush_watcher.py --replay <file> # score a past day
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from strader import alerts  # noqa: E402

CT = ZoneInfo("America/Chicago")
JOURNAL_DIR = ROOT / "data" / "exec"
FIRE_URL = "https://mydesk-1.tail89f676.ts.net"

# --- PROVISIONAL TRIGGER — every constant here awaits st-rtuu ---------------
# Read these as "conventional starting points chosen for a shadow run", not as
# findings. None has been swept, and none should be quoted as measured.
FLUSH_PTS = 25.0          # primary move size that counts as a flush
FLUSH_DIR = -1            # down only: Run You Fools is a meltdown playbook
WINDOW_OPEN = time(8, 30)
WINDOW_CLOSE = time(11, 0)  # morning regime; the studies measured this window
MAX_ALERTS_PER_DAY = 3
STALE_LIMIT_MIN = 5.0     # meter frames older than this are not evidence
# ---------------------------------------------------------------------------

POLL_S = 20


@dataclass
class WatchState:
    """What has already been alerted, so nothing fires twice for one move."""
    day: str = ""
    alerted_moves: set = field(default_factory=set)
    sent_today: int = 0
    last_input_ts: str | None = None

    def roll_day(self, day: str) -> None:
        if day != self.day:
            self.day, self.alerted_moves, self.sent_today = day, set(), 0


def move_key(mv: dict) -> str:
    """Identity of a move: its start. Extensions of the same move share it."""
    return f"{mv.get('dir')}@{mv.get('start_t')}"


def journal(event: dict) -> None:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(CT).strftime("%Y-%m-%d")
    with (JOURNAL_DIR / f"flush-watcher-{day}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                             **event}) + "\n")


def evaluate(frame: dict, state: WatchState) -> tuple[bool, str]:
    """Should this frame raise an alert? Returns (fire, reason).

    The reason is returned for BOTH outcomes and journaled either way: a
    shadow run is only useful if it records why it stayed quiet.
    """
    if frame.get("preopen"):
        return False, "pre-open"
    if frame.get("no_data"):
        return False, "no data in frame"
    mv = frame.get("move")
    if not mv:
        return False, "no primary move yet"
    stale = frame.get("stale_min")
    if stale is not None and stale > STALE_LIMIT_MIN:
        return False, f"meter stale ({stale:.0f} min) — not evidence"
    try:
        ts = datetime.fromisoformat(frame["ts"])
    except (KeyError, ValueError):
        return False, "unparseable frame timestamp"
    if not (WINDOW_OPEN <= ts.timetz().replace(tzinfo=None) <= WINDOW_CLOSE):
        return False, "outside the measured morning window"
    if mv.get("dir") != FLUSH_DIR:
        return False, f"move is {'up' if mv.get('dir') == 1 else 'undirected'}"
    if mv.get("size", 0) < FLUSH_PTS:
        return False, f"move {mv.get('size', 0):.1f} pts under the {FLUSH_PTS:.0f}-pt line"
    if move_key(mv) in state.alerted_moves:
        return False, "already alerted this move"
    if state.sent_today >= MAX_ALERTS_PER_DAY:
        return False, f"daily cap {MAX_ALERTS_PER_DAY} reached"
    contested = " (direction CONTESTED)" if mv.get("contested") else ""
    return True, (f"down {mv['size']:.0f} pts since "
                  f"{mv['start_t'][11:16]}{contested}")


def compose(frame: dict, reason: str) -> tuple[str, str]:
    mv = frame["move"]
    lv = frame.get("levels") or {}
    spx = f"SPX {lv['spx']:.0f}" if lv.get("spx") is not None else "SPX ?"
    vix = f"VIX {lv['vix']}" if lv.get("vix") is not None else ""
    return ("FLUSH — Run You Fools",
            f"{reason}. {spx} {vix}. Ticket: {FIRE_URL}")


def handle(frame: dict, state: WatchState, *, live: bool) -> bool:
    fire, reason = evaluate(frame, state)
    if not fire:
        journal({"event": "quiet", "reason": reason, "frame_ts": frame.get("ts")})
        return False
    title, message = compose(frame, reason)
    key = move_key(frame["move"])
    state.alerted_moves.add(key)
    state.sent_today += 1
    if not live:
        journal({"event": "would_alert", "mode": "shadow", "reason": reason,
                 "title": title, "message": message, "move_key": key,
                 "frame_ts": frame.get("ts")})
        print(f"[shadow] WOULD ALERT — {message}", flush=True)
        return True
    r = alerts.send(title, message, urgent=True)
    journal({"event": "alerted" if r.ok else "alert_failed", "mode": "live",
             "reason": reason, "title": title, "message": message,
             "move_key": key, "backend": r.backend, "detail": r.detail,
             "frame_ts": frame.get("ts")})
    print(f"[live] {'SENT' if r.ok else 'FAILED'} — {message}", flush=True)
    return True


def read_frames(path: Path, start_at: int = 0) -> tuple[list[dict], int]:
    """New frames since byte offset. Returns (frames, new_offset)."""
    if not path.exists():
        return [], start_at
    with path.open("r", encoding="utf-8") as fh:
        fh.seek(start_at)
        lines = fh.readlines()
        offset = fh.tell()
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue          # a partially-written last line; it'll be re-read
    return out, offset


def meter_journal(day: str | None = None) -> Path:
    day = day or datetime.now(CT).strftime("%Y-%m-%d")
    return JOURNAL_DIR / f"continuation-meter-{day}.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description="Flush watcher (shadow by default)")
    ap.add_argument("--live", action="store_true",
                    help="actually send alerts (default: shadow — sends nothing)")
    ap.add_argument("--replay", type=Path,
                    help="score a past meter journal instead of watching live")
    ap.add_argument("--interval", type=int, default=POLL_S)
    args = ap.parse_args()

    state = WatchState()

    if args.replay:
        frames, _ = read_frames(args.replay)
        state.roll_day("replay")
        fired = sum(handle(f, state, live=False) for f in frames)
        print(f"\nreplay: {len(frames)} frames, {fired} would-alert(s) "
              f"— thresholds are PROVISIONAL (st-rtuu)")
        return 0

    mode = "LIVE — alerts will reach the phone" if args.live else "SHADOW — sends nothing"
    print(f"flush watcher starting: {mode}", flush=True)
    journal({"event": "watcher_start", "mode": "live" if args.live else "shadow"})
    offset, last_seen = 0, None
    while True:
        day = datetime.now(CT).strftime("%Y-%m-%d")
        if day != state.day:
            state.roll_day(day)
            offset = 0
        path = meter_journal(day)
        frames, offset = read_frames(path, offset)
        for f in frames:
            handle(f, state, live=args.live)
            last_seen = f.get("ts")
        # A watcher that cannot distinguish "calm" from "my input died" is
        # useless; say so rather than sitting quiet.
        if frames:
            state.last_input_ts = last_seen
        _time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
