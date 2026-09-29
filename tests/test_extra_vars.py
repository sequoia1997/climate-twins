"""Optional extra matched variables (pet, srad) on synthetic data. Run: pytest tests/test_extra_vars.py
Nothing here needs the network or the real datasets."""
import copy, sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw import common as C  # noqa: E402
from ctw import analogs, cmip6, site  # noqa: E402


@pytest.fixture(autouse=True)
def reset_extras():
    C.use_extras([])
    yield
    C.use_extras([])


def cfg_with(extra, seasons=(0, 2)):
    c = copy.deepcopy(C.config())
    c["matching"]["extra"] = list(extra)
    c["matching"]["extra_seasons"] = list(seasons)
    return c


def monthly(nt=4, seed=0):
    r = np.random.default_rng(seed)
    m = np.arange(12)[:, None]
    tmax = 15 + 12 * np.sin((m - 3) / 12 * 2 * np.pi) + r.normal(0, .3, (12, nt))
    return {"tmax": tmax, "tmin": tmax - 8, "ppt": 60 + 30 * np.cos(m / 12 * 2 * np.pi) + np.zeros((12, nt)),
            "vap": 1.0 + 0.4 * np.sin((m - 3) / 12 * 2 * np.pi) + np.zeros((12, nt)),
            "pet": 80 + 60 * np.sin((m - 3) / 12 * 2 * np.pi) + np.zeros((12, nt)),
            "srad": 180 + 90 * np.sin((m - 3) / 12 * 2 * np.pi) + np.zeros((12, nt))}


def test_default_is_off_and_unchanged():
    cfg = C.config()
    assert cfg["matching"]["extra"] == []
    assert C.extra_names(cfg) == []
    assert list(C.match_idx(cfg)) == list(range(12)) + [12, 14]
    assert C.seasonalize(monthly()).shape == (16, 4)
    assert C.nvx() == 16


def test_unknown_extra_rejected():
    with pytest.raises(ValueError):
        C.extra_names(cfg_with(["wind"]))


def test_env_override(monkeypatch):
    monkeypatch.setenv("CTW_EXTRA", "pet, srad")
    assert C.config()["matching"]["extra"] == ["pet", "srad"]
    monkeypatch.setenv("CTW_EXTRA", "")
    assert C.config()["matching"]["extra"] == []


def test_vector_layout_and_selection():
    cfg = cfg_with(["pet", "srad"])
    C.use_extras(C.extra_names(cfg))
    assert C.nvx() == 24
    assert list(C.match_idx(cfg)) == list(range(12)) + [12, 14, 16, 18, 20, 22]
    assert list(C.match_idx(cfg_with(["srad"], seasons=(1, 3)))[-2:]) == [17, 19]
    v = C.seasonalize(monthly())
    assert v.shape == (24, 4)
    mon = monthly()
    assert np.allclose(v[16], mon["pet"][[11, 0, 1]].sum(0))          # DJF PET is a sum
    assert np.allclose(v[20], mon["srad"][[11, 0, 1]].mean(0))        # DJF srad is a mean
    t = C.transform(v.T)
    assert np.allclose(t[:, 16], np.log(v[16] + 1))
    assert np.allclose(t[:, 20], v[20] / 10)
    assert np.allclose(t[:, :16], C.transform(v.T[:, :16]))            # standard columns untouched


def test_missing_extra_is_nan_not_crash():
    C.use_extras(["pet"])
    mon = monthly(); mon.pop("pet")
    assert np.isnan(C.seasonalize(mon)[16:20]).all()


def test_seasonal_years_width_and_december_rule():
    C.use_extras(["pet"])
    yrs = np.arange(1990, 1995)
    r = np.random.default_rng(1)
    series = {v: r.normal(10, 1, (5, 12)) for v in ("tmax", "tmin", "ppt", "vap", "pet")}
    sy = C.seasonal_years(series, yrs, [1991, 1992])
    assert sy.shape == (2, 20)
    assert np.isclose(sy[0, 16], series["pet"][1, [0, 1]].sum() + series["pet"][0, 11])


def test_enc_fits_int16_and_roundtrips():
    C.use_extras(["pet", "srad"])
    v = C.seasonalize(monthly()).T
    v[:, 20:] = [[350.0, 300.0, 320.0, 340.0]]                          # tropical srad
    v[:, 16:20] = [[400.0, 300.0, 250.0, 380.0]]
    e = C.enc(v)
    assert e.dtype == np.int16 and e.shape == (4, 24)
    assert np.allclose(e[:, 20:] / C.ENC_SCALE, v[:, 20:] / 10, atol=1 / C.ENC_SCALE)
    assert np.allclose(np.exp(e[:, 16:20] / C.ENC_SCALE) - 1, v[:, 16:20], rtol=0.01)
    C.use_extras([])
    assert C.enc(v[:, :16]).shape == (4, 16)


def test_hargreaves_pet_behaviour():
    lat = np.array([0.0, 35.0, 60.0, -35.0])
    m = np.arange(12)[:, None]
    tm = 15 + 10 * np.sin((m - 3) / 12 * 2 * np.pi) * np.sign(lat)[None]
    tx, tn = tm + 6, tm - 6
    pet = C.hargreaves_pet(tx, tn, lat)
    assert pet.shape == (12, 4) and np.isfinite(pet).all() and (pet >= 0).all()
    assert 600 < pet[:, 1].sum() < 1600                                  # temperate annual PET, mm
    assert pet[6, 1] > 2 * pet[0, 1]                                     # northern summer > winter
    assert pet[0, 3] > pet[6, 3]                                         # southern hemisphere reversed
    assert np.allclose(pet[:, 3], np.roll(pet[:, 1], 6), rtol=0.2)
    warmer = C.hargreaves_pet(tx + 3, tn + 3, lat)
    assert (warmer >= pet).all() and (warmer[:, 1] > pet[:, 1]).all()
    assert np.isfinite(C.hargreaves_pet(tx - 60, tn - 60, lat)).all()   # polar cold: PET floors at 0


def test_extras_future_factors():
    m = monthly(3)
    bm = {k: m[k].T for k in ("tmax", "tmin", "pet", "srad")}
    lat = np.array([10.0, 40.0, 55.0])
    f = analogs.extras_future(["pet", "srad"], bm, bm["tmax"] + 3, bm["tmin"] + 3, np.full((3, 12), 1.05), lat)
    assert (f["pet"] > bm["pet"]).all() and (f["pet"] < 1.5 * bm["pet"]).all()   # warming raises PET a few % per K
    assert np.allclose(f["srad"], bm["srad"] * 1.05)
    same = analogs.extras_future(["pet"], bm, bm["tmax"], bm["tmin"], None, lat)
    assert np.allclose(same["pet"], bm["pet"])                                   # no change in climate, no change in PET
    wild = analogs.extras_future(["srad"], bm, bm["tmax"], bm["tmin"], np.full((3, 12), 5.0), lat)
    assert np.allclose(wild["srad"], bm["srad"] * 1.25)                          # ratio limit
    assert "srad" not in analogs.extras_future(["pet"], bm, bm["tmax"], bm["tmin"], None, lat)


def test_cmip6_variable_list_gated():
    assert cmip6.vars_for(cfg_with([])) == cmip6.VARS
    assert cmip6.vars_for(cfg_with(["pet"])) == cmip6.VARS                       # PET needs only tasmax/tasmin
    assert cmip6.vars_for(cfg_with(["pet", "srad"])) == cmip6.VARS + ("rsds",)


def _synthetic_search(n_pool=800, extra_informative=True, seed=3):
    """Two places, a random pool, an 'extras' metric and the arrays extra_sensitivity() expects."""
    cfg = cfg_with(["pet"])
    C.use_extras(["pet"])
    midx = C.match_idx(cfg)
    Kc = len(midx) - 2
    r = np.random.default_rng(seed)
    NT, P, S = 2, 2, 1
    ens = {"tcr_likely": [0, 1, 2], "all": [0, 1, 2, 3]}
    EN = list(ens)
    lat, lon = r.uniform(-50, 60, n_pool), r.uniform(-120, 120, n_pool)
    raw = r.normal(0, 1, (n_pool, C.nvx())) * 3 + 10
    raw[:, C.PPT] = r.uniform(20, 200, (n_pool, 4))
    raw[:, 16:20] = r.uniform(20, 200, (n_pool, 4)) if extra_informative else 100.0
    pool = dict(lat=lat, lon=lon, raw=raw, tr=C.transform(raw)[:, midx])
    import pandas as pd
    T = pd.DataFrame({"g": [1, 1]})
    fut = np.zeros((NT, P, S, 4, C.nvx()))
    LMS, SH, best_idx, best_sig = {}, {}, np.zeros((NT, P, S, 2, 2), int), np.zeros((NT, P, S, 2, 2))
    for k in range(NT):
        base = raw[r.integers(n_pool)]
        for p in range(P):
            fut[k, p, 0] = base + r.normal(0, 1, (4, C.nvx())) + 2 * (p + 1)
            fut[k, p, 0, :, C.PPT] = np.abs(fut[k, p, 0, :, C.PPT]) + 30
            fut[k, p, 0, :, 16:20] = np.abs(fut[k, p, 0, :, 16:20]) + 50
        raw_years = base + r.normal(0, 1, (30, C.nvx()))
        raw_years[:, C.PPT] = np.abs(raw_years[:, C.PPT]) + 30
        raw_years[:, 16:20] = np.abs(raw_years[:, 16:20]) + 50
        Lm = C.transform(raw_years)[:, midx]
        LMS[k] = Lm
        SH[k] = C.ShrinkSigmaModel(Lm)
        for p in range(P):
            evs = np.stack([fut[k, p, 0][ens[en]].mean(0) for en in EN])
            Pp = SH[k].project(pool["tr"])
            Q = SH[k].project(C.transform(evs)[:, midx])
            D2 = ((Pp[:, None, :] - Q[None]) ** 2).sum(2)
            i = D2.argmin(0)
            for e in range(2):
                best_idx[k, p, 0, e, 0] = i[e]
                best_sig[k, p, 0, e, 0] = C.chi_to_sigma(np.sqrt(D2[i[e], e]), SH[k].k)[0]
    return cfg, T, np.zeros(NT, bool), LMS, pool, fut, ens, EN, best_idx, best_sig, SH, Kc


def test_sensitivity_report_structure_and_ranges():
    cfg, T, bad, LMS, pool, fut, ens, EN, bi, bs, SH, Kc = _synthetic_search()
    out = analogs.extra_sensitivity(cfg, T, bad, LMS, pool, pool, fut, ens, EN, bi, bs, SH, Kc)
    assert out["extras"] == ["pet"] and out["k_core"] == Kc and out["k_with_extras"] == Kc + 2
    assert out["places"] == 2 and 0 <= out["moved_share"] <= 1 and out["median_abs_dsigma"] >= 0
    assert out["world"]["n"] == 2 * 2 * 1 * 2 and out["north_america"] is None
    assert 0 <= out["alpha_core"] <= 1 and 0 <= out["alpha_with_extras"] <= 1
    import json
    json.dumps(out)                                                              # must be serialisable for summary.json


def test_sensitivity_zero_when_extras_carry_no_information():
    cfg, T, bad, LMS, pool, fut, ens, EN, bi, bs, SH, Kc = _synthetic_search(extra_informative=False)
    # extras are constant in the pool, so the extras metric's best match is the standard metric's best match
    fut[..., 16:20] = 100.0
    for k in LMS:
        LMS[k][:, Kc:] = 0.0 + np.random.default_rng(k).normal(0, 0.1, LMS[k][:, Kc:].shape)
    out = analogs.extra_sensitivity(cfg, T, bad, LMS, pool, pool, fut, ens, EN, bi, bs, SH, Kc)
    assert out["k_with_extras"] == Kc + 2
    assert out["median_moved_km"] >= 0 and out["moved_share"] is not None


def test_more_dimensions_change_sigma_scale_but_stay_finite():
    D = np.array([1.0, 3.0, 6.0])
    s14, s18 = C.chi_to_sigma(D, 14), C.chi_to_sigma(D, 18)
    assert np.isfinite(s14).all() and np.isfinite(s18).all()
    assert (s18 < s14).all()                                                     # same distance is less surprising in more dimensions


def test_shrinkage_grows_with_dimension_at_fixed_years():
    r = np.random.default_rng(5)
    base = r.normal(size=(30, 14))
    more = np.hstack([base, r.normal(size=(30, 4))])
    a14, a18 = C.ShrinkSigmaModel(base).alpha, C.ShrinkSigmaModel(more).alpha
    assert 0 < a14 <= 1 and 0 < a18 <= 1 and a18 >= a14 - 0.05
    assert C.ShrinkSigmaModel(more).k == 18


def test_methods_section_only_when_enabled():
    assert site.extra_section(cfg_with([]), {}) == ("", "")
    toc, sec = site.extra_section(cfg_with(["pet", "srad"]), {"extra": dict(moved_km=500, moved_share=0.08, median_abs_dsigma=0.12)})
    assert 'href="#extra"' in toc and 'id="extra"' in sec and "Hargreaves" in sec and "rsds" in sec and "8%" in sec
    assert "Hargreaves" not in site.extra_section(cfg_with(["srad"]), {})[1]
