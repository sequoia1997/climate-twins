"""Grid geometry and the data interfaces of the species pilot pipeline (W3).

The pilot grid is TerraClimate's native 1/24 degree grid: 4320 rows x 8640 columns, row 0 is the northernmost row, column 0 the
westernmost; cell centres at lat = 90 - (row + 0.5) * 180 / H and lon = -180 + (col + 0.5) * 360 / W. Everything here works for any
H x W so tests run on small grids.

Interfaces (other workstreams provide the real implementations; tests use the Synthetic* classes):
  ClimateSource   baseline and per-climate-model future predictor fields, read in bands of rows (never the whole globe at once)
  Occurrences     thinned record cells with years and flags
  NativeRange / density grids are plain boolean / float arrays of shape (H, W) (or a coarser grid, see `resample`)
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from scipy.spatial import cKDTree

R_EARTH = 6371.0088          # km, same as ctw.common.R_EARTH up to rounding; kept local so this module has no heavy imports

PREDICTORS = ("bio1", "bio4", "bio5", "bio6", "bio12", "bio15", "bio17", "gdd", "cwd", "aet")
BASELINE = "1991-2020"
SSPS = ("SSP2-4.5", "SSP5-8.5")
PERIODS = ("2041-2060", "2081-2100")


def period_mid_year(period: str) -> float:
    """Mid-point of a 'YYYY-YYYY' window (inclusive years): 1991-2020 -> 2006.0."""
    a, b = (int(x) for x in period.split("-"))
    return (a + b + 1) / 2.0


@dataclass(frozen=True)
class GridSpec:
    """Geometry of a global equirectangular grid, row 0 north."""
    H: int = 4320
    W: int = 8640

    @property
    def dlat(self) -> float:
        return 180.0 / self.H

    @property
    def dlon(self) -> float:
        return 360.0 / self.W

    def lat(self, rows=None) -> np.ndarray:
        r = np.arange(self.H) if rows is None else np.asarray(rows)
        return 90.0 - (r + 0.5) * self.dlat

    def lon(self, cols=None) -> np.ndarray:
        c = np.arange(self.W) if cols is None else np.asarray(cols)
        return -180.0 + (c + 0.5) * self.dlon

    def row_of(self, lat) -> np.ndarray:
        return np.clip(((90.0 - np.asarray(lat)) / self.dlat).astype(int), 0, self.H - 1)

    def col_of(self, lon) -> np.ndarray:
        return np.clip(((np.asarray(lon) + 180.0) / self.dlon).astype(int), 0, self.W - 1)

    def row_area_km2(self) -> np.ndarray:
        """Area of one cell in each row (km2), exact for a spherical Earth."""
        edges = np.radians(90.0 - np.arange(self.H + 1) * self.dlat)
        return R_EARTH ** 2 * np.radians(self.dlon) * (np.sin(edges[:-1]) - np.sin(edges[1:]))

    def xyz(self, rows, cols) -> np.ndarray:
        la, lo = np.radians(self.lat(rows)), np.radians(self.lon(cols))
        return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)

    def km_xy(self, rows, cols) -> np.ndarray:
        """Planar (sinusoidal) kilometre coordinates, used only to assign spatial blocks (not for distances)."""
        la, lo = np.radians(self.lat(rows)), np.radians(self.lon(cols))
        return np.stack([R_EARTH * lo * np.cos(la), R_EARTH * la], -1)

    def coarse_factor(self, target_deg: float = 0.25) -> int:
        """Block factor so a coarse cell is about target_deg wide (distance work is done on this coarser grid)."""
        return max(1, int(round(target_deg / self.dlat)))


def resample(mask: np.ndarray, spec: GridSpec) -> np.ndarray:
    """Nearest-neighbour resample of a global (h, w) grid (row 0 north) to `spec`. Same shape: returned unchanged."""
    if mask.shape == (spec.H, spec.W):
        return mask
    h, w = mask.shape
    r = np.minimum((np.arange(spec.H) + 0.5) * h / spec.H, h - 1).astype(int)
    c = np.minimum((np.arange(spec.W) + 0.5) * w / spec.W, w - 1).astype(int)
    return mask[np.ix_(r, c)]


def _coarsen_any(mask: np.ndarray, f: int) -> np.ndarray:
    H, W = mask.shape
    h, w = -(-H // f), -(-W // f)
    pad = np.zeros((h * f, w * f), bool)
    pad[:H, :W] = mask
    return pad.reshape(h, f, w, f).any((1, 3))


def within_km(mask: np.ndarray, spec: GridSpec, km: float, factor: int = None) -> np.ndarray:
    """Cells of the grid within `km` (great-circle) of any True cell of `mask`. Distances are computed between block centres on a
    grid coarsened by `factor` (default about 0.25 degree, error about one coarse cell, 14 km at 1/4 degree) and then repeated to the
    fine grid; the True cells themselves are always included. km <= 0 returns a copy of the mask."""
    if km <= 0 or not mask.any():
        return mask.copy()
    f = factor or spec.coarse_factor()
    r0, r1 = np.nonzero(mask.any(1))[0][[0, -1]]
    pad = int(np.ceil(km / 111.0 / spec.dlat)) + 2                     # rows within reach of the mask (latitude only; columns are not cropped)
    a, b = max(0, r0 - pad), min(spec.H, r1 + pad + 1)
    a, b = a - a % f, min(spec.H, b + (-b) % f)
    sub = mask[a:b]
    cm = sub if f == 1 else _coarsen_any(sub, f)
    ch, cw = cm.shape
    # geometry of the coarse cells: centres of f x f blocks of the fine grid
    cr = a + (np.arange(ch) * f + (f - 1) / 2.0)
    cc = np.arange(cw) * f + (f - 1) / 2.0
    xyz = lambda rr, cc_: _xyz(spec, rr, cc_)                           # noqa: E731
    r, c = np.nonzero(cm)
    if len(r) > 300000:                                                 # a huge range: distance only matters near its edge
        r, c = np.nonzero(cm & ~_erode(cm))
    tree = cKDTree(xyz(cr[r], cc[c]))
    rr, cj = np.meshgrid(cr, cc, indexing="ij")
    d, _ = tree.query(xyz(rr.ravel(), cj.ravel()), distance_upper_bound=km / R_EARTH * 1.0001)
    near = (np.isfinite(d) & (d * R_EARTH <= km)).reshape(ch, cw)
    near = np.repeat(np.repeat(near, f, 0), f, 1)[:b - a, :spec.W]
    out = np.zeros((spec.H, spec.W), bool)
    out[a:a + near.shape[0], :near.shape[1]] = near
    return out | mask


def _xyz(spec: GridSpec, fine_rows, fine_cols) -> np.ndarray:
    """Unit vectors of (possibly fractional) fine-grid row / column positions."""
    la = np.radians(90.0 - (np.asarray(fine_rows, float) + 0.5) * spec.dlat)
    lo = np.radians(-180.0 + (np.asarray(fine_cols, float) + 0.5) * spec.dlon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)


def _erode(m: np.ndarray) -> np.ndarray:
    e = m.copy()
    e[1:] &= m[:-1]
    e[:-1] &= m[1:]
    e[:, 1:] &= m[:, :-1]
    e[:, :-1] &= m[:, 1:]
    return e


def nearest_km(src_rc: np.ndarray, spec: GridSpec, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Great-circle km from each (rows, cols) cell to the nearest of the cells in src_rc (n, 2). inf if src is empty."""
    if len(src_rc) == 0:
        return np.full(len(rows), np.inf)
    d, _ = cKDTree(spec.xyz(src_rc[:, 0], src_rc[:, 1])).query(spec.xyz(rows, cols))
    return d * R_EARTH


# --------------------------------------------------------------------------- data interfaces
@dataclass
class Occurrences:
    """Thinned record cells of one species on the grid (one entry per record kept; duplicates in a cell are allowed and collapsed)."""
    rows: np.ndarray
    cols: np.ndarray
    years: np.ndarray = None           # int per record (0 or negative = unknown)
    flags: np.ndarray = None           # int bit flags per record; 0 = clean. W2 defines the bits; nonzero is excluded unless allowed

    def __post_init__(self):
        self.rows, self.cols = np.asarray(self.rows, int), np.asarray(self.cols, int)
        n = len(self.rows)
        self.years = np.zeros(n, int) if self.years is None else np.asarray(self.years, int)
        self.flags = np.zeros(n, int) if self.flags is None else np.asarray(self.flags, int)

    def select(self, ok: np.ndarray) -> "Occurrences":
        return Occurrences(self.rows[ok], self.cols[ok], self.years[ok], self.flags[ok])

    def unique_cells(self) -> np.ndarray:
        """(k, 2) unique (row, col) pairs, sorted."""
        if len(self.rows) == 0:
            return np.zeros((0, 2), int)
        return np.unique(np.stack([self.rows, self.cols], 1), axis=0)


class ClimateSource:
    """Predictor fields on the grid. Subclasses implement `baseline_band` and `future_band`; point extraction is derived.

    `names` are predictor names (subset of PREDICTORS). Bands are float32 arrays of shape (len(names), r1 - r0, W); cells without data
    (ocean, ice) are NaN. Future fields are one climate model's fine-grid predictors (W1's apply_deltas(...) applied on the fly)."""
    spec: GridSpec
    names: tuple = PREDICTORS

    def baseline_band(self, r0: int, r1: int, names=None, window: str = BASELINE) -> np.ndarray:
        raise NotImplementedError

    def future_models(self, ssp: str, period: str) -> list:
        raise NotImplementedError

    def future_band(self, ssp: str, period: str, model: str, r0: int, r1: int, names=None) -> np.ndarray:
        raise NotImplementedError

    def baseline_points(self, rows: np.ndarray, cols: np.ndarray, names=None, window: str = BASELINE, band_rows: int = 256) -> np.ndarray:
        """(n, len(names)) predictor values at cells, read band by band (only bands that contain a requested row)."""
        names = tuple(names or self.names)
        rows, cols = np.asarray(rows), np.asarray(cols)
        out = np.full((len(rows), len(names)), np.nan, np.float32)
        band = rows // band_rows
        for b in np.unique(band):
            sel = np.nonzero(band == b)[0]
            r0 = int(b) * band_rows
            r1 = min(r0 + band_rows, self.spec.H)
            B = self.baseline_band(r0, r1, names, window)
            out[sel] = B[:, rows[sel] - r0, cols[sel]].T
        return out

    def land_band(self, r0: int, r1: int) -> np.ndarray:
        """Cells with a complete baseline predictor set (default: first predictor finite)."""
        return np.isfinite(self.baseline_band(r0, r1, self.names[:1])[0])


def land_mask(src: ClimateSource, band_rows: int = 256) -> np.ndarray:
    H, W = src.spec.H, src.spec.W
    m = np.zeros((H, W), bool)
    for r0 in range(0, H, band_rows):
        m[r0:r0 + band_rows] = src.land_band(r0, min(r0 + band_rows, H))
    return m


# --------------------------------------------------------------------------- synthetic stand-in (tests, dry runs)
@dataclass
class SyntheticClimate(ClimateSource):
    """A deterministic fake world with ten correlated predictors (a smooth function of latitude, longitude and elevation-like noise),
    land as a few blobs, and `n_models` future climate models (warming 2.0 to 4.0 C scaled by scenario and period, with polar
    amplification, +-8% precipitation). Same band interface as the real source."""
    spec: GridSpec = GridSpec(90, 180)
    n_models: int = 6
    seed: int = 0
    names: tuple = PREDICTORS
    _cache: dict = field(default_factory=dict, repr=False)

    def _fields(self):
        if "base" in self._cache:
            return self._cache["base"]
        s = self.spec
        rng = np.random.default_rng(self.seed)
        lat = s.lat()[:, None] * np.ones((1, s.W))
        lon = s.lon()[None, :] * np.ones((s.H, 1))
        # smooth noise from a few random sinusoids (no scipy.ndimage needed, cheap and reproducible)
        def smooth(k):
            f = np.zeros((s.H, s.W))
            for _ in range(k):
                a, b, p, q = rng.uniform(1, 4), rng.uniform(1, 4), rng.uniform(0, 6.28), rng.uniform(0, 6.28)
                f += np.sin(a * np.radians(lat) * 2 + p) * np.cos(b * np.radians(lon) + q)
            return f / np.sqrt(k)
        relief = smooth(5)
        wet = smooth(5)
        land = (smooth(6) + 0.5 * np.cos(np.radians(lat) * 1.5)) > -0.1
        land &= np.abs(lat) < 80
        t = 28 - 0.55 * np.abs(lat) - 3.5 * relief
        bio1 = t
        bio4 = 2.0 + 0.06 * np.abs(lat) * 10 / 3 + 1.5 * smooth(4) ** 2 + 0.5 * smooth(3)             # temperature seasonality
        bio5 = t + 8 + 5.0 * smooth(4)
        bio6 = t - 8 - 0.20 * np.abs(lat) + 4.0 * smooth(4)
        bio12 = np.exp(6.3 + 0.5 * wet - 0.012 * np.abs(lat - 10) + 0.3 * np.cos(np.radians(lat) * 4))
        bio15 = 30 + 20 * smooth(4)
        bio17 = bio12 * 0.12 * np.exp(0.4 * smooth(3))
        gdd = np.clip(t, 0, None) * 365 * 0.9 + 100 * smooth(2)
        pet = np.clip(t + 5, 0, None) * 60 + 200
        cwd = np.clip(pet - bio12 * 0.8, 0, None)
        aet = np.minimum(pet, bio12) * 0.8
        stack = np.stack([bio1, bio4, bio5, bio6, bio12, bio15, bio17, gdd, cwd, aet]).astype(np.float32)
        self._cache["base"] = (stack, land, lat)
        return self._cache["base"]

    def _sel(self, names):
        names = tuple(names or self.names)
        return [PREDICTORS.index(n) for n in names]

    def baseline_band(self, r0, r1, names=None, window=BASELINE):
        stack, land, _ = self._fields()
        out = stack[self._sel(names)][:, r0:r1].copy()
        out[:, ~land[r0:r1]] = np.nan
        shift = {"1966-1985": -0.5, "2005-2024": 0.45}.get(window, 0.0)
        sel = self._sel(names)
        if shift and 0 in sel:
            out[sel.index(0)] += shift
        return out

    def future_models(self, ssp, period):
        return [f"M{i}" for i in range(self.n_models)]

    def future_band(self, ssp, period, model, r0, r1, names=None):
        stack, land, lat = self._fields()
        idx = self._sel(names)
        i = int(model[1:])
        k = {"SSP2-4.5": 1.0, "SSP5-8.5": 1.6}[ssp] * {"2041-2060": 1.0, "2081-2100": 1.7}[period]
        dT = k * (1.2 + 1.6 * i / max(self.n_models - 1, 1)) * (1 + 0.5 * np.abs(lat[r0:r1]) / 90)
        dP = 1 + 0.08 * np.sin(np.radians(lat[r0:r1]) * 3 + i)
        x = stack[:, r0:r1].copy()
        x[[0, 2, 3]] += dT[None]            # bio1, bio5, bio6
        x[7] += 120 * dT                    # gdd
        for j in (4, 6, 9):
            x[j] *= dP
        x[8] = np.clip(x[8] + 25 * dT - (dP - 1) * 100, 0, None)      # cwd grows with warming
        out = x[idx]
        out[:, ~land[r0:r1]] = np.nan
        return out
