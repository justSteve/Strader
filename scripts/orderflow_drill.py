#!/usr/bin/env python3
"""Orderflow drill generator — simulated screen time on volume-bar footprints. [st-yfn]

Turns one corpus day of ES trades into a self-contained interactive HTML drill:

  Mode 1 (pace acclimation): replay the session's volume bars at wall-speed
  multiples with a bar-duration cue — trains "time is an output" intuition.
  Mode 2 (guess-then-reveal): playback pauses when price approaches an armed
  level; the trainee calls reject/accept before advancing; calls + heuristic
  outcomes land in an append-only in-page log (localStorage) with JSON export.

The bars come from the real st-uqf pipeline (read_corpus_day -> build_bars),
so the drill shows exactly what the engine will see — same dedup, same sort,
same straddle rule. Deterministic: same day + same N = same drill.

Usage:
    .venv/bin/python scripts/orderflow_drill.py --date 2026-07-02
    .venv/bin/python scripts/orderflow_drill.py --date 2026-07-02 --bar-n 1000 \\
        --out /tmp/my-drill.html --no-open
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.bars import build_bars          # noqa: E402
from market.orderflow.replay import read_corpus_day   # noqa: E402
from market.orderflow.recognizer import Anchor, SetupRecognizer  # noqa: E402
from market.orderflow.anatomy import anatomy_payload, build_instances  # noqa: E402
from market.signals.orderflow_config import TICK, VOLUME_BAR_N  # noqa: E402

logger = logging.getLogger("orderflow_drill")

TEMPLATE = Path(__file__).parent / "orderflow_drill_template.html"
LABELS = Path(__file__).resolve().parent.parent / "docs/measurement/mancini-setup-labels-2026-07-06.json"
DECK = Path(__file__).resolve().parent.parent / "docs/drills/scenario-deck.json"
FAMILY = {"failed_breakdown", "level_reclaim"}


def scenario_deck_for(day: _date, bar_n: int) -> list[dict]:
    """The pro forma scenario deck (st-5ov), ladder-ordered, with reference
    instances filtered to this drill's day. Bar indices in the deck are only
    valid at the deck's bar_n; on mismatch the refs keep their level (the UI
    arms it) but lose their bar jump."""
    if not DECK.exists():
        return []
    try:
        deck = json.loads(DECK.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("could not read scenario deck (%s); dropdown will be empty", e)
        return []
    bars_valid = deck.get("bar_n") == bar_n
    out = []
    for sc in deck.get("scenarios", []):
        refs = []
        for r in sc.get("refs", []):
            if r.get("date") != day.isoformat():
                continue
            r = dict(r)
            if not bars_valid:
                r["start"] = r["end"] = None
            refs.append(r)
        out.append({k: sc[k] for k in ("id", "unit", "name", "what", "tell", "call")}
                   | {"refs": refs,
                      "deck_days": sorted({r["date"] for r in sc.get("refs", [])})})
    if not bars_valid:
        logger.info("scenario deck bar_n=%s != drill bar_n=%d — refs fall back to level-arming",
                    deck.get("bar_n"), bar_n)
    return out


def mancini_levels_for(day: _date) -> list[float]:
    """The day's Mancini support/resistance levels from the labeled corpus —
    the same anchor source score_recognizer.py validated against. Empty for
    unlabeled days (anatomy then falls back to session range edges)."""
    if not LABELS.exists():
        return []
    try:
        entries = json.loads(LABELS.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("could not read Mancini labels (%s); anatomy uses range edges only", e)
        return []
    lv = {round(float(x), 2)
          for e in entries
          if e.get("session_date") == day.isoformat() and e.get("setup") in FAMILY
          for x in e.get("es_levels", []) if 5000 < float(x) < 9000}
    return sorted(lv)


def build_anatomy(bars: list, suggested: dict, mancini_levels: list[float]) -> list[dict]:
    """Run the validated recognizer over the day and fold its emissions into
    four-beat walkthrough instances (st-yfn anatomy mode). Anchors: the day's
    Mancini levels (validated `support` source) plus session range edges so
    unlabeled days still surface `range_trap` walkthroughs."""
    anchors: list[Anchor] = []
    seen: set[tuple[float, str]] = set()

    def add(price: float, kind: str, label: str, mancini: bool = False) -> None:
        key = (round(price, 2), kind)
        if key in seen:
            return
        seen.add(key)
        anchors.append(Anchor(price, kind, label, mancini=mancini))

    for lv in mancini_levels:
        add(lv, "support", f"mancini {lv:g}", mancini=True)
    add(suggested["session_high"], "range_high", "day high")
    add(suggested["session_low"], "range_low", "day low")
    if not anchors:
        return []
    recs = SetupRecognizer(anchors, mancini_prices=mancini_levels).run(bars)
    instances = build_instances(recs, bars)
    logger.info("anatomy: %d anchors -> %d recs -> %d instances",
                len(anchors), len(recs), len(instances))
    return anatomy_payload(instances)


def bars_payload(day: _date, bar_n: int, mancini_levels: list[float] | None = None) -> dict:
    trades = read_corpus_day(day)
    if not trades:
        raise SystemExit(f"corpus day {day} parsed to zero trades")
    bars = list(build_bars(trades, n=bar_n, include_partial=True))
    logger.info("%s: %d trades -> %d bars (N=%d)", day, len(trades), len(bars), bar_n)

    out_bars = []
    for b in bars:
        out_bars.append({
            "t0": b.start_ts.isoformat(), "t1": b.end_ts.isoformat(),
            "o": b.open, "h": b.high, "l": b.low, "c": b.close,
            "v": b.volume, "d": b.delta, "nv": b.none_vol,
            "dur": round(b.duration_seconds, 3),
            "poc": b.poc_price,
            "cells": [[c.price, c.bid_vol, c.ask_vol] for c in b.cells],
        })

    # level chips the drill offers out of the box (session-derived; the UI
    # also accepts any typed price)
    am = [b for b in bars if b.start_ts.hour < 11]
    suggested = {
        "open": bars[0].open,
        "am_high": max(b.high for b in (am or bars)),
        "am_low": min(b.low for b in (am or bars)),
        "session_high": max(b.high for b in bars),
        "session_low": min(b.low for b in bars),
    }
    mancini = mancini_levels if mancini_levels is not None else mancini_levels_for(day)
    anatomy = build_anatomy(bars, suggested, mancini)
    return {
        "meta": {
            "symbol": bars[0].symbol or "ES.c.0",
            "date": day.isoformat(),
            "bar_n": bar_n,
            "tick": TICK,
            "n_bars": len(bars),
            "contracts": sum(b.volume for b in bars),
        },
        "levels": suggested,
        "bars": out_bars,
        "mancini_candidates": mancini,
        "anatomy": anatomy,
        "scenarios": scenario_deck_for(day, bar_n),
    }


def render(payload: dict, out_path: Path) -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    marker = "/*__DRILL_DATA__*/null"
    if marker not in template:
        raise SystemExit(f"template {TEMPLATE} missing data marker")
    html = template.replace(marker, json.dumps(payload, separators=(",", ":")))
    out_path.write_text(html, encoding="utf-8")
    logger.info("wrote %s (%.1f KB)", out_path, out_path.stat().st_size / 1024)


def open_in_browser(path: Path) -> None:
    """WSL -> Windows browser via the desk convention (wslpath + Start-Process)."""
    try:
        win = subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
        subprocess.Popen(["powershell.exe", "-Command", f"Start-Process '{win}'"],
                         stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as e:
        logger.warning("could not auto-open browser (%s); open manually: %s", e, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate an orderflow footprint drill [st-yfn]")
    ap.add_argument("--date", required=True, help="Corpus day YYYY-MM-DD")
    ap.add_argument("--bar-n", type=int, default=VOLUME_BAR_N,
                    help=f"Contracts per bar (default {VOLUME_BAR_N})")
    ap.add_argument("--out", help="Output HTML path (default /tmp/desk-orderflow-drill-<date>.html)")
    ap.add_argument("--mancini-levels", help="Comma-separated ES levels to anchor anatomy "
                    "(overrides the labeled-corpus lookup; e.g. 7491,7510,7541)")
    ap.add_argument("--no-open", action="store_true", help="Skip auto-opening the browser")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    day = _date.fromisoformat(args.date)
    out = Path(args.out) if args.out else Path(f"/tmp/desk-orderflow-drill-{day.isoformat()}.html")

    mancini = ([float(x) for x in args.mancini_levels.split(",") if x.strip()]
               if args.mancini_levels else None)
    payload = bars_payload(day, args.bar_n, mancini_levels=mancini)
    render(payload, out)
    if not args.no_open:
        open_in_browser(out)
    print(f"drill ready: {out}  ({payload['meta']['n_bars']} bars, "
          f"{payload['meta']['contracts']:,} contracts, N={payload['meta']['bar_n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
