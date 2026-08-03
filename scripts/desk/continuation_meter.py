#!/usr/bin/env python3
"""Live continuation meter — desk pane for the morning flush. [st-byrg]

Display-only. Polls Schwab minute history for $SPX + internals, detects
today's primary move (same max-excursion definition as the st-gzwb study),
and grades continuation using the mappings measured in
docs/measurement/morning-flush-continuation.md (July 2026, n=22 days,
1,882 labeled minutes, calibrated on the 08:30-10:30 CT window).

No orders, no order strings, no FD0 coupling. The human stays the trigger.

Usage:
    .venv/bin/python3 scripts/desk/continuation_meter.py            # 30s loop
    .venv/bin/python3 scripts/desk/continuation_meter.py --once     # one frame
    .venv/bin/python3 scripts/desk/continuation_meter.py --interval 60

Journal: every rendered frame appends to data/exec/continuation-meter-<day>.jsonl.
A frame whose newest internals candle is older than STALE_MIN minutes carries
a loud STALE banner — the meter never silently shows dead numbers.
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from broker_schwab.client import create_client  # noqa: E402

CT = ZoneInfo("America/Chicago")
SYMBOLS = ("$SPX", "$TICK", "$ADD", "$VIX", "$VVIX", "$VIX9D")
SESSION_OPEN = time(8, 30)
SESSION_CLOSE = time(15, 0)
CALIB_END = time(10, 30)     # the measured window; later readings extrapolate
MOVE_FLOOR = 10.0            # pts of primary move before grading means much
STALE_MIN = 3

# Measured mappings — morning-flush-continuation.md [st-cdwe/st-40fv/st-lru8].
# Score = how many of {TICK on move's side, ADD 10m slope with move,
# VIX 5m slope with move} confirm. P(extend >=2 pts within 15 min):
SCORE_P = {0: 25, 1: 49, 2: 65, 3: 73}
# $ADD (and $VOLD) publish a session late on the minute-history endpoint —
# live mornings run breadth-less. Two-trace mapping (TICK+VIX), measured on
# the same 1,882 minutes:
SCORE2_P = {0: 33, 1: 57, 2: 74}
# ES x VIX 5-min sign quadrants, by move direction (P(CONT) %):
ESVIX_P = {
    (-1, "es-", "vix+"): (73, "flush running, vol bid"),
    (-1, "es+", "vix+"): (66, "bounce NOT believed — vol still bid"),
    (-1, "es-", "vix-"): (64, "falling, vol easing"),
    (-1, "es+", "vix-"): (45, "bounce with vol crush"),
    (1, "es+", "vix-"): (63, "healthy rally, vol crushed"),
    (1, "es+", "vix+"): (53, "rally with vol bid — suspicious"),
    (1, "es-", "vix-"): (45, "dip, vol easing"),
    (1, "es-", "vix+"): (34, "DIP WITH PROTECTION BID — warning"),
}
# VIX x VVIX 5-min sign quadrants (the vol complex), by move direction:
VOLCX_P = {
    (-1, "vix+", "vvix+"): (74, "complex bid with the move"),
    (-1, "vix+", "vvix-"): (64, "vol bid, tails quiet"),
    (-1, "vix-", "vvix+"): (55, "vol easing, tails still bid"),
    (-1, "vix-", "vvix-"): (47, "COMPLEX RELEASING — fuel gone"),
    (1, "vix-", "vvix-"): (66, "complex releasing — healthy"),
    (1, "vix-", "vvix+"): (49, "vol easing, tails bid"),
    (1, "vix+", "vvix-"): (49, "vol bid, tails quiet"),
    (1, "vix+", "vvix+"): (31, "DEATH RATTLE — complex bid against rally"),
}

GREEN, RED, YEL, DIM, BOLD, END = ("\033[32m", "\033[31m", "\033[33m",
                                   "\033[2m", "\033[1m", "\033[0m")


def fetch_minutes(client, symbol, day_start_utc):
    r = client.get_price_history_every_minute(
        symbol, start_datetime=day_start_utc,
        end_datetime=datetime.now(tz=timezone.utc),
        need_extended_hours_data=False)
    if r.status_code != 200:
        raise RuntimeError(f"{symbol}: HTTP {r.status_code}")
    data = r.json()
    out = {}
    for c in data.get("candles", []):
        ts = datetime.fromtimestamp(c["datetime"] / 1000,
                                    tz=timezone.utc).astimezone(CT)
        if ts not in out:                       # first-wins (healed segment)
            out[ts] = c["close"]
    return out


def primary_move(closes):
    """Max drawup vs drawdown over today's minute closes; larger wins."""
    ms = sorted(closes)
    run_max, run_max_t = closes[ms[0]], ms[0]
    run_min, run_min_t = closes[ms[0]], ms[0]
    dd = du = None
    for m in ms:
        p = closes[m]
        if p > run_max:
            run_max, run_max_t = p, m
        if p < run_min:
            run_min, run_min_t = p, m
        if dd is None or run_max - p > dd[0]:
            dd = (run_max - p, run_max_t, m, run_max, p)
        if du is None or p - run_min > du[0]:
            du = (p - run_min, run_min_t, m, run_min, p)
    best, direction = (dd, -1) if dd[0] >= du[0] else (du, 1)
    size, t0, t1, p0, p1 = best
    return dict(size=round(size, 2), start_t=t0, end_t=t1,
                start_p=p0, end_p=p1, dir=direction)


def d5(series, m, mins):
    a, b = series.get(m), series.get(m - timedelta(minutes=mins))
    return None if a is None or b is None else a - b


def sgn_tag(v, pos, neg):
    return pos if v is not None and v > 0 else (neg if v is not None else "?")


def build_frame(client):
    now = datetime.now(tz=CT)
    day_start = datetime.combine(now.date(), SESSION_OPEN, CT)
    series = {}
    errors = []
    for sym in SYMBOLS:
        try:
            series[sym] = fetch_minutes(
                client, sym, day_start.astimezone(timezone.utc))
        except Exception as e:                  # keep rendering on any failure
            errors.append(f"{sym}: {e}")
            series[sym] = {}
    spx = series["$SPX"]
    frame = dict(ts=now.isoformat(), errors=errors)
    if not spx:
        frame["no_data"] = True
        return frame

    last_candle = max(max(s) for s in series.values() if s)
    frame["last_candle"] = last_candle.strftime("%H:%M")
    frame["stale_min"] = round((now - last_candle).total_seconds() / 60, 1)

    mv = primary_move(spx)
    frame["move"] = mv
    d = mv["dir"]

    # each trace reads at its OWN series' newest candle — feeds can lag each
    # other by a minute; the staleness banner covers the divergence
    def latest(sym):
        return max(series[sym]) if series.get(sym) else None

    def slope(sym, mins):
        m = latest(sym)
        return d5(series[sym], m, mins) if m else None

    tick = series["$TICK"].get(latest("$TICK")) if series["$TICK"] else None
    add10 = slope("$ADD", 10)
    vix5 = slope("$VIX", 5)
    vvix5 = slope("$VVIX", 5)
    spx5 = slope("$SPX", 5)

    traces = dict(
        tick=(tick * d) if tick is not None else None,
        add=(add10 * d) if add10 is not None else None,
        vix=(vix5 * -d) if vix5 is not None else None)
    frame["traces_raw"] = dict(tick=tick, add10=add10, vix5=vix5,
                               vvix5=vvix5, spx5=spx5)
    frame["traces"] = traces
    if all(v is not None for v in traces.values()):
        frame["score"] = sum(1 for v in traces.values() if v > 0)
        frame["score_mode"] = 3
    elif traces["tick"] is not None and traces["vix"] is not None:
        frame["score"] = sum(1 for k in ("tick", "vix") if traces[k] > 0)
        frame["score_mode"] = 2
    else:
        frame["score"] = None
        frame["score_mode"] = None

    if spx5 is not None and vix5 not in (None, 0) and spx5 != 0:
        key = (d, "es+" if spx5 > 0 else "es-", "vix+" if vix5 > 0 else "vix-")
        frame["esvix"] = ESVIX_P.get(key)
    if vix5 not in (None, 0) and vvix5 not in (None, 0):
        key = (d, "vix+" if vix5 > 0 else "vix-",
               "vvix+" if vvix5 > 0 else "vvix-")
        frame["volcx"] = VOLCX_P.get(key)

    lv = lambda sym: (series[sym].get(max(series[sym]))
                      if series.get(sym) else None)
    frame["levels"] = dict(spx=lv("$SPX"), vix=lv("$VIX"), vvix=lv("$VVIX"),
                           term=((lv("$VIX9D") - lv("$VIX"))
                                 if lv("$VIX9D") is not None
                                 and lv("$VIX") is not None else None))
    return frame


def render(frame):
    out = ["\033[2J\033[H"]
    now = datetime.fromisoformat(frame["ts"])
    hdr = f"{BOLD}CONTINUATION METER{END}  {now.strftime('%a %H:%M:%S CT')}"
    out.append(hdr)
    if frame.get("no_data"):
        out.append(f"{RED}No $SPX data — session closed or feed down.{END}")
        for e in frame.get("errors", []):
            out.append(f"{RED}  {e}{END}")
        return "\n".join(out) + "\n"
    if frame["stale_min"] > STALE_MIN:
        out.append(f"{RED}{BOLD}*** STALE — newest candle {frame['last_candle']} "
                   f"({frame['stale_min']:.0f} min old). Numbers below are NOT "
                   f"current. ***{END}")
    mv = frame["move"]
    word = "DOWN" if mv["dir"] == -1 else "UP"
    out.append("")
    out.append(f"Move so far: {BOLD}{word} {mv['size']:.1f} pts{END}  "
               f"({mv['start_p']:.1f} at {mv['start_t'].strftime('%H:%M')} → "
               f"{mv['end_p']:.1f} at {mv['end_t'].strftime('%H:%M')})")
    if mv["size"] < MOVE_FLOOR:
        out.append(f"{DIM}Under the {MOVE_FLOOR:.0f}-pt floor — no qualifying "
                   f"move yet; readings below mean little.{END}")
    sc = frame.get("score")
    mode = frame.get("score_mode")
    out.append("")
    if sc is not None and mode == 3:
        out.append(f"{BOLD}Score {sc}/3 → about {SCORE_P[sc]}% chance the move "
                   f"extends 2+ pts in the next 15 min{END}  "
                   f"{DIM}(measured July, base 57%){END}")
    elif sc is not None:
        out.append(f"{BOLD}Score {sc}/2 → about {SCORE2_P[sc]}% chance the move "
                   f"extends 2+ pts in the next 15 min{END}  "
                   f"{DIM}(TICK+VIX only — breadth publishes a day late; "
                   f"base 57%){END}")
    else:
        out.append(f"{YEL}Score unavailable — internals feeds missing.{END}")
    t = frame["traces"]
    raw = frame["traces_raw"]
    def mark(v):
        return f"{GREEN}✓{END}" if v is not None and v > 0 else (
            f"{RED}✗{END}" if v is not None else "?")
    out.append(f"  {mark(t['tick'])} $TICK {raw['tick']:+.0f} — "
               f"{'on the move’s side' if (t['tick'] or 0) > 0 else 'against the move'}"
               if raw["tick"] is not None else "  ? $TICK unavailable")
    out.append(f"  {mark(t['add'])} $ADD 10-min change {raw['add10']:+.0f} — "
               f"{'breadth with the move' if (t['add'] or 0) > 0 else 'breadth against'}"
               if raw["add10"] is not None else "  ? $ADD unavailable")
    out.append(f"  {mark(t['vix'])} $VIX 5-min change {raw['vix5']:+.2f} — "
               f"{'with the move' if (t['vix'] or 0) > 0 else 'against the move'} "
               f"{DIM}(momentum proxy, not vol intelligence){END}"
               if raw["vix5"] is not None else "  ? $VIX unavailable")
    out.append("")
    for key, label in (("volcx", "Vol complex (VIX×VVIX)"),
                       ("esvix", "Price×VIX")):
        st = frame.get(key)
        if st:
            p, name = st
            col = GREEN if p >= 60 else (RED if p <= 40 else YEL)
            out.append(f"{label}: {col}{name} → {p}% state{END}")
    lvl = frame["levels"]
    if lvl["spx"] is not None:
        term = (f"{lvl['term']:+.2f}" if lvl["term"] is not None else "?")
        out.append("")
        out.append(f"{DIM}SPX {lvl['spx']:.1f} · VIX "
                   f"{lvl['vix'] if lvl['vix'] is not None else '?'} · VVIX "
                   f"{lvl['vvix'] if lvl['vvix'] is not None else '?'} · "
                   f"9D−30D {term}{END}")
    if now.time() > CALIB_END:
        out.append(f"{DIM}After 10:30 CT — mappings are calibrated on the "
                   f"morning window; treat as extrapolation.{END}")
    for e in frame.get("errors", []):
        out.append(f"{RED}feed error: {e}{END}")
    return "\n".join(out) + "\n"


def journal(frame):
    day = datetime.fromisoformat(frame["ts"]).strftime("%Y-%m-%d")
    path = ROOT / "data" / "exec" / f"continuation-meter-{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: v for k, v in frame.items() if k != "move"}
    if "move" in frame:
        keep["move"] = {k: (v.isoformat() if isinstance(v, datetime) else v)
                        for k, v in frame["move"].items()}
    with path.open("a") as fh:
        fh.write(json.dumps(keep, default=str) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=30)
    args = ap.parse_args()
    try:
        client = create_client()
    except Exception as e:
        print(f"Cannot create Schwab client (token?): {e}", file=sys.stderr)
        return 1
    while True:
        try:
            frame = build_frame(client)
        except Exception as e:
            print(f"{RED}frame error: {e}{END}", flush=True)
            if args.once:
                return 1
            _time.sleep(args.interval)
            continue
        sys.stdout.write(render(frame))
        sys.stdout.flush()
        journal(frame)
        if args.once:
            return 0
        _time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
