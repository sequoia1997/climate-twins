"""Global predictor stack for the species pilot (workstream W1): grid, tile files, predictors, change factors, loaders.

Grid: TerraClimate native 1/24 degree (2.5 arc-minute), 4320 rows x 8640 columns, row 0 = north (cell centre lat
89.979166 - i/24, lon -179.979166 + j/24), see `climategrid`. The globe is cut into 4 x 4 = 16 TILES of 1080 x 2160 cells
(45 degrees of latitude x 90 degrees of longitude), named "r<row>c<col>", row 0 = 90N-45N, column 0 = 180W-90W. A tile job
reads TerraClimate with HTTP range requests and never holds more than a few GB.

Files (all numpy .npz, compressed; land cells only, stored in row-major order of the tile):
  pred_<product>_<tile>.npz   data (10, n_land) float32 in NAMES order, land_packed (bit-packed (1080, 2160) mask), tile (2,)
  basem_<tile>.npz            baseline monthly climatology (12, n_land) for tmax, tmin, ppt, pet, def, aet, soil, stored as
                              int16/uint16 with the scales in `MONTHLY`; the input to `apply_deltas`
  deltas_<model>.npz          coarse (0.25 degree) change factors of one climate model, see `Deltas`
  landmask.npz, manifest.json global land mask and the inventory (see ctw/species/climstack_run.py)
Products: base_1991-2020, hind_1966-1985, hind_2005-2024, fut_<ssp245|ssp585>_<2041-2060|2081-2100>_ensmedian.

Predictors (float32; see UNITS): the contract names are NAMES. cwd and aet are TerraClimate's own annual `def` and `aet`
(sum of the 12 monthly climatology values) for the three observed windows; for futures they are the baseline plus the change in
our own water balance (climategrid.future_predictors).
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field

import numpy as np

from . import climategrid as G

NAMES = ("bio1", "bio4", "bio5", "bio6", "bio12", "bio15", "bio17", "gdd", "cwd", "aet")
UNITS = {
    "bio1": "deg C, annual mean of monthly (tmax+tmin)/2",
    "bio4": "deg C x 100, temperature seasonality (SD of the 12 monthly means x 100, WorldClim convention)",
    "bio5": "deg C, mean daily maximum temperature of the warmest month",
    "bio6": "deg C, mean daily minimum temperature of the coldest month",
    "bio12": "mm per year, annual precipitation",
    "bio15": "percent, precipitation seasonality (coefficient of variation of the 12 monthly totals; 0 where annual precipitation is 0)",
    "bio17": "mm, precipitation of the driest quarter (3 consecutive months, wrapping the year)",
    "gdd": "deg C days per year above 5 C (climategrid.gdd: sine method on a daily curve, calibrated on NEX-GDDP daily data)",
    "cwd": "mm per year, climatic water deficit = TerraClimate def (annual sum of the monthly climatology)",
    "aet": "mm per year, actual evapotranspiration = TerraClimate aet (annual sum of the monthly climatology)",
}
SCEN = ("ssp245", "ssp585")
PERIODS = ("2041-2060", "2081-2100")
WINDOWS = {"base_1991-2020": (1991, 2020), "hind_1966-1985": (1966, 1985), "hind_2005-2024": (2005, 2024)}
PRED_VARS = ("tmax", "tmin", "ppt", "def", "aet")           # TerraClimate variables the predictors need
MONTHLY = {                                               # variable -> (scale, dtype) of the stored baseline monthly climatology
    "tmax": (0.01, "int16"), "tmin": (0.01, "int16"), "ppt": (0.1, "uint16"), "pet": (0.1, "uint16"),
    "def": (0.1, "uint16"), "aet": (0.1, "uint16"), "soil": (0.1, "uint16"),
}
PPT_RATIO = (0.2, 5.0)                                    # limits on fine-grid precipitation change ratios (config.toml [matching] ppt_ratio)
TH, TW = 1080, 2160
NTR, NTC = G.NLAT // TH, G.NLON // TW
PRIORITY_TILES = ("r0c0", "r0c1", "r0c2", "r1c0", "r1c1", "r1c2")      # lat 0-90N, lon 180W-90E: North America and Europe
ALL_TILES = tuple(f"r{r}c{c}" for r in range(NTR) for c in range(NTC))
REST_TILES = tuple(t for t in ALL_TILES if t not in PRIORITY_TILES)


def future_products():
    return [f"fut_{s}_{p}_ensmedian" for s in SCEN for p in PERIODS]


# --------------------------------------------------------------------------- tiles and masks
def parse_tile(t):
    return int(t[1]), int(t[3])


def tile_window(t):
    r, c = parse_tile(t) if isinstance(t, str) else t
    return slice(r * TH, (r + 1) * TH), slice(c * TW, (c + 1) * TW)


def pack_mask(m):
    return np.packbits(np.asarray(m, bool).ravel())


def unpack_mask(p, shape=(TH, TW)):
    return np.unpackbits(p)[: shape[0] * shape[1]].astype(bool).reshape(shape)


def land_index(land, tile):
    """(row, col) global indices of the land cells of a tile mask, row-major."""
    rows, cols = tile_window(tile)
    i, j = np.nonzero(land)
    return i + rows.start, j + cols.start


# --------------------------------------------------------------------------- predictors
def predict(m, block=20000):
    """The 10 predictors from monthly climatologies of land cells: m has tmax, tmin, ppt, def, aet as (12, n). -> (10, n) float32."""
    n = m["tmax"].shape[1]
    out = np.full((len(NAMES), n), np.nan, "float32")
    for a in range(0, n, block):
        sl = slice(a, min(a + block, n))
        b = G.bioclim(m["tmax"][:, sl], m["tmin"][:, sl], m["ppt"][:, sl])
        b["gdd"] = G.gdd(m["tmax"][:, sl], m["tmin"][:, sl])
        b["cwd"] = np.asarray(m["def"][:, sl], "float64").sum(0)
        b["aet"] = np.asarray(m["aet"][:, sl], "float64").sum(0)
        fin = np.isfinite(m["ppt"][:, sl]).all(0)
        b["bio15"] = np.where(fin & ~np.isfinite(b["bio15"]), 0.0, b["bio15"])      # no precipitation at all -> 0
        for k, nm in enumerate(NAMES):
            out[k, sl] = b[nm]
    return out


def predict_future(base, fut_tx, fut_tn, fut_ppt, lat, block=20000):
    """Future predictors (10, n) float32. base: dict of arrays (12, n) tmax, tmin, ppt, pet, def, aet, soil; fut_*: (12, n)
    projected monthly climate; lat (n,). cwd and aet = baseline TerraClimate + change in our own water balance (see
    climategrid.future_predictors); PET is carried by the Hargreaves future/baseline ratio."""
    n = fut_tx.shape[1]
    out = np.full((len(NAMES), n), np.nan, "float32")
    lat = np.asarray(lat, "float64")
    for a in range(0, n, block):
        sl = slice(a, min(a + block, n))
        bs = {k: np.asarray(v[:, sl], "float64") for k, v in base.items()}
        ft, fn, fp = (np.asarray(x[:, sl], "float64") for x in (fut_tx, fut_tn, fut_ppt))
        P = G.future_predictors(bs, ft, fn, fp, lat[sl])
        P["gdd"] = P.pop("gdd5")
        fin = np.isfinite(fp).all(0)
        P["bio15"] = np.where(fin & ~np.isfinite(P["bio15"]), 0.0, P["bio15"])
        for k, nm in enumerate(NAMES):
            out[k, sl] = P[nm]
    return out


# --------------------------------------------------------------------------- tile files
def save_pred(path, tile, land, data, product):
    np.savez_compressed(path, data=np.asarray(data, "float32"), land_packed=pack_mask(land), tile=np.array(parse_tile(tile)),
                        names=np.array(NAMES), product=np.array(product))


def load_pred(path):
    """-> dict(data (10, n) float32, land (TH, TW) bool, tile (r, c), names, product)."""
    z = np.load(path, allow_pickle=False)
    return {"data": z["data"], "land": unpack_mask(z["land_packed"]), "tile": tuple(int(x) for x in z["tile"]),
            "names": [str(x) for x in z["names"]], "product": str(z["product"])}


def tile_to_grid(p):
    """Full (10, TH, TW) float32 grid of a loaded tile with NaN on sea."""
    g = np.full((p["data"].shape[0],) + p["land"].shape, np.nan, "float32")
    g[:, p["land"]] = p["data"]
    return g


def _reserved(dt):
    return np.iinfo(dt).min if dt == "int16" else np.iinfo(dt).max


def save_basem(path, tile, land, monthly):
    """monthly: dict var -> (12, n) float arrays; stored as scaled integers (NaN -> the dtype's reserved value)."""
    out = {}
    for v, (sc, dt) in MONTHLY.items():
        x = np.asarray(monthly[v], "float64")
        res = _reserved(dt)
        lo, hi = (np.iinfo(dt).min + 1, np.iinfo(dt).max) if dt == "int16" else (0, np.iinfo(dt).max - 1)
        q = np.clip(np.round(np.where(np.isfinite(x), x / sc, 0)), lo, hi).astype(dt)
        q[~np.isfinite(x)] = res
        out[v] = q
    np.savez_compressed(path, land_packed=pack_mask(land), tile=np.array(parse_tile(tile)),
                        scales=np.array(json.dumps({v: s for v, (s, d) in MONTHLY.items()})), **out)


def load_basem(path):
    z = np.load(path, allow_pickle=False)
    land = unpack_mask(z["land_packed"])
    tile = tuple(int(x) for x in z["tile"])
    monthly = {}
    for v, (sc, dt) in MONTHLY.items():
        q = z[v]
        monthly[v] = np.where(q == _reserved(dt), np.nan, q.astype("float32") * np.float32(sc)).astype("float32")
    return land, tile, monthly


@dataclass
class BaselineStack:
    """Baseline monthly climatology on land cells (any selection of cells): monthly[v] is (12, n) float32 for tmax, tmin, ppt, pet,
    def, aet, soil; lat, lon (n,) cell centres; row, col (n,) global grid indices (to put results back on the grid)."""
    monthly: dict
    lat: np.ndarray
    lon: np.ndarray
    row: np.ndarray = None
    col: np.ndarray = None

    @property
    def n(self):
        return self.lat.shape[0]

    def subset(self, sel):
        return BaselineStack({k: v[:, sel] for k, v in self.monthly.items()}, self.lat[sel], self.lon[sel],
                             None if self.row is None else self.row[sel], None if self.col is None else self.col[sel])


def load_baseline(root, tiles=None, bbox=None):
    """BaselineStack from basem_<tile>.npz files in directory `root`; bbox = (lat_min, lat_max, lon_min, lon_max) keeps only
    cells in the box (tiles that do not overlap it are not read)."""
    tiles = tiles or ALL_TILES
    parts = []
    if bbox is not None:
        rs, cs = G.window(*bbox)
    for t in tiles:
        tr, tc = tile_window(t)
        if bbox is not None and (tr.stop <= rs.start or tr.start >= rs.stop or tc.stop <= cs.start or tc.start >= cs.stop):
            continue
        f = os.path.join(root, f"basem_{t}.npz")
        if not os.path.exists(f):
            continue
        land, _, mon = load_basem(f)
        i, j = land_index(land, t)
        st = BaselineStack(mon, G.cell_lat(i).astype("float64"), G.cell_lon(j).astype("float64"), i, j)
        if bbox is not None:
            st = st.subset((i >= rs.start) & (i < rs.stop) & (j >= cs.start) & (j < cs.stop))
        parts.append(st)
    if not parts:
        raise FileNotFoundError(f"no basem_<tile>.npz in {root} for the requested tiles/box")
    return BaselineStack({k: np.concatenate([p.monthly[k] for p in parts], axis=1) for k in parts[0].monthly},
                         np.concatenate([p.lat for p in parts]), np.concatenate([p.lon for p in parts]),
                         np.concatenate([p.row for p in parts]), np.concatenate([p.col for p in parts]))


def read_box(root, product, bbox):
    """Predictor grids of a product over a lat/lon box from pred_<product>_<tile>.npz files in `root`:
    returns (dict name -> (ny, nx) float32 with NaN on sea, lat (ny,), lon (nx,)). Only overlapping tiles are read."""
    rs, cs = G.window(*bbox)
    ny, nx = rs.stop - rs.start, cs.stop - cs.start
    out = np.full((len(NAMES), ny, nx), np.nan, "float32")
    for t in ALL_TILES:
        tr, tc = tile_window(t)
        a0, a1, b0, b1 = max(tr.start, rs.start), min(tr.stop, rs.stop), max(tc.start, cs.start), min(tc.stop, cs.stop)
        if a0 >= a1 or b0 >= b1:
            continue
        g = tile_to_grid(load_pred(os.path.join(root, f"pred_{product}_{t}.npz")))
        out[:, a0 - rs.start:a1 - rs.start, b0 - cs.start:b1 - cs.start] = g[:, a0 - tr.start:a1 - tr.start, b0 - tc.start:b1 - tc.start]
    return ({n: out[k] for k, n in enumerate(NAMES)}, G.cell_lat(np.arange(rs.start, rs.stop)), G.cell_lon(np.arange(cs.start, cs.stop)))


def point_cells(lat, lon):
    """(row, col) of the native cell containing each point."""
    lat, lon = np.atleast_1d(lat).astype(float), np.atleast_1d(lon).astype(float)
    i = np.clip(np.floor((G.LAT0 + G.RES / 2 - lat) / G.RES).astype(int), 0, G.NLAT - 1)
    j = np.clip(np.floor((((lon + 180) % 360) - 180 - (G.LON0 - G.RES / 2)) / G.RES).astype(int), 0, G.NLON - 1)
    return i, j


def sample_points(root, product, lat, lon):
    """Predictor values (10, n_points) at points (the 2.5' cell containing the point; NaN if sea). Reads only the tiles needed."""
    i, j = point_cells(lat, lon)
    out = np.full((len(NAMES), len(i)), np.nan, "float32")
    for t in sorted(set(zip((i // TH).tolist(), (j // TW).tolist()))):
        sel = (i // TH == t[0]) & (j // TW == t[1])
        g = tile_to_grid(load_pred(os.path.join(root, f"pred_{product}_r{t[0]}c{t[1]}.npz")))
        out[:, sel] = g[:, i[sel] - t[0] * TH, j[sel] - t[1] * TW]
    return out


# --------------------------------------------------------------------------- coarse change factors
class PointInterp:
    """Bilinear interpolation of coarse global fields (..., ny, nx) at arbitrary points. lat_c ascending or descending, lon_c
    ascending and equally spaced on a periodic globe (longitudes wrap, any input longitude convention); latitude is clamped."""

    def __init__(self, lat_c, lon_c, lat, lon):
        lat_c = np.asarray(lat_c, "float64"); lon_c = np.asarray(lon_c, "float64")
        self.flip = bool(lat_c[0] > lat_c[-1])
        if self.flip:
            lat_c = lat_c[::-1]
        ny, nx = len(lat_c), len(lon_c)
        fy = np.clip((np.asarray(lat, "float64") - lat_c[0]) / (lat_c[1] - lat_c[0]), 0, ny - 1 - 1e-9)
        self.y0 = np.floor(fy).astype(int); self.wy = (fy - self.y0).astype("float32")
        fx = ((np.asarray(lon, "float64") - lon_c[0]) / (lon_c[1] - lon_c[0])) % nx
        self.x0 = np.floor(fx).astype(int) % nx; self.x1 = (self.x0 + 1) % nx; self.wx = (fx - np.floor(fx)).astype("float32")

    def __call__(self, f):
        f = np.asarray(f, "float32")
        if self.flip:
            f = f[..., ::-1, :]
        a = f[..., self.y0, self.x0] * (1 - self.wx) + f[..., self.y0, self.x1] * self.wx
        b = f[..., self.y0 + 1, self.x0] * (1 - self.wx) + f[..., self.y0 + 1, self.x1] * self.wx
        return (a * (1 - self.wy) + b * self.wy).astype("float32")


@dataclass
class Deltas:
    """Coarse monthly change factors of ONE climate model (or the ensemble median) on the NEX-GDDP 0.25 degree grid
    (600 rows, lat -59.875 .. 89.875, x 1440 columns, lon 0.125 .. 359.875), relative to that model's own 1991-2020:
      dtx, dtn   deg C added to the monthly mean daily max / min temperature
      rp         ratio (future / baseline) of monthly precipitation (1 where the model baseline month is under 0.05 mm/day)
    arrays have shape (len(scenarios), len(periods), 12, 600, 1440) (stored float16) and no NaN (ocean is filled with the nearest
    land value)."""
    model: str
    scenarios: tuple
    periods: tuple
    dtx: np.ndarray
    dtn: np.ndarray
    rp: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    meta: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path):
        z = np.load(path, allow_pickle=False)
        return cls(str(z["model"]), tuple(str(x) for x in z["scenarios"]), tuple(str(x) for x in z["periods"]), z["dtx"], z["dtn"], z["rp"],
                   z["lat"], z["lon"], json.loads(str(z["meta"])) if "meta" in z.files else {})

    def save(self, path):
        np.savez_compressed(path, model=np.array(self.model), scenarios=np.array(self.scenarios), periods=np.array(self.periods),
                            dtx=self.dtx.astype("float16"), dtn=self.dtn.astype("float16"), rp=self.rp.astype("float16"),
                            lat=self.lat.astype("float32"), lon=self.lon.astype("float32"), meta=np.array(json.dumps(self.meta)))

    def get(self, scenario, period):
        s, p = self.scenarios.index(scenario), self.periods.index(period)
        return self.dtx[s, p], self.dtn[s, p], self.rp[s, p]


def ensemble_median(items, name="ensemble_median"):
    """Median over models, per cell and month, of the change factors (temperature deltas and precipitation ratios).
    This is the fine-grid climate under the median CHANGE, not the median of per-model fine grids."""
    d0 = items[0]
    out = {}
    for a in ("dtx", "dtn", "rp"):
        shp = getattr(d0, a).shape
        r = np.empty(shp, "float32")
        for s in range(shp[0]):
            for p in range(shp[1]):                              # one scenario/period at a time keeps memory near 1 GB
                r[s, p] = np.median(np.stack([getattr(d, a)[s, p].astype("float32") for d in items]), axis=0)
        out[a] = r
    return Deltas(name, d0.scenarios, d0.periods, out["dtx"], out["dtn"], out["rp"], d0.lat, d0.lon, {"models": [d.model for d in items]})


class DeltaLibrary:
    """Directory of deltas_<model>.npz files, loaded lazily (one model is kept in memory at a time)."""

    def __init__(self, root):
        self.root = root
        self._cache = {}

    def models(self):
        return sorted(f[7:-4] for f in os.listdir(self.root) if f.startswith("deltas_") and f.endswith(".npz"))

    def get_model(self, model):
        if model not in self._cache:
            self._cache = {model: Deltas.load(os.path.join(self.root, f"deltas_{model}.npz"))}
        return self._cache[model]


def apply_deltas(baseline_stack, deltas, model, scenario, period, ppt_ratio=PPT_RATIO, interp=None):
    """Fine-grid predictors for ONE climate model, scenario and period, computed on demand (nothing per model is stored).

    baseline_stack  BaselineStack (load_baseline) with the 2.5' baseline monthly climatology of the cells wanted
    deltas          a Deltas, a DeltaLibrary, or a dict {model: Deltas}; `model` selects the entry ("ensemble_median" = the median)
    scenario, period  e.g. "ssp245", "2041-2060"
    interp          optional PointInterp for these cells (reuse it for several calls on the same stack)
    Each coarse monthly change is bilinearly interpolated to the cell and added to tmax and tmin (deg C) or multiplied with ppt
    (ratio clipped to ppt_ratio); the predictors are then recomputed (predict_future). Returns dict name -> (n,) float32 (NAMES)."""
    if isinstance(deltas, Deltas):
        d = deltas
    elif isinstance(deltas, DeltaLibrary):
        d = deltas.get_model(model)
    else:
        d = deltas[model]
    dtx, dtn, rp = d.get(scenario, period)
    st = baseline_stack
    it = interp or PointInterp(d.lat, d.lon, st.lat, st.lon)
    m = st.monthly
    fx, fn = m["tmax"] + it(dtx), m["tmin"] + it(dtn)
    fp = m["ppt"] * np.clip(it(rp), *ppt_ratio)
    out = predict_future(m, fx, fn, fp, st.lat)
    return {nm: out[k] for k, nm in enumerate(NAMES)}
