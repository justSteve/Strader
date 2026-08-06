#!/root/projects/Strader/.venv/bin/python3
"""Level strength — how hard did it trade THERE? [st-8ywx]

Carmine's differentiator is not that price reached a level. It is the conviction
of the trade at the level: who was initiating, whether the initiator got paid,
and whether size stepped in front of them. A break and a trap look identical on
a line chart and completely different in the cells.

This reads one price band over one time window out of the ES footprint and
answers four questions:

  WHO INITIATED   aggressor split at the band — sell-aggressors hitting bids
                  (``bid_vol``) vs buy-aggressors lifting offers (``ask_vol``).
  DID THEY GET PAID   where price went AFTER the band was last touched. Heavy
                  sell initiation that produces no lower prices is the
                  signature of absorption, and it is the single most useful
                  thing in here: it is what separates a real breakdown from the
                  trap that precedes a rip.
  HOW LONG        contracts and wall-clock spent in the band. A level sliced in
                  nine seconds is not the same event as one ground on for six
                  minutes.
  WHERE IT STALLED   the heaviest price in the band — the actual battleground,
                  which is often not the round number anybody named.

Vocabulary is the footprint's own (Databento/CME): ``ask_vol`` is buy-aggressor
volume, ``bid_vol`` is sell-aggressor volume, delta is ask minus bid. Prints
with no aggressor tag are excluded from delta, never silently folded in.

    .venv/bin/python3 scripts/level_strength.py 7741 7750 --from 08:30 --to 08:50
    .venv/bin/python3 scripts/level_strength.py 7741 --band 2.0 --last 30

NOT a signal and not a recommendation — it is a measurement of what already
happened at a price, for a human deciding whether the next touch is different.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from datetime import date as _date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.corpus.paths import central_date, resolve_existing  # noqa: E402
from market.orderflow.replay import es_day_path, trade_from_row  # noqa: E402

CT = ZoneInfo("America/Chicago")


def _open_tape(path: Path):
    resolved = resolve_existing(path)
    if resolved is None:
        raise SystemExit(f"[FAIL] no ES tape at {path}")
    return (gzip.open(resolved, "rt") if resolved.suffix == ".gz"
            else open(resolved, "r", encoding="utf-8")), resolved


def _hhmm(s: str) -> dtime:
    h, _, m = s.partition(":")
    return dtime(int(h), int(m or 0), tzinfo=CT)


def read_band(day: _date, levels: list[float], band: float,
              t_from: dtime | None, t_to: dtime | None) -> dict:
    """Walk the day's tape once, collecting every print inside any band."""
    fh, resolved = _open_tape(es_day_path(day))
    cells: dict[float, dict[str, int]] = defaultdict(
        lambda: {"bid": 0, "ask": 0, "none": 0})
    touches: list[dict] = []          # contiguous visits to a band
    cur: dict | None = None
    after_low = after_high = None     # extremes AFTER the last touch closed
    first_ts = last_ts = None
    n_rows = 0

    with fh:
        for line in fh:
            try:
                ts, _seq, t = trade_from_row(json.loads(line))
            except Exception:
                continue
            tod = ts.timetz()
            if t_from and tod < t_from:
                continue
            if t_to and tod > t_to:
                break
            n_rows += 1
            px, size, side = float(t.price), int(t.size), getattr(t, "side", "N")
            first_ts = first_ts or ts
            last_ts = ts

            in_band = any(abs(px - lv) <= band for lv in levels)
            if in_band:
                c = cells[round(px, 2)]
                c["bid" if side == "A" else "ask" if side == "B" else "none"] += size
                if cur is None:
                    cur = {"t0": ts, "t1": ts, "vol": 0, "bid": 0, "ask": 0,
                           "lo": px, "hi": px}
                    after_low = after_high = None
                cur["t1"] = ts
                cur["vol"] += size
                cur["lo"], cur["hi"] = min(cur["lo"], px), max(cur["hi"], px)
                if side == "A":
                    cur["bid"] += size
                elif side == "B":
                    cur["ask"] += size
            else:
                if cur is not None:
                    touches.append(cur)
                    cur = None
                    after_low = after_high = px
                if after_low is not None:
                    after_low, after_high = min(after_low, px), max(after_high, px)

    if cur is not None:
        touches.append(cur)
    return {"cells": cells, "touches": touches, "after_low": after_low,
            "after_high": after_high, "first_ts": first_ts, "last_ts": last_ts,
            "rows": n_rows, "tape": resolved.name}


def render(res: dict, levels: list[float], band: float) -> str:
    out: list[str] = []
    cells = res["cells"]
    if not cells:
        return (f"no prints within {band:g} of "
                f"{', '.join(f'{l:g}' for l in levels)} in that window")

    tot_bid = sum(c["bid"] for c in cells.values())
    tot_ask = sum(c["ask"] for c in cells.values())
    tot_none = sum(c["none"] for c in cells.values())
    tot = tot_bid + tot_ask + tot_none
    heaviest = max(cells.items(), key=lambda kv: kv[1]["bid"] + kv[1]["ask"])

    out.append(f"LEVEL STRENGTH — {', '.join(f'{l:g}' for l in levels)} "
               f"+/-{band:g}   tape={res['tape']}")
    if res["first_ts"]:
        out.append(f"window {res['first_ts']:%H:%M:%S}–{res['last_ts']:%H:%M:%S} CT")
    out.append("")
    out.append(f"{'price':>9}  {'sell-agg':>9}  {'buy-agg':>9}  {'delta':>9}  "
               f"{'total':>9}")
    out.append("-" * 54)
    for px in sorted(cells, reverse=True):
        c = cells[px]
        d = c["ask"] - c["bid"]
        mark = "  <-- heaviest" if px == heaviest[0] else ""
        out.append(f"{px:9.2f}  {c['bid']:9d}  {c['ask']:9d}  {d:+9d}  "
                   f"{c['bid'] + c['ask']:9d}{mark}")
    out.append("-" * 54)
    out.append(f"{'TOTAL':>9}  {tot_bid:9d}  {tot_ask:9d}  "
               f"{tot_ask - tot_bid:+9d}  {tot:9d}")
    if tot_none:
        out.append(f"  ({tot_none} contracts had no aggressor tag — excluded "
                   f"from delta)")

    out.append("")
    out.append(f"touches: {len(res['touches'])}")
    for i, t in enumerate(res["touches"], 1):
        secs = (t["t1"] - t["t0"]).total_seconds()
        d = t["ask"] - t["bid"]
        out.append(f"  {i}. {t['t0']:%H:%M:%S}–{t['t1']:%H:%M:%S} "
                   f"({secs:5.1f}s)  {t['vol']:6d} contracts  "
                   f"delta {d:+6d}  range {t['lo']:.2f}–{t['hi']:.2f}")

    # The read. Deliberately a description of what the tape did, not a call.
    out.append("")
    lo_lvl = min(levels) - band
    if res["after_low"] is not None:
        out.append(f"after the last touch: low {res['after_low']:.2f}  "
                   f"high {res['after_high']:.2f}")
        if tot_bid > tot_ask * 1.15 and res["after_low"] >= lo_lvl:
            out.append("  READ: sell-aggressors dominated and got NO lower "
                       "prices — size absorbed them here. This is the trap "
                       "signature, not the breakdown signature.")
        elif tot_bid > tot_ask * 1.15:
            out.append("  READ: sell-aggressors dominated and price made lower "
                       "prices after — initiation got paid.")
        elif tot_ask > tot_bid * 1.15:
            out.append("  READ: buy-aggressors dominated the band.")
        else:
            out.append("  READ: two-sided, no clear initiator — a level being "
                       "worked, not taken.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("levels", nargs="+", type=float, help="ES price level(s)")
    ap.add_argument("--band", type=float, default=1.5,
                    help="+/- points counted as 'at' the level (default 1.5)")
    ap.add_argument("--date", help="corpus day YYYY-MM-DD (default today CT)")
    ap.add_argument("--from", dest="t_from", help="start HH:MM CT")
    ap.add_argument("--to", dest="t_to", help="end HH:MM CT")
    ap.add_argument("--last", type=int, help="only the last N minutes of tape")
    args = ap.parse_args()

    day = _date.fromisoformat(args.date) if args.date else central_date()
    t_from = _hhmm(args.t_from) if args.t_from else None
    t_to = _hhmm(args.t_to) if args.t_to else None
    if args.last:
        now = datetime.now(CT)
        mins = now.hour * 60 + now.minute - args.last
        t_from = dtime(max(0, mins // 60), mins % 60, tzinfo=CT)

    res = read_band(day, args.levels, args.band, t_from, t_to)
    print(render(res, args.levels, args.band))
    return 0


if __name__ == "__main__":
    sys.exit(main())
