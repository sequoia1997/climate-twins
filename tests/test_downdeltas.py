"""Unit tests for the WorldClim / AdaptWest downscaled-change extraction helpers and the multi-source nexcheck comparison
(synthetic arrays only). Run: python -m pytest tests/test_downdeltas.py or python tests/test_downdeltas.py."""
import pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ctw import common as C, downdeltas as D, nexcheck as N

MIDX = np.r_[np.arange(12), [12, 14]]


def test_make_delta():
    b = {"tmax": np.full((2, 12), 10.0), "tmin": np.full((2, 12), 2.0), "ppt": np.full((2, 12), 50.0)}
    b["ppt"][0, 3] = 0.2                                                  # dry month -> ratio 1
    f = {"tmax": b["tmax"] + 3, "tmin": b["tmin"] + 2.5, "ppt": b["ppt"] * 1.2}
    f["tmax"][1, 0] = np.nan                                              # a missing future value stays missing
    dx, dn, rp = D.make_delta({k: v[None, None] for k, v in f.items()}, b)
    assert dx.shape == (1, 1, 2, 12)
    assert np.allclose(dx[0, 0, 0], 3) and np.allclose(dn, 2.5) and np.isnan(dx[0, 0, 1, 0])
    assert np.isclose(rp[0, 0, 0, 3], 1.0) and np.isclose(rp[0, 0, 0, 0], 1.2) and np.isclose(rp[0, 0, 1, 5], 1.2)
    f["ppt"][1, 1] = 1e9
    assert D.make_delta({k: v[None] for k, v in f.items()}, b)[2].max() == 100                 # clipped


def test_nearest_valid_and_sample():
    H, W = 18, 36                                                         # 10 degree pixels, north-up global grid
    valid = np.ones((H, W), bool)
    valid[9, 18] = False                                                  # the pixel of (lat -5, lon 5)... row 9 = lat -0..-10
    lat, lon = np.array([-5.0, 45.0, 89.9]), np.array([5.0, -179.9, 179.9])
    ri, rj = D.nearest_valid(valid, lat, lon, -180, 90, 10, 10, radius=2)
    assert (ri[0], rj[0]) != (9, 18) and abs(ri[0] - 9) <= 1 and abs(rj[0] - 18) <= 1     # moved to a neighbour
    assert (ri[1], rj[1]) == (4, 0) and (ri[2], rj[2]) == (0, 35)
    r0, _ = D.nearest_valid(np.zeros((H, W), bool), lat, lon, -180, 90, 10, 10, radius=2)
    assert (r0 == -1).all()
    arr = np.arange(12)[:, None, None] * np.ones((12, H, W))
    arr[:, ri[1], rj[1]] += 100
    out = D.sample_pixels(arr, ri, rj)
    assert out.shape == (3, 12) and np.allclose(out[1], np.arange(12) + 100) and np.allclose(out[2], np.arange(12))
    out = D.sample_pixels(arr, np.array([-1, 4]), np.array([-1, 0]))
    assert np.isnan(out[0]).all() and np.isfinite(out[1]).all()
    v2 = np.ones((H, W), bool)
    v2[:, 0] = False
    lon_wrap = D.nearest_valid(v2, np.array([0.0]), np.array([-179.0]), -180, 90, 10, 10, radius=1)
    assert lon_wrap[1][0] == 35 and lon_wrap[0][0] == 9                    # column 0 invalid -> wraps to the last column


def test_neighbour_mean():
    a = np.arange(25.0).reshape(5, 5)
    a[2, 2] = np.nan
    nb = [(np.array([1, 3]), np.array([1, 3]), np.array([1, 3, 2]), np.array([1, 3, 2]), np.array([1.0, 1.0, 5.0])),
          (np.array([2]), np.array([2]), np.array([2, 0]), np.array([2, 0]), np.array([0.0, 3.0]))]
    m = D.neighbour_mean(a, nb)
    assert np.isclose(m[0], (a[1, 1] + a[3, 3]) / 2) and np.isclose(m[1], a[0, 0])        # empty disc -> nearest valid cell


def test_parse_aw_key_and_products():
    g = ["MIROC6", "ACCESS-CM2"]
    assert D.parse_aw_key("CMIP6v73/MIROC6/ssp245/MIROC6_ssp245_2041-2060_monthly.zip", g) == ("MIROC6", "ssp245", 2041)
    assert D.parse_aw_key("CMIP6v73/Ensemble/13GCMs_ensemble_ssp585_2081-2100_monthly.zip", g) == ("ensemble", "ssp585", 2081)
    assert D.parse_aw_key("CMIP6v73/x/readme.txt", g) == (None, None, None)
    keys = [("CMIP6v73/normals/Normal_1991_2020_monthly.zip", 5), ("CMIP6v73/13GCMs_ensemble_ssp245_2041-2060_bioclim.zip", 4),
            ("CMIP6v73/13GCMs_ensemble_ssp245_2041-2060_monthly.zip", 9), ("CMIP6v73/13GCMs_ensemble_ssp126_2041-2060_monthly.zip", 9),
            ("CMIP6v73/13GCMs_ensemble_ssp585_2081-2100_monthly.zip", 7), ("CMIP6v73/MIROC6_ssp245_2041-2060_monthly.zip", 3), ("CMIP6v73/notes.txt", 1)]
    s = {**D.DEFAULTS}
    pr = D.aw_products(s, C.config(), keys)
    assert set(pr) == {"ensemble", "MIROC6"}
    assert pr["ensemble"][("ssp245", "2050")][0].endswith("ssp245_2041-2060_monthly.zip")     # the monthly file wins over bioclim
    assert ("ssp126", "2050") not in pr["ensemble"] and ("ssp585", "2100") in pr["ensemble"]  # only configured scenarios
    names = [f"x/{v}{m:02d}.tif" for v in ("Tmax", "Tmin", "PPT") for m in range(1, 13)] + ["x/readme.txt", "x/Tmax13.tif"]
    mem = D._aw_members(names)
    assert len(mem) == 36 and mem[("ppt", 12)] == "x/PPT12.tif"


def synth_files(tmp, src, names, T, dt=3.0, base_t=10.0):
    NT = len(T)
    lab = T.label.values.astype(str)
    B = {"tmax": np.full((NT, 12), base_t + 5), "tmin": np.full((NT, 12), base_t - 5), "ppt": np.full((NT, 12), 60.0)}
    C.save(tmp / f"{src}-base.npz", labels=lab, **B)
    for k, n in enumerate(names):
        F = {"tmax": np.full((2, 2, NT, 12), base_t + 5 + dt + k), "tmin": np.full((2, 2, NT, 12), base_t - 5 + dt + k),
             "ppt": np.full((2, 2, NT, 12), 66.0)}
        C.save(tmp / f"{src}-{n}.npz", labels=lab, scen=np.array(["ssp245", "ssp585"]), periods=np.array(["2050", "2100"]), **F)


def targets(nt=4):
    return pd.DataFrame({"label": [f"P{i}" for i in range(nt)], "lat": np.linspace(30, 60, nt), "lon": np.linspace(-120, -70, nt),
                         "g": np.zeros(nt, int)})


def test_aggregate_roundtrip(tmp_path=None):
    import tempfile
    tmp = pathlib.Path(tmp_path or tempfile.mkdtemp())
    wd = tmp / "dd"
    T = targets()
    synth_files(wd, "wc", ["MIROC6", "MRI-ESM2-0"], T)
    synth_files(wd, "aw", ["ensemble"], T)
    old = C.targets
    C.targets = lambda: T
    try:
        out = D.aggregate(C.config(), out=tmp / "dd.npz", work=wd)
    finally:
        C.targets = old
    Z = C.load(out)
    assert list(Z["wc_models"]) == ["MIROC6", "MRI-ESM2-0"] and Z["wc_dtx"].shape == (2, 2, 2, 4, 12) and Z["wc_dtx"].dtype == np.float16
    assert np.allclose(Z["wc_dtx"][0], 3) and np.allclose(Z["wc_dtx"][1], 4) and np.allclose(Z["wc_rp"], 1.1, atol=1e-3)
    assert list(Z["aw_models"]) == ["ensemble"] and list(Z["aw_scen"]) == ["ssp245", "ssp585"]
    srcs = N.load_sources(tmp / "none.npz", out)
    assert [x.name for x in srcs] == ["wc", "aw"] and srcs[0].get("dtx", 1, 0, 0).shape == (4, 12)
    assert np.isnan(srcs[0].get("rv", 0, 0, 0)).all()                       # no humidity from these sources


def test_combine_and_select_models():
    assert N.combine({"nex": "ok", "wc": "high", "aw": "moderate"}) == ("high", ["wc"])
    assert N.combine({"nex": "high", "wc": "high", "aw": None}) == ("high", ["nex", "wc"])
    assert N.combine({"nex": None}) == (None, [])
    assert N.combine({"a": "ok", "b": "moderate"}) == ("moderate", ["b"])
    src = N.Source("wc", ["A", "B", "C", "X"], ["ssp245"], ["p"], {})
    assert N.select_models(src, ["A", "B", "C", "D"], [0, 1], 3) == ([0, 1, 2], [0, 1, 2], "overlap")
    assert N.select_models(src, ["A", "B", "C", "D"], [0, 3], 4) == ([0, 1, 2, 3], [0, 3], "mean")      # too few shared: use the mean


def test_compare_multi_source():
    cfg = C.config()
    mcfg, K = cfg["matching"], len(MIDX)
    NT, P = 4, 2
    T = targets(NT)
    mn = [m["name"] for m in C.models(cfg)]
    rng = np.random.default_rng(3)
    m = np.arange(12)
    tx = 15 + 10 * np.sin((m - 3) / 12 * 2 * np.pi)
    bm = {"tmax": np.tile(tx, (NT, 1)), "tmin": np.tile(tx - 8, (NT, 1)), "ppt": np.full((NT, 12), 80.0), "vap": np.tile(0.4 + 0.02 * tx, (NT, 1))}
    sc = cfg["scenarios"]["ids"]
    M = len(mn)
    dts = np.linspace(1.0, 4.0, M)                                          # each model's warming
    fut = np.zeros((NT, P, len(sc), M, C.NV))
    dsrc = np.zeros((M, P, 2, NT, 12))
    for j in range(M):
        for p in range(P):
            for si, ssp in enumerate(sc):
                z = np.full((NT, 12), dts[j] * (p + 1) * (1 + si * 0.2))
                fut[:, p, si, j] = N.project(bm, (z, z, np.ones((NT, 12)), np.full((NT, 12), np.nan)), mcfg)
    for j in range(M):
        for p in range(P):
            for si, ssp in enumerate(("ssp245", "ssp585")):
                dsrc[j, p, si] = dts[j] * (p + 1) * (1 + sc.index(ssp) * 0.2)
    raw = np.abs(rng.normal(8, 3, (60, C.NV)))
    pool = C.transform(raw)[:, MIDX]
    la, lo = np.linspace(20, 60, 60), np.linspace(-130, -60, 60)
    ctx = {"R": {"fut": fut}, "T": T, "cfg": cfg, "midx": MIDX, "bm": bm, "Msh": np.tile(np.eye(K), (NT, 1, 1)), "bad": np.zeros(NT, bool),
           "G": np.zeros(NT, int), "pools": {0: (pool, la, lo), 1: (pool, la, lo)}}
    ones = np.ones_like(dsrc)
    same = N.Source("wc", mn, ["ssp245", "ssp585"], list(T.label), {"dtx": dsrc, "dtn": dsrc, "rp": ones})
    s = {**N.DEFAULTS}
    dsig, moved, info = N.compare(same, ctx, s)
    assert info["mode"] == "overlap" and info["n_models"] == M
    assert np.nanmax(dsig) < 1e-3 and np.nanmax(moved) == 0                   # identical changes: no difference (constant humidity both sides)
    hot = N.Source("wc", mn, ["ssp245", "ssp585"], list(T.label), {"dtx": dsrc + 2.5, "dtn": dsrc + 2.5, "rp": ones})
    d2, m2, _ = N.compare(hot, ctx, s)
    assert np.nanmin(d2) > 0.01 and np.isfinite(d2).all()                     # a 2.5 C warmer source differs
    ens = N.Source("aw", ["ensemble"], ["ssp245", "ssp585"], list(T.label), {"dtx": dsrc[:1] * 0 + dts.mean() * 1.0, "dtn": dsrc[:1] * 0 + dts.mean(), "rp": ones[:1]})
    d3, m3, i3 = N.compare(ens, ctx, s)
    assert i3["mode"] == "mean" and i3["n_models"] == 1 and np.isfinite(d3).all()
    part = N.Source("wc", mn, ["ssp245", "ssp585"], ["P0", "P1", "other"], {"dtx": dsrc[:, :, :, :3] + 2.5, "dtn": dsrc[:, :, :, :3] + 2.5, "rp": ones[:, :, :, :3]})
    d4, _, _ = N.compare(part, ctx, s)
    assert np.isfinite(d4[:2]).all() and np.isnan(d4[2:]).all()               # places the source lacks stay untested


def test_summary_line_with_sources():
    st = lambda o, m, h: {"ok": o, "moderate": m, "high": h, "nodata": 0, "median_dsigma": 0.2, "p95_dsigma": 0.9}
    doc = {"n_models": 13, "thresholds": {"sigma_moderate": 0.5, "sigma_high": 1.0, "moved_km": 500.0}, "summary": st(70, 20, 10),
           "sources": [{"label": "NEX-GDDP-CMIP6", "mode": "overlap", "n_models": 13, "summary": st(90, 8, 2)},
                       {"label": "AdaptWest", "mode": "mean", "n_models": 1, "summary": st(80, 10, 10)}]}
    s = N.summary_line(doc)
    assert "10% high" in s and "AdaptWest (1 model mean)" in s and "NEX-GDDP-CMIP6 (13 models)" in s and "high by source" in s


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
