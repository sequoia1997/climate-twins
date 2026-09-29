"""Unit tests for the extreme-day index math (synthetic data). Run: python -m pytest tests/test_extremes.py
or python tests/test_extremes.py."""
import pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ctw import extremes as E


def test_wet_bulb_stull_reference():
    # Stull (2011) worked example: 20 C, 50 % -> 13.7 C
    assert abs(float(E.wet_bulb(20.0, 50.0)) - 13.7) < 0.1
    # saturated air: wet-bulb close to air temperature; hot dry air is far below
    assert abs(float(E.wet_bulb(30.0, 99.0)) - 30.0) < 1.0
    assert float(E.wet_bulb(40.0, 10.0)) < 20.0
    assert float(E.wet_bulb(35.0, 80.0)) > 30.0       # the dangerous corner


def test_afternoon_humidity_lowers_tropical_wet_bulb():
    # Singapore-like day: high 32, low 25, daily-mean RH 85 % -> afternoon ~65 %, wet-bulb well under 28
    rh = float(E.rh_at_tmax(85.0, 32.0, 25.0))
    assert 60 < rh < 72
    assert float(E.wet_bulb(32.0, rh)) < 28.0 <= float(E.wet_bulb(32.0, 85.0))


def test_longest_run():
    m = np.zeros((10, 2), bool)
    m[2:5, 0] = True; m[7:9, 0] = True
    m[:, 1] = True
    assert list(E.longest_run(m)) == [3, 10]


def test_annual_indices_known_year():
    n = 365
    tx = np.full((n, 1), 20.0); tn = np.full((n, 1), 10.0)
    pr = np.full((n, 1), 2.0); rh = np.full((n, 1), 50.0)
    tx[:10] = 36; tx[10:30] = 31           # 10 days >=35, 30 days >=30
    tn[:5] = -2; tn[100:107] = 21          # 5 frost days, 7 tropical nights
    tx[200:203] = 35; tn[200:203] = 25; rh[200:203] = 90   # hot-humid: mean 90 % -> ~68 % at 35 C, wet-bulb ~29.5
    pr[50:60] = 0.2                        # dry spell of 10 days
    pr[150] = 88.0
    o = E.annual_indices(tx, tn, pr, rh)[:, 0]
    d = dict(zip(E.IDS, o))
    assert d["tx35"] == 13 and d["tx30"] == 33 and d["tr20"] == 10 and d["fd"] == 5
    assert d["wb28"] == 3                   # only the three humid days (36 C at 50 % mean humidity stays below 28)
    assert d["cdd"] == 10 and d["rx1"] == 88.0


def test_calendar_scaling_and_nan():
    tx = np.full((360, 2), 36.0); tn = np.zeros((360, 2)); pr = np.ones((360, 2)); rh = np.full((360, 2), 30.0)
    o = E.annual_indices(tx, tn, pr, rh)
    assert abs(o[0, 0] - 365) < 1e-3          # all days hot -> 365 in a 365-day year
    tx[3, 1] = np.nan
    o = E.annual_indices(tx, tn, pr, rh)
    assert np.isfinite(o[:, 0]).all() and np.isnan(o[:, 1]).all()


def test_cells_and_snap():
    ii, jj = E.cell_index(np.array([35.7721, -33.0]), np.array([-78.63861, 151.2]))
    assert abs(E.LAT0 + E.RES * ii[0] - 35.7721) <= 0.126
    assert abs(E.LON0 + E.RES * jj[0] - (360 - 78.63861)) <= 0.126
    valid = np.zeros((E.NLAT, E.NLON), bool)
    valid[ii[0], (jj[0] + 2) % E.NLON] = True
    a, b = E.snap_to_land(ii, jj, valid)
    assert (a[0], b[0]) == (ii[0], (jj[0] + 2) % E.NLON)
    assert a[1] == -1                         # nothing valid within 3 cells


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
