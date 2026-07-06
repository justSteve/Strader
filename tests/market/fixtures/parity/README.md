# Orderflow parity harness — interpreting a failure

`test_parity_harness.py` replays the committed fixture
(`es_ticks_golden_20260702.jsonl`, a real 7/2 slice with duplicates and
disorder) through the ENTIRE orderflow stack — reader → volume bars → engine
(CVD/sweeps/large-lots/divergence) → imbalances → recognizer → profile — and
compares every emitted event, field by field, against
`expected_signals_20260702.json`.

## The test failed. What now?

The assertion names the **first divergent event index** and shows expected vs
actual. Three cases:

1. **You didn't intend to change engine behavior.** You broke determinism or
   a computation. The diff tells you which signal type and field moved —
   fix the code, not the snapshot. Classic culprits: wall-clock or dict-order
   leakage, a changed tie-break, an implicit threshold.
2. **You intended the change** (new threshold, new beat rule, new signal
   field). Regenerate deliberately:
   `.venv/bin/python scripts/regen_parity_snapshot.py --reason "<why>"`
   and commit the snapshot, the CHANGES.md entry, and your code change as
   one reviewable commit.
3. **Only ordering moved** (same events, new sequence). Treat as case 1
   unless you changed the documented ordering rules in
   `market/orderflow/parity.py` — those rules are part of the contract.

## Why thresholds look small here

The fixture is a ~1,600-tick slice; production floors (100-contract, sized
for institutional prints on a full session) would produce a near-empty
snapshot. `PARITY_OVERRIDES` in `market/orderflow/parity.py` scales floors to
fixture size. Those overrides are part of the harness definition — changing
them is a regeneration event like any other.

## Live parity

The same `parity_run` consumes any trade list. When Phase B live capture
lands (st-d5f), a captured live hour teed to DBN replays through this
pipeline and must reproduce the signals logged during the live run — that
comparison closes the live==replay loop end-to-end.
