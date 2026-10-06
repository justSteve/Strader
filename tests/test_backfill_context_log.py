"""Context-log backfill [st-2rsz]."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import tools.backfill_context_log as bf


def test_tape_part_drops_only_the_history_phrase():
    live = ("long @ 7879.00 — touched 0x / defended 0x, untouched · 3 lid rejections in 40m"
            " · 22.2K sold at the level")
    back = "long @ 7879.00 — no level history · 3 lid rejections in 40m · 22.2K sold at the level"
    assert bf._tape_part(live) == bf._tape_part(back)
    assert bf._tape_part(back) != bf._tape_part(back.replace("22.2K", "22.3K"))


def test_gex_is_read_as_of_the_measured_arrival_lag():
    t1 = datetime(2026, 10, 6, 14, 38, 33, tzinfo=timezone.utc)
    bar = SimpleNamespace(end_ts=t1, close=1.0, high=2.0, low=0.5)
    a = bf._AsOf(bar, bf.GEX_ARRIVAL_LAG_S)
    assert a.end_ts == t1 - timedelta(seconds=10) and (a.close, a.high, a.low) == (1.0, 2.0, 0.5)
