# COO → Strader — live breadth wired into the gauge, and the read is now persisted

**2026-08-14 · st-9573, architecture step 0 · COO committed into this repo under
the co-qliwo standing authority**

Announcing per the second gate of that authority. One file changed in your
tree (`scripts/mi_gauge.py`), plus one new test file. Nothing else touched, no
force-push, no branch switch, and I did not restart your running daemon.

---

## Why COO did this rather than you

Steve directed it this afternoon after reading the watcher/sentinel architecture
doc and telling me live $ADD had been solved yesterday. You had explicitly
declined MI-Gauge work today to stay on his tape, so it fell to COO. If you'd
rather own it, say so and I'll stay out of `mi_gauge.py` in future.

## What was wrong, and it was your finding

Your 2026-08-13 19:49 session had it: **`$ADD` and `$VOLD` are not feeds, they
are spreads.** `$ADD = $ADVN − $DECN`, `$VOLD = $UVOL − $DVOL`, and thinkorswim
computes those differences on its own platform. Schwab *registers* the spread
symbols and describes them correctly, then serves 0.0 intraday — which is
exactly how they came to be written off.

Re-verified live, 2026-08-14 12:04 CT, with the control:

```
$TICK   -53.0
$ADVN  1396.0     $DECN  1311.0      ->  $ADD  +85
$UVOL    6.81B    $DVOL    2.53B     ->  $VOLD +4.28B

direct request for the spreads:  {'$ADD': 0.0, '$VOLD': 0.0}
```

The control matters more than the computation: it reproduces the exact
observation that produced the wrong conclusion, so nobody re-derives it.

## What changed in `mi_gauge.py`

**1. The poll set.** `get_quotes(["$TICK"])` → `get_quotes(POLL_SYMBOLS)` with
the four components. Same call, same 5-second cadence, no new loop and no new
entitlement. `POLL_SYMBOLS` carries a comment saying never to re-add `$ADD`
expecting a value.

**2. `quote_prices()` and `breadth()`** — small pure functions. `breadth()`
**omits** a pair whose leg is missing rather than emitting 0: "zero advancers"
is a real and catastrophic market state, "the quote didn't arrive" is a Tuesday,
and a downstream 10-minute slope cannot tell them apart.

**3. The scored read is now persisted** — architecture step 0. The gauge was
computing `score/band/driver/instant/cum/cum_tick` every minute and discarding
them at the pane, so any consumer wanting band transitions as event triggers had
to recompute them and would silently disagree with what Steve actually saw. They
now ride in the capture record alongside the breadth values.

**4. The pane shows `ADD +85  VOLD +4.28B`** when breadth is available, nothing
when it isn't. That changes what Steve sees on the next restart — flagging it
rather than letting it surprise you.

## The part I was most careful about

`append_capture` gained an optional `extra` dict, and it is **strictly
additive**: keys colliding with `ts/high/low/close` are dropped, because
corrupting those silently rewrites the cumulative spine on the next restore.
`restore_state()` reads only those four and ignores the rest, so extras are
invisible to the spine rebuild.

That is asserted by round-trip rather than by reading the code — a file written
with extras restores to an identical `cum_tick`, `minutes` and last-ts as one
written without, and an old extras-free file still restores. This is what makes
it safe to land under a daemon that is already appending to that file.

`tests/scripts/test_mi_gauge_breadth.py`, 13 tests. Your existing 27 gauge tests
pass unchanged; full `pytest tests/` green.

## Two things left for you

**Your daemon is running pre-change code.** pid 2669614 loaded `mi_gauge.py` at
launch, so today's capture has no breadth and no persisted read. I did not
restart it — Steve is in a live position and killing his gauge mid-session is
his call, not mine. It self-heals at the pre-open cron tomorrow.

**`st-9573`'s title carried the superseded conclusion** ("$ADD/$VOLD are not
served intraday on either Schwab surface") and had not been updated since 08-12,
so the ready queue was advertising a capability gap that does not exist. I
annotated it with the finding and retitled it. Push back if you'd rather own the
wording.

## One consumer this unblocks that neither of us mentioned

The 2026-08-04 Auditor report (`docs/audits/`) found that residualising the
continuation traces on the concurrent 5-minute ES move leaves **`add_slope10`
as the only trace with genuine residual signal** (day-median .598), while the
live meter runs on the two that fail the test and drops the one that passes —
because "$ADD publishes a session late." That premise is now false.

I am **not** acting on that. The counter-dictum programme is TABLED per Steve
(8/10) and inferences from it do not apply to work product. Recording it because
the constraint that justified dropping the trace is gone, and that is worth
knowing whenever the programme is untabled.

— COO
