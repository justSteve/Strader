#!/usr/bin/env python3
"""Absorption episode counts under tightened definitions, each tied to the
method's written definition, on the full-depth (MBO) history. [co-4owbx]

Steve, 2026-09-26, on the 09-23 depth survey's 3,275 episodes in 52 sessions:
"I'd have to question how so many absorption episodes happened across only
52 sessions." This pass re-runs that survey's own collection, then counts
the episodes under definitions that close, one at a time, the places the
coded episode is looser than the written one:

  docs/foundation/02-volume.md   absorption = big effort, small effect
  docs/foundation/05-order-flow.md
      "someone must be refilling the resting bids as fast as they're eaten"
      "the re-load: the resting orders getting eaten and reappearing at the
       same price, again and again" (Carmine's word)
      "meaningless in the middle of nowhere ... AT a mapped level"

Collection is ``absorption_depth_survey.collect`` unchanged except that its
RTH filter is lifted for the duration of the call, so reads that end
overnight are kept and tagged ``rth: false`` instead of dropped. RTH rows,
forward scoring (``SecondPath``) and the baseline are the survey's own,
so every figure here is comparable with the 09-23 run; overnight episodes
are counted but not scored (the scoring path covers 08:30-15:00 CT only).

Usage:
    .venv/bin/python scripts/measurement/absorption_definition_variants.py
    .venv/bin/python scripts/measurement/absorption_definition_variants.py --table-only
    .venv/bin/python scripts/measurement/absorption_definition_variants.py --date 2026-08-12

Writes data/measurement/absorption-variants/all-hours.jsonl (one row per day,
the depth survey's row shape plus ``rth`` on each episode).
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date as _date, datetime
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts" / "measurement"))

import absorption_depth_survey as depth  # noqa: E402
import absorption_scalp_survey as scalp  # noqa: E402
from market.orderflow.anchors import mancini_levels_for  # noqa: E402

logger = logging.getLogger("absorption_definition_variants")
DEFAULT_OUT = REPO / "data" / "measurement" / "absorption-variants" / "all-hours.jsonl"

EXPECTED_MIN = scalp.HEADLINE["expected"]   # the 09-23 headline floor, 3 ticks
ANCHOR_TICKS = scalp.HEADLINE["anchor"]     # the scalp survey's headline anchor distance, 4 ticks
REPEAT_S = 60                               # same side, same price, re-anchored within this: one episode


# ── collection ───────────────────────────────────────────────────────────────

def survey_day(day_iso: str) -> dict:
    """``absorption_depth_survey.survey_day`` with reads at every hour kept."""
    day = _date.fromisoformat(day_iso)
    try:
        path, counts = depth.pick_file(day)
        if path is None:
            return {"date": day_iso, "error": "no MBO file"}
        real_in_rth = scalp.in_rth
        scalp.in_rth = lambda ts: True
        try:
            episodes, trades, facts = depth.collect(path, day)
        finally:
            scalp.in_rth = real_in_rth
    except Exception as exc:
        logger.exception("%s failed", day_iso)
        return {"date": day_iso, "error": f"{type(exc).__name__}: {exc}"}
    trades = [t for t in trades if scalp.in_rth(t.ts)]
    if not trades:
        return {"date": day_iso, "error": "no RTH trades in the MBO file"}
    mancini = sorted(mancini_levels_for(day))
    spath = scalp.SecondPath(trades, day)
    edges = scalp.developing_edges(trades)
    for e in episodes:
        e["rth"] = scalp.in_rth(e["ts"])
        e["mancini_ticks"] = scalp.nearest_ticks(e["price"], mancini)
        e["edge_ticks"] = scalp.edge_ticks(e["price"], e["start_ts"], edges)
        e["fwd"] = spath.score(e["side"], e["price"], e["ts"]) if (e["held"] and e["rth"]) else None
    facts["all_hours_episodes"] = facts.pop("rth_episodes")
    return {"date": day_iso, "file": path.name, "contract_rth_trades": counts, **facts,
            "mancini_levels": len(mancini), "episodes": episodes,
            "baseline": scalp.baseline(trades, spath, mancini)}


# ── the definitions ──────────────────────────────────────────────────────────

def _ts(v) -> datetime:
    return v if isinstance(v, datetime) else datetime.fromisoformat(v)


def reload_multiple(e: dict) -> float:
    """Aggressor contracts traded at the level per contract showing there when
    the defense began. Above 1, size came back after it was eaten (visible
    re-adds or undisplayed size); 2 = one full re-load eaten, 3 = two."""
    return e["vol"] / max(1, e["shown_start"])


def near_anchor(e: dict, ticks: int = ANCHOR_TICKS) -> bool:
    return e.get("mancini_ticks") is not None and e["mancini_ticks"] <= ticks


def collapse_repeats(eps: list[dict], window_s: float = REPEAT_S) -> list[dict]:
    """One episode per defense: an episode on the same day, side and price
    that begins within ``window_s`` of the previous one's end continues it.
    The group keeps its first start, summed volume, and the LAST member's end,
    outcome and forward score (how the defense finally finished)."""
    out: list[dict] = []
    open_: dict[tuple, dict] = {}
    for e in sorted(eps, key=lambda x: _ts(x["start_ts"])):
        key = (_ts(e["ts"]).date(), e["side"], e["price"])
        g = open_.get(key)
        if g is not None and (_ts(e["start_ts"]) - _ts(g["ts"])).total_seconds() <= window_s:
            g.update({"ts": e["ts"], "held": e["held"], "fwd": e["fwd"], "rth": e["rth"],
                      "vol": g["vol"] + e["vol"], "members": g["members"] + 1})
            continue
        g = dict(e, members=1)
        out.append(g)
        open_[key] = g
    return out


@dataclass
class Variant:
    name: str
    reason: str
    keep: Callable[[dict], bool]
    collapse: bool = False
    anchored: bool = False    # compare against the baseline minutes within ANCHOR_TICKS


def _v0(e):
    return e["expected"] >= EXPECTED_MIN


VARIANTS = [
    Variant("V0 as run 09-23", "expected >= 3 ticks, nothing else (the 09-23 headline)", _v0),
    Variant("V1 one re-load", "doc 05: bids refilled as fast as eaten -> traded >= 2x the size showing at the start",
            lambda e: _v0(e) and reload_multiple(e) >= 2),
    Variant("V2 re-load again and again", "doc 05 / Carmine: eaten and reappearing again and again -> >= 3x shown",
            lambda e: _v0(e) and reload_multiple(e) >= 3),
    Variant("V2b refill count >= 2", "same idea on the tracker's own top-of-book refill counter (st-9vl's original gate)",
            lambda e: _v0(e) and e["refills"] >= 2),
    Variant("V3 V2 at a mapped level", "doc 05: meaningless in the middle of nowhere -> within 4 ticks of a Mancini level",
            lambda e: _v0(e) and reload_multiple(e) >= 3 and near_anchor(e), anchored=True),
    Variant("V4 V3, repeats once", "one re-load at one price is one absorption -> same side+price within 60 s counts once",
            lambda e: _v0(e) and reload_multiple(e) >= 3 and near_anchor(e), collapse=True, anchored=True),
    Variant("V5 V2, repeats once", "V4 without the anchor, for the unanchored count",
            lambda e: _v0(e) and reload_multiple(e) >= 3, collapse=True),
]


def evaluate(rows: list[dict], v: Variant) -> dict:
    ok = [r for r in rows if "error" not in r]
    sel = [e for r in ok for e in r["episodes"] if "hidden" in e and v.keep(e)]
    if v.collapse:
        sel = collapse_repeats(sel)
    rth = [e for e in sel if e["rth"]]
    per_day = [sum(1 for e in rth if _ts(e["ts"]).date().isoformat() == r["date"]) for r in ok]
    held = [e for e in rth if e["held"]]
    fs = scalp.fwd_stats([e["fwd"] for e in held])["5"]
    base = [b for r in ok for b in r["baseline"]["rows"] if b["kind"] == "off"
            and (not v.anchored or (b["ticks"] is not None and b["ticks"] <= ANCHOR_TICKS))]
    bs = scalp.fwd_stats([b["fwd"] for b in base])["5"]
    return {"name": v.name, "reason": v.reason, "days": len(ok), "all": len(sel),
            "rth": len(rth), "overnight": len(sel) - len(rth),
            "per_day_mean": len(rth) / max(1, len(ok)),
            "per_day_median": st.median(per_day) if per_day else 0,
            "held": len(held), "held_share": len(held) / max(1, len(rth)),
            "fwd5_n": fs["n"], "fwd5_broke": fs["broke"], "fwd5_win": fs["win"],
            "base5_n": bs["n"], "base5_broke": bs["broke"], "base5_win": bs["win"]}


def print_table(rows: list[dict]) -> list[dict]:
    res = [evaluate(rows, v) for v in VARIANTS]
    print(f"\n{res[0]['days']} days. Counts are RTH (read ending 08:30-15:00 CT) unless marked; "
          f"held/5-min figures are RTH held episodes scored forward, against the survey's 'off' baseline.")
    hdr = (f"{'variant':<28} {'RTH':>5} {'/day':>5} {'med':>4} {'o/n':>5} {'held':>9} "
           f"{'5m n':>5} {'stop':>5} {'tgt':>5} | {'base stop':>9} {'tgt':>4}")
    print(hdr)
    for x in res:
        print(f"{x['name']:<28} {x['rth']:>5d} {x['per_day_mean']:>5.1f} {x['per_day_median']:>4.0f} "
              f"{x['overnight']:>5d} {x['held']:>4d} {x['held_share']:>4.0%} "
              f"{x['fwd5_n']:>5d} {scalp._pct(x['fwd5_broke'])} {scalp._pct(x['fwd5_win'])} | "
              f"{scalp._pct(x['base5_broke']):>9} {scalp._pct(x['base5_win'])}")
    for x in res:
        print(f"  {x['name']}: {x['reason']}")
    return res


def load_rows(path: Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", action="append", help="one day (repeatable); default every MBO day")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--table-only", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.table_only:
        print_table(load_rows(args.out))
        return 0
    days = args.date or depth.candidate_days()
    done = {}
    if args.out.exists() and not args.date:
        done = {r["date"]: r for r in load_rows(args.out) if "error" not in r}
    todo = [d for d in days if d not in done]
    logger.info("%d days, %d already collected, %d to run", len(days), len(done), len(todo))
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
                fh.write(json.dumps(r, default=depth._jsonable) + "\n")
    print_table(json.loads(json.dumps(ordered, default=depth._jsonable)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
