#!/usr/bin/env python3
"""What price did after every ABSORPTION-CLUSTER the emitter ever fired. [co-qp8cn]

The cluster detector (market/orderflow/tape_events.py) fires when two minute
bars in a row rank heavy in volume and light in net price change against the
day so far. Its firings live in the effort-effect logs. Nobody has yet written
down what the tape did next, so this script does, mechanically:

  - the cluster's own price range (low and high across its bars) and its net
    delta, which says which side was doing the throwing: negative delta means
    sellers were hitting bids and the bid side was doing the absorbing;
  - at 5, 15 and 30 minutes after the cluster's last bar: the last price, and
    the change in points from the cluster's last close;
  - whether, inside 30 minutes, price traded beyond the cluster's range on the
    attacked side (below the low when sellers were throwing, above the high
    when buyers were) — "broke" — or never did — "held".

Trades come from the corpus day file; a cluster whose day has no trades is
reported as such. This reports numbers; it does not say what they mean.

Usage:
    .venv/bin/python scripts/measurement/absorption_cluster_outcomes.py
    .venv/bin/python scripts/measurement/absorption_cluster_outcomes.py --logs /var/moo/logs/effort-effect

Writes data/measurement/absorption-cluster-outcomes.jsonl and prints a table.
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import re
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from market.orderflow.replay import read_corpus_day  # noqa: E402

logger = logging.getLogger("absorption_cluster_outcomes")
CENTRAL = ZoneInfo("America/Chicago")
DEFAULT_OUT = REPO / "data" / "measurement" / "absorption-cluster-outcomes.jsonl"
LOG_GLOBS = ("/var/moo/logs/effort-effect/*.log",
             "/var/moo/state/footprint-icm/*/00-inputs/log.txt")
HORIZONS_MIN = (5, 15, 30)

_START = re.compile(
    r"(?P<t>\d\d:\d\d) CT EVENT ABSORPTION-CLUSTER START .*?bars=(?P<bars>\d+) "
    r"from=(?P<frm>\d\d:\d\d) to=(?P<to>\d\d:\d\d) vol=(?P<vol>\d+) "
    r"delta=(?P<delta>[+-]?\d+) effort_pct=(?P<effort>\d+)\+ effect_pct=(?P<effect>\d+)-")


def firings(paths) -> list[dict]:
    """Every START line across the logs, one per (day, minute); a firing that
    appears in two logs (the same session logged twice) counts once."""
    seen: dict[tuple[str, str], dict] = {}
    for p in paths:
        m_day = re.search(r"(\d{4}-\d{2}-\d{2})", str(p))
        if not m_day:
            continue
        day = m_day.group(1)
        with open(p, errors="replace") as fh:
            for line in fh:
                m = _START.search(re.sub(r"\s+", " ", line))
                if not m:
                    continue
                seen.setdefault((day, m["t"]), {
                    "date": day, "fired_at": m["t"], "bars": int(m["bars"]),
                    "from": m["frm"], "to": m["to"], "vol": int(m["vol"]),
                    "delta": int(m["delta"]), "effort_pct": int(m["effort"]),
                    "effect_pct": int(m["effect"]), "log": str(p)})
    return [seen[k] for k in sorted(seen)]


def _dt(day: str, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.fromisoformat(day).replace(hour=h, minute=m, tzinfo=CENTRAL)


def outcome(f: dict, trades) -> dict:
    """Price path after one firing. ``trades`` is the day's list, in order."""
    start = _dt(f["date"], f["from"])
    end = _dt(f["date"], f["to"]) + timedelta(minutes=1)   # bars are [from, to]
    inside = [t for t in trades if start <= t.ts < end]
    if not inside:
        return {**f, "error": "no trades inside the cluster window"}
    lo, hi = min(t.price for t in inside), max(t.price for t in inside)
    last_close = inside[-1].price
    attacked = "bid" if f["delta"] < 0 else "ask"
    after = [t for t in trades if end <= t.ts < end + timedelta(minutes=max(HORIZONS_MIN))]
    out = {**f, "cluster_low": lo, "cluster_high": hi, "cluster_close": last_close,
           "attacked_side": attacked, "path": {}}
    for h in HORIZONS_MIN:
        upto = [t for t in after if t.ts < end + timedelta(minutes=h)]
        if not upto:
            out["path"][str(h)] = None
            continue
        px = upto[-1].price
        out["path"][str(h)] = {
            "last": px, "change_pts": round(px - last_close, 2),
            "low": min(t.price for t in upto), "high": max(t.price for t in upto)}
    if after:
        if attacked == "bid":
            broke = [t for t in after if t.price < lo]
        else:
            broke = [t for t in after if t.price > hi]
        out["result_30m"] = "broke" if broke else "held"
        out["broke_at"] = broke[0].ts.strftime("%H:%M:%S") if broke else None
        out["broke_by_pts"] = (round(lo - min(t.price for t in after), 2) if attacked == "bid"
                               else round(max(t.price for t in after) - hi, 2)) if broke else 0.0
    else:
        out["result_30m"] = "no trades after"
    return out


def run(paths, out_path: Path) -> list[dict]:
    rows = []
    cache: dict[str, list] = {}
    for f in firings(paths):
        day = f["date"]
        if day not in cache:
            try:
                cache[day] = read_corpus_day(_date.fromisoformat(day))
            except FileNotFoundError:
                cache[day] = []
        if not cache[day]:
            rows.append({**f, "error": "no ES trades file for the day"})
            continue
        rows.append(outcome(f, cache[day]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return rows


def print_table(rows: list[dict]) -> None:
    print("# every ABSORPTION-CLUSTER firing and what price did in the next 30 minutes")
    print("attacked = the side being hit (delta<0: sellers hitting bids). held/broke = did price "
          "trade beyond the cluster's range on that side within 30 min")
    print(f"{'date':10s} {'bars CT':11s} {'vol':>6s} {'delta':>6s} {'range':17s} {'attacked':8s} "
          f"{'+5m':>7s} {'+15m':>7s} {'+30m':>7s}  result")
    for r in rows:
        if "error" in r:
            print(f"{r['date']:10s} {r['from']}-{r['to']}  {r['error']}")
            continue
        p = r["path"]
        def ch(h):
            v = p.get(str(h))
            return f"{v['change_pts']:+.2f}" if v else "-"
        res = r["result_30m"]
        if res == "broke":
            res += f" at {r['broke_at']} by {r['broke_by_pts']:.2f}"
        print(f"{r['date']:10s} {r['from']}-{r['to']} {r['vol']:>6,d} {r['delta']:>+6d} "
              f"{r['cluster_low']:.2f}-{r['cluster_high']:.2f} {r['attacked_side']:8s} "
              f"{ch(5):>7s} {ch(15):>7s} {ch(30):>7s}  {res}")
    scored = [r for r in rows if "error" not in r and r["result_30m"] in ("held", "broke")]
    held = sum(1 for r in scored if r["result_30m"] == "held")
    print(f"\n{len(scored)} scored: {held} held, {len(scored) - held} broke")


def main() -> int:
    ap = argparse.ArgumentParser(description="Outcomes after every ABSORPTION-CLUSTER firing")
    ap.add_argument("--logs", nargs="*", help="log files or directories (default: the estate's)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.logs:
        paths = []
        for l in args.logs:
            paths += sorted(glob.glob(str(Path(l) / "*.log"))) if Path(l).is_dir() else [l]
    else:
        paths = [p for g in LOG_GLOBS for p in sorted(glob.glob(g))]
    rows = run(paths, args.out)
    print_table(rows)
    logger.info("wrote %s (%d rows)", args.out, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
