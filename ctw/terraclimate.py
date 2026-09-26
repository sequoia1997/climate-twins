"""TerraClimate (Abatzoglou et al. 2018), monthly, 1/24°. One pass per variable over its yearly global files gives:
  normals05   (12, 360, 720)  baseline-period monthly normals on the 0.5° world grid (block means of land pixels)
  land05      (360, 720)      land fraction of each 0.5° cell
  series      (NT, ny, 12)    10 km neighbourhood mean at every place, for every year (Dec of year 0 feeds DJF)
  laea        (12, ny, nx)    baseline normals sampled at the North American 15 km grid cells (humidity only)
Files are fetched one year ahead of processing and deleted after use; progress is checkpointed after every year."""
from __future__ import annotations
import queue, threading, time
import netCDF4
import numpy as np
from pyproj import Transformer
from . import common as C

NLAT, NLON, B = 4320, 8640, 12
LAT = np.linspace(89.979164, -89.979164, NLAT)
LON = np.linspace(-179.97917, 179.97917, NLON)


def latest_year(cfg) -> int:
    """Latest year whose TerraClimate files exist (TerraClimate publishes whole years). The rebuild's plan job
    asks once and passes the answer on in CTW_TC_LATEST. Server hiccups are retried with growing waits."""
    import os
    if os.environ.get("CTW_TC_LATEST"):
        return int(os.environ["CTW_TC_LATEST"])
    if cfg["recent"]["end"] != "auto":
        return int(cfg["recent"]["end"])
    y = time.gmtime().tm_year
    s = C.http()
    for yy in range(y, y - 4, -1):
        url = cfg["sources"]["terraclimate"].format(v="tmax", y=yy)
        for attempt in range(8):
            try:
                r = s.head(url, timeout=60, allow_redirects=True)
                break
            except Exception as e:  # noqa: BLE001 - connection refused, timeouts: wait and try again
                wait = min(300, 20 * 2 ** attempt)
                C.log.warning("TerraClimate not answering (%s); retry in %ss", e, wait)
                time.sleep(wait)
        else:
            raise RuntimeError("TerraClimate server unreachable")
        if r.status_code == 200:
            return yy
    raise RuntimeError("no recent TerraClimate year found")


def neighbourhoods(lat, lon):
    """Pixel windows (9 x 13) around each place and their distances, as in the v9 build."""
    II, JJ, DD = [], [], []
    for la, lo in zip(lat, lon):
        i0, j0 = int(round((89.979164 - la) * 24)), int(round((lo + 179.97917) * 24))
        ii, jj = np.mgrid[i0 - 4:i0 + 5, j0 - 6:j0 + 7]
        ii = np.clip(ii, 0, NLAT - 1)
        jj = np.mod(jj, NLON)
        II.append(ii); JJ.append(jj)
        DD.append(6371 * np.hypot(np.radians(LAT[ii] - la), np.radians(LON[jj] - lo) * np.cos(np.radians(la))))
    return np.array(II), np.array(JJ), np.array(DD)


def laea_pixels(cfg):
    """Nearest 1/24° pixel (plus its 3x3 neighbours) for every North American 15 km cell centre."""
    g = cfg["grids"]
    nx, ny, cm = g["na_nx"], g["na_ny"], g["na_cell_m"]
    xc = g["na_x0"] + (np.arange(nx) + 0.5) * cm
    yc = g["na_y0"] - (np.arange(ny) + 0.5) * cm
    X, Y = np.meshgrid(xc, yc)
    lon, lat = Transformer.from_crs(g["na_crs"], "EPSG:4326", always_xy=True).transform(X.ravel(), Y.ravel())
    i0 = np.clip(np.round((89.979164 - lat) * 24).astype(int), 1, NLAT - 2)
    j0 = np.round((lon + 179.97917) * 24).astype(int)
    di, dj = np.meshgrid([-1, 0, 1], [-1, 0, 1], indexing="ij")
    return (i0[:, None] + di.ravel()[None]), np.mod(j0[:, None] + dj.ravel()[None], NLON), (ny, nx)


def run(var: str, cfg=None):
    cfg = cfg or C.config()
    T = C.targets()
    y_end = latest_year(cfg)
    b0, b1 = cfg["baseline"]["years"]
    y_first = b0 - 1                                            # December of b0-1 feeds the first winter
    years = list(range(y_first, y_end + 1))
    if C.SMOKE:
        years = [y for y in years if y <= y_first + 6] + [y for y in (y_end - 1, y_end) if y > y_first + 6]
    base_years = [y for y in years if b0 <= y <= b1]
    out_f = C.work("terraclimate", f"{var}.npz")
    ck = C.work("terraclimate", f"{var}.ckpt.npz")
    II, JJ, DD = neighbourhoods(T.lat.values, T.lon.values)
    LI = LJ = shp = None
    if var == "vap":
        LI, LJ, shp = laea_pixels(cfg)
    NY, NX = NLAT // B, NLON // B
    if ck.exists():
        d = C.load(ck)
        acc, lacc, series, land, done = d["acc"], d["lacc"], d["series"], d["land"], set(d["done"].tolist())
        if land.ndim == 0:
            land = None
    else:
        acc = np.zeros((12, NY, NX)); lacc = np.zeros((12, LI.shape[0])) if LI is not None else np.zeros(0)
        series = np.full((len(T), len(years), 12), np.nan, "float32"); land = None; done = set()
    todo = [y for y in years if y not in done]
    url = cfg["sources"]["terraclimate"]
    q: queue.Queue = queue.Queue(maxsize=1)

    def fetch():
        for y in todo:
            q.put((y, C.download(url.format(v=var, y=y), C.work("tmp", f"tc_{var}_{y}.nc"))))
        q.put(None)

    threading.Thread(target=fetch, daemon=True).start()
    t0 = time.time()
    while (item := q.get()) is not None:
        y, path = item
        yi = years.index(y)
        with netCDF4.Dataset(path) as ds:
            v = ds[var]
            v.set_auto_mask(True)
            for m in range(12):
                a = np.ma.filled(v[m].astype("float32"), np.nan)
                blk = a[II, JJ]
                ok = np.isfinite(blk)
                sel = ok & (DD <= 10)
                for k in np.where(~sel.any((1, 2)) & ok.any((1, 2)))[0]:   # no land within 10 km: nearest land pixel
                    sel[k].flat[np.argmin(np.where(ok[k], DD[k], np.inf))] = True
                n = sel.sum((1, 2))
                series[:, yi, m] = np.where(n > 0, np.where(sel, blk, 0).sum((1, 2)) / np.maximum(n, 1), np.nan)
                if y in base_years:
                    a4 = a.reshape(NY, B, NX, B)
                    cnt = np.isfinite(a4).sum((1, 3))
                    with np.errstate(invalid="ignore"):
                        acc[m] += np.nansum(a4, axis=(1, 3)) / np.maximum(cnt, 1)
                    if land is None:
                        land = cnt / B ** 2
                    if LI is not None:
                        with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
                            __import__("warnings").simplefilter("ignore")
                            lacc[m] += np.nan_to_num(np.nanmean(a[LI, LJ], axis=1), nan=-9e9)
                del a
        path.unlink(missing_ok=True)
        done.add(y)
        C.save(ck, acc=acc, lacc=lacc, series=series, land=land if land is not None else np.array(0.0), done=np.array(sorted(done)))
        C.log.info("terraclimate %s %d done (%d/%d) %.0fs", var, y, len(done), len(years), time.time() - t0)
    nb = len(base_years)
    out = dict(var=np.array(var), years=np.array(years), y_first=np.array(y_first), latest=np.array(y_end),
               normals05=(acc / nb).astype("float32"), land05=land.astype("float32"), series=series,
               labels=T.label.values.astype(str))
    if LI is not None:
        L = lacc / nb
        L[L < -1e8] = np.nan                                     # cells with no land pixel in any baseline year
        out["laea"] = L.reshape(12, *shp).astype("float32")
    C.save(out_f, **out)
    ck.unlink(missing_ok=True)
    C.log.info("terraclimate %s written: %s", var, out_f)
