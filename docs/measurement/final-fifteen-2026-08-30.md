# The final fifteen minutes — what it does, and what a $0.20 single paid

*2026-08-30 · Strader · bead st-ro04 (Final Fifteen Payoff) · Desk work order
`20260830T064716__Desk__measure-final-fifteen-move-and-premium-path`, Steve's ask
2026-08-30. All on data already on disk — no spend, no new pull. Deterministic
collection, no model inference.*

**286 ES days** (2025-05-27 → 2026-08-28) and **274 OPRA days** (2025-05-27 →
2026-08-14, 548 option legs). Every rate below carries the count behind it.
Anything under ten days is labelled a story, not a base rate.

---

## The answer in four lines

1. **The arithmetic goes to Desk, and Desk was conservative.** A ~$0.20 SPX
   0DTE strike at 14:45 sits a median **14.9 points** (calls) / **17.3 points**
   (puts) from spot — further out than the ~9 the model assumed. On the days
   that moved 9–11 points the leg's way, the peak was a median **2.08×** — a
   $0.20 option reaching **$0.35**, not $10.00. **Zero of 548 legs reached 50×.**
2. **The move Steve is describing does happen — the pricing is what's off.** The
   window travels ≥10 points on **43.0%** of days (123 of 286) and ≥20 on
   **5.9%** (17). The tape is not the problem; the strike distance is.
3. **Getting to 10× took a median 16.9 points** (24 legs, min 9.5). The 20+
   point days paid a median 12× — the payoff is real, it just starts about
   seven points further out than assumed.
4. **The big moves arrive late, and that is the tax nobody costed.** First touch
   of 10 points comes a median 9.0 minutes into the window; of 20 points,
   **11.3 minutes** — 82% of them in the second half, when there is almost no
   time value left to buy.

---

## 1. What the final fifteen actually does (286 days)

**Where the close landed** — and **what the window touched**, which is the row
that prices a long single, because the option is paid by the touch and not by
the bell.

| threshold | close, up | close, down | close, either | **touched, either** | 2025 | 2026 |
|---|---|---|---|---|---|---|
| ≥ 5 pts | 94 (32.9%) | 61 (21.3%) | 155 (54.2%) | **258 (90.2%)** | 91.8% | 88.6% |
| ≥ 10 pts | 40 (14.0%) | 24 (8.4%) | 64 (22.4%) | **123 (43.0%)** | 40.4% | 45.7% |
| ≥ 15 pts | 16 (5.6%) | 8 (2.8%) | 24 (8.4%) | **59 (20.6%)** | 21.9% | 19.3% |
| ≥ 20 pts | 5 (1.7%) | 3 (1.0%) | 8 (2.8%) | **17 (5.9%)** | 2.7% | 9.3% |

SPX rose materially across the corpus, so the same thresholds as a percentage of
each day's own 14:45 price (10 points is 0.147% at the median day's 6824):
≥0.147% touched on **125 days (43.7%)**, against 123 in points — the two
yardsticks agree, so the points figure is not an artifact of the level rising.

**Shape.** Median |move| 5.25 pts; p75 9.25; p90 14.25; max 29.00. Median window
range (high to low) **12.25 pts**. The close finished up on 156 days (54.5%),
down on 127 (44.4%), unchanged on 3.

**The 2025/2026 split is reported as a column and discards nothing** — the
split-half discard gate is retired (Steve, 2026-08-30, confirmed directly).

---

## 2. Does any 14:45 state select for it? (286 days joined)

The R1–R7 pre-registered combination rules and the footprint solo call, read at
14:45 and scored against the final fifteen. These rules were written 2026-08-29
before their first run and are not tuned here; this study imports the same table
rather than a fork of it.

| rule at 14:45 | call | fires | touch ≥10 | touch ≥20 | **lift on touch ≥10** | direction edge |
|---|---|---|---|---|---|---|
| R4 bought | up | 22 (7.7%) | **68.2%** | **18.2%** | **+25.2 pts** | +5 |
| R3 pinned | pin | 5 (1.7%) | 60.0% | 0.0% | +17.0 *(story)* | — |
| R2 launch | up | 26 (9.1%) | 46.2% | 7.7% | +3.1 pts | **+38** |
| R5 sold | down | 26 (9.1%) | 46.2% | 3.8% | +3.1 pts | +8 |
| R1 flush | down | 27 (9.4%) | 29.6% | 0.0% | **−13.4 pts** | +4 |
| _(no rule fires)_ | — | 174 (60.8%) | 40.2% | 5.7% | −2.8 pts | — |
| base rate | | 286 | 43.0% | 5.9% | — | — |

Two things separate here that are usually conflated:

- **R4 "bought" selects for movement, not direction.** It raises the ≥10-point
  touch rate from 43% to 68% and triples the ≥20 rate, on 22 days — the
  strongest movement filter in the set. But its directional edge is +5 (8 with,
  7 against). It says *something is about to happen*, not *which way*.
- **R2 "launch" selects for direction, not movement.** Only +3.1 on the touch
  rate, but 12 with against 2 against — an edge of **+38**, and it is the same
  rule that held on both halves at 14:45 in the Stage-3 work. It also pulls the
  first 10-point touch two minutes earlier than base (6.97 min vs 9.00), which
  on a decaying option is worth more than it looks.
- **R1 "flush" is anti-selective**: when it fires the window is *quieter* than
  base. Consistent with the Stage-3 finding that R1 runs inverse.

Footprint solo call at 14:45: `up` on 40 days, edge **+28** (16 with, 5 against);
`down` on 39 days, edge −3; `pin` on 207.

---

## 3. What a ~$0.20 single actually paid (274 days, 548 legs)

Per day, per side, the OTM strike whose last print in 14:40–14:45 sat nearest
$0.20, walked to the close.

**A $0.20 strike was available every single day** — 274 of 274, both sides, with
a median mark of exactly $0.20 (median error $0.05). It was never untradeable at
14:45. What it was, was **far away**: a median 14.9 points (calls) / 17.3 points
(puts) from spot, p75 21.3 / 22.9.

That distance is the whole of the arithmetic. Near expiry the option is worth
about its intrinsic value, so reaching a target premium needs *the strike
distance plus the target*, not the target alone.

| peak reached | legs | rate | on a 5-lot ($100 in) |
|---|---|---|---|
| ≥ 2× | 197 | 35.9% | $200 out |
| ≥ 3× | 97 | 17.7% | $300 out |
| ≥ 5× | 52 | 9.5% | $500 out |
| ≥ 10× | 24 | 4.4% | $1,000 out |
| ≥ 20× | 10 | 1.8% | $2,000 out |
| **≥ 50×** | **0** | **0.0%** | $5,000 out |

**What move it took**, joined to the day's ES excursion in the leg's favour:

| favourable excursion | legs | median peak | reached 10× |
|---|---|---|---|
| under 5 pts | 245 | 1.33× | 0 (0%) |
| 5–10 pts | 171 | 2.00× | 1 (1%) |
| 10–15 pts | 63 | 2.27× | 7 (11%) |
| 15–20 pts | 42 | 4.83× | 7 (17%) |
| 20+ pts | 17 | **12.00×** | 9 (53%) |

**Steve's case isolated** — the 49 legs whose day travelled 9–11 points the
leg's way: peak multiple median **2.08×**, p90 5.00×, max 12.50×. Entry premium
median $0.20 → peak premium median **$0.35**. Reached 50× on **0 of 49**.

**Desk's order-of-magnitude model is confirmed, and it understated the gap.**
Desk put the required move "nearer twenty points" on an assumed ~9-point strike
distance; measured, the strike distance is 15–17 points, so 10× took a median
**16.9 points** and 50× took more than the corpus ever produced in fifteen
minutes.

**Median close multiple 0.20–0.24×** — the median leg gives back three-quarters
to four-fifths of its value by the bell. Holding this to the close is close to a
total loss by construction.

---

## 4. When to take it off (item 4)

The peak prints at a median **1.08 minutes** after 14:45 — but that is the
signature of a decaying option whose high *is* its first print. The number that
matters is the winners: **on the 97 legs that at least tripled, the peak printed
at a median 7.12 minutes after 14:45**, and only 3% of all legs peaked in the
last three minutes.

So the take-profit window on a working trade is roughly **14:50–14:54**, not the
bell. That sits against the arrival finding in §1 — the 20-point moves *first
touch* at a median 11.3 minutes — meaning the largest moves arrive after the
best exit window has passed for a position opened at 14:45.

**Arrival buckets, first touch after 14:45:**

| threshold | days touched | median first touch | early half (14:45–14:52) | late half |
|---|---|---|---|---|
| ≥ 5 pts | 258 (90.2%) | 5.14 min | 177 (69%) | 81 |
| ≥ 10 pts | 123 (43.0%) | 9.00 min | 49 (40%) | 74 |
| ≥ 15 pts | 59 (20.6%) | 10.27 min | 13 (22%) | 46 |
| ≥ 20 pts | 17 (5.9%) | 11.33 min | 3 (18%) | 14 |

The bigger the move, the later it shows up. Desk expected a first-order effect
here and it is first-order.

---

## 5. Two holes, both named rather than filled

**The spread is not in this measurement and cannot be.** Every OPRA record in
this corpus is `schema: trades`; the estate has never held OPRA NBBO. Entries at
the ask and exits at the bid are not computable from this data at any sample
size. A far-OTM SPX option in the last fifteen minutes is wide — a "$0.20"
option may be 0.15 bid / 0.30 ask — so **every multiple above is a
print-to-print result and an upper bound on an achievable one**, and on a
lottery-shaped trade that tax is larger than usual. Desk ruled this path (a) on
2026-08-30: run on prints now, state the hole, never estimate it. Filling it
needs an OPRA quotes pull, which is spend and is gated by st-byif.

Liquidity, as far as prints can show it: the longest silence on the chosen
strike ran a median 22s, p90 64s, max 219s.

**The closing-seconds artifact — found here, and it changes the headline.** The
last seconds of the OPRA tape carry prints that are not single-leg marks. On
2026-08-05 the 7725 put printed **$84.70** in the final six seconds while it was
about three points in the money and ES had fallen 16.75 over the window; all 87
prints above $10 on that symbol landed inside those six seconds, against a
median print of $0.30.

Twelve of 548 legs peak in the last thirty seconds — but **eight of the
twenty-nine legs that reached 10× do**, so the artifact concentrates in exactly
the tail this study reports. Every leg is therefore scored twice, over the full
window and over a clean window ending 14:59:00, and **the clean window is what
is quoted above**. The difference is not cosmetic: on the full window two legs
reach 50× and the maximum is 385×; on the clean window **none do**. Anyone
re-running an OPRA study over this corpus should carry the same cut.

---

## Sources and how to re-run

```
scripts/measurement/final_fifteen_base.py            -> data/measurement/final-fifteen-base-2026-08-30.jsonl
scripts/measurement/final_fifteen_summary.py         -> docs/measurement/final-fifteen-distribution-2026-08-30.txt
scripts/measurement/final_fifteen_by_rule.py         -> docs/measurement/final-fifteen-by-rule-2026-08-30.md
scripts/measurement/final_fifteen_premium.py         -> data/measurement/final-fifteen-premium-2026-08-30.jsonl
scripts/measurement/final_fifteen_premium_summary.py -> docs/measurement/final-fifteen-premium-2026-08-30.md
```

`final_hour_combo.py` was refactored so its pre-registered R1–R7 table is
importable rather than re-typed — item 2 scores the same rules, not a fork.
Verified: its own output is byte-identical before and after the refactor.

**The split-half discard gate is retired — confirmed by Steve directly,
2026-08-30.** This report ran that way: by-half behaviour is a reported column
and no rule was dropped for failing a half. The instruction had reached here
relayed through Desk, and a peer relaying an authorisation is a claim to verify
rather than an authorisation, so it was carried as an open question until Steve
answered it himself. He has. Nothing in this report changed either way — no rule
was discarded under either reading — but the standing method is now settled:
**report both halves, discard on neither.**
