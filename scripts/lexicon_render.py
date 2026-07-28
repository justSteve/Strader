#!/usr/bin/env python3
"""Render the PA lexicon to the desk — the Steve-facing glossary. [st-g9y]

Usage:  .venv/bin/python scripts/lexicon_render.py [--no-open]
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.orderflow_drill import open_in_browser  # noqa: E402

TIER_ORDER = ["axis", "band", "atom", "leg", "day", "stage", "episode",
              "primitive", "level-state", "signature"]
TIER_TITLES = {
    "axis": "Axes — the measuring sticks",
    "band": "Grade bands — how sure a label is",
    "atom": "Atom tier — one minute",
    "leg": "Leg tier — the archetypes",
    "day": "Day tier",
    "stage": "Stages — the four-part sequence (live, episode tier)",
    "episode": "Episode tier — the recognizer's live unit",
    "primitive": "Orderflow primitives — your existing words live here",
    "level-state": "Level states — the renderer's clock",
    "signature": "Cross-tier signatures — the trading discoveries",
}


def render(lex: dict) -> str:
    e = html.escape
    parts = ["""<!doctype html><meta charset="utf-8"><title>PA Lexicon</title><style>
:root{--fg:#1a1a1a;--bg:#fff;--line:#ccc;--th:#f2f2f2;--live:#1a7f37;--hind:#9a6700;--mut:#666}
@media (prefers-color-scheme: dark){:root{--fg:#ddd;--bg:#161616;--line:#444;--th:#242424;--live:#3fb950;--hind:#d4a72c;--mut:#999}}
body{font:15px/1.55 system-ui;margin:2rem auto;max-width:62rem;padding:0 1rem;color:var(--fg);background:var(--bg)}
h1,h2{font-weight:600} h2{margin-top:2rem;border-bottom:1px solid var(--line);padding-bottom:.2rem}
.term{margin:1rem 0;padding:.6rem .9rem;border:1px solid var(--line);border-radius:6px}
.term b{font-size:1.05em} .badge{font-size:.78em;padding:1px 7px;border-radius:9px;border:1px solid;margin-left:.5em}
.live{color:var(--live);border-color:var(--live)} .hind{color:var(--hind);border-color:var(--hind)}
.prov{color:var(--mut);border-color:var(--mut)}
.chart{margin-top:.35rem;color:var(--mut)} .chart::before{content:"On the chart: ";color:var(--fg);font-weight:600}
p.pre{color:var(--mut)}
</style>
<h1>PA Lexicon v1</h1>
<p class="pre">One vocabulary, tiered. <span class="badge live">LIVE</span> = knowable in the moment — the only tier
yea/nay decisions ride on. <span class="badge hind">HINDSIGHT</span> = how the tape gets graded afterward.
Compound rule: boundary-crossing words always carry a partner word.</p>"""]
    by_tier: dict[str, list[dict]] = {}
    for t in lex["terms"]:
        by_tier.setdefault(t["tier"], []).append(t)
    for tier in TIER_ORDER:
        if tier not in by_tier:
            continue
        parts.append(f"<h2>{e(TIER_TITLES.get(tier, tier))}</h2>")
        for t in by_tier[tier]:
            lv = str(t["live"])
            badge = ('<span class="badge live">LIVE</span>' if lv == "live" else
                     '<span class="badge hind">HINDSIGHT</span>' if lv == "hindsight" else
                     f'<span class="badge prov">{e(lv)}</span>')
            status = "" if t["status"] == "ratified" else \
                f' <span class="badge prov">{e(str(t["status"]).split()[0])}</span>'
            parts.append(
                f'<div class="term"><b>{e(t["term"])}</b>{badge}{status}'
                f'<div>{e(" ".join(str(t["definition"]).split()))}</div>'
                f'<div class="chart">{e(" ".join(str(t["on_the_chart"]).split()))}</div></div>')
    banned = ", ".join(b["word"] for b in lex["banned_bare"])
    parts.append(f'<h2>Banned bare words</h2><p class="pre">Never alone in a definition, emission, '
                 f'or CLI terminal (compounds only): <b>{e(banned)}</b></p>')
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render PA lexicon to desk [st-g9y]")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    lex = yaml.safe_load((REPO_ROOT / "docs/lexicon/lexicon.yaml").read_text())
    out = Path("/tmp/desk-pa-lexicon.html")
    out.write_text(render(lex), encoding="utf-8")
    print(f"rendered {len(lex['terms'])} terms -> {out}")
    if not args.no_open:
        open_in_browser(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
