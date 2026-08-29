"""Final-hour base rates — 14:00 CT state -> 15:00 CT outcome, ES trade tape only. [st-g0jo]

WHY
    Stage 0 of the Final-Hour Acuity program (docs/plans/2026-08-28-final-hour-acuity.md).
    Before any lens is scored, know what the final hour actually pays: how far
    the close lands from the 14:00 CT print, how big the excursion is, how
    often the close stays inside the 13:00-14:00 box.

WHAT
    One row per corpus day from data/corpus/<day>/databento_glbx_es.jsonl(.gz).
    RTH prints 08:30-15:00 CT (DST-aware via America/Chicago). Delta uses the
    Databento side field: B = buy aggressor, A = sell aggressor.

    COVERAGE CAVEAT (measured 2026-08-28): 247 of 288 days hold only the
    13:00-15:00 CT window (the 2025 backfill pulled the late-day window);
    only the live-collection days from 2026-07-03 onward hold the full
    session. Fields that look back before 13:00 (pos_in_range, cumdelta_to14,
    poc/val/vah, vol_dry_ratio, p1200) are meaningful ONLY on full-session
    days. The final-hour outcome fields are valid on every day.

RUN
    .venv/bin/python3 scripts/measurement/final_hour_base.py [out.jsonl]
    Summary: see docs/measurement/final-hour-base-rates-2026-08-28.md
"""
import json, gzip, glob, os, sys, collections
from datetime import datetime, time
from zoneinfo import ZoneInfo
from multiprocessing import Pool
CT = ZoneInfo("America/Chicago")
OUT = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-hour-base.jsonl"

def opener(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)

def run_day(path):
    day = os.path.basename(os.path.dirname(path))
    try:
        y, m, d = map(int, day.split("-"))
    except Exception:
        return None
    # UTC offset for that day
    off = datetime(y, m, d, 12, tzinfo=CT).utcoffset().total_seconds() / 3600
    def utc_hm(h, mi):  # CT clock -> "HH:MM" utc string
        return f"{int(h - off):02d}:{mi:02d}"
    t0830, t1200, t1300, t1330, t1400, t1430, t1500 = [utc_hm(*x) for x in ((8,30),(12,0),(13,0),(13,30),(14,0),(14,30),(15,0))]
    trades = []  # (hm, price, size, side)
    with opener(path) as f:
        for line in f:
            i = line.find('"ts_event": "')
            if i < 0: continue
            hm = line[i+24:i+29]  # HH:MM of ts_event (utc)
            if hm < t0830 or hm >= t1500: continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            dd = r["data"]; ts = r["provenance"]["ts_event"]
            trades.append((ts[11:19], dd["price"], dd["size"], dd["side"]))
    if len(trades) < 1000:
        return {"day": day, "skip": "thin", "n": len(trades)}
    trades.sort()
    def seg(a, b):
        return [t for t in trades if a <= t[0][:5] < b]
    def stats(ts):
        if not ts: return None
        v = sum(t[2] for t in ts); dl = sum(t[2] if t[3]=="B" else (-t[2] if t[3]=="A" else 0) for t in ts)
        return {"o": ts[0][1], "h": max(t[1] for t in ts), "l": min(t[1] for t in ts), "c": ts[-1][1], "v": v, "d": dl}
    pre = seg(t0830, t1400); box = seg(t1300, t1400); last30pre = seg(t1330, t1400)
    mid = seg(utc_hm(10,30), utc_hm(11,30))
    fin = seg(t1400, t1500); fin2 = seg(t1430, t1500)
    if not pre or not fin or not box:
        return {"day": day, "skip": "gap", "n": len(trades)}
    S = stats
    p = S(pre); b = S(box); l30 = S(last30pre); m = S(mid); f = S(fin); f2 = S(fin2)
    p1400 = pre[-1][1]
    # profile to 14:00
    prof = collections.Counter()
    for t in pre: prof[t[1]] += t[2]
    tot = sum(prof.values()); poc = max(prof, key=prof.get)
    acc = 0; va = []
    for pr, v in sorted(prof.items(), key=lambda x: -x[1]):
        acc += v; va.append(pr)
        if acc >= 0.7 * tot: break
    val, vah = min(va), max(va)
    # excursions in final hour
    up = max(t[1] for t in fin) - p1400; dn = p1400 - min(t[1] for t in fin)
    close = fin[-1][1]
    p1430 = fin2[0][1] if fin2 else None
    day_rng = p["h"] - p["l"]
    row = {
        "day": day, "n": len(trades), "off": off,
        "open": p["o"], "hi_to14": p["h"], "lo_to14": p["l"], "p1200": seg(t1200, t1300)[0][1] if seg(t1200,t1300) else None,
        "p1400": p1400, "pos_in_range": round((p1400 - p["l"]) / day_rng, 3) if day_rng else None,
        "cumdelta_to14": p["d"], "vol_to14": p["v"],
        "box_h": b["h"], "box_l": b["l"], "box_rng": round(b["h"] - b["l"], 2), "box_delta": b["d"], "box_vol": b["v"], "box_chg": round(b["c"] - b["o"], 2),
        "l30_delta": l30["d"] if l30 else None, "l30_chg": round(l30["c"] - l30["o"], 2) if l30 else None,
        "vol_dry_ratio": round(b["v"] / m["v"], 3) if m and m["v"] else None,
        "poc": poc, "val": val, "vah": vah, "vs_value": ("below" if p1400 < val else "above" if p1400 > vah else "inside"),
        "close": close, "close_chg": round(close - p1400, 2), "fin_up": round(up, 2), "fin_dn": round(dn, 2),
        "fin_delta": f["d"], "fin_vol": f["v"],
        "p1430": p1430, "close_chg_1430": round(close - p1430, 2) if p1430 else None,
        "l30_up": round(max(t[1] for t in fin2) - p1430, 2) if fin2 else None, "l30_dn": round(p1430 - min(t[1] for t in fin2), 2) if fin2 else None,
        "close_in_box": bool(b["l"] <= close <= b["h"]),
    }
    return row

if __name__ == "__main__":
    paths = sorted(glob.glob("data/corpus/20*/databento_glbx_es.jsonl") + glob.glob("data/corpus/20*/databento_glbx_es.jsonl.gz"))
    with Pool(6) as pool, open(OUT, "w") as out:
        for row in pool.imap_unordered(run_day, paths):
            if row: out.write(json.dumps(row) + "\n"); out.flush()
    print("done", len(paths))
