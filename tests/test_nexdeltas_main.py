"""NEX-GDDP-CMIP6 changes as the main projection's source ([deltas] source = "nex"): loading, blending with the CMIP6 change,
the per-model record, the resolution check against native-grid CMIP6 and the extremes parts (synthetic data).
Run: python -m pytest tests/test_nexdeltas_main.py or python tests/test_nexdeltas_main.py.

The end-to-end "no data/nexdeltas.npz -> bit-identical results" check runs analogs on a synthetic work directory and compares every
array of results.npz byte for byte (done for the change that added this; see the CHANGELOG); here the pieces that guarantee it."""
import pathlib, sys, tempfile
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ctw import common as C, extremes as E, nexcheck as N
from ctw.analogs import deltas, apply_delta

MCFG = {"ppt_ratio": [0.2, 5.0], "vap_ratio": [0.5, 3.0]}
CFG = {"periods": {"keys": ["2050", "2100"]}, "scenarios": {"ids": ["ssp126", "ssp245", "ssp370", "ssp585"]}, "gates": {"moved_km": 500},
       "deltas": {"source": "nex"}, "matching": MCFG}
LABELS = ["A", "B", "C"]
T = pd.DataFrame({"label": LABELS, "lat": [35.0, 1.3, -33.9], "lon": [-78.6, 103.8, 151.2], "g": [0, 1, 1]})


def cm_delta(nt=3, dt=2.0, r=1.1):
    b = np.stack([np.full((nt, 12), 20.0), np.full((nt, 12), 10.0), np.full((nt, 12), 3.0), np.full((nt, 12), 0.008)])
    f = np.stack([b[0] + dt, b[1] + dt, b[2] * r, b[3] * 1.12])
    return deltas(b, f, MCFG)


def nex_file(path, models=("M1",), scen=("ssp245", "ssp585"), labels=("C", "A", "B"), periods=("2050", "2100")):
    M, P, S, NT = len(models), len(periods), len(scen), len(labels)
    sh = (M, P, S, NT, 12)
    dtx = np.full(sh, 3.0); dtn = np.full(sh, 2.5); rp = np.full(sh, 1.3); rv = np.full(sh, 1.2)
    dtx[:, :, :, 0] = np.nan                                    # file place 0 ("C") off the land mask
    rv[:, :, :, 1] = np.nan                                     # file place 1 ("A"): no humidity (a model without hurs)
    rp[:, :, :, 2] = 9.0                                        # file place 2 ("B"): a ratio beyond the limit
    np.savez_compressed(path, dtx=dtx.astype("float16"), dtn=dtn.astype("float16"), rp=rp.astype("float16"), rv=rv.astype("float16"),
                        models=np.array(models), scen=np.array(scen), periods=np.array(periods), labels=np.array(labels),
                        lat=np.zeros(NT, "float32"), lon=np.zeros(NT, "float32"))
    return pathlib.Path(path)


def test_load_main_absent_or_cmip6_gives_none():
    with tempfile.TemporaryDirectory() as d:
        assert N.load_main(CFG, T, pathlib.Path(d) / "nexdeltas.npz") is None             # no file: the CMIP6-only build
        p = nex_file(pathlib.Path(d) / "nexdeltas.npz")
        assert N.load_main({**CFG, "deltas": {"source": "cmip6"}}, T, p) is None
        assert N.load_main({**CFG, "periods": {"keys": ["2050"]}}, T, p) is None            # built for other periods
        assert N.load_main(CFG, T, p) is not None
        assert N.load_main({k: v for k, v in CFG.items() if k != "deltas"}, T, p) is not None   # default source is "nex"


def test_get_reorders_places_and_misses():
    with tempfile.TemporaryDirectory() as d:
        X = N.load_main(CFG, T, nex_file(pathlib.Path(d) / "nexdeltas.npz"))
        assert X.get("M2", 0, "ssp245") is None and X.get("M1", 0, "ssp126") is None and X.get("M1", 5, "ssp245") is None
        dtx, dtn, rp, rv = X.get("M1", 1, "ssp585")
        assert dtx.shape == (3, 12)
        assert np.isfinite(dtx[0]).all() and np.isfinite(dtx[1]).all() and np.isnan(dtx[2]).all()     # "C" is last here
        assert np.isnan(rv[0]).all() and np.allclose(rv[1], 1.2, atol=1e-3)
        T2 = pd.concat([T, pd.DataFrame({"label": ["D"], "lat": [0.0], "lon": [0.0], "g": [1]})], ignore_index=True)
        X2 = N.load_main(CFG, T2, nex_file(pathlib.Path(d) / "n2.npz"))
        assert np.isnan(X2.get("M1", 0, "ssp245")[0][3]).all()                                        # a place added later


def test_blend_uses_nex_where_present_and_falls_back():
    d_cm = cm_delta()
    with tempfile.TemporaryDirectory() as d:
        X = N.load_main(CFG, T, nex_file(pathlib.Path(d) / "nexdeltas.npz"))
        d, used = N.blend(d_cm, X.get("M1", 0, "ssp245"), MCFG)
    assert used.tolist() == [True, True, False]
    assert np.allclose(d[0][:2], 3.0) and np.array_equal(d[0][2], d_cm[0][2])                   # C: CMIP6 temperature change
    assert np.allclose(d[1][:2], 2.5)
    assert np.allclose(d[2][0], 1.3, atol=1e-3) and np.allclose(d[2][1], 5.0)                   # B: ratio limited to ppt_ratio
    assert np.array_equal(d[3][0], d_cm[3][0])                                                   # A: no NEX humidity -> CMIP6 huss ratio
    assert np.allclose(d[3][1], 1.2, atol=1e-3) and np.array_equal(d[3][2], d_cm[3][2])


def test_blend_without_nex_values_is_bit_identical():
    d_cm = cm_delta()
    nan = tuple(np.full((3, 12), np.nan) for _ in range(4))
    d, used = N.blend(d_cm, nan, MCFG)
    assert not used.any()
    for a, b in zip(d, d_cm):
        assert a.dtype == b.dtype and a.tobytes() == b.tobytes()
    extra = d_cm + (np.full((3, 12), 1.05),)                                                    # the rsds ratio (extras) stays CMIP6
    d2, _ = N.blend(extra, nan, MCFG)
    assert len(d2) == 5 and d2[4] is extra[4]


def test_blend_matches_nex_projection():
    """Where NEX-GDDP covers a place, the main projection is exactly nexcheck.project on the NEX change (one delta method)."""
    bm = {"tmax": np.full((3, 12), 25.0), "tmin": np.full((3, 12), 12.0), "ppt": np.full((3, 12), 60.0), "vap": np.full((3, 12), 1.2)}
    with tempfile.TemporaryDirectory() as d:
        X = N.load_main(CFG, T, nex_file(pathlib.Path(d) / "nexdeltas.npz"))
        dn = X.get("M1", 0, "ssp245")
    d, used = N.blend(cm_delta(), dn, MCFG)
    mine = C.seasonalize({v: apply_delta(bm, d)[v].T for v in N.MON}).T
    ref = N.project(bm, dn, MCFG)
    assert np.allclose(mine[1], ref[1])


def test_delta_summary_and_line():
    names = ["M1", "M2"]
    S0 = N.delta_summary(CFG, {}, names, np.zeros(3, bool))
    assert S0["source"] == "cmip6" and S0["label"] == {"M1": "cmip6", "M2": "cmip6"} and "nexdeltas" in S0["why"]
    assert "every model" in N.delta_line(S0)
    NT, P, S, E_ = 3, 2, 4, 2
    sh = np.zeros((2, P, S)); sh[0, :, 1] = sh[0, :, 3] = 1.0; sh[1] = 0.5
    km = np.full((NT, P, S, E_), 10.0); km[0, 0, 1, 0] = 900.0
    R = {"delta_nex_share": sh, "src_km": km, "src_dbest": np.full((NT, P, S, E_), 0.2), "src_dist": np.full((NT, P, S, E_), 0.4)}
    S1 = N.delta_summary(CFG, R, names, np.array([False, False, True]), T.g.values)
    assert S1["label"] == {"M1": "mixed", "M2": "nex"} and S1["models"]["M1"]["ssp245"] == 1.0 and S1["n_nex"] == 2
    e = S1["effect"]["all"]
    assert e["n_places"] == 2 and abs(e["moved_share"] - 1 / 32) < 1e-4 and e["places_moved_share"] == 0.5
    assert e["median_dbest"] == 0.2 and e["median_dist"] == 0.4
    assert "north_america" in S1["effect"] and "moved more than 500 km" in N.delta_line(S1)


def test_compare_raw_identical_projection_is_zero():
    rng = np.random.default_rng(3)
    NT, P, S, NM = 3, 2, 4, 2
    midx = np.r_[np.arange(12), [12, 14]]
    raw = np.abs(rng.normal(10, 3, (NT, C.NV)))
    fut = np.broadcast_to(raw[:, None, None, None], (NT, P, S, NM, C.NV)).copy()
    pool = np.abs(rng.normal(10, 3, (40, C.NV))); pool[:3] = raw
    tr = C.transform(pool)[:, midx]
    sh = np.zeros((NM, P, S)); sh[0, :, 1] = 1.0
    fc = fut.copy(); fc[:, :, 1, 0, :4] += 10.0                          # CMIP6 differs where NEX was used
    ctx = {"R": {"fut": fut, "fut_cmip6": fut.copy(), "delta_nex_share": sh}, "T": T,
           "cfg": {**CFG, "models": {"list": [{"name": "M1"}, {"name": "M2"}]}}, "midx": midx,
           "Msh": np.tile(np.eye(len(midx)), (NT, 1, 1)), "bad": np.zeros(NT, bool), "G": np.array([0, 1, 1]),
           "pools": {0: (tr, np.zeros(40), np.arange(40.0)), 1: (tr, np.zeros(40), np.arange(40.0))}}
    dsig, moved, info = N.compare_raw(ctx, N.settings({}))
    assert info["name"] == "cmip6" and info["models"] == ["M1"] and info["scenarios"] == ["ssp245"]
    assert np.allclose(dsig[:, :, 1], 0, atol=1e-6) and np.allclose(moved[:, :, 1], 0) and np.isnan(dsig[:, :, 0]).all()
    ctx["R"]["fut_cmip6"] = fc
    dsig, moved, info = N.compare_raw(ctx, N.settings({}))
    assert (dsig[:, :, 1] > 1.0).all() and np.isnan(dsig[:, :, 0]).all()


def test_annual_indices_without_humidity():
    n = 365
    tx = np.full((n, 2), 36.0); tn = np.full((n, 2), 22.0); pr = np.ones((n, 2)); rh = np.full((n, 2), 60.0)
    rh[:, 1] = np.nan                                                    # a model NEX-GDDP publishes without hurs
    o = E.annual_indices(tx, tn, pr, rh)
    assert np.isfinite(o[:, 0]).all() and np.isnan(o[4, 1]) and np.isfinite(np.delete(o[:, 1], 4)).all()
    mm = E.monthly_means(tx, tn, pr, rh)
    assert np.isnan(mm[3, :, 1]).all() and np.isfinite(mm[:3, :, 1]).all()


def test_merge_parts():
    NT, P, NI = 3, 2, E.NI
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        lab = np.array(LABELS)
        np.savez(d / "M1__base.npz", base=np.ones((NI, NT), "float32"), mon_base=np.ones((4, NT, 12), "float32"), labels=lab, scen=np.array(["ssp245"]))
        np.savez(d / "M1__ssp585.npz", fut=np.full((P, 1, NI, NT), 5, "float32"), mon_fut=np.full((P, 1, 4, NT, 12), 2, "float32"), labels=lab, scen=np.array(["ssp585"]))
        np.savez(d / "M1__ssp126.npz", fut=np.full((P, 1, NI, NT), 3, "float32"), mon_fut=np.full((P, 1, 4, NT, 12), 1.5, "float32"), labels=lab, scen=np.array(["ssp126"]))
        np.savez(d / "M2__ssp245.npz", fut=np.full((P, 1, NI, NT), 5, "float32"), labels=lab, scen=np.array(["ssp245"]))   # no baseline
        np.savez(d / "M3.npz", base=np.zeros((NI, NT), "float32"), fut=np.stack([np.full((NI, NT), 7.0), np.full((NI, NT), 8.0)], 0)[None].repeat(P, 0).astype("float32"),
                 mon_base=np.zeros((4, NT, 12), "float32"), mon_fut=np.ones((P, 2, 4, NT, 12), "float32"), labels=lab, scen=np.array(["ssp245", "ssp585"]))
        scen = ["ssp126", "ssp245", "ssp370", "ssp585"]
        names, Z = E.merge_parts(sorted(d.glob("*.npz")), scen, P)
    assert names == ["M1", "M3"]
    z1, z3 = Z
    assert z1["have"].tolist() == [True, False, False, True] and z3["have"].tolist() == [False, True, False, True]
    assert z1["fut"].shape == (P, 4, NI, NT) and np.all(z1["fut"][:, 0] == 3) and np.isnan(z1["fut"][:, 1]).all() and np.all(z1["fut"][:, 3] == 5)
    assert z1["mon_fut"].shape == (P, 4, 4, NT, 12) and np.all(z1["mon_fut"][:, 0] == 1.5) and np.isnan(z1["mon_fut"][:, 2]).all()
    assert np.all(z3["fut"][:, 1] == 7) and np.all(z3["fut"][:, 3] == 8)
    dtx, dtn, rp, rv = N.pack_deltas(np.stack([z["mon_base"] for z in Z]), np.stack([z["mon_fut"] for z in Z]))
    assert np.allclose(dtx[0, :, 0], 0.5) and np.isnan(dtx[0, :, 1]).all()                      # a missing scenario -> NaN -> CMIP6 there


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
