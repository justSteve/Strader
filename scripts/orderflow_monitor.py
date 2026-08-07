#!/usr/bin/env python3
"""Orderflow Doctrine Monitor [st-2n69].

Mechanical event detection over the GexBot capture stream
(data/corpus/<date>/gexbot.jsonl, written by corpus_poll_gexbot.py).
Detects the objective patterns from the orderflow doctrine
(docs/gexbot/screenshots/orderflow-capture-checklist.md) and journals
them. Interpretation is out of scope: no direction calls, no alerts.

Modes:
  --follow            tail today's corpus file live (default)
  --replay YYYY-MM-DD run the full day's file once and exit

Outputs:
  data/derived/orderflow-events/<date>.jsonl   one JSON object per event
  stdout                                       terse feed for a tmux pane
  /var/moo/state/orderflow-monitor.json        heartbeat, every cycle

Event types:
  CVR_SPIKE_UP / CVR_SPIKE_DOWN    convexity orderflow print beyond threshold
                                   (UP = the doctrine's "brake")
  GEX_SPIKE_CALL / GEX_SPIKE_PUT   gex orderflow print beyond threshold
  TWO_SIGNAL                       brake + gex spike within max_gap_pulls
  NETCVX_DUMP_START / _END         ocvr falls dump_drop off its rolling max
  NETCVX_RAMP_START / _END         mirror of dump
  NETCVX_VTURN                     sharp rise off the min while in a dump
  WALL_MOVE                        major call/put gamma jumps >= move_pts
  INVERSION_ON / INVERSION_OFF     major call gamma below major put gamma
  SPOT_CROSS                       spot crosses a wall (with hysteresis)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
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
        summary = rec["data"].get("summary") or {}
        return {
            "ts": rec["ts_pull_utc"],
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
        self.prev: dict | None = None
        # debounced wall state: effective level, candidate, persist count
        self.walls: dict[str, dict] = {
            "call": {"eff": None, "cand": None, "count": 0, "side": None},
            "put": {"eff": None, "cand": None, "count": 0, "side": None},
        }
        self.idx = 0
        self.pulls_seen = 0
        self.pulls_skipped = 0

    # -- public -----------------------------------------------------------

    def feed(self, pull: dict) -> list[dict]:
        self.idx += 1
        self.pulls_seen += 1
        events: list[dict] = []
        events += self._spikes(pull)
        events += self._two_signal(pull)
        events += self._netcvx(pull)
        events += self._walls(pull)
        self.cvr_window.append(abs(pull["cvr_of"]))
        self.gex_window.append(abs(pull["gex_of"]))
        self.spot_window.append(pull["spot"])
        self.netcvx_window.append(pull["netcvx"])
        self.prev = pull
        for ev in events:
            ev["ts"] = pull["ts"]
            ev["spot"] = pull["spot"]
        return events

    # -- individual detectors ---------------------------------------------

    def _threshold(self, window: deque[float], floor: float) -> float | None:
        s = self.cfg["spike"]
        if len(window) < s["min_warmup"]:
            return None
        p95 = percentile(sorted(window), 0.95)
        return max(floor, s["pctl_mult"] * p95)

    def _spikes(self, pull: dict) -> list[dict]:
        s = self.cfg["spike"]
        events = []
        thr_cvr = self._threshold(self.cvr_window, s["cvr_abs_floor"])
        if thr_cvr is not None and abs(pull["cvr_of"]) > thr_cvr:
            kind = "CVR_SPIKE_UP" if pull["cvr_of"] > 0 else "CVR_SPIKE_DOWN"
            events.append({"type": kind, "value": pull["cvr_of"],
                           "threshold": round(thr_cvr, 2)})
            if kind == "CVR_SPIKE_UP":
                self.recent_brakes.append(self.idx)
        thr_gex = self._threshold(self.gex_window, s["gex_abs_floor"])
        if thr_gex is not None and abs(pull["gex_of"]) > thr_gex:
            kind = "GEX_SPIKE_CALL" if pull["gex_of"] > 0 else "GEX_SPIKE_PUT"
            events.append({"type": kind, "value": pull["gex_of"],
                           "threshold": round(thr_gex, 2)})
            self.recent_gex_spikes.append((self.idx, pull["gex_of"]))
        return events

    def _two_signal(self, pull: dict) -> list[dict]:
        gap = self.cfg["two_signal"]["max_gap_pulls"]
        if not self.recent_brakes or not self.recent_gex_spikes:
            return []
        brake_idx = self.recent_brakes[-1]
        gex_idx, gex_val = self.recent_gex_spikes[-1]
        if abs(brake_idx - gex_idx) > gap or max(brake_idx, gex_idx) != self.idx:
            return []
        trend = 0.0
        if len(self.spot_window) >= 2:
            trend = pull["spot"] - self.spot_window[0]
        # consume both so one pair emits once
        self.recent_brakes.clear()
        self.recent_gex_spikes.clear()
        return [{
            "type": "TWO_SIGNAL",
            "gex_value": gex_val,
            "gex_side": "call" if gex_val > 0 else "put",
            "trend_pts": round(trend, 2),
            "gap_pulls": abs(brake_idx - gex_idx),
        }]

    def _netcvx(self, pull: dict) -> list[dict]:
        n = self.cfg["netcvx"]
        v = pull["netcvx"]
        events = []
        if not self.netcvx_window:
            return []
        roll_max = max(self.netcvx_window)
        roll_min = min(self.netcvx_window)
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
                events.append({"type": "NETCVX_DUMP_END", "value": v,
                               "min_reached": round(self.netcvx_extreme, 2)})
        elif self.netcvx_state == "RAMP":
            if v > self.netcvx_extreme:
                self.netcvx_extreme, self.netcvx_extreme_idx = v, self.idx
            fall = self.netcvx_extreme - v
            if fall >= n["ramp_clear"] + n["ramp_rise"] / 2:
                self.netcvx_state = "NEUTRAL"
                events.append({"type": "NETCVX_RAMP_END", "value": v,
                               "max_reached": round(self.netcvx_extreme, 2)})
        return events

    def _wall_effective(self, label: str, cur: float | None) -> tuple | None:
        """Debounce a wall level; returns (old, new) when the effective
        level actually shifts (new level persisted persist_pulls pulls)."""
        w = self.cfg["walls"]
        st = self.walls[label]
        if cur is None:
            return None
        if st["eff"] is None:
            st["eff"] = cur
            return None
        if abs(cur - st["eff"]) < w["move_pts"]:
            st["cand"], st["count"] = None, 0
            st["eff"] = cur  # track small drift without an event
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
            if moved:
                events.append({"type": "WALL_MOVE", "wall": label,
                               "from": moved[0], "to": moved[1],
                               "threshold": w["move_pts"]})
            eff = st["eff"]
            if eff is None:
                continue
            side = 1 if pull["spot"] > eff + w["cross_hysteresis_pts"] else (
                -1 if pull["spot"] < eff - w["cross_hysteresis_pts"] else None)
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


def run(day: str, follow: bool, cfg: dict, cfg_path: str) -> int:
    corpus = REPO / cfg["runtime"]["corpus_dir"] / day / "gexbot.jsonl"
    events_dir = REPO / cfg["runtime"]["events_dir"]
    events_dir.mkdir(parents=True, exist_ok=True)
    events_path = events_dir / f"{day}.jsonl"
    hb_path = Path(cfg["runtime"]["heartbeat_path"])
    det = Detector(cfg)
    n_events = 0

    log(f"orderflow-monitor [st-2n69] day={day} mode="
        f"{'follow' if follow else 'replay'} config={cfg_path}")
    log(f"  corpus: {corpus}")
    log(f"  events: {events_path}")

    if not corpus.exists() and not follow:
        log(f"ERROR: no corpus file for {day}")
        return 1

    fh = None
    while True:
        if fh is None:
            if corpus.exists():
                fh = corpus.open()
            elif follow:
                _heartbeat(hb_path, det, n_events, day, "waiting-for-corpus")
                time.sleep(cfg["runtime"]["poll_seconds"])
                continue
        line = fh.readline()
        if line:
            if not line.endswith("\n") and follow:
                # partial line still being written; back up and retry
                fh.seek(fh.tell() - len(line))
                time.sleep(1)
                continue
            pull = parse_pull(line, cfg["fields"])
            if pull is None:
                det.pulls_skipped += 1
                continue
            rth = cfg["runtime"].get("rth_utc")
            if rth and not (rth[0] <= pull["ts"][11:16] < rth[1]):
                continue
            for ev in det.feed(pull):
                n_events += 1
                with events_path.open("a") as ef:
                    ef.write(json.dumps(ev) + "\n")
                log(event_line(ev))
            continue
        # EOF
        if not follow:
            break
        _heartbeat(hb_path, det, n_events, day, "following")
        time.sleep(cfg["runtime"]["poll_seconds"])

    _heartbeat(hb_path, det, n_events, day, "replay-done")
    log(f"done: {det.pulls_seen} pulls, {det.pulls_skipped} skipped, "
        f"{n_events} events -> {events_path}")
    return 0


def _heartbeat(path: Path, det: Detector, n_events: int, day: str,
               status: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": status,
            "day": day,
            "pulls_seen": det.pulls_seen,
            "pulls_skipped": det.pulls_skipped,
            "events": n_events,
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
                      help="process one day's file and exit")
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
    return run(date.today().isoformat(), follow=True, cfg=cfg,
               cfg_path=args.config)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
