"""PRISM monthly 4 km time series (PRISM Climate Group; Daly et al. 2008) at contiguous-US places:
10 km neighbourhood means (nearest valid cell if none), December of the year before the baseline through the
baseline's last December. Year-to-year variability in the contiguous US uses these; elsewhere TerraClimate.
Writes work/prism.npz: tmax/tmin/ppt (NT, nyears, 12), NaN for places outside the contiguous US."""
from __future__ import annotations
import io, time, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from . import common as C

VARS = ("tmax", "tmin", "ppt")


def read_zip(blob: bytes):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".tif"))
        data = z.read(name)
    with MemoryFile(data) as mf, mf.open() as r:
        return r.read(1, masked=True).astype("float32").filled(np.nan), r.transform


def fetch(url, tries=8):
    s = C.http()
    for attempt in range(tries):
        try:
            r = s.get(url, timeout=180)
            r.raise_for_status()
            return r.content
        except Exception as e:  # noqa: BLE001
            C.log.warning("prism %s failed (%s)", url, e)
            time.sleep(min(300, 10 * 2 ** attempt))
    raise RuntimeError(url)


def run(cfg=None):
    cfg = cfg or C.config()
    T = C.targets()
    conus = np.where(T.domain.values == "conus")[0]
    b0, b1 = cfg["baseline"]["years"]
    y_first = b0 - 1
    years = list(range(y_first, b1 + 1))
    months = [(y_first, 12)] + [(y, m) for y in range(b0, b1 + 1) for m in range(1, 13)]
    if C.SMOKE:
        months = months[:73]                     # December 1990 through 1996
    url = cfg["sources"]["prism"]
    out = {v: np.full((len(T), len(years), 12), np.nan, "float32") for v in VARS}
    # neighbourhoods from the first grid
    a, tr = read_zip(fetch(url.format(v="tmax", y=b0, m=1)))
    ny, nx = a.shape
    lat = tr.f + (np.arange(ny) + .5) * tr.e
    lon = tr.c + (np.arange(nx) + .5) * tr.a
    valid = np.isfinite(a)
    nb = {}
    for k in conus:
        la, lo = T.lat[k], T.lon[k]
        i0, j0 = int(np.argmin(np.abs(lat - la))), int(np.argmin(np.abs(lon - lo)))
        span = 12
        ii = np.arange(max(0, i0 - span), min(ny, i0 + span + 1))
        jj = np.arange(max(0, j0 - span), min(nx, j0 + span + 1))
        I, J = np.meshgrid(ii, jj, indexing="ij")
        d = C.haversine_km(la, lo, lat[I], lon[J])
        ok = valid[I, J]
        sel = ok & (d <= 10.0)
        if not sel.any():
            sel = np.zeros_like(ok)
            sel.flat[np.argmin(np.where(ok, d, np.inf))] = True
        nb[k] = (I[sel], J[sel])

    def job(v, y, m):
        g, _ = read_zip(fetch(url.format(v=v, y=y, m=m)))
        return v, y, m, {k: float(np.nanmean(g[I, J])) for k, (I, J) in nb.items()}

    t0 = time.time()
    tasks = [(v, y, m) for v in VARS for (y, m) in months]
    with ThreadPoolExecutor(8) as ex:
        futs = [ex.submit(job, *t) for t in tasks]
        for n, f in enumerate(as_completed(futs), 1):
            v, y, m, vals = f.result()
            for k, x in vals.items():
                out[v][k, y - y_first, m - 1] = x
            if n % 100 == 0:
                C.log.info("prism %d/%d %.0fs", n, len(tasks), time.time() - t0)
    C.save(C.work("prism.npz"), years=np.array(years), y_first=np.array(y_first), labels=T.label.values.astype(str), **out)
    C.log.info("prism done %.0fs", time.time() - t0)
