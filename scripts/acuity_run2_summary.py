#!/usr/bin/env python3
"""Summarize an acuity run-2 sweep — bullish and bearish graded SEPARATELY. [st-tme]

    .venv/bin/python scripts/acuity_run2_summary.py --run 2026...Z [--baseline 20260727T054148Z]

Reads ``data/measurement/acuity-run2-{days,confirmations}.jsonl`` (append-only;
rows filtered on the run id) and prints, for the run: the confirm population
split by bias (support anchors → bullish; resistance anchors → bearish, new
with st-tme), each with first-touch ±5 @ 30 min, median MFE/MAE, the
time-split halves (tune < 2026-06-01 / validate ≥ — the st-98z discipline),
and cuts by setup, anchor source, hour and day type. With ``--baseline`` the
bullish population is also compared to that run on common days, which is
the regression check: carrying kind must leave the support-side stream
where it was (the only intended support-side change is a pivot now also
entering as a support).

Markdown tables to stdout; pipe into a desk page or a measurement doc.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "measurement"
SPLIT_DAY = "2026-06-01"
WINDOW = 30


def _rows(path: Path, run: str) -> list[dict]:
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("run") == run:
                out.append(r)
    return out


def grade(confs: list[dict], w: int = WINDOW) -> dict:
    v = Counter(c.get(f"verdict{w}") for c in confs)
    wins, losses = v.get("win", 0), v.get("loss", 0)
    decided = wins + losses
    mfe = [c[f"mfe{w}"] for c in confs if c.get(f"mfe{w}") is not None]
    mae = [c[f"mae{w}"] for c in confs if c.get(f"mae{w}") is not None]
    return {
        "n": len(confs), "win": wins, "loss": losses,
        "undecided": len(confs) - decided,
        "win_pct": (100.0 * wins / decided) if decided else None,
        "med_mfe": statistics.median(mfe) if mfe else None,
        "med_mae": statistics.median(mae) if mae else None,
        "mfe_gt_mae_pct": (100.0 * sum(1 for c in confs if c.get(f"mfe{w}", 0) > c.get(f"mae{w}", 0))
                           / len(confs)) if confs else None,
    }


def _pct(x) -> str:
    return "—" if x is None else f"{x:.0f}%"


def _f(x) -> str:
    return "—" if x is None else f"{x:.2f}"


def table(title: str, groups: list[tuple[str, list[dict]]]) -> str:
    lines = [f"### {title}", "", "| Cut | n | Win (±5 @30) | W / L / und | Med MFE / MAE | MFE>MAE |",
             "|---|---|---|---|---|---|"]
    for name, confs in groups:
        g = grade(confs)
        lines.append(f"| {name} | {g['n']} | {_pct(g['win_pct'])} | {g['win']} / {g['loss']} / "
                     f"{g['undecided']} | {_f(g['med_mfe'])} / {_f(g['med_mae'])} | "
                     f"{_pct(g['mfe_gt_mae_pct'])} |")
    return "\n".join(lines) + "\n"


def by(confs: list[dict], key) -> list[tuple[str, list[dict]]]:
    d: dict[str, list[dict]] = defaultdict(list)
    for c in confs:
        d[str(key(c))].append(c)
    return sorted(d.items(), key=lambda kv: kv[0])


def summarize(run: str, baseline: str | None) -> str:
    days = _rows(OUT_DIR / "acuity-run2-days.jsonl", run)
    confs = _rows(OUT_DIR / "acuity-run2-confirmations.jsonl", run)
    if not days:
        return f"no rows for run {run}"
    ok = [d for d in days if d.get("status") == "ok"]
    out = [f"## Acuity run 2 — run `{run}`", "",
           f"- days: {len(days)} candidates, {len(ok)} scored, "
           f"{sum(1 for d in days if d.get('status') == 'no_anchors')} no anchors, "
           f"{sum(1 for d in days if d.get('status') == 'empty')} empty, "
           f"{sum(1 for d in days if d.get('status') == 'error')} error",
           f"- anchor source: {dict(Counter(d.get('anchor_src') for d in ok))}",
           f"- days with ≥1 resistance anchor: "
           f"{sum(1 for d in ok if d.get('n_resistance_anchors', 0) > 0)} "
           f"(resistance anchors total {sum(d.get('n_resistance_anchors', 0) for d in ok)})",
           f"- confirmations: {len(confs)} "
           f"({sum(1 for c in confs if c['bias'] == 'bullish')} bullish, "
           f"{sum(1 for c in confs if c['bias'] == 'bearish')} bearish)", ""]

    bull = [c for c in confs if c["bias"] == "bullish"]
    bear = [c for c in confs if c["bias"] == "bearish"]
    out.append(table("Population — graded separately, never pooled", [
        ("bullish (support anchors)", bull),
        ("bearish (resistance anchors) — NEW", bear),
    ]))
    for name, pop in (("bullish", bull), ("bearish", bear)):
        if not pop:
            continue
        out.append(table(f"{name}: time split (tune < {SPLIT_DAY} / validate ≥)", [
            ("tune", [c for c in pop if c["day"] < SPLIT_DAY]),
            ("validate", [c for c in pop if c["day"] >= SPLIT_DAY]),
        ]))
        out.append(table(f"{name}: by setup", by(pop, lambda c: c["setup"])))
        out.append(table(f"{name}: by anchor source", by(pop, lambda c: c.get("anchor_src"))))
        out.append(table(f"{name}: by hour of confirm (CT)", by(pop, lambda c: f"{c['hour']:02d}")))
        out.append(table(f"{name}: by full-day type (hindsight)", by(pop, lambda c: c.get("day_type"))))
        out.append(table(f"{name}: by developing day type at confirm",
                         by(pop, lambda c: c.get("developing_day_type"))))
        out.append(table(f"{name}: by fire index", by(pop, lambda c: min(int(c.get("fire_index", 1)), 4))))
        out.append(table(f"{name}: by coverage", by(pop, lambda c: c.get("coverage"))))

    if baseline:
        b_days = {d["day"] for d in _rows(OUT_DIR / "acuity-run2-days.jsonl", baseline)
                  if d.get("status") == "ok"}
        b_conf = _rows(OUT_DIR / "acuity-run2-confirmations.jsonl", baseline)
        common = b_days & {d["day"] for d in ok}
        b_bull = [c for c in b_conf if c["bias"] == "bullish" and c["day"] in common]
        n_bull = [c for c in bull if c["day"] in common]
        out.append(f"### Regression check vs baseline `{baseline}` — bullish, common days only "
                   f"({len(common)} days)\n")
        out.append(table("bullish stream, before vs after", [
            (f"baseline {baseline}", b_bull), (f"this run {run}", n_bull)]))
        # what moved on the support side: new confirms at prices the baseline never anchored
        b_keys = Counter((c["day"], c["anchor"], c["setup"], c["ct"]) for c in b_bull)
        n_keys = Counter((c["day"], c["anchor"], c["setup"], c["ct"]) for c in n_bull)
        added = sum((n_keys - b_keys).values())
        removed = sum((b_keys - n_keys).values())
        out.append(f"- bullish confirms added {added}, removed {removed} "
                   f"(keyed on day, anchor, setup, minute; 0/0 = stream unchanged)\n")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--baseline", default=None)
    args = ap.parse_args()
    print(summarize(args.run, args.baseline))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
