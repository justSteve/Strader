"""Final-hour combination calls — the lenses read together, abstaining unless they agree. [st-g0jo]

WHY
    Stage 2 had each lens call pin/down/up on every day and none carried a
    14:00 direction (docs/measurement/final-hour-lens-calls-2026-08-29.md).
    The 08-28 hand read was not one lens; it was a footprint state read
    against a Mancini level, and it made its call only because they agreed.
    This scores that: rules that fire only when the parts line up, and say
    nothing otherwise. Coverage (how often a rule speaks) is reported beside
    its hit rate, because a rule that speaks on 8 days is a story, not an edge.

THE PRE-REGISTERED RULES (written 2026-08-29 before the first run; not tuned)

  Inputs are the Stage 2 row fields at T (data before T only):
    fp.pos        where p_T sits in the 13:00->T box (0 = low, 1 = high)
    fp.l30_chg    price change over the last 30 minutes
    fp.l30_delta  aggressor delta over the last 30 minutes
    fp.energy     last-30 volume per minute / box volume per minute
    fp.absorb     "buy" = box delta > 0 with no price progress; "sell" mirror
    mc.floor      a Mancini support within 10 below p_T that held/reclaimed
    mc.lid        a Mancini resistance within 10 above p_T that held/reclaimed
    mc.lost       a Mancini support within 10 ABOVE p_T that broke, not reclaimed
    mc.taken      a Mancini resistance within 10 BELOW p_T that broke, not reclaimed

  Rules, checked in this order; the first that fires is the call; else no call.
    R1  flush   : pos <= 0.25 and l30_chg < 0 and l30_delta < 0 and not floor       -> down
                  (pressing the bottom of the box on selling, nothing of Mancini's held under it)
    R2  launch  : pos >= 0.75 and l30_chg > 0 and l30_delta > 0 and not lid          -> up
    R3  pinned  : floor and lid and energy <= 1.0                                    -> pin
                  (a Mancini level held on both sides, tape quieter than its box)
    R4  bought  : pos <= 0.25 and floor and floor within 5 below p_T                 -> up
                  (sitting on a defended support at the bottom of the box — the failed-breakdown shape)
    R5  sold    : pos >= 0.75 and lid and lid within 5 above p_T                     -> down
    R6  lost    : lost and not floor and l30_chg < 0                                 -> down
                  (under a support that broke this window, nothing held below, still falling)
    R7  taken   : taken and not lid and l30_chg > 0                                  -> up

  Two ablations, scored beside them so the Mancini leg is shown to matter or not:
    A1  R1 without the Mancini clause (pos, chg, delta only)                         -> down
    A2  R2 without the Mancini clause                                                -> up

  Scoring is Stage 3's: realized = close 5+ from p_T (up/down) else pin; hit /
  miss / flat; edge = hit - miss; 2025 vs 2026 halves; the 14:00 calls through
  the Stage 1 ITM single. Rows lacking the Mancini leg (25 days) are skipped
  for R3-R7 and for the Mancini clauses of R1/R2 (treated as "not present").

RUN
    .venv/bin/python3 scripts/measurement/final_hour_combo.py [lens.jsonl] [premium.jsonl]
"""
import json, sys, statistics as st, collections

LENS = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-hour-lens-2026-08-29.jsonl"
PREM_FILES = {  # per-T entry pricing from final_hour_premium.py <base> <out> [HH:MM]
    "1400": sys.argv[2] if len(sys.argv) > 2 else "data/measurement/final-hour-premium-2026-08-29.jsonl",
    "1430": "data/measurement/final-hour-premium-1430-2026-08-29.jsonl",
    "1445": "data/measurement/final-hour-premium-1445-2026-08-29.jsonl",
}
rows = [json.loads(l) for l in open(LENS)]
rows = [r for r in rows if "skip" not in r and r.get("fp")]
PREM = {}
for T, path in PREM_FILES.items():
    PREM[T] = {}
    try:
        for l in open(path):
            r = json.loads(l); PREM[T][r["day"]] = r
    except FileNotFoundError:
        pass

def parts(r):
    fp, mc = r["fp"], r.get("mc") or {}
    pT = r["pT"]
    floor = mc.get("floor"); lid = mc.get("lid")
    return dict(
        pos=fp["pos"], chg=fp["l30_chg"], dl=fp["l30_delta"], energy=fp.get("energy") or 1.0, absorb=fp["absorb"],
        floor=floor, lid=lid, lost=mc.get("lost"), taken=mc.get("taken"), has_mc=bool(mc),
        floor5=bool(floor) and (pT - floor) <= 5, lid5=bool(lid) and (lid - pT) <= 5,
    )

RULES = [
    ("R1 flush",  "down", lambda p: p["pos"] <= 0.25 and p["chg"] < 0 and p["dl"] < 0 and not p["floor"]),
    ("R2 launch", "up",   lambda p: p["pos"] >= 0.75 and p["chg"] > 0 and p["dl"] > 0 and not p["lid"]),
    ("R3 pinned", "pin",  lambda p: p["has_mc"] and p["floor"] and p["lid"] and p["energy"] <= 1.0),
    ("R4 bought", "up",   lambda p: p["pos"] <= 0.25 and p["floor5"]),
    ("R5 sold",   "down", lambda p: p["pos"] >= 0.75 and p["lid5"]),
    ("R6 lost",   "down", lambda p: p["lost"] and not p["floor"] and p["chg"] < 0),
    ("R7 taken",  "up",   lambda p: p["taken"] and not p["lid"] and p["chg"] > 0),
]
ABLATIONS = [
    ("A1 flush, no Mancini",  "down", lambda p: p["pos"] <= 0.25 and p["chg"] < 0 and p["dl"] < 0),
    ("A2 launch, no Mancini", "up",   lambda p: p["pos"] >= 0.75 and p["chg"] > 0 and p["dl"] > 0),
]

def first_call(p):
    for name, call, fn in RULES:
        if fn(p): return name, call
    return None, None

def pct(a, b): return f"{100*a/b:.0f}%" if b else "—"
def medf(xs): return f"{st.median(xs):+.2f}" if xs else "—"

def score(sub, call):
    n = len(sub)
    if call == "pin":
        hit = sum(1 for r in sub if r["out"]["realized"] == "pin")
        return n, hit, None, [abs(r["out"]["net"]) for r in sub], []
    opp = "down" if call == "up" else "up"; sgn = 1 if call == "up" else -1
    hit = sum(1 for r in sub if r["out"]["realized"] == call)
    miss = sum(1 for r in sub if r["out"]["realized"] == opp)
    heat = [r["out"]["heat_up" if call == "up" else "heat_down"] for r in sub if r["out"]["realized"] == call]
    return n, hit, miss, [r["out"]["net"] * sgn for r in sub], [h for h in heat if h is not None]

def line(name, call, sub, total):
    n, hit, miss, net, heat = score(sub, call)
    if not n: return f"| {name} | {call} | 0 | — | — | — | — | — | — |"
    if call == "pin":
        return f"| {name} | pin | {n} ({pct(n,total)}) | {pct(hit,n)} | — | — | median \\|net\\| {st.median(net):.2f} | — | — |"
    halves = []
    for tag, pred in (("25", lambda d: d < "2026"), ("26", lambda d: d >= "2026")):
        s2 = [r for r in sub if pred(r["day"])]
        if s2:
            n2, h2, m2, _, _ = score(s2, call); halves.append(f"{tag}: {100*(h2-m2)/n2:+.0f} (n{n2})")
    return (f"| {name} | {call} | {n} ({pct(n,total)}) | {pct(hit,n)} | {pct(miss,n)} | {100*(hit-miss)/n:+.0f} | "
            f"{medf(net)} | {medf(heat) if heat else '—'} | {' · '.join(halves)} |")

print("# Final-hour combination calls — scored\n")
print(f"rows {len(rows)} · days {len(set(r['day'] for r in rows))} · premium days joined " + ", ".join(f"{T} {len(v)}" for T, v in PREM.items()) + "\n")
for T in ("1400", "1430", "1445"):
    rs = [r for r in rows if r["T"] == T]
    c = collections.Counter(r["out"]["realized"] for r in rs); n = len(rs)
    print(f"## T = {T[:2]}:{T[2:]} CT — {n} days · base up {pct(c['up'],n)} / down {pct(c['down'],n)} / pin {pct(c['pin'],n)}\n")
    print("| rule | call | fires (coverage) | hit | miss | edge | median net, call's way | heat before +5 on hits | edge by half |")
    print("|---|---|---|---|---|---|---|---|---|")
    fired = collections.defaultdict(list)
    for r in rs:
        name, call = first_call(parts(r))
        if name: fired[name].append(r)
    for name, call, _ in RULES:
        print(line(name, call, fired[name], n))
    for name, call, fn in ABLATIONS:
        sub = [r for r in rs if fn(parts(r))]
        print(line(name, call, sub, n))
    # the combined caller
    called = [(r, first_call(parts(r))[1]) for r in rs]
    dirs = [(r, cl) for r, cl in called if cl in ("up", "down")]
    if dirs:
        hit = sum(1 for r, cl in dirs if r["out"]["realized"] == cl)
        miss = sum(1 for r, cl in dirs if r["out"]["realized"] == ("down" if cl == "up" else "up"))
        print(f"\n_combined caller, directional: speaks on {len(dirs)} of {n} days ({pct(len(dirs),n)}), hit {pct(hit,len(dirs))}, miss {pct(miss,len(dirs))}, edge {100*(hit-miss)/len(dirs):+.0f}; silent on {pct(n-len([1 for _,cl in called if cl]),n)}_")
    prem = PREM.get(T) or {}
    if prem:
        print(f"\nPremium — the ITM single bought at {T[:2]}:{T[2:]} on the called side (Stage 1 marks, entry re-priced at T):")
        rets = collections.defaultdict(list)
        for r, cl in dirs:
            if r["day"] not in prem: continue
            leg = prem[r["day"]].get("call_itm10" if cl == "up" else "put_itm10")
            if leg and leg.get("ret_close") is not None:
                rets[first_call(parts(r))[0]].append(leg); rets["all"].append(leg)
        for k in [x[0] for x in RULES if x[1] != "pin"] + ["all"]:
            xs = rets.get(k)
            if not xs or len(xs) < 3: continue
            rc = [x["ret_close"] for x in xs]
            print(f"- {k}: {len(xs)} OPRA days, entry median {st.median(x['entry'] for x in xs):.2f}, at close median {100*st.median(rc):+.0f}% / mean {100*st.mean(rc):+.0f}%, "
                  f">0 on {pct(sum(x>0 for x in rc),len(rc))}, printed +25% on {pct(sum(x['tgt25']['hit'] for x in xs),len(xs))}, "
                  f"−10% cut fired on {pct(sum(x['cut10']['hit'] for x in xs),len(xs))}")
    print()
