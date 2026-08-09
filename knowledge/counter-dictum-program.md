---
type: decision
title: "The Counter-Dictum Program — what we are trying to do and why"
description: "Canonical charter for the orderflow/execution-harness effort: find an edge that justifies deliberately running counter to 'don't chase' and 'don't overtrade', for single-leg SPX scalp-proxy trades. Read this before designing or resuming any study in this program."
timestamp: 2026-08-09T16:00:00-05:00
metadata:
  bead: st-k68o
  supersedes_fragments: "COO auto-memory project_orderflow-mastery-directive, project_singleton-scalp-proxy-target, project_execution-harness-exploration"
---

# The Counter-Dictum Program

**This is the one canonical statement of the program's purpose.** Every memory
store in this enterprise is per-repo — beads issues, `bd remember`, Claude
auto-memory, `CLAUDE.md`, and the two OKF bundles are all repo-scoped, and
nothing is shared by default. Cross-repo *reads* are free. So this file is the
single source and everything else points at it. If you are about to restate its
contents somewhere else, don't — link here instead.

---

## 1. The goal

**Find an edge that justifies deliberately running counter to "don't chase" and
"don't overtrade."**

Not "test whether the maxims are true." The program starts from Steve's
contention that both are **artifacts of a broker-UI era**, not laws of the tape,
and looks for the conditions under which violating them is correct.

**What the binding constraint actually is** — Steve, 2026-08-09, correcting the
framing this charter was first drafted with:

> Movement is abundant; direction is part of problem but greater is codifying an
> entry and stop loss strat.

Round 4 concluded "direction is the entire problem." That is wrong, or at least
badly weighted. Movement is abundant (§4.2) and direction is *one* input, but
the larger unsolved piece is **codified entry and stop-loss mechanics** — where
exactly you get in, where exactly the stop sits, and what happens after it
fires. This is the same claim §2 makes about the source of his losses, and it
means the execution work is not downstream of the signal hunt. It is the main
line. A perfect directional signal with uncodified entry and stop mechanics
still loses the way it always has.

## 2. Why Steve believes this (his reasoning, not ours)

Steve attributes the majority of his career losses to **fumbling a
one-size-fits-all broker interface** under time pressure — small click targets,
hurried decisions, no gates against his own known weaknesses — rather than to
the trades themselves. His case:

- Purpose-built code changes the calculus. A trade string carrying a stop
  trigger cannot be hand-built inside a time-constrained window; code can build
  it in one keystroke.
- The current regime features large, mostly uninterrupted moves in the first
  hour. On such a tape, refusing to chase means no conventional entry exists at
  all.
- Mancini's level-to-level one-and-done leaves money on the table.

**The meta-reason, which governs design:** he asked for **gates against his own
weaknesses**. The harness is as much a self-protection device as an aggression
device. Build it that way. A version that only removes friction has missed half
the ask.

## 3. What the edge is for — the target application

**Single-leg SPX options traded as a proxy for futures scalping.** Holding
window 5–15 minutes. Steve's own framing: *"an option single is a futures
contract on its last day"* ([[singles-as-futures-proxy]]).

**NOT fly assistance.** Steve corrected this drift explicitly on 2026-08-08.
Do not propose the late-day butterfly lane as the payoff of this work. The fly
lane exists and is governed separately ([[directional-gex-butterflies]],
[[buying-movement-delta-first]]); it is not this program's destination.

## 4. How candidates are scored (binding)

0. **Entry and stop geometry is the primary object of study, not a downstream
   detail** (§1). A candidate is not "a signal" — it is a signal *plus* a
   specified entry point, a specified stop, and a specified response to the stop
   firing. Evaluate the triple. A study that reports directional accuracy
   without stating where the entry and stop sat has not answered the question
   being asked. The metrics that speak to this are **MFE/MAE and stop-survival**,
   not hit rate.
1. **Directional tail shift, not drift.** Where direction *is* being scored, a
   candidate must move `P(≥10-pt move WITH the signal's direction)` relative to
   against it. Median 30-minute drift is the wrong metric — Steve said so
   directly, and round 4 confirmed it empirically. Note this is one input to
   §4.0, not the whole grade.
2. **Score against the signal's own hour, never a pooled baseline.** Movement is
   abundant and steeply time-dependent:

   | CT hour | P(≥10-pt move in 15 min) | median 15-min excursion |
   |---|---|---|
   | 08 (from 08:30) | **77%** | 14.80 pts |
   | 09 | 62% | 11.67 |
   | 10 | 42% | 8.88 |
   | 11 | 32% | 7.33 |
   | 12 | 26% | 6.67 |
   | 13 | 25% | 6.09 |
   | 14 | 27% | 6.66 |

   63 days, 1-second archive, 2026-05-07..2026-08-06 (st-1bv1). The pooled ~40%
   figure from round 4 averages across this gradient and is **retired as a
   comparator**. A signal that fires at 08:40 and produces a 60% hit rate is
   *worse* than doing nothing.
3. **Traverse the channel families before measuring.** Binding procedure in
   [[channel-family-taxonomy]] — write a verdict per family into the study doc
   *before* any measurement. Four orderflow rounds skipped this; the clock
   family it had already flagged as `NEVER-TRAVERSED` then beat every signal
   those rounds produced. This is the enforcement layer, and it is not optional.
4. **Spot metrics are provisional.** Everything measured so far is spot. The
   options layer (0DTE theta and gamma) will change every number; a favorable
   5-point excursion in minute one and minute ten are not the same trade.

## 4a. The stop doctrine (Steve, 2026-08-09 — supersedes "zero-tolerance")

Steve withdrew the zero-tolerance framing as **overstated**. It was never his
position properly stated, and this matters because the measurement that
"refuted the tight stop" tested the overstatement, not the position.

**The doctrine, in his words:**

> until P/L is green a drawdown of more than 3 points needs to be avoided.
> tolerance for drawdowns need to balance probability of profit against — can
> increase tolerance but only to an extent.
>
> Getting back into a trade liberally is counter to 'don't over trade'. But
> semi-automated API management should be able to mitigate the stress/friction
> points and ease the management process.

Three things follow, and all three are design-bearing:

1. **The stop is state-dependent, not a number.** Before the position is green
   the budget is ~3 points. After it is green the tolerance widens — but
   bounded, traded off against probability of profit. This is a **ratchet**, not
   a fixed stop, and "green" is doing real work as a state boundary: it is a
   proxy for *the thesis is working*.
2. **The refutation may not touch this rule.** What st-gzwb killed was
   zero-tolerance and near-noise-floor cuts — FD0's ~1.1-pt budget-derived stop
   measured roughly 3× *inside* the noise floor. Separately measured: at 2-pt
   backtests the move resumes 96–98%. A 3-point pre-green stop sits just
   **outside** that common backtest band, which is a materially different animal
   from anything tested. **Treat the tight-stop question as OPEN, not settled.**
   The cheap decisive test is a sweep of pre-green budgets (2 / 3 / 4 / 5 pts)
   against a post-green ratchet, on the corpus already on disk.
3. **Liberal re-entry is knowingly counter to "don't overtrade."** Steve is not
   claiming otherwise — he is claiming the friction that made overtrading
   expensive is a tooling artifact, and that semi-automated management removes
   it. That is the wager the whole program tests.

**On "semi-automated":** Steve's own words — *"I don't know exactly what
'semi-automated' means yet but it is in the vein of the life-long goal of
software — to lubricate the mechanics of the problem domain."* It is
deliberately undefined and he has asked for **creative approaches** to it. The
fixed points are §7's boundaries: the human triggers, code prepares. Everything
between is open design space, and proposals are wanted rather than merely
tolerated.

## 5. What is settled — the ledger

**Live:**

- The morning regime is real: median 52.6-pt primary move 08:30–10:30 CT, every
  day of a 22-day corpus (st-gzwb).
- **Liberal re-entry is validated.** After a 2-point backtest the move resumes
  96–98% of the time; re-entry needs no filter.
- **Continuation is gradeable in real time.** $TICK on the move's side + VIX
  co-travel + $ADD slope grades next-15-minute continuation 25%→73% against a
  57% base (st-cdwe). Meter built, display-only, running the 2-trace live
  mapping because $ADD publishes a session late on Schwab.
- **Excursion asymmetry beats win rate.** Positive dealer gamma at confirm:
  median MFE/MAE 15.75/5.25 with 70% MFE>MAE, against 7.75/8.25 and 46% in
  negative gamma, at near-identical win rates (st-trbn). This is the
  stop-survivability metric a re-entry harness actually needs, and it is
  currently unexploited.
- **Hour of day is the largest single effect measured anywhere on this corpus**
  (§4.2) — larger than any orderflow signal from four rounds.

**Killed — do not re-propose without new grounds:**

- Flow leads price — refuted decision-grade (st-ek8b). Contemporaneous coupling
  is real; lead is not.
- The V-turn signal — its lead-lag statistics were indistinguishable from random
  timestamps (87.9% vs 88.1%); conditioning did not save it (st-yirc, st-mvvf).
- The two-signal reversal, for this lane — under scalp metrics the near-wall cut
  *reduces* the 10-point tail to 12% against an 18% control. It marks **pinning**,
  not launching: a containment signal (st-a2cj).
- Netcvx regime state as a fast-move timer — 36–43% across all states (st-a2cj).
- The post-entry "fuel" rule — ran backwards on the larger sample, 52% with fuel
  vs 63% without (st-gkbo).
- The vanna threshold as operationalized — the $800MM last-hour bar is exceeded
  on 58 of 63 days (st-mvvf).
- VIX slope as protection-demand intelligence — ~80% mechanical ES coupling,
  residual is a coin flip (st-40fv). Survives only as a momentum proxy.
- **Flow-print magnitude as an event trigger** — 97% of giant prints land in the
  final 30 minutes, where displacement is at its daily floor. That surge is
  expiry mechanics moving notional without moving price (st-1bv1).

## 6. What is open

Ordered by §1: entry-and-stop codification leads, signal hunting follows.

- **THE MAIN LINE — entry and stop geometry.** The tight-stop variants that
  tested net-negative (st-gzwb) were zero-tolerance and near-noise-floor cuts on
  **breakout** entry — one corner of a design space nobody has mapped, and
  explicitly *not* the doctrine in §4a. Two untested shapes, both cheap on data
  already on disk:
  - **The pre-green/post-green ratchet** (§4a) — sweep pre-green budgets
    2/3/4/5 pts against a post-green widening rule. This is Steve's actual
    position and it has never been measured.
  - **[[Join The Turn]]** (st-chat, never built) — enter *on* the backtest, so
    each failed cycle risks turn-plus-stop instead of the full wiggle amplitude.

  Adjacent and also unbuilt: the execution harness itself (st-ug5) — stop
  attached at entry, coded re-entry after a stop-out, human-triggered. Steve's
  2026-08-09 reframe puts all of this ahead of the signal hunt, not beside it,
  and he has asked for **creative approaches** to the semi-automation layer.
- **Stop-survivability is measured but unexploited.** The excursion asymmetry in
  §5 (3 points of MFE per point of MAE in positive gamma, at identical win
  rates) is a stop-design input sitting unused. It says *where a stop can live*,
  which is the question §4.0 asks and no study has yet taken up.
- **The momentum side of the vendor doctrine is untested** — dump onsets as
  *events* rather than states, convexity down-spike moments, and the
  dump-then-ramp sequence. The reversion half has been tested four times and
  mostly died; the momentum half is the one canonical continuation claim and it
  has never been run.
- **The regime rule's input has never been defined.** The GexBot principal's
  whole method compresses to "rising vol → lean long gamma for continuation;
  falling vol → fade off it." We have no operational definition of rising versus
  falling volatility on this corpus, so everything downstream is untested.
- **Nothing measured so far is decision-grade.** Four rounds, multiple
  definitions, no pre-registration. st-trbn states it plainly for its own study
  and the same applies here.

## 7. Hard boundaries (design constraints, not preferences)

- **Human-triggered. Not automated, not high-frequency.** Steve set this himself
  and it is a design boundary, not a phase. Code semi-automates what a human
  cannot do in time — attaching the stop, building the re-entry — never the
  decision to enter.
- **Full-size SPX only.** Never propose XSP or SPY step-downs; size via
  structure (strike, DTE, spread width). [[spx-only]] is a standing overrule.
- **Steve is the sole risk and sizing authority.** Hindsight measurement grades
  correctness; it does not set size.
- **Nothing enters the trading workflow unmeasured.** Vendor and community
  claims are claims until tested against our own archive
  ([[canonical-community-measured]]).

## 8. Time box

The GexBot Quant tier is a one-month commitment from 2026-08-05; the
downgrade decision lands ~Sep 1 and should be informed by what this program
finds. `/hist` is a rolling 90-day window, so archive days age out permanently —
overlap only grows forward.

## 9. Where the work lives

Epic **Orderflow Mastery** (st-ygy1). Measurement record in
`docs/measurement/`; doctrine in `docs/gexbot/`. COO works this domain directly
under an explicit division-of-labor exception Steve declared 2026-08-06, scoped
to this effort and time-boxed to the Quant month.
