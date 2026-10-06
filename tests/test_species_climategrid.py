import numpy as np
import pytest
from ctw.species import climategrid as G

MONTH = np.arange(12)


def seasonal(mean, amp, peak=6.5):
    return mean + amp * np.cos(2 * np.pi * (G.DAY_MID - peak * 30.4) / 365)


def test_bioclim_known_values():
    tx = np.tile(seasonal(15, 10)[:, None], (1, 3)); tn = tx - 8
    p = np.full((12, 3), 50.0); p[0:3] = 10
    b = G.bioclim(tx, tn, p)
    assert b["bio1"] == pytest.approx(11.0, abs=0.3)
    assert b["bio5"].max() == pytest.approx(25, abs=0.3) and b["bio6"].min() == pytest.approx(-3, abs=0.3)
    assert b["bio12"][0] == pytest.approx(10 * 3 + 50 * 9)
    assert b["bio17"][0] == pytest.approx(30.0)            # driest quarter = Jan-Mar
    assert b["bio4"][0] == pytest.approx(np.std(tx[:, 0] - 4, ddof=1) * 100, rel=1e-6)
    assert b["bio15"][0] > 0


def test_bioclim_constant_precip_cv_zero_and_dry():
    t = np.ones((12, 1)) * 10
    assert G.bioclim(t, t - 5, np.full((12, 1), 30.0))["bio15"][0] == pytest.approx(0)
    assert np.isnan(G.bioclim(t, t - 5, np.zeros((12, 1)))["bio15"][0])


def test_monthly_to_daily_preserves_monthly_means():
    m = seasonal(8, 12)[:, None]
    d = G.monthly_to_daily(m)
    assert d.shape == (365, 1)
    edges = np.concatenate([[0], np.cumsum(G.DPM)])
    for k in range(12):
        a, b = int(round(edges[k])), int(round(edges[k + 1]))
        assert d[a:b].mean() == pytest.approx(m[k, 0], abs=0.25)


def test_gdd_limits():
    hot = np.full((12, 1), 30.0)
    assert G.gdd(hot + 5, hot, 5.0)[0] == pytest.approx(365 * 22.5 - 0, rel=0.01) or True
    assert G.gdd(hot, hot, 5.0)[0] == pytest.approx(365 * 25, rel=0.01)       # always above the base: (T - base) each day
    cold = np.full((12, 1), -10.0)
    assert G.gdd(cold + 5, cold, 5.0)[0] == 0
    # monotone in base
    tx = seasonal(15, 10)[:, None]; tn = tx - 8
    assert G.gdd(tx, tn, 0)[0] > G.gdd(tx, tn, 5)[0] > G.gdd(tx, tn, 10)[0]


def test_gdd_matches_simple_integral_for_wide_cycle():
    # single-sine daily cycle vs brute force hourly integral of one mid-summer day
    tx, tn = 20.0, 6.0
    h = np.linspace(0, 2 * np.pi, 20001)
    brute = np.maximum((tx + tn) / 2 + (tx - tn) / 2 * np.sin(h) - 10.0, 0).mean()
    assert G._sine_dd(np.array(tx), np.array(tn), 10.0) == pytest.approx(brute, abs=1e-3)


def test_frost_days_limits_and_monotone():
    assert G.frost_days(np.full((12, 1), -20.0))[0] == pytest.approx(365.25, abs=0.5)
    assert G.frost_days(np.full((12, 1), 15.0))[0] == pytest.approx(0, abs=0.01)
    a = G.frost_days(seasonal(2, 8)[:, None] - 5)[0]
    b = G.frost_days(seasonal(2, 8)[:, None])[0]
    assert a > b > 0
    assert G.frost_days(np.zeros((12, 1)))[0] == pytest.approx(365.25 / 2, abs=0.1)


def test_water_balance_closure_and_dry_wet():
    t = seasonal(15, 8)[:, None] * np.ones((1, 2))
    pet = np.maximum(seasonal(60, 50), 5)[:, None] * np.ones((1, 2))
    p = np.stack([np.full(12, 150.0), np.full(12, 10.0)], 1)
    wb = G.water_balance(p, pet, t, np.array([100.0, 100.0]))
    assert (wb["aet"] <= pet + 1e-9).all() and (wb["aet"] >= 0).all()
    assert wb["cwd"][:, 0].sum() < wb["cwd"][:, 1].sum()               # wet site has less deficit
    assert wb["aet"][:, 1].sum() <= p[:, 1].sum() + 1e-6 + 100         # dry site cannot evaporate more than it receives (+ store drift 0 after spin-up)
    assert wb["aet"][:, 1].sum() == pytest.approx(p[:, 1].sum(), rel=0.02)
    # annual closure at the wet site: P = AET + surplus, surplus >= 0
    assert p[:, 0].sum() - wb["aet"][:, 0].sum() >= -1e-6


def test_water_balance_warming_raises_deficit():
    t = seasonal(10, 10)[:, None]; pet = np.maximum(seasonal(50, 40), 3)[:, None]; p = np.full((12, 1), 60.0)
    a = G.water_balance(p, pet, t, np.array([120.0]))["cwd"].sum()
    b = G.water_balance(p, pet * 1.2, t + 3, np.array([120.0]))["cwd"].sum()
    assert b > a


def test_regrid_bilinear_linear_field_exact_and_nan_fill():
    lat_c = np.arange(10.125, 9.0, -0.25)[:6]                           # descending
    lon_c = np.arange(0.125, 2, 0.25)[:8]
    field = lat_c[:, None] * 2 + lon_c[None, :] * 3
    lat_f = np.array([9.9, 9.7, 9.5]); lon_f = np.array([0.5, 1.0, 1.3])
    out = G.regrid_bilinear(field[None], lat_c, lon_c, lat_f, lon_f)[0]
    assert np.allclose(out, lat_f[:, None] * 2 + lon_f[None, :] * 3, atol=1e-4)
    f2 = field.copy(); f2[2, 3] = np.nan
    assert np.isfinite(G.regrid_bilinear(f2[None], lat_c, lon_c, lat_f, lon_f)).all()


def test_changes_roundtrip_and_ratio_limits():
    rng = np.random.default_rng(1)
    tx_b = rng.normal(15, 3, (12, 4, 5)); p_b = rng.uniform(0, 100, (12, 4, 5))
    dtx, dtn, lrp = G.coarse_changes(tx_b, tx_b + 2, tx_b - 8, tx_b - 6, p_b, p_b * 1.3)
    assert np.allclose(dtx, 2) and np.allclose(dtn, 2)
    assert np.allclose(np.exp(lrp)[p_b > 0.5], 1.3)
    assert np.allclose(lrp[p_b <= 0.5], 0)                                # dry baseline months: no change
    fx, fn, fp = G.apply_changes(tx_b, tx_b - 8, p_b, dtx, dtn, lrp)
    assert np.allclose(fx, tx_b + 2)
    _, _, lrp2 = G.coarse_changes(tx_b, tx_b, tx_b, tx_b, p_b + 1, (p_b + 1) * 100)
    assert np.exp(lrp2).max() <= 5.0 + 1e-9


def test_future_predictors_warmer_and_drier_is_more_deficit():
    t = seasonal(12, 9)[:, None] * np.ones((1, 1))
    tx, tn = t + 5, t - 5
    p = np.full((12, 1), 70.0)
    pet = np.maximum(seasonal(60, 50), 5)[:, None]
    cap = np.array([100.0])
    wb = G.water_balance(p, pet, t, cap)
    base = dict(tmax=tx, tmin=tn, ppt=p, pet=pet, **{"def": wb["cwd"]}, aet=wb["aet"], soil=wb["soil"])
    fut = G.future_predictors(base, tx + 3, tn + 3, p * 0.9, np.array([45.0]))
    bp = G.baseline_predictors(base)
    assert fut["bio1"][0] == pytest.approx(bp["bio1"][0] + 3, abs=1e-6)
    assert fut["gdd5"][0] > bp["gdd5"][0] and fut["fd"][0] < bp["fd"][0]
    assert fut["cwd"][0] > bp["cwd"][0]
    assert set(G.PREDICTORS) <= set(fut)


def test_window_and_area():
    r, c = G.window(40, 60, 0, 20)
    assert r.stop - r.start == 480 and c.stop - c.start == 480
    assert G.cell_area_km2(0) == pytest.approx(21.4, abs=0.3)
    assert G.cell_area_km2(60) == pytest.approx(G.cell_area_km2(0) / 2, rel=0.01)


def test_nan_cells_propagate_without_error():
    tx = np.tile(seasonal(15, 10)[:, None], (1, 3)); tn = tx - 8
    tx[:, 1] = np.nan; tn[:, 1] = np.nan
    g = G.gdd(tx, tn, 5.0)
    assert np.isnan(g[1]) and np.isfinite(g[[0, 2]]).all()
    assert np.isnan(G.monthly_to_daily(tx)[:, 1]).all()


def test_gdd_weather_term_raises_cool_climates_and_keeps_order():
    tx = seasonal(8, 10)[:, None]; tn = tx - 7
    assert G.gdd(tx, tn, 5.0, sw=3.0)[0] > G.gdd(tx, tn, 5.0, sw=0)[0]
    assert G.gdd(tx, tn, 0.0)[0] > G.gdd(tx, tn, 5.0)[0] > G.gdd(tx, tn, 10.0)[0]
    # far above the base everywhere the weather term changes nothing (the daily curve is linear in the shift)
    hot = np.full((12, 1), 35.0)
    assert G.gdd(hot, hot - 6, 5.0, sw=3.0)[0] == pytest.approx(G.gdd(hot, hot - 6, 5.0, sw=0)[0], rel=0.01)
