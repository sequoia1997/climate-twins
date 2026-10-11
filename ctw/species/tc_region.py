"""TerraClimate at its native 1/24 degree grid for Spike B: regional reads by HTTP range requests (h5py over fsspec), so a
20 x 20 degree box costs a fraction of the global yearly file, and a whole-globe pass is the fallback."""
from __future__ import annotations
import time
import numpy as np

TC_URL = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA/TerraClimate_{v}_{y}.nc"
VARS = ("tmax", "tmin", "ppt", "def", "aet", "soil", "pet", "vpd", "srad")


def read_months(var, year, rows, cols, block_mb=16, url=TC_URL):
    """(12, ny, nx) float32 of one TerraClimate variable-year over a window of the native grid; fill values become NaN.
    Returns (array, seconds)."""
    import fsspec, h5py
    t0 = time.time()
    with fsspec.open(url.format(v=var, y=year), block_size=block_mb << 20).open() as f, h5py.File(f, "r") as h:
        d = h[var]
        raw = d[:, rows, cols]
        at = dict(d.attrs)
    return decode(raw, at), time.time() - t0


def decode(raw, at):
    """Apply fill value, scale_factor and add_offset attributes."""
    a = raw.astype("float32")
    for k in ("_FillValue", "missing_value"):
        if k in at:
            fv = np.asarray(at[k]).ravel()[0]
            a[raw == fv] = np.nan
    if np.issubdtype(raw.dtype, np.floating):
        a[np.abs(raw) > 1e30] = np.nan
    sf = float(np.asarray(at.get("scale_factor", 1.0)).ravel()[0]); off = float(np.asarray(at.get("add_offset", 0.0)).ravel()[0])
    return a * sf + off
