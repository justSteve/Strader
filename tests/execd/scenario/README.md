# execd scenario harness [st-ug1h]

Steve, 2026-09-30: *"There is a CLI backing the GUI form, right? Seems like
tests should have caught these bugs and edge cases."* Four bugs reached his
paper account that day with ~1330 execd tests green. The tests ran against
`MockBroker`, whose stops never fire on their own; the broker that does fill
stops against live quotes — `PaperBroker` — was never run under the service;
every scenario was one hand-set price; and nothing drove the order form from
pricing to SEND and compared what the service received with the screen.

This directory is the answer: **the real `ExecService` over the real
`PaperBroker`, wired as `execd/__main__.py` wires it in paper mode, on a
replayed market, with every invariant checked after every step.**

## Run it

```bash
python3 -m pytest tests/execd/scenario -q            # fast: ~10 s, part of tests/execd
python3 -m pytest tests/execd/scenario -q --scenario-wide   # wide: ~6 min
python3 -m pytest 'tests/execd/scenario/test_generated.py::test_a_generated_session[17]'
```

`--scenario-wide` (or `EXECD_SCENARIO_WIDE=1` in the environment) widens the
generated sessions from 12 seeds × 200 frames to 200 seeds × 600 frames with
resting dip-buy entries, and runs the whole recorded half hour. State lives in
`/dev/shm` when the machine has it: the journal `fsync`s every line, which on
this box's disk was 70 % of a session's time.

A failure prints the invariant's name, the numbers that broke it, and the
whole sequence so far — CT-stamped, with SPX, the contract's quote, what the
step did and the journal lines it wrote. The same seed reproduces it exactly.

## The pieces

| file | what |
|---|---|
| `tape.py` | `Tape` = index path + `OptionModel` (Black-Scholes on the 0DTE clock, quotes on the exchange grid). `random_walk(seed, …)` (gaps, stale stretches, wide frames), `scripted` / `ramp` (hand paths; frames may pin exact quotes, deltas, and the chain's own SPX), `recorded()` |
| `fixtures/recorded_2026-09-30.json` | 13:15–13:45 CT 2026-09-30: SPX per second from the Databento ES tape less one Schwab basis, and the 18:00 UTC Schwab chain (IV, spreads). Built by `fixtures/build_recorded.py` |
| `market.py` | `ReplayMarket` — the transport the paper book wraps: quotes, Schwab-shaped chains, preview, balances from the tape at the clock's moment; refuses all four trading calls (`LiveSideTraded`) |
| `harness.py` | `Scenario` — the wiring, the clock, the `Watcher` one pass at a time, the steps (`tick`, `send`, `adjust`, `cancel`, `exit`, `flatten`, `lock`, `unlock`, `restart`), the page on demand |
| `invariants.py` | `check()` — every invariant, named, after every step |
| `screen.py` | `OrderScreen` — the order page driven as its script drives it: side, strike tap, steppers, close-at box, padlock, SEND, the poll |
| `faults.py` | `FaultBook` — the paper book plus the broker behaviours it does not model (lost answers, acknowledged-only cancels, two-print fills, partial entries, a failing child read, an outside fill). Knobs off, it is `PaperBroker` exactly |
| `known_bugs.py` | the open defects the scenarios pin; waivers must cite one |
| `against.py` | run this suite against `execd/` as it was at any commit |

## The invariants (checked after every step)

`short_position` · `oversold_journaled` · `two_stops` / `two_targets` ·
`bracket_not_linked` · `resting_sell_exceeds_held` /
`resting_sell_without_position` · `stop_not_below_bid_when_placed` /
`target_not_above_bid_when_placed` (a triggered child judged at its entry's
SEND) · `open_mismatch` (service `_open` vs the book, once a reconcile has
run) · `closed_kind_unknown` · `external_close_of_own_order` · `pnl_mismatch`
(closed/filled lines vs the book's fills, P&L arithmetic) ·
`stop_level_crossed_at_fill` · `false_short_alarm` · `trail_moved_down` ·
`trail_locked_a_loss` · `stop_dollars_off_ticket` (a dollar stop rests that
far from the FILL, within one tick). Details in `invariants.py`'s docstring;
`test_harness.py` shows each one firing on the state it names.

## The scenarios

* `test_sequences.py` — entries (unlocked at the ask, padlocked under it,
  the ask followed), fills against the stop sent with them (at the limit,
  a little better, much better, a spread wider than the stop, SPX moving
  before the send), the bracket (stop fires, target fires first, FLATTEN,
  two lots and a partial exit, an add), a cancel racing a fill, Steve's
  adjusts (dollars and SPX levels, both legs, a refused one), LOCK with a
  position open, restarts (with a position, with a working entry), the
  trailing stop up its tiers and the reversal, the SPX-mark exit loop.
* `test_seed_0930.py` — the four 09-30 bugs, each failing before its fix
  and passing now (below).
* `test_page_flow.py` — the screen: what SEND posts equals what the ticket
  showed (strike, lots, limit, stop price or level), across steppers, the
  close-at box, the padlock and a market that moved between paint and tap;
  then the card, the caption, the closed cards and the day's total against
  the service through fills and closes.
* `test_generated.py` — seeded sessions on seeded tapes (entries, adjusts,
  FLATTEN, restarts), every invariant every step.
* `test_recorded.py` — the 09-30 half hour, entries at 13:24 and 13:38.
* `test_audit_defects.py` — the 2026-10-01 audit's D1–D15, strict xfails.

## Open defects, xfail, and waivers

`known_bugs.py` lists every open defect a scenario pins — D1–D15 from the
audit, H1–H4 found by the harness — each with the invariant it breaks and
the test that pins it as `xfail(strict=True)`. When a defect is fixed its
test passes, the strict xfail turns red, and the fix's commit deletes the
marker and the entry together. A scenario that must run past an open defect
to test something else may `waive={"<invariant>": "<key>"}`; a key that is
not open, or that names a different invariant, is refused.

## The 09-30 seed cases against the code before each fix

```bash
python3 tests/execd/scenario/against.py 5ad0386^ tests/execd/scenario/test_seed_0930.py   # seeds 1, 2 fail
python3 tests/execd/scenario/against.py 87ced9c^ tests/execd/scenario/test_seed_0930.py   # seed 3 fails (11.60)
python3 tests/execd/scenario/against.py 13e43dd^ tests/execd/scenario/test_seed_0930.py   # seed 4 fails
```

`against.py` `git archive`s `execd/` and `tests/execd/` at the commit into a
temporary directory, lays this suite over it, and runs pytest there.

## What it does not model

* **The paper book has no clock.** A resting order fills when something
  reads the book (a reconcile, a cancel, the children read), at that
  moment's quote — as in production paper mode. While LOCKED nothing reads,
  so a stop the market crossed fills at the first read after the unlock.
* **Option prices are a model** — Black-Scholes on one IV (generated) or on
  the recorded chain's IV per strike (recorded); the index path is real in
  the recorded tape, the option quotes are derived.
* Fills are whole and in one print unless a scenario asks `FaultBook` for
  otherwise. Alpaca's venues are not covered (paper here is Schwab's
  `PaperBroker`). The page's JavaScript is not executed; the script's own
  behaviour is pinned in `test_order_screen.py` and the headless-Chromium
  passes, and `OrderScreen` posts what that script posts.
