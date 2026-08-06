"""Level-state tracker — the letter's levels against the live tape. [st-qih1]

Item 3 of the st-pjp8 review (ruled 2026-08-06). ``overnight.py`` runs the
touched/held/broken/reclaimed machine once, at parse time, over the overnight
window. This module runs the SAME machine — literally the same function,
``overnight.compute_interactions`` — continuously through the session and
writes the result to a small JSON file that anything can read. "What happened
to 7549?" becomes a file lookup, not an agent investigation.

Design: every tick re-fetches the full window (letter write-time 4pm ET the
prior day → now, Schwab /ES 5-minute, extended hours) and recomputes all
states from scratch. No incremental state to drift, no divergence possible
between live and replay — replay IS the live path fed from a file. A tick is
one API call and sub-second compute; once a minute is far below any limit.

State file: ``data/level_state/current.json`` (atomic replace), plus a per-day
copy ``data/level_state/<day>.json``. Every state transition carries the
candle row behind it (``events``), so every claim the file makes is checkable
against the tape — a tracker nobody can score is the artifact class the
2026-08-04 audit warned about.

Lifecycle:
  --once            single tick and exit (smoke, cron health checks)
  --loop            tick every --interval seconds until session end
                    (15:15 CT) or SIGTERM; pidfile prevents double loops
  --replay FILE     compute from a candle-fixture JSON instead of Schwab,
                    write state, exit — the regression hook
No parse for the day yet → the loop waits and says so (the 08:15 cron alerts
readiness; Steve may not have parsed yet). Repeated fetch failures alert once
per streak via strader.alerts (non-urgent), then keep retrying.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import overnight
from .schema import ParseResult

logger = logging.getLogger("runbook.mancini")

REPO = Path(__file__).resolve().parents[2]
PARSED_ROOT = Path(__file__).resolve().parent / "parsed"
STATE_ROOT = REPO / "data" / "level_state"

SESSION_END_CT = (15, 15)          # stop ticking after 15:15 CT
FAILURE_ALERT_STREAK = 5           # consecutive failed ticks before one alert


def _now_ct() -> datetime:
    return datetime.now(tz=overnight.CENTRAL)


def _load_parse(day: str, parsed_root: Path) -> ParseResult | None:
    path = parsed_root / f"{day}.json"
    if not path.exists():
        return None
    return ParseResult.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_state(result: ParseResult, candles: list[dict],
                tolerance: float = overnight.DEFAULT_TOLERANCE_PTS) -> dict:
    """One pass of the machine over ``candles`` → the serializable state doc."""
    interactions = overnight.compute_interactions(result.levels, candles,
                                                  tolerance)
    last_price = candles[-1]["close"] if candles else None
    levels = []
    for it in interactions:
        levels.append({
            "price": it.price,
            "kind": it.kind,
            "major": it.major,
            "state": it.state,
            "first_touch": it.first_touch,
            "n_touches": it.touches,
            "n_defenses": it.defenses,
            "last_event_ts": it.last_event_ts,
            "distance_from_price": (round(last_price - it.price, 2)
                                    if last_price is not None else None),
            "break_time": it.break_time,
            "reclaim_time": it.reclaim_time,
            "extreme": it.extreme,
            "events": it.events,
        })

    def _prices(state: str) -> list[float]:
        return [l["price"] for l in levels if l["state"] == state]

    untested = [l for l in levels if l["state"] == "untouched"]
    return {
        "day": result.date,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "source": "schwab:/ES:5m:eth",
        "tolerance_pts": tolerance,
        "window": {
            "start": overnight._iso_utc(candles[0]["datetime"]) if candles else None,
            "end": overnight._iso_utc(candles[-1]["datetime"]) if candles else None,
            "candle_count": len(candles),
        },
        "last_price": last_price,
        "levels": levels,
        "rollups": {
            "broken": _prices("broken"),
            "reclaimed": _prices("reclaimed"),
            "tested_held": _prices("tested-held"),
            "untested_above": sorted(l["price"] for l in untested
                                     if last_price is not None
                                     and l["price"] > last_price),
            "untested_below": sorted((l["price"] for l in untested
                                      if last_price is not None
                                      and l["price"] < last_price),
                                     reverse=True),
        },
    }


def write_state(state: dict, state_root: Path) -> Path:
    """Atomic write: current.json plus the per-day copy."""
    state_root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2)
    for name in ("current.json", f"{state['day']}.json"):
        tmp = state_root / f".{name}.tmp"
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, state_root / name)
    return state_root / "current.json"


def tick(day: str, parsed_root: Path = PARSED_ROOT,
         state_root: Path = STATE_ROOT,
         fetch=None, candles: list[dict] | None = None) -> tuple[bool, str]:
    """One cycle: load parse → get candles → compute → write. Returns (ok, note)."""
    result = _load_parse(day, parsed_root)
    if result is None:
        return False, f"no parse yet for {day} ({parsed_root}/{day}.json)"
    if candles is None:
        start = overnight.letter_window_start(day)
        candles = (fetch or overnight.fetch_overnight_candles)(start)
    state = build_state(result, candles)
    path = write_state(state, state_root)
    r = state["rollups"]
    return True, (f"{len(state['levels'])} levels @ {state['last_price']:g}: "
                  f"{len(r['broken'])} broken, {len(r['reclaimed'])} reclaimed, "
                  f"{len(r['tested_held'])} held, "
                  f"{len(r['untested_above']) + len(r['untested_below'])} "
                  f"untested → {path}")


class _PidLock:
    """No zombie loops: one tracker per state-root, stale locks reaped."""

    def __init__(self, state_root: Path):
        self.path = state_root / "tracker.pid"

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                pid = int(self.path.read_text().strip())
                os.kill(pid, 0)          # raises if not running
                return False             # live tracker owns the lock
            except (ValueError, ProcessLookupError, PermissionError):
                logger.warning("reaping stale pidfile %s", self.path)
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        return True

    def release(self) -> None:
        try:
            if int(self.path.read_text().strip()) == os.getpid():
                self.path.unlink()
        except (OSError, ValueError):
            pass


def loop(day: str, interval: int, parsed_root: Path = PARSED_ROOT,
         state_root: Path = STATE_ROOT) -> int:
    lock = _PidLock(state_root)
    if not lock.acquire():
        print(f"another tracker is already running ({lock.path})",
              file=sys.stderr)
        return 1

    stop = {"flag": False}

    def _sigterm(_sig, _frm):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)

    fail_streak = 0
    alerted = False
    logger.info("tracker loop start: day=%s interval=%ss", day, interval)
    try:
        while not stop["flag"]:
            now_ct = _now_ct()
            if (now_ct.hour, now_ct.minute) >= SESSION_END_CT:
                logger.info("session end (%02d:%02d CT) — tracker exiting",
                            *SESSION_END_CT)
                break
            try:
                ok, note = tick(day, parsed_root, state_root)
                if ok:
                    fail_streak, alerted = 0, False
                    logger.info("tick: %s", note)
                else:
                    logger.info("waiting: %s", note)   # no parse yet — benign
            except Exception as e:  # noqa: BLE001 — a tick must not kill the loop
                fail_streak += 1
                logger.warning("tick failed (%d in a row): %s", fail_streak, e)
                if fail_streak >= FAILURE_ALERT_STREAK and not alerted:
                    alerted = True
                    try:
                        from strader.alerts import send as alert_send
                        alert_send("Level tracker degraded",
                                   f"{fail_streak} consecutive tick failures "
                                   f"(last: {e}). Still retrying; level-state "
                                   "file is stale.", urgent=False)
                    except Exception as ae:  # noqa: BLE001
                        logger.warning("degradation alert failed: %s", ae)
            # Sleep in 1s slices so SIGTERM lands promptly.
            for _ in range(interval):
                if stop["flag"]:
                    break
                time.sleep(1)
    finally:
        lock.release()
    logger.info("tracker loop end")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mancini level-state tracker [st-qih1]")
    ap.add_argument("--day", help="plan-day YYYY-MM-DD (default: today CT)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="single tick, exit")
    mode.add_argument("--loop", action="store_true",
                      help="tick every --interval until session end / SIGTERM")
    mode.add_argument("--replay", metavar="CANDLES_JSON",
                      help="compute from a candle fixture file, write, exit")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--parsed-root", type=Path, default=PARSED_ROOT)
    ap.add_argument("--state-root", type=Path, default=STATE_ROOT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    day = args.day or _now_ct().date().isoformat()

    if args.loop:
        return loop(day, args.interval, args.parsed_root, args.state_root)

    candles = None
    if args.replay:
        candles = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        if isinstance(candles, dict):
            candles = candles["candles"]
    try:
        ok, note = tick(day, args.parsed_root, args.state_root, candles=candles)
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {e}", file=sys.stderr)
        return 2
    print(("OK: " if ok else "WAITING: ") + note)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
