"""Orderflow sentinel — coded level-proximity watcher. [st-igim]

The watching tier of the trader loop Steve directed 2026-08-10: deterministic
code watches the live 1 Hz orderflow feed (st-ipn0) and fires an alert when
something worth a deep read happens; a model is summoned only THEN. No LLM in
this file, on purpose — proximity is arithmetic, and arithmetic never blinks.

Triggers (v1):
  approach     spot enters the proximity band around major long / short gamma
               while closing in. One alert per entry; re-arms when spot leaves
               the re-arm band (hysteresis, no spam at a level being straddled).
  relocation   major long / short gamma jumps more than --move pts between
               snapshots — the ladder re-formed; every prior lean is stale.

Alerts are one-line JSON appended to data/corpus/<date>/orderflow_alerts.jsonl
and mirrored to stdout (the tmux sentinel window and the harness Monitor both
read stdout). Heartbeat line every --heartbeat s so a silent sentinel is
distinguishable from a dead one.

Reads the feed file incrementally by byte offset; survives day rollover by
recomputing the path when the date changes. Off-session there are simply no
new rows — the sentinel idles at the poll interval, harmlessly.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import CORPUS_ROOT, central_date  # noqa: E402
from market.corpus.writer import append_jsonl, utc_now_iso  # noqa: E402

LEVELS = ("z_mlgamma", "z_msgamma")
LEVEL_NAMES = {"z_mlgamma": "major long gamma", "z_msgamma": "major short gamma"}


def _feed_path() -> Path:
    return CORPUS_ROOT / central_date().isoformat() / "gexbot_orderflow_1s.jsonl"


def _alerts_path() -> Path:
    return CORPUS_ROOT / central_date().isoformat() / "orderflow_alerts.jsonl"


def _emit(alert: dict) -> None:
    alert["ts_alert_utc"] = utc_now_iso()
    append_jsonl(_alerts_path(), alert)
    print(json.dumps(alert), flush=True)


class LevelWatch:
    """Hysteresis per level: alert once on band entry, re-arm on clear exit.

    Ladder identity is judged over a ROLLING WINDOW, not per snapshot. Observed
    live 2026-08-10 ~15:00Z: z_mlgamma alternated 7721 <-> 7740 on a ~10s
    cycle — two nodes of near-equal magnitude trading the argmax. Per-snapshot
    debounce (v1: 5 held rows) still narrated every swap. The truthful states
    are:

      stable      one cluster dominates the window   -> relocation alerts only
                  when the dominant cluster itself moves
      contested   two clusters split the window      -> ONE alert on entry,
                  silence until one side wins, then a resolution alert

    Clusters are values within --move pts of a running center; window is the
    last WINDOW snapshots (~2 min at feed cadence).
    """

    WINDOW = 90
    MIN_ROWS = 20        # no verdicts before the window has substance
    DOMINANT = 0.85      # share that makes a cluster the stable value
    CONTENDER = 0.25     # share that makes a second cluster a real contender

    def __init__(self, key: str, band: float, rearm: float, move: float) -> None:
        self.key = key
        self.band = band
        self.rearm = rearm
        self.move = move
        self.window: deque[float] = deque(maxlen=self.WINDOW)
        self.value: float | None = None       # current stable cluster center
        self.contested = False
        self.prev_dist: float | None = None
        self.armed = True

    def _clusters(self) -> list[tuple[float, int]]:
        """(center, count) sorted by count desc; centers are running means."""
        out: list[list[float]] = []  # [center, count]
        for v in self.window:
            for c in out:
                if abs(v - c[0]) <= self.move:
                    c[0] += (v - c[0]) / (c[1] + 1)
                    c[1] += 1
                    break
            else:
                out.append([v, 1])
        return sorted(((c, int(n)) for c, n in out), key=lambda t: -t[1])

    def _update_identity(self, spot: float) -> None:
        self.window.append(self._last_level)
        if self.value is None:
            self.value = self._last_level
            return
        if len(self.window) < self.MIN_ROWS:
            return
        cl = self._clusters()
        top_center, top_n = cl[0]
        share = top_n / len(self.window)
        second_share = (cl[1][1] / len(self.window)) if len(cl) > 1 else 0.0

        if not self.contested:
            if second_share >= self.CONTENDER:
                self.contested = True
                _emit({"kind": "contested", "level": self.key,
                       "name": LEVEL_NAMES[self.key], "spot": spot,
                       "contenders": [{"value": round(c, 2),
                                       "share": round(n / len(self.window), 2)}
                                      for c, n in cl[:2]]})
            elif share >= self.DOMINANT and abs(top_center - self.value) > self.move:
                _emit({"kind": "relocation", "level": self.key,
                       "name": LEVEL_NAMES[self.key], "spot": spot,
                       "old": round(self.value, 2), "new": round(top_center, 2)})
                self.value = top_center
                self.armed = True
                self.prev_dist = None
            elif abs(top_center - self.value) <= self.move:
                self.value = top_center  # drift tracks silently
        elif share >= self.DOMINANT:
            self.contested = False
            _emit({"kind": "resolved", "level": self.key,
                   "name": LEVEL_NAMES[self.key], "spot": spot,
                   "old": round(self.value, 2), "new": round(top_center, 2)})
            self.value = top_center
            self.armed = True
            self.prev_dist = None

    def update(self, level: float | None, spot: float | None) -> None:
        if level is None or spot is None:
            return
        self._last_level = level
        self._update_identity(spot)

        dist = abs(spot - level)
        approaching = self.prev_dist is not None and dist < self.prev_dist
        if self.armed and dist <= self.band and approaching:
            _emit({"kind": "approach", "level": self.key,
                   "name": LEVEL_NAMES[self.key], "value": level,
                   "spot": spot, "distance_pts": round(dist, 2),
                   "side": "from_below" if spot < level else "from_above"})
            self.armed = False
        elif not self.armed and dist >= self.rearm:
            self.armed = True
        self.prev_dist = dist


def main() -> int:
    ap = argparse.ArgumentParser(description="Orderflow level-proximity sentinel")
    ap.add_argument("--band", type=float, default=2.5,
                    help="Alert when spot is within this many SPX pts of a "
                         "level and approaching (default 2.5)")
    ap.add_argument("--rearm", type=float, default=5.0,
                    help="Re-arm a level after spot is at least this far away "
                         "(default 5.0)")
    ap.add_argument("--move", type=float, default=5.0,
                    help="Alert when a level itself relocates by more than "
                         "this many pts (default 5.0)")
    ap.add_argument("--poll", type=float, default=2.0,
                    help="Seconds between feed-file checks (default 2.0)")
    ap.add_argument("--heartbeat", type=int, default=600,
                    help="Heartbeat line interval, seconds (default 600)")
    ap.add_argument("--feed", type=Path, default=None,
                    help="Override feed path (testing)")
    ap.add_argument("--alerts", type=Path, default=None,
                    help="Override alerts path (testing)")
    args = ap.parse_args()

    global _feed_path, _alerts_path
    if args.feed:
        _feed_path = lambda: args.feed  # noqa: E731
    if args.alerts:
        _alerts_path = lambda: args.alerts  # noqa: E731

    watches = {k: LevelWatch(k, args.band, args.rearm, args.move) for k in LEVELS}
    path = _feed_path()
    offset = path.stat().st_size if path.exists() else 0  # start at NOW, not history
    last_beat = time.monotonic()
    rows = 0

    print(f"sentinel up — watching {path} (band {args.band}, rearm {args.rearm}, "
          f"move {args.move})", flush=True)
    while True:
        current = _feed_path()
        if current != path:  # day rollover
            path, offset = current, 0
        if path.exists():
            size = path.stat().st_size
            if size < offset:  # truncated/rotated defensively
                offset = 0
            if size > offset:
                with path.open() as f:
                    f.seek(offset)
                    for line in f:
                        if not line.endswith("\n"):
                            break  # partial write — re-read whole next pass
                        offset += len(line.encode())
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if "anomaly" in row:
                            continue
                        rows += 1
                        spot = row.get("spot")
                        for key, w in watches.items():
                            w.update(row.get(key), spot)
        if time.monotonic() - last_beat >= args.heartbeat:
            state = {k: {"value": w.value, "armed": w.armed}
                     for k, w in watches.items()}
            print(f"heartbeat {utc_now_iso()} rows={rows} {json.dumps(state)}",
                  flush=True)
            last_beat = time.monotonic()
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
