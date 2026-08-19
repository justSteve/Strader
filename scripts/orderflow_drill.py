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
from datetime import date as _date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.orderflow.bars import build_bars          # noqa: E402
from market.orderflow.fill import bar_fill_steps      # noqa: E402
from market.orderflow.replay import read_corpus_day   # noqa: E402
from market.orderflow.recognizer import SetupRecognizer  # noqa: E402
from market.orderflow.anatomy import anatomy_payload, build_instances  # noqa: E402
from market.orderflow.anchors import (  # noqa: E402
    Kinds, day_anchors, mancini_kinds_for, mancini_levels_for)
from market.orderflow.parity import full_stack_events  # noqa: E402
from market.orderflow.anchored_profile import (  # noqa: E402
    CENTRAL, RTH_OPEN_CT, SplitAccumulator, anchor_utc, profile_payload,
)
from market.signals.orderflow_config import TICK, VOLUME_BAR_N  # noqa: E402

logger = logging.getLogger("orderflow_drill")

TEMPLATE = Path(__file__).parent / "orderflow_drill_template.html"
# The companion minute-candle page render() writes beside the drill. Lost in
# ba9e512 — the bar_fill_steps extraction removed the FILL_STEPS line directly
# above this one and took this with it, which killed drill generation outright
# (render() always reaches the candles branch, because bars_payload always sets
# "_candles"). [st-en7w]
CANDLE_TEMPLATE = Path(__file__).parent / "candles_template.html"
DECK = Path(__file__).resolve().parent.parent / "docs/drills/scenario-deck.json"


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


def build_anatomy(bars: list, suggested: dict, mancini_levels: list[float],
                  mancini_kinds: Kinds | None = None) -> list[dict]:
    """Run the validated recognizer over the day and fold its emissions into
    four-stage walkthrough instances (st-yfn anatomy mode). Anchors come from
    market.orderflow.anchors.day_anchors — the same rule the replay recorder
    uses (st-055), so drill anatomy and the measured record cannot diverge.
    ``mancini_kinds``: each level's parsed kind (None = all supports)."""
    anchors = day_anchors(mancini_levels,
                          suggested["session_high"], suggested["session_low"],
                          mancini_kinds)
    if not anchors:
        return []
    recs = SetupRecognizer(anchors, mancini_prices=mancini_levels).run(bars)
    instances = build_instances(recs, bars)
    logger.info("anatomy: %d anchors -> %d recs -> %d instances",
                len(anchors), len(recs), len(instances))
    return anatomy_payload(instances)


def minute_candles(trades) -> list[list]:
    """1-minute OHLCV from the tape — the companion 'familiar view' (st-9lh).
    ``[minuteISO, o, h, l, c, v]`` per traded minute; empty minutes omitted."""
    out: list[list] = []
    cur_key = None
    for t in trades:
        key = t.ts.replace(second=0, microsecond=0)
        if key != cur_key:
            out.append([key.isoformat(), t.price, t.price, t.price, t.price, 0])
            cur_key = key
        k = out[-1]
        k[2] = max(k[2], t.price)
        k[3] = min(k[3], t.price)
        k[4] = t.price
        k[5] += t.size
    return out


def bars_payload(day: _date, bar_n: int, mancini_levels: list[float] | None = None,
                 mancini_kinds: Kinds | None = None) -> dict:
    trades = read_corpus_day(day)
    if not trades:
        raise SystemExit(f"corpus day {day} parsed to zero trades")
    bars = list(build_bars(trades, n=bar_n, include_partial=True))
    logger.info("%s: %d trades -> %d bars (N=%d)", day, len(trades), len(bars), bar_n)

    fill = bar_fill_steps(trades, bars)
    out_bars = []
    for b, steps in zip(bars, fill):
        out_bars.append({
            "t0": b.start_ts.isoformat(), "t1": b.end_ts.isoformat(),
            "o": b.open, "h": b.high, "l": b.low, "c": b.close,
            "v": b.volume, "d": b.delta, "nv": b.none_vol,
            "dur": round(b.duration_seconds, 3),
            "poc": b.poc_price,
            "cells": [[c.price, c.bid_vol, c.ask_vol] for c in b.cells],
            "steps": steps,
            "ev": [],
        })

    # level chips the drill offers out of the box (session-derived; the UI
    # also accepts any typed price). SESSION MEANS THE CASH SESSION [st-fgno]:
    # the tape starts at 02:50 CT (st-btu), and until 2026-08-18 "Open" was the
    # 02:50 print, "AM" ran 02:50-11:00 and "Day Hi/Lo" spanned the overnight —
    # numbers wearing labels they did not earn. A bar is RTH when it STARTS at
    # or after 08:30 CT (a bar straddling the open is pre-open); a day with no
    # RTH bars (partial capture) falls back to the whole tape.
    suggested, first_rth, n_rth = session_levels(bars, day)
    if mancini_levels is not None:
        mancini = mancini_levels            # override: kinds as given (bare = support)
    else:
        mancini = mancini_levels_for(day)
        if mancini_kinds is None:
            mancini_kinds = mancini_kinds_for(day)
    anatomy = build_anatomy(bars, suggested, mancini, mancini_kinds)

    # Emissions per bar [st-b0n9] — the same panel the live surface carries, so
    # a rep drilled on a replay reads the identical thing live. Same anchor rule
    # as build_anatomy, so the two cannot disagree about what fired. (Known
    # waste: the recognizer runs twice over the day, once here and once inside
    # build_anatomy, because build_instances consumes SetupRecognition objects
    # rather than serialized events. Deterministic either way — same anchors,
    # same input, same result.)
    final: list[dict] = []
    events = full_stack_events(trades, bar_n=bar_n,
                               anchors=day_anchors(mancini, suggested["session_high"],
                                                   suggested["session_low"], mancini_kinds),
                               mancini_prices=mancini)
    for e in events:
        i = e.get("bar_i")
        if i is None:
            final.append(e)
        elif 0 <= i < len(out_bars):
            out_bars[i]["ev"].append(e)
    logger.info("emissions: %d on bars, %d end-of-stream", len(events) - len(final), len(final))
    return {
        "meta": {
            "symbol": bars[0].symbol or "ES.c.0",
            "date": day.isoformat(),
            "bar_n": bar_n,
            "tick": TICK,
            "n_bars": len(bars),
            "contracts": sum(b.volume for b in bars),
            "candles_file": f"desk-candles-{day.isoformat()}.html",
            # session = cash session [st-fgno]; the page numbers, sums and dims by it
            "rth_open_ct": RTH_OPEN_CT.strftime("%H:%M:%S"),
            "first_rth_bar": first_rth,
            "n_rth_bars": n_rth,
        },
        # The prior-session layer of the anchored volume profile [st-fgno]:
        # prints from the prior trading day's 08:30 CT open through the end of
        # its tape (the live feed seeds the same). Today's layer is built on the
        # page from the bars' cells as the drill advances, so it never shows a
        # print the trainee has not yet "seen".
        "profile_seed": profile_seed(day),
        "_candles": minute_candles(trades),
        "levels": suggested,
        "bars": out_bars,
        "mancini_candidates": mancini,
        "anatomy": anatomy,
        "final": final,
        "scenarios": scenario_deck_for(day, bar_n),
    }


def session_levels(bars, day: _date) -> tuple[dict, int | None, int]:
    """Cash-session level chips + where the session starts in ``bars``.

    Returns ``(levels, first_rth_index, n_rth_bars)``. A bar is RTH when it
    STARTS at or after 08:30 CT on ``day``; a bar straddling the open is
    pre-open. ``levels``: open = first RTH bar's open, am_* = RTH bars starting
    before 11:00 CT, session_* = all RTH bars. A tape with no RTH bar (partial
    capture) falls back to the whole tape and reports ``first_rth_index=None``.
    [st-fgno]
    """
    session_open = datetime.combine(day, RTH_OPEN_CT, tzinfo=CENTRAL)
    first_rth = next((i for i, b in enumerate(bars)
                      if b.start_ts.astimezone(CENTRAL) >= session_open), None)
    rth = bars[first_rth:] if first_rth is not None else bars
    am = [b for b in rth if b.start_ts.astimezone(CENTRAL).hour < 11]
    levels = {
        "open": rth[0].open,
        "am_high": max(b.high for b in (am or rth)),
        "am_low": min(b.low for b in (am or rth)),
        "session_high": max(b.high for b in rth),
        "session_low": min(b.low for b in rth),
    }
    return levels, first_rth, (len(rth) if first_rth is not None else 0)


def profile_seed(day: _date) -> dict | None:
    """The prior trading day's aggressor-split profile from its 08:30 CT open,
    in the bridge wire form (``profile_payload``) — the faint layer the drill's
    volume profile panel draws under today's bars. None when the prior day has
    no ES tape (the panel then starts empty and says so). [st-fgno]"""
    from strader.market_calendar import prior_trading_day
    prior = prior_trading_day(day)
    anchor_ts = anchor_utc(prior, RTH_OPEN_CT)
    try:
        trades = read_corpus_day(prior)
    except FileNotFoundError:
        logger.warning("profile seed: no ES tape for %s — drill profile starts empty", prior)
        return None
    acc = SplitAccumulator(1)
    for t in trades:
        if t.ts >= anchor_ts:
            acc.add(t)
    if not acc.n:
        return None
    acc.mark_seeded()
    out = profile_payload(acc, anchor="prior-rth", anchor_ts=anchor_ts,
                          session_day=day.isoformat())
    logger.info("profile seed: %d prints from %s 08:30 CT", acc.n, prior)
    return out


def render(payload: dict, out_path: Path) -> None:
    candles = payload.pop("_candles", None)
    template = TEMPLATE.read_text(encoding="utf-8")
    marker = "/*__DRILL_DATA__*/null"
    if marker not in template:
        raise SystemExit(f"template {TEMPLATE} missing data marker")
    html = template.replace(marker, json.dumps(payload, separators=(",", ":")))
    out_path.write_text(html, encoding="utf-8")
    logger.info("wrote %s (%.1f KB)", out_path, out_path.stat().st_size / 1024)
    if candles is not None:
        cpath = out_path.parent / payload["meta"]["candles_file"]
        ctpl = CANDLE_TEMPLATE.read_text(encoding="utf-8")
        cmark = "/*__CANDLE_DATA__*/null"
        if cmark not in ctpl:
            raise SystemExit(f"template {CANDLE_TEMPLATE} missing data marker")
        cpayload = {"meta": {"symbol": payload["meta"]["symbol"],
                             "date": payload["meta"]["date"]},
                    "candles": candles}
        cpath.write_text(ctpl.replace(cmark, json.dumps(cpayload, separators=(",", ":"))),
                         encoding="utf-8")
        logger.info("wrote companion %s (%.1f KB)", cpath, cpath.stat().st_size / 1024)


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
