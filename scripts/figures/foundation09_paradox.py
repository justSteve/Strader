#!/usr/bin/env python3
"""Foundation-09 supporting figures — the 7/22 atom/leg paradox. [st-ndw]

Generates two inline SVGs for docs/foundation/09-fundamental-units.md and
splices them between marker comments in the doc:

  Figure 1 — the afternoon leg (11:19–14:59 CT) price path with its atom
  string: 221 per-minute cells. F1/F2/F3 carry the validated categorical
  hues; F4 "dead" deliberately renders as a short recessive tick — the
  absence class reads as absence.

  Figure 2 — the same 221 minutes as a running sum of effort, against
  coverage-matched corpus landmarks (leg percentiles rank within the 213
  full-RTH legs; window truncation biases leg statistics, so late-day
  collections are never mixed in).

Ground truth is the published store (run 20260728T123632Z):
data/measurement/moves/atoms.jsonl + moves.jsonl. Prices are regenerated
from the same tape through the same pipeline (moves.one_minute_atoms →
grade_atoms) and the regenerated cell string is asserted equal to the
stored one — any drift between store and pipeline fails the run rather
than silently drawing a different day.

Usage:
    .venv/bin/python3 scripts/figures/foundation09_paradox.py            # regenerate + splice
    .venv/bin/python3 scripts/figures/foundation09_paradox.py --check    # verify only, no write
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from bisect import bisect_right
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from market.orderflow import moves as mv            # noqa: E402
from market.orderflow.replay import read_corpus_day  # noqa: E402

RUN = "20260728T123632Z"
DAY = "2026-07-22"
LEG_START, LEG_END = "11:19", "14:59"               # inclusive atom range
STORE = ROOT / "data" / "measurement" / "moves"
DOC = ROOT / "docs" / "foundation" / "09-fundamental-units.md"
MARK_A, MARK_Z = "<!-- fig:722-paradox START -->", "<!-- fig:722-paradox END -->"

# Palette — validated (dataviz six-checks, light surface #fafafa, all-pairs):
# slots 1-3 for the three "something happening" cells; F4 dead is the absence
# class and wears recessive gridline gray at reduced height, never a hue.
CELL_FILL = {"F1": "#2a78d6", "F2": "#eb6834", "F3": "#1baf7a", "F4": "#c9c8c1"}
CELL_NAME = {"F1": "conviction", "F2": "absorption", "F3": "hollow", "F4": "dead"}
INK, INK2, MUTED, GRID = "#222222", "#52514e", "#898781", "#e1e0d9"
FONT = 'font-family="system-ui,-apple-system,Segoe UI,sans-serif"'


def load_store():
    atoms = [json.loads(l) for l in open(STORE / "atoms.jsonl")]
    legs = [json.loads(l) for l in open(STORE / "moves.jsonl")]
    atoms = [a for a in atoms if a["run"] == RUN]
    legs = [m for m in legs if m["run"] == RUN]
    leg_atoms = [a for a in atoms if a["day"] == DAY and LEG_START <= a["ct"] <= LEG_END]
    leg_row = next(m for m in legs if m["day"] == DAY and m["start_ct"] == LEG_START)
    rth = sorted(m["effort"] for m in legs if m["coverage"] == "rth")
    morning = next(m for m in legs if m["day"] == DAY and m["start_ct"] == "09:44")
    return leg_atoms, leg_row, rth, morning


def regenerate_closes(leg_atoms):
    """Minute closes from the tape via the same pipeline; assert cell parity."""
    trades = read_corpus_day(date.fromisoformat(DAY))
    graded = mv.grade_atoms(mv.one_minute_atoms(trades))
    window = [a for a in graded if LEG_START <= a.ts.strftime("%H:%M") <= LEG_END]
    if len(window) != len(leg_atoms):
        raise SystemExit(f"atom count drift: tape {len(window)} vs store {len(leg_atoms)}")
    regen = "".join(a.cell for a in window)
    stored = "".join(a["cell"] for a in leg_atoms)
    if regen != stored:
        raise SystemExit("cell-string drift between pipeline and published store — investigate before drawing")
    return [a.close for a in window]


def _nice_ticks(lo, hi, n=4):
    span = hi - lo
    step = max(1, round(span / n / 5) * 5)
    t0 = (int(lo) // step + 1) * step
    return list(range(t0, int(hi) + 1, step))


def fig1(leg_atoms, closes) -> str:
    W, H = 860, 380
    x0, x1 = 56, 844
    py0, py1 = 52, 236                      # price panel
    sy0, sy1 = 252, 288                     # atom strip
    n = len(leg_atoms)
    lo, hi = min(closes), max(closes)
    pad = (hi - lo) * 0.06
    lo, hi = lo - pad, hi + pad

    def X(i): return x0 + (x1 - x0) * i / (n - 1)
    def Y(p): return py1 - (py1 - py0) * (p - lo) / (hi - lo)

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-label="Price path and atom string of the 7/22 afternoon leg" '
             f'xmlns="http://www.w3.org/2000/svg" style="background:#fafafa">']
    parts.append(f'<text x="{x0}" y="24" {FONT} font-size="15" font-weight="600" fill="{INK}">'
                 f'The afternoon leg, atom by atom — 11:19 → 15:00 CT, −26.00 pts</text>')
    parts.append(f'<text x="{x0}" y="42" {FONT} font-size="12" fill="{MUTED}">'
                 f'ES 1-minute closes (top) and the leg&#8217;s atom string (below) — one tick per minute, colored by cell</text>')

    for t in _nice_ticks(lo, hi):
        y = Y(t)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{x0-8}" y="{y+4:.1f}" {FONT} font-size="11" fill="{MUTED}" text-anchor="end">{t}</text>')

    pts = " ".join(f"{X(i):.1f},{Y(c):.1f}" for i, c in enumerate(closes))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{INK2}" stroke-width="2" stroke-linejoin="round"/>')

    # annotations: the quiet pivot that opens the leg, the climax atom that ends it
    parts.append(f'<circle cx="{X(0):.1f}" cy="{Y(closes[0]):.1f}" r="4" fill="{INK2}"/>')
    parts.append(f'<text x="{X(0)+8:.1f}" y="{Y(closes[0])+20:.1f}" {FONT} font-size="11" fill="{MUTED}">'
                 f'11:19 — quiet pivot, F4 dead 0.276</text>')
    parts.append(f'<circle cx="{X(n-1):.1f}" cy="{Y(closes[-1]):.1f}" r="4" fill="{CELL_FILL["F1"]}"/>')
    parts.append(f'<text x="{X(n-1)-8:.1f}" y="{Y(closes[-1])-10:.1f}" {FONT} font-size="11" fill="{MUTED}" '
                 f'text-anchor="end">14:59 — loudest atom of the day, F1 1.000</text>')

    # atom string: F1/F2/F3 full-height, F4 short center tick (absence recedes)
    w = (x1 - x0) / n
    for i, a in enumerate(leg_atoms):
        cell = a["cell"]
        if cell == "F4":
            y, h = (sy0 + sy1) / 2 - 4, 8
        else:
            y, h = sy0, sy1 - sy0
        title = (f'{a["ct"]} · {cell} {CELL_NAME[cell]} {a["grade"]:.3f} · '
                 f'{a["vol"]:,} contracts · net {a["net"]:+.2f}')
        parts.append(f'<rect x="{x0+i*w:.2f}" y="{y:.1f}" width="{max(w-0.6,1.2):.2f}" height="{h}" '
                     f'fill="{CELL_FILL[cell]}"><title>{title}</title></rect>')

    # time axis under the strip
    ticks = [("11:30", 11), ("12:00", 41), ("12:30", 71), ("13:00", 101),
             ("13:30", 131), ("14:00", 161), ("14:30", 191), ("15:00", 220)]
    for lab, i in ticks:
        parts.append(f'<text x="{X(i):.1f}" y="{sy1+16}" {FONT} font-size="11" fill="{MUTED}" '
                     f'text-anchor="middle">{lab}</text>')

    # legend with counts (the relief labels the contrast WARN requires)
    from collections import Counter
    c = Counter(a["cell"] for a in leg_atoms)
    lx = x0
    ly = sy1 + 44
    for cell in ("F1", "F2", "F3", "F4"):
        h = 6 if cell == "F4" else 12
        yoff = 3 if cell == "F4" else 0
        parts.append(f'<rect x="{lx}" y="{ly-10+yoff}" width="12" height="{h}" fill="{CELL_FILL[cell]}"/>')
        label = f'{cell} {CELL_NAME[cell]} ×{c[cell]}'
        parts.append(f'<text x="{lx+18}" y="{ly}" {FONT} font-size="12" fill="{INK2}">{label}</text>')
        lx += 18 + 9 * len(label) + 24
    parts.append('</svg>')
    return "\n".join(parts)


def fig2(leg_atoms, leg_row, rth_efforts, morning) -> str:
    W, H = 860, 320
    x0, x1 = 72, 844
    py0, py1 = 52, 252
    n = len(leg_atoms)
    cum = []
    s = 0
    for a in leg_atoms:
        s += a["vol"]
        cum.append(s)
    total = s
    med = statistics.median(rth_efforts)
    top = max(total, morning["effort"]) * 1.22   # headroom so the end annotation clears the subtitle row

    def X(i): return x0 + (x1 - x0) * i / (n - 1)
    def Y(v): return py1 - (py1 - py0) * v / top

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-label="Cumulative effort of the afternoon leg vs corpus landmarks" '
             f'xmlns="http://www.w3.org/2000/svg" style="background:#fafafa">']
    parts.append(f'<text x="{x0}" y="24" {FONT} font-size="15" font-weight="600" fill="{INK}">'
                 f'The same 221 minutes as a running sum of effort</text>')
    parts.append(f'<text x="{x0}" y="42" {FONT} font-size="12" fill="{MUTED}">'
                 f'small efforts, summed minute over minute — atom texture below, corpus-scale mass at the right edge</text>')

    for v in range(0, int(top), 100_000):
        y = Y(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{x0-8}" y="{y+4:.1f}" {FONT} font-size="11" fill="{MUTED}" text-anchor="end">{v//1000}k</text>')

    area = f"M {X(0):.1f},{py1} " + " ".join(f"L {X(i):.1f},{Y(v):.1f}" for i, v in enumerate(cum)) + f" L {X(n-1):.1f},{py1} Z"
    parts.append(f'<path d="{area}" fill="#cde2fb" fill-opacity="0.55"/>')
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(cum))
    parts.append(f'<polyline points="{line}" fill="none" stroke="{CELL_FILL["F1"]}" stroke-width="2"/>')

    # invisible hover columns carrying per-minute native tooltips
    w = (x1 - x0) / n
    for i, a in enumerate(leg_atoms):
        parts.append(f'<rect x="{x0+i*w:.2f}" y="{py0}" width="{w:.2f}" height="{py1-py0}" fill="transparent">'
                     f'<title>{a["ct"]} · +{a["vol"]:,} → cum {cum[i]:,}</title></rect>')

    for v, lab in ((med, f"median full-RTH leg — {round(med/1000)}k"),
                   (morning["effort"], f"7/22&#8217;s own morning leg-grind, whole — {round(morning['effort']/1000)}k")):
        y = Y(v)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{MUTED}" '
                     f'stroke-width="1.5" stroke-dasharray="6 4"/>')
        parts.append(f'<text x="{x0+6}" y="{y-6:.1f}" {FONT} font-size="11" fill="{MUTED}">{lab}</text>')

    parts.append(f'<circle cx="{X(n-1):.1f}" cy="{Y(total):.1f}" r="5" fill="{CELL_FILL["F1"]}"/>')
    parts.append(f'<text x="{x1-4}" y="{Y(total)-24:.1f}" {FONT} font-size="12" font-weight="600" fill="{INK}" '
                 f'text-anchor="end">{total:,} contracts</text>')
    parts.append(f'<text x="{x1-4}" y="{Y(total)-8:.1f}" {FONT} font-size="11" fill="{MUTED}" text-anchor="end">'
                 f'{leg_row["effort_pct"]}th percentile of the {len(rth_efforts)} full-RTH legs → F1 at leg scale</text>')

    ticks = [("11:30", 11), ("12:30", 71), ("13:30", 131), ("14:30", 191), ("15:00", 220)]
    for lab, i in ticks:
        parts.append(f'<text x="{X(i):.1f}" y="{py1+18}" {FONT} font-size="11" fill="{MUTED}" '
                     f'text-anchor="middle">{lab}</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify store/pipeline parity only")
    args = ap.parse_args()

    leg_atoms, leg_row, rth, morning = load_store()
    assert len(leg_atoms) == 221, f"expected 221 leg atoms, got {len(leg_atoms)}"
    assert leg_row["effort"] == sum(a["vol"] for a in leg_atoms), "leg effort != sum of atom volumes"
    closes = regenerate_closes(leg_atoms)
    if args.check:
        print("store/pipeline parity OK — 221 atoms, cell strings identical")
        return 0

    block = "\n".join([
        MARK_A,
        fig1(leg_atoms, closes),
        "",
        f'*Figure 1 — every minute of the fade, graded. Full-height ticks are atoms with something '
        f'happening; the short gray ticks are F4 dead — the leg is mostly absence. '
        f'(run `{RUN}`, hover any tick for its atom.)*',
        "",
        fig2(leg_atoms, leg_row, rth, morning),
        "",
        f'*Figure 2 — the paradox resolved: no single minute is loud, but the sum passes the whole '
        f'morning leg-grind and lands in the corpus&#8217;s top decile of full-RTH legs. Leg percentiles '
        f'rank against coverage-matched legs only (window truncation biases leg statistics).*',
        MARK_Z,
    ])

    doc = DOC.read_text()
    if MARK_A in doc:
        pre, rest = doc.split(MARK_A, 1)
        _, post = rest.split(MARK_Z, 1)
        doc = pre + block + post
    else:
        anchor = "say which tier you mean.\n"
        if anchor not in doc:
            raise SystemExit("anchor paragraph not found in doc — insertion point moved")
        doc = doc.replace(anchor, anchor + "\n" + block + "\n", 1)
    DOC.write_text(doc)
    print(f"spliced 2 figures into {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
