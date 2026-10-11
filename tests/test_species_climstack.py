import numpy as np
import pytest
from ctw.species import climategrid as G
from ctw.species import climstack as S
from ctw.species import climstack_run as R


def monthly(n, tmean=10.0, amp=8.0, ppt=60.0, seed=0):
    """Synthetic monthly climate for n cells: dict of (12, n)."""
    rng = np.random.default_rng(seed)
    base = tmean + rng.normal(0, 3, n)
    t = base[None, :] + amp * np.cos(2 * np.pi * (np.arange(12)[:, None] - 6.5) / 12)
    p = ppt * (1 + 0.5 * np.cos(2 * np.pi * np.arange(12) / 12))[:, None] * rng.uniform(0.5, 1.5, n)[None, :]
    pet = np.maximum(t, 0) * 5 + 20
    d = np.maximum(pet - p, 0)
    return {"tmax": t + 4, "tmin": t - 4, "ppt": p, "pet": pet, "def": d, "aet": pet - d, "soil": np.full((12, n), 80.0)}


def stack(n=40):
    lat = np.linspace(-50, 60, n); lon = np.linspace(-170, 175, n)
    return S.BaselineStack({k: v.astype("float32") for k, v in monthly(n).items()}, lat, lon)


def deltas(dt=0.0, ratio=1.0, scen=("ssp245", "ssp585"), model="M"):
    shp = (len(scen), 2, 12, 600, 1440)
    return S.Deltas(model, scen, S.PERIODS, np.full(shp, dt, "float32"), np.full(shp, dt, "float32"), np.full(shp, ratio, "float32"),
                    -59.875 + 0.25 * np.arange(600), 0.125 + 0.25 * np.arange(1440))


def test_tiles_cover_the_grid():
    assert S.NTR * S.TH == G.NLAT and S.NTC * S.TW == G.NLON and len(S.ALL_TILES) == 16
    r, c = S.tile_window("r2c3")
    assert (r.start, r.stop, c.start, c.stop) == (2160, 3240, 6480, 8640)
    assert set(S.PRIORITY_TILES) | set(S.REST_TILES) == set(S.ALL_TILES) and not set(S.PRIORITY_TILES) & set(S.REST_TILES)
    # priority tiles: north of the equator, west of 90E
    assert all(int(t[1]) < 2 and int(t[3]) < 3 for t in S.PRIORITY_TILES)


def test_mask_pack_roundtrip():
    m = np.random.default_rng(1).random((S.TH, S.TW)) > 0.7
    assert (S.unpack_mask(S.pack_mask(m)) == m).all()


def test_predict_matches_climategrid_and_handles_dry_cells():
    m = monthly(30)
    m["ppt"][:, 0] = 0.0
    P = S.predict({k: m[k] for k in S.PRED_VARS}, block=7)
    b = G.bioclim(m["tmax"], m["tmin"], m["ppt"])
    for k, nm in enumerate(S.NAMES[:7]):
        if nm == "bio15":
            assert P[k, 0] == 0.0 and np.allclose(P[k, 1:], b[nm][1:], rtol=1e-4)
        else:
            assert np.allclose(P[k], b[nm], rtol=1e-4, atol=1e-3)
    assert np.allclose(P[S.NAMES.index("gdd")], G.gdd(m["tmax"], m["tmin"]), rtol=1e-4)
    assert np.allclose(P[S.NAMES.index("cwd")], m["def"].sum(0), rtol=1e-5) and np.allclose(P[S.NAMES.index("aet")], m["aet"].sum(0), rtol=1e-5)
    assert P.dtype == np.float32 and np.isfinite(P).all()


def test_basem_roundtrip_precision(tmp_path):
    land = np.zeros((S.TH, S.TW), bool); land[10, 5:15] = True
    m = monthly(10)
    m["tmax"][0, 0] = np.nan
    S.save_basem(tmp_path / "b.npz", "r1c2", land, m)
    land2, tile, back = S.load_basem(tmp_path / "b.npz")
    assert tile == (1, 2) and (land2 == land).all()
    assert np.isnan(back["tmax"][0, 0])
    for v, (sc, _) in S.MONTHLY.items():
        ok = np.isfinite(m[v])
        assert np.abs(back[v][ok] - m[v][ok]).max() <= sc / 2 + 1e-4


def test_point_interp_linear_field_and_dateline_wrap():
    lat_c = -59.875 + 0.25 * np.arange(600); lon_c = 0.125 + 0.25 * np.arange(1440)
    f = (2.0 * lat_c[:, None] + 0 * lon_c[None, :]).astype("float32")                 # linear in latitude
    it = S.PointInterp(lat_c, lon_c, [10.3, -40.01, 89.99], [5.0, -170.0, 0.0])
    assert np.allclose(it(f), [20.6, -80.02, 2 * 89.875], atol=1e-3)               # latitude clamps at the last row
    g = np.tile(np.cos(np.radians(lon_c))[None, :], (600, 1)).astype("float32")      # periodic in lon
    it = S.PointInterp(lat_c, lon_c, [0.0, 0.0], [-0.05, 359.97])                    # across the 0/360 seam, negative and >180 conventions
    assert np.allclose(it(g), np.cos(np.radians([-0.05, 359.97])), atol=1e-3)
    # descending latitude works the same
    it2 = S.PointInterp(lat_c[::-1], lon_c, [10.3], [5.0])
    assert np.allclose(it2(f[::-1]), [20.6], atol=1e-3)


def test_apply_deltas_zero_change_is_baseline_and_plus3_shifts_bio1():
    st = stack()
    P0 = S.predict({k: st.monthly[k] for k in S.PRED_VARS})
    r0 = S.apply_deltas(st, deltas(), "M", "ssp245", "2041-2060")
    assert set(r0) == set(S.NAMES)
    for k, nm in enumerate(S.NAMES):
        assert np.allclose(r0[nm], P0[k], rtol=1e-3, atol=1e-2), nm              # cwd/aet: own water balance difference is 0 for a 0 change
    r3 = S.apply_deltas(st, {"M": deltas(3.0, 1.1)}, "M", "ssp585", "2081-2100")
    assert np.allclose(r3["bio1"] - r0["bio1"], 3.0, atol=1e-3)
    assert np.allclose(r3["bio12"] / r0["bio12"], 1.1, rtol=2e-3)
    assert (r3["gdd"] > r0["gdd"]).all() and (r3["cwd"] >= 0).all() and (r3["bio6"] - r0["bio6"] > 2.9).all()
    assert r3["bio1"].dtype == np.float32


def test_apply_deltas_ratio_is_clipped_and_scenario_period_selected():
    d = deltas(0.0, 1.0)
    d.dtx[1, 1] += 5.0; d.dtn[1, 1] += 5.0                                                    # only ssp585 / 2081-2100 warms
    d.rp[1, 1] = 20.0
    st = stack(12)
    a = S.apply_deltas(st, d, "M", "ssp245", "2041-2060")
    b = S.apply_deltas(st, d, "M", "ssp585", "2081-2100")
    assert np.allclose(b["bio1"] - a["bio1"], 5.0, atol=1e-3)
    assert np.allclose(b["bio12"] / a["bio12"], S.PPT_RATIO[1], rtol=1e-3)


def test_ensemble_median_and_library(tmp_path):
    ds = [deltas(1.0, 1.0, model="a"), deltas(2.0, 1.2, model="b"), deltas(9.0, 3.0, model="c")]
    e = S.ensemble_median(ds)
    assert np.allclose(e.dtx, 2.0) and np.allclose(e.rp, 1.2) and e.meta["models"] == ["a", "b", "c"]
    small = deltas(1.5, 1.0, scen=("ssp245",), model="a")
    small.save(tmp_path / "deltas_a.npz")
    lib = S.DeltaLibrary(str(tmp_path))
    assert lib.models() == ["a"]
    d = lib.get_model("a")
    assert d.scenarios == ("ssp245",) and np.allclose(d.dtx.astype("float32"), 1.5)
    r = S.apply_deltas(stack(8), lib, "a", "ssp245", "2081-2100")
    assert np.isfinite(r["bio1"]).all()


def test_make_deltas_fills_ocean_and_guards_dry_months():
    ny, nx = 8, 10
    base = np.ones((3, 12, ny, nx), "float32") * 10; base[2] = 2.0
    base[:, :, :, 5:] = np.nan                                            # ocean columns
    base[2, 3, 1, 1] = 0.01                                               # nearly dry month -> ratio 1
    fut = {s: np.stack([base * np.array([1, 1, 1.5], "float32")[:, None, None, None] + np.array([2, 2, 0])[:, None, None, None]] * 2)
           for s in S.SCEN}
    d = R.make_deltas("M", base, fut, {"tcr": 2.0})
    assert d.dtx.shape == (2, 2, 12, ny, nx) and np.isfinite(d.dtx).all() and np.isfinite(d.rp).all()
    assert np.allclose(d.dtx, 2.0) and np.isclose(d.rp[0, 0, 0, 0, 0], 1.5)
    assert d.rp[0, 0, 3, 1, 1] == 1.0


def test_sample_points_and_read_box_from_tile_files(tmp_path):
    land = np.zeros((S.TH, S.TW), bool); land[100:110, 200:210] = True            # tile r1c2 (rows 1080.., cols 4320..)
    n = int(land.sum())
    data = np.arange(10, dtype="float32")[:, None] + np.arange(n, dtype="float32")[None, :] * 0.001
    S.save_pred(tmp_path / "pred_base_1991-2020_r1c2.npz", "r1c2", land, data, "base_1991-2020")
    i, j = 1080 + 105, 4320 + 205
    lat, lon = G.cell_lat(i), G.cell_lon(j)
    v = S.sample_points(str(tmp_path), "base_1991-2020", [lat, lat + 0.5], [lon, lon])
    assert v.shape == (10, 2) and np.isfinite(v[:, 0]).all() and np.isnan(v[:, 1]).all()
    assert v[0, 0] == pytest.approx(0 + (5 * 10 + 5) * 0.001, abs=1e-4)
    p = S.load_pred(tmp_path / "pred_base_1991-2020_r1c2.npz")
    grid = S.tile_to_grid(p)
    assert grid.shape == (10, S.TH, S.TW) and np.isfinite(grid[0]).sum() == n


def test_tc_jobs_cover_windows():
    jobs = R.tc_jobs()
    keys = {(v, y) for v, y, _ in jobs}
    assert ("pet", 2000) in keys and ("pet", 1970) not in keys and ("tmax", 1966) in keys and ("tmax", 2024) in keys and ("tmax", 2025) not in keys
    w = {(v, y): ws for v, y, ws in jobs}
    assert set(w[("tmax", 2010)]) == {"base_1991-2020", "hind_2005-2024"} and w[("tmax", 1970)] == ("hind_1966-1985",)
    assert len(keys) == 5 * 54 + 2 * 30
