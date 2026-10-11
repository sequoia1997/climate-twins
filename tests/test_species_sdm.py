"""Unit tests for the species-distribution engine (ctw/species/sdm.py, virtual.py): synthetic grids, fast.
Run: pytest tests/test_species_sdm.py"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw.species import sdm, virtual as V  # noqa: E402


def synth_grid(n=2500, seed=0):
    """A small fake domain: warm in the south, wet in the east, with place-level deltas (+2 C, +5% rain) for projections."""
    rng = np.random.default_rng(seed)
    lat, lon = rng.uniform(25, 65, n), rng.uniform(-125, -65, n)
    X = np.zeros((n, 16))
    base = 32 - 0.6 * (lat - 25)[:, None] + rng.normal(0, 0.6, (n, 1))
    X[:, 0:4] = base + np.array([-8, 0, 7, 1]) + 5
    X[:, 4:8] = X[:, 0:4] - 10
    X[:, 8:12] = np.exp(rng.normal(4.2 + 0.012 * (lon + 125)[:, None], 0.35, (n, 4)))
    X[:, 12:16] = X[:, 4:8] - 2
    npl = 40
    pl, po = rng.uniform(25, 65, npl), rng.uniform(-125, -65, npl)
    delta = np.zeros((npl, 2, 4, 3, 16))
    delta[..., :8] = 2.0 * np.array([1, 1.5])[None, :, None, None, None] * (1 + 0.1 * rng.random((npl, 1, 1, 3, 1)))
    delta[..., 12:] = 1.5
    delta[..., 8:12] = 0.05
    return V.Grid("synth", lat, lon, X, np.full(n, 225.0), rng.integers(0, 50, n), rng.integers(0, 50, n),
                  pl, po, rng.uniform(1e4, 1e6, npl), delta)


# --------------------------------------------------------------------------- metrics
def test_auc_and_tss_known_values():
    assert sdm.auc(np.array([3., 4]), np.array([1., 2])) == 1.0
    assert sdm.auc(np.array([1., 2]), np.array([3., 4])) == 0.0
    assert sdm.auc(np.array([1., 1]), np.array([1., 1])) == 0.5
    pos, neg = np.array([.9, .8, .7, .2]), np.array([.1, .2, .3, .75])
    t = sdm.best_threshold(pos, neg)
    assert sdm.tss(pos, neg, t) == max(sdm.tss(pos, neg, c) for c in np.r_[pos, neg])


def test_thresholds_order_and_boyce():
    pos = np.linspace(0.3, 1, 50)
    neg = np.linspace(0, 1, 500)
    assert sdm.threshold(pos, neg, "minpres") == pos.min()
    assert sdm.threshold(pos, neg, "minpres") <= sdm.threshold(pos, neg, "p05") <= sdm.threshold(pos, neg, "p10")
    rng = np.random.default_rng(1)
    allc = rng.random(5000)
    assert sdm.boyce(np.clip(rng.normal(0.85, 0.07, 200), 0, 1), allc) > 0.8       # presences at high scores
    assert abs(sdm.boyce(rng.random(200), allc)) < 0.5                              # random presences
    assert sdm.boyce(1 - np.clip(rng.normal(0.85, 0.07, 200), 0, 1), allc) < -0.5


def test_range_agreement_and_summaries():
    area = np.ones(6)
    a = sdm.range_agreement(np.array([1, 1, 0, 0, 0, 0], bool), np.array([1, 0, 1, 0, 0, 0], bool), area)
    assert a["sens"] == 0.5 and np.isclose(a["spec"], 0.75) and np.isclose(a["tss"], 0.25) and np.isclose(a["sorensen"], 0.5)
    lat, lon = np.array([40., 41, 42, 43]), np.full(4, -100.)
    s = sdm.summarise(lat, lon, np.ones(4), np.array([1, 1, 0, 0], bool), np.array([0, 1, 1, 0], bool))
    assert s["gain"] == 1 and s["loss"] == 1 and s["stable"] == 1 and s["change_pct"] == 0
    assert 100 < s["shift_km"] < 120 and (s["bearing"] < 1 or s["bearing"] > 359)       # one degree of latitude north
    assert sdm.angle_diff(350, 10) == 20
    assert np.isclose(sdm.bearing(0, 0, 0, 10), 90)


def test_block_folds_keep_blocks_together_and_balance():
    rng = np.random.default_rng(0)
    km = rng.uniform(0, 4000, (3000, 2))
    w = (rng.random(3000) < 0.1).astype(float)
    f = sdm.block_folds(km, 500, 5, w, seed=3)
    key = np.floor(km[:, 0] / 500) * 1000 + np.floor(km[:, 1] / 500)
    assert all(len(set(f[key == k])) == 1 for k in np.unique(key))                  # no block is split
    per = [w[f == i].sum() for i in range(5)]
    assert max(per) - min(per) <= 0.5 * np.mean(per)
    assert (f == sdm.block_folds(km, 500, 5, w, seed=3)).all()                      # deterministic


def test_mess_flags_novel_and_not_inside():
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, (2000, 3))
    m, which = sdm.mess(ref, np.array([[0, 0, 0], [0, 0, 5.0], [9, 0, 0]]))
    assert m[0] > 90 and m[1] < 0 and m[2] < 0 and which[1] == 2 and which[2] == 0
    d, flag = sdm.mahal_novelty(ref, np.array([[0, 0, 0], [8, 8, 8.0]]))
    assert not flag[0] and flag[1]


def test_dispersal_modes():
    lat = np.array([0., 0, 0, 0, 0]); lon = np.array([0., 1, 2, 3, 4])           # one degree ~ 111 km
    xyz = V.C.unit_xyz(lat, lon)
    now = np.array([1, 0, 0, 0, 0], bool)
    fut = np.array([1, 1, 1, 1, 0], bool)
    assert sdm.dispersal_limit(xyz, now, fut, None).sum() == 4                      # unlimited
    assert sdm.dispersal_limit(xyz, now, fut, 0).tolist() == [True, False, False, False, False]
    assert sdm.dispersal_limit(xyz, now, fut, 150).tolist() == [True, True, False, False, False]
    assert sdm.dispersal_limit(xyz, now, np.array([0, 1, 0, 0, 0], bool), 150).tolist() == [False, True, False, False, False]   # old cell lost


def test_select_uncorrelated_and_vif():
    rng = np.random.default_rng(0)
    a = rng.normal(size=1000)
    X = np.c_[a, a + 0.05 * rng.normal(size=1000), rng.normal(size=1000)]
    assert sdm.select_uncorrelated(X, ["a", "b", "c"], 0.7) == ["a", "c"]
    assert sdm.select_uncorrelated(X, ["a", "b", "c"], 0.7, priority=["b", "a", "c"]) == ["b", "c"]
    v = sdm.vif(X)
    assert v[0] > 50 and v[2] < 2


# --------------------------------------------------------------------------- models and pipeline
def test_every_model_learns_a_gaussian_niche():
    rng = np.random.default_rng(0)
    Xall = rng.normal(0, 1, (6000, 3))
    p = np.exp(-0.5 * ((Xall[:, 0] - 0.5) / 0.6) ** 2 - 0.5 * (Xall[:, 1] / 0.8) ** 2)
    occ = p > 0.5
    pres = Xall[np.nonzero(occ)[0][:150]]
    X, y = np.vstack([pres, Xall[:2000]]), np.r_[np.ones(len(pres), int), np.zeros(2000, int)]
    ens = sdm.fit_ensemble(X, y, Xall, sdm.ALGOS)
    sc, per = ens.score(Xall, per_model=True)
    for j, a in enumerate(ens.names):
        assert sdm.auc(per[occ, j], per[~occ, j]) > 0.85, a
    assert sdm.auc(sc[occ], sc[~occ]) > 0.95
    assert 0 <= sc.min() and sc.max() <= 1


def test_mahal_sigma_grows_with_distance():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (400, 4))
    m = sdm.Mahal().fit(X, np.ones(400, int))
    s = m.sigma(np.array([[0., 0, 0, 0], [2, 0, 0, 0], [6, 0, 0, 0]]))
    assert s[0] < s[1] < s[2] and s[0] < 1


def test_virtual_species_and_sampling_are_deterministic_and_truthful():
    g = synth_grid()
    cat = V.catalog(g)
    assert set(cat) == {"broad", "narrow", "cold_limited", "drought_limited", "heat_limited", "region_excluded", "patchy"}
    for sp in cat.values():
        now, fut = sp.present(g), sp.present(g, "SSP5-8.5", "2100")
        assert 0 < now.sum() < g.n and fut.shape == now.shape
    assert cat["narrow"].present(g).mean() < cat["broad"].present(g).mean()
    assert not cat["region_excluded"].present(g)[g.lon < np.quantile(g.lon, .35)].any()
    assert cat["cold_limited"].present(g, "SSP5-8.5", "2100").sum() > cat["cold_limited"].present(g).sum()      # warming relieves the cold limit
    assert cat["heat_limited"].present(g, "SSP5-8.5", "2100").sum() < cat["heat_limited"].present(g).sum()
    sp = cat["broad"]
    bias = V.bias_surface(g)
    assert bias.min() >= 0.03 - 1e-9 and np.isclose(bias.max(), 1)
    kw = dict(present=sp.present(g), suit=sp.suitability(g), n=200, bias=bias, false_pos=0, jitter=0)
    r1 = V.sample_occurrences(g, rng=np.random.default_rng(5), **kw)
    r2 = V.sample_occurrences(g, rng=np.random.default_rng(5), **kw)
    assert (r1 == r2).all() and len(set(r1)) == len(r1) and sp.present(g)[r1].all()
    hi = V.sample_occurrences(g, rng=np.random.default_rng(5), bias_power=3.0, **kw)
    assert bias[hi].mean() > bias[V.sample_occurrences(g, rng=np.random.default_rng(5), bias_power=0.0, **kw)].mean()


def test_grid_future_and_coarsen():
    g = synth_grid()
    X1 = g.climate("SSP5-8.5", "2100")
    assert 2.5 < (X1[:, 0] - g.X[:, 0]).mean() < 4.5 and (X1[:, 8:12] > g.X[:, 8:12]).all()
    assert g.climate("SSP5-8.5", "2100") is X1                                     # cached
    c = g.coarsen(5)
    assert c.n < g.n and np.isclose(c.area.sum(), g.area.sum()) and len(c.parent) == g.n
    assert np.allclose(c.X[c.parent[0]], g.X[c.parent == c.parent[0]].mean(0))


def test_run_sdm_end_to_end_recovers_range_and_shift():
    g = synth_grid(2500)
    sp = V.catalog(g)["broad"]
    s = sdm.Settings(algos=("gam", "gbm", "mahal"), n_bg=1500, n_ref=1500, seed=1, cv_folds=3, block_km=800)
    r = V.evaluate(g, sp, n=150, seed=1, settings=s, scenarios=(("SSP5-8.5", "2100"),))
    assert r["n_rec"] > 100 and r["cv_folds"] >= 2
    assert r["now_auc_truth"] > 0.9 and r["now_sorensen"] > 0.7
    assert 0.0 <= r["5-8_2100_novel_share"] <= 1 and r["5-8_2100_class_agree"] > 0.6
    assert r["5-8_2100_none_disp_area_ratio"] <= r["5-8_2100_unlimited_disp_area_ratio"] + 1e-9 or np.isnan(r["5-8_2100_none_disp_area_ratio"])
    r2 = V.evaluate(g, sp, n=150, seed=1, settings=s, scenarios=(("SSP5-8.5", "2100"),))
    assert r["now_sorensen"] == r2["now_sorensen"] and r["cv_auc"] == r2["cv_auc"]       # deterministic


def test_real_grid_loads_and_projects():
    g = V.load_grid("na")
    assert g.n == 97488 and len(g.plat) == 790 and g.X.shape == (97488, 16)
    assert -50 < g.X[:, 0].min() and g.X[:, 0].max() < 50 and g.X[:, 8:12].min() >= 0
    dt = g.climate("SSP5-8.5", "2100")[:, :8].mean() - g.X[:, :8].mean()
    d2 = g.climate("SSP2-4.5", "2050")[:, :8].mean() - g.X[:, :8].mean()
    assert 3 < dt < 9 and 0.5 < d2 < dt                                            # SSP5-8.5 2100 warms far more than SSP2-4.5 2050
