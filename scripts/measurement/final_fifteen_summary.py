"""Final-fifteen item 1 — the 14:45 -> 15:00 CT move distribution. [st-ro04]

Reads final-fifteen-base-*.jsonl and prints the distribution Desk asked for:
frequency at >= 5/10/15/20 points, split by direction, each threshold in BOTH
points and as a percentage of the 14:45 price, with the day count behind every
figure. Close-based AND touch-based, because a long single is paid by the touch
and not by the close.

Percentage thresholds are anchored to the corpus MEDIAN 14:45 price, so
"10 points" and "the percentage 10 points was worth at the median day" are the
same yardstick applied two ways. SPX rose materially across the corpus; a
points-only rate flatters the recent half, which is what the pct column exists
to expose.

The 2025/2026 split is reported as a column, never as a discard gate — Steve
retired the discard gate 2026-08-30, confirmed by him directly the same day.
Nothing here drops a rule for failing a half.

RUN
    .venv/bin/python3 scripts/measurement/final_fifteen_summary.py [base.jsonl]
"""
import json, sys, statistics as st

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-fifteen-base-2026-08-30.jsonl"
THRESHOLDS = (5, 10, 15, 20)

rows = [json.loads(l) for l in open(SRC) if l.strip()]
good = [r for r in rows if "skip" not in r]
skipped = [r for r in rows if "skip" in r]

print(f"FINAL-FIFTEEN MOVE DISTRIBUTION — 14:45 -> 15:00 CT, ES trade tape")
print(f"source {SRC}")
print(f"{len(rows)} day-files, {len(good)} usable, {len(skipped)} skipped "
      f"({', '.join(sorted({r['skip'] for r in skipped})) or 'none'})")
if good:
    print(f"span {min(r['day'] for r in good)} -> {max(r['day'] for r in good)}")
med_price = st.median([r["p1445"] for r in good])
print(f"median 14:45 price {med_price:.2f}  "
      f"(first-day {good[0]['p1445'] if good else 0:.0f} .. last-day "
      f"{sorted(good, key=lambda r: r['day'])[-1]['p1445']:.0f})")
print()


def halves(rs):
    return ([r for r in rs if r["day"] < "2026-01-01"],
            [r for r in rs if r["day"] >= "2026-01-01"])


def rate(rs, pred):
    n = sum(1 for r in rs if pred(r))
    return n, (100.0 * n / len(rs) if rs else 0.0)


def band(n, total):
    """A rate standing on few days is a story, not a base rate — say so."""
    return "  <- few days, a story not a base rate" if n < 10 else ""


h25, h26 = halves(good)
print(f"halves: 2025 n={len(h25)}  2026 n={len(h26)}   (reported as a column, never a discard gate)")
print()

# ─── close-based ─────────────────────────────────────────────────────────────
print("=" * 100)
print("A. WHERE THE CLOSE LANDED  (close - 14:45 price, signed)")
print("=" * 100)
print(f"{'threshold':>12} | {'up':>15} | {'down':>15} | {'either':>15} | {'2025':>9} | {'2026':>9}")
print("-" * 100)
for n in THRESHOLDS:
    pct = n / med_price
    up_n, up_r = rate(good, lambda r, n=n: r["move"] >= n)
    dn_n, dn_r = rate(good, lambda r, n=n: r["move"] <= -n)
    ei_n, ei_r = rate(good, lambda r, n=n: abs(r["move"]) >= n)
    _, r25 = rate(h25, lambda r, n=n: abs(r["move"]) >= n)
    _, r26 = rate(h26, lambda r, n=n: abs(r["move"]) >= n)
    print(f"{'>= ' + str(n) + ' pts':>12} | {up_n:4d} {up_r:6.1f}% | {dn_n:4d} {dn_r:6.1f}% | "
          f"{ei_n:4d} {ei_r:6.1f}% | {r25:7.1f}% | {r26:7.1f}%{band(ei_n, len(good))}")
    # the same threshold as a percentage of that day's own 14:45 price
    up_n, up_r = rate(good, lambda r, p=pct: r["move_pct"] >= p)
    dn_n, dn_r = rate(good, lambda r, p=pct: r["move_pct"] <= -p)
    ei_n, ei_r = rate(good, lambda r, p=pct: abs(r["move_pct"]) >= p)
    _, r25 = rate(h25, lambda r, p=pct: abs(r["move_pct"]) >= p)
    _, r26 = rate(h26, lambda r, p=pct: abs(r["move_pct"]) >= p)
    print(f"{'>= ' + format(pct * 100, '.3f') + '%':>12} | {up_n:4d} {up_r:6.1f}% | {dn_n:4d} {dn_r:6.1f}% | "
          f"{ei_n:4d} {ei_r:6.1f}% | {r25:7.1f}% | {r26:7.1f}%   (same bar, per-day pct)")
    print()

# ─── touch-based ─────────────────────────────────────────────────────────────
print("=" * 100)
print("B. WHAT THE WINDOW TOUCHED  (peak excursion from the 14:45 price)")
print("   This is the row that prices a long single. The option is paid by the touch, not the close.")
print("=" * 100)
print(f"{'threshold':>12} | {'up touch':>15} | {'down touch':>15} | {'either':>15} | {'2025':>9} | {'2026':>9}")
print("-" * 100)
for n in THRESHOLDS:
    pct = n / med_price
    up_n, up_r = rate(good, lambda r, n=n: r["f15_up"] >= n)
    dn_n, dn_r = rate(good, lambda r, n=n: r["f15_dn"] >= n)
    ei_n, ei_r = rate(good, lambda r, n=n: max(r["f15_up"], r["f15_dn"]) >= n)
    _, r25 = rate(h25, lambda r, n=n: max(r["f15_up"], r["f15_dn"]) >= n)
    _, r26 = rate(h26, lambda r, n=n: max(r["f15_up"], r["f15_dn"]) >= n)
    print(f"{'>= ' + str(n) + ' pts':>12} | {up_n:4d} {up_r:6.1f}% | {dn_n:4d} {dn_r:6.1f}% | "
          f"{ei_n:4d} {ei_r:6.1f}% | {r25:7.1f}% | {r26:7.1f}%{band(ei_n, len(good))}")
    up_n, up_r = rate(good, lambda r, p=pct: r["f15_up"] / r["p1445"] >= p)
    dn_n, dn_r = rate(good, lambda r, p=pct: r["f15_dn"] / r["p1445"] >= p)
    ei_n, ei_r = rate(good, lambda r, p=pct: max(r["f15_up"], r["f15_dn"]) / r["p1445"] >= p)
    _, r25 = rate(h25, lambda r, p=pct: max(r["f15_up"], r["f15_dn"]) / r["p1445"] >= p)
    _, r26 = rate(h26, lambda r, p=pct: max(r["f15_up"], r["f15_dn"]) / r["p1445"] >= p)
    print(f"{'>= ' + format(pct * 100, '.3f') + '%':>12} | {up_n:4d} {up_r:6.1f}% | {dn_n:4d} {dn_r:6.1f}% | "
          f"{ei_n:4d} {ei_r:6.1f}% | {r25:7.1f}% | {r26:7.1f}%   (same bar, per-day pct)")
    print()

# ─── shape ───────────────────────────────────────────────────────────────────
mv = sorted(r["move"] for r in good)
am = sorted(abs(r["move"]) for r in good)
up = sorted(r["f15_up"] for r in good)
dn = sorted(r["f15_dn"] for r in good)
rng = sorted(r["f15_up"] + r["f15_dn"] for r in good)


def pct_of(xs, q):
    return xs[min(len(xs) - 1, int(q * len(xs)))]


print("=" * 100)
print(f"C. SHAPE  (n={len(good)} days)")
print("=" * 100)
for name, xs in (("signed move", mv), ("|move|", am), ("up excursion", up),
                 ("down excursion", dn), ("window range", rng)):
    print(f"  {name:16s} p10 {pct_of(xs,.10):7.2f}  p25 {pct_of(xs,.25):7.2f}  "
          f"median {pct_of(xs,.50):7.2f}  p75 {pct_of(xs,.75):7.2f}  "
          f"p90 {pct_of(xs,.90):7.2f}  max {xs[-1]:7.2f}")
print()
up_days = sum(1 for r in good if r["move"] > 0)
dn_days = sum(1 for r in good if r["move"] < 0)
flat = len(good) - up_days - dn_days
print(f"  direction of the close: up {up_days} ({100*up_days/len(good):.1f}%)  "
      f"down {dn_days} ({100*dn_days/len(good):.1f}%)  unchanged {flat}")
print()

# ─── arrival ─────────────────────────────────────────────────────────────────
print("=" * 100)
print("D. ARRIVAL — when the move showed up inside the fifteen minutes")
print("   Desk expects a first-order effect here: 10 pts at 14:47 leaves 13 minutes of")
print("   time value on a now-near-the-money option; the same 10 pts at 14:58 pays intrinsic.")
print("=" * 100)
for n in THRESHOLDS:
    hits = [r for r in good if r.get(f"up_hit_{n}") is not None or r.get(f"dn_hit_{n}") is not None]
    if not hits:
        print(f"  >= {n:2d} pts touched: 0 days")
        continue
    firsts = []
    for r in hits:
        c = [r[k] for k in (f"up_hit_{n}", f"dn_hit_{n}") if r.get(k) is not None]
        firsts.append(min(c))
    early = sum(1 for f in firsts if f < 7.5)
    print(f"  >= {n:2d} pts touched on {len(hits):3d} days ({100*len(hits)/len(good):5.1f}%)  "
          f"| first touch: median {st.median(firsts):5.2f} min after 14:45, "
          f"p25 {sorted(firsts)[len(firsts)//4]:5.2f}, p75 {sorted(firsts)[3*len(firsts)//4]:5.2f}  "
          f"| early half {early} ({100*early/len(hits):.0f}%), late half {len(hits)-early}"
          f"{band(len(hits), len(good))}")
print()
print("  Peak-excursion timing — where in the window the extreme actually printed:")
for label, key in (("up peak", "up_peak_min"), ("down peak", "dn_peak_min")):
    xs = sorted(r[key] for r in good if r.get(key) is not None)
    if xs:
        last3 = sum(1 for x in xs if x >= 12.0)
        print(f"    {label:9s} median {st.median(xs):5.2f} min  |  in the final 3 minutes on "
              f"{last3} of {len(xs)} days ({100*last3/len(xs):.0f}%)")
