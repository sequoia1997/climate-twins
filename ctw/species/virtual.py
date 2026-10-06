"""Virtual species on the climate Climate Twins already ships (spike F).

A virtual species has a niche we define, so its true suitability, true range now and true range under the projected
climate are known exactly. We sample biased, noisy "occurrence" records from the true range, hand them to the SDM
engine (sdm.py) and measure how well it recovers the truth.

Climate: the present-day 16-value seasonal vector of every cell of the North America (15 km, 97,488 cells) and world
(0.5 degree, 64,958 cells) search pools, read from site/data/{na,world}.dat. Futures: the shards store the 24-model
change (delta) at ~790 (NA) / ~1,600 (world) places for each SSP and period; `Grid.climate(ssp, period)` spreads those
deltas to every cell by inverse-distance weighting (the change signal is smooth, 25-100 km, so this is adequate for
testing). Only delta-based futures exist; there is no per-cell future file.

Run `python -m ctw.species.virtual` for a one-screen summary of the species catalogue.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
import numpy as np
from scipy.spatial import cKDTree

from .. import common as C
from ..reshard import read

DATA = C.SITE / "data"
SSPS = ("SSP1-2.6", "SSP2-4.5", "SSP3-7.0", "SSP5-8.5")
PERIODS = ("2050", "2100")
# derived predictors (bioclim-like) built from the 16 seasonal values; ppt-type ones are logs
BIO_NAMES = ("mat", "tcold", "twarm", "tseas", "lpann", "lpdry", "lpwet", "vpd", "vpdmax", "wbal")
BIO_LABEL = {"mat": "mean annual temperature (C)", "tcold": "coldest-season mean minimum (C)",
             "twarm": "warmest-season mean maximum (C)", "tseas": "temperature seasonality (C)",
             "lpann": "log annual precipitation", "lpdry": "log driest-season precipitation",
             "lpwet": "log wettest-season precipitation", "vpd": "mean vapour-pressure deficit (kPa)",
             "vpdmax": "peak-season vapour-pressure deficit (kPa)", "wbal": "water-balance proxy, log(P) - log(VPD)"}
KM_PER_DEG = 111.195


# --------------------------------------------------------------------------- climate grid
def decode_pool(planes: np.ndarray, n: int) -> np.ndarray:
    """Page-encoded pool (16 planes of int16) -> raw (n, 16): temperatures and dewpoints /100, precipitation expm1(v/1000)."""
    X = planes.reshape(C.NV, n).T.astype("float64")
    X[:, :8] /= 100
    X[:, 12:16] /= 100
    X[:, 8:12] = np.expm1(X[:, 8:12] / 1000)
    return X


def bio(X: np.ndarray) -> np.ndarray:
    """(n, 16) raw seasonal climate -> (n, 10) derived predictors in BIO_NAMES order."""
    tx, tn, pp, dw = X[:, 0:4], X[:, 4:8], X[:, 8:12], X[:, 12:16]
    tm = (tx + tn) / 2
    vpd = np.maximum(C.sat_vap(tm) - C.sat_vap(dw), 0.0)
    pann = pp.sum(1)
    out = np.stack([tm.mean(1), tn.min(1), tx.max(1), tm.max(1) - tm.min(1), np.log1p(pann), np.log1p(pp.min(1)),
                    np.log1p(pp.max(1)), vpd.mean(1), vpd.max(1), np.log1p(pann) - np.log(vpd.mean(1) * 1000 + 1.0)], 1)
    return out


@dataclass
class Grid:
    """One modelling grid: cells with climate, area, position, and the place-level future deltas that make projections."""
    domain: str
    lat: np.ndarray
    lon: np.ndarray
    X: np.ndarray                      # (n, 16) present climate, raw units
    area: np.ndarray                   # km2 per cell
    row: np.ndarray
    col: np.ndarray
    plat: np.ndarray = None            # places carrying future deltas
    plon: np.ndarray = None
    ppop: np.ndarray = None
    delta: np.ndarray = None           # (np, 2 periods, 4 ssps, 24 members, 16) physical units (ppt in log(mm+1) units)
    parent: np.ndarray = None          # for a coarsened grid: fine-cell -> this grid's cell
    _idw: tuple = field(default=None, repr=False)
    _cache: dict = field(default_factory=dict, repr=False)

    @property
    def n(self) -> int:
        return len(self.lat)

    @property
    def xyz(self) -> np.ndarray:
        return C.unit_xyz(self.lat, self.lon)

    @property
    def km(self) -> np.ndarray:
        """Cheap planar coordinates (km) for block assignment and plotting; not for distances (use haversine / xyz)."""
        return np.c_[self.lon * KM_PER_DEG * np.cos(np.radians(self.lat)), self.lat * KM_PER_DEG]

    def predictors(self, X: np.ndarray = None, names=BIO_NAMES) -> np.ndarray:
        """Derived predictors for raw climate X (default: present day), columns in the order of `names`."""
        B = bio(self.X if X is None else X)
        return B[:, [BIO_NAMES.index(m) for m in names]]

    def _weights(self, k=5):
        if self._idw is None:
            tree = cKDTree(C.unit_xyz(self.plat, self.plon))
            d, i = tree.query(self.xyz, k=k)
            w = 1.0 / np.maximum(d, 1e-4) ** 2
            self._idw = (i, w / w.sum(1, keepdims=True))
        return self._idw

    def climate(self, ssp: str = None, period: str = None, member: int = None) -> np.ndarray:
        """Raw climate (n, 16) for the present (ssp None) or a scenario/period. `member` picks one of the 24 climate
        models; None uses the ensemble median change at each place, then spreads it to the cells (IDW, 5 places)."""
        if ssp is None:
            return self.X
        key = (ssp, period, member)
        if key not in self._cache:
            p, s = PERIODS.index(period), SSPS.index(ssp)
            D = self.delta[:, p, s]
            D = np.median(D, 1) if member is None else D[:, member]
            i, w = self._weights()
            d = (D[i] * w[..., None]).sum(1)
            X = self.X.copy()
            X[:, :8] += d[:, :8]
            X[:, 12:] += d[:, 12:]
            X[:, 8:12] = np.expm1(np.log1p(X[:, 8:12]) + d[:, 8:12])
            self._cache[key] = X
        return self._cache[key]

    def coarsen(self, f: int) -> "Grid":
        """Block-average the grid by an integer factor f (15 km -> 15*f km). Keeps `parent` (fine cell -> coarse cell)."""
        key = (self.row // f) * 100000 + (self.col // f)
        u, inv = np.unique(key, return_inverse=True)
        cnt = np.bincount(inv).astype(float)

        def mean(a):
            return np.stack([np.bincount(inv, a[:, j]) / cnt for j in range(a.shape[1])], 1)
        la = np.bincount(inv, self.lat) / cnt
        lo = np.bincount(inv, self.lon) / cnt
        g = Grid(self.domain, la, lo, mean(self.X), np.bincount(inv, self.area), u // 100000, u % 100000,
                 self.plat, self.plon, self.ppop, self.delta, parent=inv)
        return g

    def neighbours(self, k=9) -> np.ndarray:
        """Indices of the k nearest cells (including self), for coordinate-jitter noise."""
        if "nn" not in self._cache:
            self._cache["nn"] = cKDTree(self.xyz).query(self.xyz, k=k)[1]
        return self._cache["nn"]


def _place_deltas(domain_g: int):
    idx = json.loads((DATA / "index.json").read_text())
    cols = {c: j for j, c in enumerate(idx["cols"])}
    rows = idx["rows"]
    lat = np.array([r[cols["lat"]] for r in rows])
    lon = np.array([r[cols["lon"]] for r in rows])
    pop = np.array([r[cols["pop"]] for r in rows], "float64")
    gg = np.array([r[cols["g"]] for r in rows])
    out = {}
    for sh in idx["shards"]:
        if sh["g"] != domain_g:
            continue
        h, a, _ = read(DATA / sh["f"])
        ids = h["ids"]
        d = a(h["fut_d"]).astype("float64").reshape(len(ids), len(PERIODS), len(SSPS), -1, C.NV)
        d[..., :8] /= 100
        d[..., 12:] /= 100
        d[..., 8:12] /= 1000
        for j, t in enumerate(ids):
            out[t] = d[j]
    order = np.array(sorted(out))
    return lat[order], lon[order], pop[order], np.stack([out[t] for t in order])


def load_grid(domain: str = "na") -> Grid:
    """Read the present-day pool of `domain` ('na' or 'world') and the place-level futures from site/data."""
    h, a, _ = read(DATA / f"{domain}.dat")
    nx, ny = h["nx"], h["ny"]
    m = np.unpackbits(a(h["mask"]).view(np.uint8))[:nx * ny]
    cells = np.nonzero(m)[0]
    n = len(cells)
    if domain == "na":
        X = decode_pool(a(h["pool"]), n)
        lat, lon = a(h["plat"]).astype("float64"), a(h["plon"]).astype("float64")
        area = np.full(n, (h["cell_m"] / 1000) ** 2)
        g = 0
    else:
        X = decode_pool(a(h["pool_p"]), n)
        res = h["res"]
        lat, lon = 90 - (cells // nx + .5) * res, -180 + (cells % nx + .5) * res
        area = (res * KM_PER_DEG) ** 2 * np.cos(np.radians(lat)) * (a(h["land"]).astype("float64") / 255)
        g = 1
    pla, plo, pop, delta = _place_deltas(g)
    return Grid(domain, lat, lon, X, area, cells // nx, cells % nx, pla, plo, pop, delta)


# --------------------------------------------------------------------------- niches
def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def gauss(x, mu, sd):
    """Gaussian response curve, 1 at the optimum mu, ~0.5 at +-1.18 sd."""
    return np.exp(-0.5 * ((x - mu) / sd) ** 2)


def lower(x, x0, w):
    """Logistic response that needs x above x0 (cold or drought limit); w is the transition width."""
    return _sigmoid((x - x0) / w)


def upper(x, x0, w):
    """Logistic response that needs x below x0 (heat limit)."""
    return _sigmoid((x0 - x) / w)


@dataclass
class VirtualSpecies:
    """A species with a known climatic niche. `response(B)` maps (n, 10) bio predictors to suitability in [0, 1];
    `region(grid)` is an optional boolean mask of where the species is excluded for non-climatic reasons.
    Truth: present iff suitability >= 0.5 and not excluded."""
    name: str
    description: str
    drivers: tuple                     # predictor names the niche depends on
    response: callable
    exclude: callable = None

    def suitability(self, grid: Grid, ssp: str = None, period: str = None, member: int = None) -> np.ndarray:
        B = bio(grid.climate(ssp, period, member))
        s = self.response(B)
        if self.exclude is not None:
            s = np.where(self.exclude(grid), 0.0, s)
        return s

    def present(self, grid: Grid, ssp: str = None, period: str = None, member: int = None) -> np.ndarray:
        """True presence (bool per cell)."""
        return self.suitability(grid, ssp, period, member) >= 0.5


def catalog(grid: Grid) -> dict:
    """Six virtual species whose niche parameters are quantiles of the grid's own present-day predictors, so the same
    definitions work for NA and world. Names say what is being tested."""
    B = bio(grid.X)
    q = lambda v, p: float(np.quantile(B[:, BIO_NAMES.index(v)], p))        # noqa: E731
    ix = {v: BIO_NAMES.index(v) for v in BIO_NAMES}
    lon_cut = float(np.quantile(grid.lon, 0.35))
    sp = [
        VirtualSpecies("broad", "broad climatic tolerance (wide temperature and rainfall optimum)", ("mat", "lpann"),
                       lambda B, a=(q("mat", .5), (q("mat", .9) - q("mat", .1)) / 2.6, q("lpann", .5), (q("lpann", .9) - q("lpann", .1)) / 2.6):
                       gauss(B[:, ix["mat"]], a[0], a[1]) * gauss(B[:, ix["lpann"]], a[2], a[3])),
        VirtualSpecies("narrow", "narrow temperature and rainfall optimum (small range)", ("mat", "lpann"),
                       lambda B, a=(q("mat", .55), (q("mat", .9) - q("mat", .1)) / 11.0, q("lpann", .6), (q("lpann", .9) - q("lpann", .1)) / 7.0):
                       gauss(B[:, ix["mat"]], a[0], a[1]) * gauss(B[:, ix["lpann"]], a[2], a[3])),
        VirtualSpecies("cold_limited", "frost-intolerant: needs a mild coldest season and some rain", ("tcold", "lpann"),
                       lambda B, a=(q("tcold", .45), q("lpann", .2)):
                       lower(B[:, ix["tcold"]], a[0], 1.2) * lower(B[:, ix["lpann"]], a[1], 0.15)),
        VirtualSpecies("drought_limited", "needs a positive water balance and a not-too-cold winter", ("wbal", "tcold"),
                       lambda B, a=(q("wbal", .45), q("tcold", .15)):
                       lower(B[:, ix["wbal"]], a[0], 0.12) * lower(B[:, ix["tcold"]], a[1], 1.5)),
        VirtualSpecies("heat_limited", "cool-climate species: optimum at a low mean temperature, hard limit on summer heat", ("mat", "twarm"),
                       lambda B, a=(q("mat", .3), (q("mat", .9) - q("mat", .1)) / 3.2, q("twarm", .55)):
                       gauss(B[:, ix["mat"]], a[0], a[1]) * upper(B[:, ix["twarm"]], a[2], 1.0)),
        VirtualSpecies("region_excluded", "broad climate niche but absent from the western 35% of the domain (non-climatic constraint)",
                       ("mat", "lpann"),
                       lambda B, a=(q("mat", .5), (q("mat", .9) - q("mat", .1)) / 2.0, q("lpann", .5), (q("lpann", .9) - q("lpann", .1)) / 2.0):
                       gauss(B[:, ix["mat"]], a[0], a[1]) * gauss(B[:, ix["lpann"]], a[2], a[3]),
                       exclude=lambda g, c=lon_cut: g.lon < c),
    ]
    return {s.name: s for s in sp}


# --------------------------------------------------------------------------- sampling bias and records
def bias_surface(grid: Grid, sigma_km: float = 120.0, floor: float = 0.03) -> np.ndarray:
    """Relative sampling effort per cell in (0, 1]: a sum of Gaussian kernels around known places weighted by
    log10(population), plus a small floor. A stand-in for road and city proximity (the real bias in GBIF data)."""
    P = C.unit_xyz(grid.plat, grid.plon)
    w = np.log10(np.maximum(grid.ppop, 10.0))
    X = grid.xyz
    out = np.zeros(grid.n)
    s2 = (sigma_km / C.R_EARTH) ** 2
    for a in range(0, grid.n, 4000):
        d2 = ((X[a:a + 4000, None, :] - P[None]) ** 2).sum(-1)       # chord^2, ~ arc^2 for short distances
        out[a:a + 4000] = (np.exp(-d2 / (2 * s2)) * w).sum(1)
    out = out / out.max()
    return floor + (1 - floor) * out


def sample_occurrences(grid: Grid, present: np.ndarray, suit: np.ndarray, n: int, rng: np.random.Generator,
                       bias: np.ndarray = None, bias_power: float = 1.0, false_pos: float = 0.03, jitter: float = 0.10) -> np.ndarray:
    """Draw up to n distinct occurrence cells.
    Probability of a record in a truly occupied cell is proportional to suitability x effort^bias_power (bias_power 0 =
    unbiased). Noise: a share `false_pos` of records are replaced by a random effort-weighted cell anywhere (misidentification,
    escapes), and a share `jitter` is moved to a random neighbouring cell (coordinate error). One record per cell
    (thinned), so the result can be shorter than n."""
    idx = np.nonzero(present)[0]
    if len(idx) == 0:
        return idx
    w = suit[idx] * (bias[idx] ** bias_power if bias is not None else 1.0)
    k = min(n, len(idx))
    rec = rng.choice(idx, k, replace=False, p=w / w.sum())
    nfp = rng.binomial(k, false_pos)
    if nfp:
        rec[:nfp] = rng.choice(grid.n, nfp, p=None if bias is None else bias / bias.sum())
    nj = rng.binomial(k, jitter)
    if nj:
        pick = rng.integers(1, 9, nj)
        rec[nfp:nfp + nj] = grid.neighbours()[rec[nfp:nfp + nj], pick]
    return np.unique(rec)


def target_group_background(grid: Grid, bias: np.ndarray, n: int, rng: np.random.Generator, bias_power: float = 1.0,
                            n_group: int = 20000) -> np.ndarray:
    """Cells of a simulated target group: `n_group` records of other species drawn with the same effort surface (so the
    bias is estimated from noisy data, not handed over exactly), from which n background cells are taken, as in
    target-group background practice. Returns cell indices (with repeats removed)."""
    grp = rng.choice(grid.n, n_group, p=bias ** bias_power / (bias ** bias_power).sum())
    cells = np.unique(grp)
    return rng.choice(cells, min(n, len(cells)), replace=False)


def uniform_background(grid: Grid, n: int, rng: np.random.Generator) -> np.ndarray:
    """Random background cells over the whole domain."""
    return rng.choice(grid.n, min(n, grid.n), replace=False)


if __name__ == "__main__":
    g = load_grid("na")
    print(f"NA grid: {g.n} cells, {len(g.plat)} places carrying deltas")
    for name, s in catalog(g).items():
        pr = s.present(g)
        f1, f2 = s.present(g, "SSP2-4.5", "2050"), s.present(g, "SSP5-8.5", "2100")
        print(f"{name:16s} range {g.area[pr].sum():10.0f} km2 ({pr.mean():5.1%}); 2050/245 {f1.mean():5.1%}; 2100/585 {f2.mean():5.1%}")
