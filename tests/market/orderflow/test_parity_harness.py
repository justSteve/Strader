"""Full-stack parity harness (st-bw9, spec §5).

Replays the committed fixture through the entire orderflow pipeline and
diffs every event against the committed snapshot. On failure, read
tests/market/fixtures/parity/README.md before touching anything.
"""
import json
import time
from pathlib import Path

from market.orderflow.parity import parity_run
from market.orderflow.replay import read_corpus_day

FIXTURES = Path(__file__).parent.parent / "fixtures"
FIXTURE = FIXTURES / "es_ticks_golden_20260702.jsonl"
SNAPSHOT = FIXTURES / "parity" / "expected_signals_20260702.json"


def test_full_stack_parity():
    t0 = time.monotonic()
    actual = parity_run(read_corpus_day(FIXTURE))
    elapsed = time.monotonic() - t0

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert len(actual) > 0, "parity run produced no events — pipeline is broken"

    for i, (e, a) in enumerate(zip(expected, actual)):
        assert e == a, (
            f"parity diverges at event {i}/{len(expected)}:\n"
            f"  expected: {e}\n  actual:   {a}\n"
            "See tests/market/fixtures/parity/README.md — fix the code if this "
            "was unintended, or regen via scripts/regen_parity_snapshot.py."
        )
    assert len(actual) == len(expected), (
        f"event count changed: expected {len(expected)}, got {len(actual)} "
        f"(first extra/missing at index {min(len(expected), len(actual))})"
    )
    # AC-3: CI-friendly runtime, generous margin over the observed ~<1s
    assert elapsed < 120, f"parity run took {elapsed:.1f}s — over CI budget"


def test_parity_run_is_deterministic():
    trades = read_corpus_day(FIXTURE)
    assert parity_run(trades) == parity_run(trades)
