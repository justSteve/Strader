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

Day boundary and vendor first rows [st-n0qm.1, plan §5 Phase 0]: at rollover the
LevelWatch machines are REBUILT — the old code reset only the path and offset,
so day 1's identity window judged day 2's first rows and fired spurious
first-minute alerts (measured 08-12 13:31:01Z, 08-14 13:30:04Z). The vendor's
first rows of a day are also not market rows: 08-14 row 1 carried a
`timestamp` of 08-13T19:59:59Z (prior close snapshot, pulled 13:30:02Z) and
row 2 a zeroed reset (`z_mlgamma == z_msgamma == 7535`, `agg_dex == 0`);
08-13 row 1 was the zeroed reset. `row_verdict` skips both shapes and counts
them, and the health file reports the counts so a skip rule that starts eating
real rows is visible (Risk 11).

Health: `data/corpus/<day>/_sentinel_health.json` every HEALTH_INTERVAL_S,
self-reported — rows seen, rows skipped by reason, last row's pull time, last
alert, watch state. A live-but-frozen sentinel is then distinguishable from a
dead one by anyone reading the file, not only by tailing the log.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import CORPUS_ROOT, central_date  # noqa: E402
from market.corpus.writer import append_jsonl, utc_now_iso  # noqa: E402

LEVELS = ("z_mlgamma", "z_msgamma")
LEVEL_NAMES = {"z_mlgamma": "major long gamma", "z_msgamma": "major short gamma"}
REARM_ROWS = 15            # re-arm needs SUSTAINED distance, not one flapped row
APPROACH_COOLDOWN_S = 120  # a repeat approach inside this window is not news
STALE_ROW_S = 120          # vendor `timestamp` older than this vs ts_pull_utc:
                           # a prior-session snapshot, not a market row
HEALTH_INTERVAL_S = 60     # _sentinel_health.json cadence


def _feed_path() -> Path:
    return CORPUS_ROOT / central_date().isoformat() / "gexbot_orderflow_1s.jsonl"


def _alerts_path() -> Path:
    return CORPUS_ROOT / central_date().isoformat() / "orderflow_alerts.jsonl"


def _health_path() -> Path:
    return CORPUS_ROOT / central_date().isoformat() / "_sentinel_health.json"


def _pull_epoch(ts_pull_utc) -> float | None:
    """`2026-08-14T13:30:02Z` -> epoch seconds; None when unparseable."""
    if not isinstance(ts_pull_utc, str):
        return None
    try:
        return datetime.fromisoformat(ts_pull_utc.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def row_verdict(row: dict) -> str | None:
    """None when the row is a market row the watches should see; otherwise the
    reason it is skipped: ``anomaly`` (collector-marked), ``reset`` (vendor
    zeroed reset — both major-gamma levels equal and aggregate DEX exactly 0;
    measured 08-13 row 1 and 08-14 row 2) or ``stale`` (vendor timestamp more
    than STALE_ROW_S behind the pull time — the prior-close snapshot the vendor
    hands out as row 1; measured 08-14 row 1, 17.5 h old).

    Order matters: a stale row that is also zeroed reads as ``reset``; neither
    reaches a watch, and the counters are what Risk 11 measures.
    """
    if "anomaly" in row:
        return "anomaly"
    ml, ms = row.get("z_mlgamma"), row.get("z_msgamma")
    if ml is not None and ml == ms and row.get("agg_dex") == 0:
        return "reset"
    ts = row.get("timestamp")
    pull = _pull_epoch(row.get("ts_pull_utc"))
    if isinstance(ts, (int, float)) and pull is not None and pull - ts > STALE_ROW_S:
        return "stale"
    return None


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
#: The live SentinelState, set by main()/replay_file so _emit can count alerts
#: for the health file without threading it through LevelWatch.
_STATE = None
#: Bridge base URL, or None (replay, --bridge off) [st-n0qm.9]. Set by main().
_BRIDGE: str | None = None
_BRIDGE_TIMEOUT_S = 1.5
_bridge_failures = 0


def _post_alert(alert: dict) -> bool:
    """Best-effort POST of one alert to the bridge's /alerts so the footprint
    page can paint it [st-n0qm.9]. Never raises and never blocks the watch
    loop for more than the short timeout: the durable record is
    orderflow_alerts.jsonl, written before this is called; the bridge is a
    display. Failures are logged on the first and then every 50th so a dead
    bridge is visible in the sentinel log without flooding it."""
    global _bridge_failures
    if not _BRIDGE:
        return False
    body = json.dumps(alert).encode()
    req = urllib.request.Request(f"{_BRIDGE}/alerts", data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_BRIDGE_TIMEOUT_S) as r:
            r.read()
        _bridge_failures = 0
        return True
    except (urllib.error.URLError, OSError, ValueError) as e:
        _bridge_failures += 1
        if _bridge_failures == 1 or _bridge_failures % 50 == 0:
            _LOG.write(f"[{utc_now_iso()}] bridge post failed ({_bridge_failures}x): {e}")
        return False


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
    if _STATE is not None and _STATE.last_row_pull_utc:
        # The row that fired it — wall clock says when the sentinel spoke,
        # ts_row says which second of the tape it was speaking about (the two
        # differ by the poll interval live and by hours in --replay).
        alert["ts_row"] = _STATE.last_row_pull_utc
    append_jsonl(_alerts_path(), alert)
    _LOG.write(json.dumps(alert))
    if _STATE is not None:
        _STATE.note_alert(alert["ts_alert_utc"])
    _post_alert(alert)


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


class SentinelState:
    """Everything the loop carries across rows: the watches, the day they
    belong to, and the counters the health file reports. `feed_row` is the
    unit a test drives — no file, no clock, no sleep."""

    def __init__(self, band: float, rearm: float, move: float,
                 levels: tuple[str, ...] = LEVELS) -> None:
        self.band, self.rearm, self.move, self.levels = band, rearm, move, levels
        self.day: str | None = None
        self.watches: dict[str, LevelWatch] = {}
        self.rows = 0
        self.rows_today = 0
        self.skipped: dict[str, int] = {}
        self.last_row_pull_utc: str | None = None
        self.last_alert_utc: str | None = None
        self.alerts_today = 0
        self.rollovers = 0
        self._new_watches()

    def _new_watches(self) -> None:
        self.watches = {k: LevelWatch(k, self.band, self.rearm, self.move)
                        for k in self.levels}

    def rollover(self, day: str) -> None:
        """A new CT day: fresh watches, fresh per-day counters. The identity
        window of yesterday's ladder must never judge today's first rows."""
        first = self.day is None
        self.day = day
        self._new_watches()
        self.rows_today = 0
        self.skipped = {}
        self.alerts_today = 0
        if not first:
            self.rollovers += 1

    def feed_row(self, row: dict) -> str | None:
        """Route one feed row. Returns the skip reason, or None when the row
        reached the watches."""
        verdict = row_verdict(row)
        if verdict is not None:
            self.skipped[verdict] = self.skipped.get(verdict, 0) + 1
            return verdict
        self.rows += 1
        self.rows_today += 1
        pull = row.get("ts_pull_utc")
        if isinstance(pull, str):
            self.last_row_pull_utc = pull
        spot = row.get("spot")
        for key, w in self.watches.items():
            w.update(row.get(key), spot)
        return None

    def note_alert(self, ts_utc: str) -> None:
        self.alerts_today += 1
        self.last_alert_utc = ts_utc

    def health(self, *, path: Path | None, offset: int) -> dict:
        return {
            "written_utc": utc_now_iso(),
            "pid": os.getpid(),
            "day": self.day,
            "feed": str(path) if path is not None else None,
            "feed_offset": offset,
            "rows": self.rows,
            "rows_today": self.rows_today,
            "skipped": dict(self.skipped),
            "last_row_pull_utc": self.last_row_pull_utc,
            "alerts_today": self.alerts_today,
            "last_alert_utc": self.last_alert_utc,
            "rollovers": self.rollovers,
            "watches": {k: {"value": w.value, "armed": w.armed,
                            "contested": w.contested,
                            "zone": list(w.zone) if w.zone else None}
                        for k, w in self.watches.items()},
        }


def write_health(path: Path, payload: dict) -> None:
    """Atomic replace so a reader never sees a torn file. Failure to write is
    logged, never fatal — the watcher's job is to keep watching."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        _LOG.write(f"[sentinel] health file unavailable ({e})")


def _iter_complete_lines(path: Path, offset: int):
    """Yield (row, new_offset) for each complete JSON line past `offset`. A
    partial trailing write is left for the next pass; undecodable lines are
    skipped but their bytes are consumed."""
    with path.open() as f:
        f.seek(offset)
        for line in f:
            if not line.endswith("\n"):
                break
            offset += len(line.encode())
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield row, offset


def replay_file(path: Path, state: SentinelState, day: str | None = None) -> dict:
    """Drive every row of `path` through `state` from byte 0 (the fixture and
    Risk-11 runner — the live loop starts at EOF). Returns the health dict."""
    global _STATE
    _STATE = state
    state.rollover(day or path.parent.name)
    offset = 0
    for row, offset in _iter_complete_lines(path, 0):
        state.feed_row(row)
    return state.health(path=path, offset=offset)


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
    ap.add_argument("--health", type=Path, default=None,
                    help="Override health file path (default "
                         "data/corpus/<day>/_sentinel_health.json)")
    ap.add_argument("--log-dir", type=Path, default=None,
                    help="Mirror stdout to <dir>/<CT date>.log, rolling daily. "
                         "The systemd unit passes /var/moo/logs/orderflow-sentinel")
    ap.add_argument("--bridge", default=os.environ.get("STRADER_BRIDGE", "http://127.0.0.1:7788"),
                    help="drill bridge base URL to POST alerts to for the "
                         "footprint page [st-n0qm.9]; 'off' disables (default "
                         "$STRADER_BRIDGE or http://127.0.0.1:7788; always off "
                         "under --replay)")
    ap.add_argument("--replay", type=Path, default=None, metavar="FEED_FILE",
                    help="Run every row of FEED_FILE from byte 0 through fresh "
                         "watches, print the health summary (rows, skips, "
                         "alerts) and exit. Alerts go to --alerts (default: a "
                         "sibling orderflow_alerts.replay.jsonl). Never touches "
                         "the live alerts file.")
    args = ap.parse_args()

    global _feed_path, _alerts_path, _health_path, _LOG, _STATE, _BRIDGE
    if args.log_dir:
        _LOG = DailyLog(args.log_dir)
    if not args.replay and args.bridge and args.bridge.lower() != "off":
        _BRIDGE = args.bridge.rstrip("/")
    if args.feed:
        _feed_path = lambda: args.feed  # noqa: E731
    if args.alerts:
        _alerts_path = lambda: args.alerts  # noqa: E731
    if args.health:
        _health_path = lambda: args.health  # noqa: E731

    if args.replay:
        if not args.alerts:
            _alerts_path = lambda: args.replay.with_name(  # noqa: E731
                "orderflow_alerts.replay.jsonl")
        state = SentinelState(args.band, args.rearm, args.move)
        summary = replay_file(args.replay, state)
        summary["alerts_path"] = str(_alerts_path())
        print(json.dumps(summary, indent=1))
        return 0

    state = SentinelState(args.band, args.rearm, args.move)
    _STATE = state
    path = _feed_path()
    state.rollover(central_date().isoformat())
    offset = path.stat().st_size if path.exists() else 0  # start at NOW, not history
    last_beat = time.monotonic()
    last_health = 0.0

    _LOG.write(f"sentinel up — watching {path} (band {args.band}, "
               f"rearm {args.rearm}, move {args.move})")
    while True:
        current = _feed_path()
        if current != path:  # day rollover: new file, new watches, new counters
            path, offset = current, 0
            state.rollover(central_date().isoformat())
            _LOG.write(f"day rollover — watching {path}; watches rebuilt")
        if path.exists():
            size = path.stat().st_size
            if size < offset:  # truncated/rotated defensively
                offset = 0
            if size > offset:
                for row, offset in _iter_complete_lines(path, offset):
                    reason = state.feed_row(row)
                    if reason in ("reset", "stale"):
                        _LOG.write(f"skipped {reason} row: ts={row.get('timestamp')} "
                                   f"pull={row.get('ts_pull_utc')} "
                                   f"z_mlgamma={row.get('z_mlgamma')} "
                                   f"z_msgamma={row.get('z_msgamma')} "
                                   f"agg_dex={row.get('agg_dex')}")
        now_m = time.monotonic()
        if now_m - last_beat >= args.heartbeat:
            st = {k: {"value": w.value, "armed": w.armed}
                  for k, w in state.watches.items()}
            _LOG.write(f"heartbeat {utc_now_iso()} rows={state.rows} "
                       f"skipped={json.dumps(state.skipped)} {json.dumps(st)}")
            last_beat = now_m
        if now_m - last_health >= HEALTH_INTERVAL_S:
            write_health(_health_path(), state.health(path=path, offset=offset))
            last_health = now_m
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
