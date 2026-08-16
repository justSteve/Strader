"""SPX→ES basis from synchronous pairs on a corpus day (Watcher V2 plan, Risk 4).

For every ``gexbot_orderflow_1s`` row in RTH — filtered on the vendor
``timestamp`` (epoch s), never ``ts_pull_utc`` — take the last ES print at or
before that second and compute ``es − spot``. Reports the median, the p95 of
the absolute deviation from the median, the per-hour drift, and the Schwab
snapshot basis for the same day so the two sources can be compared.

The number that matters for the Live Basis estimate is the p95 deviation: if
it is under ~1.5 ES points the 1 Hz ``spot`` is a usable live basis source and
SPX rows can be drawn on the ES chart at ``strike + basis`` without a band.

Usage:
    .venv/bin/python scripts/measurement/basis_pairs.py 2026-08-14 [more days]
"""
from __future__ import annotations

import bisect
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "data" / "corpus"


def _parse_ts_event(te: str) -> float:
    # "2026-08-14T07:50:07.711753281+00:00" — nanoseconds; trim to microseconds
    head, _, tail = te.partition(".")
    frac = tail[:6]
    tz = tail[9:] if len(tail) > 9 else "+00:00"
    return datetime.fromisoformat(f"{head}.{frac}{tz}").timestamp()


def load_prints(day: str) -> tuple[list[float], list[float]]:
    ts: list[float] = []
    px: list[float] = []
    with open(CORPUS / day / "databento_glbx_es.jsonl") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = r.get("data") or {}
            if d.get("action") != "T":
                continue
            te = (r.get("provenance") or {}).get("ts_event")
            if not te:
                continue
            ts.append(_parse_ts_event(te))
            px.append(float(d["price"]))
    return ts, px


def measure(day: str) -> dict:
    ts, px = load_prints(day)

    def es_at(t: float) -> float | None:
        i = bisect.bisect_right(ts, t) - 1
        return px[i] if i >= 0 else None

    rth0 = datetime.fromisoformat(f"{day}T13:30:00+00:00").timestamp()
    rth1 = datetime.fromisoformat(f"{day}T20:00:00+00:00").timestamp()

    pairs: list[tuple[float, float]] = []
    with open(CORPUS / day / "gexbot_orderflow_1s.jsonl") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            t, s = r.get("timestamp"), r.get("spot")
            if not isinstance(t, (int, float)) or not isinstance(s, (int, float)) or s <= 0:
                continue
            if not (rth0 <= t <= rth1):
                continue
            e = es_at(t)
            if e is not None:
                pairs.append((t, e - s))

    out: dict = {"day": day, "prints": len(ts), "pairs": len(pairs)}
    if not pairs:
        return out
    b = [p[1] for p in pairs]
    med = statistics.median(b)
    dev = sorted(abs(x - med) for x in b)
    out.update(median=round(med, 2), p95_dev=round(dev[int(0.95 * (len(dev) - 1))], 2),
               lo=round(min(b), 2), hi=round(max(b), 2))
    hourly: dict[str, list[float]] = defaultdict(list)
    for t, bb in pairs:
        hourly[datetime.fromtimestamp(t, timezone.utc).strftime("%H")].append(bb)
    out["hourly"] = {
        h: {"n": len(v), "median": round(statistics.median(v), 2),
            "p95_dev": round(sorted(abs(x - statistics.median(v)) for x in v)
                             [int(0.95 * (len(v) - 1))], 2)}
        for h, v in sorted(hourly.items())}

    sw = []
    sp = CORPUS / day / "schwab.jsonl"
    if sp.exists():
        with open(sp) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = r.get("ts_pull_utc")
                d = r.get("data") or {}
                if not t or not d.get("spot_es") or not d.get("spot_spx"):
                    continue
                tt = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
                if rth0 <= tt <= rth1:
                    sw.append({"ts": t, "schwab_basis": round(d["spot_es"] - d["spot_spx"], 2),
                               "spx": d["spot_spx"], "es": d["spot_es"], "es_print": es_at(tt)})
    out["schwab"] = sw
    return out


def main(argv: list[str]) -> int:
    days = argv[1:] or ["2026-08-14"]
    for day in days:
        r = measure(day)
        print(f"{r['day']}: {r['prints']} prints, {r['pairs']} RTH pairs")
        if "median" not in r:
            print("  no pairs")
            continue
        print(f"  basis median {r['median']:+.2f}  p95|dev| {r['p95_dev']:.2f}  "
              f"range {r['lo']:+.2f}..{r['hi']:+.2f}")
        for h, v in r["hourly"].items():
            print(f"    {h}Z n={v['n']:5d} median {v['median']:+.2f} p95|dev| {v['p95_dev']:.2f}")
        for s in r["schwab"]:
            print(f"    schwab {s['ts']} basis {s['schwab_basis']:+.2f} "
                  f"(spx {s['spx']} es {s['es']} | ES print that second {s['es_print']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
