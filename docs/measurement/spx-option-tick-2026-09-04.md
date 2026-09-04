# The SPX option quoting increment, measured — 2026-09-04

**Bead:** st-pohq (Tick Above Three). **Why it exists:** `execd/stops.py`
rounded every protective stop to a 0.05 tick. If SPX options quote in 0.10 at
and above $3.00, a stop derived at 3.05 is a stop the exchange refuses, under a
live position — the one state the module exists to prevent. The bead asked for
a measurement before stage 2 sends anything.

**Method.** `scripts/record_schwab_shapes.py --market-only --strikes 80`
records a live `$SPX` chain (strategy SINGLE, all contract types, today's
expiry through three days out) from Schwab's market-data API — the same
transport execd uses. `scripts/measurement/spx_option_tick.py` reads the
capture and, for every quoted bid and ask, asks whether the price sits on the
0.10 grid, only on the 0.05 grid, or on neither. The question is answered by
the counts. No rule book was consulted.

## Capture 1 — pre-open, 08:11 CT

Chain of 160 contracts (80 strikes, calls and puts, expiry 2026-09-04),
underlying 7747.71 (the prior close; the index had not printed yet).
316 quoted sides.

| band | quoted sides | on the 0.10 grid | 0.05 grid only | on neither |
|---|---|---|---|---|
| below 3.00 | 111 | 56 | 55 | 0 |
| 3.00–9.99 | 29 | 29 | 0 | 0 |
| 10.00–49.99 | 55 | 55 | 0 | 0 |
| 50.00 and up | 121 | 121 | 0 | 0 |

At or above $3.00: **205 of 205 quoted sides on the 0.10 grid, 0 needing
0.05.** Below $3.00: about half sit on odd nickels (2.65, 2.05, 1.15, 0.95,
0.45, 0.35, 0.25 …), which is the 0.05 grid in use.

## Capture 2 — regular hours, 08:32 CT

Same shape of capture two minutes after the open: 160 contracts, expiry
2026-09-04, underlying 7742.24 (live — the index had moved from the 7747.71
close), 316 quoted sides.

| band | quoted sides | on the 0.10 grid | 0.05 grid only | on neither |
|---|---|---|---|---|
| below 3.00 | 128 | 61 | 67 | 0 |
| 3.00–9.99 | 22 | 22 | 0 | 0 |
| 10.00–49.99 | 45 | 45 | 0 | 0 |
| 50.00 and up | 121 | 121 | 0 | 0 |

At or above $3.00: **188 of 188 quoted sides on the 0.10 grid, 0 needing
0.05.** Below $3.00, 67 of 128 sit on the 0.05 grid only. Two captures, 393
quoted sides at or above $3.00 between them, none off the 0.10 grid. The rule
`stops.py` assumed — 0.05 everywhere — is wrong above $3.00, and the fix below
follows the measurement.

## What changed because of it

- `execd/stops.py`: `tick_for(price)` returns 0.10 at and above $3.00 and
  0.05 below; `_round_up_to_tick` rounds up to the fine grid and, if that
  crosses $3.00, up again to the coarse one (2.96 → 3.00, 3.01 → 3.10). The
  cap one tick under the fill uses the grid in force at the fill.
- `execd/bounds.py`: a new bound, `tick`, refuses any limit or stop price off
  the grid in force at that price — entries and exits alike, because an
  off-grid stop is no stop and refusing it cannot trap anyone.
- Tests: `tests/execd/test_stops.py::TestTheTickAboveThree`,
  `tests/execd/test_bounds.py::TestTheTick`.

## What this does not settle

The 0.10 grid is measured on quotes; whether Schwab's order entry rejects an
off-grid limit or silently rounds it could not be measured, because the app
lacked the Accounts and Trading product on this date (see the st-w2nw ledger
row of 2026-09-04). Refusing off-grid prices before the send makes the
distinction moot for this service.
