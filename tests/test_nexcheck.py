"""Unit tests for the NEX-GDDP delta / sigma logic of `ctw nexcheck` and the monthly climatologies of the extremes pass
(synthetic data). Run: python -m pytest tests/test_nexcheck.py or python tests/test_nexcheck.py."""
import pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ctw import common as C, extremes as E, nexcheck as N

MCFG = {"ppt_ratio": [0.2, 5.0], "vap_ratio": [0.5, 3.0]}
MIDX = np.r_[np.arange(12), [12, 14]]


def base_mon(nt=3):
    m = np.arange(12)
    tx = 15 + 10 * np.sin((m - 3) / 12 * 2 * np.pi)
    return {"tmax": np.tile(tx, (nt, 1)), "tmin": np.tile(tx - 8, (nt, 1)), "ppt": np.full((nt, 12), 80.0),
            "vap": np.tile(0.4 + 0.02 * tx, (nt, 1))}


def test_month_index_calendars():
    for n, d in ((360, 30), (365, 31), (366, 31)):
        mi = E.month_index(n)
        assert len(mi) == n and mi[0] == 0 and mi[-1] == 11 and (mi == 0).sum() == d
    assert (E.month_index(365) == 1).sum() == 28 and (E.month_index(366) == 1).sum() == 29
    assert len(E.month_index(300)) == 300 and E.month_index(300).max() == 11


def test_monthly_means():
    n = 365
    mi = E.month_index(n)
    tx = np.tile((mi + 1.0)[:, None], (1, 2)); tn = tx - 5; pr = np.ones((n, 2)); rh = np.full((n, 2), 60.0)
    tx[0, 1] = np.nan
    o = E.monthly_means(tx, tn, pr, rh)
    assert o.shape == (4, 12, 2)
    assert np.allclose(o[0, :, 0], np.arange(1, 13)) and np.allclose(o[1, :, 0], np.arange(1, 13) - 5)
    assert np.allclose(o[2], 1) and np.allclose(o[3], 60)
    assert np.isnan(o[0, 0, 1]) and np.isfinite(o[0, 1:, 1]).all()          # only the January of place 1 is missing


def test_pack_deltas_known_change():
    M, P, S, NT = 2, 1, 1, 3
    b = np.zeros((M, 4, NT, 12)); b[:, 0] = 20; b[:, 1] = 10; b[:, 2] = 2.0; b[:, 3] = 70
    f = np.zeros((M, P, S, 4, NT, 12)); f[:, 0, 0, 0] = 23; f[:, 0, 0, 1] = 12; f[:, 0, 0, 2] = 2.4; f[:, 0, 0, 3] = 70
    b[1, 2, 0, :] = 0.0                                                     # a dry base month -> ratio 1
    dtx, dtn, rp, rv = N.pack_deltas(b, f)
    assert dtx.shape == (M, P, S, NT, 12)
    assert np.allclose(dtx, 3) and np.allclose(dtn, 2)
    assert np.allclose(rp[0], 1.2) and np.allclose(rp[1, :, :, 0], 1.0) and np.allclose(rp[1, :, :, 1], 1.2)
    want = C.sat_vap(17.5) / C.sat_vap(15.0)                                # same relative humidity, warmer air
    assert np.allclose(rv, want) and 1.1 < want < 1.3


def test_project_zero_change_is_identity_and_ratios_clipped():
    bm = base_mon()
    z = np.zeros((3, 12)); one = np.ones((3, 12))
    v0 = N.project(bm, (z, z, one, one), MCFG)
    ref = C.seasonalize({k: bm[k].T for k in N.MON}).T
    assert np.allclose(v0, ref)
    v = N.project(bm, (z + 3, z + 3, one * 50, one * 50), MCFG)             # ratios far outside the range are limited
    assert np.allclose(v[:, 8:12], ref[:, 8:12] * 5.0)                      # precipitation x 5 (the limit), seasonal sums
    assert np.allclose(v[:, :4], ref[:, :4] + 3)


def test_ensemble_mean_of_projections_matches_manual():
    bm = base_mon()
    ds = [(np.full((3, 12), a), np.full((3, 12), a), np.full((3, 12), r), np.ones((3, 12))) for a, r in ((1.0, 1.0), (3.0, 1.4))]
    ens = np.mean([N.project(bm, d, MCFG) for d in ds], axis=0)
    manual = N.project(bm, (np.full((3, 12), 2.0), np.full((3, 12), 2.0), np.full((3, 12), 1.2), np.ones((3, 12))), MCFG)
    assert np.allclose(ens[:, :8], manual[:, :8]) and np.allclose(ens[:, 8:12], manual[:, 8:12])   # both linear here


def test_sigma_between():
    K = len(MIDX)
    Mx = np.tile(np.eye(K), (2, 1, 1))              # unit metric: sigma distance = plain distance in the measures
    A = np.tile(np.linspace(0, 10, C.NV), (2, 1))
    assert np.allclose(N.sigma_between(A, A, Mx, MIDX), 0, atol=1e-6)
    B = A.copy(); B[1, 0] += 2.0                    # place 1: 2 units in one measure
    s = N.sigma_between(A, B, Mx, MIDX)
    assert abs(s[0]) < 1e-6 and abs(s[1] - float(C.chi_to_sigma(2.0, K)[0])) < 1e-9
    Mx2 = Mx.copy(); Mx2[1] *= 0.5                  # a place with twice the variability sees the same change as smaller
    assert N.sigma_between(A, B, Mx2, MIDX)[1] < s[1]
    assert s[1] < 2.0                               # half-normal equivalent is below the raw distance in 14 dimensions


def test_best_cell():
    K = len(MIDX)
    rng = np.random.default_rng(1)
    raw = np.abs(rng.normal(5, 2, (50, C.NV)))
    tr = C.transform(raw)[:, MIDX]
    q = raw[17] + 0.01
    assert N.best_cell(q, np.eye(K), tr, MIDX) == 17
    Mk = np.diag(np.r_[1000.0, np.ones(K - 1)])     # a metric that only cares about the first measure
    j = N.best_cell(raw[17] + np.r_[0.0, np.full(C.NV - 1, 5.0)], Mk, tr, MIDX)
    assert abs(tr[j, 0] - tr[17, 0]) <= abs(tr[:, 0] - tr[17, 0])[np.argsort(abs(tr[:, 0] - tr[17, 0]))[1]] + 1e-9


def test_classify_thresholds():
    F = lambda d, m: N.classify(np.array(d, float).reshape(2, 2), np.array(m, bool).reshape(2, 2))
    assert F([0.1, 0.2, 0.3, 0.4], [0, 0, 0, 0]) == "ok"
    assert F([0.1, 0.2, 0.3, 0.1], [0, 0, 0, 1]) == "moderate"          # moved, but a small difference: not high
    assert F([0.1, 0.5, 0.3, 0.1], [0, 0, 0, 0]) == "moderate"
    assert F([0.1, 0.2, 0.99, 0.1], [0, 0, 0, 0]) == "moderate"
    assert F([0.1, 0.2, 1.0, 0.1], [0, 0, 0, 0]) == "high"
    assert F([0.1, 0.6, 0.3, 0.1], [0, 1, 0, 0]) == "high"              # moved and >= 0.5
    assert F([np.nan] * 4, [0] * 4) is None
    assert F([np.nan, 0.2, np.nan, np.nan], [0, 0, 0, 0]) == "ok"       # a missing scenario does not hide the others


def test_summary_line():
    doc = {"n_models": 13, "thresholds": {"sigma_moderate": 0.5, "sigma_high": 1.0, "moved_km": 500.0},
           "summary": {"ok": 80, "moderate": 15, "high": 5, "nodata": 2, "median_dsigma": 0.21, "p95_dsigma": 0.9}}
    s = N.summary_line(doc)
    assert "80% ok" in s and "15% moderate" in s and "5% high" in s and "13 models" in s


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
