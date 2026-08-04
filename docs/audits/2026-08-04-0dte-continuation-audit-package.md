# Audit Package — 0DTE Singleton Continuation Program

**Bead:** Package For Audit (st-lgcg) · **Date:** 2026-08-04
**Prepared for:** an outside reviewer ("the Auditor") with no session context.
Everything needed is in this document plus the pointed-to files. Verify every
claim against its pointer; nothing here is authoritative on its own.

## Why this audit exists

The operator (Steve) trades 0DTE SPX options as human-triggered singletons —
full SPX, never step-downs, he is sole risk authority. Over 2026-08-03/04 a
measurement program was built around one question: **the recent regime of
large one-sided morning moves — can continuation be graded live, and can a
tight-cut/liberal-re-entry execution style capture these moves?**

The program produced real results (below), but the session exposed a process
weakness Steve named himself: **the completeness of the search depended on his
own prompting.** VVIX — an obvious member of the vol-instrument family — was
measured only because he proposed it; the agent had extended only by adjacency
from what he'd named. One systemic correction is already standing (enumerate
the candidate space before measuring; re-enumerate after capability unlocks).
This audit is the second correction: a cold context hunting the *class* of
oversight, not the instances already caught.

## Your charter, Auditor

Find what the inside view missed. Specifically:

1. **Candidate-space omissions.** What belongs in the space of
   continuation-relevant channels/instruments/representations that still is
   not there? (Exemplar of the class: VVIX, missed until prompted; $VIX1D,
   missed until a post-hoc enumeration.)
2. **Mechanical-coupling errors.** Where might a reported "signal" be another
   variable wearing a costume? (Exemplar: the VIX 5-min slope trace, AUC .66,
   turned out ~80 % mechanical coupling to the concurrent ES move; its
   residual was a coin flip. Found only because a residual test was run.
   Which reported numbers have NOT had their residual test?)
3. **Label and definition soundness.** The whole continuation framework rests
   on one labeling choice: CONT = price extends ≥2 pts beyond the standing
   extreme within 15 min, morning window, last 15 min excluded. Neither
   parameter was swept. Is the framework measuring what the trader needs?
4. **Small-n and clustering honesty.** 22 July days; minutes cluster within
   days; several key cells run n = 38. Are any displayed probabilities too
   confident for decision use? The meter shows "73 % state" to a novice —
   does that representation overstate?
5. **Prompting-dependency residue.** List the decisions in this program that
   exist only because the operator happened to ask (VVIX, VIX1D, the audit
   itself). What does a systematic version of this program look like, where
   coverage does not depend on operator prompting?
6. **Execution-side blind spots.** The chase simulations refuted
   cut-on-slightest-backtest, but the dip-entry ("join the turn") lane was
   abandoned at tick granularity as artifact-prone. Is the refutation itself
   artifact-free? (Entry models, friction model, R_END trail choice — all
   unswept or lightly swept.)

## The channels accumulated (inventory with coverage and gaps)

| Channel | What | Coverage | Gaps the Auditor should know |
|---|---|---|---|
| ES tape | DataBento GLBX trades, ES.c.0 | 267 days, but **morning (08:30-) coverage only 21 full-RTH days (July 2026) + 14 partial days (2025-07→2026-04) + 2026-03-20** | The regime question rests on this asymmetry; see st-4ts confound below |
| ES book | DataBento MBP-1 | ~13 days, 2026-07 | **Captured but never used in any study** |
| SPX options tape | DataBento OPRA SPXW trades | 250 days, **13:00–15:00 CT only** | No morning options flow exists; extension is a paid decision, never made |
| Market internals | Schwab minute candles, 11 symbols: $TICK $TRIN $ADD $VOLD $VIX $VIX9D $VIX3M $VVIX $VIX1D $COR1M $COR3M | From 2026-06-18 (first 4); vol complex from 2026-08-03/04 backfills | $ADD/$VOLD publish a session late (no live breadth); $VIX1D/$COR1M/$COR3M serve ~1 session of history — a missed daily pull is permanent loss (alerting bead st-c3r is the only net) |
| Not served by Schwab | $SKEW, put/call ratios, $DXY | — | Recorded in `scripts/corpus_pull_internals.py` docstring |
| Serve, deliberately excluded | /ZN (24 h sessions), TLT | — | Cross-asset stream design never done |
| Mancini letters | daily parsed levels/stance | daily | **Never joined to the measurement program** (open lane) |
| GEX / dealer positioning | GexBot | **paused 2026-07-03** | Orderflow-first direction chosen instead; V-metric bead st-r2o.1 is the in-house path, unfinished |
| Legs corpus | zigzag decomposition, 1,649 legs / 263 days | full corpus | Built pre-program; 4 recent days missing from moves.jsonl |

## The studies and what they found (with commits)

All in `/root/projects/Strader`; every number regenerates from the named
script. Negative results are load-bearing — do not skim them.

**1. Grade The Flush (st-gzwb, closed) — `scripts/measurement/morning_flush_study.py`, doc `docs/measurement/morning-flush-anatomy.md`, commits 3338a3d/5161a7e.**
Regime confirmed: 22/22 July days had a primary morning move (median 52.6
pts); out-of-sample (12 selected days 2025-07→2026-04) median 31.0 — the
recency claim survives a bias running against it. Backtests inside moves
resume 96–98 % (100 % with ≥5 pts remaining). **Every tight-stop chase
variant tested was net-negative at the median — including with oracle
direction** — while oracle-direction endure made +18.5 pts/day median.
Early tape ANTI-predicts direction in July (f5 agreement 8/22) but that fade
rule failed out-of-sample (3/9): July-local. Early *energy* grades size in
both samples (f15 volume ρ +.57 in-sample, +.90 OOS). FD0's budget-derived
~1.1-pt stop measured ~3× inside the noise floor.

**2. Continuation Trace (st-cdwe, closed) — `scripts/measurement/morning_flush_continuation.py`, doc `docs/measurement/morning-flush-continuation.md`, commit 55679e5.**
1,882 labeled minutes. Best traces: $TICK on move's side (AUC .665, medians
flip +116/−49), VIX 5-min slope (.660), $ADD slope (.653). Convergence score
0–3 monotone: 25/49/65/73 % vs 57 % base. $TRIN dead (.44). **Delta
divergence points the WRONG way** (22 % of continuing minutes vs 10.5 % of
dying ones). At 2-pt backtest events, failures are 11/448 — re-entry needs no
filter. Day-level: VIX co-traveled with the move 22/22 days, ρ +.85 vs size.

**3. Vix Reads Deeper (st-40fv, closed) — `scripts/measurement/morning_flush_vix_depth.py`, same doc, commit ba6e3f5.**
ΔVIX = −1.55·ΔES% at R² .79 → **the VIX slope trace was ~80 % mechanical;
residual AUC .522 = coin flip.** De-seasoning immaterial at 5-min. Quadrants
survive: dn-move bounce with VIX still bid → 66 % continuation (n = 38);
up-move dip with VIX bid → 34 % (n = 274); the ES-side monetization read
FAILED (64 %, predicted low). Term spread (9D−30D) inverted intraday only on
07-23/07-27 — descriptive.

**4. Vol Of Vol (st-lru8, closed) — `scripts/measurement/morning_flush_vvix.py`, same doc, commit dd1a4dd.**
ΔVVIX = 2.15·ΔVIX at R² .53; residual AUC .532 — no incremental 5-min
signal. VVIX/VIX ratio slope inverted (mechanical). **Vol-complex quadrants
earn the seat:** complex bid against an up move → 30.9 % continuation
(n = 220, the strongest warning state measured); complex releasing during a
down move → 46.8 % — the fuel-gone read works in vol space where it failed
in price space. Day-scale early-warning use (VVIX firming while VIX sleeps)
untestable — July was calm (VVIX 86–108).

**5. Meter Goes Live (st-byrg, closed) — `scripts/desk/continuation_meter.py`, commit 95482c4.**
Live 30 s pane on steves-desk:meter. Display-only. Two-trace fallback
(33/57/74 %) because breadth publishes a day late. Stale banner ≥3 min.
Frames journal to `data/exec/continuation-meter-<day>.jsonl` — **the meter's
own calls are scoreable retrospectively; nobody has done so yet.**

**6. Roster Completes (st-b3jq, closed) — commit 42de6dc.** The
post-correction enumeration: $VIX1D/$COR1M/$COR3M captured (forward-only);
VIX1D community standing reviewed — credible as event-premium/regime gauge,
poor as naive intraday signal (documented overnight-bias artifact; no
tradeable products, so no arbitrage discipline). Recommendation on record:
display, don't score, until residual + de-seasoned tests pass on our tape.

## Oversights already caught — the exemplar class

These were caught *conversationally*, which is the problem. Each is a class
instance; the Auditor's job is the class.

1. **VVIX omission** — knowledge present, unproposed until the operator named
   it. Cause analysis in COO auto-memory `feedback_enumerate-before-measuring`.
2. **VIX slope as costume** — .66 AUC reported before the residual test
   existed; caught one pass later.
3. **First-pass artifacts in st-gzwb** — span-clipped resume rates (100 % by
   construction) and a tick-churn dip-entry sim (1,300+ attempts/day);
   both caught and corrected in-session, but by the same context that made
   them.
4. **$ADD publishes a session late** — discovered only at live meter launch,
   not during study design.
5. **st-9k1 phantom bead ID** cited in a standing memory; the real bead is
   st-m3f (Fade The Fourth Fire). Corrected.
6. **st-4ts recency-regime confound** — its 51 %→88 % morning-share claim
   compares windows with structurally different pull coverage; full-RTH
   restriction gives 78 %→88 %. Flagged on the bead, unresolved.
7. **"First-hour edge 54 %"** cited in st-ug5's own text; the source doc
   says 52 % for hour 08, bullish-anchor-biased
   (`docs/measurement/recognizer-acuity-run2.md`).

## Known limitations the Auditor should press on

- n = 22 clustered days for everything internals-based; no OOS exists before
  2026-06-18 and none was held out.
- Label parameters (≥2 pts / 15 min / morning window) chosen once, unswept.
- Thresholds and quadrant cells read in-sample; several cells n = 38.
- The three meter traces are mutually correlated ("three views of one state");
  the meter presents per-state percentages to a novice reader.
- Direction remains unsolved; the +18.5/day oracle-endure number is a
  ceiling, not an edge.
- The chase refutation used specific entry (±5/±8 off open), trail (8 pt) and
  friction (0.6 pt/attempt) choices; the dip-entry lane (Join The Turn,
  st-chat, open) was parked, not resolved.
- MBP-1 book data and Mancini levels: captured/available, never joined.
- Meter journal exists but the meter has never been scored against outcomes.

## Open beads in this program

Join The Turn (st-chat) · st-4ts (recency lens, confound flagged) · st-5tt
(internals forward re-test) · st-c3r (pull-failure alerting — now the only
net for 3 symbols) · st-m3f (fourth-fire fade) · st-r2o/.1 (V-metric,
options-flow convexity) · st-btu (pre-market capture ruling) · st-u56
(07-31 decomposition, unblocked) · plus FD0/execution lane st-apzt / st-5ey
under st-ug5.

## Reading order for a cold start

1. This document.
2. `docs/measurement/morning-flush-anatomy.md` (regime + anatomy + OOS).
3. `docs/measurement/morning-flush-continuation.md` (traces → VIX depth →
   VVIX, includes every negative result and the meter's operational notes).
4. The scripts, in the same order — each regenerates its numbers.
5. Bead trail: st-gzwb → st-cdwe → st-40fv → st-lru8 → st-b3jq → st-byrg
   (`bd show <id>` from /root/projects/Strader).
