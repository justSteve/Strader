"""Final-fifteen items 3 & 4 — what a ~$0.20 0DTE single actually paid, from prints. [st-ro04]

WHY
    Steve's working assumption (2026-08-30): a 10-point move in the last fifteen
    minutes takes a ~$0.20 single to ~$10.00 — a 5-lot for $100 becoming ~$5,000.
    Desk's model says the multiplier arithmetic is right at $100 per point but
    the pricing leg is off about an order of magnitude, because near expiry an
    option is worth about its intrinsic value: $10.00 needs ~10 points IN the
    money, so the required move is about (distance to the strike) + (the target
    premium), nearer twenty points than ten.

    Desk stated plainly that this is a model and not a measurement, and that if
    the tape disagrees the tape wins. This script is the tape.

WHAT
    Per corpus day holding an OPRA SPXW trades file (plain or gzipped — the
    compactor gzips older days and the plain glob alone hid seven of them):

      * SPX at 14:45 CT inferred from 0DTE put-call parity on prints in
        14:42-14:48 (SPX ~= K + C - P; carry ignored over fifteen minutes).
      * Per side, the strike whose LAST PRINT in 14:40-14:45 sits nearest
        $0.20 becomes the leg. Its distance from spot is recorded, because
        that distance is the whole of Desk's arithmetic.
      * That symbol's prints are walked to 15:00. Recorded: entry, close,
        PEAK and the minute it printed (item 4 — the take-profit design
        number, and the reason a close-only measurement understates the
        trade), trough, print count, and the largest silence between prints.

    THE CLOSING-SECONDS ARTIFACT. Every leg is scored TWICE: once over the full
    window to 15:00, and once over a clean window ending 14:59:00 (the *_1459
    fields). The closing seconds carry prints that are not single-leg marks —
    measured on 2026-08-05, the 7725 put printed $84.70 in the last six seconds
    while it was about three points in the money and ES had fallen 16.75 on the
    window. Eighty-seven prints above $10 on that symbol all landed inside the
    final six seconds against a median print of $0.30. Twelve of 548 legs peak
    in the last thirty seconds, but EIGHT of the twenty-nine legs that reached
    10x do — the artifact concentrates in exactly the tail this study reports,
    so the clean window is the one to quote and the full window is kept beside
    it so the difference is visible rather than hidden. One minute of fifteen is
    a cheap price, and nobody takes profit in the last five seconds anyway.

    A MARK IS A LAST PRINT, NOT A MID. Every OPRA record in this corpus is
    schema: trades — the estate has never held OPRA NBBO. So:
      * "the strike whose mark was nearest $0.20" is necessarily "whose last
        print was nearest $0.20", a different object, and
      * the SPREAD LEG CANNOT BE MEASURED AT ALL. Entries at the ask and exits
        at the bid are not computable from this data at any sample size. It is
        reported as an explicit hole with its reason, never estimated and never
        silently omitted, so no later reader mistakes a print-to-print result
        for an achievable fill. On a lottery-shaped trade that tax is large and
        it moves the strike-distance arithmetic. Desk ruled this path (a) on
        2026-08-30.
      * A day whose nearest-$0.20 strike never printed near 14:45 is a
        REPORTABLE ROW, not a skipped one — how often a $0.20 strike is simply
        untradeable at 14:45 is part of the answer to the question.

RUN
    .venv/bin/python3 scripts/measurement/final_fifteen_premium.py [out.jsonl]
"""
import json, gzip, glob, os, sys, statistics as st
from datetime import datetime
from zoneinfo import ZoneInfo
from multiprocessing import Pool

CT = ZoneInfo("America/Chicago")
OUT = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-fifteen-premium.jsonl"
TARGET_PREMIUM = 0.20


def _open(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def parse_sym(sym):
    # "SPXW  250807C06345000"
    s = sym.split()
    if len(s) != 2 or s[0] != "SPXW":
        return None
    body = s[1]
    return body[:6], body[6], int(body[7:]) / 1000.0


def run_day(path):
    day = os.path.basename(os.path.dirname(path))
    try:
        y, m, d = map(int, day.split("-"))
    except Exception:
        return None
    off = datetime(y, m, d, 12, tzinfo=CT).utcoffset().total_seconds() / 3600
    exp = f"{y % 100:02d}{m:02d}{d:02d}"
    tag = f"SPXW  {exp}"

    def hm(hh, mm):
        tot = (hh - int(off)) * 60 + mm
        return f"{tot // 60:02d}:{tot % 60:02d}"

    t1440, t1442, t1445, t1448, t1500 = hm(14, 40), hm(14, 42), hm(14, 45), hm(14, 48), hm(15, 0)
    t1459 = hm(14, 59)   # end of the clean window — see THE CLOSING-SECONDS ARTIFACT

    pre = {}      # sym -> last (hms, price) in 14:40-14:45  — the "mark at 14:45"
    parity = {}   # strike -> {"C": [...], "P": [...]} in 14:42-14:48
    walk = {}     # sym -> [(hms, price)] in 14:45-15:00
    with _open(path) as f:
        for line in f:
            if tag not in line:
                continue
            i = line.find('"ts_event": "')
            if i < 0:
                continue
            clock = line[i + 24:i + 29]
            if clock < t1440 or clock >= t1500:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            sym = r["data"]["symbol"]
            ps = parse_sym(sym)
            if not ps or ps[0] != exp:
                continue
            hms = r["provenance"]["ts_event"][11:19]
            price = r["data"]["price"]
            if clock < t1445:
                pre[sym] = (hms, price, ps[1], ps[2])
            else:
                walk.setdefault(sym, []).append((hms, price))
            if t1442 <= clock < t1448:
                parity.setdefault(ps[2], {"C": [], "P": []})[ps[1]].append(price)

    diffs = [(k, st.median(cp["C"]) - st.median(cp["P"]))
             for k, cp in parity.items() if cp["C"] and cp["P"]]
    if len(diffs) < 3:
        return {"day": day, "skip": "no-parity", "n_syms": len(pre)}
    diffs.sort(key=lambda x: abs(x[1]))
    spx = st.median([k + dlt for k, dlt in diffs[:5]])

    h0, m0 = int(t1445[:2]), int(t1445[3:5])

    def mins(hhmmss):
        return (int(hhmmss[:2]) - h0) * 60 + (int(hhmmss[3:5]) - m0) + int(hhmmss[6:8]) / 60.0

    out = {"day": day, "spx1445": round(spx, 2), "n_syms_pre": len(pre)}

    for cp, label in (("C", "call"), ("P", "put")):
        # every strike of this side that printed in 14:40-14:45, OTM only —
        # a $0.20 ITM option does not exist, and a stale deep-ITM print at
        # $0.20 would be a data artifact, not a tradeable mark.
        cands = [(sym, v) for sym, v in pre.items() if v[2] == cp
                 and ((v[3] > spx) if cp == "C" else (v[3] < spx))]
        if not cands:
            out[label] = {"skip": "no-otm-print-1440-1445"}
            continue
        sym, (t_mark, mark, _, k) = min(cands, key=lambda x: abs(x[1][1] - TARGET_PREMIUM))
        leg = {"k": k, "sym_dist": round(abs(k - spx), 2), "mark_1445": mark,
               "t_mark": t_mark, "mark_err": round(abs(mark - TARGET_PREMIUM), 2)}
        p = sorted(walk.get(sym, []))
        clean = [x for x in p if x[0][:5] < t1459]
        if not p:
            leg["skip"] = "no-print-after-1445"
            leg["n_prints"] = 0
            out[label] = leg
            continue
        entry = p[0][1]
        peak = max(x[1] for x in p)
        trough = min(x[1] for x in p)
        t_peak = next(t for t, v in p if v == peak)
        leg.update({
            "n_prints": len(p), "entry": entry, "t_entry": p[0][0],
            "entry_lag_min": round(mins(p[0][0]), 2),
            "close": p[-1][1], "peak": peak, "t_peak": t_peak,
            "peak_min": round(mins(t_peak), 2), "trough": trough,
            "mult_close": round(p[-1][1] / entry, 2) if entry else None,
            "mult_peak": round(peak / entry, 2) if entry else None,
            "gap_max_s": max(
                (int(b[0][:2]) * 3600 + int(b[0][3:5]) * 60 + int(b[0][6:8]))
                - (int(a[0][:2]) * 3600 + int(a[0][3:5]) * 60 + int(a[0][6:8]))
                for a, b in zip(p, p[1:])) if len(p) > 1 else None,
        })
        if clean:
            pk = max(x[1] for x in clean)
            leg.update({
                "n_prints_1459": len(clean),
                "close_1459": clean[-1][1],
                "peak_1459": pk,
                "peak_min_1459": round(mins(next(t for t, v in clean if v == pk)), 2),
                "mult_close_1459": round(clean[-1][1] / entry, 2) if entry else None,
                "mult_peak_1459": round(pk / entry, 2) if entry else None,
            })
        else:
            leg["n_prints_1459"] = 0
        out[label] = leg
    return out


if __name__ == "__main__":
    paths = sorted(glob.glob("data/corpus/20*/databento_opra.jsonl")
                   + glob.glob("data/corpus/20*/databento_opra.jsonl.gz"))
    n = 0
    with Pool(6) as pool, open(OUT, "w") as out:
        for row in pool.imap_unordered(run_day, paths):
            if row:
                out.write(json.dumps(row) + "\n")
                out.flush()
                n += 1
    print(f"done {n} rows from {len(paths)} OPRA day-files -> {OUT}")
