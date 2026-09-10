#!/usr/bin/env python3
"""ES level watch over the live Databento tape — one line per event, CT stamps. [st-d7qe]

Built 2026-09-10 while Steve traded the open and asked for eyes on ES. Reads
the day's ES trades file as it is written (no network, no Schwab), and prints:

  * a trade CLEARING a Mancini level or a GEX major — hysteresis of ``--band``
    points on the far side, so ticks oscillating on the level are not events,
    and a ``--cooldown`` per level so a chop is counted, not narrated (the
    count lands in the next 15-minute summary);
  * a GEX major that moved — only when the new value holds two consecutive
    polls and was not seen in the last 30 minutes (the vendor toggles between
    near-equal clusters poll to poll; 7525/7540 vs 7580/7600 on 09-10);
  * a stale tape — no print for 90 s inside RTH;
  * a 15-minute summary — last, range, open, delta, volume, chop counts.

Delta is ask-hit volume minus bid-hit volume (Databento side A/B). It is
pressure, not progress: on 09-10 the morning sold off on POSITIVE delta and
bounced on negative delta. The line carries the number; the read is Steve's.

Run (tmux target on the moocity socket, or under Monitor in a session):

    .venv/bin/python tools/es_level_watch.py                 # today, CT
    .venv/bin/python tools/es_level_watch.py --date 2026-09-10 --band 1 --cooldown 300
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from math import inf
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
CT = ZoneInfo("America/Chicago")
RTH_OPEN, RTH_CLOSE = 8 * 60 + 30, 15 * 60
STALE_S = 90
SUMMARY_S = 900
GEX_POLL_S = 60
GEX_REPEAT_S = 1800


def stamp() -> str:
    return datetime.now(CT).strftime("%H:%M:%S")


def say(s: str) -> None:
    print(f"{stamp()} {s}", flush=True)


def load_mancini_levels(day: str) -> dict[float, str]:
    """price -> 'Mancini <kind>[ MAJOR]' from the day's in-session parse."""
    p = REPO / "runbook" / "mancini" / "parsed" / f"{day}.json"
    out: dict[float, str] = {}
    for lv in json.loads(p.read_text())["levels"]:
        major = str(lv.get("label", "")).startswith("major")
        out[float(lv["price"])] = f"Mancini {lv['kind']}{' MAJOR' if major else ''}"
    return out


class LevelCrosser:
    """Per-level above/below state with hysteresis and a per-level cooldown.

    ``update(px, t)`` returns the crossings to REPORT as (level, direction);
    crossings inside the cooldown are counted in ``chop`` instead.
    """

    def __init__(self, band: float, cooldown: float) -> None:
        self.band = band
        self.cooldown = cooldown
        self.state: dict[float, str] = {}
        self.last_cross: dict[float, float] = {}
        self.chop: dict[float, int] = {}

    def update(self, px: float, levels: dict[float, str], t: float) -> list[tuple[float, str, str]]:
        out = []
        for lv, name in levels.items():
            st = self.state.get(lv)
            if px >= lv + self.band:
                new = "above"
            elif px <= lv - self.band:
                new = "below"
            else:
                new = st
            if st is None:
                self.state[lv] = new
            elif new is not None and new != st:
                self.state[lv] = new
                direction = "UP through" if new == "above" else "DOWN through"
                if t - self.last_cross.get(lv, -inf) < self.cooldown:
                    self.chop[lv] = self.chop.get(lv, 0) + 1
                else:
                    out.append((lv, name, direction))
                self.last_cross[lv] = t
        return out

    def take_chop(self) -> dict[float, int]:
        c, self.chop = self.chop, {}
        return c


class GexMajors:
    """Damped GEX summary: a major is reported when it holds two polls and its
    new value was not reported in the last GEX_REPEAT_S seconds."""

    KEYS = {"gamma-zero": "spot_at_gamma_zero", "major +": "major_positive",
            "major −": "major_negative", "long-gamma": "major_long_gamma",
            "short-gamma": "major_short_gamma"}
    DAMPED = ("major +", "major −")

    def __init__(self, path: Path) -> None:
        self.path = path
        self.levels: dict[str, float | None] = {}
        self.pending: dict[str, float] = {}
        self.recent: dict[str, dict[float, float]] = {}

    def poll(self, t: float) -> list[str]:
        try:
            last = None
            with self.path.open() as f:
                for line in f:
                    if line.strip():
                        last = line
            if not last:
                return []
            s = json.loads(last)["data"]["summary"]
        except (OSError, KeyError, ValueError):
            return []
        new = {k: (None if s.get(v) is None else round(float(s[v]))) for k, v in self.KEYS.items()}
        return self.apply(new, t)

    def apply(self, new: dict[str, float | None], t: float) -> list[str]:
        msgs = []
        if not self.levels:
            self.levels = dict(new)
            msgs.append("GEX: " + ", ".join(f"{k} {v}" for k, v in new.items()))
            return msgs
        for k in self.DAMPED:
            v = new[k]
            if v == self.levels.get(k):
                self.pending.pop(k, None)
                continue
            if self.pending.get(k) == v:
                seen = self.recent.setdefault(k, {})
                if t - seen.get(v, -inf) > GEX_REPEAT_S:
                    msgs.append(f"GEX {k} moved {self.levels.get(k)} → {v} (held two polls)")
                seen[v] = t
                seen[self.levels.get(k)] = t
                self.levels[k] = v
                self.pending.pop(k, None)
            else:
                self.pending[k] = v
        for k in self.KEYS:
            if k not in self.DAMPED:
                self.levels[k] = new[k]
        return msgs

    def as_levels(self) -> dict[float, str]:
        return {float(v): f"GEX {k}" for k, v in self.levels.items()
                if v is not None and k != "gamma-zero"}


def follow(path: Path):
    """Yield new lines appended to ``path`` from its current end; None when idle."""
    with path.open() as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            yield line or None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ES level watch over the live tape")
    ap.add_argument("--date", default=datetime.now(CT).strftime("%Y-%m-%d"))
    ap.add_argument("--band", type=float, default=1.0, help="points a level must be cleared by")
    ap.add_argument("--cooldown", type=float, default=300, help="seconds before the same level reports again")
    args = ap.parse_args(argv)

    day_dir = REPO / "data" / "corpus" / args.date
    tape = day_dir / "databento_glbx_es.jsonl"
    if not tape.exists():
        print(f"no live tape at {tape}", file=sys.stderr)
        return 3
    try:
        mancini = load_mancini_levels(args.date)
    except (OSError, ValueError, KeyError) as e:
        say(f"[ALERT] no Mancini levels for {args.date}: {e}")
        mancini = {}
    gex = GexMajors(day_dir / "gexbot.jsonl")
    crosser = LevelCrosser(args.band, args.cooldown)

    for m in gex.poll(time.time()):
        say(m)
    say(f"watching {tape} — {len(mancini)} Mancini levels loaded")

    last_px = None
    last_print = time.time()
    stale = False
    last_gex = time.time()
    win_start = time.time()
    w_hi = w_lo = w_open = None
    w_buy = w_sell = w_vol = 0

    for line in follow(tape):
        t = time.time()
        if line is None:
            time.sleep(0.5)
            now = datetime.now(CT)
            minute = now.hour * 60 + now.minute
            if not stale and t - last_print > STALE_S and RTH_OPEN <= minute <= RTH_CLOSE:
                say(f"[ALERT] ES tape stale: no print for {STALE_S} s inside RTH")
                stale = True
            if t - last_gex > GEX_POLL_S:
                for m in gex.poll(t):
                    say(m)
                last_gex = t
            if t - win_start >= SUMMARY_S and w_hi is not None:
                chop = crosser.take_chop()
                chop_s = ("  chop: " + ", ".join(f"{lv:g}×{n}" for lv, n in sorted(chop.items()))) if chop else ""
                say(f"15-min: last {last_px}  range {w_lo}–{w_hi}  open {w_open}  "
                    f"delta {w_buy - w_sell:+,}  vol {w_vol:,}{chop_s}")
                win_start = t
                w_hi = w_lo = w_open = None
                w_buy = w_sell = w_vol = 0
            continue
        try:
            r = json.loads(line)
            d = r["data"]
            px = d.get("price")
        except (ValueError, KeyError, TypeError):
            continue
        if px is None:
            continue
        sz = d.get("size") or 0
        side = d.get("side")
        last_print = t
        if stale:
            say("ES tape live again")
            stale = False
        if w_open is None:
            w_open = px
        w_hi = px if w_hi is None or px > w_hi else w_hi
        w_lo = px if w_lo is None or px < w_lo else w_lo
        w_vol += sz
        if side == "A":
            w_buy += sz
        elif side == "B":
            w_sell += sz
        levels = {**mancini, **gex.as_levels()}
        for lv, name, direction in crosser.update(px, levels, t):
            say(f"ES {px} {direction} {lv:g} ({name})  15-min delta so far {w_buy - w_sell:+,}  vol {w_vol:,}")
        last_px = px
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
