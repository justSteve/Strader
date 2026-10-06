#!/usr/bin/env python3
"""Emission Review packet — one FP-chart bar, its emissions, its context. [st-rf95]

    .venv/bin/python tools/emission_review.py --bar 232            # today
    .venv/bin/python tools/emission_review.py --day 2026-10-06 --bar 232

``--bar`` is the PAGE's label — the "Bar N" the FP chart prints in an emission's
detail panel and the emissions table, which is the bar index + 1. The packet
records both so nobody has to redo the off-by-one.

WHAT THIS IS. The data half of the Emission Review lookback (Steve, 2026-10-06:
"a procedure to review the emissions to FP chart to have an agent provide
commentary on the text of the emission"). It gathers, deterministically and in
one shape every time: the emission text verbatim, the bar, the twenty minutes of
tape before it, the Mancini levels and GEX around it, and — clearly fenced off
as HINDSIGHT — what price did in the bars after. The commentary half (bias the
emission calls, how much it should matter, what confirms or negates) is the
`/emission-review` skill's job; this tool writes the card with those sections
left for it.

SOURCES, IN ORDER.
  1. The drill bridge (127.0.0.1:7788/bars) when ``--day`` is the day the bridge
     is serving. It holds exactly what the page received, context lines
     included — Fuel and GEX are payload-only and never reach the run log
     (market/orderflow/fuel.py, INTEGRATION CONTRACT).
  2. ``data/derived/live-parity/<day>.jsonl``, the feeder's run log, for any
     other day. It carries every recognition emission but NOT the context lines,
     so a Fuel bar reviewed after the fact from here shows no Fuel — the packet
     says so in ``source_note`` rather than presenting a quiet bar.

The packet is written next to the card, so the lookback keeps what the page said
even after the bridge has rolled over to the next day.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from market.orderflow.context_log import read_last_run  # noqa: E402
CT = ZoneInfo("America/Chicago")
BRIDGE = "http://127.0.0.1:7788"
OUT_ROOT = REPO / "docs" / "emission-reviews"
DESK_INBOX = Path("/mnt/c/Users/steve/zgent-bridge/Desk/inbox")
UNFILLED = "REVIEW: fill"
PRIOR_BARS = 10          # the run-up the reviewer reads the emission against
HINDSIGHT = (5, 10, 20)  # bars after the emission bar
LEVEL_BAND = 15.0        # Mancini levels within this many ES points of the close

# Where a reviewer reads what an emission type MEANS, and what has actually been
# MEASURED about its follow-through. "unmeasured" is a finding, not a gap to
# paper over: the card must then grade impact as reasoned, never as measured.
CANON = {
    "Fuel": ("knowledge/trapped-seller-fuel.md",
             "unmeasured — canon §Validation: a display of what the tape shows, "
             "not a graded signal, until the postmortem measurement exists"),
    "SetupRecognition": ("knowledge/index.md (setup concepts) · market/orderflow/",
                         "check data/measurement/ for the named setup before grading"),
    "Absorption": ("knowledge/index.md · market/orderflow/",
                   "data/measurement/absorption-impact-survey.jsonl"),
}


def ct(iso: str | None) -> str:
    if not iso:
        return "-"
    return datetime.fromisoformat(iso).astimezone(CT).strftime("%H:%M:%S")


def today_ct() -> _date:
    return datetime.now(CT).date()


def from_bridge(day: _date) -> tuple[list[dict], dict] | None:
    try:
        with urllib.request.urlopen(f"{BRIDGE}/bars?since=0", timeout=5) as r:
            d = json.load(r)
    except (OSError, ValueError):
        return None
    meta = d.get("meta") or {}
    if meta.get("day") != day.isoformat():
        return None
    return d.get("bars") or [], meta


def from_run_log(day: _date) -> tuple[list[dict], dict]:
    path = REPO / "data" / "derived" / "live-parity" / f"{day}.jsonl"
    if not path.exists():
        sys.exit(f"no bridge session and no run log for {day} ({path})")
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    # The log can hold several runs (a feeder restart replays the day from the
    # first print); the LAST run is the one the page was showing at the end.
    starts = [n for n, r in enumerate(rows) if r.get("k") == "run"] or [0]
    rows = rows[starts[-1]:]
    bars, meta = [], dict(rows[0]) if rows and rows[0].get("k") == "run" else {}
    for r in rows:
        if r.get("k") == "bar":
            bars.append({**r, "ev": []})
        elif r.get("k") == "ev" and r.get("bar_i") is not None and r["bar_i"] < len(bars):
            bars[r["bar_i"]]["ev"].append(r)
    # Context lines, from the feeder's separate log [st-2rsz]: Fuel goes back on
    # the bar's emissions as the page showed it (after the recognitions), GEX and
    # basis back on the bar. Absent for days before that log existed.
    ctx = read_last_run(context_log_path(day))
    for i, c in ctx.items():
        if i < len(bars) and c.get("t1") == bars[i]["t1"]:
            if c.get("fuel"):
                bars[i]["ev"].append({**c["fuel"], "context": True})
            for k in ("gex", "bs"):
                if c.get(k):
                    bars[i][k] = c[k]
    meta["_ctx_rows"] = len(ctx)
    cp = context_log_path(day)
    heads = ([json.loads(x) for x in cp.open(encoding="utf-8") if '"k":"run"' in x]
             if cp.exists() else [])
    meta["_ctx_backfill"] = bool(heads and heads[-1].get("backfill"))
    return bars, meta


def correct_fuel(day: _date, bars: list[dict], *, from_page: bool) -> None:
    """Put the CORRECTED Fuel line on each bar, and what the page printed beside it.

    Before st-ygoz the page's Fuel history phrase came from a file loaded once
    per run, so it could be hours stale: on 10-06, 28 of 34 lines. The
    corrected line (as-of-bar history from the tape, tools/backfill_context_log.py)
    is what the card reviews. The page's own line rides along as ``as_shown``
    whenever it differs, because Steve may have acted on it. ``as_shown`` comes
    from the bridge (``from_page``) or from ``<day>.shown.jsonl``; when neither
    holds it, the card says the page's line for that bar is not recorded.
    """
    base = REPO / "data" / "derived" / "live-context"
    fixed = read_last_run(base / f"{day}.jsonl")
    shown: dict[int, dict] = {}
    sp = base / f"{day}.shown.jsonl"
    if sp.exists():
        for line in sp.open(encoding="utf-8"):
            r = json.loads(line)
            shown[r["i"]] = r["fuel"]
    for i, b in enumerate(bars):
        page = next((e for e in b.get("ev", []) if e.get("type") == "Fuel"), None)
        if from_page and page is not None:
            shown.setdefault(i, page)
        c = fixed.get(i)
        if not c or c.get("t1") != b["t1"] or not c.get("fuel"):
            continue
        new = {**c["fuel"], "context": True}
        old = shown.get(i)
        new["as_shown"] = (old.get("reason") if old else None)
        new["as_shown_known"] = old is not None
        b["ev"] = [e for e in b.get("ev", []) if e.get("type") != "Fuel"] + [new]


def context_log_path(day: _date) -> Path:
    return REPO / "data" / "derived" / "live-context" / f"{day}.jsonl"


def mancini_near(day: _date, price: float) -> list[dict]:
    path = REPO / "runbook" / "mancini" / "parsed" / f"{day}.json"
    if not path.exists():
        return []
    out = []
    for lv in json.loads(path.read_text(encoding="utf-8")).get("levels", []):
        dist = round(lv["price"] - price, 2)
        if abs(dist) <= LEVEL_BAND:
            out.append({"price": lv["price"], "dist_pts": dist, "kind": lv["kind"],
                        "label": lv.get("label", ""), "intent": lv.get("intent", "unstated"),
                        "setup": lv.get("setup", "none")})
    return sorted(out, key=lambda x: -x["price"])


def hindsight(bars: list[dict], i: int) -> dict:
    base = bars[i]["c"]
    out = {"from_close": base}
    for n in HINDSIGHT:
        seg = bars[i + 1:i + 1 + n]
        if len(seg) < n:
            out[f"+{n}"] = {"available": len(seg)}
            continue
        out[f"+{n}"] = {
            "close_chg": round(seg[-1]["c"] - base, 2),
            "max_up": round(max(b["h"] for b in seg) - base, 2),
            "max_down": round(min(b["l"] for b in seg) - base, 2),
            "delta_sum": sum(b["d"] for b in seg),
            "until_ct": ct(seg[-1]["t1"]),
        }
    return out


def build(day: _date, label: int) -> dict:
    src = from_bridge(day) if day == today_ct() else None
    if src:
        bars, meta = src
        source, note = "bridge", ("the page's bars and recognitions as received; Fuel history "
                                  "corrected to as-of-bar where the page's was stale (st-ygoz)")
    else:
        bars, meta = from_run_log(day)
        if meta.get("_ctx_rows") and meta.get("_ctx_backfill"):
            source = "run-log+backfill"
            note = ("feeder run log plus a BACKFILLED context log — Fuel's tape components exact, "
                    "its level history CORRECTED to as-of-bar from the tape (st-ygoz), GEX matched "
                    "live on 326 of 327 bars when measured (tools/backfill_context_log.py)")
        elif meta.get("_ctx_rows"):
            source = "run-log+context"
            note = "feeder run log plus its context log — recognitions, Fuel and GEX as the page showed them"
        else:
            source = "run-log"
            note = ("feeder run log — recognition emissions only; no context log for this "
                    "day, so context lines (Fuel, GEX) are NOT in this record")
    correct_fuel(day, bars, from_page=source == "bridge")
    i = label - 1
    if not 0 <= i < len(bars):
        sys.exit(f"Bar {label} not in {day}: the session holds bars 1–{len(bars)}")
    b = bars[i]
    prior = bars[max(0, i - PRIOR_BARS):i]
    emissions = [{"type": e.get("type"), "text": e.get("reason", ""),
                  "context_only": bool(e.get("context")),
                  "fields": {k: v for k, v in e.items()
                             if k not in ("type", "reason", "context", "bar_i", "k")}}
                 for e in b.get("ev", [])]
    return {
        "day": day.isoformat(), "bar_label": label, "bar_index": i,
        "source": source, "source_note": note,
        "generated_ct": datetime.now(CT).strftime("%Y-%m-%d %H:%M CT"),
        "bar": {"start_ct": ct(b["t0"]), "close_ct": ct(b["t1"]),
                "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
                "vol": b["v"], "delta": b["d"], "dur_s": b.get("dur"),
                "poc": b.get("poc")},
        "emissions": emissions,
        "canon": {e["type"]: dict(zip(("read", "measured"),
                                      CANON.get(e["type"], ("market/orderflow/ (by source)",
                                                            "not catalogued — reviewer checks data/measurement/"))))
                  for e in emissions},
        "prior": {"bars": len(prior),
                  "from_ct": ct(prior[0]["t0"]) if prior else "-",
                  "net_pts": round(b["o"] - prior[0]["o"], 2) if prior else 0,
                  "high": max((x["h"] for x in prior), default=None),
                  "low": min((x["l"] for x in prior), default=None),
                  "delta_sum": sum(x["d"] for x in prior),
                  "deltas": [x["d"] for x in prior]},
        "mancini_near": mancini_near(day, b["c"]),
        "gex": b.get("gex"),
        # ES−SPX from this bar's close and the GEX snapshot's SPX spot: as old
        # as that snapshot (age_s), so a translation to strikes, not a quote.
        "basis_approx": (round(b["c"] - b["gex"]["spot"], 2)
                         if (b.get("gex") or {}).get("spot") else None),
        "vol_40m": sum(x["v"] for x in bars[:i + 1]
                       if (datetime.fromisoformat(b["t1"]) - datetime.fromisoformat(x["t1"])).total_seconds() <= 2400),
        "hindsight": hindsight(bars, i),
        "later_emissions": [{"bar_label": j + 1, "close_ct": ct(bars[j]["t1"]),
                             "type": e.get("type"),
                             "text": e.get("reason", "") + (
                                 " *(history corrected; page showed a stale phrase)*"
                                 if e.get("as_shown_known") and e.get("as_shown") != e.get("reason") else "")}
                            for j in range(i + 1, min(len(bars), i + 1 + HINDSIGHT[-1]))
                            for e in bars[j].get("ev", [])],
    }


def card(p: dict) -> str:
    """The Markdown card. Data sections filled here; commentary sections are
    the skill's, marked so an unfilled card can never pass for a reviewed one."""
    b, pr = p["bar"], p["prior"]
    L = [f"# Emission Review — {p['day']} · Bar {p['bar_label']} · {b['close_ct']} CT",
         "",
         f"*ES {b['c']} at the close of the bar · source: {p['source']} ({p['source_note']}) · "
         f"packet {p['generated_ct']} · [st-rf95]*", "",
         "## The emission", ""]
    if not p["emissions"]:
        L.append("_No emission on this bar._")
    for e in p["emissions"]:
        tag = " · context line, not a recognition" if e["context_only"] else ""
        L.append(f"- **{e['type']}**{tag}: {e['text']}")
        f = e["fields"]
        if e["type"] == "Fuel" and "as_shown_known" in f:
            if not f["as_shown_known"]:
                L.append("  - *Page showed:* not recorded for this bar. Before the st-ygoz fix its "
                         "history phrase came from a file loaded once per run and may have been stale.")
            elif f["as_shown"] != e["text"]:
                L.append(f"  - *Page showed:* {f['as_shown']}")
                L.append("  - *The history phrase above is corrected to what was true at this bar's "
                         "close (st-ygoz); the page's phrase was stale.*")
    L += ["", "## Bias the emission is calling", "", "<!-- REVIEW: fill -->", "",
          "## How much it should matter", "", "<!-- REVIEW: fill -->", "",
          "## What would confirm · what would negate", "", "<!-- REVIEW: fill -->", "",
          "## The bar and the run-up", "",
          f"- Bar: {b['start_ct']}–{b['close_ct']} CT · O {b['o']} H {b['h']} L {b['l']} C {b['c']} · "
          f"Δ {b['delta']:+d} · {b['dur_s']}s · POC {b['poc']}",
          f"- Prior {pr['bars']} bars (from {pr['from_ct']} CT): {pr['net_pts']:+} pts open-to-open · "
          f"range {pr['low']}–{pr['high']} · Δ sum {pr['delta_sum']:+d} · per bar {pr['deltas']}"]
    g = p.get("gex")
    if g:
        L.append(f"- GEX (SPX, published {ct(g.get('ts'))} CT): regime {g.get('regime')} · "
                 f"flip {g.get('flip')} · +{g.get('pos')} / −{g.get('neg')} · spot {g.get('spot')}")
    if p.get("basis_approx") is not None:
        L.append(f"- SPX ≈ ES − {p['basis_approx']:g} (this close vs the GEX snapshot's spot) · "
                 f"40-min volume to this bar {p['vol_40m']:,}")
    if p["mancini_near"]:
        L += ["", "**Mancini levels within 15 pts**", ""]
        for lv in p["mancini_near"]:
            L.append(f"- {lv['price']:g} ({lv['dist_pts']:+g}) {lv['kind']}"
                     + (f" — {lv['label']}" if lv["label"] else ""))
    L += ["", "## What happened next — HINDSIGHT", "",
          "*Not available when the emission fired. Read it as the outcome, never as the signal.*", ""]
    for k, v in p["hindsight"].items():
        if k == "from_close":
            continue
        if "available" in v:
            L.append(f"- {k} bars: only {v['available']} bar(s) printed so far")
        else:
            L.append(f"- {k} bars (to {v['until_ct']} CT): close {v['close_chg']:+} · "
                     f"best +{v['max_up']} · worst {v['max_down']} · Δ sum {v['delta_sum']:+d}")
    if p["later_emissions"]:
        L += ["", "**Later emissions in that window**", ""]
        for e in p["later_emissions"]:
            L.append(f"- Bar {e['bar_label']} ({e['close_ct']} CT) **{e['type']}**: {e['text']}")
    L += ["", "<!-- REVIEW: one line on whether the outcome bore the read out -->", "",
          "## Canon and measurement", ""]
    for t, c in p["canon"].items():
        L.append(f"- {t}: meaning in `{c['read']}` · follow-through: {c['measured']}")
    L += ["", "## Questions this card should be able to answer", "", "<!-- REVIEW: fill -->", ""]
    return "\n".join(L)


def deliver(card_path: Path, inbox: Path = DESK_INBOX) -> Path:
    """Drop a REVIEWED card into Desk's bridge inbox. Refuses an unfilled one:
    a card with its commentary missing must never reach Steve looking done."""
    text = card_path.read_text(encoding="utf-8")
    if UNFILLED in text:
        sys.exit(f"refused: {card_path} still has {text.count(UNFILLED)} "
                 f"'{UNFILLED}' marker(s) — write the commentary first")
    day, stem = card_path.parent.name, card_path.stem
    now = datetime.now(CT)
    front = ("---\nfrom: Strader\nto: Desk\n"
             f"topic: emission-review-{day}-{stem}\nkind: EMISSION-REVIEW\n"
             "priority: normal\nexpects_reply: false\n"
             f"date: {now:%Y-%m-%d}\nbead: st-rf95\n---\n\n")
    out = inbox / f"{now:%Y%m%dT%H%M%S}__Strader__emission-review-{day}-{stem}.md"
    out.write_text(front + text, encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deliver", type=Path, default=None,
                    help="send a reviewed card (docs/emission-reviews/<day>/bar-NNN.md) to Desk")
    ap.add_argument("--bar", type=int, help="the page's Bar label (index + 1)")
    ap.add_argument("--day", default=None, help="YYYY-MM-DD, default today CT")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args()
    if a.deliver:
        print(deliver(a.deliver))
        return 0
    if a.bar is None:
        ap.error("--bar is required (or --deliver <card>)")
    day = _date.fromisoformat(a.day) if a.day else today_ct()
    p = build(day, a.bar)
    out = a.out_dir or OUT_ROOT / p["day"]
    out.mkdir(parents=True, exist_ok=True)
    stem = f"bar-{p['bar_label']:03d}"
    (out / f"{stem}.json").write_text(json.dumps(p, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / f"{stem}.md").write_text(card(p), encoding="utf-8")
    print(out / f"{stem}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
