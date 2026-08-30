"""Final-fifteen base rates — the 14:45 -> 15:00 CT move, ES trade tape only. [st-ro04]

WHY
    Desk work order 2026-08-30 (Steve's ask): what does the last fifteen
    minutes actually do, and what would a ~$0.20 singleton have paid? Item 1
    is the move distribution; this script is that item, and the day rows it
    writes are what items 2-4 condition on.

    Steve's working assumption is that a 10-point move in the final fifteen
    takes a $0.20 single to ~$10.00. Desk's model says the pricing leg is off
    about an order of magnitude. Neither is a measurement. This is the ES half
    of the measurement; final_fifteen_premium.py is the OPRA half.

WHAT
    One row per corpus day from data/corpus/<day>/databento_glbx_es.jsonl(.gz),
    plain or gzipped (the compactor gzips older days). RTH prints only,
    DST-aware via America/Chicago.

      p1445        first ES print at/after 14:45 CT — the entry reference
      close        last print before 15:00 CT
      move         close - p1445, SIGNED, ES points
      move_pct     the same move as a fraction of p1445

    Both units are carried because SPX rose materially across the corpus: a
    points-only base rate flatters the recent half, which is exactly what Desk
    asked to avoid. Every summary rate must be reported with the day count
    behind it.

    ARRIVAL. For each threshold in THRESHOLDS the row carries, per side, the
    minutes after 14:45 at which price FIRST reached p1445 +/- threshold
    (up_hit_<n> / dn_hit_<n>), or null if it never did. Desk expects a
    first-order effect here that a close-only measurement cannot see: ten
    points arriving at 14:47 leaves thirteen minutes of time value on a
    now-near-the-money option, the same ten points at 14:58 pays intrinsic and
    nothing more. `arrival_half` buckets the day's first 10-point touch, either
    side, into early (14:45-14:52) or late (14:52-15:00).

    EXCURSION. f15_up / f15_dn are the peak distances travelled from p1445 in
    each direction, with the minute each peaked (up_peak_min / dn_peak_min).
    The peak is the take-profit design number; the close is not.

RUN
    .venv/bin/python3 scripts/measurement/final_fifteen_base.py [out.jsonl]
    Default out: data/measurement/final-fifteen-base.jsonl
"""
import json, gzip, glob, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
from multiprocessing import Pool

CT = ZoneInfo("America/Chicago")
OUT = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-fifteen-base.jsonl"
THRESHOLDS = (5, 10, 15, 20)
WINDOW_MIN = 15.0          # 14:45 -> 15:00
EARLY_CUTOFF_MIN = 7.5     # first half of the window


def opener(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def run_day(path):
    day = os.path.basename(os.path.dirname(path))
    try:
        y, m, d = map(int, day.split("-"))
    except Exception:
        return None
    off = datetime(y, m, d, 12, tzinfo=CT).utcoffset().total_seconds() / 3600

    def utc_hm(h, mi):
        return f"{int(h - off):02d}:{mi:02d}"

    t1445, t1500 = utc_hm(14, 45), utc_hm(15, 0)

    trades = []  # (hhmmss, price, size, side)
    with opener(path) as f:
        for line in f:
            i = line.find('"ts_event": "')
            if i < 0:
                continue
            hm = line[i + 24:i + 29]
            if hm < t1445 or hm >= t1500:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            dd = r["data"]
            trades.append((r["provenance"]["ts_event"][11:19], dd["price"], dd["size"], dd["side"]))

    if len(trades) < 50:
        return {"day": day, "skip": "thin", "n": len(trades)}
    trades.sort()

    # minutes after 14:45, from the UTC clock string
    h0, m0 = int(t1445[:2]), int(t1445[3:5])
    def mins(hhmmss):
        h, mi, s = int(hhmmss[:2]), int(hhmmss[3:5]), int(hhmmss[6:8])
        return (h - h0) * 60 + (mi - m0) + s / 60.0

    p1445 = trades[0][1]
    close = trades[-1][1]
    hi = max(t[1] for t in trades)
    lo = min(t[1] for t in trades)
    vol = sum(t[2] for t in trades)
    delta = sum(t[2] if t[3] == "B" else (-t[2] if t[3] == "A" else 0) for t in trades)

    row = {
        "day": day, "n": len(trades), "off": off,
        "p1445": p1445, "close": close,
        "move": round(close - p1445, 2),
        "move_pct": round((close - p1445) / p1445, 6) if p1445 else None,
        "f15_up": round(hi - p1445, 2), "f15_dn": round(p1445 - lo, 2),
        "f15_vol": vol, "f15_delta": delta,
        "span_min": round(mins(trades[-1][0]), 2),
    }

    # peak minutes — when the excursion actually happened
    up_peak = next((t for t in trades if t[1] == hi), None)
    dn_peak = next((t for t in trades if t[1] == lo), None)
    row["up_peak_min"] = round(mins(up_peak[0]), 2) if up_peak else None
    row["dn_peak_min"] = round(mins(dn_peak[0]), 2) if dn_peak else None

    # first-touch arrival per threshold, per side
    first_touch_any = None
    for n in THRESHOLDS:
        up_t = next((mins(t[0]) for t in trades if t[1] - p1445 >= n), None)
        dn_t = next((mins(t[0]) for t in trades if p1445 - t[1] >= n), None)
        row[f"up_hit_{n}"] = round(up_t, 2) if up_t is not None else None
        row[f"dn_hit_{n}"] = round(dn_t, 2) if dn_t is not None else None
        if n == 10:
            cands = [x for x in (up_t, dn_t) if x is not None]
            first_touch_any = min(cands) if cands else None

    row["first10_min"] = round(first_touch_any, 2) if first_touch_any is not None else None
    row["arrival_half"] = (None if first_touch_any is None
                           else "early" if first_touch_any < EARLY_CUTOFF_MIN else "late")
    return row


if __name__ == "__main__":
    paths = sorted(glob.glob("data/corpus/20*/databento_glbx_es.jsonl")
                   + glob.glob("data/corpus/20*/databento_glbx_es.jsonl.gz"))
    n = 0
    with Pool(6) as pool, open(OUT, "w") as out:
        for row in pool.imap_unordered(run_day, paths):
            if row:
                out.write(json.dumps(row) + "\n")
                out.flush()
                n += 1
    print(f"done {n} rows from {len(paths)} day-files -> {OUT}")
