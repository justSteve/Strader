#!/usr/bin/env python3
"""Absorption episodes measured with the full order book (MBO), against the
same forward scoring and per-minute baseline as absorption_scalp_survey.py.
[co-4owbx]

Steve, 2026-09-23: "go ahead with historical depth first — as complete a
comparison as possible." This pass asks what full depth adds to the
episodes the ImpactAbsorptionTracker already finds on top of book.

Per day it replays the Databento MBO file (market.orderflow.mbo_book), feeds
the MBP-1-shaped read-out to the tracker exactly as the scalp survey feeds
the recorded MBP-1 (floor at zero, same population), and while each episode
is open accumulates, at the defended price P on the defended side:

  - shown_start  size resting at P when the episode began
  - added        size that arrived at P (new orders, orders moved in, size raised)
  - filled       size that left P because it traded (a Cancel/Modify that
                 follows a Fill of the same order in one exchange event)
  - pulled       size that left P without trading
  - hidden       aggressor volume at P beyond the visible size that filled:
                 iceberg or other undisplayed size doing the defending
  - pulled_5s / filled_5s   the same two in the last five seconds before the
                 episode closed — for a broke level, eaten or withdrawn
  - behind_start / behind_end   size resting 1-4 ticks behind P
  - opp_start    size on the opposite side's first four levels at the start

Scoring, the baseline, the Mancini and developing-edge distances are the scalp
survey's own functions. Forward paths are built from the MBO file's own trades,
so a roll-week day is scored on the contract that was trading: on the days in
the September roll where the pull has both contracts, the one with more RTH
trades is used (the recorded MBP-1 followed ESU6 through 09-17, st-d6k8).

Parity check printed per day: the episode count at the widest expected floor
against the recorded-MBP-1 survey's count for the same day
(data/measurement/absorption-scalp-survey.jsonl), where one exists.

Usage:
    .venv/bin/python scripts/measurement/absorption_depth_survey.py
    .venv/bin/python scripts/measurement/absorption_depth_survey.py --date 2026-07-02
    .venv/bin/python scripts/measurement/absorption_depth_survey.py --table-only

Writes data/measurement/absorption-depth-survey.jsonl (one row per day).
MBO files: /var/moo/depth/mbo/<day>_<symbol>.mbo.dbn.zst (pull_mbo_depth.py).
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics as st
import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts" / "measurement"))

import absorption_scalp_survey as scalp  # noqa: E402
from market.orderflow.absorption_impact import ImpactAbsorptionTracker  # noqa: E402
from market.orderflow.anchors import mancini_levels_for  # noqa: E402
from market.orderflow.mbo_book import PX, iter_mbo_records, replay  # noqa: E402
from market.signals.orderflow_config import TICK  # noqa: E402

logger = logging.getLogger("absorption_depth_survey")
CENTRAL = ZoneInfo("America/Chicago")
MBO_ROOT = Path("/var/moo/depth/mbo")
DEFAULT_OUT = REPO / "data" / "measurement" / "absorption-depth-survey.jsonl"
SCALP_OUT = REPO / "data" / "measurement" / "absorption-scalp-survey.jsonl"
TICK_I = int(round(TICK / PX))
BEHIND_TICKS = 4
LAST_S = 5
LAST_NS = LAST_S * 1_000_000_000
BOOK_SIDE = {"bid": "B", "ask": "A"}


@dataclass
class Trade:
    ts: datetime
    price: float


@dataclass
class Acc:
    side: str
    p: int
    start_ts: datetime
    shown_start: int
    behind_start: int
    opp_start: int
    added: int = 0
    filled: int = 0
    pulled: int = 0
    behind_end: int = 0
    closed_ns: int | None = None
    recent: deque = None   # (ts_ns, 'f'|'p', size)

    def __post_init__(self):
        self.recent = deque()

    def reduce(self, ns: int, size: int, filled: bool) -> None:
        if filled:
            self.filled += size
        else:
            self.pulled += size
        self.recent.append((ns, "f" if filled else "p", size))
        while self.recent and self.recent[0][0] < ns - LAST_NS:
            self.recent.popleft()

    def last(self, end_ns: int) -> tuple[int, int]:
        f = p = 0
        for ns, k, sz in self.recent:
            if ns >= end_ns - LAST_NS:
                if k == "f":
                    f += sz
                else:
                    p += sz
        return f, p


def _levels_sum(levels: dict, prices) -> int:
    return sum(levels[q][0] for q in prices if q in levels)


def behind(book, side: str, p: int) -> int:
    if side == "bid":
        return _levels_sum(book.bid.levels, (p - k * TICK_I for k in range(1, BEHIND_TICKS + 1)))
    return _levels_sum(book.ask.levels, (p + k * TICK_I for k in range(1, BEHIND_TICKS + 1)))


def opposite(book, side: str) -> int:
    b, a = book.top()
    if side == "bid":
        if a is None:
            return 0
        return _levels_sum(book.ask.levels, (a + k * TICK_I for k in range(BEHIND_TICKS)))
    if b is None:
        return 0
    return _levels_sum(book.bid.levels, (b - k * TICK_I for k in range(BEHIND_TICKS)))


def mbo_files(day: str) -> list[Path]:
    return sorted(MBO_ROOT.glob(f"{day}_*.mbo.dbn.zst"))


def rth_trade_count(path: Path, day: _date) -> int:
    lo = int(datetime.combine(day, scalp.RTH_OPEN, tzinfo=CENTRAL).timestamp() * 1e9)
    hi = int(datetime.combine(day, scalp.RTH_CLOSE, tzinfo=CENTRAL).timestamp() * 1e9)
    n = 0
    for r in iter_mbo_records(path):
        a = r.action if isinstance(r.action, str) else r.action.value
        if a == "T" and lo <= r.ts_event < hi:
            n += 1
    return n


def pick_file(day: _date) -> tuple[Path | None, dict]:
    files = mbo_files(day.isoformat())
    if len(files) <= 1:
        return (files[0] if files else None), {}
    counts = {f.name: rth_trade_count(f, day) for f in files}
    best = max(files, key=lambda f: counts[f.name])
    return best, counts


def collect(path: Path, day: _date) -> tuple[list[dict], list[Trade], dict]:
    tracker = ImpactAbsorptionTracker(expected_ticks_min=0.0, hold_min_s=0.0,
                                      refill_min=0, big_prints_min=0)
    accs: dict[int, Acc] = {}          # id(open episode) -> accumulator
    closed: dict[tuple, Acc] = {}      # (side, p, start_ts) -> accumulator
    rows: list[dict] = []
    trades: list[Trade] = []
    facts = {"mbo_records": 0, "book_events": 0, "trade_events": 0, "rth_episodes": 0,
             "unmatched_reads": 0}
    iid = None
    for me, book, be in replay(path):
        facts["mbo_records"] += 1
        if iid is None:
            iid = me.instrument_id
        elif me.instrument_id != iid:
            continue
        # depth accounting against the episodes open before this record
        for side, ep in tracker._episodes.items():
            if ep is None:
                continue
            acc = accs.get(id(ep))
            if acc is None:
                continue
            bs = BOOK_SIDE[side]
            if me.action == "A" and me.side == bs and me.px == acc.p:
                acc.added += me.size
            elif me.action in ("C", "M") and me.before is not None and me.before[0] == bs:
                _, opx, osz = me.before
                if opx == acc.p:
                    kept = me.size if (me.action == "M" and me.px == acc.p) else 0
                    if me.action == "C":
                        acc.reduce(me.ts_ns, min(me.size, osz), me.filled)
                    elif kept < osz:
                        acc.reduce(me.ts_ns, osz - kept, me.filled)
                    elif kept > osz:
                        acc.added += kept - osz
                elif me.action == "M" and me.px == acc.p:
                    acc.added += me.size
        if be is None:
            continue
        facts["book_events"] += 1
        if be.action == "T" and be.size:
            facts["trade_events"] += 1
            if be.price is not None and scalp.in_rth(be.ts):
                trades.append(Trade(be.ts, be.price))
        before = dict(tracker._episodes)
        reads = tracker.process(be)
        for side, ep in before.items():
            if ep is not None and tracker._episodes[side] is not ep:
                acc = accs.pop(id(ep), None)
                if acc is not None:
                    acc.behind_end = behind(book, side, acc.p)
                    acc.closed_ns = be.ts_ns
                    closed[(side, acc.p, ep.start_ts)] = acc
        for side, ep in tracker._episodes.items():
            if ep is not None and id(ep) not in accs and before.get(side) is not ep:
                p = int(round(ep.price / PX))
                accs[id(ep)] = Acc(side, p, ep.start_ts,
                                   shown_start=book.size_at(BOOK_SIDE[side], p),
                                   behind_start=behind(book, side, p),
                                   opp_start=opposite(book, side))
        for r in reads:
            if not scalp.in_rth(r.timestamp):
                continue
            facts["rth_episodes"] += 1
            if r.expected_ticks < min(scalp.EXPECTED_GRID):
                continue
            row = scalp._row(r)
            acc = closed.pop((r.side, int(round(r.price / PX)), r.start_ts), None)
            if acc is None:
                facts["unmatched_reads"] += 1
            else:
                f5, p5 = acc.last(acc.closed_ns)
                row.update({"shown_start": acc.shown_start, "added": acc.added,
                            "filled": acc.filled, "pulled": acc.pulled,
                            "hidden": max(0, r.aggressive_vol - acc.filled),
                            "filled_5s": f5, "pulled_5s": p5,
                            "behind_start": acc.behind_start, "behind_end": acc.behind_end,
                            "opp_start": acc.opp_start})
            rows.append(row)
        closed.clear()       # a read is emitted in the same step its episode closes
    tracker.flush()
    return rows, trades, facts


def recorded_count(day_iso: str) -> int | None:
    if not SCALP_OUT.exists():
        return None
    with SCALP_OUT.open() as fh:
        for line in fh:
            if f'"date": "{day_iso}"' in line[:40]:
                d = json.loads(line)
                return len(d.get("episodes", [])) if "episodes" in d else None
    return None


def survey_day(day_iso: str) -> dict:
    day = _date.fromisoformat(day_iso)
    try:
        path, counts = pick_file(day)
        if path is None:
            return {"date": day_iso, "error": "no MBO file"}
        episodes, trades, facts = collect(path, day)
    except Exception as exc:
        logger.exception("%s failed", day_iso)
        return {"date": day_iso, "error": f"{type(exc).__name__}: {exc}"}
    if not trades:
        return {"date": day_iso, "error": "no RTH trades in the MBO file"}
    mancini = sorted(mancini_levels_for(day))
    spath = scalp.SecondPath(trades, day)
    edges = scalp.developing_edges(trades)
    for e in episodes:
        e["mancini_ticks"] = scalp.nearest_ticks(e["price"], mancini)
        e["edge_ticks"] = scalp.edge_ticks(e["price"], e["start_ts"], edges)
        e["fwd"] = spath.score(e["side"], e["price"], e["ts"]) if e["held"] else None
    return {"date": day_iso, "file": path.name, "contract_rth_trades": counts, **facts,
            "recorded_mbp1_episodes": recorded_count(day_iso),
            "mancini_levels": len(mancini), "episodes": episodes,
            "baseline": scalp.baseline(trades, spath, mancini)}


def candidate_days() -> list[str]:
    days = sorted({p.name[:10] for p in MBO_ROOT.glob("*.mbo.dbn.zst")})
    return [d for d in days if _date.fromisoformat(d).weekday() < 5]


# ── tables ───────────────────────────────────────────────────────────────────

FEATURES = [
    ("hidden share", lambda e: e["hidden"] / e["vol"] if e.get("vol") else None),
    ("pulled share", lambda e: e["pulled"] / (e["pulled"] + e["filled"]) if (e.get("pulled", 0) + e.get("filled", 0)) else None),
    ("added / shown", lambda e: e["added"] / e["shown_start"] if e.get("shown_start") else None),
    ("behind start", lambda e: e.get("behind_start")),
    ("behind end/start", lambda e: e["behind_end"] / e["behind_start"] if e.get("behind_start") else None),
    ("opp / (shown+behind)", lambda e: e["opp_start"] / (e["shown_start"] + e["behind_start"]) if (e.get("shown_start", 0) + e.get("behind_start", 0)) else None),
]


def terciles(vals: list[float]) -> tuple[float, float]:
    q = st.quantiles(vals, n=3)
    return q[0], q[1]


def _hz(stats, h="5"):
    s = stats[h]
    return f"{s['n']:>5d} {scalp._pct(s['broke'])} {scalp._pct(s['win'])}"


def print_tables(rows: list[dict]) -> None:
    ok = [r for r in rows if "error" not in r]
    bad = [r for r in rows if "error" in r]
    print(f"\n{len(ok)} days surveyed, {len(bad)} skipped: " + ", ".join(f"{r['date']} ({r['error']})" for r in bad))
    print("\nParity with the recorded-MBP-1 survey (episodes at the widest floor):")
    for r in ok:
        rec = r.get("recorded_mbp1_episodes")
        mark = "" if rec is None else ("  same" if rec == len(r["episodes"]) else f"  recorded {rec}")
        roll = f"  {r['contract_rth_trades']}" if r.get("contract_rth_trades") else ""
        print(f"  {r['date']} {r['file']:<32} {len(r['episodes']):>5d}{mark}{roll}"
              + (f"  unmatched {r['unmatched_reads']}" if r.get("unmatched_reads") else ""))
    eps = [e for r in ok for e in r["episodes"] if e["expected"] >= scalp.HEADLINE["expected"] and "hidden" in e]
    base = [b for r in ok for b in r["baseline"]["rows"] if b["kind"] == "off"]
    bstats = scalp.fwd_stats([b["fwd"] for b in base])
    print(f"\nEpisodes at expected >= {scalp.HEADLINE['expected']} ticks: {len(eps)}; "
          f"held {sum(e['held'] for e in eps)} ({sum(e['held'] for e in eps) / max(1, len(eps)):.0%})")
    print(f"Baseline 'off' minutes, 5-minute: n broke win = {_hz(bstats)}")
    print("\nEach depth feature split into thirds. held% is over all episodes in the third; "
          "the 1/2/5-minute columns (n broke win) are the HELD ones scored forward.")
    for name, fn in FEATURES:
        vals = [(fn(e), e) for e in eps]
        vals = [(v, e) for v, e in vals if v is not None]
        if len(vals) < 30:
            continue
        a, b = terciles([v for v, _ in vals])
        print(f"\n  {name}: cuts {a:.3g} / {b:.3g}")
        for label, sel in (("low", [e for v, e in vals if v <= a]),
                           ("mid", [e for v, e in vals if a < v <= b]),
                           ("high", [e for v, e in vals if v > b])):
            held = [e for e in sel if e["held"]]
            fs = scalp.fwd_stats([e["fwd"] for e in held])
            print(f"    {label:<5} n {len(sel):>6d} held {len(held) / max(1, len(sel)):4.0%}   "
                  f"1m {_hz(fs, '1')}   2m {_hz(fs, '2')}   5m {_hz(fs, '5')}")
    broke = [e for e in eps if not e["held"] and (e["filled_5s"] + e["pulled_5s"])]
    if broke:
        pulled = sum(1 for e in broke if e["pulled_5s"] > e["filled_5s"])
        print(f"\nBroke episodes, last {LAST_S} s at the level: withdrawn (pulled > filled) "
              f"{pulled} of {len(broke)} ({pulled / len(broke):.0%}); eaten {len(broke) - pulled}")


def _jsonable(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o))


def load_rows(path: Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", action="append", help="one day (repeatable); default every MBO day")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--table-only", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.table_only:
        print_tables(load_rows(args.out))
        return 0
    days = args.date or candidate_days()
    done = {}
    if args.out.exists() and not args.date:
        done = {r["date"]: r for r in load_rows(args.out) if "error" not in r}
    todo = [d for d in days if d not in done]
    logger.info("%d days, %d already surveyed, %d to run", len(days), len(done), len(todo))
    rows = dict(done)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(survey_day, d): d for d in todo}
        for f in as_completed(futs):
            r = f.result()
            rows[r["date"]] = r
            logger.info("%s: %s", r["date"], r.get("error") or f"{len(r['episodes'])} episodes")
    ordered = [rows[d] for d in sorted(rows)]
    if not args.date:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as fh:
            for r in ordered:
                fh.write(json.dumps(r, default=_jsonable) + "\n")
    print_tables(ordered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
