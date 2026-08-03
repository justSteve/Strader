# FD0 — Bare-Bones Flush-Down Harness

**Bead:** Cut And Await (st-apzt) · child of Coded Counter Wisdom (st-ug5)
**Date:** 2026-08-02, pre-export window · **Target:** Monday 2026-08-03 open
**Go/no-go:** Steve's call Monday morning. If any checklist line fails, NO-GO.

## What the platform actually does — RESEARCHED 2026-08-03

**This section replaces the original "Steve's validation card", which was
wrong to exist.** It asked Steve to go discover thinkorswim's order
grammar as though it were unknown territory. TOS order syntax and
conditional orders are documented and decades old; three of its four
questions were answerable from the manual and should never have been put
to him. Corrected under st-apzt after his 08-03 pushback.

**1. Paste-from-clipboard is a real, supported feature.** *Order Entry
Tools* (lower left of the main window) → *Order Entry* sub-tab → **Paste
order from clipboard**, lower right. It handles stocks, options, futures
and forex. Documented format, from a working example:

```
BUY +1 BUTTERFLY AMZN 100 17 Dec 21 3390/3400/3410 CALL @.20 LMT
```

Shape: action · signed qty · [strategy] · underlying · multiplier ·
expiry · strike(s) · CALL/PUT · `@`price · order type. Our entry-leg
grammar matches it. **Caveat that matters for a clipboard-driven
harness: stray spaces or extra text break the paste.** The renderer must
emit the order string and nothing else — no leading indent, no trailing
newline, no surrounding pane furniture.

**2. A condition CAN trigger on a different symbol, including an index.**
The TOS manual's conditional-order page says to "type in the desirable
symbol name in the corresponding form"; secondary documentation states
conditions may be based on "the price of other equities or indices (such
as the S&P 500)". So an SPX-index-conditional exit attached to an SPXW
option order is a supported, documented construct. **This was the
design's central open question and it is answered: yes.**

UI path: in the Order Entry form, the *Order Rules* column carries a gear
icon → *Order Rules* window → *Conditions* area, submission rules on the
left, cancellation on the right.

**3. The condition does NOT ride in the paste string.** The documented
paste grammar carries legs, price and order type — nothing else. There is
no condition syntax in it. Conditions are attached per-leg through the
gear icon, in the UI.

**Consequence for the renderer — this settles "string mode vs template
mode", and the answer is both, split by role:**

| Piece | How it reaches TOS |
|---|---|
| Entry leg | paste string → clipboard → one click |
| Conditional exit | **cannot be pasted.** Built once in the UI; the harness renders the two values Steve types into it: trigger symbol `SPX` and trigger price |

**4. There is no conditional paste string. Confirmed, not inferred.**

A compound order does have a text representation — one surfaced in the
wild looks like `FIRST_TRIGGERS_OCO 1 SELL MARKET/1 MU STUDY 'TMLSMA()…`
— but that is the *saved order's internal form*, not paste input. In the
thread where it appears, the answer given is explicitly not to paste it.
And on the paste feature itself: **no user reports successfully pasting a
conditional order string**, and every working example is the plain
legs-price-ordertype shape.

So the harness must not try to emit one. Rendering a conditional string
that TOS silently mangles is worse than rendering nothing.

**5. The reuse path is the chart context menu, not a template reload.**
A saved OCO/bracket order — *including a conditional one* — appears in
the **right-click menu on a chart** (`Buy Custom…`). That is the intended
way back to a saved conditional order, and it sidesteps the template
question entirely: nothing is being reloaded from a file, so nothing can
be lost in the round trip.

**6. The Method drop-down — observed in the live UI, 08-03.** Steve read
it off the screen while building the condition:

```
bid · ask · mark · vol index · front vol · back vol · vol diff · study
```

`study` opens a flyout. **There is no `last`** — an earlier note here
suggested falling back to LAST and that was wrong; it was inferred from
the adjacent *STOP Linked To* drop-down, which is a different control.
Ground truth beat the inference. **Use `mark`.**

Note what that list is made of: bid, ask, mark, and four *volatility*
measures — option quantities. That suggested the Method list is scoped to
the symbol in the row, so the order of operations matters: **set Symbol
first, then read Method.**

**Confirmed in the UI, 08-03: with `SPX` in the Symbol field, `mark` is
present.** The exit condition is therefore buildable exactly as designed —
SPX `mark` at or above the trigger — and this line is closed.

A `mark` condition is the "plain price comparison" this document meant:
a number compared to a number, nothing to compile. `study` is thinkScript,
and is the one a saved order degrades — it keeps the study's *name*, not
its script, "so it would not function as intended". FD0 never emits
anything script-shaped.

**7. A condition gates SUBMISSION — so it must hang on the SELL, not the
BUY.** Steve caught this in the UI: the Order Rules gear belongs to the
order whose row you clicked, and the Conditions area holds "rules for
order submission and cancellation… submission rules on the left".
Attached to the entry, an SPX condition would gate *when you buy*, which
is the opposite of a stop.

The correct construct is **1st Triggers**: "an order, once filled,
triggers execution of another order". So:

| Order | What it is | Where the condition goes |
|---|---|---|
| BUY +1 …PUT @limit LMT | the entry | **no condition** |
| SELL −1 same put @MARKET | triggered by the entry's fill | **condition here** — SPX `mark` at or above trigger |

The exit order comes into existence when the entry fills, then sits
unsubmitted until SPX crosses the level. That *is* the stop: this design
never uses a STOP order type, it uses a held-back market order. Closing an
option position off the underlying's price is a well-worn TOS pattern,
not an exotic one.

**Open, and worth confirming on the confirm dialog rather than assuming:**
community reports note that combining 1st Triggers with a conditional leg
has edge behaviour around whether a condition stays armed or resets after
the first trigger. Those reports concern *study* conditions and FD0 uses
`mark`, but the interaction has not been verified for our shape.

### The one thing still genuinely his

Build the exit condition once, save it, and confirm it comes back from
the chart right-click menu with the trigger price editable in seconds.

That is account behaviour, not documentation — the only kind of question
worth his time. Everything else above came out of the manual and the
platform's own community record.

Entry leg grammar (matches the documented paste shape):
`BUY +1 SPX 100 (Weeklys) 3 AUG 26 <strike> PUT @<limit> LMT`

Exit remains **MARKET** on trigger: a limit can miss outright in a
runaway rally, and one contract at ~0.30δ in a liquid book is exactly
where market-on-trigger is defensible. Steve can override with a limit
offset if he prefers.

## What FD0 is, in one paragraph

You suspect a flush down and press one key. The harness reads the live
chain, picks the ~0.30δ put, prices it off the book, derives the stop
distance from your remaining risk budget, renders the full ticket +
order string to the pane and the Windows clipboard, and warns if the
derived stop sits inside the noise floor. You paste and send in TOS; the
stop lives on Schwab's side, conditioned on the SPX tape itself. The
harness watches the tape only to know state: when SPX trades through
your stop condition it presumes the cut, books the estimated loss
against the budget, and waits. Reload is you pressing the key again —
there is no automated re-entry in this generation. When the budget
can't fund another attempt, it refuses to compose and says why.

## Fixed decisions (not open for the build)

| Decision | Value | Source |
|---|---|---|
| Direction | Flush-down only — long SPXW puts | Steve 08-02 |
| Risk ceiling | **$100 total realized loss**, hard | Steve 08-02 |
| Attempts | 2 | Steve 08-02 |
| Delta target | ~0.30 (band 0.25–0.35) | Steve 08-02 |
| Stop | **Derived** from remaining budget at live delta; never a fixed distance | Steve 08-02 (supersedes the 2-pt sketch: at 0.60δ that was ~3.6× the ceiling) |
| Stop home | TOS-resident, SPX-underlying conditional | Steve 08-02 |
| Reload | Manual only — cut and WAIT | Steve 08-02 |
| Execution surface | Desk only; iOS is collaboration only | Steve 08-02 |
| Size | 1 contract, full SPX | standing ruling (SPX only, no step-downs) |

## The budget engine (the heart)

```
friction_est   = spread_now + fees_rt          # live half-spread×2 + ~$3
attempt_risk   = (budget_remaining / attempts_left) − friction_est
stop_premium   = attempt_risk / 100            # $ → option points
stop_spx_pts   = stop_premium / delta_live     # via the picked strike's delta
```

- All inputs live at compose time: delta and spread from `chain.py`,
  never assumed. The ticket prints every number in this chain so the
  derivation is auditable at a glance.
- **Noise floor**: `max(spread_now/delta_live, median 1-min high-low of
  the last 15 min)`. If `stop_spx_pts < noise_floor` the ticket carries
  a loud warning line — compose is not blocked (Steve's risk authority),
  but the warning is unmissable and journaled.
- After a cut: Steve confirms the actual exit premium (or accepts the
  tape estimate); realized loss debits `budget_remaining`; attempt 2's
  stop re-derives from what's actually left.
- A compose that cannot fund `attempt_risk > 0` is refused with the
  arithmetic printed.

Illustrative at ~0.30δ, ~$15 spread, $3 fees: attempt 1 ≈ $50 − $18 =
$32 premium risk → 0.32 pts of premium → **≈ 1.1 SPX pts of stop**.
Verify against the live chain Monday; the code never uses these
illustrations.

## States and keys

```
IDLE ──s──▶ COMPOSED ──(Steve: "in <premium>")──▶ OPEN
  ▲             │ (Steve: n — didn't send)          │ tape ≥ stop condition
  │             ▼                                   ▼
  └──────── IDLE                          CUT_PRESUMED ──(Steve: "out <premium>")──▶ WAITING
                                                                                       │ s (budget permitting)
DONE ◀──x── any state                                                                  ▼
                                                                                   COMPOSED
```

Keys: `s` compose short ticket · `in <px>` confirm fill · `out <px>`
confirm cut · `n` discard ticket · `x` end session. Everything else is
display. The harness never acts on tape alone except to *presume* and
pre-compute; every ledger entry is confirmed or corrected by Steve.

## Components (all Layer-1 — no order API, no credentials)

| Piece | Home | Job |
|---|---|---|
| `strader/execution/fd0.py` | new | state machine + budget engine + ticket renderer |
| `strader/execution/compose.py` | new | strike pick (δ band), pricing, string/template-field rendering |
| feed | existing `broker_schwab/readers/{quote,chain}.py` | SPX quote ~1–2 s, chain ~5–10 s |
| clipboard | `clip.exe` | ticket fields land ready to paste |
| journal | `data/exec/fd0-<day>.jsonl` | every compose/confirm/presume/warn/refuse, with the full derivation chain |
| surface | tmux pane on steves-desk | single-key input, plain-words output |

Token note: refresh wall is 08-05 — valid Monday. `schwab_token.py`
status is printed in the go/no-go check anyway.

## Monday 08:15 go/no-go checklist (harness prints PASS/FAIL per line)

1. Schwab token status `ok` (not warn/critical)
2. SPX quote stream live and moving (three ticks, monotonic timestamps)
3. Chain readable; a 0.25–0.35δ Monday-expiry put exists with spread
   below the friction assumption
4. Order construct validated in TOS (Sunday's card) — human line, Steve
   initials it
5. Budget ledger armed: $100 / 2 attempts / $0 spent
6. Journal file writable

Any FAIL → NO-GO, per Steve's own rule. The harness renders the
checklist; Steve makes the call.

## Deliberately out of scope (gen 0)

Flush-up. Automated re-entry on level reclaim (st-ug5 keeps it). Any
API order transmission (st-5ey builds that wall first). Multi-contract
sizing. Mobile anything. GEX/internals context flags — the fourth-fire
and climax-heat gates return in the full harness, not here.

## Build plan (Sunday)

1. `compose.py` + budget engine, unit-tested against recorded chain
   fixtures (mock/ + a fresh Friday chain snapshot)
2. `fd0.py` state machine, pure-logic tests (no feed)
3. Replay smoke: 7/22 and 7/31 tapes through the watcher — presumption
   timing sane, no false CUT on the noise floor itself
4. Dry run end-to-end at the desk pane with live-ish quotes (Sunday
   futures session if available, else replay), ticket to clipboard
5. Steve's TOS validation result folded in: string mode or template mode
   becomes the default renderer

If any of 1–4 slips past Sunday, that is a NO-GO input, stated plainly
in Monday's checklist.
