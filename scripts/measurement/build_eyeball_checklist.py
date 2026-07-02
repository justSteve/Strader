#!/usr/bin/env python3
"""Build the V-day eyeball validation checklist markdown + render charts. [st-r2o]

Reads data/measurement/v_days.jsonl and emits:
- docs/measurement/v_day_eyeball_v0.md (or v_day_eyeball_<version>.md)
- data/measurement/charts/YYYY-MM-DD_HHMM-HHMM.html — one per checklist row

The markdown embeds file:// links to each chart so Steve can click straight from
the checklist into a pre-annotated chart with the detector's claims overlaid.

Usage:
    .venv/bin/python scripts/measurement/build_eyeball_checklist.py
    .venv/bin/python scripts/measurement/build_eyeball_checklist.py --version v0
    .venv/bin/python scripts/measurement/build_eyeball_checklist.py --no-render
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.local_chart import render_v_day_chart  # noqa: E402

V_DAYS_PATH = REPO_ROOT / "data" / "measurement" / "v_days.jsonl"
CHARTS_DIR = REPO_ROOT / "data" / "measurement" / "charts"
DOCS_DIR = REPO_ROOT / "docs" / "measurement"


def _fmt_ct(ts: str | None) -> str:
    return ts.split("T")[1][:5] if ts else "--:--"


_HTTP_BASE: str | None = None  # set by build() per --http-base


def _chart_link(date: str) -> str:
    fname = f"{date}_1300-1500.html"
    if _HTTP_BASE:
        return f"{_HTTP_BASE.rstrip('/')}/{fname}"
    return f"file://{CHARTS_DIR / fname}"


def _row_v_down(r: dict) -> str:
    d = r["v_down"]
    ratio = d["depth"] / r["latr_20"]
    link = _chart_link(r["date"])
    return (f"| [{r['date']}]({link}) | {_fmt_ct(r['trough_t'])} | "
            f"{r['vwap_p']:.2f} | {r['trough_p']:.2f} | {r['close_p']:.2f} | "
            f"{d['depth']:.2f} | {d['recovery']:.2f} | {d['landing']:.2f} | "
            f"{ratio:.2f} | _ |")


def _row_v_up(r: dict) -> str:
    d = r["v_up"]
    ratio = d["depth"] / r["latr_20"]
    link = _chart_link(r["date"])
    return (f"| [{r['date']}]({link}) | {_fmt_ct(r['peak_t'])} | "
            f"{r['vwap_p']:.2f} | {r['peak_p']:.2f} | {r['close_p']:.2f} | "
            f"{d['depth']:.2f} | {d['recovery']:.2f} | {d['landing']:.2f} | "
            f"{ratio:.2f} | _ |")


def _row_none(r: dict) -> str:
    link = _chart_link(r["date"])
    return (f"| [{r['date']}]({link}) | {r['vwap_p']:.2f} | "
            f"{r['trough_p']:.2f} | {r['peak_p']:.2f} | {r['close_p']:.2f} | "
            f"{r['latr_20']:.2f} | _ |")


def build(version: str = "v0", render: bool = True, seed: int = 42,
          http_base: str | None = None, interval_min: int = 1) -> Path:
    global _HTTP_BASE
    _HTTP_BASE = http_base
    random.seed(seed)
    rows = [json.loads(l) for l in V_DAYS_PATH.open()]

    v_down = [r for r in rows if r["label"] == "v_down"]
    v_up = [r for r in rows if r["label"] == "v_up"]
    nones = [r for r in rows if r["label"] == "none"]

    # MISS-BY-1 (v_down arm) — drop + recovery present but landing failed
    crit_keys = ["below_vwap", "depth_ok", "recovery_ok", "landing_ok"]
    miss_one: list[tuple[dict, str]] = []
    for r in nones:
        c = r["v_down"]["criteria"]
        fails = [k for k in crit_keys if not c[k]]
        if len(fails) == 1:
            miss_one.append((r, fails[0]))
    miss_one.sort(key=lambda x: -x[0]["v_down"]["depth"] / x[0]["latr_20"])
    miss_top = [r for r, _ in miss_one[:8]]

    # Random "none" controls — disjoint from miss_top
    miss_dates = {r["date"] for r in miss_top}
    clean_nones = [r for r in nones if r["date"] not in miss_dates]
    ctrl_nones = sorted(random.sample(clean_nones, 5), key=lambda r: r["date"])

    # Render charts
    all_to_render: list[dict] = v_down + v_up + miss_top + ctrl_nones
    if render:
        print(f"# Rendering {len(all_to_render)} charts -> {CHARTS_DIR}", flush=True)
        CHARTS_DIR.mkdir(parents=True, exist_ok=True)
        for i, r in enumerate(all_to_render, 1):
            try:
                render_v_day_chart(r, out_dir=CHARTS_DIR, interval_min=interval_min)
            except Exception as e:
                print(f"  WARN {r['date']}: {e}", file=sys.stderr)
            if i % 10 == 0 or i == len(all_to_render):
                print(f"  {i}/{len(all_to_render)} rendered", flush=True)

    # Markdown
    md = [
        f"# V-Day Eyeball Validation — {version} (params: DEPTH=0.6×LATR, RECOVERY=50%, LANDING=0.3×LATR)",
        "",
        "**How to use:** click each date link to open the pre-annotated chart "
        "(local HTML, file:// URL — opens in browser). The chart shows ES 5m "
        "bars over [13:00, 15:00) CT with the detector's trough/peak markers "
        "and a dashed line at VWAP_p. Mark `Eye` column:",
        "",
        "- **V** = clear V pattern matching the detector",
        "- **~** = borderline / not obvious",
        "- **X** = does NOT look like a V",
        "- **?** = can't tell from chart",
        "",
        "**Targets:**",
        "- V-DOWN / V-UP rows should mostly score V",
        "- MISS-BY-1 rows: detector said no (landing too far) — expect mostly X or ~",
        "- NONE CONTROL rows should score X",
        "",
        "---",
        "",
        "## V-DOWN flagged (n=16) — should look like late-day drops with snap-back",
        "",
        "| Date | Trough@ | VWAP_p | Trough_p | Close_p | Depth | Reco | Land | d/LATR | Eye |",
        "|------|---------|--------|----------|---------|-------|------|------|--------|-----|",
    ]
    md.extend(_row_v_down(r) for r in v_down)

    md.extend([
        "",
        "## V-UP flagged (n=6) — should look like late-day rallies with fade",
        "",
        "| Date | Peak@ | VWAP_p | Peak_p | Close_p | Depth | Reco | Land | d/LATR | Eye |",
        "|------|-------|--------|--------|---------|-------|------|------|--------|-----|",
    ])
    md.extend(_row_v_up(r) for r in v_up)

    md.extend([
        "",
        "## MISS-BY-1 (n=8) — drop + recovery present, but close didn't land near VWAP_p",
        "",
        "| Date | Trough@ | VWAP_p | Trough_p | Close_p | Depth | Reco | Land | d/LATR | Eye |",
        "|------|---------|--------|----------|---------|-------|------|------|--------|-----|",
    ])
    md.extend(_row_v_down(r) for r in miss_top)

    md.extend([
        "",
        "## NONE CONTROL (n=5, random sample) — detector says clearly not a V",
        "",
        "| Date | VWAP_p | Trough_p | Peak_p | Close_p | LATR | Eye |",
        "|------|--------|----------|--------|---------|------|-----|",
    ])
    md.extend(_row_none(r) for r in ctrl_nones)

    md.extend([
        "",
        "---",
        "",
        "## Tally (fill after completion)",
        "",
        "| Section | V (agree) | ~ (borderline) | X (disagree) | ? (skip) | n |",
        "|---------|-----------|----------------|--------------|----------|---|",
        "| V-DOWN flagged | _ | _ | _ | _ | 16 |",
        "| V-UP flagged | _ | _ | _ | _ | 6 |",
        "| MISS-BY-1 | (X expected) | _ | _ | _ | 8 |",
        "| NONE control | (X expected) | _ | _ | _ | 5 |",
        "",
        "**Agreement metric:** (V on flagged) + (X on miss-by-1+control) / total scored.",
        "Target ≥ 80%. Below = retune. Above = freeze v0 params and move to greek correlation.",
        "",
    ])

    out_path = DOCS_DIR / f"v_day_eyeball_{version}.md"
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md))
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default="v0")
    parser.add_argument("--no-render", action="store_true",
                        help="Skip chart rendering (markdown only)")
    parser.add_argument("--http-base", default=None,
                        help="Base URL for chart links (e.g. http://localhost:8000). "
                             "Default: file:// URLs (won't work in viewers that block file:// for security)")
    parser.add_argument("--interval", type=int, default=1,
                        help="Bar interval in minutes for rendered charts (default 1)")
    args = parser.parse_args()
    path = build(version=args.version, render=not args.no_render,
                 http_base=args.http_base, interval_min=args.interval)
    print(f"\n# Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
