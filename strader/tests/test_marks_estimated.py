"""strader/marks/estimated.py — the proxy, its calibration, and the coverage
guard. [st-9hhc]

Pins the three things the plan names: the decay term, the ES->premium
conversion at known bins, and the guard that refuses to extrapolate
silently. Deterministic, no network, no corpus.
"""
import pytest

from strader.marks import estimated as em
from strader.marks.prints import WINDOW_END_S, WINDOW_START_S


def flat_cal(delta: float, theta: float) -> em.Calibration:
    return em.Calibration(pooled=(delta, theta, 10_000), fit_days="test")


def es_grid(start_s: int, prices: list[float]) -> list[tuple[int, float]]:
    return [(start_s + 60 * i, p) for i, p in enumerate(prices)]


# ------------------------------------------------------------------- bins

def test_mbin_edges():
    assert em.mbin(-10.0) == 0   # otm
    assert em.mbin(-5.0) == 0    # edge belongs to otm
    assert em.mbin(0.0) == 1     # near
    assert em.mbin(4.99) == 1
    assert em.mbin(5.0) == 2     # itm
    assert em.mbin(12.0) == 2


def test_ttc_buckets():
    assert em.ttc_bucket(5) == 0
    assert em.ttc_bucket(15) == 0
    assert em.ttc_bucket(16) == 1
    assert em.ttc_bucket(45) == 2
    assert em.ttc_bucket(75) == 3
    assert em.ttc_bucket(120) == 4


# ------------------------------------------------------------ decay term

def test_flat_es_decays_at_theta():
    """No ES move: the path is pure decay, theta pts per minute, floored at 0."""
    cal = flat_cal(delta=0.5, theta=-0.02)
    grid = es_grid(WINDOW_START_S, [6000.0] * 61)  # 13:00..14:00, flat
    path = em.estimated_path("C", 6000, 0.50, 6000.0, WINDOW_START_S, grid, cal)
    assert path[0].mark == 0.50
    assert path[1].mark == pytest.approx(0.48)
    assert path[10].mark == pytest.approx(0.50 - 0.02 * 10)
    assert path[-1].mark == pytest.approx(0.0)  # 25 min of decay hits the floor
    assert all(p.mark >= 0.0 for p in path)
    assert not any(p.extrapolated for p in path)


# --------------------------------------------- conversion at known bins

def test_conversion_uses_the_state_at_step_start():
    """A call entered ATM: the first +10 ES step prices off the NEAR bin,
    the next step prices off the ITM bin — the step keys off the moneyness
    the option had before the move, same convention the fit consumes."""
    cal = em.Calibration(
        table={(1, 4): (0.50, 0.0, 1000),   # near, >90 min out
               (2, 4): (0.90, 0.0, 1000)},  # itm, >90 min out
        fallback={0: (0.10, 0.0, 1000), 1: (0.50, 0.0, 1000), 2: (0.90, 0.0, 1000)},
        pooled=(0.5, 0.0, 1000), fit_days="test")
    grid = es_grid(WINDOW_START_S, [6000.0, 6010.0, 6020.0])
    path = em.estimated_path("C", 6000, 5.0, 6000.0, WINDOW_START_S, grid, cal)
    # step 1: moneyness at start 0 -> near bin, delta 0.5 on +10
    assert path[1].mark == pytest.approx(5.0 + 0.5 * 10)
    # step 2: moneyness at start +10 -> itm bin, delta 0.9 on +10
    assert path[2].mark == pytest.approx(10.0 + 0.9 * 10)


def test_put_favour_is_downward():
    cal = flat_cal(delta=0.8, theta=0.0)
    grid = es_grid(WINDOW_START_S, [6000.0, 5995.0])
    path = em.estimated_path("P", 6010, 12.0, 6000.0, WINDOW_START_S, grid, cal)
    assert path[1].mark == pytest.approx(12.0 + 0.8 * 5)   # ES down favours the put


def test_thin_cell_falls_back():
    cal = em.Calibration(
        table={(2, 4): (0.9, 0.0, em.MIN_CELL_N - 1)},       # too thin to use
        fallback={2: (0.7, 0.0, 1000)},
        pooled=(0.5, 0.0, 1000), fit_days="test")
    assert cal.cell(2, 4) == (0.7, 0.0)                       # mbin fallback
    assert cal.cell(0, 0) == (0.5, 0.0)                       # pooled


# ------------------------------------------------------- coverage guard

def test_refuses_entry_before_coverage():
    cal = flat_cal(0.5, -0.02)
    grid = es_grid(10 * 3600, [6000.0] * 5)
    with pytest.raises(em.CoverageBound):
        em.estimated_path("C", 6000, 5.0, 6000.0, 10 * 3600, grid, cal)


def test_extrapolation_is_labelled_never_silent():
    cal = flat_cal(0.5, -0.02)
    grid = es_grid(10 * 3600, [6000.0] * 5)
    path = em.estimated_path("C", 6000, 5.0, 6000.0, 10 * 3600, grid, cal,
                             allow_extrapolation=True)
    assert all(p.extrapolated for p in path)
    inside = es_grid(WINDOW_START_S, [6000.0] * 5)
    path = em.estimated_path("C", 6000, 5.0, 6000.0, WINDOW_START_S, inside, cal,
                             allow_extrapolation=True)
    assert not any(p.extrapolated for p in path)


def test_grid_hole_reanchors_without_inventing_steps():
    cal = flat_cal(0.5, -0.02)
    grid = [(WINDOW_START_S, 6000.0), (WINDOW_START_S + 60, 6001.0),
            (WINDOW_START_S + 300, 6010.0),  # 4-minute hole
            (WINDOW_START_S + 360, 6011.0)]
    path = em.estimated_path("C", 6000, 5.0, 6000.0, WINDOW_START_S, grid, cal)
    # entry + one step before the hole + one step after re-anchoring
    assert [p.ct_s for p in path] == [WINDOW_START_S, WINDOW_START_S + 60,
                                      WINDOW_START_S + 360]


def test_input_validation():
    cal = flat_cal(0.5, 0.0)
    with pytest.raises(ValueError):
        em.estimated_path("X", 6000, 5.0, 6000.0, WINDOW_START_S, [], cal)
    with pytest.raises(ValueError):
        em.estimated_path("C", 6000, 0.0, 6000.0, WINDOW_START_S, [], cal)


# ------------------------------------------------------------ fire scans

def test_first_at_or_below_skips_entry_point():
    cal = flat_cal(0.5, 0.0)
    grid = es_grid(WINDOW_START_S, [6000.0, 5999.0, 5998.0])
    path = em.estimated_path("C", 6000, 5.0, 6000.0, WINDOW_START_S, grid, cal)
    hit = em.first_at_or_below(path, 4.6)
    assert hit is not None and hit.ct_s == WINDOW_START_S + 60
    assert em.first_at_or_above(path, 5.5) is None


# ------------------------------------------------------------ calibration

def test_fit_recovers_known_delta_and_theta():
    samples = []
    for i in range(500):
        x = (i % 21 - 10) / 4.0                    # ES moves -2.5..+2.5
        samples.append((2, 1, x, 0.6 * x - 0.02))  # exact linear law
    cal = em.fit_calibration(samples, fit_days="synthetic")
    delta, theta, n = cal.table[(2, 1)]
    assert delta == pytest.approx(0.6, abs=1e-6)
    assert theta == pytest.approx(-0.02, abs=1e-6)
    assert n == 500
    assert cal.fallback[2][0] == pytest.approx(0.6, abs=1e-6)
    assert cal.pooled[0] == pytest.approx(0.6, abs=1e-6)


def test_fit_zero_variance_yields_intercept_only():
    samples = [(1, 1, 0.0, -0.03)] * 200
    cal = em.fit_calibration(samples, fit_days="synthetic")
    assert cal.table[(1, 1)] == (0.0, -0.03, 200)


def test_calibration_json_roundtrip():
    samples = [(mi, ti, (i % 7 - 3) / 2.0, 0.5 * ((i % 7 - 3) / 2.0) - 0.01)
               for mi in (0, 1, 2) for ti in (0, 4) for i in range(150)]
    cal = em.fit_calibration(samples, fit_days="2025-05-27..2026-08-14")
    back = em.Calibration.from_json(cal.to_json())
    assert back == cal
    assert back.fit_days == "2025-05-27..2026-08-14"


def test_calibration_json_refuses_foreign_edges():
    bad = ('{"version": 1, "fit_days": "x", "mbin_edges": [-2.0, 2.0], '
           '"ttc_edges": [15.0, 30.0, 60.0, 90.0], "table": {}, '
           '"fallback": {}, "pooled": [0.5, 0.0, 100]}')
    with pytest.raises(ValueError):
        em.Calibration.from_json(bad)


# ------------------------------------------------------------ determinism

def test_two_walks_are_identical():
    cal = flat_cal(0.47, -0.013)
    grid = es_grid(WINDOW_START_S, [6000.0 + (i * 7 % 13) * 0.25 for i in range(120)])
    a = em.estimated_path("P", 6005, 8.0, 6000.0, WINDOW_START_S, grid, cal)
    b = em.estimated_path("P", 6005, 8.0, 6000.0, WINDOW_START_S, grid, cal)
    assert a == b
