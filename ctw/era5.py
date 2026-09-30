"""ERA5 (Hersbach et al. 2020) as an independent second opinion on every place's present climate.

Source: the daily aggregation of ARCO-ERA5 (Google Research / WeatherBench 2) at 0.25°:
gs://weatherbench2/datasets/era5_daily/1959-2023_01_10-full_37-1h-0p25deg-chunk-1-s2s.zarr, whose daily
2 m temperature maximum and minimum, 24 h total precipitation and mean 2 m dewpoint are computed from the hourly
ARCO-ERA5 fields (gs://gcp-public-data-arco-era5). The hourly ARCO stores are chunked one hour per file
(263,000 files for 1991-2020 per variable); this daily store is chunked one day per file (11,000), which is
what makes a 30-year global pass affordable. Days are UTC days.

One pass per variable (same names as terraclimate.py: tmax, tmin, ppt, vap) writes work/era5/{var}.npz:
  series   (NT, ny, 12)       monthly values at every place, for every year (Dec of year 0 feeds DJF)
  w0, w1   (12, 360, 720)     monthly normals of the two hindcast windows on a 0.5° grid (2x2 block means)
  lsm05    (360, 720)         land fraction of each 0.5° cell
  cell     (NT, ny, 12)       monthly values of each place's own ERA5 land cell (NaN: no land cell, see land_cell)
  cell_i, cell_j, cell_km, cell_lsm (NT,)  that cell's row, column, distance from the place and land fraction
The place value (series, used by the hindcast) is the bilinear interpolation of the four surrounding 0.25° cells,
weighted toward land cells. The baseline-agreement check uses `cell` instead: one whole ERA5 land cell, compared with
the place's own dataset averaged over that same cell's footprint (matched resolution; see matched()).
Dewpoint is averaged as vapour pressure (Magnus, as for TerraClimate) and converted back after seasonal averaging.
Progress is checkpointed after every year."""
from __future__ import annotations
import os, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from . import common as C

STORE = "weatherbench2/datasets/era5_daily/1959-2023_01_10-full_37-1h-0p25deg-chunk-1-s2s.zarr"
LSM_STORE = "gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
ARRAY = {"tmax": "2m_temperature_max", "tmin": "2m_temperature_min", "ppt": "total_precipitation_24hr", "vap": "2m_dewpoint_temperature"}
EPOCH = np.datetime64("1959-01-01")
NLAT, NLON = 721, 1440


def load_lsm(ar):
    """Land-sea mask (0..1) on the 0.25 degree grid. The hourly store keeps this static field in a time-shaped array that is
    only filled at some steps (the first is empty), so look for a step that holds data."""
    la = ar["land_sea_mask"]
    if la.ndim == 2:
        return np.asarray(la[:], "float32")
    for i in (500000, 600000, 700000, 400000, 300000, 900000, 1000000, 200000, 100000):
        x = np.asarray(la[i], "float32")
        if np.isfinite(x).all():
            return x
    raise RuntimeError("no land-sea mask found in the ARCO-ERA5 store")


def _open(cfg):
    import gcsfs, zarr
    fs = gcsfs.GCSFileSystem(token="anon")
    return zarr.open(fs.get_mapper(cfg.get("era5", {}).get("store", STORE)), mode="r")


def years_needed(cfg):
    h = cfg["hindcast"]["windows"]
    y0 = min(h[0][0], cfg["baseline"]["years"][0]) - 1
    y1 = max(h[1][1], cfg["baseline"]["years"][1])
    env = os.environ.get("CTW_ERA5_YEARS")
    if env:
        a, b = env.split("-")
        return list(range(int(a), int(b) + 1))
    ys = list(range(y0, y1 + 1))
    if C.SMOKE:
        ys = [y for y in ys if y <= y0 + 6] + [y1 - 1, y1]
    return ys


def interp_weights(lat, lon, lsm):
    """Bilinear corner indices and weights on the 0.25° grid (lat 90..-90, lon 0..359.75), land cells preferred."""
    lat, lon = np.asarray(lat, float), np.mod(np.asarray(lon, float), 360.0)
    fi = np.clip((90 - lat) / 0.25, 0, NLAT - 1 - 1e-9)
    i0 = np.floor(fi).astype(int); di = fi - i0
    fj = lon / 0.25
    j0 = np.floor(fj).astype(int); dj = fj - j0
    I = np.stack([i0, i0, i0 + 1, i0 + 1], 1)
    J = np.stack([j0, j0 + 1, j0, j0 + 1], 1) % NLON
    W = np.stack([(1 - di) * (1 - dj), (1 - di) * dj, di * (1 - dj), di * dj], 1)
    land = lsm[I, J] >= 0.5
    Wl = np.where(land, W, 0.0)
    ok = Wl.sum(1) > 1e-6                                  # at least one land corner: ignore the sea corners
    W = np.where(ok[:, None], Wl, W)
    return I, J, W / W.sum(1, keepdims=True)


# ------------------------------------------------------------------------------------------ matched-resolution cells
DEG = 0.25
TC_PER_CELL = 6                                         # TerraClimate 1/24° pixels per 0.25° cell side


def land_params(cfg):
    e = (cfg or {}).get("era5", {})
    return float(e.get("land_frac_min", 0.5)), float(e.get("land_max_km", 50.0))


def cells_within(lat, lon, km):
    """0.25° ERA5 cells (row i: latitude 90 - 0.25 i; column j: longitude 0.25 j) whose centres lie within km of each
    place. Returns a list of (i, j, distance_km) arrays, one per place."""
    step = C.R_EARTH * np.radians(DEG)                 # km per 0.25° of latitude
    dr = int(np.ceil(km / step))
    out = []
    for la, lo in zip(np.asarray(lat, float), np.asarray(lon, float)):
        i0, j0 = int(round((90 - la) / DEG)), int(round(np.mod(lo, 360.0) / DEG))
        cosm = max(np.cos(np.radians(min(89.9, abs(la) + (dr + 1) * DEG))), 1e-3)
        dc = int(min(NLON // 2, np.ceil(km / (step * cosm))))
        ii, jj = np.mgrid[i0 - dr:i0 + dr + 1, j0 - dc:j0 + dc + 1]
        ii, jj = ii.ravel(), jj.ravel()
        keep = (ii >= 0) & (ii < NLAT)
        ii, jj = ii[keep], np.mod(jj[keep], NLON)
        d = C.haversine_km(la, lo, 90.0 - ii * DEG, jj * DEG)
        s = d <= km
        out.append((ii[s], jj[s], d[s]))
    return out


def land_cell(lat, lon, lsm, min_frac=0.5, max_km=50.0):
    """Each place's own ERA5 land cell: the 0.25° cell nearest to the place (by centre) whose land fraction is at least
    min_frac, within max_km. Returns (i, j, km); i = j = -1 and km = NaN where there is none ('no land cell': small
    islands and atolls ERA5 treats as sea)."""
    n = len(np.atleast_1d(lat))
    I, J, D = np.full(n, -1), np.full(n, -1), np.full(n, np.nan)
    for k, (ii, jj, d) in enumerate(cells_within(lat, lon, max_km)):
        m = lsm[ii, jj] >= min_frac
        if m.any():
            q = int(np.argmin(np.where(m, d, np.inf)))
            I[k], J[k], D[k] = ii[q], jj[q], d[q]
    return I, J, D


def candidate_cells(lat, lon, max_km=50.0):
    """Flat indices (i * 1440 + j, sorted, unique) of every 0.25° cell that can be some place's land cell. The TerraClimate
    step averages its pixels over these cells without needing the ERA5 land-sea mask."""
    parts = [ii.astype(np.int64) * NLON + jj for ii, jj, _ in cells_within(lat, lon, max_km + 1.0)]
    return np.unique(np.concatenate(parts)) if parts else np.zeros(0, np.int64)


def box_pixels(flat, per=TC_PER_CELL, nlat=4320, nlon=8640):
    """Row and column indices (n, per*per) of the 1/24° TerraClimate pixels inside each 0.25° ERA5 cell. TerraClimate
    pixel r spans latitudes 90 - r/24 .. 90 - (r+1)/24 and column c longitudes -180 + c/24 .. -180 + (c+1)/24, so ERA5
    cell (i, j), centred on (90 - i/4, j/4) with half-width 1/8°, holds rows 6i-3 .. 6i+2 and columns 6j+4317 .. 6j+4322
    (mod 8640) exactly. Rows beyond the poles are clipped (repeats; irrelevant for places)."""
    flat = np.asarray(flat, np.int64)
    i, j = flat // NLON, flat % NLON
    h = per // 2
    o = np.arange(per)
    rows = np.clip(i[:, None] * per - h + o[None, :], 0, nlat - 1)
    cols = np.mod(j[:, None] * per + nlon // 2 - h + o[None, :], nlon)
    R = np.repeat(rows, per, axis=1)
    Cc = np.tile(cols, (1, per))
    return R, Cc


def box_means(a, R, Cc):
    """Mean of the finite (land) pixels of the 2-D field a in each box; returns (mean (n,), land pixel count (n,)). NaN
    where a box has no land pixel."""
    b = a[R, Cc]
    ok = np.isfinite(b)
    n = ok.sum(1)
    with np.errstate(invalid="ignore"):
        m = np.where(ok, b, 0).sum(1) / np.maximum(n, 1)
    return np.where(n > 0, m, np.nan), n


def _read(arr, i, tries=6):
    for a in range(tries):
        try:
            return np.asarray(arr[i], "float32")
        except Exception as e:  # noqa: BLE001 - network hiccups: wait and retry
            time.sleep(min(60, 3 * 2 ** a))
            err = e
    raise RuntimeError(f"could not read day {i}: {err}")


def _sat_vap32(t):
    return (0.61094 * np.exp(17.625 * t / (t + 243.04))).astype("float32")


def run(var: str, cfg=None):
    cfg = cfg or C.config()
    T = C.targets()
    g = _open(cfg)
    import gcsfs, zarr
    ar = zarr.open(gcsfs.GCSFileSystem(token="anon").get_mapper(LSM_STORE), mode="r")   # static fields live in the hourly store
    lsm = load_lsm(ar)
    assert 0.2 < lsm.mean() < 0.4, "land-sea mask looks wrong"
    I, J, W = interp_weights(T.lat.values, T.lon.values, lsm)
    ci, cj, ckm = land_cell(T.lat.values, T.lon.values, lsm, *land_params(cfg))       # each place's own land cell
    hasc = ci >= 0
    C.log.info("era5: %d of %d places have an ERA5 land cell within %.0f km (no land cell: %s)", int(hasc.sum()), len(T),
               land_params(cfg)[1], T.label[~hasc].tolist()[:40])
    years = years_needed(cfg)
    hw = cfg["hindcast"]["windows"]
    arr = g[ARRAY[var]]
    out_f, ck = C.work("era5", f"{var}.npz"), C.work("era5", f"{var}.ckpt.npz")
    lsm05 = lsm[:720].reshape(360, 2, 720, 2).mean((1, 3))
    if ck.exists():
        d = C.load(ck)
        series, w, done = d["series"], [d["w0"], d["w1"]], set(d["done"].tolist())
        cell = d["cell"] if "cell" in d else np.full(series.shape, np.nan, "float32")
    else:
        series = np.full((len(T), len(years), 12), np.nan, "float32")
        cell = np.full((len(T), len(years), 12), np.nan, "float32")
        w = [np.zeros((12, 360, 720), "float32") for _ in hw]
        done = set()
    t0 = time.time()
    pool, outer = ThreadPoolExecutor(24), ThreadPoolExecutor(1)
    for yi, y in enumerate(years):
        if y in done:
            continue
        d0 = int((np.datetime64(f"{y}-01-01") - EPOCH).astype(int))
        d1 = int((np.datetime64(f"{y + 1}-01-01") - EPOCH).astype(int))
        days = np.arange(d0, d1)
        mon = (np.datetime64(f"{y}-01-01") + np.arange(len(days))).astype("datetime64[M]").astype(int) % 12
        acc = np.zeros((12, NLAT, NLON), "float32")
        cnt = np.bincount(mon, minlength=12)
        batch = 48
        nxt = outer.submit(lambda b: list(pool.map(lambda i: _read(arr, int(i)), b)), days[:batch])
        for s in range(0, len(days), batch):
            cur = nxt.result()
            if s + batch < len(days):
                nxt = outer.submit(lambda b: list(pool.map(lambda i: _read(arr, int(i)), b)), days[s + batch:s + 2 * batch])
            for k, f in enumerate(cur):
                m = mon[s + k]
                if var in ("tmax", "tmin"):
                    acc[m] += f - 273.15
                elif var == "ppt":
                    acc[m] += np.maximum(f, 0) * 1000.0
                else:
                    acc[m] += _sat_vap32(f - 273.15)
        if var != "ppt":
            acc /= cnt[:, None, None].astype("float32")
        # values at the places: (12, NT, 4) x weights
        series[:, yi] = np.einsum("mnc,nc->nm", acc[:, I, J], W)
        cell[hasc, yi] = acc[:, ci[hasc], cj[hasc]].T
        for wi, (a, b) in enumerate(hw):
            if a <= y <= b:
                w[wi] += acc[:, :720].reshape(12, 360, 2, 720, 2).mean((2, 4)) / (b - a + 1)
        done.add(y)
        C.save(ck, series=series, cell=cell, w0=w[0], w1=w[1], done=np.array(sorted(done)))
        C.log.info("era5 %s %d done (%d/%d) %.0fs", var, y, len(done), len(years), time.time() - t0)
    C.save(out_f, var=np.array(var), years=np.array(years), series=series, w0=w[0], w1=w[1], lsm05=lsm05,
           cell=cell, cell_i=ci.astype("int32"), cell_j=cj.astype("int32"), cell_km=ckm.astype("float32"),
           cell_lsm=np.where(hasc, lsm[np.maximum(ci, 0), np.maximum(cj, 0)], np.nan).astype("float32"),
           labels=T.label.values.astype(str), windows=np.array(hw))
    ck.unlink(missing_ok=True)
    C.log.info("era5 %s written: %s", var, out_f)


# ------------------------------------------------------------------------------------------ use by other steps
def available() -> bool:
    return all(C.work("era5", f"{v}.npz").exists() for v in ARRAY)


def load_series(T=None):
    """{var: (NT, ny, 12)} and the years, or None when the era5 step has not run."""
    if not available():
        return None
    d = {v: C.load(C.work("era5", f"{v}.npz")) for v in ARRAY}
    if T is not None:
        assert list(d["tmax"]["labels"]) == T.label.tolist(), "ERA5 was extracted for different places"
    return d


def baseline_vectors(d, b0, b1):
    """ERA5 16-value seasonal baseline (NT, 16) for the years b0..b1 (mean of per-year seasonal vectors, as for the
    other sources: DJF of year y uses December of y-1)."""
    years = d["tmax"]["years"]
    ys = [y for y in range(b0, b1 + 1) if y in set(years.tolist()) and (y - 1) in set(years.tolist())]
    NT = d["tmax"]["series"].shape[0]
    out = np.full((NT, C.nvx()), np.nan)                 # 16 standard columns (+4 per active extra, NaN: ERA5 has no pet or srad)
    if not ys:
        return out
    for k in range(NT):
        out[k] = np.nanmean(C.seasonal_years({v: d[v]["series"][k] for v in ARRAY}, years, ys), 0)
    return out


def _normals(series, years, b0, b1):
    """Monthly normals (NT, 12) over the years b0..b1 of a (NT, ny, 12) series (NaN where no year has data)."""
    years = np.asarray(years)
    sel = (years >= b0) & (years <= b1)
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        return np.nanmean(np.asarray(series, "float64")[:, sel], axis=1)


def cell_vectors(d, b0, b1):
    """(NT, nvx) ERA5 baseline of each place's own land cell (monthly normals over b0..b1, then seasonalised; extras NaN).
    NaN rows: no land cell. None when the era5 files predate the per-cell series."""
    if "cell" not in d["tmax"]:
        return None
    mon = {v: _normals(d[v]["cell"], d[v]["years"], b0, b1) for v in ARRAY}
    return C.seasonalize({v: m.T for v, m in mon.items()}).T


def box_vectors(tc, d, names):
    """(NT, nvx) the place's baseline dataset (TerraClimate, all monthly variables in names) averaged over the land pixels
    of that place's ERA5 land cell, from the per-cell normals the TerraClimate step writes (box_cells, box_normals).
    NaN rows: no land cell, or no TerraClimate land pixel in it. None when either step predates the per-cell output."""
    if "cell_i" not in d["tmax"] or any("box_cells" not in tc[v] for v in names):
        return None
    ci, cj = np.asarray(d["tmax"]["cell_i"]), np.asarray(d["tmax"]["cell_j"])
    flat = ci.astype(np.int64) * NLON + cj
    mon = {}
    for v in names:
        cells = np.asarray(tc[v]["box_cells"], np.int64)
        m = np.full((len(ci), 12), np.nan)
        if not len(cells):
            mon[v] = m
            continue
        pos = np.clip(np.searchsorted(cells, flat), 0, len(cells) - 1)
        hit = (ci >= 0) & (cells[pos] == flat)
        m[hit] = np.asarray(tc[v]["box_normals"], "float64")[:, pos[hit]].T
        mon[v] = m
    return C.seasonalize({v: m.T for v, m in mon.items()}).T


def untransform(X):
    """Inverse of C.transform (precipitation and log-matched extras back from log(x+1); divided extras multiplied back)."""
    X = np.array(X, dtype="float64", copy=True)
    X[..., C.PPT] = np.exp(X[..., C.PPT]) - 1.0
    for j, n in enumerate(C._ACTIVE):
        if X.shape[-1] >= C.NV + 4 * (j + 1):
            c = slice(C.NV + 4 * j, C.NV + 4 * j + 4)
            X[..., c] = np.exp(X[..., c]) - 1.0 if C.EXTRAS[n]["log"] else X[..., c] * C.EXTRAS[n]["div"]
    return X


def footprint(base, point, box):
    """The place's own baseline carried from its point (10 km neighbourhood) to the footprint of its ERA5 cell, using the
    TerraClimate difference between the cell box and the point: base + (box - point) for temperatures and dewpoints,
    base x (box + 1) / (point + 1) for precipitation (the same shift in the metric's transformed space). For TerraClimate
    places base is the point, so this is exactly the box mean; AdaptWest places keep their own dataset, moved by
    TerraClimate's point-to-cell difference."""
    return untransform(C.transform(base) + C.transform(box) - C.transform(point))


def matched(d, tc, base, point, b0, b1, names, mode="cell"):
    """The two vectors the baseline-agreement check compares. mode "cell" (matched resolution): the place's baseline
    moved to its ERA5 land cell's footprint (footprint()) against that one cell (cell_vectors()); places without a land
    cell get NaN ('no land cell'). mode "point", or files from before the per-cell output: the place's point baseline
    against ERA5 interpolated to the point (the original check). Returns (ref, era, no_cell (NT,) bool, mode used)."""
    NT = base.shape[0]
    if mode == "cell":
        ev, bx = cell_vectors(d, b0, b1), box_vectors(tc, d, names)
        if ev is None or bx is None:
            C.log.warning("era5: per-cell output missing (%s): falling back to the point comparison",
                          "ERA5 cell series" if ev is None else "TerraClimate box normals")
        else:
            ref = footprint(base, point, bx)
            nocell = np.asarray(d["tmax"]["cell_i"]) < 0
            return ref, ev, nocell, "cell"
    return np.array(base, "float64", copy=True), baseline_vectors(d, b0, b1), np.zeros(NT, bool), "point"


def offsets(base, era, groups):
    """Typical ERA5 minus baseline difference per measure (in the metric's space: precipitation as log ratio), the median
    over places of each group (0 = AdaptWest places, 1 = TerraClimate places). ERA5 has systematic offsets against the
    gridded observational datasets (warm nights, slightly cool days, wet bias); left in, they would flag most places, so
    the agreement measures how far a place departs from that typical offset."""
    diff = C.transform(era) - C.transform(base)
    off = np.zeros((2, diff.shape[1]))
    for g in (0, 1):
        ok = (groups == g) & np.isfinite(diff).all(1)
        if ok.sum() >= 3:
            off[g] = np.median(diff[ok], 0)
    return off


def agreement(sm, midx, a, b, off=None):
    """Sigma distance between two 16-vectors under a place's variability model (same metric as the matching);
    off (16,) is subtracted from b's transformed vector first (the typical dataset offset)."""
    tb = C.transform(b) - (0 if off is None else off)
    pa, pb = sm.project(C.transform(a)[midx])[0], sm.project(tb[midx])[0]
    return float(C.chi_to_sigma(np.sqrt(((pa - pb) ** 2).sum()), sm.k)[0])
