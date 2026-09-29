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
The place value is the bilinear interpolation of the four surrounding 0.25° cells, weighted toward land cells.
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
    la = ar["land_sea_mask"]
    lsm = np.asarray(la[0] if la.ndim == 3 else la[:], "float32")
    I, J, W = interp_weights(T.lat.values, T.lon.values, lsm)
    years = years_needed(cfg)
    hw = cfg["hindcast"]["windows"]
    arr = g[ARRAY[var]]
    out_f, ck = C.work("era5", f"{var}.npz"), C.work("era5", f"{var}.ckpt.npz")
    lsm05 = lsm[:720].reshape(360, 2, 720, 2).mean((1, 3))
    if ck.exists():
        d = C.load(ck)
        series, w, done = d["series"], [d["w0"], d["w1"]], set(d["done"].tolist())
    else:
        series = np.full((len(T), len(years), 12), np.nan, "float32")
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
        for wi, (a, b) in enumerate(hw):
            if a <= y <= b:
                w[wi] += acc[:, :720].reshape(12, 360, 2, 720, 2).mean((2, 4)) / (b - a + 1)
        done.add(y)
        C.save(ck, series=series, w0=w[0], w1=w[1], done=np.array(sorted(done)))
        C.log.info("era5 %s %d done (%d/%d) %.0fs", var, y, len(done), len(years), time.time() - t0)
    C.save(out_f, var=np.array(var), years=np.array(years), series=series, w0=w[0], w1=w[1], lsm05=lsm05,
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
    out = np.full((NT, C.NV), np.nan)
    if not ys:
        return out
    for k in range(NT):
        out[k] = np.nanmean(C.seasonal_years({v: d[v]["series"][k] for v in ARRAY}, years, ys), 0)
    return out


def agreement(sm, midx, a, b):
    """Sigma distance between two 16-vectors under a place's variability model (same metric as the matching)."""
    pa, pb = sm.project(C.transform(a)[midx])[0], sm.project(C.transform(b)[midx])[0]
    return float(C.chi_to_sigma(np.sqrt(((pa - pb) ** 2).sum()), sm.k)[0])
