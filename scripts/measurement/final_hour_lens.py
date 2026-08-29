"""Final-hour lens states at 14:00 / 14:30 / 14:45 CT, no lookahead, each lens calling pin / down / up. [st-g0jo]

WHY
    Stage 2 of Final-Hour Acuity (docs/plans/2026-08-28-final-hour-acuity.md).
    Stage 0 measured what the last hour pays; Stage 1 measured it in premium.
    This stage rebuilds, for every corpus day, what each of the three lenses
    used in the 08-28 close read would have shown at T in {14:00, 14:30, 14:45}
    CT using only prints stamped before T, and has each lens emit its own call
    by a rule fixed HERE, before any scoring ran. Stage 3 scores the calls.

THE PRE-REGISTERED RULES (written 2026-08-29 before the first run; do not tune)

  footprint (ES tape, every day) — box = 13:00->T, last30 = T-30m->T,
    pos = (p_T - box_low) / box_range.
      1. pos <= 0.20 and last30 chg < 0 and last30 delta < 0   -> down
      2. pos >= 0.80 and last30 chg > 0 and last30 delta > 0   -> up
      3. otherwise                                              -> pin
    (absorption, energy, node location, profile fields are RECORDED as
    features for Stage 3 cross-tabs; they are not in the rule.)

  mancini (parsed letter levels, ES points) — level state replayed on the
    tape over 13:00->T: touched = a print within 1.0; broke = a print 2.0+
    through on the far side; reclaimed = broke, then a print 1.0+ back on
    the near side; held = touched and not broke. Only supports below p_T and
    resistances above p_T count as floor / lid; a broken level is judged
    from where p_T sits relative to it.
      floor = nearest support within 10 pts below p_T, state held|reclaimed
      lid   = nearest resistance within 10 pts above p_T, state held|reclaimed
      lost  = a support within 10 pts ABOVE p_T that broke and was not reclaimed
      taken = a resistance within 10 pts BELOW p_T that broke and was not reclaimed
      1. lost and not floor   -> down
      2. taken and not lid    -> up
      3. floor and lid        -> pin
      4. floor only           -> up
      5. lid only             -> down
      6. otherwise            -> pin
    (levels with no touch in the window carry state "untested"; a major flag
    is recorded; the letter's bias text is recorded where the parse has it.)

  gex (GexBot classic gex_zero majors, SPX points; ~23 days) — latest row
    at or before T, no older than 10 minutes. zero = zero_gamma,
    mpos = largest positive-gamma strike by volume, mneg = largest negative.
      1. zero missing (0)                          -> no call
      2. spot >= zero and |spot - mpos| <= 10       -> pin
      3. spot <  zero and mneg <  spot              -> down
      4. spot <  zero and mneg >= spot              -> up
      5. spot >= zero and mpos >  spot + 10         -> up
      6. spot >= zero and mpos <  spot - 10         -> down
      7. otherwise                                  -> pin

  outcome at T (the scoreboard, from the same tape): net = close - p_T;
    realized = up if net >= 5, down if net <= -5, else pin. Heat is the
    adverse excursion from p_T before the first print 5+ in favour, on each
    side, so Stage 3 can score the shake as well as the direction.

WHAT
    One JSON row per (day, T). Fields are grouped: fp, mc, gx, out. Days are
    every data/corpus/<day>/databento_glbx_es.jsonl(.gz) with 1000+ RTH
    prints. Mancini levels come from runbook/mancini/parsed/<day>.json (the
    letter written for that session). GEX from data/corpus/<day>/gexbot.jsonl.

    COVERAGE CAVEAT (Stage 0): 247 of 288 tape days hold only 13:00-15:00 CT;
    fields prefixed full_ are meaningful only on the ~40 full-session days.

RUN
    .venv/bin/python3 scripts/measurement/final_hour_lens.py [out.jsonl]
    Summary: scripts/measurement/final_hour_lens_summary.py
"""
import json, gzip, glob, os, sys, collections
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from multiprocessing import Pool

CT = ZoneInfo("America/Chicago")
OUT = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-hour-lens.jsonl"
TS = ((14, 0), (14, 30), (14, 45))
TOUCH, BREAK, RECLAIM, NEAR = 1.0, 2.0, 1.0, 10.0
TGT = 5.0

def opener(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)

def load_json_maybe_gz(path):
    with open(path, "rb") as f:
        magic = f.read(2)
    return json.load(gzip.open(path, "rt") if magic == b"\x1f\x8b" else open(path))

# ---------------------------------------------------------------- tape
def load_tape(path, off):
    """RTH prints as (hhmmss_utc, price, size, side); off = CT utc offset (hours)."""
    def utc_hm(h, mi): return f"{int(h - off):02d}:{mi:02d}"
    t0830, t1500 = utc_hm(8, 30), utc_hm(15, 0)
    trades = []
    with opener(path) as f:
        for line in f:
            i = line.find('"ts_event": "')
            if i < 0: continue
            hm = line[i + 24:i + 29]
            if hm < t0830 or hm >= t1500: continue
            try: r = json.loads(line)
            except Exception: continue
            dd = r["data"]; ts = r["provenance"]["ts_event"]
            trades.append((ts[11:19], dd["price"], dd["size"], dd["side"]))
    trades.sort()
    return trades

def stats(ts):
    if not ts: return None
    v = sum(t[2] for t in ts)
    dl = sum(t[2] if t[3] == "B" else (-t[2] if t[3] == "A" else 0) for t in ts)
    return {"o": ts[0][1], "h": max(t[1] for t in ts), "l": min(t[1] for t in ts), "c": ts[-1][1], "v": v, "d": dl}

# ---------------------------------------------------------------- footprint
def footprint(trades, seg, pT, T_min, full):
    box = seg(13 * 60, T_min); l30 = seg(T_min - 30, T_min); l15 = seg(T_min - 15, T_min)
    if not box or not l30: return None
    b, l, s15 = stats(box), stats(l30), stats(l15)
    rng = b["h"] - b["l"]
    pos = (pT - b["l"]) / rng if rng else 0.5
    # node location: price with the heaviest sell (A) and buy (B) volume in the last 15
    sell = collections.Counter(); buy = collections.Counter()
    for t in l15:
        (sell if t[3] == "A" else buy if t[3] == "B" else collections.Counter())[t[1]] += t[2]
    sell_node = max(sell, key=sell.get) if sell else None
    buy_node = max(buy, key=buy.get) if buy else None
    box_min = T_min - 13 * 60
    energy = (l["v"] / 30) / (b["v"] / box_min) if b["v"] and box_min else None
    absorb = ("buy" if b["d"] > 0 and b["c"] - b["o"] <= 0 else
              "sell" if b["d"] < 0 and b["c"] - b["o"] >= 0 else "none")
    l30_chg = round(l["c"] - l["o"], 2)
    if pos <= 0.20 and l30_chg < 0 and l["d"] < 0: call = "down"
    elif pos >= 0.80 and l30_chg > 0 and l["d"] > 0: call = "up"
    else: call = "pin"
    row = {
        "box_h": b["h"], "box_l": b["l"], "box_rng": round(rng, 2), "box_delta": b["d"], "box_vol": b["v"],
        "box_chg": round(b["c"] - b["o"], 2), "pos": round(pos, 3), "absorb": absorb,
        "l30_chg": l30_chg, "l30_delta": l["d"], "l30_vol": l["v"], "energy": round(energy, 3) if energy else None,
        "l15_delta": s15["d"] if s15 else None,
        "sell_node": sell_node, "sell_node_rel": (round(sell_node - pT, 2) if sell_node is not None else None),
        "buy_node": buy_node, "buy_node_rel": (round(buy_node - pT, 2) if buy_node is not None else None),
        "call": call,
    }
    if full:
        pre = seg(8 * 60 + 30, T_min); mid = seg(10 * 60 + 30, 11 * 60 + 30)
        p = stats(pre); m = stats(mid)
        prof = collections.Counter()
        for t in pre: prof[t[1]] += t[2]
        tot = sum(prof.values()); poc = max(prof, key=prof.get)
        acc = 0; va = []
        for pr, v in sorted(prof.items(), key=lambda x: -x[1]):
            acc += v; va.append(pr)
            if acc >= 0.7 * tot: break
        day_rng = p["h"] - p["l"]
        row.update({
            "full_pos_in_range": round((pT - p["l"]) / day_rng, 3) if day_rng else None,
            "full_cumdelta": p["d"], "full_poc": poc, "full_val": min(va), "full_vah": max(va),
            "full_vs_value": "below" if pT < min(va) else "above" if pT > max(va) else "inside",
            "full_vol_dry": round(b["v"] / m["v"], 3) if m and m["v"] else None,
        })
    return row

# ---------------------------------------------------------------- mancini
def level_state(level, kind, window):
    """Replay one level over the window's prints -> untested|held|broke|reclaimed, plus counts."""
    touched = broke = reclaimed = False; n_touch = 0; was_near = False
    for _, px, _, _ in window:
        near = abs(px - level) <= TOUCH
        if near and not was_near: n_touch += 1
        was_near = near
        if near: touched = True
        through = (px <= level - BREAK) if kind == "support" else (px >= level + BREAK)
        back = (px >= level + RECLAIM) if kind == "support" else (px <= level - RECLAIM)
        if through and not broke: broke, reclaimed = True, False
        elif broke and back: reclaimed = True
    state = "reclaimed" if reclaimed else "broke" if broke else "held" if touched else "untested"
    return state, n_touch

def mancini(levels, window, pT, bias):
    if not levels: return None
    rows = []
    for lv in levels:
        kind = lv.get("kind")
        if kind not in ("support", "resistance"): continue
        px = float(lv["price"])
        if abs(px - pT) > 25: continue
        st, n = level_state(px, kind, window)
        major = "major" in (lv.get("source_quote", "") + " " + lv.get("label", "")).lower()
        rows.append({"price": px, "kind": kind, "major": major, "state": st, "touches": n, "rel": round(px - pT, 2),
                     "intent": lv.get("intent", "unstated"), "setup": lv.get("setup", "none")})
    sup_below = sorted([r for r in rows if r["kind"] == "support" and r["price"] <= pT], key=lambda r: -r["price"])
    res_above = sorted([r for r in rows if r["kind"] == "resistance" and r["price"] >= pT], key=lambda r: r["price"])
    sup_above = [r for r in rows if r["kind"] == "support" and r["price"] > pT and r["price"] - pT <= NEAR]
    res_below = [r for r in rows if r["kind"] == "resistance" and r["price"] < pT and pT - r["price"] <= NEAR]
    floor = next((r for r in sup_below if pT - r["price"] <= NEAR and r["state"] in ("held", "reclaimed")), None)
    lid = next((r for r in res_above if r["price"] - pT <= NEAR and r["state"] in ("held", "reclaimed")), None)
    lost = next((r for r in sorted(sup_above, key=lambda r: r["price"]) if r["state"] == "broke"), None)
    taken = next((r for r in sorted(res_below, key=lambda r: -r["price"]) if r["state"] == "broke"), None)
    if lost and not floor: call = "down"
    elif taken and not lid: call = "up"
    elif floor and lid: call = "pin"
    elif floor: call = "up"
    elif lid: call = "down"
    else: call = "pin"
    nm_s = next((r for r in sup_below if r["major"]), None); nm_r = next((r for r in res_above if r["major"]), None)
    return {
        "n_levels": len(rows), "bias": (bias or "")[:80] or None,
        "sup1": sup_below[0] if sup_below else None, "res1": res_above[0] if res_above else None,
        "major_sup": nm_s, "major_res": nm_r,
        "floor": floor and floor["price"], "lid": lid and lid["price"],
        "lost": lost and lost["price"], "taken": taken and taken["price"],
        "n_held": sum(r["state"] == "held" for r in rows), "n_broke": sum(r["state"] == "broke" for r in rows),
        "n_reclaimed": sum(r["state"] == "reclaimed" for r in rows),
        "call": call,
    }

# ---------------------------------------------------------------- gex
def load_gex(day):
    """[(epoch, spot, zero, mpos, mneg)] from the corpus pull, sorted."""
    path = f"data/corpus/{day}/gexbot.jsonl"
    out = []
    if not os.path.exists(path): return out
    with open(path) as f:
        for line in f:
            try: r = json.loads(line)
            except Exception: continue
            m = (r.get("data") or {}).get("responses", {}).get("/SPX/classic/gex_zero/majors")
            if not m or not m.get("spot"): continue
            out.append((m["timestamp"], m["spot"], m.get("zero_gamma") or 0, m.get("mpos_vol") or 0, m.get("mneg_vol") or 0))
    out.sort()
    return out

def gex(rows, t_epoch, t13_epoch):
    if not rows: return None
    cur = [r for r in rows if r[0] <= t_epoch]
    if not cur or t_epoch - cur[-1][0] > 600: return None
    ts, spot, zero, mpos, mneg = cur[-1]
    base = next((r for r in rows if r[0] >= t13_epoch), None)
    if not zero: call = None
    elif spot >= zero and abs(spot - mpos) <= 10: call = "pin"
    elif spot < zero and mneg < spot: call = "down"
    elif spot < zero: call = "up"
    elif mpos > spot + 10: call = "up"
    elif mpos < spot - 10: call = "down"
    else: call = "pin"
    return {
        "age_s": int(t_epoch - ts), "spot": spot, "zero": zero, "mpos": mpos, "mneg": mneg,
        "spot_vs_zero": round(spot - zero, 2) if zero else None,
        "mpos_rel": round(mpos - spot, 2) if mpos else None, "mneg_rel": round(mneg - spot, 2) if mneg else None,
        "mpos_drift_13": round(mpos - base[3], 2) if base and base[3] and mpos else None,
        "zero_drift_13": round(zero - base[2], 2) if base and base[2] and zero else None,
        "call": call,
    }

# ---------------------------------------------------------------- outcome
def outcome(fin, pT):
    if not fin: return None
    close = fin[-1][1]; net = close - pT
    up = max(t[1] for t in fin) - pT; dn = pT - min(t[1] for t in fin)
    def heat(sign):
        worst = 0.0; hit_t = None
        for ts, px, _, _ in fin:
            fav = (px - pT) * sign
            if fav >= TGT: hit_t = ts; break
            worst = max(worst, -fav)
        return (round(worst, 2) if hit_t else None), hit_t
    hu, tu = heat(+1); hd, td = heat(-1)
    first = "up" if tu and (not td or tu < td) else "down" if td else None
    return {"close": close, "net": round(net, 2), "up_exc": round(up, 2), "dn_exc": round(dn, 2),
            "realized": "up" if net >= TGT else "down" if net <= -TGT else "pin",
            "heat_up": hu, "t_up5": tu, "heat_down": hd, "t_down5": td, "first5": first,
            "fin_delta": stats(fin)["d"], "fin_vol": stats(fin)["v"]}

# ---------------------------------------------------------------- driver
def run_day(path):
    day = os.path.basename(os.path.dirname(path))
    try: y, m, d = map(int, day.split("-"))
    except Exception: return []
    off = datetime(y, m, d, 12, tzinfo=CT).utcoffset().total_seconds() / 3600
    trades = load_tape(path, off)
    if len(trades) < 1000: return [{"day": day, "skip": "thin", "n": len(trades)}]
    def hms_to_min(hms):  # utc HH:MM:SS -> CT minutes since midnight
        return (int(hms[:2]) + off) * 60 + int(hms[3:5]) + int(hms[6:8]) / 60
    mins = [hms_to_min(t[0]) for t in trades]
    def seg(a, b): return [t for t, mn in zip(trades, mins) if a <= mn < b]
    full = bool(seg(9 * 60, 10 * 60))
    parsed = f"runbook/mancini/parsed/{day}.json"
    levels = bias = None
    if os.path.exists(parsed):
        try:
            pj = json.load(open(parsed)); levels = pj.get("levels") or []; bias = pj.get("session_bias")
        except Exception: levels = None
    grows = load_gex(day)
    out = []
    for (h, mi) in TS:
        T_min = h * 60 + mi
        pre = seg(13 * 60, T_min); fin = seg(T_min, 15 * 60)
        if not pre or not fin:
            out.append({"day": day, "T": f"{h:02d}{mi:02d}", "skip": "gap"}); continue
        pT = pre[-1][1]
        t_epoch = datetime(y, m, d, h, mi, tzinfo=CT).timestamp()
        t13 = datetime(y, m, d, 13, 0, tzinfo=CT).timestamp()
        out.append({
            "day": day, "T": f"{h:02d}{mi:02d}", "full": full, "pT": pT, "n": len(trades),
            "fp": footprint(trades, seg, pT, T_min, full),
            "mc": mancini(levels, pre, pT, bias),
            "gx": gex(grows, t_epoch, t13),
            "out": outcome(fin, pT),
        })
    return out

if __name__ == "__main__":
    paths = sorted(glob.glob("data/corpus/20*/databento_glbx_es.jsonl") + glob.glob("data/corpus/20*/databento_glbx_es.jsonl.gz"))
    n = 0
    with Pool(6) as pool, open(OUT, "w") as out:
        for rows in pool.imap_unordered(run_day, paths):
            for row in rows:
                out.write(json.dumps(row) + "\n"); n += 1
            out.flush()
    print("done", len(paths), "days", n, "rows ->", OUT)
