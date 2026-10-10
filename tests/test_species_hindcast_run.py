"""Plumbing test of the BBS hindcast on the W3 synthetic climate (known truth). Not a test of ecological accuracy."""
import numpy as np
import pandas as pd
from ctw.species import grid, hindcast as H, hindcast_run as HR, pipeline as PL

SPEC = grid.GridSpec(120, 240)


def make_routes(src, n=700, seed=0):
    rng = np.random.default_rng(seed)
    land = grid.land_mask(src)
    rr, cc = np.nonzero(land[10:110])
    rr = rr + 10
    pick = rng.choice(len(rr), min(n, len(rr)), replace=False)
    r, c = rr[pick], cc[pick]
    df = pd.DataFrame(dict(country=840, state=1, route=np.arange(len(r)), row=r, col=c, lat=SPEC.lat(r), lon=SPEC.lon(c)))
    return df


def presence(src, routes, aou=1):
    """Truth: present where bio1 within [10, 30] (a cold limit that moves with the +0.95 C window warming)."""
    out = {}
    for w, k in ((HR.W1, "p1"), (HR.W2, "p2")):
        x = src.baseline_points(routes.row.values, routes.col.values, ("bio1",), window=w)[:, 0]
        out[k] = np.isfinite(x) & (x >= 12.0) & (x <= 30)
    return pd.DataFrame(dict(country=840, state=1, route=routes.route.values, AOU=aou, p1=out["p1"], p2=out["p2"]))


def test_window_source_defaults_to_window():
    src = grid.SyntheticClimate(SPEC, n_models=2)
    ws = HR.WindowSource(src, HR.W2)
    r, c = np.array([60, 61]), np.array([100, 101])
    a = ws.baseline_points(r, c, ("bio1",))
    b = src.baseline_points(r, c, ("bio1",), window=HR.W2)
    assert np.allclose(a, b, equal_nan=True) and not np.allclose(a, src.baseline_points(r, c, ("bio1",)), equal_nan=True)


def test_hindcast_bbs_end_to_end():
    src = grid.SyntheticClimate(SPEC, n_models=2)
    routes = make_routes(src)
    pres = presence(src, routes)
    assert pres.p1.sum() > 60
    q = routes.sample(frac=0.7, random_state=1)
    out, fits = HR.hindcast_bbs({"virtual": 1}, routes, q, pres, SPEC, src, cfg=PL.FitConfig(n_jobs=1, check_model=False, cv_folds=3), n_boot=40,
                                log=lambda *a: None)
    assert set(out) == {"blocked", "fit_cells"}
    for mode, (results, g, v, cs) in out.items():
        r = results["virtual"]
        assert r["auc2"] > 0.8, mode                         # the climate niche is recoverable and transfers to window 2
        assert g["status"] == "insufficient data"           # one species is never a conclusive group
        assert not v["virtual"]["tier1"]
        assert "INSUFFICIENT DATA" in H.report("bbs", "synthetic", results, g, v)
    # the blocked variant scores every comparable cell with a model that did not see it; its CV skill is presence-absence based
    cvb = out["blocked"][0]["virtual"]["cv"]
    assert cvb["source"].startswith("presence-absence") and cvb["auc"] > 0.8
    sc = HR.score_cells(fits["virtual"], src, q.row.values, q.col.values)
    assert np.abs(sc.score2 - sc.score1).mean() > 0
