"""Climate predictor stack for species modelling (Spike B, Tier A).

Grid: the TerraClimate native grid, 1/24 degree = 2.5 arc-minutes (4320 x 8640 global, rows north to south, cell centres
at lat 89.979166 - 1/24*i, lon -179.979166 + 1/24*j). Tier A therefore needs no resampling of the baseline at all.

Monthly inputs are arrays with the month on axis 0: (12, ...) for tmax, tmin (deg C), ppt, pet, aet, def, soil (mm).
Everything here is pure numpy so it can be applied to a tile of any shape; global runs go through `by_tiles`.

Predictors (names used in the output):
  bio1  annual mean temperature (deg C), mean of monthly (tmax+tmin)/2
  bio4  temperature seasonality, standard deviation of the 12 monthly means x 100 (WorldClim convention)
  bio5  max temperature of the warmest month (monthly mean tmax), bio6 min temperature of the coldest month (monthly mean tmin)
  bio12 annual precipitation (mm), bio15 precipitation seasonality (coefficient of variation of monthly ppt, %)
  bio17 precipitation of the driest quarter (mm; wrapped 3-month windows)
  gdd5  growing degree days above 5 C (deg C days), daily curve from the monthly means (see `gdd`)
  fd    frost days (days per year with tmin < 0 C), from monthly tmin with a normal daily spread (see `frost_days`)
  cwd   climatic water deficit (mm/yr) and aet actual evapotranspiration (mm/yr), TerraClimate def and aet at baseline
"""
from __future__ import annotations
import numpy as np
from scipy import ndimage
from scipy.interpolate import CubicSpline
from scipy.special import ndtr

DPM = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], "float64")
DAY_MID = np.cumsum(DPM) - DPM / 2                     # day of year at mid month (0..365)
NDAY = 365
RES = 1 / 24
NLAT, NLON = 4320, 8640
LAT0, LON0 = 89.979166667, -179.979166667             # centre of cell (0, 0)
PREDICTORS = ("bio1", "bio4", "bio5", "bio6", "bio12", "bio15", "bio17", "gdd5", "fd", "cwd", "aet")


# --------------------------------------------------------------------------- grid helpers
def cell_lat(i):
    return LAT0 - RES * np.asarray(i)


def cell_lon(j):
    return LON0 + RES * np.asarray(j)


def window(lat_min, lat_max, lon_min, lon_max):
    """Row and column slices of the native grid covering a lat/lon box."""
    i0 = int(np.floor((LAT0 + RES / 2 - lat_max) / RES + 1e-6)); i1 = int(np.ceil((LAT0 + RES / 2 - lat_min) / RES - 1e-6))
    j0 = int(np.floor((lon_min - (LON0 - RES / 2)) / RES + 1e-6)); j1 = int(np.ceil((lon_max - (LON0 - RES / 2)) / RES - 1e-6))
    return slice(max(i0, 0), min(i1, NLAT)), slice(max(j0, 0), min(j1, NLON))


def cell_area_km2(lat):
    """Area of a 1/24 degree cell (km2) at the given latitude (WGS84 sphere of radius 6371.0088 km)."""
    r = 6371.0088
    return (r * np.radians(RES)) ** 2 * np.cos(np.radians(lat))


def global_cell_stats(land_rows):
    """land_rows: (NLAT,) number of land cells in each row. Returns total cells, area km2."""
    lat = cell_lat(np.arange(NLAT))
    return int(np.sum(land_rows)), float(np.sum(land_rows * cell_area_km2(lat)))


# --------------------------------------------------------------------------- bioclim-style variables
def tmean(tmax, tmin):
    return (np.asarray(tmax, "float64") + np.asarray(tmin, "float64")) / 2


def _quarter_sums(x):
    """(12, ...) -> (12, ...) sum of month m, m+1, m+2 (wrapping the year)."""
    return x + np.roll(x, -1, axis=0) + np.roll(x, -2, axis=0)


def bioclim(tmax, tmin, ppt) -> dict:
    """Seven bioclim variables from monthly climatologies (12, ...). Quarter variables use calendar-wrapped 3-month windows
    (WorldClim uses the same definition, weighting months equally)."""
    tx, tn, p = (np.asarray(a, "float64") for a in (tmax, tmin, ppt))
    tm = (tx + tn) / 2
    pm = p.mean(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        cv = np.where(pm > 0, p.std(0, ddof=1) / pm * 100, np.nan)       # WorldClim bio15: CV of the 12 monthly totals (+1 mm floor not used)
    return {
        "bio1": tm.mean(0),
        "bio4": tm.std(0, ddof=1) * 100,
        "bio5": tx.max(0),
        "bio6": tn.min(0),
        "bio12": p.sum(0),
        "bio15": cv,
        "bio17": _quarter_sums(p).min(0),
    }


# --------------------------------------------------------------------------- daily curves, degree days, frost
def monthly_to_daily(m):
    """Monthly means (12, ...) -> daily values (365, ...) by a periodic cubic spline through the mid-month points.
    Smooth annual cycle; the annual mean is preserved to within about 0.1 C for temperature."""
    m = np.asarray(m, "float64")
    x = np.concatenate([[DAY_MID[-1] - NDAY], DAY_MID, [DAY_MID[0] + NDAY]])
    y = np.concatenate([m[-1:], m, m[:1]])
    cs = CubicSpline(x, y, axis=0)
    d = np.arange(NDAY) + 0.5
    out = cs(d)
    # rescale each month so its mean equals the input monthly mean (keeps degree-day sums consistent with the input)
    mon = np.minimum(np.searchsorted(np.cumsum(DPM), d, side="right"), 11)
    for k in range(12):
        sel = mon == k
        out[sel] += m[k] - out[sel].mean(0)
    return out


def _sine_dd(tx, tn, base):
    """Single-sine degree days above `base` for one day (Baskerville & Emin 1969), arrays of equal shape."""
    tx = np.maximum(tx, tn)
    M, W = (tx + tn) / 2, (tx - tn) / 2
    with np.errstate(invalid="ignore", divide="ignore"):
        th = np.arcsin(np.clip((base - M) / np.where(W > 0, W, 1), -1, 1))
        part = (1 / np.pi) * ((M - base) * (np.pi / 2 - th) + W * np.cos(th))
    return np.where(tn >= base, M - base, np.where(tx <= base, 0.0, part))


def gdd(tmax, tmin, base=5.0) -> np.ndarray:
    """Growing degree days (deg C days per year) above `base` (default 5 C, the usual choice for plants and the
    ClimateNA/ClimateEU DD5). Method: daily tmax and tmin curves from the monthly means (`monthly_to_daily`), then the
    single-sine within-day method. It cannot see day-to-day weather, so it is slightly low where the threshold is crossed
    in the shoulder seasons; the error against NEX-GDDP daily data is reported in docs/spikes/B-climate-stack.md."""
    dx, dn = monthly_to_daily(tmax), monthly_to_daily(tmin)
    return _sine_dd(dx, dn, base).sum(0)


def frost_sigma(tmax=None, tmin=None, a=2.6, b=0.0):
    """Standard deviation (deg C) of daily tmin about the climatological monthly mean tmin, used by `frost_days`.
    Default is a constant; `b` lets it grow with the diurnal range (tmax - tmin) when supplied."""
    if tmax is None or b == 0:
        return a
    return a + b * (np.asarray(tmax, "float64") - np.asarray(tmin, "float64"))


def frost_days(tmin, sigma=3.0, tmax=None) -> np.ndarray:
    """Frost-day proxy: days per year with tmin < 0 C. In each month the daily minimum is taken as normal with mean = the
    monthly mean tmin and SD `sigma`; frost days = sum_m days_m * P(T < 0). `sigma` is a scalar or an array broadcastable
    with tmin. It is calibrated against NEX-GDDP daily data (see the spike document) and its error is reported there."""
    tn = np.asarray(tmin, "float64")
    s = np.maximum(np.asarray(sigma, "float64"), 0.3)
    p = ndtr((0.0 - tn) / s)
    return (p * DPM.reshape(-1, *([1] * (tn.ndim - 1)))).sum(0)


# --------------------------------------------------------------------------- water balance
def water_balance(ppt, pet, tmean_, cap, melt_dd=3.0, spin=3):
    """Monthly Thornthwaite-Mather bucket with a simple snow store, run to a repeating year.
    ppt, pet, tmean_ (12, ...) in mm and deg C; cap (...) soil water capacity (mm). Returns dict aet, cwd, soil (12, ...).
    Snowfall fraction falls linearly from 1 at -2 C to 0 at +2 C; melt = melt_dd mm per deg C per day above 0 C.
    Soil water follows Thornthwaite & Mather (1957): when PET exceeds the water input the store is drained
    exponentially, which is also how TerraClimate (Abatzoglou et al. 2018) computes def/aet, with its own snow module.
    Used for the future: cwd_future = cwd_TerraClimate + (cwd_model(future) - cwd_model(baseline)) so the model's own bias cancels."""
    p, e, t = (np.asarray(a, "float64") for a in (ppt, pet, tmean_))
    cap = np.maximum(np.asarray(cap, "float64"), 1.0)
    dpm = DPM.reshape(-1, *([1] * (p.ndim - 1)))
    fs = np.clip((2.0 - t) / 4.0, 0, 1)
    snowfall, rain = p * fs, p * (1 - fs)
    swe = np.zeros_like(cap); soil = cap.copy()
    aet = np.zeros_like(p); soil_m = np.zeros_like(p)
    for cyc in range(spin):
        for m in range(12):
            avail = swe + snowfall[m]
            melt = np.minimum(avail, melt_dd * np.maximum(t[m], 0) * dpm[m])
            swe = avail - melt
            w = rain[m] + melt
            wet = w >= e[m]
            soil_wet = np.minimum(cap, soil + (w - e[m]))
            soil_dry = soil * np.exp(-(e[m] - w) / cap)
            new = np.where(wet, soil_wet, soil_dry)
            aet[m] = np.where(wet, e[m], w + (soil - new))
            soil = new
            soil_m[m] = soil
    return {"aet": aet, "cwd": np.maximum(e - aet, 0), "soil": soil_m}


def cap_from_soil(soil_months):
    """Soil water capacity proxy (mm) from TerraClimate's monthly soil moisture climatology: its largest monthly value,
    floored at 20 mm (TerraClimate gives no capacity layer)."""
    return np.maximum(np.nanmax(np.asarray(soil_months, "float64"), axis=0), 20.0)


def hargreaves_ratio(tmax_f, tmin_f, tmax_b, tmin_b, lat):
    """Projected / baseline Hargreaves-Samani PET (12, ...) per month, used to carry TerraClimate's Penman-Monteith PET
    into the future (the repo's own convention, [matching] pet_ratio = [0.5, 3.0])."""
    lat = np.broadcast_to(np.asarray(lat, "float64"), np.asarray(tmax_b).shape[1:])
    shp = np.asarray(tmax_b).shape
    f = lambda tx, tn: _hargreaves(np.asarray(tx, "float64").reshape(12, -1), np.asarray(tn, "float64").reshape(12, -1), lat.reshape(-1)).reshape(shp)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.clip(np.where(f(tmax_b, tmin_b) > 0, f(tmax_f, tmin_f) / f(tmax_b, tmin_b), 1.0), 0.5, 3.0)


def _hargreaves(tx, tn, lat):
    from ..common import hargreaves_pet
    return hargreaves_pet(tx, tn, lat)


# --------------------------------------------------------------------------- change factors on the fine grid
def fill_nearest(a):
    """Fill NaN in a 2-D array with the value of the nearest finite cell (coastal cells where a coarse model has no land)."""
    bad = ~np.isfinite(a)
    if not bad.any() or bad.all():
        return a
    idx = ndimage.distance_transform_edt(bad, return_distances=False, return_indices=True)
    return a[tuple(idx)]


def regrid_bilinear(coarse, lat_c, lon_c, lat_f, lon_f, wrap=True):
    """Bilinear interpolation of a coarse field (..., ny, nx) onto the fine lat/lon vectors. lat_c descending or ascending,
    lon_c ascending; NaN in the coarse field is first filled by the nearest valid cell. With wrap=True (a global field)
    longitudes wrap around; with wrap=False (a regional subset) they are clamped at the edge."""
    lat_c = np.asarray(lat_c, "float64"); lon_c = np.asarray(lon_c, "float64")
    lead = coarse.shape[:-2]
    c = coarse.reshape(-1, *coarse.shape[-2:]).astype("float64")
    if lat_c[0] > lat_c[-1]:
        lat_c = lat_c[::-1]; c = c[:, ::-1]
    res = lon_c[1] - lon_c[0]
    fy = np.clip((np.asarray(lat_f, "float64") - lat_c[0]) / (lat_c[1] - lat_c[0]), 0, len(lat_c) - 1 - 1e-9)
    fx = (np.asarray(lon_f, "float64") - lon_c[0]) / res
    fx = fx % len(lon_c) if wrap else np.clip(fx, 0, len(lon_c) - 1 - 1e-9)
    y0 = np.floor(fy).astype(int); wy = (fy - y0)[:, None]
    x0 = np.floor(fx).astype(int); x1 = (x0 + 1) % len(lon_c) if wrap else np.minimum(x0 + 1, len(lon_c) - 1); wx = (fx - x0)[None, :]
    out = np.empty((c.shape[0], len(lat_f), len(lon_f)), "float32")
    for k in range(c.shape[0]):
        g = fill_nearest(c[k])
        a = g[y0][:, x0] * (1 - wx) + g[y0][:, x1] * wx
        b = g[y0 + 1][:, x0] * (1 - wx) + g[y0 + 1][:, x1] * wx
        out[k] = a * (1 - wy) + b * wy
    return out.reshape(*lead, len(lat_f), len(lon_f))


def coarse_changes(tx_b, tx_f, tn_b, tn_f, p_b, p_f, dry_mm=0.5, ratio=(0.2, 5.0)):
    """Monthly change factors on the model grid from baseline and future monthly means (12, ny, nx):
    dtx, dtn (deg C, additive) and lrp = log precipitation ratio (clipped to `ratio`; 0 where the baseline month is drier than
    dry_mm per day-equivalent, i.e. no change). The same conventions as ctw.downdeltas.make_delta, in log space so that
    interpolation stays a geometric (ratio) mean."""
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(p_b > dry_mm, p_f / p_b, 1.0)
    r = np.clip(np.where(np.isfinite(r), r, 1.0), *ratio)
    return tx_f - tx_b, tn_f - tn_b, np.log(r)


def apply_changes(base_tx, base_tn, base_ppt, dtx, dtn, lrp, ratio=(0.2, 5.0)):
    """Fine-grid future monthly climate from fine baseline (12, ny, nx) and interpolated changes of the same shape."""
    return base_tx + dtx, base_tn + dtn, base_ppt * np.clip(np.exp(lrp), *ratio)


def future_predictors(base, fut_tx, fut_tn, fut_ppt, lat):
    """Predictor dict for a projected climate. `base` holds the baseline monthly 'tmax','tmin','ppt','pet','def','aet','soil'
    (12, ...). PET is scaled by the Hargreaves ratio, the water balance is rerun for baseline and future with the same
    capacity, and cwd/aet are baseline TerraClimate values plus the modelled difference."""
    out = predictors(fut_tx, fut_tn, fut_ppt)
    ratio = hargreaves_ratio(fut_tx, fut_tn, base["tmax"], base["tmin"], lat)
    pet_f = base["pet"] * ratio
    cap = cap_from_soil(base["soil"])
    wb_b = water_balance(base["ppt"], base["pet"], tmean(base["tmax"], base["tmin"]), cap)
    wb_f = water_balance(fut_ppt, pet_f, tmean(fut_tx, fut_tn), cap)
    out["cwd"] = np.maximum(base["def"].sum(0) + (wb_f["cwd"].sum(0) - wb_b["cwd"].sum(0)), 0)
    out["aet"] = np.maximum(base["aet"].sum(0) + (wb_f["aet"].sum(0) - wb_b["aet"].sum(0)), 0)
    return out


def predictors(tmax, tmin, ppt, sigma=3.0, base_t=5.0) -> dict:
    """The climate predictors that need only tmax, tmin, ppt (everything except cwd and aet)."""
    out = bioclim(tmax, tmin, ppt)
    out["gdd5"] = gdd(tmax, tmin, base_t)
    out["fd"] = frost_days(tmin, sigma)
    return out


def baseline_predictors(m: dict, sigma=3.0) -> dict:
    """Baseline predictors from TerraClimate monthly climatologies m with keys tmax, tmin, ppt, def, aet."""
    out = predictors(m["tmax"], m["tmin"], m["ppt"], sigma)
    out["cwd"] = np.asarray(m["def"], "float64").sum(0)
    out["aet"] = np.asarray(m["aet"], "float64").sum(0)
    return out


# --------------------------------------------------------------------------- tiling
def by_tiles(shape, tile=512):
    """Yield (row slice, col slice) tiles covering a 2-D grid."""
    for i in range(0, shape[0], tile):
        for j in range(0, shape[1], tile):
            yield slice(i, min(i + tile, shape[0])), slice(j, min(j + tile, shape[1]))
