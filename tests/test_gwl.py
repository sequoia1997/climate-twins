"""Unit tests for the global-warming-level window logic (synthetic series). Run: pytest tests/test_gwl.py"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw import gwl  # noqa: E402

YEARS = np.arange(1850, 2101)


def linear(rate, t0=1900, base=14.0):
    """Flat at `base` until t0, then warming `rate` degC per year."""
    return base + np.maximum(YEARS - t0, 0) * rate


def test_running_mean_window_and_edges():
    a = np.arange(100.0)
    rm = gwl.running_mean(a)
    assert np.isnan(rm[:10]).all() and np.isnan(rm[-9:]).all()
    assert rm[10] == a[0:20].mean() and rm[50] == a[40:60].mean()          # 10 before, 9 after
    assert np.isfinite(rm[10:91]).all()


def test_running_mean_missing_year_blocks_window():
    a = np.arange(60.0); a[30] = np.nan
    rm = gwl.running_mean(a)
    assert np.isnan(rm[21:40]).all()                              # every window containing index 30
    assert rm[20] == a[10:30].mean()                              # window ends just before the gap
    assert np.isfinite(rm[15]) and np.isfinite(rm[45])


def test_linear_crossing_year_and_window():
    # 0.03 degC/yr after 1900: the 20-yr mean centred on year y is 0.03*(y - 0.5 - 1900 ... ) below; compute exactly
    tas = linear(0.03)
    cy = gwl.crossing_years(YEARS, tas, [1.5, 2.0, 3.0, 4.0])
    rm = gwl.running_mean(tas) - tas[:51].mean()
    for L, y in zip([1.5, 2.0, 3.0, 4.0], cy):
        i = int(y - 1850)
        assert rm[i] >= L and rm[i - 1] < L                       # first crossing
    assert list(cy) == sorted(cy) and cy[0] > 1900
    lo, hi = gwl.window(cy[0])
    assert hi - lo + 1 == 20 and lo == cy[0] - 10 and hi == cy[0] + 9
    assert hi <= 2100


def test_level_never_reached_is_zero():
    tas = linear(0.005)                                           # +1.0 by 2100 at most
    cy = gwl.crossing_years(YEARS, tas, [1.5, 2.0, 3.0, 4.0])
    assert list(cy) == [0, 0, 0, 0]


def test_crossing_needs_running_mean_not_a_spike():
    tas = linear(0.0)
    tas[150:152] += 6.0                                           # a two-year spike cannot lift the 20-yr mean by 1.5
    assert gwl.crossing_years(YEARS, tas, [1.5])[0] == 0
    tas[150:170] += 1.6                                           # a sustained 20-year step can
    y = gwl.crossing_years(YEARS, tas, [1.5])[0]
    assert y != 0 and 1990 <= y <= 2010


def test_reference_requires_full_period():
    assert np.isnan(gwl.reference(np.arange(1900, 2101), np.zeros(201)))
    assert gwl.reference(YEARS, np.full(len(YEARS), 3.0)) == 3.0
    assert (gwl.crossing_years(np.arange(1900, 2101), np.arange(201.0), [1.5]) == 0).all()


def test_reference_offset_invariance():
    a = gwl.crossing_years(YEARS, linear(0.03, base=10.0), [2.0])
    b = gwl.crossing_years(YEARS, linear(0.03, base=25.0), [2.0])
    assert a[0] == b[0]


def test_pool_deltas_averages_scenarios_that_reach():
    d = np.array([[1.0, np.nan], [3.0, np.nan], [np.nan, np.nan]])
    out = gwl.pool_deltas(d)
    assert out[0] == 2.0 and np.isnan(out[1])
