"""AdaptWest / ClimateNA v7.30 1991-2020 monthly normals, 1 km, North America (AdaptWest Project 2022).
Writes work/adaptwest.npz with the 15 km pool (block means, land fraction) and each North American place's
baseline (mean of 1 km cells within 10 km; nearest valid pixel if none)."""
from __future__ import annotations
import time
import numpy as np
import rasterio
from pyproj import Transformer
from . import common as C

VMAP = {"tmax": "Tmax", "tmin": "Tmin", "ppt": "PPT"}
INNER = "Normal_1991_2020/Normal_1991_2020_monthly/Normal_1991_2020_{v}{m:02d}.tif"


def run(cfg=None):
    cfg = cfg or C.config()
    g = cfg["grids"]
    BLOCK = int(round(g["na_cell_m"] / 1000))
    zp = C.download(cfg["sources"]["adaptwest"], C.work("downloads", "adaptwest_monthly.zip"))
    Z = f"zip://{zp}!" + INNER
    T = C.targets()
    na = np.where(T.g.values == 0)[0]
    with rasterio.open(Z.format(v="Tmax", m=1)) as r:
        W, H, tr, crs = r.width, r.height, r.transform, r.crs
    x = tr.c + (np.arange(W) + .5) * tr.a
    y = tr.f + (np.arange(H) + .5) * tr.e
    ny, nx = H // BLOCK, W // BLOCK
    assert (ny, nx) == (g["na_ny"], g["na_nx"]), f"AdaptWest grid changed: {(ny, nx)}"
    assert abs(tr.c - g["na_x0"]) < 1 and abs(tr.f - g["na_y0"]) < 1, "AdaptWest grid origin changed"
    tx, ty = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(T.lon.values[na], T.lat.values[na])
    nb = []
    for X, Y in zip(tx, ty):
        j0, i0 = int((X - tr.c) / tr.a), int((Y - tr.f) / tr.e)
        ii, jj = np.mgrid[i0 - 11:i0 + 12, j0 - 11:j0 + 12]
        ok = (ii >= 0) & (ii < H) & (jj >= 0) & (jj < W)
        ii, jj = ii[ok], jj[ok]
        d = np.hypot(x[jj] - X, y[ii] - Y)
        nb.append((ii[d <= 10000], jj[d <= 10000], ii, jj, d))
    coarse = {v: np.zeros((12, ny, nx), "float32") for v in VMAP}
    tb = {v: np.full((len(T), 12), np.nan) for v in VMAP}
    landfrac = None
    t0 = time.time()
    months = range(1, 13)
    for v, V in VMAP.items():
        for m in months:
            with rasterio.open(Z.format(v=V, m=m)) as r:
                a = r.read(1).astype("float32")
            a[a < -1000] = np.nan
            b = a[:ny * BLOCK, :nx * BLOCK].reshape(ny, BLOCK, nx, BLOCK)
            cnt = np.isfinite(b).sum((1, 3))
            with np.errstate(invalid="ignore"):
                coarse[v][m - 1] = np.nansum(b, axis=(1, 3)) / np.maximum(cnt, 1)
            if landfrac is None:
                landfrac = cnt / BLOCK ** 2
            for n, (i, j, ia, ja, d) in enumerate(nb):
                vals = a[i, j]
                vals = vals[np.isfinite(vals)]
                if vals.size == 0:
                    va = a[ia, ja]
                    okk = np.isfinite(va)
                    vals = va[okk][np.argsort(d[okk])[:1]] if okk.any() else np.array([np.nan])
                tb[v][na[n], m - 1] = vals.mean()
            del a, b
            C.log.info("adaptwest %s %02d %.0fs", v, m, time.time() - t0)
    C.save(C.work("adaptwest.npz"), landfrac=landfrac.astype("float32"), crs=np.array(crs.to_wkt()),
           labels=T.label.values.astype(str), **coarse, **{"t_" + v: tb[v] for v in VMAP})
    C.log.info("adaptwest done: %d pool cells", int((landfrac >= g["na_landfrac_min"]).sum()))


BIOCLIM = {"pas": "PAS", "nffd": "NFFD", "emt": "EMT", "ffp": "FFP"}


def run_bioclim(cfg=None):
    """ClimateNA's station-calibrated snowfall (PAS, mm), frost-free days (NFFD) and extreme minimum temperature
    (EMT, °C), block-averaged to the 15 km pool. Used only to calibrate the monthly estimators in features.py."""
    from remotezip import RemoteZip
    cfg = cfg or C.config()
    g = cfg["grids"]
    BLOCK = int(round(g["na_cell_m"] / 1000))
    url = cfg["sources"]["adaptwest"].replace("_monthly.zip", "_bioclim.zip")
    out = {}
    with RemoteZip(url) as rz:
        names = rz.namelist()
        for k, V in BIOCLIM.items():
            member = next(n for n in names if n.endswith(f"_{V}.tif"))
            local = C.work("downloads", "adaptwest_bioclim", member.split("/")[-1])
            if not local.exists():
                local.parent.mkdir(parents=True, exist_ok=True)
                with rz.open(member) as src, open(local, "wb") as dst:
                    while chunk := src.read(1 << 22):
                        dst.write(chunk)
            with rasterio.open(local) as r:
                a = r.read(1).astype("float32")
                assert abs(r.transform.c - g["na_x0"]) < 1 and abs(r.transform.f - g["na_y0"]) < 1
            a[a < -1000] = np.nan
            ny, nx = g["na_ny"], g["na_nx"]
            b = a[:ny * BLOCK, :nx * BLOCK].reshape(ny, BLOCK, nx, BLOCK)
            with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
                __import__("warnings").simplefilter("ignore")
                out[k] = np.nanmean(b, axis=(1, 3)).astype("float32")
            C.log.info("bioclim %s done", V)
    C.save(C.work("adaptwest_bioclim.npz"), **out)
