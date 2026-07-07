"""Anatomy folding tests (st-yfn phase 3): the flat SetupRecognition stream
folds back into per-engagement four-beat instances, with each beat mapped to
the bar it fired on and re-engagements split into separate walkthroughs."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from market.orderflow.anatomy import BEAT_GLOSS, anatomy_payload, build_instances
from market.signals.orderflow import SetupRecognition

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 7, 2, 9, 0, 0, tzinfo=CENTRAL)

# fake bars: build_instances only needs .end_ts and positional indexing
BARS = [SimpleNamespace(end_ts=T0 + timedelta(minutes=i)) for i in range(40)]


def rec(i, beats, state, *, anchor=7510.0, kind="support",
        setup="failed_breakdown", bias="bullish", mancini=True):
    return SetupRecognition(
        timestamp=BARS[i].end_ts, source="orderflow.recognizer",
        confidence=0.8 if state == "confirmed" else 0.3,
        reason=f"{setup} {state} @ {anchor:.2f}: beats {'+'.join(beats)}",
        setup=setup, bias=bias, anchor_price=anchor, anchor_kind=kind,
        state=state, beats=tuple(beats), mancini_confluence=mancini,
    )


def _confirmed_stream():
    # one confirmed engagement at 7510: flush@10, stall@11, flip@15, confirm@20
    return [
        rec(10, ["flush"], "forming"),
        rec(11, ["flush", "stall"], "forming"),
        rec(15, ["flush", "stall", "flip"], "forming"),
        rec(20, ["flush", "stall", "flip", "confirm"], "confirmed"),
    ]


def test_confirmed_instance_maps_beats_to_bars():
    inst = build_instances(_confirmed_stream(), BARS)
    assert len(inst) == 1
    x = inst[0]
    assert x.state == "confirmed"
    assert x.setup == "failed_breakdown" and x.mancini is True
    assert [b.beat for b in x.beats] == ["flush", "stall", "flip", "confirm"]
    assert [b.bar for b in x.beats] == [10, 11, 15, 20]          # firing bar per beat
    assert x.start_bar == 10 and x.end_bar == 20
    assert x.beats[0].clock == "09:10:00"                        # bar end_ts, HH:MM:SS


def test_invalidated_instance():
    stream = [
        rec(5, ["flush"], "forming", anchor=7541.0),
        rec(6, ["flush", "flip"], "forming", anchor=7541.0),
        rec(8, ["flush", "flip"], "invalidated", anchor=7541.0),
    ]
    inst = build_instances(stream, BARS)
    assert len(inst) == 1 and inst[0].state == "invalidated"
    assert [b.bar for b in inst[0].beats] == [5, 6]              # no new beat at terminal


def test_reengagement_splits_into_two_instances():
    # same anchor engaged twice: terminal closes the first, next flush opens a new one
    stream = _confirmed_stream() + [
        rec(30, ["flush"], "forming"),
        rec(33, ["flush", "flip"], "invalidated"),
    ]
    inst = build_instances(stream, BARS)
    assert len(inst) == 2
    assert inst[0].state == "confirmed" and inst[1].state == "invalidated"
    assert inst[0].start_bar == 10 and inst[1].start_bar == 30  # sorted by start bar


def test_payload_ranks_confirmed_first_and_carries_gloss():
    stream = [
        rec(5, ["flush"], "forming", anchor=7541.0),
        rec(8, ["flush", "flip"], "invalidated", anchor=7541.0),
    ] + _confirmed_stream()
    payload = anatomy_payload(build_instances(stream, BARS))
    assert payload[0]["state"] == "confirmed"                   # confirmed leads
    assert payload[0]["beats"][0]["gloss"] == BEAT_GLOSS["flush"]
    assert payload[0]["beats"][0]["clock"] == "09:10:00"


def test_payload_top_cap():
    streams = []
    for k in range(6):
        a = 7000.0 + k
        streams += [rec(2 * k, ["flush"], "forming", anchor=a),
                    rec(2 * k + 1, ["flush", "flip"], "invalidated", anchor=a)]
    assert len(anatomy_payload(build_instances(streams, BARS), top=3)) == 3
