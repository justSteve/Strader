#!/usr/bin/env python3
"""Continuation traces — internals/VIX/orderflow state inside morning moves. [st-cdwe]

Steve's question (2026-08-03): standing inside one of the big one-sided
morning moves, what measurable trace says it CONTINUES? Not base rates —
live state. Candidates: market internals ($TICK/$TRIN/$ADD/$VOLD), $VIX
(backfilled this bead), and ES orderflow (aggressor delta, volume pace,
wiggle depth).

Method: for each day in data/measurement/morning_flush_study.json (the
st-gzwb move spans), walk minutes from the primary move's start to 10:15 CT
(the last 15 minutes are excluded — truncated lookahead). A minute is
labeled CONT if price extends >= EXT_PTS beyond the extreme-standing-at-t
within the next LOOKAHEAD minutes, else TERM. Every trace is causal (uses
data through minute t only) and oriented so HIGHER = confirms the move.

Internals are 1-minute candles read at their close — up to 59s stale vs the
tape. Minutes within a day are autocorrelated; day-clustered honesty:
aggregate AUC is reported alongside the median of per-day AUCs.

Usage:
    .venv/bin/python3 scripts/measurement/morning_flush_continuation.py

Output: data/measurement/morning_flush_continuation.json + a stderr summary.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from market.orderflow.replay import read_corpus_day  # noqa: E402

CT = ZoneInfo("America/Chicago")
CORPUS = ROOT / "data" / "corpus"
STUDY = ROOT / "data" / "measurement" / "morning_flush_study.json"
OUT = ROOT / "data" / "measurement" / "morning_flush_continuation.json"

LOOKAHEAD_MIN = 15   # minutes ahead a new extreme must print
EXT_PTS = 2.0        # how far beyond the standing extreme counts as continuation
LAST_LABELED = time(10, 15)  # minutes after this lack full lookahead


def load_internals(day: date) -> dict[str, dict[datetime, float]]:
    """symbol -> {minute (CT datetime) -> close}."""
    path = CORPUS / day.isoformat() / "internals.jsonl"
    out: dict[str, dict[datetime, float]] = defaultdict(dict)
    if not path.exists():
        return out
    with path.open() as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            prov = row.get("provenance", {})
            sym = prov.get("symbol")
            ts = prov.get("ts_candle")
            close = row.get("data", {}).get("close")
            if not sym or not ts or close is None:
                continue
            out[sym][datetime.fromisoformat(ts)] = close
    return out


def minute_bars(trades, start: datetime, end: datetime):
    """minute -> dict(close, high, low, delta, vol) for [start, end)."""
    bars: dict[datetime, dict] = {}
    for t in trades:
        if not (start <= t.ts < end):
            continue
        m = t.ts.replace(second=0, microsecond=0)
        b = bars.setdefault(m, dict(close=t.price, high=t.price, low=t.price,
                                    delta=0, vol=0))
        b["close"] = t.price
        b["high"] = max(b["high"], t.price)
        b["low"] = min(b["low"], t.price)
        if t.side == "B":
            b["delta"] += t.size
        elif t.side == "A":
            b["delta"] -= t.size
        b["vol"] += t.size
    return bars


def auc(cont_vals, term_vals):
    """Rank-sum P(cont > term) with tie credit — the Mann-Whitney AUC."""
    if not cont_vals or not term_vals:
        return None
    wins = ties = 0
    sv = sorted(term_vals)
    import bisect
    for x in cont_vals:
        lo = bisect.bisect_left(sv, x)
        hi = bisect.bisect_right(sv, x)
        wins += lo
        ties += hi - lo
    return (wins + 0.5 * ties) / (len(cont_vals) * len(term_vals))


def main():
    study = json.loads(STUDY.read_text())
    samples = []          # one dict per labeled minute
    day_events = []       # backtest-event states (T=2 resume_events)
    day_rows = []         # day-level one-sidedness

    for row in study:
        d = date.fromisoformat(row["date"])
        move = row.get("move")
        if not move:
            continue
        mdir = 1 if move["dir"] == "up" else -1
        m_start = datetime.combine(
            d, time.fromisoformat(move["start"]), CT)
        w_end = datetime.combine(d, time(10, 30), CT)
        try:
            trades = read_corpus_day(d)
        except FileNotFoundError:
            continue
        w_trades = [t for t in trades if time(8, 30) <= t.ts.time() < time(10, 30)]
        bars = minute_bars(w_trades, m_start.replace(second=0), w_end)
        if not bars:
            continue
        internals = load_internals(d)
        minutes = sorted(bars)

        # running extreme series + forward continuation label
        ext = None
        ext_series = {}
        for m in minutes:
            best = bars[m]["high"] if mdir == 1 else bars[m]["low"]
            ext = best if ext is None else (max(ext, best) if mdir == 1
                                            else min(ext, best))
            ext_series[m] = ext

        day_samples = []
        for i, m in enumerate(minutes):
            if m.time() > LAST_LABELED:
                break
            horizon = m + timedelta(minutes=LOOKAHEAD_MIN)
            future = [mm for mm in minutes if m < mm <= horizon]
            if not future:
                continue
            fut_best = (max(bars[mm]["high"] for mm in future) if mdir == 1
                        else min(bars[mm]["low"] for mm in future))
            cont = (fut_best - ext_series[m]) * mdir >= EXT_PTS

            def closes(sym, back):
                s = internals.get(sym, {})
                return [s.get(m - timedelta(minutes=k)) for k in range(back)]

            tick_now = closes("$TICK", 1)[0]
            tick10 = [v for v in closes("$TICK", 10) if v is not None]
            add10 = closes("$ADD", 11)
            vold10 = closes("$VOLD", 11)
            trin_now = closes("$TRIN", 1)[0]
            vix5 = closes("$VIX", 6)

            look5 = minutes[max(0, i - 4):i + 1]
            prev5 = minutes[max(0, i - 9):max(0, i - 4)]
            delta5 = sum(bars[mm]["delta"] for mm in look5)
            vol5 = sum(bars[mm]["vol"] for mm in look5)
            elapsed = minutes[:i + 1]
            avg_vol5 = 5 * sum(bars[mm]["vol"] for mm in elapsed) / len(elapsed)

            def depth(win):
                if not win:
                    return None
                worst = (min(bars[mm]["low"] for mm in win) if mdir == 1
                         else max(bars[mm]["high"] for mm in win))
                ref = ext_series[win[-1]]
                return (ref - worst) * mdir

            d5, dprev = depth(look5), depth(prev5)
            new_ext_5 = any(
                (bars[mm]["high"] if mdir == 1 else bars[mm]["low"]) == ext_series[mm]
                and (i == 0 or ext_series[mm] != ext_series.get(
                    minutes[max(0, minutes.index(mm) - 1)]))
                for mm in look5)

            s = dict(
                date=row["date"], minute=m.strftime("%H:%M"), cont=cont,
                tick_aligned=(tick_now * mdir) if tick_now is not None else None,
                tick_share10=(sum(1 for v in tick10 if v * mdir > 0) / len(tick10)
                              if tick10 else None),
                add_slope10=((add10[0] - add10[10]) * mdir
                             if add10[0] is not None and add10[10] is not None
                             else None),
                vold_slope10=((vold10[0] - vold10[10]) * mdir
                              if vold10[0] is not None and vold10[10] is not None
                              else None),
                trin_aligned=((trin_now - 1.0) * -mdir
                              if trin_now is not None else None),
                vix_slope5=((vix5[0] - vix5[5]) * -mdir
                            if vix5[0] is not None and vix5[5] is not None
                            else None),
                delta5_aligned=delta5 * mdir,
                delta_div=bool(new_ext_5 and delta5 * mdir < 0),
                vol_pace=(vol5 / avg_vol5 if avg_vol5 > 0 else None),
                wiggle_calm=(-(d5 - dprev)
                             if d5 is not None and dprev is not None else None),
            )
            day_samples.append(s)
        samples.extend(day_samples)

        # backtest events (T=2.0) — state at the event minute
        for ev in row.get("resume_events", {}).get("2.0", []):
            em = datetime.combine(d, time.fromisoformat(ev["t"]), CT)
            em = em.replace(second=0)
            match = next((s for s in day_samples if s["minute"] == em.strftime("%H:%M")), None)
            if match:
                day_events.append(dict(match, resumed=ev["resumed"],
                                       depth=ev["depth"]))

        # day-level one-sidedness over the move span
        span = [m for m in minutes if m <= datetime.combine(
            d, time.fromisoformat(move["end"]), CT)]
        ticks = [internals.get("$TICK", {}).get(m) for m in span]
        ticks = [v for v in ticks if v is not None]
        vix_span = [internals.get("$VIX", {}).get(m) for m in span]
        vix_span = [v for v in vix_span if v is not None]
        vold_end = internals.get("$VOLD", {}).get(span[-1]) if span else None
        day_rows.append(dict(
            date=row["date"], dir=move["dir"], size=move["size"],
            tick_sign_share=(sum(1 for v in ticks if v * mdir > 0) / len(ticks)
                             if ticks else None),
            vix_net=((vix_span[-1] - vix_span[0]) * -mdir if len(vix_span) > 1
                     else None),
            vold_end_aligned=(vold_end * mdir if vold_end is not None else None),
        ))

    # ---- aggregate ----
    metrics = ["tick_aligned", "tick_share10", "add_slope10", "vold_slope10",
               "trin_aligned", "vix_slope5", "delta5_aligned", "vol_pace",
               "wiggle_calm"]
    summary = {}
    for k in metrics:
        cont = [s[k] for s in samples if s["cont"] and s[k] is not None]
        term = [s[k] for s in samples if not s["cont"] and s[k] is not None]
        a = auc(cont, term)
        per_day = []
        for dte in {s["date"] for s in samples}:
            c = [s[k] for s in samples if s["date"] == dte and s["cont"]
                 and s[k] is not None]
            t = [s[k] for s in samples if s["date"] == dte and not s["cont"]
                 and s[k] is not None]
            ad = auc(c, t)
            if ad is not None:
                per_day.append(ad)
        per_day.sort()
        med = lambda v: v[len(v) // 2] if v else None
        summary[k] = dict(
            auc=round(a, 3) if a is not None else None,
            auc_day_median=(round(med(per_day), 3) if per_day else None),
            n_cont=len(cont), n_term=len(term),
            cont_median=round(med(sorted(cont)), 3) if cont else None,
            term_median=round(med(sorted(term)), 3) if term else None)
    # delta divergence is a flag, not a scalar
    dd_cont = [s for s in samples if s["cont"]]
    dd_term = [s for s in samples if not s["cont"]]
    summary["delta_div_rate"] = dict(
        cont=round(sum(1 for s in dd_cont if s["delta_div"]) / len(dd_cont), 3),
        term=round(sum(1 for s in dd_term if s["delta_div"]) / len(dd_term), 3),
        n_cont=len(dd_cont), n_term=len(dd_term))

    ev_summary = {}
    res = [e for e in day_events if e["resumed"]]
    fail = [e for e in day_events if not e["resumed"]]
    for k in metrics:
        rv = [e[k] for e in res if e[k] is not None]
        fv = [e[k] for e in fail if e[k] is not None]
        a = auc(rv, fv)
        med = lambda v: sorted(v)[len(v) // 2] if v else None
        ev_summary[k] = dict(auc=round(a, 3) if a is not None else None,
                             resumed_median=round(med(rv), 3) if rv else None,
                             failed_median=round(med(fv), 3) if fv else None,
                             n_resumed=len(rv), n_failed=len(fv))

    # convergence score: how many of the three interpretable traces confirm
    combo_keys = ("tick_aligned", "vix_slope5", "add_slope10")
    combo = {}
    for s in samples:
        vals = [s[k] for k in combo_keys]
        if any(v is None for v in vals):
            continue
        score = sum(1 for v in vals if v > 0)
        c = combo.setdefault(score, [0, 0])
        c[0] += 1
        c[1] += s["cont"]
    combo_table = {
        str(score): dict(n=n, cont=k, p_cont=round(k / n, 3))
        for score, (n, k) in sorted(combo.items())}
    sc = [sum(1 for k in combo_keys if s[k] > 0) for s in samples
          if s["cont"] and all(s[k] is not None for k in combo_keys)]
    st_ = [sum(1 for k in combo_keys if s[k] > 0) for s in samples
           if not s["cont"] and all(s[k] is not None for k in combo_keys)]
    combo_auc = auc(sc, st_)

    out = dict(samples=len(samples), summary=summary,
               event_summary=ev_summary, events=len(day_events),
               combo=dict(keys=list(combo_keys), table=combo_table,
                          auc=round(combo_auc, 3) if combo_auc else None),
               day_rows=day_rows, minute_samples=samples)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"labeled minutes: {len(samples)} "
          f"(cont {sum(1 for s in samples if s['cont'])}, "
          f"term {sum(1 for s in samples if not s['cont'])}); "
          f"backtest events matched: {len(day_events)}", file=sys.stderr)
    for k, v in summary.items():
        print(f"  {k:16s} {json.dumps(v)}", file=sys.stderr)
    print("-- backtest-event cut --", file=sys.stderr)
    for k, v in ev_summary.items():
        print(f"  {k:16s} {json.dumps(v)}", file=sys.stderr)
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
