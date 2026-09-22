"""absorption_scalp_survey (co-qp8cn): the per-second forward path, its
horizon rule, the win/broke rule, anchor distances, the two baselines and
the grid selection. Synthetic trades only."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from market.entities.trade import Trade
from scripts.measurement import absorption_scalp_survey as sv

CENTRAL = ZoneInfo("America/Chicago")
DAY = date(2026, 9, 10)
OPEN = datetime(2026, 9, 10, 8, 30, tzinfo=CENTRAL)


def tr(t, price, size=1, side="B"):
    return Trade(ts=t, symbol="ESZ6", instrument_id=1, price=price, size=size, side=side)


def path_from(points):
    """points: (seconds after the open, price)."""
    trades = [tr(OPEN + timedelta(seconds=s), p) for s, p in points]
    return sv.SecondPath(trades, DAY), trades


def test_win_means_target_before_stop_and_broke_means_stop_hit():
    t0 = OPEN + timedelta(minutes=60)
    # bid defense at 7500: price goes 2 pt away at +10 s, then 1.25 through at +40 s
    path, _ = path_from([(3600 + 10, 7502.0), (3600 + 40, 7498.75), (3600 + 200, 7500.0)])
    sc = path.score("bid", 7500.0, t0)
    assert sc["1"] == [1.25, 2.0, True, True]      # won first, then broke
    # the mirror: an ask defense at 7500 with the same prints is broke first
    sc2 = path.score("ask", 7500.0, t0)
    assert sc2["1"][2] is True and sc2["1"][3] is False
    assert sc2["1"][0] == 2.0 and sc2["1"][1] == 1.25


def test_stop_and_target_in_the_same_second_is_not_a_win():
    t0 = OPEN + timedelta(minutes=60)
    path, _ = path_from([(3600 + 5, 7498.75), (3600 + 5, 7502.0)])
    sc = path.score("bid", 7500.0, t0)
    assert sc["1"][2] is True and sc["1"][3] is False


def test_horizons_are_scored_only_when_the_window_ends_by_the_close():
    late = OPEN + timedelta(hours=6, minutes=27)          # 14:57
    path, _ = path_from([(6 * 3600 + 27 * 60 + 30, 7501.0), (6 * 3600 + 29 * 60, 7501.5)])
    sc = path.score("bid", 7500.0, late)
    assert set(sc) == {"1", "2"}                            # 5 and 30 minutes run past 15:00
    assert sc["2"] == [0.0, 1.5, False, False]
    assert path.score("bid", 7500.0, OPEN + timedelta(hours=6, minutes=59, seconds=30)) is None


def test_window_starts_the_second_after_the_read():
    t0 = OPEN + timedelta(minutes=60, milliseconds=400)
    # a print in the read's own second is not scored; the next second is
    path, _ = path_from([(3600, 7490.0), (3601, 7500.5)])
    sc = path.score("bid", 7500.0, t0)
    assert sc["1"] == [0.0, 0.5, False, False]


def test_nearest_ticks_and_developing_edges():
    assert sv.nearest_ticks(7500.0, [7490.0, 7501.0, 7520.0]) == 4
    assert sv.nearest_ticks(7500.0, []) is None
    trades = [tr(OPEN + timedelta(minutes=i), p) for i, p in enumerate((7500.0, 7505.0, 7495.0, 7510.0))]
    edges = sv.developing_edges(trades)
    # at minute 2.5 the day's high is 7505 and low 7495: a level at 7504 is 4 ticks off the high
    assert sv.edge_ticks(7504.0, OPEN + timedelta(minutes=2, seconds=30), edges) == 4
    # before the first RTH print there is no edge yet
    assert sv.edge_ticks(7504.0, OPEN - timedelta(minutes=1), edges) is None
    # overnight prints do not seed the edges
    pre = [tr(OPEN - timedelta(minutes=5), 7600.0)] + trades
    assert sv.developing_edges(pre)[1][0] == 7500.0


def test_baseline_at_and_off_forms():
    # one minute: prints 7500 (low), 7501.5 (high), last 7500.75 — bid 'off'
    # level is the low with price 3 ticks off it (inside the 2-4 bound); the
    # ask side is also 3 ticks under the high, so both 'off' rows exist
    t = OPEN + timedelta(hours=2)
    trades = [tr(t + timedelta(seconds=5), 7500.0), tr(t + timedelta(seconds=20), 7501.5),
              tr(t + timedelta(seconds=40), 7500.75),
              tr(t + timedelta(minutes=1, seconds=10), 7503.0),
              tr(t + timedelta(minutes=3), 7504.0)]
    path = sv.SecondPath(trades, DAY)
    b = sv.baseline(trades, path, [7500.0])
    kinds = sorted((r["kind"], r["ticks"]) for r in b["rows"])
    # minute 1: at ×2 (bid, ask) on 7500.75 (3 ticks from 7500), off bid on 7500 (0 ticks),
    # off ask on 7501.5 (6 ticks); minutes 2 and 3 hold one print each so only 'at' rows
    assert kinds.count(("at", 3)) == 2 and ("off", 0) in kinds and ("off", 6) in kinds
    assert all(r["off"] == 3 for r in b["rows"] if r["kind"] == "off")
    assert b["minutes"] == 3
    # a minute whose price already sits 8 ticks off its low is not a fair twin
    far = [tr(t + timedelta(seconds=5), 7500.0), tr(t + timedelta(seconds=40), 7502.0),
           tr(t + timedelta(minutes=3), 7504.0)]
    b2 = sv.baseline(far, sv.SecondPath(far, DAY), [])
    assert not [r for r in b2["rows"] if r["kind"] == "off"]


def test_cell_select_applies_every_bound():
    eps = [
        {"expected": 3.5, "hold_s": 20.0, "mancini_ticks": 3, "max_print": 60, "print_norm": 3.0},
        {"expected": 2.5, "hold_s": 20.0, "mancini_ticks": 3, "max_print": 60, "print_norm": 3.0},   # floor
        {"expected": 3.5, "hold_s": 90.0, "mancini_ticks": 3, "max_print": 60, "print_norm": 3.0},   # hold
        {"expected": 3.5, "hold_s": 20.0, "mancini_ticks": 9, "max_print": 60, "print_norm": 3.0},   # anchor
        {"expected": 3.5, "hold_s": 20.0, "mancini_ticks": None, "max_print": 60, "print_norm": 3.0},  # no levels
        {"expected": 3.5, "hold_s": 20.0, "mancini_ticks": 3, "max_print": 20, "print_norm": 3.0},   # print
        {"expected": 3.5, "hold_s": 20.0, "mancini_ticks": 3, "max_print": 20, "print_norm": 0.0},   # no norm yet
    ]
    assert sv.cell_select(eps, 3.0, 60.0, 4, 20) == [eps[0]]
    assert len(sv.cell_select(eps, 2.0, None, None, None)) == 7


def test_fwd_stats_counts_only_scored_horizons():
    scored = [{"1": [0.0, 2.0, False, True], "5": [1.5, 2.0, True, False]},
              {"1": [0.0, 0.5, False, False]},
              None]
    s = sv.fwd_stats(scored)
    assert s["1"]["n"] == 2 and s["1"]["win"] == 0.5 and s["1"]["broke"] == 0.0
    assert s["5"]["n"] == 1 and s["5"]["broke"] == 1.0
    assert s["30"]["n"] == 0 and s["30"]["win"] is None
