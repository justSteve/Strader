#!/usr/bin/env python3
"""Anchored /ES volume profile from Schwab minute candles. [st-2f2]

Offline: reads a JSONL dump produced by `broker_schwab/readers/history.py
--out` (one full price-history response per line) — no live API access here.

Builds a volume-at-price profile anchored at a cash open (08:30 CT) and
running through the latest candle, overnight included. Minute bars carry
volume-per-bar, not volume-per-price, so each bar's volume is distributed
uniformly across its high-low range in 0.25 ticks — the standard
approximation; structure (HVN/LVN/POC) is robust to it at >=1-pt display
buckets even though exact per-tick counts are not.

Usage:
    python3 scripts/es_volume_profile.py DUMP.jsonl --anchor 2026-07-23 \
        [--out /tmp/desk-es-volume-profile.html] [--levels "7474:major,7447:major"]
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
TICK = 0.25
CASH_OPEN = _time(8, 30)
CASH_CLOSE = _time(15, 0)


def load_candles(dump_path: Path) -> list[dict]:
    candles: list[dict] = []
    for line in dump_path.read_text().splitlines():
        if not line.strip():
            continue
        candles.extend(json.loads(line).get("candles", []))
    # de-dup on timestamp (multiple dump lines may overlap), keep last
    seen: dict[int, dict] = {c["datetime"]: c for c in candles}
    return [seen[k] for k in sorted(seen)]


def build_profile(candles: list[dict], anchor_day: str):
    """Return (buckets, meta). buckets: {tick_price: [cash_vol, on_vol]}."""
    y, m, d = (int(x) for x in anchor_day.split("-"))
    anchor = datetime(y, m, d, CASH_OPEN.hour, CASH_OPEN.minute, tzinfo=CENTRAL)
    buckets: dict[float, list[float]] = {}
    first = last = None
    for c in candles:
        ts = datetime.fromtimestamp(c["datetime"] / 1000, tz=CENTRAL)
        if ts < anchor:
            continue
        first = first or ts
        last = ts
        in_cash = (ts.date() == anchor.date()
                   and CASH_OPEN <= ts.time() < CASH_CLOSE)
        lo, hi, vol = c["low"], c["high"], c["volume"]
        n_ticks = max(1, round((hi - lo) / TICK) + 1)
        share = vol / n_ticks
        for i in range(n_ticks):
            px = round((lo + i * TICK) / TICK) * TICK
            slot = buckets.setdefault(px, [0.0, 0.0])
            slot[0 if in_cash else 1] += share
    last_close = None
    for c in reversed(candles):
        ts = datetime.fromtimestamp(c["datetime"] / 1000, tz=CENTRAL)
        if ts >= anchor:
            last_close = c["close"]
            break
    return buckets, {"anchor": anchor, "first": first, "last": last,
                     "last_close": last_close}


def aggregate(buckets: dict[float, list[float]], step: float):
    rows: dict[float, list[float]] = {}
    for px, (cash, on) in buckets.items():
        key = (px // step) * step
        slot = rows.setdefault(key, [0.0, 0.0])
        slot[0] += cash
        slot[1] += on
    return dict(sorted(rows.items(), reverse=True))


def value_area(rows: dict[float, list[float]]):
    """POC + 70% value area over total volume, expanding from POC."""
    totals = {px: sum(v) for px, v in rows.items()}
    poc = max(totals, key=totals.get)
    target = 0.70 * sum(totals.values())
    prices = sorted(totals)
    i = j = prices.index(poc)
    acc = totals[poc]
    while acc < target and (i > 0 or j < len(prices) - 1):
        up = totals[prices[j + 1]] if j < len(prices) - 1 else -1
        dn = totals[prices[i - 1]] if i > 0 else -1
        if up >= dn:
            j += 1
            acc += totals[prices[j]]
        else:
            i -= 1
            acc += totals[prices[i]]
    return poc, prices[i], prices[j]  # poc, VAL, VAH


def render(rows, meta, step, levels, out_path: Path):
    poc, val, vah = value_area(rows)
    max_total = max(sum(v) for v in rows.values())
    total_vol = sum(sum(v) for v in rows.values())
    cash_vol = sum(v[0] for v in rows.values())
    lvl_map = {}
    for spec in levels:
        px, _, tag = spec.partition(":")
        lvl_map[float(px)] = tag or "level"

    bars = []
    for px, (cash, on) in rows.items():
        total = cash + on
        w_cash = 100.0 * cash / max_total
        w_on = 100.0 * on / max_total
        classes = ["row"]
        if px == poc:
            classes.append("poc")
        if val <= px <= vah:
            classes.append("va")
        near = [f"{p:g} {t}" for p, t in lvl_map.items() if px <= p < px + step]
        lvl_txt = f" — {', '.join(near)}" if near else ""
        cur = meta["last_close"]
        is_cur = cur is not None and px <= cur < px + step
        if is_cur:
            classes.append("cur")
        tip = (f"{px:g}–{px + step:g}: total {total:,.0f}"
               f" (cash {cash:,.0f} / o-n {on:,.0f}, {100 * total / total_vol:.1f}%)"
               f"{lvl_txt}{' — LAST' if is_cur else ''}")
        label = f"{px:g}" if (px % 5 == 0 or px == poc or near or is_cur) else ""
        note = (" POC" if px == poc else "") + (f" ◀ {cur:g}" if is_cur else "") + \
               (f" — {', '.join(near)}" if near else "")
        bars.append(
            f'<div class="{" ".join(classes)}" data-tip="{html.escape(tip)}">'
            f'<span class="px">{label}</span>'
            f'<span class="track"><i class="cash" style="width:{w_cash:.2f}%"></i>'
            f'<i class="on" style="width:{w_on:.2f}%"></i></span>'
            f'<span class="note">{html.escape(note)}</span></div>')

    table = "".join(
        f"<tr><td>{px:g}</td><td>{v[0]:,.0f}</td><td>{v[1]:,.0f}</td>"
        f"<td>{sum(v):,.0f}</td></tr>" for px, v in rows.items())

    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>/ES anchored volume profile</title>
<style>
.viz-root {{
  color-scheme: light;
  --surface-1:#fcfcfb; --surface-2:#f1f0ee;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7a7975;
  --cash:#2a78d6; --on:#eb6834; --va-bg:rgba(42,120,214,.08);
  --ref:#7a7975; --cur:#0b0b0b;
}}
@media (prefers-color-scheme: dark) {{
  .viz-root {{
    color-scheme: dark;
    --surface-1:#1a1a19; --surface-2:#242422;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
    --cash:#3987e5; --on:#d95926; --va-bg:rgba(57,135,229,.14);
    --ref:#8f8e86; --cur:#ffffff;
  }}
}}
body {{ margin:0; }}
.viz-root {{ font-family:-apple-system,'Segoe UI',sans-serif; background:var(--surface-1);
  color:var(--text-primary); padding:36px 48px; min-height:100vh; box-sizing:border-box; }}
h1 {{ font-size:20px; margin:0 0 4px; }}
.sub {{ color:var(--text-secondary); font-size:13px; margin-bottom:18px; }}
.stats {{ display:flex; gap:28px; margin:0 0 22px; flex-wrap:wrap; }}
.stat b {{ display:block; font-size:20px; font-weight:600; }}
.stat span {{ font-size:12px; color:var(--text-secondary); }}
.legend {{ display:flex; gap:18px; font-size:12.5px; color:var(--text-secondary); margin-bottom:10px; }}
.legend i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; }}
.row {{ display:flex; align-items:center; height:9px; margin-bottom:2px; position:relative; }}
.row.va {{ background:var(--va-bg); }}
.px {{ width:52px; text-align:right; padding-right:10px; font-size:10.5px;
  color:var(--text-muted); font-variant-numeric:tabular-nums; flex:none; }}
.track {{ flex:1; display:flex; height:7px; }}
.track i {{ height:100%; border-radius:0 3px 3px 0; }}
.track i.cash {{ background:var(--cash); margin-right:2px; }}
.track i.on {{ background:var(--on); }}
.row.poc .track i {{ outline:2px solid var(--surface-1); box-shadow:0 0 0 3px var(--cash); }}
.note {{ position:absolute; left:64px; right:0; pointer-events:none; font-size:10px;
  color:var(--text-secondary); text-align:right; padding-right:6px; }}
.row.cur .note {{ color:var(--text-primary); font-weight:600; }}
.row:hover .track i {{ filter:brightness(1.15); }}
#tip {{ position:fixed; display:none; background:var(--surface-2); color:var(--text-primary);
  font-size:12px; padding:6px 10px; border-radius:6px; pointer-events:none;
  box-shadow:0 2px 10px rgba(0,0,0,.25); z-index:9; max-width:340px; }}
details {{ margin-top:26px; font-size:13px; }}
table {{ border-collapse:collapse; margin-top:8px; }}
td,th {{ padding:3px 14px; text-align:right; font-variant-numeric:tabular-nums;
  border-bottom:1px solid var(--surface-2); }}
</style></head><body><div class="viz-root">
<h1>/ES volume profile — anchored {meta['anchor'].strftime('%-m/%-d %H:%M CT')} cash open</h1>
<div class="sub">through {meta['last'].strftime('%-m/%-d %H:%M CT')} · Schwab minute candles,
volume distributed across each bar's range ({step:g}-pt buckets) · shaded band = 70% value area</div>
<div class="stats">
  <div class="stat"><b>{poc:g}–{poc + step:g}</b><span>POC</span></div>
  <div class="stat"><b>{val:g} / {vah + step:g}</b><span>value area low / high</span></div>
  <div class="stat"><b>{meta['last_close']:g}</b><span>last</span></div>
  <div class="stat"><b>{total_vol:,.0f}</b><span>contracts ({100 * cash_vol / total_vol:.0f}% cash session)</span></div>
</div>
<div class="legend"><span><i style="background:var(--cash)"></i>Cash session 7/23</span>
<span><i style="background:var(--on)"></i>Overnight + pre-open</span></div>
{''.join(bars)}
<div id="tip"></div>
<details><summary>Data table</summary><table>
<tr><th>Bucket</th><th>Cash</th><th>Overnight</th><th>Total</th></tr>{table}</table></details>
<script>
const tip = document.getElementById('tip');
document.querySelectorAll('.row').forEach(r => {{
  r.addEventListener('mousemove', e => {{
    tip.style.display = 'block';
    tip.textContent = r.dataset.tip;
    tip.style.left = Math.min(e.clientX + 14, innerWidth - 360) + 'px';
    tip.style.top = (e.clientY + 14) + 'px';
  }});
  r.addEventListener('mouseleave', () => tip.style.display = 'none');
}});
</script>
</div></body></html>"""
    out_path.write_text(doc)
    return poc, val, vah


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dump", help="JSONL from history.py --out")
    ap.add_argument("--anchor", required=True, help="cash-open day YYYY-MM-DD")
    ap.add_argument("--out", default="/tmp/desk-es-volume-profile.html")
    ap.add_argument("--bucket", type=float, default=None,
                    help="display bucket in points (default: auto 1 or 2)")
    ap.add_argument("--levels", default="",
                    help="comma list px[:tag] reference levels to mark")
    args = ap.parse_args()

    candles = load_candles(Path(args.dump))
    buckets, meta = build_profile(candles, args.anchor)
    if not buckets:
        print("no candles at/after anchor")
        return 1
    span = max(buckets) - min(buckets)
    step = args.bucket or (1.0 if span <= 75 else 2.0)
    rows = aggregate(buckets, step)
    levels = [s for s in args.levels.split(",") if s.strip()]
    poc, val, vah = render(rows, meta, step, levels, Path(args.out))
    print(f"profile: {min(buckets):g}-{max(buckets):g} ({len(rows)} rows @ {step:g}pt) "
          f"POC {poc:g} VA {val:g}-{vah + step:g} last {meta['last_close']:g}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    main()
