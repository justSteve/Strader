"""Final-fifteen items 3 & 4 — the summary that settles the arithmetic. [st-ro04]

Joins final-fifteen-premium-*.jsonl (the OPRA leg walks) to
final-fifteen-base-*.jsonl (the ES move that drove them) and answers the
question Desk put: is Steve's "$0.20 to $10.00 on a ten-point move" right, is
Desk's "you need nearer twenty points" right, or is the tape a third thing?

Every rate carries its day count. Anything under ten days is labelled a story.
The spread is reported as an unmeasured hole with its reason, never estimated.

Multiples are quoted on the CLEAN WINDOW (14:45-14:59), with the full window to
15:00 shown beside them. The closing seconds carry prints that are not
single-leg marks; final_fifteen_premium.py documents the measurement. Twelve of
548 legs peak in the last thirty seconds but eight of the twenty-nine legs that
reached 10x do, so the choice of window is load-bearing for exactly the tail
this study is about.

RUN
    .venv/bin/python3 scripts/measurement/final_fifteen_premium_summary.py [prem.jsonl] [base.jsonl]
"""
import json, sys, statistics as st, collections

PREM = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-fifteen-premium-2026-08-30.jsonl"
BASE = sys.argv[2] if len(sys.argv) > 2 else "data/measurement/final-fifteen-base-2026-08-30.jsonl"

prem = [json.loads(l) for l in open(PREM) if l.strip()]
base = {}
for l in open(BASE):
    r = json.loads(l)
    if "skip" not in r:
        base[r["day"]] = r

ok = [r for r in prem if "skip" not in r]
skipped = [r for r in prem if "skip" in r]

print("# What a ~$0.20 0DTE single actually paid in the final fifteen\n")
print(f"OPRA day-files scored {len(prem)} · usable {len(ok)} · "
      f"skipped {len(skipped)} ({collections.Counter(r['skip'] for r in skipped)})")
if ok:
    print(f"span {min(r['day'] for r in ok)} -> {max(r['day'] for r in ok)}")
print()
print("Multiples below are the CLEAN WINDOW, 14:45-14:59. The full window to 15:00 is shown")
print("beside them: the closing seconds carry prints that are not single-leg marks (on")
print("2026-08-05 a put three points in the money printed $84.70 in the last six seconds).")
print()
print("**The spread is not in this measurement and cannot be.** Every OPRA record in this")
print("corpus is `schema: trades`; the estate has never held OPRA NBBO. Entries at the ask")
print("and exits at the bid are not computable from this data at any sample size. A far-OTM")
print("SPX option in the last fifteen minutes is wide — a \"$0.20\" option may be 0.15 bid /")
print("0.30 ask — so every multiple below is a print-to-print result and an UPPER BOUND on")
print("an achievable one. On a lottery-shaped trade that tax is larger than usual.")
print()


def legs(side):
    return [(r, r[side]) for r in ok if side in r and "skip" not in r[side]]


def nprint(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


# ─── availability ────────────────────────────────────────────────────────────
print("## 1. Is a $0.20 strike even there at 14:45?\n")
print("| side | days with an OTM print 14:40-14:45 | of which no print after 14:45 | usable legs |")
print("|---|---|---|---|")
for side in ("call", "put"):
    have = [r for r in ok if side in r and r[side].get("skip") != "no-otm-print-1440-1445"]
    dead = [r for r in have if r[side].get("skip") == "no-print-after-1445"]
    live = legs(side)
    print(f"| {side} | {len(have)} of {len(ok)} | {len(dead)} | {len(live)} |")
print()
for side in ("call", "put"):
    L = [leg for _, leg in legs(side)]
    if not L:
        continue
    errs = [leg["mark_err"] for leg in L]
    print(f"- **{side}**: the strike nearest $0.20 was a median "
          f"${st.median(leg['mark_1445'] for leg in L):.2f} "
          f"(|error| from $0.20: median ${st.median(errs):.2f}, p90 ${nprint(errs, .90):.2f}). "
          f"It sat a median **{st.median(leg['sym_dist'] for leg in L):.1f} points** from spot "
          f"(p25 {nprint([leg['sym_dist'] for leg in L], .25):.1f}, "
          f"p75 {nprint([leg['sym_dist'] for leg in L], .75):.1f}).")
print()
print("That distance is the whole of the arithmetic: near expiry the option is about its")
print("intrinsic value, so reaching a target premium needs the strike distance PLUS the")
print("target — not the target alone.")
print()

# ─── what it actually paid ───────────────────────────────────────────────────
print("## 2. What the leg actually reached (item 4 — peak, not close)\n")
print("| side | legs | close multiple (median / p90 / max) | PEAK multiple (median / p90 / max) | full-window peak max |")
print("|---|---|---|---|---|")
for side in ("call", "put"):
    L = [leg for _, leg in legs(side) if leg.get("mult_peak_1459") is not None]
    if not L:
        continue
    mc = [leg["mult_close_1459"] for leg in L]
    mp = [leg["mult_peak_1459"] for leg in L]
    raw = [leg["mult_peak"] for leg in L if leg.get("mult_peak") is not None]
    print(f"| {side} | {len(L)} | {st.median(mc):.2f}x / {nprint(mc, .90):.2f}x / {max(mc):.2f}x "
          f"| {st.median(mp):.2f}x / {nprint(mp, .90):.2f}x / {max(mp):.2f}x | {max(raw):.2f}x |")
print()

allL = [leg for side in ("call", "put") for _, leg in legs(side) if leg.get("mult_peak_1459") is not None]
print(f"Pooled, {len(allL)} legs. How often the peak reached each multiple of the entry:\n")
print("| multiple | legs reaching it | rate | what that is in money on a 5-lot ($100 in) |")
print("|---|---|---|---|")
for mult in (2, 3, 5, 10, 20, 50):
    n = sum(1 for leg in allL if leg["mult_peak_1459"] >= mult)
    tag = "  *(story, not a base rate)*" if 0 < n < 10 else ""
    print(f"| >= {mult}x | {n} | {100.0 * n / len(allL):.1f}% | ${100 * mult:,} out{tag} |")
print()
print("Steve's assumption is the **50x** row: $0.20 -> $10.00, $100 -> $5,000.")
print()

# ─── what move it took ───────────────────────────────────────────────────────
print("## 3. What move it actually took\n")
rows = []
for side in ("call", "put"):
    for r, leg in legs(side):
        b = base.get(r["day"])
        if not b or leg.get("mult_peak_1459") is None:
            continue
        fav = b["f15_up"] if side == "call" else b["f15_dn"]
        rows.append((side, r["day"], leg, fav, b))
print(f"{len(rows)} legs joined to their day's ES excursion.\n")
print("| favourable ES excursion in the window | legs | median peak multiple | reached 10x | reached 50x |")
print("|---|---|---|---|---|")
for lo, hi, label in ((0, 5, "under 5 pts"), (5, 10, "5-10 pts"), (10, 15, "10-15 pts"),
                      (15, 20, "15-20 pts"), (20, 999, "20+ pts")):
    sub = [x for x in rows if lo <= x[3] < hi]
    if not sub:
        print(f"| {label} | 0 | — | — | — |")
        continue
    mp = [x[2]["mult_peak_1459"] for x in sub]
    t10 = sum(1 for x in sub if x[2]["mult_peak_1459"] >= 10)
    t50 = sum(1 for x in sub if x[2]["mult_peak_1459"] >= 50)
    tag = "  *(story)*" if len(sub) < 10 else ""
    print(f"| {label} | {len(sub)} | {st.median(mp):.2f}x | {t10} ({100.0*t10/len(sub):.0f}%) "
          f"| {t50} ({100.0*t50/len(sub):.0f}%){tag} |")
print()

big = [x for x in rows if x[2]["mult_peak_1459"] >= 50]
if big:
    favs = [x[3] for x in big]
    dists = [x[2]["sym_dist"] for x in big]
    print(f"**The {len(big)} legs that did reach 50x** needed a favourable excursion of "
          f"median **{st.median(favs):.1f} points** (min {min(favs):.1f}, max {max(favs):.1f}), "
          f"from a strike a median {st.median(dists):.1f} points away.")
else:
    print("**No leg in the corpus reached 50x.**")
tens = [x for x in rows if x[2]["mult_peak_1459"] >= 10]
if tens:
    favs = [x[3] for x in tens]
    print(f"The {len(tens)} legs that reached 10x needed median **{st.median(favs):.1f} points** "
          f"(min {min(favs):.1f}).")
print()

# ─── the ten-point day, Steve's case ─────────────────────────────────────────
print("## 4. Steve's case, isolated: the days that moved ~10 points the leg's way\n")
sub = [x for x in rows if 9 <= x[3] <= 11]
if sub:
    mp = [x[2]["mult_peak_1459"] for x in sub]
    mc = [x[2]["mult_close_1459"] for x in sub]
    print(f"{len(sub)} legs whose day travelled 9-11 points in the leg's favour.")
    print(f"- peak multiple: median **{st.median(mp):.2f}x**, p90 {nprint(mp, .90):.2f}x, max {max(mp):.2f}x")
    print(f"- close multiple: median {st.median(mc):.2f}x")
    print(f"- entry premium median ${st.median(x[2]['entry'] for x in sub):.2f}, "
          f"peak premium median ${st.median(x[2]['peak_1459'] for x in sub):.2f}")
    n50 = sum(1 for m in mp if m >= 50)
    print(f"- reached 50x on **{n50} of {len(sub)}**")
else:
    print("no legs in the 9-11 point band")
print()

# ─── arrival ─────────────────────────────────────────────────────────────────
print("## 5. When the peak printed (the take-profit number)\n")
pk = [leg["peak_min_1459"] for leg in allL if leg.get("peak_min_1459") is not None]
if pk:
    late = sum(1 for x in pk if x >= 11.0)
    print(f"Median peak at **{st.median(pk):.2f} minutes** after 14:45 "
          f"(p25 {nprint(pk, .25):.2f}, p75 {nprint(pk, .75):.2f}). "
          f"In the last three minutes of the clean window on {late} of {len(pk)} legs "
          f"({100.0*late/len(pk):.0f}%).")
    winners = [leg["peak_min_1459"] for leg in allL if leg["mult_peak_1459"] >= 3]
    if winners:
        print(f"On the {len(winners)} legs that at least tripled, the peak printed at a median "
              f"**{st.median(winners):.2f} minutes** after 14:45.")
print()
gaps = [leg["gap_max_s"] for leg in allL if leg.get("gap_max_s") is not None]
if gaps:
    print(f"Liquidity caveat: the longest silence between prints on the chosen strike ran a median "
          f"{st.median(gaps):.0f}s, p90 {nprint(gaps, .90):.0f}s, max {max(gaps):.0f}s. A gap is a "
          f"stretch where this measurement cannot see the mark and a live order might not fill.")
