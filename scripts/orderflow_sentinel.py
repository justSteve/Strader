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
REARM_ROWS = 15            # re-arm needs SUSTAINED distance, not one flapped row
APPROACH_COOLDOWN_S = 120  # a repeat approach inside this window is not news


def _feed_path() -> Path:
    return CORPUS_ROOT / central_date().isoformat() / "gexbot_orderflow_1s.jsonl"


def _alerts_path() -> Path:
    return CORPUS_ROOT / central_date().isoformat() / "orderflow_alerts.jsonl"


class DailyLog:
    """Mirror every printed line to ``<dir>/<central date>.log``, rolling at the
    CT day boundary — the same boundary the feed path already turns on.

    Why this exists [co-03ojd.7, enterprise-audit sweep J finding F11]: the
    sentinel used to be hand-launched under a `tee` to a filename pinned at
    launch time, so four days of content accumulated under
    `/var/moo/logs/orderflow-sentinel-2026-08-12.log`. Every other per-job log
    in `/var/moo/logs` rolls daily (`corpus-daily/2026-08-15.log`), so looking
    for the sentinel's activity on 08-13 or 08-14 by filename returned nothing
    and the newest file read as four days stale. It looked like absence while
    the process was in fact running and its `rows=` counter advancing — the
    inverse of the head-ed-listing trap in COO's `completeness-sweeps.md`.

    Stdout is written unconditionally: journald, the tmux sentinel window and
    the harness Monitor all read it, and the file is an addition to that, not a
    replacement for it. A file that cannot be opened degrades to stdout-only
    rather than killing a watcher whose whole job is to still be there.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.dir = directory
        self._day: str | None = None
        self._fh = None

    def write(self, line: str) -> None:
        print(line, flush=True)
        if self.dir is None:
            return
        day = central_date().isoformat()
        if day != self._day:
            self._close()
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
                self._fh = (self.dir / f"{day}.log").open("a", encoding="utf-8")
            except OSError as e:
                print(f"[sentinel] log file unavailable ({e}); stdout only",
                      file=sys.stderr, flush=True)
                self.dir = None
                return
            self._day = day
        self._fh.write(line + "\n")
        self._fh.flush()

    def _close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


#: Replaced in main() when --log-dir is given. Module-level so _emit can reach
#: it without threading a handle through LevelWatch.
_LOG = DailyLog()


def _strike(x: float) -> int:
    """Nearest SPX strike (5-pt grid near the money). Ladder values are
    computed centers (7754.83); Steve trades strikes (7755)."""
    return int(round(x / 5.0) * 5)


def _emit(alert: dict) -> None:
    for src in ("value", "new", "settled"):
        if src in alert:
            alert["strike"] = _strike(alert[src])
            break
    if "low" in alert and "high" in alert:
        alert["strike_low"] = _strike(alert["low"])
        alert["strike_high"] = _strike(alert["high"])
    for c in alert.get("contenders", []):
        c["strike"] = _strike(c["value"])
    alert["ts_alert_utc"] = utc_now_iso()
    append_jsonl(_alerts_path(), alert)
    _LOG.write(json.dumps(alert))


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
    ZONE_REOPEN_S = 1800  # same pair re-contesting within this -> it's a ZONE
    ZONE_EXIT_ROWS = 450  # ~10 min of one-cluster dominance dissolves the zone

    def __init__(self, key: str, band: float, rearm: float, move: float) -> None:
        self.key = key
        self.band = band
        self.rearm = rearm
        self.move = move
        self.window: deque[float] = deque(maxlen=self.WINDOW)
        self.value: float | None = None       # current stable cluster center
        self.contested = False
        self.zone: tuple[float, float] | None = None
        self.zone_stable_rows = 0
        self.last_pair: tuple[float, float] | None = None
        self.last_pair_at: float = 0.0
        self.prev_dist: float | None = None
        self.armed = True
        self.far_rows = 0
        self.last_approach_at = 0.0

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

        if self.zone is not None:
            # In a zone, contest/resolve chatter is suppressed. The zone
            # dissolves only after sustained one-cluster dominance.
            self.zone_stable_rows = self.zone_stable_rows + 1 \
                if share >= self.DOMINANT else 0
            if self.zone_stable_rows >= self.ZONE_EXIT_ROWS:
                _emit({"kind": "zone_dissolved", "level": self.key,
                       "name": LEVEL_NAMES[self.key], "spot": spot,
                       "zone": list(self.zone), "settled": round(top_center, 2)})
                self.zone = None
                self.value = top_center
                self.contested = False
                self.armed = True
                self.prev_dist = None
            return

        if not self.contested:
            if second_share >= self.CONTENDER:
                pair = tuple(sorted(round(c, 2) for c, _ in cl[:2]))
                now_s = time.monotonic()
                same_pair = (self.last_pair is not None
                             and abs(pair[0] - self.last_pair[0]) <= self.move
                             and abs(pair[1] - self.last_pair[1]) <= self.move)
                if same_pair and now_s - self.last_pair_at <= self.ZONE_REOPEN_S:
                    self.zone = pair
                    self.zone_stable_rows = 0
                    _emit({"kind": "zone", "level": self.key,
                           "name": LEVEL_NAMES[self.key], "spot": spot,
                           "low": pair[0], "high": pair[1],
                           "note": "recurring two-node contest — treat as a "
                                   "support/resistance ZONE; contest chatter "
                                   "suppressed until one node holds ~10 min"})
                    self.last_pair, self.last_pair_at = pair, now_s
                    return
                self.last_pair, self.last_pair_at = pair, now_s
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
            # A contest that resolves back to the incumbent is not news.
            if abs(top_center - self.value) > self.move:
                _emit({"kind": "resolved", "level": self.key,
                       "name": LEVEL_NAMES[self.key], "spot": spot,
                       "old": round(self.value, 2), "new": round(top_center, 2)})
                self.armed = True
                self.prev_dist = None
            self.value = top_center

    def update(self, level: float | None, spot: float | None) -> None:
        if level is None or spot is None:
            return
        self._last_level = level
        self._update_identity(spot)

        # In a zone the instantaneous value flaps between the nodes; measuring
        # proximity against it re-arms and re-fires on every swap (observed
        # 16:28-16:30Z: three approach alerts in 90s). Measure against the
        # nearest zone edge instead — stable by construction.
        if self.zone is not None:
            level = min(self.zone, key=lambda e: abs(spot - e))
        dist = abs(spot - level)
        approaching = self.prev_dist is not None and dist < self.prev_dist
        if self.armed and dist <= self.band and approaching:
            # Cooldown guards the pre-zone window, where the instantaneous
            # value still flaps: one row far away must not re-arm (that fired
            # three alerts in 16s at 16:31Z), and even a legitimate re-arm
            # inside APPROACH_COOLDOWN_S is a repeat, not news.
            now_s = time.monotonic()
            if now_s - self.last_approach_at >= APPROACH_COOLDOWN_S:
                _emit({"kind": "approach", "level": self.key,
                       "name": LEVEL_NAMES[self.key], "value": level,
                       "spot": spot, "distance_pts": round(dist, 2),
                       "side": "from_below" if spot < level else "from_above"})
                self.last_approach_at = now_s
            self.armed = False
            self.far_rows = 0
        elif not self.armed:
            self.far_rows = self.far_rows + 1 if dist >= self.rearm else 0
            if self.far_rows >= REARM_ROWS:
                self.armed = True
                self.far_rows = 0
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
    ap.add_argument("--log-dir", type=Path, default=None,
                    help="Mirror stdout to <dir>/<CT date>.log, rolling daily. "
                         "The systemd unit passes /var/moo/logs/orderflow-sentinel")
    args = ap.parse_args()

    global _feed_path, _alerts_path, _LOG
    if args.log_dir:
        _LOG = DailyLog(args.log_dir)
    if args.feed:
        _feed_path = lambda: args.feed  # noqa: E731
    if args.alerts:
        _alerts_path = lambda: args.alerts  # noqa: E731

    watches = {k: LevelWatch(k, args.band, args.rearm, args.move) for k in LEVELS}
    path = _feed_path()
    offset = path.stat().st_size if path.exists() else 0  # start at NOW, not history
    last_beat = time.monotonic()
    rows = 0

    _LOG.write(f"sentinel up — watching {path} (band {args.band}, "
               f"rearm {args.rearm}, move {args.move})")
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
            _LOG.write(f"heartbeat {utc_now_iso()} rows={rows} {json.dumps(state)}")
            last_beat = time.monotonic()
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
