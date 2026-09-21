"""Absorption rate survey (co-qp8cn) — the one-pass method and the day summary.

The survey lowers the tracker's two emission floors once, collects every
episode, and reads the production count off that population. That is only
honest if filtering afterwards gives exactly what the tracker emits when run
verbatim at production floors — pinned here on a synthetic stream that mixes
episodes above and below each floor, and on the committed 2026-07-02 fixture.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import market.orderflow.absorption as absorption
from market.entities.book import BookEvent
from market.orderflow.absorption import AbsorptionTracker
from market.orderflow.quotes import read_mbp1_day
from market.signals import orderflow_config as cfg
from scripts.measurement import absorption_rate_survey as survey

CENTRAL = ZoneInfo("America/Chicago")
MBP1_FIXTURE = (Path(__file__).parent.parent / "market" / "fixtures"
                / "es_mbp1_golden_20260702.jsonl.gz")


def ev(ts, action="M", side="N", price=None, size=None, bid=(7500.0, 100), ask=(7500.25, 100)):
    return BookEvent(ts=ts, symbol="ESZ6", instrument_id=1, action=action, side=side,
                     price=price, size=size, bid_px=bid[0], bid_sz=bid[1],
                     ask_px=ask[0], ask_sz=ask[1])


def defended_bid(t0, price, refills, vol_each):
    """Sellers hit the bid `refills+1` times, size refills `refills` times, then
    the bid lifts beyond the band and the episode closes."""
    out, t = [ev(t0, bid=(price, 100), ask=(price + 0.25, 100))], t0
    for i in range(refills + 1):
        t += timedelta(milliseconds=10)
        out.append(ev(t, action="T", side="A", price=price, size=vol_each,
                      bid=(price, 20), ask=(price + 0.25, 100)))
        if i < refills:
            t += timedelta(milliseconds=10)
            out.append(ev(t, bid=(price, 100), ask=(price + 0.25, 100)))
    t += timedelta(milliseconds=10)
    out.append(ev(t, bid=(price + 5.0, 60), ask=(price + 5.25, 80)))
    return out


def mixed_stream():
    """Four bid defenses: passes both floors, under the volume floor, under the
    refill floor, and a large one inside the last ten minutes of RTH."""
    v, k = cfg.ABSORPTION_VOL_MIN, cfg.ABSORPTION_REFILL_MIN
    day = datetime(2026, 9, 10, tzinfo=CENTRAL)
    return (
        defended_bid(day.replace(hour=9, minute=5), 7500.0, refills=k, vol_each=v)
        + defended_bid(day.replace(hour=10, minute=5), 7520.0, refills=k, vol_each=v // (k + 2))
        + defended_bid(day.replace(hour=11, minute=5), 7540.0, refills=k - 1, vol_each=v)
        + defended_bid(day.replace(hour=14, minute=55), 7560.0, refills=k + 2, vol_each=v * 3)
    )


def key(r):
    return (r.timestamp, r.side, r.price, r.aggressive_vol, r.refill_events,
            r.displacement_ticks)


def test_filtering_collected_episodes_equals_a_verbatim_production_run():
    stream = mixed_stream()
    verbatim = AbsorptionTracker().run(stream)
    episodes, _ = survey.collect_episodes([("s0", stream)])
    prod = survey.at_floors(episodes, survey.PROD_VOL_MIN, survey.PROD_REFILL_MIN)
    assert len(verbatim) == 2
    assert len(episodes) > len(prod)   # the lowered floors did surface the sub-floor ones
    assert [key(r) for r, _ in prod] == [key(r) for r in verbatim]


def test_same_equivalence_on_the_committed_fixture():
    verbatim = AbsorptionTracker().run(read_mbp1_day(MBP1_FIXTURE))
    episodes, facts = survey.collect_episodes([("fixture", read_mbp1_day(MBP1_FIXTURE))])
    prod = survey.at_floors(episodes, survey.PROD_VOL_MIN, survey.PROD_REFILL_MIN)
    assert [key(r) for r, _ in prod] == [key(r) for r in verbatim]
    assert facts["book_events"] > 0 and facts["trade_events"] > 0


def test_a_segment_that_breaks_part_way_keeps_its_events_and_is_named():
    whole = mixed_stream()
    cut = len(defended_bid(whole[0].ts, 7500.0, cfg.ABSORPTION_REFILL_MIN,
                           cfg.ABSORPTION_VOL_MIN))   # the first, passing, defense

    def broken():
        yield from whole[:cut]
        raise RuntimeError("impossible record length")

    episodes, facts = survey.collect_episodes([("seg.3", broken()), ("seg.4", whole[cut:])])
    assert facts["book_events"] == len(whole)
    (bad,) = facts["unreadable"]
    assert (bad["segment"], bad["events_before"]) == ("seg.3", cut)
    assert "impossible record length" in bad["error"]
    assert len(survey.at_floors(episodes, survey.PROD_VOL_MIN, survey.PROD_REFILL_MIN)) == 2
    assert absorption.ABSORPTION_VOL_MIN == cfg.ABSORPTION_VOL_MIN
    assert absorption.ABSORPTION_REFILL_MIN == cfg.ABSORPTION_REFILL_MIN


def test_tracker_restarts_per_segment_and_marks_flush_closed_reads():
    v, k = cfg.ABSORPTION_VOL_MIN, cfg.ABSORPTION_REFILL_MIN
    t0 = datetime(2026, 9, 10, 9, 5, tzinfo=CENTRAL)
    open_at_end = defended_bid(t0, 7500.0, refills=k, vol_each=v)[:-1]   # never closes
    next_segment = [ev(t0 + timedelta(minutes=1), bid=(7400.0, 50), ask=(7400.25, 50))]
    episodes, _ = survey.collect_episodes([("s0", open_at_end), ("s1", next_segment)])
    (read, flushed), = survey.at_floors(episodes, v, k)
    assert flushed is True
    assert read.displacement_ticks == 0   # closed by end of segment, not by the 100-point gap


def test_a_segment_that_starts_before_the_last_one_ended_is_flagged():
    stream = mixed_stream()
    _, clean = survey.collect_episodes([("s0", stream[:5]), ("s1", stream[5:])])
    _, doubled = survey.collect_episodes([("s0", stream), ("s1", stream)])
    assert clean["overlapping"] == []
    (hit,) = doubled["overlapping"]
    assert hit["segment"] == "s1" and hit["starts"] < hit["previous_ended"]


def test_only_an_overlap_inside_rth_taints_the_rth_count():
    night = {"starts": "2026-08-28T03:31:05-05:00", "previous_ended": "2026-08-28T03:48:43-05:00"}
    midday = {"starts": "2026-08-28T11:59:00-05:00", "previous_ended": "2026-08-28T12:04:00-05:00"}
    assert survey.overlap_reaches_rth([night]) is False
    assert survey.overlap_reaches_rth([night, midday]) is True


def test_summary_counts_rth_hours_and_the_last_ten_minutes():
    episodes, facts = survey.collect_episodes([("s0", mixed_stream())])
    row = survey.summarize(date(2026, 9, 10), [Path("seg0")], episodes, facts)
    assert row["reads_rth"] == 2 and row["reads_all"] == 2
    assert row["reads_rth_last_ten_min"] == 1
    assert row["reads_by_hour_ct"] == {"09": 1, "14": 1}
    assert row["reads_rth_bid"] == 2 and row["reads_rth_broke"] == 0
    assert row["rth_grid"][str(cfg.ABSORPTION_VOL_MIN)][str(cfg.ABSORPTION_REFILL_MIN)] == 2
    assert row["rth_grid_before_1450"][str(cfg.ABSORPTION_VOL_MIN)][str(cfg.ABSORPTION_REFILL_MIN)] == 1
    assert row["floors"]["vol_min"] == cfg.ABSORPTION_VOL_MIN
    assert row["trade_volume"] == facts["trade_volume"] > 0


def test_a_day_with_nothing_recorded_reports_an_error_row(monkeypatch):
    monkeypatch.setattr(survey, "mbp1_raw_segments", lambda day: [])
    monkeypatch.setattr(survey, "day_file", lambda day: None)
    assert survey.survey_day("2026-09-19") == {
        "date": "2026-09-19", "error": "no raw MBP-1 segments and no day file"}


def test_a_batch_filled_day_is_surveyed_from_its_day_file(monkeypatch):
    monkeypatch.setattr(survey, "mbp1_raw_segments", lambda day: [])
    monkeypatch.setattr(survey, "day_file", lambda day: MBP1_FIXTURE)
    row = survey.survey_day("2026-07-02")
    assert row["source"] == "jsonl" and row["trade_events"] > 0 and "error" not in row


def test_a_day_file_without_trade_rows_is_an_error_not_a_zero(monkeypatch, tmp_path):
    quotes_only = tmp_path / "databento_glbx_es_mbp1.jsonl"
    quotes_only.write_text(json.dumps({
        "provenance": {"ts_event": "2026-09-18T14:00:00+00:00"},
        "data": {"symbol": "ESZ6", "instrument_id": 1, "action": None, "side": None,
                 "price": None, "size": None, "bid_px": 7700.0, "ask_px": 7700.25,
                 "bid_sz": 5, "ask_sz": 5}}) + "\n")
    monkeypatch.setattr(survey, "mbp1_raw_segments", lambda day: [])
    monkeypatch.setattr(survey, "day_file", lambda day: quotes_only)
    assert survey.survey_day("2026-09-18") == {
        "date": "2026-09-18",
        "error": "no raw segments, and the day file carries no trade rows"}


def test_rows_merge_by_date_and_a_rerun_replaces_the_day(tmp_path):
    out = tmp_path / "survey.jsonl"
    survey.write_rows(out, [{"date": "2026-09-02", "reads_rth": 1},
                            {"date": "2026-09-01", "reads_rth": 5}])
    survey.write_rows(out, [{"date": "2026-09-02", "reads_rth": 9}])
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows == [{"date": "2026-09-01", "reads_rth": 5},
                    {"date": "2026-09-02", "reads_rth": 9}]
