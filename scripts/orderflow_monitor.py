#!/usr/bin/env python3
"""Orderflow Doctrine Monitor [st-2n69].

Mechanical event detection over the GexBot capture stream
(data/corpus/<date>/gexbot.jsonl, written by corpus_poll_gexbot.py).
Detects the objective patterns from the orderflow doctrine
(docs/gexbot/screenshots/orderflow-capture-checklist.md) and journals
them. Interpretation is out of scope: no direction calls, no alerts.

Modes:
  --follow            tail today's corpus file live (default)
  --replay YYYY-MM-DD run the full day's file once and exit; the
                      journal for that day is REWRITTEN from scratch

Outputs:
  data/derived/orderflow-events/<date>.jsonl   one JSON object per event
  stdout                                       terse feed for a tmux pane
  /var/moo/state/orderflow-monitor.json        heartbeat, every cycle

Health semantics (see docs/gexbot/orderflow-monitor.md):
  heartbeat ts stale            -> the monitor died
  ts fresh, last_pull_ts frozen
  during RTH                    -> the collector died (monitor is fine)

Follow mode exits 0 at midnight Central (day rollover); the launcher
detects the dead process and restarts onto the new day's file.
Event writes are deduplicated against the existing journal, so a
restart mid-day re-derives detector state without duplicating events.

Event types:
  CVR_SPIKE_UP / CVR_SPIKE_DOWN    convexity orderflow print beyond threshold
                                   (UP = the doctrine's "brake")
  GEX_SPIKE_CALL / GEX_SPIKE_PUT   gex orderflow print beyond threshold
  TWO_SIGNAL                       brake + gex spike within max_gap_pulls
  NETCVX_DUMP_START / _END         zcvr falls dump_drop off its rolling max
  NETCVX_RAMP_START / _END         mirror of dump
  NETCVX_VTURN                     sharp rise off the min while in a dump
  WALL_MOVE                        call/put wall shifts >= move_pts (anchored:
                                   slow creep accumulates until it emits)
  INVERSION_ON / INVERSION_OFF     call wall below put wall
  SPOT_CROSS                       spot crosses a wall (spot's own motion
                                   only; wall moves re-seed, never emit)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from market.corpus.paths import central_date, gexbot_path, open_corpus_text  # noqa: E402

OF_ENDPOINT = "/SPX/orderflow/orderflow"


# ---------------------------------------------------------------- helpers

def log(msg: str) -> None:
    print(msg, flush=True)


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def parse_pull(line: str, fields: dict) -> dict | None:
    """Extract the fields the monitor needs from one corpus line.

    Field names for the pane series come from config["fields"] — the
    panes run at expiry=latest (0DTE), so net convexity is zcvr and the
    wall lines are zero_mcall/zero_mput (verified against the rendered
    chart 2026-08-07; ocvr is all-expiry and diverges completely).

    Returns None (and no exception) for malformed lines, non-orderflow
    pulls, or pulls where the orderflow endpoint errored.
    """
    try:
        rec = json.loads(line)
        resp = rec["data"]["responses"].get(OF_ENDPOINT)
        if not isinstance(resp, dict):
            return None
        ts = rec["ts_pull_utc"]
        if not isinstance(ts, str):
            return None
        summary = rec["data"].get("summary") or {}
        return {
            "ts": ts,
            "spot": float(resp["spot"]),
            "cvr_of": float(resp["cvroflow"]),
            "gex_of": float(resp["gexoflow"]),
            "netcvx": float(resp[fields["netcvx"]]),
            "m_call": _maybe_float(resp.get(fields["wall_call"],
                                            summary.get("major_positive"))),
            "m_put": _maybe_float(resp.get(fields["wall_put"],
                                           summary.get("major_negative"))),
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _maybe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- detector

class Detector:
    """Stateful pattern detector. Feed pulls in order; collects events."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        w = cfg["spike"]["window_pulls"]
        self.cvr_window: deque[float] = deque(maxlen=w)
        self.gex_window: deque[float] = deque(maxlen=w)
        self.spot_window: deque[float] = deque(
            maxlen=cfg["two_signal"]["trend_lookback_pulls"])
        self.netcvx_window: deque[float] = deque(
            maxlen=cfg["netcvx"]["lookback_pulls"])
        self.recent_brakes: deque[int] = deque(maxlen=8)   # pull indices
        self.recent_gex_spikes: deque[tuple[int, float]] = deque(maxlen=8)
        self.netcvx_state = "NEUTRAL"   # NEUTRAL | DUMP | RAMP
        self.netcvx_extreme: float | None = None  # min in dump / max in ramp
        self.netcvx_extreme_idx = 0
        self.vturn_emitted = False
        self.inverted: bool | None = None
        # anchored wall state: eff moves ONLY via an emitted WALL_MOVE, so
        # sub-threshold creep accumulates against the anchor until it emits
        self.walls: dict[str, dict] = {
            "call": {"eff": None, "cand": None, "count": 0, "side": None},
            "put": {"eff": None, "cand": None, "count": 0, "side": None},
        }
        self.idx = 0
        self.last_ts: str | None = None
        self.pulls_seen = 0
        self.pulls_skipped = 0
        self.pulls_filtered = 0     # RTH-filtered, counted by the run loop
        self._append_cvr: float = 0.0
        self._append_gex: float = 0.0

    # -- public -----------------------------------------------------------

    def feed(self, pull: dict) -> list[dict]:
        # out-of-order / duplicate guard: the corpus is append-only and
        # monotonic; anything else is a producer bug we refuse to detect on
        if self.last_ts is not None and pull["ts"] <= self.last_ts:
            self.pulls_skipped += 1
            return []
        self.last_ts = pull["ts"]
        self.idx += 1
        self.pulls_seen += 1
        events: list[dict] = []
        events += self._spikes(pull)
        events += self._two_signal(pull)
        events += self._netcvx(pull)
        events += self._walls(pull)
        # windows are appended AFTER detection (deliberate: a print never
        # sets its own threshold); spikes enter clamped at the threshold
        # they beat so the bar adapts to regime, not to its own output
        self.cvr_window.append(self._append_cvr)
        self.gex_window.append(self._append_gex)
        self.spot_window.append(pull["spot"])
        self.netcvx_window.append(pull["netcvx"])
        for ev in events:
            ev["ts"] = pull["ts"]
            ev["spot"] = pull["spot"]
        return events

    # -- individual detectors ---------------------------------------------

    def _threshold(self, window: deque[float], floor: float) -> float:
        s = self.cfg["spike"]
        if len(window) < s["min_warmup"]:
            return floor          # floor applies from pull one
        p95 = percentile(sorted(window), 0.95)
        return max(floor, s["pctl_mult"] * p95)

    def _spikes(self, pull: dict) -> list[dict]:
        s = self.cfg["spike"]
        events = []
        thr_cvr = self._threshold(self.cvr_window, s["cvr_abs_floor"])
        self._append_cvr = abs(pull["cvr_of"])
        if self._append_cvr > thr_cvr:
            kind = "CVR_SPIKE_UP" if pull["cvr_of"] > 0 else "CVR_SPIKE_DOWN"
            events.append({"type": kind, "value": pull["cvr_of"],
                           "threshold": round(thr_cvr, 2)})
            self._append_cvr = thr_cvr
            if kind == "CVR_SPIKE_UP":
                self.recent_brakes.append(self.idx)
        thr_gex = self._threshold(self.gex_window, s["gex_abs_floor"])
        self._append_gex = abs(pull["gex_of"])
        if self._append_gex > thr_gex:
            kind = "GEX_SPIKE_CALL" if pull["gex_of"] > 0 else "GEX_SPIKE_PUT"
            events.append({"type": kind, "value": pull["gex_of"],
                           "threshold": round(thr_gex, 2)})
            self._append_gex = thr_gex
            self.recent_gex_spikes.append((self.idx, pull["gex_of"]))
        return events

    def _two_signal(self, pull: dict) -> list[dict]:
        gap = self.cfg["two_signal"]["max_gap_pulls"]
        # pair the CLOSEST brake/gex combination that completes on this
        # pull; consume only the two paired entries so a nearby third
        # spike stays available for its own pair
        best = None
        for b in self.recent_brakes:
            for gi, gv in self.recent_gex_spikes:
                if abs(b - gi) <= gap and max(b, gi) == self.idx:
                    d = abs(b - gi)
                    if best is None or d < best[0]:
                        best = (d, b, gi, gv)
        if best is None:
            return []
        d, b, gi, gv = best
        self.recent_brakes.remove(b)
        self.recent_gex_spikes.remove((gi, gv))
        trend = 0.0
        if len(self.spot_window) >= 2:
            trend = pull["spot"] - self.spot_window[0]
        return [{
            "type": "TWO_SIGNAL",
            "gex_value": gv,
            "gex_side": "call" if gv > 0 else "put",
            "trend_pts": round(trend, 2),
            "gap_pulls": d,
        }]

    def _netcvx(self, pull: dict) -> list[dict]:
        n = self.cfg["netcvx"]
        v = pull["netcvx"]
        events = []
        # warmup: never arm off a thin window (a fresh window after an END
        # needs state_warmup_pulls of post-recovery data before re-arming)
        if (self.netcvx_state == "NEUTRAL"
                and len(self.netcvx_window) < n["state_warmup_pulls"]):
            return []
        roll_max = max(self.netcvx_window)
        roll_min = min(self.netcvx_window)
        ended = False
        if self.netcvx_state == "NEUTRAL":
            if roll_max - v >= n["dump_drop"]:
                self.netcvx_state = "DUMP"
                self.netcvx_extreme, self.netcvx_extreme_idx = v, self.idx
                self.vturn_emitted = False
                events.append({"type": "NETCVX_DUMP_START", "value": v,
                               "from_rolling_max": round(roll_max, 2),
                               "threshold": n["dump_drop"]})
            elif v - roll_min >= n["ramp_rise"]:
                self.netcvx_state = "RAMP"
                self.netcvx_extreme, self.netcvx_extreme_idx = v, self.idx
                events.append({"type": "NETCVX_RAMP_START", "value": v,
                               "from_rolling_min": round(roll_min, 2),
                               "threshold": n["ramp_rise"]})
        elif self.netcvx_state == "DUMP":
            if v < self.netcvx_extreme:
                self.netcvx_extreme, self.netcvx_extreme_idx = v, self.idx
            rise = v - self.netcvx_extreme
            if (not self.vturn_emitted and rise >= n["vturn_rise"]
                    and self.idx - self.netcvx_extreme_idx <= n["vturn_pulls"]):
                self.vturn_emitted = True
                events.append({"type": "NETCVX_VTURN", "value": v,
                               "off_min": round(self.netcvx_extreme, 2),
                               "threshold": n["vturn_rise"]})
            if rise >= n["dump_clear"] + n["dump_drop"] / 2:
                self.netcvx_state = "NEUTRAL"
                ended = True
                events.append({"type": "NETCVX_DUMP_END", "value": v,
                               "min_reached": round(self.netcvx_extreme, 2)})
        elif self.netcvx_state == "RAMP":
            if v > self.netcvx_extreme:
                self.netcvx_extreme, self.netcvx_extreme_idx = v, self.idx
            fall = self.netcvx_extreme - v
            if fall >= n["ramp_clear"] + n["ramp_rise"] / 2:
                self.netcvx_state = "NEUTRAL"
                ended = True
                events.append({"type": "NETCVX_RAMP_END", "value": v,
                               "max_reached": round(self.netcvx_extreme, 2)})
        if ended:
            # a regime that just ended must not re-arm off its own
            # excursion still sitting in the window; measure the next
            # regime from post-recovery data only
            self.netcvx_window.clear()
        return events

    def _wall_effective(self, label: str, cur: float | None) -> tuple | None:
        """Anchored wall debounce; returns (old, new) when the level
        genuinely shifts (>= move_pts off the anchor, persisted
        persist_pulls pulls). The anchor NEVER drifts silently — creep
        accumulates against it until it earns a WALL_MOVE."""
        w = self.cfg["walls"]
        st = self.walls[label]
        if cur is None:
            return None
        if st["eff"] is None:
            st["eff"] = cur
            return None
        if abs(cur - st["eff"]) < w["move_pts"]:
            st["cand"], st["count"] = None, 0
            return None
        if st["cand"] is not None and abs(cur - st["cand"]) < w["move_pts"]:
            st["count"] += 1
        else:
            st["cand"], st["count"] = cur, 1
        if st["count"] >= w["persist_pulls"]:
            old, st["eff"] = st["eff"], cur
            st["cand"], st["count"] = None, 0
            return (old, cur)
        return None

    def _walls(self, pull: dict) -> list[dict]:
        w = self.cfg["walls"]
        events = []
        for key, label in (("m_call", "call"), ("m_put", "put")):
            moved = self._wall_effective(label, pull[key])
            st = self.walls[label]
            eff = st["eff"]
            if eff is None:
                continue
            side = 1 if pull["spot"] > eff + w["cross_hysteresis_pts"] else (
                -1 if pull["spot"] < eff - w["cross_hysteresis_pts"] else None)
            if moved:
                events.append({"type": "WALL_MOVE", "wall": label,
                               "from": moved[0], "to": moved[1],
                               "threshold": w["move_pts"]})
                # the wall moved under spot; re-seed which side spot is on
                # WITHOUT emitting — SPOT_CROSS means spot moved, not the wall
                st["side"] = side if side is not None else st["side"]
                continue
            if side is not None:
                if st["side"] is not None and side != st["side"]:
                    events.append({"type": "SPOT_CROSS", "wall": label,
                                   "level": eff,
                                   "direction": "above" if side > 0 else "below"})
                st["side"] = side
        eff_call = self.walls["call"]["eff"]
        eff_put = self.walls["put"]["eff"]
        if eff_call is not None and eff_put is not None:
            inv = eff_call < eff_put
            if self.inverted is not None and inv != self.inverted:
                events.append({
                    "type": "INVERSION_ON" if inv else "INVERSION_OFF",
                    "m_call": eff_call, "m_put": eff_put})
            self.inverted = inv
        return events


# ---------------------------------------------------------------- runner

def event_line(ev: dict) -> str:
    """Terse one-line rendering for the tmux pane / stdout feed."""
    t = ev["ts"].replace("T", " ").replace("Z", "")
    core = {k: v for k, v in ev.items() if k not in ("ts", "type")}
    detail = " ".join(f"{k}={v}" for k, v in core.items())
    return f"{t}Z  {ev['type']:<18} {detail}"


class Journal:
    """Event journal with cross-run dedupe.

    Replay truncates and rewrites the day. Follow appends, but loads the
    existing journal first and suppresses byte-identical lines — so a
    mid-day restart (which re-derives detector state from byte 0) does
    not duplicate events. Determinism of replay makes the line itself a
    sufficient key.
    """

    def __init__(self, path: Path, follow: bool):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.seen: set[str] = set()
        if follow and path.exists():
            self.seen = set(path.read_text().splitlines())
        self.fh = path.open("a" if follow else "w")
        self.written = 0
        self.suppressed = 0

    def write(self, ev: dict) -> bool:
        line = json.dumps(ev)
        if line in self.seen:
            self.suppressed += 1
            return False
        self.seen.add(line)
        self.fh.write(line + "\n")
        self.fh.flush()
        self.written += 1
        return True


def run(day: str, follow: bool, cfg: dict, cfg_path: str) -> int:
    from datetime import date as _date
    corpus = gexbot_path(_date.fromisoformat(day))
    events_path = REPO / cfg["runtime"]["events_dir"] / f"{day}.jsonl"
    hb_path = Path(cfg["runtime"]["heartbeat_path"])
    det = Detector(cfg)
    journal = Journal(events_path, follow)
    consecutive_errors = 0

    log(f"orderflow-monitor [st-2n69] day={day} mode="
        f"{'follow' if follow else 'replay'} config={cfg_path}")
    log(f"  corpus: {corpus}")
    log(f"  events: {events_path}"
        + (f" ({len(journal.seen)} existing events loaded for dedupe)"
           if journal.seen else ""))

    fh = None
    if not follow:
        try:
            fh = open_corpus_text(corpus)   # gz-aware for archived days
        except FileNotFoundError as e:
            log(f"ERROR: {e}")
            return 1

    while True:
        try:
            if fh is None:
                if corpus.exists():
                    fh = corpus.open()
                else:
                    _heartbeat(hb_path, det, journal, day, "waiting-for-corpus",
                               corpus)
                    time.sleep(cfg["runtime"]["poll_seconds"])
                    continue
            pos = fh.tell()
            line = fh.readline()
            if line:
                if not line.endswith("\n") and follow:
                    # partial line still being written; restore the exact
                    # pre-read position (cookie from tell(), never
                    # arithmetic on it — byte/char confusion otherwise)
                    fh.seek(pos)
                    _heartbeat(hb_path, det, journal, day, "partial-line",
                               corpus)
                    time.sleep(1)
                    continue
                pull = parse_pull(line, cfg["fields"])
                if pull is None:
                    det.pulls_skipped += 1
                    continue
                rth = cfg["runtime"].get("rth_utc")
                if rth and not (rth[0] <= pull["ts"][11:16] < rth[1]):
                    det.pulls_filtered += 1
                    continue
                for ev in det.feed(pull):
                    if journal.write(ev):
                        log(event_line(ev))
                consecutive_errors = 0
                continue
            # EOF ---------------------------------------------------------
            if not follow:
                break
            if central_date().isoformat() != day:
                log(f"day rolled over ({day} -> {central_date().isoformat()}); "
                    "exiting for a clean relaunch")
                _heartbeat(hb_path, det, journal, day, "day-rolled", corpus)
                return 0
            fh = _revalidate(fh, corpus, det, journal, day, hb_path)
            _heartbeat(hb_path, det, journal, day, "following", corpus)
            time.sleep(cfg["runtime"]["poll_seconds"])
        except KeyboardInterrupt:
            raise
        except Exception as e:                      # noqa: BLE001
            # one bad line, one failed write, one transient OSError must
            # not kill an unattended trading-day process
            consecutive_errors += 1
            log(f"WARN loop error ({consecutive_errors} consecutive): {e!r}")
            if consecutive_errors >= 30:
                log("ERROR: 30 consecutive loop errors; giving up")
                _heartbeat(hb_path, det, journal, day, "error-loop", corpus)
                return 1
            time.sleep(min(consecutive_errors, 10))

    _heartbeat(hb_path, det, journal, day, "replay-done", corpus)
    log(f"done: {det.pulls_seen} pulls, {det.pulls_skipped} skipped, "
        f"{det.pulls_filtered} outside RTH, {journal.written} events "
        f"-> {events_path}")
    return 0


def _revalidate(fh, corpus: Path, det: Detector, journal: Journal,
                day: str, hb_path: Path):
    """At EOF, detect a recreated or truncated corpus file and recover:
    reopen from byte 0 with a fresh detector; journal dedupe suppresses
    re-emission of events already written."""
    try:
        disk = os.stat(corpus)
        held = os.fstat(fh.fileno())
        if disk.st_ino != held.st_ino or disk.st_size < held.st_size:
            log("WARN corpus file recreated or truncated; re-deriving "
                "state from byte 0 (journal dedupe active)")
            fh.close()
            det.__init__(det.cfg)
            return corpus.open()
    except OSError as e:
        log(f"WARN revalidate stat failed: {e}")
    return fh


def _heartbeat(path: Path, det: Detector, journal: Journal, day: str,
               status: str, corpus: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            corpus_bytes = corpus.stat().st_size
        except OSError:
            corpus_bytes = None
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": status,
            "day": day,
            "last_pull_ts": det.last_ts,
            "pulls_seen": det.pulls_seen,
            "pulls_skipped": det.pulls_skipped,
            "pulls_filtered_rth": det.pulls_filtered,
            "events_written": journal.written,
            "events_suppressed_dup": journal.suppressed,
            "corpus_bytes": corpus_bytes,
            "netcvx_state": det.netcvx_state,
            "inverted": det.inverted,
            "pid": os.getpid(),
        }))
        tmp.replace(path)
    except OSError as e:
        log(f"WARN heartbeat write failed: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--follow", action="store_true",
                      help="tail today's corpus live (default)")
    mode.add_argument("--replay", metavar="YYYY-MM-DD",
                      help="process one day's file and exit (rewrites journal)")
    ap.add_argument("--config",
                    default=str(REPO / "scripts/orderflow_monitor.config.json"))
    args = ap.parse_args()
    try:
        cfg = json.loads(Path(args.config).read_text())
    except (OSError, json.JSONDecodeError) as e:
        log(f"ERROR: cannot load config {args.config}: {e}")
        return 1
    if args.replay:
        return run(args.replay, follow=False, cfg=cfg, cfg_path=args.config)
    return run(central_date().isoformat(), follow=True, cfg=cfg,
               cfg_path=args.config)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
