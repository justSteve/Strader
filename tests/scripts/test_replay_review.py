"""Review-payload merge tests. [st-055]"""
from scripts.replay_review import review_payload

ROWS = [
    {"type": "RunMeta", "run": "r2", "n": 0, "date": "2026-07-13",
     "n_trades": 1000, "n_bars": 12, "bar_n": 2000},
    {"type": "DayType", "run": "r2", "n": 1, "day_type": "trend", "why": "one-timeframing"},
    {"type": "SweepPrint", "run": "r2", "n": 2, "bar_i": 3},
    {"type": "SetupRecognition", "run": "r2", "n": 3, "bar_i": 5,
     "setup": "failed_breakdown", "bias": "bullish", "anchor_price": 6212.0,
     "state": "forming", "beats": ["flush"], "timestamp": "2026-07-13T09:12:04-05:00"},
    {"type": "SetupRecognition", "run": "r2", "n": 4, "bar_i": 7,
     "setup": "failed_breakdown", "bias": "bullish", "anchor_price": 6212.0,
     "state": "confirmed", "beats": ["flush", "stall", "flip", "confirm"],
     "timestamp": "2026-07-13T09:31:40-05:00"},
]
ANNS = [{"type": "Annotation", "date": "2026-07-13", "time_ct": "09:14",
         "bar_i": None, "text": "the real one"}]


def test_review_payload_splits_and_counts():
    p = review_payload(ROWS, ANNS)
    assert p["meta"]["run"] == "r2"
    assert p["day_type"]["day_type"] == "trend"
    assert p["counts"] == {"SweepPrint": 1, "SetupRecognition": 2}
    assert len(p["recognitions"]) == 2
    assert len(p["confirmed"]) == 1 and p["confirmed"][0]["state"] == "confirmed"
    assert p["annotations"] == ANNS


def test_review_payload_empty_inputs():
    p = review_payload([], [])
    assert p["meta"] == {} and p["counts"] == {} and p["confirmed"] == []
