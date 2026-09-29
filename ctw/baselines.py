"""More independent opinions on every place's present climate, and the combined baseline-agreement check.

Sources (era5.py holds the first; this module holds the rest and the generalised metric):
  era5    all 16 measures                          (ctw/era5.py)
  chirps  precipitation only (cols 8-11)           CHIRPS v2.0 monthly, 0.05 deg, 50S-50N, 1991-2020 (Funk et al. 2015)
  chelsa  highs, lows, precipitation (cols 0-11)   CHELSA v2.1 monthly climatologies 1981-2010, 30 arcsec (Karger et al. 2017)

CHIRPS is fetched one monthly GeoTIFF at a time (chirps-v2.0.YYYY.MM.tif.gz, ~14 MB): downloaded, sampled at every place,
deleted. The gzip stream cannot be read in windows, so a partial read would still pull the whole file. The job is split
into parts of consecutive years (one Actions job each): work/chirps/part{i}.npz holds series (NT, ny, 12) of monthly
precipitation (mm) at every place.

CHELSA is fetched one climatology file at a time (36 files: tasmax, tasmin, pr x 12 months), each sampled at every place
and deleted; one job per variable writes work/chelsa/{var}.npz with normal (NT, 12). CHELSA covers 1981-2010, not
1991-2020: the period difference (about 0.5 C of warming, small precipitation shifts) is a systematic offset that the
same per-measure median-offset removal used for ERA5 takes out.

Agreement: for each source, the sigma distance between the place's baseline and the source's baseline on the measures
that source covers, under the place's own variability model restricted to those measures (marginal covariance of the
matching model), after subtracting the source's typical offset (median over places, per measure and place group).
The combined agreement of a place is the maximum over sources; the source that gives it is the one the page names."""
from __future__ import annotations
import gzip, os, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from . import common as C

SOURCES = ("era5", "chirps", "chelsa")
COLS = {"era5": np.arange(16), "chirps": np.arange(8, 12), "chelsa": np.arange(12)}
LABEL = {"era5": "ERA5", "chirps": "CHIRPS", "chelsa": "CHELSA"}
CHIRPS_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/chirps-v2.0.{y}.{m:02d}.tif.gz"
# CHELSA moved from os.zhdk.ch/envicloud (retired) to the SWITCH object store in 2026 (layout checked 2026-09-29).
CHELSA_URL = ("https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/{v}/1981-2010/"
              "CHELSA_{v}_{m:02d}_1981-2010_V.2.1.tif")
CHELSA_VARS = {"tasmax": "tmax", "tasmin": "tmin", "pr": "ppt"}


# ------------------------------------------------------------------------------------------ sampling rasters at places
def _gather(a, r, c, rad):
    """Mean of the valid (finite) cells within rad of (r, c); returns (sum, count). a is a 2-D float array with NaN gaps."""
    s = np.zeros(len(r)); n = np.zeros(len(r))
    for dr in range(-rad, rad + 1):
        for dc in range(-rad, rad + 1):
            rr = np.clip(r + dr, 0, a.shape[0] - 1); cc = np.clip(c + dc, 0, a.shape[1] - 1)
            v = a[rr, cc]
            ok = np.isfinite(v)
            s += np.where(ok, v, 0.0); n += ok
    return s, n


def sample_array(a, r, c, rads=(0, 1, 2)):
    """Values of the 2-D array a (NaN = no data) at integer cells (r, c): the cell itself if valid, else the mean of the
    valid cells within 1 cell, else 2 (radii in rads). NaN where nothing valid is found."""
    out = np.full(len(r), np.nan)
    todo = np.ones(len(r), bool)
    for rad in rads:
        if not todo.any():
            break
        s, n = _gather(a, r[todo], c[todo], rad)
        got = n > 0
        idx = np.where(todo)[0][got]
        out[idx] = s[got] / n[got]
        todo[idx] = False
    return out


def sample_dataset(ds, lat, lon, rads=(0, 1, 2), strip=512, positive=False):
    """Sample band 1 of an open rasterio dataset at the places (NaN outside the raster or in no-data areas). Reads
    strips of rows, so a very large raster is never held whole. Scale and offset tags are applied. positive: negative
    values are no-data (precipitation)."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    inv = ~ds.transform
    col, row = inv * (lon, lat)
    row, col = np.floor(row).astype(int), np.floor(col).astype(int)
    inside = (row >= 0) & (row < ds.height) & (col >= 0) & (col < ds.width)
    out = np.full(len(lat), np.nan)
    pad = max(rads)
    scale = (ds.scales[0] if ds.scales else 1.0) or 1.0
    offset = (ds.offsets[0] if ds.offsets else 0.0) or 0.0
    nod = ds.nodata
    from rasterio.windows import Window
    for r0 in range(0, ds.height, strip):
        sel = np.where(inside & (row >= r0) & (row < r0 + strip))[0]
        if not len(sel):
            continue
        a0, a1 = max(0, r0 - pad), min(ds.height, r0 + strip + pad)
        raw = ds.read(1, window=Window(0, a0, ds.width, a1 - a0)).astype("float64")
        bad = ~np.isfinite(raw)
        if nod is not None and np.isfinite(nod):
            bad |= raw == nod
        a = raw * scale + offset
        if positive:
            bad |= a < 0
        a[bad] = np.nan
        out[sel] = sample_array(a, row[sel] - a0, col[sel], rads)
    return out


# ------------------------------------------------------------------------------------------ CHIRPS
def chirps_years(cfg):
    b0, b1 = cfg["baseline"]["years"]
    env = os.environ.get("CTW_CHIRPS_YEARS")
    if env:
        a, b = env.split("-")
        return list(range(int(a), int(b) + 1))
    ys = list(range(b0 - 1, b1 + 1))                 # December of the year before feeds DJF
    return ys[:3] if C.SMOKE else ys


def split_years(ys, part, of):
    return [int(y) for y in np.array_split(np.array(ys), of)[part]]


def _chirps_month(y, m, lat, lon, tmp):
    import rasterio
    from rasterio.io import MemoryFile
    dest = tmp / f"chirps-v2.0.{y}.{m:02d}.tif.gz"
    C.download(CHIRPS_URL.format(y=y, m=m), dest)
    with gzip.open(dest, "rb") as fh:
        data = fh.read()
    dest.unlink(missing_ok=True)
    with MemoryFile(data) as mf, mf.open() as ds:
        return sample_dataset(ds, lat, lon, rads=(0, 1, 2), positive=True)


def run_chirps(part=0, of=1, cfg=None):
    cfg = cfg or C.config()
    T = C.targets()
    ys = split_years(chirps_years(cfg), part, of)
    if not ys:                                        # smoke runs use fewer years than parts
        C.log.info("chirps part %d: no years", part)
        return None, ys
    lat, lon = T.lat.values, T.lon.values
    tmp = C.work("chirps", "tmp", f"part{part}", "x").parent
    series = np.full((len(T), len(ys), 12), np.nan, "float32")
    t0 = time.time()
    jobs = [(yi, m) for yi in range(len(ys)) for m in range(1, 13)]
    with ThreadPoolExecutor(int(os.environ.get("CTW_CHIRPS_THREADS", 6))) as pool:
        futs = [(yi, m, pool.submit(_chirps_month, ys[yi], m, lat, lon, tmp)) for yi, m in jobs]
        for n, (yi, m, f) in enumerate(futs):
            series[:, yi, m - 1] = f.result()
            if m == 12:
                C.log.info("chirps %d done (%d/%d files) %.0fs", ys[yi], n + 1, len(jobs), time.time() - t0)
    C.save(C.work("chirps", f"part{part}.npz"), years=np.array(ys), series=series, labels=T.label.values.astype(str))
    C.log.info("chirps part %d written: years %d-%d, %.0fs, %d of %d places have data", part, ys[0], ys[-1], time.time() - t0,
               int(np.isfinite(series).any((1, 2)).sum()), len(T))
    return series, ys


def load_chirps(T=None):
    """(years, series (NT, ny, 12)) from all work/chirps/part*.npz, or None."""
    fs = sorted(C.work("chirps", "x").parent.glob("part*.npz"))
    if not fs:
        return None
    parts = [C.load(f) for f in fs]
    if T is not None:
        for p in parts:
            assert list(p["labels"]) == T.label.tolist(), "CHIRPS was extracted for different places"
    years = np.concatenate([p["years"] for p in parts])
    order = np.argsort(years)
    series = np.concatenate([p["series"] for p in parts], 1)[:, order]
    return years[order], series


def seasonal_ppt(series, years, ys):
    """(NT, len(ys), 4) seasonal precipitation totals from monthly series (NT, ny, 12): DJF of year y uses December of y-1."""
    pos = {int(y): i for i, y in enumerate(years)}
    out = np.full((series.shape[0], len(ys), 4), np.nan)
    for n, y in enumerate(ys):
        if y not in pos or (y - 1) not in pos:
            continue
        m = series[:, pos[y]].astype("float64").copy()
        m[:, 11] = series[:, pos[y - 1], 11]
        for s, ms in enumerate(C.SEASONS):
            out[:, n, s] = m[:, [x - 1 for x in ms]].sum(1)
    return out


def chirps_vectors(years, series, b0, b1):
    """(NT, nvx) baseline: seasonal precipitation (mean over b0..b1) in the four precipitation columns, NaN elsewhere."""
    ys = [y for y in range(b0, b1 + 1) if y in set(np.asarray(years).tolist()) and (y - 1) in set(np.asarray(years).tolist())]
    out = np.full((series.shape[0], C.nvx()), np.nan)
    if ys:
        with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore")
            out[:, C.PPT] = np.nanmean(seasonal_ppt(series, years, ys), 1)
    return out


def icv_ratio(years, series, b0, b1, icvsd):
    """Interannual variability check: detrended SD of log(seasonal precipitation + 1) in CHIRPS over the baseline years,
    divided by the SD in the place's variability model (icvsd, precipitation columns). Returns (NT, 4), NaN where unavailable."""
    ys = [y for y in range(b0, b1 + 1) if y in set(np.asarray(years).tolist()) and (y - 1) in set(np.asarray(years).tolist())]
    NT = series.shape[0]
    out = np.full((NT, 4), np.nan)
    if len(ys) < 10:
        return out
    L = np.log(seasonal_ppt(series, years, ys) + 1.0)
    for k in range(NT):
        if np.isfinite(L[k]).all():
            out[k] = C.detrend(L[k]).std(0, ddof=1) / np.maximum(icvsd[k, C.PPT], 1e-6)
    return out


# ------------------------------------------------------------------------------------------ CHELSA
def chelsa_months(cfg):
    env = os.environ.get("CTW_CHELSA_MONTHS")
    if env:
        return [int(x) for x in env.split(",")]
    return [1, 7] if C.SMOKE else list(range(1, 13))


def to_physical(var, x):
    """CHELSA v2.1 stores temperature in Kelvin and precipitation in kg m-2 month-1 (scale/offset tags are applied when
    the raster is read). Guard against a file still carrying Kelvin after scaling, or Kelvin x 10 without a scale tag;
    anything that is not a plausible air temperature afterwards is an error, not a silent wrong number."""
    x = np.asarray(x, float)
    if var in ("tasmax", "tasmin") and np.isfinite(x).any():
        med = np.nanmedian(x)
        if med > 1000:
            x = x / 10.0
            med /= 10.0
        if med > 150:
            x = x - 273.15
        if not -60 < np.nanmedian(x) < 50:
            raise ValueError(f"CHELSA {var}: unexpected units (median {med:.0f} before conversion)")
    return x


def _chelsa_month(var, m, lat, lon, tmp, tries=3):
    import rasterio
    url = CHELSA_URL.format(v=var, m=m)
    dest = tmp / f"CHELSA_{var}_{m:02d}.tif"
    t0 = time.time()
    C.download(url, dest, tries=tries)
    t1 = time.time()
    with rasterio.open(dest) as ds:
        v = sample_dataset(ds, lat, lon, rads=(1, 3))
        info = f"{ds.width}x{ds.height} {ds.dtypes[0]} scale={ds.scales[0]} offset={ds.offsets[0]} nodata={ds.nodata}"
    size = dest.stat().st_size / 1e6
    dest.unlink(missing_ok=True)
    C.log.info("chelsa %s %02d: %.0f MB in %.0fs, sampled in %.0fs; %s", var, m, size, t1 - t0, time.time() - t1, info)
    return to_physical(var, v)


def run_chelsa(var, cfg=None):
    cfg = cfg or C.config()
    T = C.targets()
    ms = chelsa_months(cfg)
    lat, lon = T.lat.values, T.lon.values
    tmp = C.work("chelsa", "tmp", var, "x").parent
    normal = np.full((len(T), 12), np.nan, "float32")
    t0 = time.time()
    with ThreadPoolExecutor(int(os.environ.get("CTW_CHELSA_THREADS", 3))) as pool:
        futs = [(m, pool.submit(_chelsa_month, var, m, lat, lon, tmp)) for m in ms]
        for m, f in futs:
            normal[:, m - 1] = f.result()
    C.save(C.work("chelsa", f"{var}.npz"), var=np.array(var), normal=normal, months=np.array(ms), labels=T.label.values.astype(str))
    C.log.info("chelsa %s written: %d months, %.0fs, %d of %d places have data", var, len(ms), time.time() - t0,
               int(np.isfinite(normal).any(1).sum()), len(T))
    return normal


def load_chelsa(T=None):
    """{var: (NT, 12)} for tmax, tmin, ppt (CHELSA's tasmax, tasmin, pr) or None when any is missing."""
    d = {}
    for cv, v in CHELSA_VARS.items():
        f = C.work("chelsa", f"{cv}.npz")
        if not f.exists():
            return None
        z = C.load(f)
        if T is not None:
            assert list(z["labels"]) == T.label.tolist(), "CHELSA was extracted for different places"
        d[v] = z["normal"]
    return d


def chelsa_vectors(d):
    """(NT, nvx) seasonal vectors from monthly normals {tmax, tmin, ppt: (NT, 12)}; dewpoint and extras are NaN."""
    v = C.seasonalize({k: np.asarray(x, "float64").T for k, x in d.items()})       # (nvx, NT)
    return v.T


# ------------------------------------------------------------------------------------------ the generalised metric
def offsets(base, other, groups, cols):
    """Typical (other - base) difference per measure in the metric's space (precipitation as a log ratio), the median over
    places of each group (0 = AdaptWest places, 1 = TerraClimate places), using places where the covered columns are
    finite. Columns outside cols stay 0. Returns (2, nvx)."""
    diff = C.transform(other) - C.transform(base)
    off = np.zeros((2, diff.shape[1]))
    cols = np.asarray(cols)
    for g in (0, 1):
        ok = (groups == g) & np.isfinite(diff[:, cols]).all(1)
        if ok.sum() >= 3:
            off[g, cols] = np.median(diff[ok][:, cols], 0)
    return off


def covariance(sm):
    """Covariance of the model's standardised measures as (Cs, sd) from a ShrinkSigmaModel: x/sd has covariance
    V diag(pc_sd^2) V'. The matching model lives on the matched columns (midx)."""
    return (sm.V * sm.pc_sd ** 2) @ sm.V.T, sm.sd


def sigma_on(sm, midx, cols, a, b, off=None):
    """Sigma distance between vectors a and b (nvx,) restricted to the measures cols that are also matched, under the place's
    variability model marginalised to them. off (nvx,) is subtracted from b's transformed vector first. NaN when nothing
    overlaps or a value is missing."""
    midx = np.asarray(midx)
    sub = [i for i, c in enumerate(midx) if c in set(np.asarray(cols).tolist())]
    if not sub:
        return float("nan")
    ta, tb = C.transform(a)[midx[sub]], C.transform(b)[midx[sub]]
    if off is not None:
        tb = tb - np.asarray(off)[midx[sub]]
    d = ta - tb
    if not np.isfinite(d).all():
        return float("nan")
    Cs, sd = covariance(sm)
    S = Cs[np.ix_(sub, sub)] * np.outer(sd[sub], sd[sub])
    D2 = float(d @ np.linalg.solve(S, d))
    return float(C.chi_to_sigma(np.sqrt(max(D2, 0.0)), len(sub))[0])


def source_agreement(SH, midx, base, other, groups, cols, ok=None):
    """Per-place sigma disagreement of one source, offsets removed. ok: boolean mask of places with a model. Returns
    (sigma (NT,), offsets (2, nvx))."""
    NT = base.shape[0]
    cols = np.asarray(cols)
    fin = np.isfinite(other[:, cols]).all(1) & np.isfinite(base[:, cols]).all(1)
    use = fin if ok is None else fin & ok
    off = offsets(base[use], other[use], groups[use], cols)
    sig = np.full(NT, np.nan, "float32")
    for k in np.where(use)[0]:
        sig[k] = sigma_on(SH[k], midx, cols, base[k], other[k], off[groups[k]])
    return sig, off


def combine(sig, mode="worst"):
    """sig (NT, n_sources) with NaN for unavailable. Returns (sigma (NT,), index of the source giving it (NT,), -1 where none).
    mode "worst": the largest disagreement over the sources. mode "corroborated": the second largest, so a place is only
    flagged when two independent datasets both disagree with its baseline; NaN where fewer than two sources exist."""
    sig = np.asarray(sig, float)
    have = np.isfinite(sig)
    filled = np.where(have, sig, -np.inf)
    if mode == "corroborated":
        if sig.shape[1] < 2:
            return np.full(len(sig), np.nan, "float32"), np.full(len(sig), -1, "int8")
        order = np.argsort(filled, axis=1)
        idx = order[:, -2]
        second = np.take_along_axis(filled, idx[:, None], 1)[:, 0]
        ok = np.isfinite(second)
        return np.where(ok, second, np.nan).astype("float32"), np.where(ok, idx, -1).astype("int8")
    idx = filled.argmax(1)
    worst = np.where(have.any(1), filled.max(1), np.nan)
    return worst.astype("float32"), np.where(have.any(1), idx, -1).astype("int8")
