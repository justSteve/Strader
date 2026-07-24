"""mi_gauge live-capture / state-restore tests (st-cm5).

Proves the 'recreate state' contract without any Schwab call: because the gauge
is a deterministic pure function of its tick stream, capturing the fed minutes
and replaying them reconstructs the exact spine. This is what makes a
mid-session respawn continue instead of resetting to cum=0.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from mi_gauge import (  # noqa: E402
    append_capture,
    default_capture_path,
    restore_state,
)

from market.internals.gauge import MIGauge, TickMinute  # noqa: E402

CENTRAL = ZoneInfo("America/Chicago")
DAY = datetime(2026, 7, 23, tzinfo=CENTRAL).date()


def tm(hh, mm, high, low, close):
    return TickMinute(ts=datetime(2026, 7, 23, hh, mm, tzinfo=CENTRAL),
                      high=high, low=low, close=close)


# A one-sided afternoon down-leg then a partial recovery — the shape of a real
# trend-day spine, so cum_tick is meaningfully non-zero.
STREAM = (
    [tm(13, i, 120 - 4 * i, -300 - 8 * i, close=-160 - 5 * i) for i in range(20)]
    + [tm(13, 20 + i, 200, -40, close=90) for i in range(10)]
)


def _capture_stream(path, stream):
    """Feed a stream through a live-like gauge, capturing each minute — mirrors
    what live() does via commit_minute (process + append_capture)."""
    g = MIGauge()
    for m in stream:
        g.process(m)
        append_capture(path, m)
    return g


def test_restore_reconstructs_exact_spine(tmp_path):
    cap = tmp_path / "mi_gauge_live.jsonl"
    live_gauge = _capture_stream(cap, STREAM)

    # Fresh process comes up and restores from the capture file.
    restored = MIGauge()
    last_ts = restore_state(cap, restored, DAY, echo=False)

    assert last_ts == STREAM[-1].ts
    assert restored.cum_tick == live_gauge.cum_tick
    assert restored.minutes == live_gauge.minutes
    # The out-of-order guard is armed at the right point for live to continue.
    assert restored._last_ts == STREAM[-1].ts


def test_restored_gauge_continues_identically(tmp_path):
    """A restore + one more minute must equal a gauge that never died."""
    cap = tmp_path / "mi_gauge_live.jsonl"
    _capture_stream(cap, STREAM)
    next_min = tm(13, 30, 260, -30, close=150)

    restored = MIGauge()
    restore_state(cap, restored, DAY, echo=False)
    r_restored = restored.process(next_min)

    never_died = MIGauge()
    for m in STREAM:
        never_died.process(m)
    r_never = never_died.process(next_min)

    assert r_restored == r_never
    assert r_restored.cum_tick == r_never.cum_tick


def test_truncated_final_line_tolerated(tmp_path):
    """A kill mid-write can only corrupt the last line; restore must survive it
    and recover every whole minute before it."""
    cap = tmp_path / "mi_gauge_live.jsonl"
    full = _capture_stream(cap, STREAM)

    text = cap.read_text()
    # Chop the final newline + half the last record to simulate a torn write.
    torn = text[: -(len(text.splitlines()[-1]) // 2)]
    cap.write_text(torn)

    restored = MIGauge()
    restore_state(cap, restored, DAY, echo=False)
    # Lost only the final minute; everything before it is intact.
    assert restored.minutes == full.minutes - 1
    assert restored._last_ts == STREAM[-2].ts


def test_records_from_other_day_skipped(tmp_path):
    """A capture path reused across days must not fold yesterday into today."""
    cap = tmp_path / "mi_gauge_live.jsonl"
    with cap.open("a") as fh:
        fh.write(json.dumps({"ts": datetime(2026, 7, 22, 13, 0,
                 tzinfo=CENTRAL).isoformat(), "high": 500,
                 "low": -500, "close": 400}) + "\n")
    for m in STREAM:
        append_capture(cap, m)

    restored = MIGauge()
    restore_state(cap, restored, DAY, echo=False)
    today_only = MIGauge()
    for m in STREAM:
        today_only.process(m)
    assert restored.cum_tick == today_only.cum_tick  # 400 not folded in


def test_missing_file_is_clean_noop(tmp_path):
    restored = MIGauge()
    assert restore_state(tmp_path / "nope.jsonl", restored, DAY, echo=False) is None
    assert restored.cum_tick == 0 and restored.minutes == 0


def test_default_capture_path_shape():
    p = default_capture_path(DAY)
    assert p.parts[-3:] == ("corpus", "2026-07-23", "mi_gauge_live.jsonl")
