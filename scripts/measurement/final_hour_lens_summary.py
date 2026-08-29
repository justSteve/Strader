"""Score the Stage 2 lens calls: hit rates per lens and T, time split, confluence, premium. [st-g0jo]

RUN
    .venv/bin/python3 scripts/measurement/final_hour_lens_summary.py [lens.jsonl] [premium.jsonl]
    Prints markdown. Stage 3 of docs/plans/2026-08-28-final-hour-acuity.md.

Scoring vocabulary (fixed with the rules in final_hour_lens.py):
    directional call (up|down): HIT  = realized the same side (net 5+ that way)
                                MISS = realized the other side (net 5+ against)
                                FLAT = |net| < 5
    pin call:                   HIT  = |net| < 5      (also reported: close inside the 13:00->T box)
    edge = hit - miss on directional calls; the base rate for a coin-flip
    directional call is the split between up and down days at that T.
"""
import json, sys, statistics as st, collections

LENS = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-hour-lens-2026-08-29.jsonl"
PREM = sys.argv[2] if len(sys.argv) > 2 else "data/measurement/final-hour-premium-2026-08-29.jsonl"
rows = [json.loads(l) for l in open(LENS)]
rows = [r for r in rows if "skip" not in r]
prem = {}
try:
    for l in open(PREM):
        r = json.loads(l); prem[r["day"]] = r
except FileNotFoundError:
    pass

def pct(a, b): return f"{100*a/b:.0f}%" if b else "—"
def med(xs): return f"{st.median(xs):+.2f}" if xs else "—"

def score(rs, lens):
    """rs: rows with lens present and a call. Returns dict of counts/medians."""
    out = collections.OrderedDict()
    for call in ("down", "up", "pin"):
        sub = [r for r in rs if r[lens]["call"] == call]
        n = len(sub)
        if call == "pin":
            hit = sum(1 for r in sub if r["out"]["realized"] == "pin")
            inbox = sum(1 for r in sub if r["fp"] and r["fp"]["box_l"] <= r["out"]["close"] <= r["fp"]["box_h"])
            out[call] = {"n": n, "hit": hit, "inbox": inbox, "net_abs": [abs(r["out"]["net"]) for r in sub]}
        else:
            sgn = 1 if call == "up" else -1
            hit = sum(1 for r in sub if r["out"]["realized"] == call)
            miss = sum(1 for r in sub if r["out"]["realized"] == ("down" if call == "up" else "up"))
            heat = [r["out"]["heat_up" if call == "up" else "heat_down"] for r in sub if r["out"]["realized"] == call]
            heat = [h for h in heat if h is not None]
            out[call] = {"n": n, "hit": hit, "miss": miss, "flat": n - hit - miss,
                         "net_for": [r["out"]["net"] * sgn for r in sub], "heat": heat}
    return out

def base(rs):
    c = collections.Counter(r["out"]["realized"] for r in rs)
    n = len(rs)
    return c, n

def table(rs, lens, label):
    rs = [r for r in rs if r[lens] and r[lens]["call"]]
    if not rs: print(f"\n_{label}: no rows_"); return
    c, n = base(rs)
    s = score(rs, lens)
    print(f"\n**{label}** — {n} days · realized up {pct(c['up'],n)} / down {pct(c['down'],n)} / pin {pct(c['pin'],n)}")
    print("| call | n | hit | miss | flat | edge (hit−miss) | median net, call's way | heat before +5 on hits (median) |")
    print("|---|---|---|---|---|---|---|---|")
    for call in ("down", "up"):
        d = s[call]
        if not d["n"]: print(f"| {call} | 0 | — | — | — | — | — | — |"); continue
        print(f"| {call} | {d['n']} | {pct(d['hit'],d['n'])} | {pct(d['miss'],d['n'])} | {pct(d['flat'],d['n'])} | "
              f"{100*(d['hit']-d['miss'])/d['n']:+.0f} pts | {med(d['net_for'])} | {med(d['heat']) if d['heat'] else '—'} |")
    d = s["pin"]
    if d["n"]:
        print(f"| pin | {d['n']} | {pct(d['hit'],d['n'])} (|net|<5) | — | — | close in box {pct(d['inbox'],d['n'])} | median |net| {st.median(d['net_abs']):.2f} | — |")
    # pooled directional
    dn, up = s["down"], s["up"]
    N = dn["n"] + up["n"]
    if N:
        H, M = dn["hit"] + up["hit"], dn["miss"] + up["miss"]
        print(f"\n_directional pooled: n={N}, hit {pct(H,N)}, miss {pct(M,N)}, edge {100*(H-M)/N:+.0f} pts, "
              f"median net the call's way {med(dn['net_for']+up['net_for'])}_")

def premium_line(rs, lens, label):
    """14:00 only: the ITM single on the called side, Stage 1 marks."""
    rs = [r for r in rs if r["T"] == "1400" and r[lens] and r[lens]["call"] in ("up", "down") and r["day"] in prem]
    if not rs: return
    rets, wins, cuts = [], 0, 0
    for r in rs:
        leg = prem[r["day"]].get("call_itm10" if r[lens]["call"] == "up" else "put_itm10")
        if not leg or leg.get("ret_close") is None: continue
        rets.append(leg["ret_close"]); wins += leg["ret_close"] > 0; cuts += bool(leg.get("cut10", {}).get("hit"))
    if rets:
        print(f"- **{label}**, ITM single on the called side, {len(rets)} days with OPRA: median at close "
              f"{100*st.median(rets):+.0f}%, mean {100*st.mean(rets):+.0f}%, finished >0 on {pct(wins,len(rets))}, "
              f"a −10% cut fired on {pct(cuts,len(rets))}")

def agree(rs, a, b):
    return [r for r in rs if r[a] and r[b] and r[a]["call"] and r[a]["call"] == r[b]["call"]]

print("# Stage 2/3 — lens calls scored\n")
print(f"rows {len(rows)} · days {len(set(r['day'] for r in rows))} · premium days joined {len(prem)}")
for T in ("1400", "1430", "1445"):
    rs = [r for r in rows if r["T"] == T]
    print(f"\n## T = {T[:2]}:{T[2:]} CT\n")
    c, n = base(rs)
    print(f"Base: {n} days · up {pct(c['up'],n)} / down {pct(c['down'],n)} / pin {pct(c['pin'],n)} · "
          f"first 5-pt print went up {pct(sum(1 for r in rs if r['out']['first5']=='up'),n)}, down {pct(sum(1 for r in rs if r['out']['first5']=='down'),n)}")
    for lens, label in (("fp", "Footprint"), ("mc", "Mancini"), ("gx", "GEX")):
        table(rs, lens, label)
    # confluence
    print("\n**Confluence**")
    for a, b, lab in (("fp", "mc", "footprint = Mancini"), ("fp", "gx", "footprint = GEX"), ("mc", "gx", "Mancini = GEX")):
        ag = agree(rs, a, b)
        if not ag: print(f"- {lab}: no rows"); continue
        for call in ("down", "up", "pin"):
            sub = [r for r in ag if r[a]["call"] == call]
            if not sub: continue
            hit = sum(1 for r in sub if r["out"]["realized"] == call)
            miss = sum(1 for r in sub if call != "pin" and r["out"]["realized"] == ("down" if call == "up" else "up"))
            print(f"- {lab} → {call}: n={len(sub)}, hit {pct(hit,len(sub))}" + (f", miss {pct(miss,len(sub))}" if call != "pin" else ""))
    all3 = [r for r in rs if r["fp"] and r["mc"] and r["gx"] and r["gx"]["call"] and r["fp"]["call"] == r["mc"]["call"] == r["gx"]["call"]]
    print(f"- all three agree: n={len(all3)} " + (f"({', '.join(r['day']+':'+r['fp']['call']+'→'+r['out']['realized'] for r in all3)})" if all3 else ""))
    # disagreement: fp directional vs mc directional opposite
    opp = [r for r in rs if r["fp"] and r["mc"] and r["fp"]["call"] != "pin" and r["mc"]["call"] != "pin" and r["fp"]["call"] != r["mc"]["call"]]
    if opp:
        fpw = sum(1 for r in opp if r["out"]["realized"] == r["fp"]["call"]); mcw = sum(1 for r in opp if r["out"]["realized"] == r["mc"]["call"])
        print(f"- footprint and Mancini call opposite directions: n={len(opp)}, footprint right {pct(fpw,len(opp))}, Mancini right {pct(mcw,len(opp))}, neither {pct(len(opp)-fpw-mcw,len(opp))}")

print("\n## Time split — 14:00 directional calls, 2025 vs 2026\n")
for lens, label in (("fp", "Footprint"), ("mc", "Mancini")):
    for half, pred in (("2025", lambda d: d < "2026"), ("2026", lambda d: d >= "2026")):
        rs = [r for r in rows if r["T"] == "1400" and pred(r["day"]) and r[lens] and r[lens]["call"] in ("up", "down")]
        if not rs: continue
        hit = sum(1 for r in rs if r["out"]["realized"] == r[lens]["call"])
        miss = sum(1 for r in rs if r["out"]["realized"] == ("down" if r[lens]["call"] == "up" else "up"))
        pins = [r for r in rows if r["T"] == "1400" and pred(r["day"]) and r[lens] and r[lens]["call"] == "pin"]
        ph = sum(1 for r in pins if r["out"]["realized"] == "pin")
        print(f"- {label} {half}: directional n={len(rs)}, hit {pct(hit,len(rs))}, miss {pct(miss,len(rs))}, edge {100*(hit-miss)/len(rs):+.0f}; "
              f"pin n={len(pins)}, |net|<5 on {pct(ph,len(pins))}")

print("\n## In premium — 14:00 directional calls through the Stage 1 ITM single\n")
for lens, label in (("fp", "Footprint"), ("mc", "Mancini"), ("gx", "GEX")):
    premium_line(rows, lens, label)
ag = agree([r for r in rows if r["T"] == "1400"], "fp", "mc")
class _W:  # premium line over the agreeing rows, reusing fp's call
    pass
rs = [r for r in ag if r["fp"]["call"] in ("up", "down") and r["day"] in prem]
if rs:
    rets = []
    for r in rs:
        leg = prem[r["day"]].get("call_itm10" if r["fp"]["call"] == "up" else "put_itm10")
        if leg and leg.get("ret_close") is not None: rets.append(leg["ret_close"])
    if rets:
        print(f"- **footprint = Mancini**, {len(rets)} days: median {100*st.median(rets):+.0f}%, mean {100*st.mean(rets):+.0f}%, >0 on {pct(sum(x>0 for x in rets),len(rets))}")

print("\n## Feature cross-tabs recorded for later (14:00, not in any rule)\n")
rs = [r for r in rows if r["T"] == "1400" and r["fp"]]
for feat, fn in (("absorption", lambda r: r["fp"]["absorb"]),
                 ("energy (last-30 vol vs box avg)", lambda r: "dried <0.8" if r["fp"]["energy"] and r["fp"]["energy"] < 0.8 else "hot >1.2" if r["fp"]["energy"] and r["fp"]["energy"] > 1.2 else "even"),
                 ("box position", lambda r: "bottom" if r["fp"]["pos"] <= 0.25 else "top" if r["fp"]["pos"] >= 0.75 else "middle")):
    c = collections.defaultdict(collections.Counter)
    for r in rs: c[fn(r)][r["out"]["realized"]] += 1
    print(f"- {feat}: " + "; ".join(f"{k} n={sum(v.values())} up {pct(v['up'],sum(v.values()))}/down {pct(v['down'],sum(v.values()))}/pin {pct(v['pin'],sum(v.values()))}" for k, v in sorted(c.items())))
full = [r for r in rs if r["full"]]
if full:
    c = collections.defaultdict(collections.Counter)
    for r in full: c[r["fp"]["full_vs_value"]][r["out"]["realized"]] += 1
    print(f"- vs value area (full-session days, n={len(full)}): " + "; ".join(f"{k} n={sum(v.values())} up {pct(v['up'],sum(v.values()))}/down {pct(v['down'],sum(v.values()))}/pin {pct(v['pin'],sum(v.values()))}" for k, v in sorted(c.items())))
    c = collections.defaultdict(collections.Counter)
    for r in full:
        k = "dry <0.5" if r["fp"]["full_vol_dry"] and r["fp"]["full_vol_dry"] < 0.5 else "not dry"
        c[k][r["out"]["realized"]] += 1
    print(f"- volume drying vs late morning (full-session days): " + "; ".join(f"{k} n={sum(v.values())} up {pct(v['up'],sum(v.values()))}/down {pct(v['down'],sum(v.values()))}/pin {pct(v['pin'],sum(v.values()))}" for k, v in sorted(c.items())))
mc = [r for r in rows if r["T"] == "1400" and r["mc"]]
c = collections.defaultdict(collections.Counter)
for r in mc:
    ms = r["mc"]["major_sup"]; k = "major support ≤10 below, held" if ms and -10 <= ms["rel"] <= 0 and ms["state"] in ("held", "reclaimed") else "no held major within 10 below"
    c[k][r["out"]["realized"]] += 1
print(f"- Mancini major support: " + "; ".join(f"{k} n={sum(v.values())} up {pct(v['up'],sum(v.values()))}/down {pct(v['down'],sum(v.values()))}/pin {pct(v['pin'],sum(v.values()))}" for k, v in sorted(c.items())))
