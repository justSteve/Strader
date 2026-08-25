"""Deterministic tape-event detection — the accuracy tier. [st-dgwj, st-85dv]

Every threshold in EventKnobs was set by measuring the real effort-effect logs,
so the tests are written against those same measured cases rather than against
invented numbers. When a case here cites a bar, that bar is quoted from
/var/moo/logs/effort-effect/ and the figures are the ones the live scorer
actually printed.

The failures being pinned, each one an emission that went wrong for real:

  - 2026-08-24 10:41-42 — two consecutive absorption bars (effort 85/90,
    effect 6/6, d-122 and d-493, both net 0.00). A thesis event, never narrated.
  - 2026-08-24 10:20 — d-725, a climax at the 99.8th percentile of the session's
    |delta| so far, never narrated.
  - 2026-08-25 08:43 — d-676, the day's new max SELL delta, narrated as "both
    tests bought, net positive delta".
  - 2026-08-25 08:47 — effort 97, effect 7, but a LONE bar. One bar of
    absorption is a bar, not a cluster, and must not fire.
  - "biggest buy-delta of the day" answered from a running maximum that only
    ever tracked |delta| and so could only ever show a sell record.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from market.orderflow.tape_events import (  # noqa: E402
    EventKnobs, TapeEvent, TapeEventDetector, load_knobs)

DAY = datetime(2026, 8, 24)


def atom(hhmm: str, *, volume: int, delta: int, o: float = 100.0,
         h: float | None = None, l: float | None = None,  # noqa: E741
         c: float | None = None, net: float | None = None,
         rng: float | None = None):
    """A moves.Atom-shaped stand-in. The detector reads fields, never methods,
    so a namespace is a faithful double and keeps the cases readable."""
    hh, mm = hhmm.split(":")
    c = o if c is None else c
    h = max(o, c) if h is None else h
    l = min(o, c) if l is None else l  # noqa: E741
    return SimpleNamespace(
        ts=DAY.replace(hour=int(hh), minute=int(mm)),
        open=o, high=h, low=l, close=c, volume=volume, delta=delta,
        net=(c - o) if net is None else net,
        range_pts=(h - l) if rng is None else rng)


def dev(effort: float, effect: float, n: int = 500) -> dict:
    return {"effort_pct_dev": effort, "effect_pct_dev": effect, "n_atoms": n}


def feed(det: TapeEventDetector, rows) -> list[TapeEvent]:
    out = []
    for a, d in rows:
        out.extend(det.on_atom(a, d))
    return out


def warmup(det: TapeEventDetector, n: int = 120, base_delta: int = 40,
           peak_volume: int = 8752):
    """Ordinary bars, so the detector is past its small-n guards and has a
    believable |delta| distribution to rank against. Deliberately unremarkable:
    none of these should produce an event.

    The opening volume spike is part of the fixture, not decoration. On the real
    2026-08-25 tape the session's max volume was 8752 at 08:30, so the 08:43 bar
    (vol 4004) set the DELTA record and nothing else. Warming up on 800-lot bars
    would make 4004 a volume record too and quietly turn a one-event case into a
    two-event one — the fixture, not the detector, would be deciding the test."""
    rows = [(atom("06:00", volume=peak_volume, delta=base_delta), dev(50, 50, 1))]
    for i in range(1, n):
        rows.append((atom(f"06:{i % 60:02d}", volume=800 + (i % 7) * 20,
                          delta=base_delta + (i % 11) * 5), dev(50, 50, i + 1)))
    return feed(det, rows)


# ── the guards that keep an idle tape quiet ─────────────────────────────────

def test_ordinary_bars_produce_no_events():
    det = TapeEventDetector()
    assert warmup(det) == [], "a quiet tape must not wake anybody"


def test_first_bars_of_a_session_do_not_announce_records():
    """With three atoms in, every one of them sets some record. That is
    arithmetic, not news, and waking a model for it burns the budget the
    two-tier design exists to protect."""
    det = TapeEventDetector()
    events = feed(det, [(atom("06:00", volume=5000, delta=900), dev(99, 99, 1)),
                        (atom("06:01", volume=6000, delta=-950), dev(99, 99, 2))])
    assert events == []


# ── SUPERLATIVE: buy and sell are separate series ───────────────────────────

def test_new_max_sell_delta_is_named_as_a_sell():
    """2026-08-25 08:43, d-676 — narrated as 'both tests bought, net positive
    delta'. The event must say SELL in its own name."""
    det = TapeEventDetector()
    warmup(det)
    events = feed(det, [(atom("08:43", volume=4004, delta=-676,
                              o=7695.75, h=7696, l=7692, c=7693.75), dev(99, 95))])
    sup = [e for e in events if e.kind == "SUPERLATIVE"]
    assert len(sup) == 1, sup
    assert sup[0].subtype == "MAX-SELL-DELTA"
    assert ("delta", "-676") in sup[0].fields
    assert "MAX-SELL-DELTA" in sup[0].line()


def test_a_buy_record_and_a_sell_record_are_tracked_independently():
    """The scorer's existing smax ranks delta on |d|, so whichever side is
    larger hides the other entirely — which is how 'biggest buy-delta of the
    day' got answered off a line that only ever showed a sell maximum."""
    det = TapeEventDetector()
    warmup(det)
    feed(det, [(atom("08:43", volume=4004, delta=-676), dev(99, 95))])
    events = feed(det, [(atom("08:44", volume=3054, delta=+630), dev(98, 77))])
    sup = [e for e in events if e.kind == "SUPERLATIVE"]
    assert [e.subtype for e in sup] == ["MAX-BUY-DELTA"], sup
    mx = det.session_max()
    assert mx["max_sell_delta"]["value"] == -676
    assert mx["max_buy_delta"]["value"] == 630, (
        "a +630 buy record must survive alongside a larger sell record")


def test_session_max_answers_a_superlative_without_recall():
    """st-6s6x rule 1 is grep-not-recall. That is only possible if the
    instrument exposes the answer."""
    det = TapeEventDetector()
    warmup(det)
    feed(det, [(atom("10:47", volume=3000, delta=+786), dev(95, 90)),
               (atom("13:14", volume=2000, delta=+549), dev(90, 80))])
    assert det.session_max()["max_buy_delta"]["value"] == 786, (
        "13:14's +549 must not displace 10:47's +786 — the 2026-08-24 "
        "self-contradiction")


# ── ABSORPTION-CLUSTER ──────────────────────────────────────────────────────

def test_two_consecutive_absorption_bars_fire_once():
    """2026-08-24 10:41-42, the calibration case.

    THE NUMBERS HERE ARE THE UNROUNDED ONES, deliberately. The log prints these
    bars as effort 85 and 90 (the graded line formats percentiles with ".0f"),
    but the true values are 84.7 and 90.4. The first cut of this detector used a
    threshold of 85.0 taken from the printed line and silently missed the case
    it exists for, while this test — also written from the printed line — passed.
    A fixture quoting a rounded display cannot catch a threshold set against the
    same rounded display."""
    det = TapeEventDetector()
    warmup(det)
    events = feed(det, [
        (atom("10:41", volume=1796, delta=-122, o=7677, c=7677, h=7677.25, l=7676), dev(84.7, 6.3)),
        (atom("10:42", volume=2627, delta=-493, o=7677, c=7677, h=7677.25, l=7675.25), dev(90.4, 6.4)),
    ])
    clusters = [e for e in events if e.kind == "ABSORPTION-CLUSTER"]
    assert len(clusters) == 1, clusters
    assert clusters[0].subtype == "START"
    assert ("bars", "2") in clusters[0].fields
    assert ("from", "10:41") in clusters[0].fields
    assert ("delta", "-615") in clusters[0].fields, "the cluster's delta is summed"


def test_a_lone_absorption_bar_is_not_a_cluster():
    """2026-08-25 08:47: effort 97, effect 7, but the bars either side are
    effect 93 and 98. One bar of absorption is a bar."""
    det = TapeEventDetector()
    warmup(det)
    events = feed(det, [
        (atom("08:46", volume=2768, delta=+212), dev(97, 93)),
        (atom("08:47", volume=2683, delta=-91), dev(97, 7)),
        (atom("08:48", volume=2616, delta=+246), dev(96, 98)),
    ])
    assert [e for e in events if e.kind == "ABSORPTION-CLUSTER"] == []


def test_the_calibration_cluster_survives_its_own_rounding():
    """A guard on the specific trap above: a bar whose printed effort reads 85
    but whose real value is 84.7 must still fire. If someone later 'tidies' the
    threshold back to 85, this fails and says why."""
    det = TapeEventDetector()
    warmup(det)
    events = feed(det, [(atom("10:41", volume=1796, delta=-122), dev(84.7, 6.3)),
                        (atom("10:42", volume=2627, delta=-493), dev(90.4, 6.4))])
    assert [e for e in events if e.kind == "ABSORPTION-CLUSTER"], (
        "the 2026-08-24 calibration cluster must fire on its TRUE percentiles, "
        "not only on the rounded ones the log displays")


def test_a_cluster_reports_its_end_when_the_band_breaks():
    det = TapeEventDetector()
    warmup(det)
    events = feed(det, [
        (atom("10:41", volume=1796, delta=-122), dev(84.7, 6.3)),
        (atom("10:42", volume=2627, delta=-493), dev(90.4, 6.4)),
        (atom("10:43", volume=2190, delta=+46, o=7677, c=7676.25), dev(87.8, 57.0)),
    ])
    subs = [e.subtype for e in events if e.kind == "ABSORPTION-CLUSTER"]
    assert subs == ["START", "END"], subs
    end = [e for e in events if e.subtype == "END"][0]
    assert ("broken_by", "10:43") in end.fields


def test_a_longer_cluster_still_announces_only_once_at_its_start():
    """Re-announcing every bar of a five-bar cluster is four wakes for one
    event."""
    det = TapeEventDetector()
    warmup(det)
    rows = [(atom(f"10:4{i}", volume=1800, delta=-100), dev(90, 5)) for i in range(1, 6)]
    events = feed(det, rows)
    starts = [e for e in events if e.subtype == "START"]
    assert len(starts) == 1, starts


# ── CLIMAX ──────────────────────────────────────────────────────────────────

def test_climax_fires_on_a_top_percentile_delta_that_is_not_a_record():
    """2026-08-24 10:20, d-725 at the 99.8th percentile — the day's max was
    already d-1100 at 08:42, so a record-only detector misses this entirely."""
    det = TapeEventDetector()
    warmup(det, n=200, base_delta=40)
    feed(det, [(atom("08:42", volume=9000, delta=-1100), dev(99, 90))])
    events = feed(det, [(atom("10:20", volume=3135, delta=-725,
                              o=7660.75, h=7661, l=7658.25, c=7659.5), dev(94, 77))])
    climax = [e for e in events if e.kind == "CLIMAX"]
    assert len(climax) == 1, climax
    assert climax[0].subtype == "SELL"
    assert ("delta", "-725") in climax[0].fields


def test_a_new_record_reports_as_a_superlative_not_also_a_climax():
    """A new maximum is a climax by any reading; two lines for one bar is
    noise, and the record is the stronger claim."""
    det = TapeEventDetector()
    warmup(det, n=200)
    events = feed(det, [(atom("08:43", volume=4004, delta=-676), dev(99, 95))])
    kinds = sorted({e.kind for e in events})
    assert kinds == ["SUPERLATIVE"], kinds


def test_a_merely_large_delta_below_the_percentile_is_not_a_climax():
    """10:42's d-493 sits at the 99.0th percentile — large, but part of an
    absorption cluster rather than a climax. 99.5 is where the measured line
    falls between them."""
    det = TapeEventDetector()
    warmup(det, n=200, base_delta=300)   # a session where 493 is unremarkable
    events = feed(det, [(atom("10:42", volume=2627, delta=-493), dev(90, 6))])
    assert [e for e in events if e.kind == "CLIMAX"] == []


def test_climax_respects_the_absolute_floor():
    det = TapeEventDetector(knobs=EventKnobs(climax_min_abs_delta=300))
    warmup(det, n=200, base_delta=5)     # a tape where 250 would rank at 100
    events = feed(det, [(atom("10:00", volume=3000, delta=-250), dev(90, 50))])
    assert [e for e in events if e.kind == "CLIMAX"] == []


# ── PLAN-LEVEL ──────────────────────────────────────────────────────────────

LEVELS = [7692.5, 7699.75]
KINDS = {7692.5: ("support",), 7699.75: ("resistance",)}


def test_a_bar_spanning_an_anchor_reports_a_touch_once():
    det = TapeEventDetector(levels=LEVELS, kinds=KINDS)
    events = feed(det, [
        (atom("09:00", volume=900, delta=10, o=7694, c=7693, h=7695, l=7691), dev(50, 50)),
        (atom("09:01", volume=900, delta=10, o=7693, c=7693.5, h=7694, l=7692), dev(50, 50)),
    ])
    touches = [e for e in events if e.subtype == "TOUCH"]
    assert len(touches) == 1, "a continuing touch is one event, not one per bar"
    assert ("level", "7692.5") in touches[0].fields
    assert ("anchor", "support") in touches[0].fields


def test_acceptance_needs_a_crossing_not_merely_sitting_on_one_side():
    """Without this, every anchor price happens to be above announces
    acceptance on its second bar."""
    det = TapeEventDetector(levels=[7692.5], kinds=KINDS)
    events = feed(det, [(atom(f"09:{i:02d}", volume=900, delta=5,
                              o=7710, c=7711, h=7712, l=7709), dev(50, 50))
                        for i in range(6)])
    assert [e for e in events if e.subtype == "ACCEPTANCE"] == []


def test_two_closes_through_an_anchor_is_acceptance():
    det = TapeEventDetector(levels=[7699.75], kinds=KINDS)
    events = feed(det, [
        (atom("08:30", volume=900, delta=5, o=7695, c=7696, h=7697, l=7694), dev(50, 50)),
        (atom("08:34", volume=1500, delta=200, o=7698, c=7701.25, h=7701.5, l=7697), dev(60, 70)),
        (atom("08:35", volume=1400, delta=150, o=7701, c=7702, h=7702.5, l=7700.5), dev(60, 70)),
    ])
    acc = [e for e in events if e.subtype == "ACCEPTANCE"]
    assert len(acc) == 1, acc
    assert ("side", "above") in acc[0].fields
    assert ("level", "7699.75") in acc[0].fields


def test_acceptance_announces_once_per_crossing_not_every_later_bar():
    det = TapeEventDetector(levels=[7699.75], kinds=KINDS)
    rows = [(atom("08:30", volume=900, delta=5, o=7695, c=7696, h=7697, l=7694), dev(50, 50))]
    rows += [(atom(f"08:{34 + i}", volume=1400, delta=100,
                   o=7701, c=7702, h=7702.5, l=7700.5), dev(60, 70)) for i in range(5)]
    events = feed(det, rows)
    assert len([e for e in events if e.subtype == "ACCEPTANCE"]) == 1


def test_a_wick_through_that_closes_back_is_a_rejection_not_a_touch():
    det = TapeEventDetector(levels=[7699.75], kinds=KINDS)
    events = feed(det, [
        (atom("08:30", volume=900, delta=5, o=7695, c=7696, h=7697, l=7694), dev(50, 50)),
        (atom("08:31", volume=2000, delta=-300, o=7698, c=7697, h=7701.25, l=7696.5), dev(80, 60)),
    ])
    subs = [e.subtype for e in events if e.kind == "PLAN-LEVEL"]
    assert "REJECTION" in subs
    assert "TOUCH" not in subs, "a rejection already implies the touch"


def test_distant_anchors_are_not_scanned():
    det = TapeEventDetector(levels=[7000.0, 8500.0], kinds={})
    events = feed(det, [(atom("09:00", volume=900, delta=5, o=7694, c=7693), dev(50, 50))])
    assert events == []


# ── the emitted line ────────────────────────────────────────────────────────

def test_the_line_is_greppable_and_parsable():
    det = TapeEventDetector()
    warmup(det)
    events = feed(det, [(atom("08:43", volume=4004, delta=-676,
                              o=7695.75, h=7696, l=7692, c=7693.75), dev(99, 95))])
    line = events[0].line()
    assert line.startswith("08:43 CT  EVENT SUPERLATIVE MAX-SELL-DELTA")
    # How a consumer actually reads this: scan the whole line for key=value
    # tokens. Nothing should depend on how many spaces separate them.
    payload = dict(tok.split("=", 1) for tok in line.split() if "=" in tok)
    assert payload["delta"] == "-676"
    assert payload["vol"] == "4004"
    assert payload["close"] == "7693.75"


def test_every_event_line_carries_the_event_token():
    """The monitor filter keys on this token. If a class ever renders without
    it, that class silently stops waking anyone."""
    det = TapeEventDetector(levels=LEVELS, kinds=KINDS)
    warmup(det)
    events = feed(det, [
        (atom("08:43", volume=4004, delta=-676), dev(99, 95)),
        (atom("10:41", volume=1796, delta=-122), dev(85, 6)),
        (atom("10:42", volume=2627, delta=-493), dev(90, 6)),
        (atom("09:00", volume=900, delta=10, o=7694, c=7693, h=7695, l=7691), dev(50, 50)),
    ])
    assert events, "this fixture is meant to produce events"
    for e in events:
        assert " EVENT " in e.line(), e.line()


# ── knobs ───────────────────────────────────────────────────────────────────

def test_missing_config_means_measured_defaults(tmp_path):
    assert load_knobs(tmp_path / "absent.yaml") == EventKnobs()


def test_an_unknown_knob_is_loud(tmp_path):
    """A typo'd threshold that silently does nothing is the worst outcome for a
    knob whose whole purpose is to be tuned."""
    p = tmp_path / "tape_events.yaml"
    p.write_text("absorbtion_min_bars: 3\n")   # deliberate misspelling
    with pytest.raises(ValueError, match="unknown tape-event knob"):
        load_knobs(p)


def test_knobs_are_honoured(tmp_path):
    p = tmp_path / "tape_events.yaml"
    p.write_text("absorption_min_bars: 3\n")
    k = load_knobs(p)
    assert k.absorption_min_bars == 3
    det = TapeEventDetector(knobs=k)
    warmup(det)
    events = feed(det, [(atom("10:41", volume=1796, delta=-122), dev(85, 6)),
                        (atom("10:42", volume=2627, delta=-493), dev(90, 6))])
    assert [e for e in events if e.kind == "ABSORPTION-CLUSTER"] == [], (
        "two bars must not fire when the knob asks for three")


# ── causality, which is what makes replay and the cutover verifiable ────────

def test_detection_is_causal():
    """An event at minute i must depend only on minutes <= i. This is what lets
    a replay over a finished tape reproduce exactly what a live session emitted,
    which is how the mid-session cutover is verified."""
    rows = [(atom(f"07:{i:02d}", volume=800 + i, delta=(-1) ** i * (50 + i)),
             dev(50, 50, i + 1)) for i in range(50)]
    rows.append((atom("08:43", volume=9999, delta=-5000), dev(99, 99)))

    prefix = TapeEventDetector()
    prefix_events = [e.line() for e in feed(prefix, rows[:50])]

    full = TapeEventDetector()
    full_events = [e.line() for e in feed(full, rows)]

    assert full_events[:len(prefix_events)] == prefix_events, (
        "a later bar changed what earlier bars emitted")


# ── the regime gate's mechanical half [Desk amendment, 2026-08-25 ~09:55] ───

def test_superlatives_carry_minutes_since_the_rth_open():
    """Steve's amendment: "within-day superlatives early in RTH are additionally
    discounted — sixty minutes in, some bar is always the record." That is
    mechanically knowable, and st-eaa8's mechanical-first condition puts
    anything mechanically knowable in the instrument rather than in the
    analyst's memory.

    The calibration case is exactly 60 minutes: 2026-08-25 09:30 set BOTH day
    records on one 17-point bar, met every mechanical failed-breakdown criterion
    on the reclaim, and gave back nearly all of it inside a rotation."""
    det = TapeEventDetector()
    warmup(det)
    events = feed(det, [(atom("09:30", volume=14778, delta=-1240,
                              o=7680, h=7680.25, l=7663.25, c=7676.75), dev(100, 98))])
    sup = [e for e in events if e.kind == "SUPERLATIVE"]
    assert sup, "the day's record volume and sell delta must both be detected"
    for e in sup:
        assert ("rth_min", "60") in e.fields, e.fields


def test_an_overnight_record_reads_as_before_the_open():
    """A record set overnight is not an early-RTH record, and the sign says so
    rather than the reader having to work it out."""
    det = TapeEventDetector()
    warmup(det)
    events = feed(det, [(atom("02:00", volume=20000, delta=+900), dev(99, 99))])
    sup = [e for e in events if e.kind == "SUPERLATIVE"]
    assert sup
    assert ("rth_min", "-390") in sup[0].fields, sup[0].fields
