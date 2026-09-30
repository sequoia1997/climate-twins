"""Unit tests for the multi-source baseline agreement (ctw/baselines.py) on synthetic arrays. Run: pytest tests/test_baselines.py"""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw import baselines as BL, common as C, era5 as ERA5  # noqa: E402

RNG = np.random.default_rng(7)
MIDX = np.r_[np.arange(12), [12, 14]]


def make_base(n, g=None):
    """(n, 16) plausible baselines; rows are places."""
    x = np.zeros((n, 16))
    x[:, 0:4] = RNG.uniform(0, 30, (n, 1)) + np.array([-4, 0, 4, 0])
    x[:, 4:8] = x[:, 0:4] - 9
    x[:, 8:12] = RNG.uniform(30, 400, (n, 4))
    x[:, 12:16] = x[:, 4:8] - 3
    return x


def make_models(base, years=30):
    """A ShrinkSigmaModel per place from a synthetic year-to-year series around the baseline (transformed space, matched columns)."""
    out = []
    for b in base:
        t = C.transform(b)[MIDX]
        sd = np.r_[np.full(8, 0.8), np.full(4, 0.25), np.full(2, 0.7)]
        out.append(C.ShrinkSigmaModel(t + RNG.normal(0, 1, (years, len(MIDX))) * sd))
    return out


# ------------------------------------------------------------------------------------------ sampling
def test_sample_array_prefers_the_cell_then_neighbours():
    a = np.full((6, 6), np.nan); a[2, 2] = 5.0; a[3, 3] = 9.0
    r, c = np.array([2, 2, 3, 0, 5]), np.array([2, 3, 2, 0, 5])
    v = BL.sample_array(a, r, c, rads=(0, 1, 2))
    assert v[0] == 5.0                                     # the cell itself
    assert v[1] == 7.0 and v[2] == 7.0                     # (2,3) and (3,2): mean of the two valid cells within 1
    assert v[3] == 5.0                                     # (0,0): (2,2) is 2 cells away, found at radius 2
    assert v[4] == 9.0                                     # (5,5): (3,3) is 2 away


def test_sample_array_none_valid_is_nan():
    a = np.full((5, 5), np.nan)
    assert np.isnan(BL.sample_array(a, np.array([2]), np.array([2]))).all()


def _tif(data, scale=1.0, offset=0.0, nodata=None, dtype="float32", res=1.0, top=10.0, left=0.0):
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin
    h, w = data.shape
    mf = MemoryFile()
    with mf.open(driver="GTiff", height=h, width=w, count=1, dtype=dtype, transform=from_origin(left, top, res, res), crs="EPSG:4326", nodata=nodata) as ds:
        ds.write(data.astype(dtype), 1)
        ds.scales = (scale,); ds.offsets = (offset,)
    return mf


def test_sample_dataset_scale_offset_nodata_and_strips():
    data = (np.arange(100).reshape(10, 10) * 10).astype("uint16")     # value at row r, col c = (10 r + c) * 10
    data[4, 4] = 65535                                                  # nodata cell
    mf = _tif(data, scale=0.1, offset=-5.0, nodata=65535, dtype="uint16")
    with mf.open() as ds:
        lat = np.array([9.5, 5.5, 5.5, 20.0])        # rows 0, 4 (nodata cell), 4, outside
        lon = np.array([0.5, 4.5, 6.5, 0.5])
        v = BL.sample_dataset(ds, lat, lon, rads=(0, 1), strip=3)       # strips of 3 rows exercise the padding
    assert v[0] == pytest.approx(-5.0)                                   # cell (0, 0): raw 0
    row4_col6 = (4 * 10 + 6) * 10 * 0.1 - 5.0
    assert v[2] == pytest.approx(row4_col6)
    nb = [(r * 10 + c) * 10 * 0.1 - 5.0 for r in (3, 4, 5) for c in (3, 4, 5) if (r, c) != (4, 4)]
    assert v[1] == pytest.approx(np.mean(nb))                            # nodata cell: mean of the valid neighbours
    assert np.isnan(v[3])                                                # outside the raster


def test_sample_dataset_positive_masks_negative_fill():
    data = np.full((4, 4), 50.0, "float32"); data[1, 1] = -9999.0
    with _tif(data, nodata=None).open() as ds:
        v = BL.sample_dataset(ds, np.array([8.5]), np.array([1.5]), rads=(0,), positive=True)
    assert np.isnan(v[0])


# ------------------------------------------------------------------------------------------ CHIRPS / CHELSA vectors
def test_seasonal_ppt_uses_previous_december_for_djf():
    years = np.array([1990, 1991, 1992])
    s = np.zeros((1, 3, 12))
    s[0, 0, 11] = 100                     # December 1990
    s[0, 1, 0:2] = 10                     # Jan, Feb 1991
    s[0, 1, 11] = 999                     # December 1991 belongs to DJF 1992
    out = BL.seasonal_ppt(s, years, [1991, 1992])
    assert out[0, 0, 0] == 120            # 100 + 10 + 10
    assert out[0, 1, 0] == 999
    assert np.isnan(BL.seasonal_ppt(s, years, [1990])).all()


def test_chirps_vectors_fill_only_precipitation():
    C.use_extras([])
    years = np.arange(1990, 2021)
    s = np.full((3, len(years), 12), 30.0)
    v = BL.chirps_vectors(years, s, 1991, 2020)
    assert v.shape == (3, 16)
    assert np.allclose(v[:, 8:12], 90.0) and np.isnan(v[:, :8]).all() and np.isnan(v[:, 12:]).all()


def test_chirps_vectors_no_years_is_nan():
    v = BL.chirps_vectors(np.array([1985, 1986]), np.ones((2, 2, 12)), 1991, 2020)
    assert np.isnan(v).all()


def test_chelsa_vectors_and_units():
    C.use_extras([])
    d = {"tmax": np.full((2, 12), 20.0), "tmin": np.full((2, 12), 10.0), "ppt": np.full((2, 12), 50.0)}
    v = BL.chelsa_vectors(d)
    assert v.shape == (2, 16) and np.allclose(v[:, :4], 20) and np.allclose(v[:, 4:8], 10) and np.allclose(v[:, 8:12], 150)
    assert np.isnan(v[:, 12:]).all()
    assert BL.to_physical("tasmax", np.array([293.15, 283.15]))[0] == pytest.approx(20.0)
    assert BL.to_physical("pr", np.array([12.0]))[0] == 12.0
    assert BL.to_physical("tasmax", np.array([2931.5]))[0] == pytest.approx(20.0)      # Kelvin x 10 without a scale tag
    with pytest.raises(ValueError):
        BL.to_physical("tasmax", np.array([500.0]))


def test_split_years_covers_all_once():
    ys = list(range(1990, 2021))
    parts = [BL.split_years(ys, i, 6) for i in range(6)]
    assert sum(parts, []) == ys and all(parts)


# ------------------------------------------------------------------------------------------ the metric
def test_full_column_sigma_equals_era5_agreement():
    base = make_base(1); SH = make_models(base)
    other = base + RNG.normal(0, 1, base.shape) * np.array([1] * 8 + [40] * 4 + [1] * 4)
    a = BL.sigma_on(SH[0], MIDX, BL.COLS["era5"], base[0], other[0])
    b = ERA5.agreement(SH[0], MIDX, base[0], other[0])
    assert a == pytest.approx(b, rel=1e-6, abs=1e-6)


def test_offsets_removed_and_real_disagreement_found():
    n = 60
    base = make_base(n); SH = make_models(base)
    g = np.r_[np.zeros(20, int), np.ones(40, int)]
    other = base.copy()
    other[:, 4:8] += 1.5                                                # a systematic warm-night offset
    other[:, 8:12] = (base[:, 8:12] + 1) * 1.2 - 1                      # and a 20% wet bias
    other[7, 8:12] = (base[7, 8:12] + 1) * 4 - 1                        # place 7: precipitation really four times higher
    with_off, off = BL.source_agreement(SH, MIDX, base, other, g, BL.COLS["era5"])
    no_off = np.array([BL.sigma_on(SH[k], MIDX, BL.COLS["era5"], base[k], other[k]) for k in range(n)])
    assert np.nanmedian(with_off) < 0.7 < np.nanmedian(no_off)         # the offset alone would flag places
    assert off[1, 4] == pytest.approx(1.5, abs=0.05) and off[1, 8] == pytest.approx(np.log(1.2), abs=0.05)
    assert with_off[7] == np.nanmax(with_off) and with_off[7] > 3.5


def test_chirps_sees_only_precipitation_and_chelsa_temperature_too():
    n = 40
    base = make_base(n); SH = make_models(base)
    g = np.ones(n, int)
    ppt_bad = np.full((n, 16), np.nan); ppt_bad[:, 8:12] = base[:, 8:12]
    ppt_bad[3, 8:12] = (base[3, 8:12] + 1) * 5 - 1                      # place 3: precipitation far off
    s_chirps, _ = BL.source_agreement(SH, MIDX, base, ppt_bad, g, BL.COLS["chirps"])
    assert s_chirps[3] > 3.5 and np.nanmedian(s_chirps) < 0.5

    temp_bad = base.copy(); temp_bad[:, 12:] = np.nan
    temp_bad[5, 0:4] += 8                                              # place 5: temperatures far off, precipitation fine
    s_chirps5, _ = BL.source_agreement(SH, MIDX, base, temp_bad, g, BL.COLS["chirps"])
    s_chelsa, _ = BL.source_agreement(SH, MIDX, base, temp_bad, g, BL.COLS["chelsa"])
    assert s_chirps5[5] < 2 and s_chelsa[5] > 3.5                      # only the source that covers temperature can see it


def test_missing_values_give_nan_and_do_not_break_offsets():
    n = 30
    base = make_base(n); SH = make_models(base)
    other = np.full((n, 16), np.nan); other[:20, 8:12] = base[:20, 8:12]
    s, off = BL.source_agreement(SH, MIDX, base, other, np.ones(n, int), BL.COLS["chirps"])
    assert np.isfinite(s[:20]).all() and np.isnan(s[20:]).all()
    assert np.allclose(off[1, 8:12], 0, atol=1e-9) and np.allclose(off[0], 0)


def test_places_without_a_model_are_skipped():
    n = 10
    base = make_base(n); SH = make_models(base)
    ok = np.ones(n, bool); ok[2] = False; SH[2] = None
    other = base.copy()
    s, _ = BL.source_agreement(SH, MIDX, base, other, np.ones(n, int), BL.COLS["era5"], ok)
    assert np.isnan(s[2]) and np.isfinite(np.delete(s, 2)).all()


def test_combine_takes_the_worst_source_and_names_it():
    sig = np.array([[1.0, 4.0, np.nan], [np.nan, np.nan, np.nan], [2.5, np.nan, 0.5], [0.1, 0.2, 5.0]])
    worst, which = BL.combine(sig)
    assert worst[0] == 4.0 and which[0] == 1
    assert np.isnan(worst[1]) and which[1] == -1
    assert worst[2] == 2.5 and which[2] == 0
    assert worst[3] == 5.0 and which[3] == 2


def test_icv_ratio_near_one_for_matching_variability():
    C.use_extras([])
    years = np.arange(1990, 2021)
    rng = np.random.default_rng(3)
    logm = np.log(101.0)
    L = logm + rng.normal(0, 0.3, (5, len(years), 12))                 # log(monthly+1) around 100 mm, sd 0.3 (before seasonal summing)
    series = np.exp(L) - 1
    sd = np.array([C.detrend(np.log(BL.seasonal_ppt(series, years, list(range(1991, 2021)))[k] + 1)).std(0, ddof=1) for k in range(5)])
    icvsd = np.zeros((5, 16)); icvsd[:, 8:12] = sd * 1.25              # model says 25% more variable than CHIRPS
    r = BL.icv_ratio(years, series, 1991, 2020, icvsd)
    assert np.allclose(r, 0.8, atol=0.01)


def test_agreement_summary_shapes():
    from ctw import export
    cfg = C.config()
    n = 50
    AGR = np.stack([RNG.gamma(1.2, 1.5, n), RNG.gamma(1.2, 1.5, n), RNG.gamma(1.2, 1.5, n)], 1).astype("float32")
    AGR[10:, 1] = np.nan
    R = {"agr_diff": RNG.normal(0, 1, (n, 2, 16)).astype("float32"), "chirps_icv": RNG.uniform(.8, 1.2, (n, 4)).astype("float32")}
    import pandas as pd
    T = pd.DataFrame({"g": np.r_[np.zeros(20, int), np.ones(30, int)]})
    cfg["era5"]["combine"] = "worst"
    out = export.agreement_summary(cfg, AGR, R, np.zeros(n, bool), T)
    assert set(out["sources"]) == {"era5", "chirps", "chelsa"} and out["sources"]["chirps"]["n"] == 10
    cb = out["combined"]
    assert cb["n"] == n and cb["median"] >= out["sources"]["era5"]["median"] and cb["over_poor"] >= out["sources"]["era5"]["over_poor"]
    cfg["era5"]["combine"] = "corroborated"          # the default: two sources must both disagree, so it can only be milder
    oc = export.agreement_summary(cfg, AGR, R, np.zeros(n, bool), T)["combined"]
    assert oc["n"] == 10 and oc["median"] <= cb["median"]      # badge sources: ERA5 + CHIRPS (CHELSA reported only); CHIRPS has 10 rows
    assert oc["over_poor"] <= cb["over_poor"]
    assert sum(cb["poor_by"].values()) == int(round(cb["over_poor"] * n))
    assert set(out["bias"]) == {"chirps", "chelsa"} and len(out["bias"]["chelsa"]["World cities"]["tmax"]) == 4
    assert len(out["chirps_icv_ratio"]) == 4
    old = export.agreement_matrix({"era5_sig": AGR[:, 0]})                # results written before the multi-source check
    assert old.shape == (n, 3) and np.isnan(old[:, 1:]).all()


# ------------------------------------------------------------------------------------------ the extraction jobs, with the network replaced
def _places():
    import pandas as pd
    return pd.DataFrame({"label": ["A", "B", "C"], "lat": [10.2, -20.7, 60.0], "lon": [5.3, 130.1, 10.0], "g": [1, 1, 1]})


def _fake_download(tmp_path, kind):
    """C.download stand-in: writes a small global raster whose value encodes (year, month) or (variable, month)."""
    import gzip, re
    import rasterio
    from rasterio.transform import from_origin

    def fake(url, dest, tries=8, timeout=300):
        dest = Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
        if kind == "chirps":
            y, m = map(int, re.search(r"\.(\d{4})\.(\d{2})\.tif", url).groups())
            a = np.full((200, 720), float(m + 100 * (y - 2000)), "float32")
            a[:, :10] = -9999.0
            tif = tmp_path / f"x{y}{m}.tif"
            with rasterio.open(tif, "w", driver="GTiff", height=200, width=720, count=1, dtype="float32", nodata=-9999.0, crs="EPSG:4326",
                               transform=from_origin(-180, 50, 0.5, 0.5)) as ds:
                ds.write(a, 1)
            dest.write_bytes(gzip.compress(tif.read_bytes()))
            tif.unlink()
        else:
            v, m = re.search(r"CHELSA_(\w+?)_(\d{2})_", url).groups()
            base = {"tasmax": 2980, "tasmin": 2880, "pr": 100}[v]                # Kelvin x 10 with scale 0.1, or precipitation
            a = np.full((180, 360), base + int(m), "uint16")
            with rasterio.open(dest, "w", driver="GTiff", height=180, width=360, count=1, dtype="uint16", crs="EPSG:4326",
                               transform=from_origin(-180, 90, 1.0, 1.0), nodata=65535) as ds:
                ds.write(a, 1); ds.scales = (0.1,); ds.offsets = (0.0,)
        return dest
    return fake


def test_run_chirps_end_to_end_with_fake_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "WORK", tmp_path); monkeypatch.setattr(C, "SMOKE", False)
    monkeypatch.setattr(C, "targets", _places)
    monkeypatch.setattr(C, "download", _fake_download(tmp_path, "chirps"))
    monkeypatch.setenv("CTW_CHIRPS_YEARS", "2001-2004")
    C.use_extras([])
    cfg = C.config()
    for part in (0, 1):
        BL.run_chirps(part, 2, cfg)
    years, s = BL.load_chirps(_places())
    assert years.tolist() == [2001, 2002, 2003, 2004] and s.shape == (3, 4, 12)
    assert s[0, 1, 5] == 6 + 100 * 2                                   # year 2002, June
    assert np.isnan(s[2]).all() and np.isfinite(s[:2]).all()           # 60N is outside the 50S-50N raster
    v = BL.chirps_vectors(years, s, 2002, 2004)
    want = np.mean([(12 + 100 * (y - 2001)) + (1 + 100 * (y - 2000)) + (2 + 100 * (y - 2000)) for y in (2002, 2003, 2004)])   # DJF uses December of the year before
    assert v[0, 8] == pytest.approx(want)


def test_run_chelsa_end_to_end_with_fake_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "WORK", tmp_path); monkeypatch.setattr(C, "SMOKE", False)
    monkeypatch.setattr(C, "targets", _places)
    monkeypatch.setattr(C, "download", _fake_download(tmp_path, "chelsa"))
    monkeypatch.setenv("CTW_CHELSA_MONTHS", "1,7")
    cfg = C.config()
    for v in ("tasmax", "tasmin", "pr"):
        BL.run_chelsa(v, cfg)
    d = BL.load_chelsa(_places())
    assert d["tmax"][0, 0] == pytest.approx(298.1 - 273.15, abs=1e-3) and d["tmax"][0, 6] == pytest.approx(298.7 - 273.15, abs=1e-3)
    assert d["ppt"][1, 0] == pytest.approx(10.1, abs=1e-3)
    assert np.isnan(d["tmax"][:, 1]).all()                              # months not fetched stay empty


def test_combine_corroborated_needs_two_sources():
    sig = np.array([[55.0, 0.1, np.nan],      # ERA5 far off, CHIRPS fine: not flagged (second largest is 0.1)
                    [4.0, 5.0, np.nan],       # both off: flagged at the smaller of the two
                    [9.0, np.nan, np.nan],    # only one source: never flagged
                    [np.nan, np.nan, np.nan]])
    v, which = BL.combine(sig, "corroborated")
    assert v[0] == np.float32(0.1) and which[0] == 1
    assert v[1] == 4.0 and which[1] == 0
    assert np.isnan(v[2]) and which[2] == -1
    assert np.isnan(v[3]) and which[3] == -1
    w, _ = BL.combine(sig)                      # default mode is unchanged
    assert w[0] == 55.0


def test_badge_matrix_drops_reported_only_sources():
    from ctw import export
    cfg = C.config()
    cfg["era5"]["badge_sources"] = ["era5", "chirps"]
    A = np.array([[4.0, 0.1, 5.0], [0.2, 4.5, 6.0]], "float32")
    B = export.badge_matrix(cfg, A)
    assert np.isnan(B[:, BL.SOURCES.index("chelsa")]).all() and B[0, 0] == 4.0 and B[1, 1] == 4.5
    v, _ = BL.combine(B, "corroborated")
    assert v[0] == np.float32(0.1) and v[1] == np.float32(0.2)       # ERA5 + CHELSA alone never corroborate
