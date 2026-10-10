"""W1 adapter (ctw/species/inputs.py) against a fake tile directory made with W1's own writers, and the real-size (4320 x 8640) grid path
of the W3 pipeline. Run: pytest tests/test_species_inputs.py"""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw.species import climstack as CS, inputs as IN, grid, pipeline as PL, project as PR, summary as SM  # noqa: E402

TILE = (1, 1)                  # rows 1080-2160 (45N-0), cols 2160-4320 (90W-0)
BLOCK = (slice(300, 420), slice(500, 640))       # 120 x 140 land cells inside the tile (5 x 5.8 degrees)


def monthly(n, seed=0):
    rng = np.random.default_rng(seed)
    base = 8 + rng.normal(0, 3, n) + np.linspace(-6, 6, n)
    t = base[None, :] + 9 * np.cos(2 * np.pi * (np.arange(12)[:, None] - 6.5) / 12)
    p = 70 * (1 + 0.5 * np.cos(2 * np.pi * np.arange(12) / 12))[:, None] * rng.uniform(0.5, 1.5, n)[None, :]
    pet = np.maximum(t, 0) * 5 + 20
    d = np.maximum(pet - p, 0)
    return {"tmax": t + 4, "tmin": t - 4, "ppt": p, "pet": pet, "def": d, "aet": pet - d, "soil": np.full((12, n), 80.0)}


@pytest.fixture(scope="module")
def clim(tmp_path_factory):
    root = tmp_path_factory.mktemp("clim")
    land = np.zeros((CS.TH, CS.TW), bool)
    land[BLOCK] = True
    n = int(land.sum())
    m = monthly(n)
    tile = f"r{TILE[0]}c{TILE[1]}"
    CS.save_pred(root / f"pred_base_1991-2020_{tile}.npz", tile, land, CS.predict({k: m[k] for k in CS.PRED_VARS}), "base_1991-2020")
    CS.save_basem(root / f"basem_{tile}.npz", tile, land, m)
    shp = (2, 2, 12, 600, 1440)
    for name, dt in (("A", 1.0), ("B", 2.5), ("C", 4.0)):
        CS.Deltas(name, CS.SCEN, CS.PERIODS, np.full(shp, dt, "float32"), np.full(shp, dt, "float32"), np.full(shp, 1.0, "float32"),
                  -59.875 + 0.25 * np.arange(600), 0.125 + 0.25 * np.arange(1440)).save(root / f"deltas_{name}.npz")
    return root, land, m


def test_w1_source_bands_match_tile_files(clim):
    root, land, m = clim
    src = IN.W1Source(str(root))
    assert src.future_models("SSP2-4.5", "2041-2060") == ["A", "B", "C"]
    r0, r1 = 1080 + 290, 1080 + 330                      # a band inside the block's first rows
    B = src.baseline_band(r0, r1, ("bio1", "cwd"))
    assert B.shape == (2, 40, 8640)
    P = CS.predict({k: m[k] for k in CS.PRED_VARS})
    full = np.full((2, CS.TH, CS.TW), np.nan, np.float32)
    full[:, land] = P[[0, 8]]
    assert np.allclose(B[:, :, 2160:4320], full[:, 290:330], equal_nan=True)
    assert np.isnan(B[:, :, :2160]).all() and np.isnan(B[:, :, 4320:]).all()
    # a band spanning two tile rows (the lower one has no files) and the land mask
    B2 = src.baseline_band(2150, 2170, ("bio1",))
    assert np.isnan(B2).all()
    lm = src.land_band(1080 + 295, 1080 + 305)
    assert lm.sum() == 5 * 140 and lm[:, 2160 + 500:2160 + 640].sum() == lm.sum() or lm.sum() == 5 * 140
    pts = src.baseline_points(np.array([1080 + 310, 5]), np.array([2160 + 520, 5]), ("bio1",))
    assert np.isfinite(pts[0, 0]) and np.isnan(pts[1, 0])


def test_w1_source_future_bands_apply_the_model_delta(clim):
    root, land, m = clim
    src = IN.W1Source(str(root))
    dom = np.zeros((4320, 8640), bool)
    dom[1080 + 300:1080 + 420, 2160 + 500:2160 + 640] = True
    src.prepare(dom)
    r0, r1 = 1080 + 330, 1080 + 360
    base = src.baseline_band(r0, r1, ("bio1", "bio12"))
    for model, dt in (("A", 1.0), ("C", 4.0)):
        f = src.future_band("SSP5-8.5", "2081-2100", model, r0, r1, ("bio1", "bio12"))
        ok = np.isfinite(base[0])
        assert np.allclose((f[0] - base[0])[ok], dt, atol=0.02) and np.allclose(f[1][ok], base[1][ok], rtol=2e-3)
    assert np.isnan(src.future_band("SSP5-8.5", "2081-2100", "A", 0, 10, ("bio1",))).all()


def test_real_size_grid_end_to_end(clim):
    """Fit and project a small species on the real 4320 x 8640 grid geometry with the fake tile (checks no step assumes a small grid)."""
    root, land, m = clim
    src = IN.W1Source(str(root), names=("bio1", "bio6", "bio12", "cwd"))
    spec = src.spec
    rows, cols = np.nonzero(land)
    rows, cols = rows + CS.TH * TILE[0], cols + CS.TW * TILE[1]
    B = src.baseline_points(rows, cols, ("bio1", "bio12"))
    s = np.exp(-0.5 * ((B[:, 0] - 9) / 1.2) ** 2) * np.exp(-0.5 * ((B[:, 1] - 900) / 250) ** 2)
    rng = np.random.default_rng(0)
    pick = rng.choice(len(rows), 200, p=s / s.sum())
    occ = grid.Occurrences(rows[pick], cols[pick])
    native = np.zeros((4320, 8640), bool)
    native[rows[s > 0.3 * s.max()], cols[s > 0.3 * s.max()]] = True
    lm = np.zeros((4320, 8640), bool)
    lm[rows, cols] = True
    cfg = PL.FitConfig(check_model=False, n_bg_min=2000, n_eval=2000, train_buffer_km=100.0, proj_buffer_km=200.0)
    fit = PL.fit_species("fake", spec, src, occ, land=lm, native=native, density=None, group="tree", cfg=cfg)
    assert fit.train.shape == (4320, 8640) and fit.proj.sum() >= fit.train.sum() > 0
    proj = PR.project_species(fit, src, ("SSP5-8.5",), ("2081-2100",), group="tree", cfg=PR.ProjConfig(band_rows=120))
    sc = proj.scen[("SSP5-8.5", "2081-2100")]
    assert sc.n_models == 3 and sc.S.shape == (4320, 8640) and not sc.S[~fit.proj].any()
    summ = SM.build_summary(fit, proj, dict(scientific_name="Fake sp", group="tree"), expert=native)
    assert summ["area_now_km2"] > 0 and summ["scenarios"]["SSP5-8.5|2081-2100"]["n_models"] == 3
