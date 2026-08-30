"""Final-fifteen item 2 — does any 14:45 rule state SELECT for the big last-fifteen move? [st-ro04]

WHY
    Item 1 gives the base rate: how often the final fifteen travels 5/10/15/20
    points. That is the price of a lottery ticket bought blind. Item 2 asks the
    only question that could make it a trade rather than a lottery — whether any
    state readable AT 14:45 raises that rate. Desk: "whether any rule state
    selects for the big closes, not the base rate."

WHAT
    Joins two things on the day:
      * the 14:45 rule state — the R1-R7 pre-registered combination rules and
        the footprint solo call, imported from final_hour_combo so this study
        scores the SAME table rather than a fork of it. Those rules were
        written 2026-08-29 before their first run and are not tuned here.
      * the final-fifteen outcome from final_fifteen_base.py.

    For each rule the report gives coverage (how often it speaks), then the
    close and touch rates at each threshold WITH the base rate beside them, so
    a lift is visible as a lift. Every rate carries its day count; anything
    under ten days is labelled a story, not a base rate.

    Directional agreement is scored separately: a rule that fires "up" is only
    useful for a call if the final fifteen actually went up.

    The 2025/2026 split is a reported column, never a discard gate (Steve
    retired the gate 2026-08-30, relayed via Desk — confirm at first contact).

RUN
    .venv/bin/python3 scripts/measurement/final_fifteen_by_rule.py [base.jsonl] [lens.jsonl]
"""
import json, sys, os, collections, statistics as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from final_hour_combo import load, parts, first_call, RULES, DEFAULT_LENS  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "data/measurement/final-fifteen-base-2026-08-30.jsonl"
LENS = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_LENS
THRESHOLDS = (5, 10, 15, 20)

fifteen = {}
for l in open(BASE):
    r = json.loads(l)
    if "skip" not in r:
        fifteen[r["day"]] = r

lens_rows, _ = load(LENS)
at1445 = {r["day"]: r for r in lens_rows if r["T"] == "1445"}

days = sorted(set(fifteen) & set(at1445))
print("# Final-fifteen by 14:45 rule state\n")
print(f"final-fifteen rows {len(fifteen)} · lens rows at 14:45 {len(at1445)} · "
      f"joined on {len(days)} days\n")
if not days:
    sys.exit("no overlap")

base = [fifteen[d] for d in days]


def rates(sub):
    """close and touch rates at every threshold, for one subset of days."""
    n = len(sub)
    out = {"n": n}
    for t in THRESHOLDS:
        out[f"close{t}"] = sum(1 for r in sub if abs(r["move"]) >= t)
        out[f"touch{t}"] = sum(1 for r in sub if max(r["f15_up"], r["f15_dn"]) >= t)
    return out


def pc(k, n):
    return f"{100.0 * k / n:5.1f}%" if n else "    —"


B = rates(base)
print(f"BASE RATE, all {B['n']} joined days")
print("| measure | >=5 | >=10 | >=15 | >=20 |")
print("|---|---|---|---|---|")
print("| close moved | " + " | ".join(f"{B[f'close{t}']} ({pc(B[f'close{t}'], B['n']).strip()})" for t in THRESHOLDS) + " |")
print("| window touched | " + " | ".join(f"{B[f'touch{t}']} ({pc(B[f'touch{t}'], B['n']).strip()})" for t in THRESHOLDS) + " |")
print()

# ─── which rule fires at 14:45 ───────────────────────────────────────────────
fired = collections.defaultdict(list)
called = {}
for d in days:
    name, call = first_call(parts(at1445[d]))
    if name:
        fired[name].append(fifteen[d])
        called[d] = call
silent = [fifteen[d] for d in days if d not in called]

print("## The R1-R7 combination rules, scored on the final fifteen\n")
print("Coverage is how often the rule speaks at 14:45. Lift is the touch>=10 rate")
print("against the base rate on the same joined days — the number that says whether")
print("the state selects for a move at all.\n")
print("| rule at 14:45 | call | fires | touch>=5 | touch>=10 | touch>=15 | touch>=20 | close>=10 | lift on touch>=10 |")
print("|---|---|---|---|---|---|---|---|---|")

CALL_OF = {name: call for name, call, _ in RULES}
for name, call, _ in RULES:
    sub = fired.get(name, [])
    if not sub:
        print(f"| {name} | {call} | 0 | — | — | — | — | — | — |")
        continue
    R = rates(sub)
    lift = (100.0 * R["touch10"] / R["n"]) - (100.0 * B["touch10"] / B["n"])
    tag = "  *(story, not a base rate)*" if R["n"] < 10 else ""
    print(f"| {name} | {call} | {R['n']} ({pc(R['n'], B['n']).strip()}) | "
          + " | ".join(pc(R[f"touch{t}"], R["n"]).strip() for t in THRESHOLDS)
          + f" | {pc(R['close10'], R['n']).strip()} | {lift:+.1f} pts{tag} |")

if silent:
    R = rates(silent)
    lift = (100.0 * R["touch10"] / R["n"]) - (100.0 * B["touch10"] / B["n"])
    print(f"| _(no rule fires)_ | — | {R['n']} ({pc(R['n'], B['n']).strip()}) | "
          + " | ".join(pc(R[f"touch{t}"], R["n"]).strip() for t in THRESHOLDS)
          + f" | {pc(R['close10'], R['n']).strip()} | {lift:+.1f} pts |")
print()

# ─── direction ───────────────────────────────────────────────────────────────
print("## Direction — when a rule speaks, does the final fifteen go its way?\n")
print("A directional rule is only tradeable if the move it names is the move that")
print("happens. Scored on days the final fifteen moved at least 5 points either way;")
print("days quieter than that are 'flat' and count against neither side.\n")
print("| rule | call | fires | went its way | went against | flat (<5pt) | edge |")
print("|---|---|---|---|---|---|---|")
for name, call, _ in RULES:
    sub = fired.get(name, [])
    if not sub or call == "pin":
        if sub and call == "pin":
            flat = sum(1 for r in sub if abs(r["move"]) < 5)
            print(f"| {name} | pin | {len(sub)} | stayed inside 5pt on {flat} "
                  f"({pc(flat, len(sub)).strip()}) | — | — | — |")
        continue
    sgn = 1 if call == "up" else -1
    with_ = sum(1 for r in sub if r["move"] * sgn >= 5)
    against = sum(1 for r in sub if r["move"] * sgn <= -5)
    flat = len(sub) - with_ - against
    edge = 100.0 * (with_ - against) / len(sub)
    tag = "  *(story)*" if len(sub) < 10 else ""
    print(f"| {name} | {call} | {len(sub)} | {with_} ({pc(with_, len(sub)).strip()}) | "
          f"{against} ({pc(against, len(sub)).strip()}) | {flat} | {edge:+.0f}{tag} |")
print()

# ─── the footprint solo call ─────────────────────────────────────────────────
print("## The footprint solo call at 14:45\n")
solo = collections.defaultdict(list)
for d in days:
    c = (at1445[d].get("fp") or {}).get("call")
    if c:
        solo[c].append(fifteen[d])
print("| fp call | days | touch>=10 | close>=10 | went its way (>=5pt) | went against | edge |")
print("|---|---|---|---|---|---|---|")
for c in sorted(solo):
    sub = solo[c]
    R = rates(sub)
    if c in ("up", "down"):
        sgn = 1 if c == "up" else -1
        with_ = sum(1 for r in sub if r["move"] * sgn >= 5)
        against = sum(1 for r in sub if r["move"] * sgn <= -5)
        edge = f"{100.0 * (with_ - against) / len(sub):+.0f}"
        w, a = f"{with_} ({pc(with_, len(sub)).strip()})", f"{against} ({pc(against, len(sub)).strip()})"
    else:
        w = a = edge = "—"
    print(f"| {c} | {R['n']} | {pc(R['touch10'], R['n']).strip()} | {pc(R['close10'], R['n']).strip()} | {w} | {a} | {edge} |")
print()

# ─── arrival, conditioned ────────────────────────────────────────────────────
print("## Arrival, conditioned on the rule speaking\n")
print("Item 1 found the big moves arrive late. If a rule state pulled the arrival")
print("EARLIER it would be worth more than its hit rate alone suggests, because an")
print("early move leaves time value on the option. Median minutes after 14:45 to the")
print("first 10-point touch, on the days that touched.\n")
allf = [r["first10_min"] for r in base if r.get("first10_min") is not None]
print(f"| state | days touching >=10 | median first-touch min | vs base ({st.median(allf):.2f}) |")
print("|---|---|---|---|")
for name, call, _ in RULES:
    sub = [r for r in fired.get(name, []) if r.get("first10_min") is not None]
    if len(sub) < 3:
        continue
    m = st.median(r["first10_min"] for r in sub)
    print(f"| {name} | {len(sub)} | {m:.2f} | {m - st.median(allf):+.2f} |")
