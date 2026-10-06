"""NEX-GDDP-CMIP6 (0.25 degree daily) regional reads for Spike B: monthly means of tasmax, tasmin, pr over a lat/lon box, and
daily series for a few years. Each yearly file is one global gzip chunk per day, so a regional read still streams the whole
file (about 245 MB); it is read day by day and only the box is kept."""
from __future__ import annotations
import numpy as np

BUCKET = "https://nex-gddp-cmip6.s3-us-west-2.amazonaws.com/NEX-GDDP-CMIP6/"
LAT0, LON0, RES = -59.875, 0.125, 0.25
FILL = 1e19
DPM_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def url(model, exp, member, grid, var, year):
    v = "" if grid is None else grid
    return f"{BUCKET}{model}/{exp}/{member}/{var}/{var}_day_{model}_{exp}_{member}_{grid}_{year}.nc"


def box_index(lat_min, lat_max, lon_min, lon_max):
    """Row and column slices of the NEX grid for a box (lon in 0..360)."""
    i0 = int(round((lat_min - LAT0) / RES - 0.5 + 1e-6)); i1 = int(round((lat_max - LAT0) / RES - 0.5 + 1e-6))
    j0 = int(round((lon_min - LON0) / RES - 0.5 + 1e-6)); j1 = int(round((lon_max - LON0) / RES - 0.5 + 1e-6))
    return slice(i0 + 1, i1 + 1), slice(j0 + 1, j1 + 1)


def read_year(u, var, rows, cols, block_mb=8):
    """(days, ny, nx) float32 over the box in the variable's native unit; fill -> NaN."""
    import fsspec, h5py
    with fsspec.open(u, block_size=block_mb << 20).open() as f, h5py.File(f, "r") as h:
        d = h[var]
        out = np.empty((d.shape[0], rows.stop - rows.start, cols.stop - cols.start), "float32")
        for k in range(d.shape[0]):
            out[k] = d[k, rows, cols]
    out[out > FILL] = np.nan
    return out


def to_units(a, var):
    if var in ("tasmax", "tasmin"):
        return a - 273.15
    if var == "pr":
        return a * 86400.0
    return a


def monthly_from_daily(a):
    """(365 or 366 days, ...) -> (12, ...) means; leap day dropped from February's end like a 365 calendar."""
    a = a[:365] if a.shape[0] == 366 else a
    edges = np.concatenate([[0], np.cumsum(DPM_DAYS)])
    return np.stack([a[edges[k]:edges[k + 1]].mean(0) for k in range(12)])
