"""Final-hour premium scoreboard — a 14:00 CT 0DTE single each side, marked from OPRA prints. [st-g0jo]

WHY
    Stage 1 of the Final-Hour Acuity program. ES points say how far the close
    travelled; only the option's own prints say what a long single actually
    paid or cost over that hour. Steve 2026-08-29: process both and see what
    correlation there is.

WHAT
    Per corpus day holding both ES tape and OPRA SPXW trades:
      * SPX at 14:00 CT is inferred from 0DTE put-call parity on prints in
        13:57-14:03 CT (SPX ~= K + C - P, carry ignored for one hour).
      * Six hypothetical singles: put and call at ~10 ITM, ATM, ~10 OTM
        (nearest 5-pt strike). Entry = first print at/after 14:00 CT.
        Steve leans ITM for the futures-proxy single (knowledge/singles-as-
        futures-proxy.md; the 08-26 paper 7685P was ~9 ITM at 10.10).
      * Mark path = that symbol's prints to 15:00 CT. Scored: mark at close,
        best mark (MFE), worst mark (MAE), result under 3%/10% and 0.30/0.50-pt
        cuts (first print at/below the cut level exits there), the print-to-
        print noise floor, first time +25/+50/+100% printed, and heat before
        each target.
      * ES columns from data/measurement/final-hour-base-<date>.jsonl.
    Print-based marks: a strike that goes untraded for a stretch has a gap —
    that is the OPRA caveat, and it is why ES columns ride alongside.

RUN
    .venv/bin/python3 scripts/measurement/final_hour_premium.py <base.jsonl> <out.jsonl> [HH:MM]
    The optional third argument is the entry time, CT (default 14:00). Stage 3's
    combination calls fire at 14:30 and 14:45 too, and a call at 14:45 has to be
    priced from a 14:45 entry, not the 14:00 one. Rows carry "entry_ct"; the
    SPX-at-entry field keeps its Stage 1 name "spx1400" so the summary reads both.
"""
import json, glob, os, sys, statistics as st
from datetime import datetime
from zoneinfo import ZoneInfo
from multiprocessing import Pool
CT = ZoneInfo("America/Chicago")
BASE, OUT = sys.argv[1], sys.argv[2]
ENTRY = sys.argv[3] if len(sys.argv) > 3 else "14:00"
EH, EM = int(ENTRY[:2]), int(ENTRY[3:5])
OFFSETS = (-10, 0, 10)   # OTM distance in SPX pts; negative = ITM (Steve leans ITM: 08-26 paper 7685P was ~9 ITM)
CUTS = (0.03, 0.10)
ABS_CUTS = (0.30, 0.50)  # Steve's 08-26 yardstick: 0.30 on a 10.10 single
TARGETS = (0.25, 0.50, 1.00)

def parse_sym(sym):
    # "SPXW  250807C06345000"
    s = sym.split()
    if len(s) != 2 or s[0] != "SPXW": return None
    body = s[1]
    return body[:6], body[6], int(body[7:]) / 1000.0

def run_day(path):
    day = os.path.basename(os.path.dirname(path))
    y, m, d = map(int, day.split("-"))
    off = datetime(y, m, d, 12, tzinfo=CT).utcoffset().total_seconds() / 3600
    h15 = int(15 - off)
    exp = f"{y%100:02d}{m:02d}{d:02d}"
    tag = f"SPXW  {exp}"
    def hm(hh, mm):  # CT clock -> utc "HH:MM"
        tot = (hh - int(off)) * 60 + mm
        return f"{tot // 60:02d}:{tot % 60:02d}"
    t1357 = hm(EH, EM - 3); t1403 = hm(EH, EM + 3); t1400 = hm(EH, EM); t1500 = f"{h15:02d}:00"
    prints = {}  # sym -> [(hms, price)]
    parity = {}  # strike -> {"C": [...], "P": [...]}
    with open(path) as f:
        for line in f:
            if tag not in line: continue
            i = line.find('"ts_event": "')
            hm = line[i+24:i+29]
            if hm < t1357 or hm >= t1500: continue
            r = json.loads(line); sym = r["data"]["symbol"]; ps = parse_sym(sym)
            if not ps or ps[0] != exp: continue
            hms = r["provenance"]["ts_event"][11:19]; price = r["data"]["price"]
            if hm < t1403:
                parity.setdefault(ps[2], {"C": [], "P": []})[ps[1]].append(price)
            if hm >= t1400:
                prints.setdefault(sym, []).append((hms, price))
    # infer SPX from parity
    diffs = []
    for k, cp in parity.items():
        if cp["C"] and cp["P"]:
            diffs.append((k, st.median(cp["C"]) - st.median(cp["P"])))
    if len(diffs) < 3:
        return {"day": day, "skip": "no-parity", "n_syms": len(prints)}
    # strikes whose C-P is small in magnitude (near the money) give the cleanest estimate
    diffs.sort(key=lambda x: abs(x[1]))
    spx = st.median([k + dlt for k, dlt in diffs[:5]])
    out = {"day": day, "entry_ct": ENTRY, "spx1400": round(spx, 2)}
    legs = []
    for otm in OFFSETS:
        legs.append((f"put_{'itm' if otm<0 else 'atm' if otm==0 else 'otm'}{abs(otm)}", "P", int(round((spx - otm) / 5.0)) * 5))
        legs.append((f"call_{'itm' if otm<0 else 'atm' if otm==0 else 'otm'}{abs(otm)}", "C", int(round((spx + otm) / 5.0)) * 5))
    for side, cp, k in legs:
        sym = f"SPXW  {exp}{cp}{int(k*1000):08d}"
        path_ = sorted(prints.get(sym, []))
        if len(path_) < 5:
            out[side] = {"skip": "thin", "n": len(path_), "k": k}; continue
        entry = path_[0][1]; t_entry = path_[0][0]
        closem = path_[-1][1]
        mfe = max(p for _, p in path_); mae = min(p for _, p in path_)
        t_mfe = next(t for t, p in path_ if p == mfe)
        res = {"k": k, "entry": entry, "t_entry": t_entry, "n_prints": len(path_), "close": closem,
               "ret_close": round(closem / entry - 1, 3), "mfe": mfe, "t_mfe": t_mfe,
               "ret_mfe": round(mfe / entry - 1, 3), "mae": mae, "ret_mae": round(mae / entry - 1, 3)}
        for cut in CUTS:
            lvl = entry * (1 - cut); ex = None
            for t, p in path_[1:]:
                if p <= lvl: ex = (t, p); break
            res[f"cut{int(cut*100)}"] = {"hit": ex is not None, "t": ex[0] if ex else None,
                                        "ret": round((ex[1] if ex else closem) / entry - 1, 3)}
        for ac in ABS_CUTS:
            lvl = entry - ac; ex = None
            for t, p in path_[1:]:
                if p <= lvl: ex = (t, p); break
            res[f"cut_{int(ac*100)}c"] = {"hit": ex is not None, "t": ex[0] if ex else None,
                                          "ret": round((ex[1] if ex else closem) / entry - 1, 3)}
        steps = [abs(b[1] - a[1]) for a, b in zip(path_, path_[1:])]
        res["noise_pts"] = round(st.median(steps), 2) if steps else None   # median print-to-print change, pts
        for tg in TARGETS:
            lvl = entry * (1 + tg); hit = None; heat = 0.0
            for t, p in path_[1:]:
                heat = min(heat, p / entry - 1)
                if p >= lvl: hit = t; break
            res[f"tgt{int(tg*100)}"] = {"hit": hit is not None, "t": hit, "heat_before": round(heat, 3) if hit else None}
        # gaps: longest silence between prints in seconds
        def sec(t): h, mi, s = t.split(":"); return int(h)*3600 + int(mi)*60 + int(s)
        gaps = [sec(b[0]) - sec(a[0]) for a, b in zip(path_, path_[1:])]
        res["max_gap_s"] = max(gaps) if gaps else None
        out[side] = res
    return out

if __name__ == "__main__":
    base = {json.loads(l)["day"]: json.loads(l) for l in open(BASE)}
    paths = sorted(p for p in glob.glob("data/corpus/20*/databento_opra.jsonl")
                   if os.path.basename(os.path.dirname(p)) in base and "skip" not in base[os.path.basename(os.path.dirname(p))])
    n = 0
    with Pool(6) as pool, open(OUT, "w") as out:
        for row in pool.imap_unordered(run_day, paths):
            b = base[row["day"]]
            row["es"] = {k: b[k] for k in ("p1400", "close", "close_chg", "fin_up", "fin_dn", "p1430", "close_chg_1430", "box_rng", "close_in_box")}
            out.write(json.dumps(row) + "\n"); out.flush(); n += 1
    print("done", n, "of", len(paths))
