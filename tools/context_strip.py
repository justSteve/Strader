#!/usr/bin/env python3
"""Session context strip, by hand until st-8d3a builds the real one.

Prints the checks the 08-20 emitter-miss post-mortem said must precede any
directional read: VWAP side+distance, cumulative RTH delta and 15-min slope,
$TICK/$ADD, gamma-flip side, net_dex trend. Run before characterizing
direction; output is CT-stamped.

Usage: .venv/bin/python /path/to/context_strip.py  (cwd = Strader repo)
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
REPO = Path("/root/projects/Strader")

def main() -> None:
    now = datetime.now(tz=CT)
    day = now.strftime("%Y-%m-%d")
    corpus = REPO / "data" / "corpus" / day
    rth_open_utc = datetime.now(tz=timezone.utc).replace(hour=13, minute=30, second=0, microsecond=0)
    rth_prefix = day + "T"

    # --- ES tape: day high/low, RTH VWAP, cum RTH delta + 15-min slope ---
    tape = corpus / "databento_glbx_es.jsonl"
    day_hi = day_lo = last_px = None
    pv = vol = 0.0
    cum_delta = 0.0
    last_ts = None
    # (ts, cum_delta) samples each minute for the slope
    delta_track: list[tuple[datetime, float]] = []
    n_rth = 0
    with open(tape) as f:
        for line in f:
            # cheap prefilter: price for day range without full parse cost is
            # not worth separate handling — parse everything, file is one day
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = r.get("data") or {}
            px = d.get("price"); sz = d.get("size") or 0
            if px is None:
                continue
            day_hi = px if day_hi is None else max(day_hi, px)
            day_lo = px if day_lo is None else min(day_lo, px)
            last_px = px
            ts_s = (r.get("provenance") or {}).get("ts_event") or ""
            try:
                ts = datetime.fromisoformat(ts_s)
            except ValueError:
                continue
            last_ts = ts
            if ts >= rth_open_utc:
                n_rth += 1
                pv += px * sz; vol += sz
                side = d.get("side")
                if side == "B":
                    cum_delta += sz
                elif side == "A":
                    cum_delta -= sz
                if not delta_track or (ts - delta_track[-1][0]) >= timedelta(minutes=1):
                    delta_track.append((ts, cum_delta))

    print(f"context strip — {now:%H:%M:%S} CT  (tape thru "
          f"{last_ts.astimezone(CT):%H:%M:%S} CT)" if last_ts else "no tape")
    print(f"  ES last {last_px}  day range {day_lo}–{day_hi}")
    if vol > 0:
        vwap = pv / vol
        print(f"  RTH VWAP {vwap:.2f}  price {'ABOVE' if last_px >= vwap else 'BELOW'} "
              f"by {abs(last_px - vwap):.2f}  (rth trades {n_rth})")
        slope = ""
        if last_ts is not None:
            cutoff = last_ts - timedelta(minutes=15)
            older = [c for t, c in delta_track if t <= cutoff]
            if older:
                slope = f"  15m slope {cum_delta - older[-1]:+.0f}"
        print(f"  cum RTH delta {cum_delta:+.0f}{slope}")
    else:
        print("  pre-RTH: no VWAP/cum-delta yet (opens 08:30 CT)")

    # --- gauge: $TICK close, $ADD now vs 15 min ago ---
    gauge = corpus / "mi_gauge_live.jsonl"
    rows = []
    if gauge.exists():
        with open(gauge) as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if rows:
        g = rows[-1]
        add_prev = next((r.get("add") for r in reversed(rows[:-1])
                         if r.get("ts", "") <= rows[-1].get("ts", "")
                         and r is not g and _mins_before(rows[-1], r) >= 15), None)
        trend = f" (15m ago {add_prev:+.0f})" if add_prev is not None else ""
        print(f"  gauge @{g.get('ts','?')[-14:-6]}: TICK {g.get('close'):+} "
              f" ADD {g.get('add'):+.0f}{trend}")
    else:
        print("  gauge: no rows yet")

    # --- gex: flip side, majors, net_dex now vs 15 min ago ---
    sys.path.insert(0, str(REPO))
    rec = None
    if not (corpus / "gexbot.jsonl").exists():
        print("  gex 60s: no file yet (normal before 08:30)")
    else:
        try:
            from market.orderflow.gex_context import GexContext
            gc = GexContext(corpus / "gexbot.jsonl")
            gc.refresh()
            rec = gc._polls[-1] if getattr(gc, "_polls", None) else None
            if rec is None:
                print("  gex 60s: file exists but no parseable polls")
        except Exception as e:
            print(f"  gex: unreadable ({e})")
    if rec:
        age = (datetime.now(tz=timezone.utc) - rec["ts"]).total_seconds() / 60
        print(f"  gex @{rec['ts'].astimezone(CT):%H:%M} ({age:.0f}m old): "
              f"spot {rec['spot']}  flip {rec['flip']}  pos {rec['pos']}  neg {rec['neg']}  "
              f"0dte pos/neg {rec['one_pos']}/{rec['one_neg']}")
    of1 = corpus / "gexbot_orderflow_1s.jsonl"
    if of1.exists():
        tail_rows = []
        with open(of1) as f:
            for line in f:
                try:
                    tail_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if tail_rows:
            last = tail_rows[-1]
            t_last = last.get("timestamp") or 0
            prev = next((r for r in reversed(tail_rows)
                         if (t_last - (r.get("timestamp") or 0)) >= 900), None)
            prev_s = f" (15m ago {prev.get('net_dex'):+.0f})" if prev else ""
            print(f"  net_dex {last.get('net_dex'):+.0f}{prev_s}  spot {last.get('spot')}")
        else:
            print("  orderflow_1s: file empty")
    else:
        print("  orderflow_1s: not started (normal before 08:30)")

def _mins_before(newer: dict, older: dict) -> float:
    try:
        a = datetime.fromisoformat(newer["ts"]); b = datetime.fromisoformat(older["ts"])
        return (a - b).total_seconds() / 60
    except Exception:
        return 0.0

if __name__ == "__main__":
    main()
