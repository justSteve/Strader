"""The blotter's aggregates and its write-up. [st-uc23]

Every aggregate splits rows by mark path (prints | estimated) and never pools
them — Strader's counter §5.2: pooled, the P&L becomes a function of which
days got an OPRA pull. The 2025/2026 halves are computed and reported on
row P&L; nothing is discarded on the split (Steve, 2026-08-30 — the discard
gate is retired, the split is still shown).
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Iterable, Mapping, Sequence

__all__ = ["aggregate", "grid_table", "render_markdown"]


def _stats(pnls: Sequence[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"n": 0}
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    return {
        "n": n, "wins": wins, "losses": losses, "flat": n - wins - losses,
        "sum_pts": round(sum(pnls), 2), "mean_pts": round(sum(pnls) / n, 3),
        "median_pts": round(statistics.median(pnls), 3),
        "sum_usd": round(sum(pnls) * 100.0, 2),
    }


def aggregate(rows: Iterable[Mapping]) -> dict:
    """{rule_id: {mark_path: {"all": stats, "2025": stats, "2026": stats, "exits": {reason: n}}}}"""
    by: dict[str, dict[str, list[Mapping]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[r["rule_id"]][r["mark_path"]].append(r)
    out: dict = {}
    for rule_id in sorted(by):
        out[rule_id] = {}
        for path in sorted(by[rule_id]):
            rs = by[rule_id][path]
            halves: dict[str, list[float]] = defaultdict(list)
            for r in rs:
                halves[r["day"][:4]].append(float(r["pnl_pts"]))
            exits: dict[str, int] = defaultdict(int)
            for r in rs:
                exits[r["exit_reason"]] += 1
            block = {"all": _stats([float(r["pnl_pts"]) for r in rs]), "exits": dict(sorted(exits.items()))}
            for half in sorted(halves):
                block[half] = _stats(halves[half])
            if path == "estimated":
                would: dict[str, int] = defaultdict(int)
                for r in rs:
                    ee = r.get("estimated_exit") or {}
                    would[ee.get("would_exit_reason_extreme", "?")] += 1
                block["proxy_would_exit_extreme"] = dict(sorted(would.items()))
            out[rule_id][path] = block
    return out


def grid_table(rows: Iterable[Mapping]) -> dict:
    """{rule_id: {cell: stats}} over printed rows only (the grid is null elsewhere)."""
    by: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    exits: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in rows:
        g = r.get("grid")
        if not g:
            continue
        for cell, v in g.items():
            by[r["rule_id"]][cell].append(float(v["pnl_pts"]))
            exits[r["rule_id"]][cell][v["exit_reason"]] += 1
    out: dict = {}
    for rule_id in sorted(by):
        out[rule_id] = {}
        for cell in sorted(by[rule_id], key=lambda c: (float(c.split("x")[0]), int(c.split("x")[1]))):
            st = _stats(by[rule_id][cell])
            st["exits"] = dict(sorted(exits[rule_id][cell].items()))
            out[rule_id][cell] = st
    return out


def _fmt(st: Mapping) -> str:
    if st.get("n", 0) == 0:
        return "— | — | — | — | —"
    return (f"{st['n']} | {st['wins']}/{st['losses']}/{st['flat']} | {st['sum_pts']:+.2f} | "
            f"{st['median_pts']:+.2f} | {st['sum_usd']:+,.0f}")


def render_markdown(rows: Sequence[Mapping], reports: Sequence[Mapping], *, as_of: str, day_from: str,
                    day_to: str, rules_meta: Sequence[Mapping], calibration: str | None,
                    estimated_mark_doc: str | None) -> str:
    agg = aggregate(rows)
    grid = grid_table(rows)
    n_days = len(reports)
    skipped = [r for r in reports if r.get("skip")]
    unpriced = [u for r in reports for u in r.get("unpriced", [])]
    fires = [f for r in reports for f in r.get("fires", []) if f.get("call")]
    lines: list[str] = []
    lines.append(f"# Blotter Replay — registered rules scored as trades, {as_of}")
    lines.append("")
    lines.append(f"**Bead:** st-uc23 (*Blotter Replay*) · **Range:** {day_from} → {day_to} · **Rows:** "
                 f"`data/measurement/blotter/replay-<day>.jsonl` · **Script:** "
                 f"`scripts/measurement/blotter_replay.py` · **Calibration for estimated rows:** "
                 f"`{calibration}`" if calibration else
                 f"**Bead:** st-uc23 (*Blotter Replay*) · **Range:** {day_from} → {day_to} · **Rows:** "
                 f"`data/measurement/blotter/replay-<day>.jsonl` · **Script:** `scripts/measurement/blotter_replay.py`")
    lines.append("")
    lines.append("Every number below is **measured** from the rows named above. Rows marked from the "
                 "symbol's own prints and rows marked from the ES→premium proxy are **never pooled**: "
                 "each table splits them. Estimated rows resolve `time` only; what the proxy would "
                 "have resolved is shown beside, and the residuals it carries are in "
                 + (f"`{estimated_mark_doc}`." if estimated_mark_doc else "the estimated-mark write-up."))
    lines.append("")
    lines.append("## 0. What was scanned")
    lines.append("")
    lines.append("| | count |")
    lines.append("|---|---|")
    lines.append(f"| days in range with an ES file | {n_days} |")
    lines.append(f"| days skipped (thin tape or no file) | {len(skipped)} |")
    lines.append(f"| rule calls (a rule said up or down) | {len(fires)} |")
    lines.append(f"| calls priced (rows) | {len(rows)} |")
    lines.append(f"| calls unpriced | {len(unpriced)} |")
    if unpriced:
        reasons: dict[str, int] = defaultdict(int)
        for u in unpriced:
            reasons[u["reason"]] += 1
        lines.append("")
        lines.append("Unpriced calls by reason (a call the corpus could not price, named so the count is honest):")
        lines.append("")
        lines.append("| reason | calls |")
        lines.append("|---|---|")
        for k in sorted(reasons):
            lines.append(f"| {k} | {reasons[k]} |")
    lines.append("")
    lines.append("## 1. The rules")
    lines.append("")
    lines.append("| rule | fires at | instrument | declared exit | registered |")
    lines.append("|---|---|---|---|---|")
    for m in rules_meta:
        ex = m["exit"]
        lines.append(f"| `{m['id']}` | {', '.join(m['fire_at'])} CT | {m['instrument']} | "
                     f"stop {ex['stop_pts']:.2f} pts · target +{ex['target_pct']:.0f}% · {ex['time']} | `{m['registered']}` |")
    lines.append("")
    lines.append("## 2. Rows by rule and mark path — the declared exit")
    lines.append("")
    lines.append("P&L in premium points on one contract (1 pt = $100). `w/l/f` = rows that gained / lost / closed flat. "
                 "Halves are calendar years of the row's day.")
    lines.append("")
    lines.append("| rule | mark path | rows | w/l/f | sum pts | median pts | sum $ | exits | 2025: n · sum · median | 2026: n · sum · median |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for rule_id in agg:
        for path in agg[rule_id]:
            b = agg[rule_id][path]
            exits = ", ".join(f"{k} {v}" for k, v in b["exits"].items())
            h25 = b.get("2025", {"n": 0}); h26 = b.get("2026", {"n": 0})
            def half(h):
                return f"{h['n']} · {h['sum_pts']:+.2f} · {h['median_pts']:+.2f}" if h.get("n") else "—"
            lines.append(f"| `{rule_id}` | {path} | {_fmt(b['all'])} | {exits} | {half(h25)} | {half(h26)} |")
    est_lines = []
    for rule_id in agg:
        b = agg[rule_id].get("estimated")
        if b and b.get("proxy_would_exit_extreme"):
            est_lines.append(f"| `{rule_id}` | " + ", ".join(f"{k} {v}" for k, v in b["proxy_would_exit_extreme"].items()) + " |")
    if est_lines:
        lines.append("")
        lines.append("Estimated rows: what the proxy would have resolved at the minute's ES extreme "
                     "(carried on the row as `estimated_exit`, not in the P&L):")
        lines.append("")
        lines.append("| rule | proxy would exit |")
        lines.append("|---|---|")
        lines.extend(est_lines)
    lines.append("")
    lines.append("## 3. The premium grid beside the declared exit — printed rows only")
    lines.append("")
    lines.append("Stop in premium points below the entry × target as a percent of the entry, first touch wins, "
                 "the same rows as the `prints` line above. This is the blotter's premium grid on registered "
                 "rules; it is not st-fpc4's ES-point grid on recognizer confirmations.")
    for rule_id in grid:
        lines.append("")
        lines.append(f"**`{rule_id}`**")
        lines.append("")
        lines.append("| stop × target | rows | w/l/f | sum pts | median pts | sum $ | exits |")
        lines.append("|---|---|---|---|---|---|---|")
        for cell, st in grid[rule_id].items():
            exits = ", ".join(f"{k} {v}" for k, v in st["exits"].items())
            lines.append(f"| {cell} | {_fmt(st)} | {exits} |")
    lines.append("")
    lines.append("## 4. Determinism")
    lines.append("")
    lines.append("Two runs over one range with unchanged code and files are byte-identical (rows and this "
                 "document); the test pins it on a synthetic corpus and the run manifest records the "
                 "range. A rule change ships its blotter diff as the review.")
    lines.append("")
    return "\n".join(lines)
