"""impact_by_interval and absorption_impact_survey (co-qp8cn): the OFI step,
the binning, the slope, and the survey's grid and forward rule. Synthetic."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from market.entities.book import BookEvent
from market.entities.trade import Trade
from scripts.measurement import absorption_impact_survey as survey
from scripts.measurement import impact_by_interval as ibi

CENTRAL = ZoneInfo("America/Chicago")
T0 = datetime(2026, 9, 10, 10, 0, 0, tzinfo=CENTRAL)


def ev(t, action="M", side="N", price=None, size=None, bid=(7500.0, 40), ask=(7500.25, 40)):
    return BookEvent(ts=t, symbol="ESZ6", instrument_id=1, action=action, side=side,
                     price=price, size=size, bid_px=bid[0], bid_sz=bid[1],
                     ask_px=ask[0], ask_sz=ask[1])


def test_ofi_step_follows_cont_kukanov_stoikov():
    # bid size grows at the same price: +Δ on the bid side
    assert ibi.ofi_step((7500.0, 7500.25, 40, 40), (7500.0, 7500.25, 55, 40)) == 55 - 40
    # ask size grows at the same price: −Δ
    assert ibi.ofi_step((7500.0, 7500.25, 40, 40), (7500.0, 7500.25, 40, 70)) == -(70 - 40)
    # bid steps up: the new bid size counts in full, the old is not subtracted
    assert ibi.ofi_step((7500.0, 7500.25, 40, 40), (7500.25, 7500.5, 12, 40)) == 12 + 40
    # bid steps down: the old bid size is lost in full
    assert ibi.ofi_step((7500.0, 7500.25, 40, 40), (7499.75, 7500.0, 30, 40)) == -40 - 40


def test_bins_and_slope_recover_a_known_rate():
    events, px = [], 7500.0
    for i in range(12):                                  # 12 bins of 10 s, 2 minutes
        t = T0 + timedelta(seconds=10 * i)
        events.append(ev(t, bid=(px, 40), ask=(px + 0.25, 40)))
        events.append(ev(t + timedelta(seconds=3), action="T", side="B", price=px + 0.25,
                         size=100, bid=(px, 40), ask=(px + 0.25, 40)))
        px += 0.5                                        # 2 ticks per 100 contracts
        events.append(ev(t + timedelta(seconds=6), bid=(px, 40), ask=(px + 0.25, 40)))
    bins = ibi.bins_for_day(events)
    assert len(bins) == 12 and all(b["ti"] == 100 for b in bins)
    assert [b["dp_ticks"] for b in bins] == [2] * 12
    b, r2 = ibi.slope_through_origin([b["ti"] for b in bins], [b["dp_ticks"] for b in bins])
    assert abs(b - 0.02) < 1e-9 and abs(r2 - 1.0) < 1e-9
    (row,) = ibi.intervals_for_day("2026-09-10", bins)
    assert row["interval"] == "10:00" and row["bins"] == 12 and row["volume"] == 1200
    assert abs(row["beta_ti_ticks_per_contract"] - 0.02) < 1e-6 and row["avg_depth"] == 40.0


def test_bins_ignore_events_outside_rth():
    early = ev(T0.replace(hour=7), action="T", side="B", price=7500.25, size=50)
    assert ibi.bins_for_day([early]) == []


def _t(hh, mm, ss, px):
    return Trade(ts=datetime(2026, 9, 10, hh, mm, ss, tzinfo=CENTRAL), symbol="ESZ6",
                 instrument_id=1, price=px, size=1, side="N")


def test_excursions_and_forward_rule_are_on_the_attacked_side():
    ep = {"ts": T0, "side": "bid", "price": 7500.0}
    tr = [_t(10, 5, 0, 7510.0), _t(10, 20, 0, 7498.5)]
    assert survey.excursions("bid", 7500.0, T0, tr) == (1.5, 10.0)
    assert survey.excursions("ask", 7500.0, T0, tr) == (10.0, 1.5)
    assert survey.forward_result(ep, tr, through_pts=1.0) == "broke"
    assert survey.forward_result(ep, tr, through_pts=2.0) == "held"
    assert survey.forward_result(ep, [_t(10, 45, 0, 7400.0)]) is None       # past 30 min


def test_baseline_takes_one_level_per_rth_minute_with_a_full_window():
    tr = [_t(9, 0, 1, 7500.0), _t(9, 0, 30, 7501.0), _t(9, 1, 0, 7499.0), _t(9, 20, 0, 7503.0),
          _t(14, 40, 0, 7510.0), _t(14, 50, 0, 7509.0)]
    base = survey.baseline_excursions(tr)
    assert len(base) == 2                     # 09:00 and 09:01; 14:40 and 14:50 have no full window
    assert base[0] == (2.0, 2.0)              # from 7501 (last print in 09:00): low 7499, high 7503
    assert base[1] == (0.0, 4.0)              # from 7499: nothing below, 7503 above


def test_summary_cells_apply_floor_and_hold_and_count_the_last_ten_minutes():
    def e(hh, mm, expected, hold_s, held, side="bid", price=7500.0):
        return {"ts": datetime(2026, 9, 10, hh, mm, tzinfo=CENTRAL), "side": side, "price": price,
                "vol": 100, "expected": expected, "rate": 0.02, "held": held, "hold_s": hold_s,
                "refills": 1, "disp": 1 if held else -1, "flushed": False}
    episodes = [e(9, 5, 2.5, 1.0, True), e(11, 0, 3.5, 20.0, True), e(14, 55, 9.0, 2.0, True),
                e(13, 0, 5.0, 40.0, False), e(15, 30, 9.0, 40.0, True)]   # last one is outside RTH
    trades = [_t(9, 10, 0, 7498.5), _t(11, 10, 0, 7501.0), _t(14, 58, 0, 7502.0)]
    row = survey.summarize_day("2026-09-10", episodes, {"book_events": 5, "trade_events": 5,
                                                         "unreadable": [], "segments": 1}, trades)
    c = row["cells"]["3/0"]
    assert (c["reads"], c["held"], c["held_last_ten"]) == (3, 2, 1)
    assert (c["fwd_scored"], c["fwd_broke"]) == (2, 0)
    assert c["fwd_through_pts"] == [0.0, 0.0] and c["fwd_away_pts"] == [1.0, 2.0]
    assert c["held_by_hour"] == {"11": 1, "14": 1}
    assert row["cells"]["2/0"]["reads"] == 4 and row["cells"]["2/0"]["fwd_broke"] == 1
    assert row["baseline_minutes"] == 0 and row["baseline_broke"] == 0   # no minute has a full window here
    assert row["cells"]["3/15"]["held"] == 1 and row["cells"]["8/30"]["reads"] == 0
