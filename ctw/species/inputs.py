"""Adapters from the real pilot data (W1 climate stack, W2 occurrences) to the interfaces of ctw/species/grid.py.

W1 (docs/pilot/W1-climate.md, ctw/species/climstack.py): tile files `pred_<product>_<tile>.npz` (baseline and hindcast windows), `basem_<tile>.npz`
(baseline monthly climatology) and `deltas_<model>.npz` (per climate model change factors) in one directory; futures of one climate model
come from `climstack.apply_deltas` on demand.

The directory is $W3_CLIM (default work/clim); `fetch_release` downloads the files of the GitHub release tagged `species-pilot-data`.
"""
from __future__ import annotations
import os
import numpy as np

from . import climstack as CS, climategrid as G
from .grid import GridSpec, ClimateSource, BASELINE

SSP_NAME = {"SSP2-4.5": "ssp245", "SSP5-8.5": "ssp585"}
WINDOW_PRODUCT = {"1991-2020": "base_1991-2020", "1966-1985": "hind_1966-1985", "2005-2024": "hind_2005-2024"}
SPEC = GridSpec(G.NLAT, G.NLON)


class W1Source(ClimateSource):
    """ClimateSource over W1's tile files. Bands are read from the tile files directly (no whole-grid arrays). For futures,
    `prepare(domain)` builds one BaselineStack of the domain's land cells (monthly baseline, about 340 bytes per cell) and keeps it for
    the whole projection; one climate model's predictors for a band are then produced by `apply_deltas` on that band's cells."""

    def __init__(self, root: str = None, models=None, names=None):
        self.root = root or os.environ.get("W3_CLIM", "work/clim")
        self.spec = SPEC
        self.names = tuple(names or CS.NAMES)
        self._lib = CS.DeltaLibrary(self.root)
        avail = [m for m in self._lib.models() if m != "ensemble_median"]
        sel = models or (os.environ.get("W3_MODELS", "").split(",") if os.environ.get("W3_MODELS") else None)
        self._models = [m for m in avail if (not sel or m in sel)]
        self._tiles = {}            # (product, tile) -> loaded pred dict (small LRU)
        self._stack = None
        self._interp = {}
        self._plan = {}
        self.decimate = int(os.environ.get("W3_DECIMATE", "4"))

    # ---- baseline / hindcast windows
    def _pred(self, product, tile):
        k = (product, tile)
        if k not in self._tiles:
            if len(self._tiles) >= 5:
                self._tiles.pop(next(iter(self._tiles)))
            self._tiles[k] = CS.load_pred(os.path.join(self.root, f"pred_{product}_{tile}.npz"))
        return self._tiles[k]

    def baseline_band(self, r0, r1, names=None, window=BASELINE):
        names = tuple(names or self.names)
        ix = [CS.NAMES.index(n) for n in names]
        product = WINDOW_PRODUCT[window]
        out = np.full((len(ix), r1 - r0, self.spec.W), np.nan, np.float32)
        for tr in range(r0 // CS.TH, (r1 - 1) // CS.TH + 1):
            a, b = max(r0, tr * CS.TH), min(r1, (tr + 1) * CS.TH)
            for tc in range(CS.NTC):
                tile = f"r{tr}c{tc}"
                if not os.path.exists(os.path.join(self.root, f"pred_{product}_{tile}.npz")):
                    continue
                p = self._pred(product, tile)
                land = p["land"]
                start = int(land[:a - tr * CS.TH].sum())
                sub = land[a - tr * CS.TH:b - tr * CS.TH]
                n = int(sub.sum())
                if not n:
                    continue
                block = np.full((len(ix), b - a, CS.TW), np.nan, np.float32)
                block[:, sub] = p["data"][ix][:, start:start + n]
                out[:, a - r0:b - r0, tc * CS.TW:(tc + 1) * CS.TW] = block
        return out

    def land_band(self, r0, r1):
        out = np.zeros((r1 - r0, self.spec.W), bool)
        for tr in range(r0 // CS.TH, (r1 - 1) // CS.TH + 1):
            a, b = max(r0, tr * CS.TH), min(r1, (tr + 1) * CS.TH)
            for tc in range(CS.NTC):
                f = os.path.join(self.root, f"pred_{WINDOW_PRODUCT[BASELINE]}_r{tr}c{tc}.npz")
                if os.path.exists(f):
                    out[a - r0:b - r0, tc * CS.TW:(tc + 1) * CS.TW] = self._pred(WINDOW_PRODUCT[BASELINE], f"r{tr}c{tc}")["land"][a - tr * CS.TH:b - tr * CS.TH]
        return out

    # ---- futures
    def future_models(self, ssp, period):
        return list(self._models)

    def prepare(self, domain: np.ndarray):
        """Load the baseline monthly stack of the land cells inside `domain` (bool, full grid), sorted by (row, col)."""
        tiles = []
        parts = []
        for tr in range(CS.NTR):
            for tc in range(CS.NTC):
                rs, cs = CS.tile_window((tr, tc))
                if not domain[rs, cs].any():
                    continue
                f = os.path.join(self.root, f"basem_r{tr}c{tc}.npz")
                if not os.path.exists(f):
                    raise FileNotFoundError(f)
                land, _, mon = CS.load_basem(f)
                i, j = CS.land_index(land, (tr, tc))
                keep = domain[i, j]
                st = CS.BaselineStack({k: v[:, keep] for k, v in mon.items()}, G.cell_lat(i[keep]).astype("float64"), G.cell_lon(j[keep]).astype("float64"),
                                      i[keep], j[keep])
                parts.append(st)
                del mon
        order = np.lexsort((np.concatenate([p.col for p in parts]), np.concatenate([p.row for p in parts])))
        cat = lambda a: np.concatenate(a)[order]                                                       # noqa: E731
        self._stack = CS.BaselineStack({k: np.concatenate([p.monthly[k] for p in parts], axis=1)[:, order] for k in parts[0].monthly},
                                       cat([p.lat for p in parts]), cat([p.lon for p in parts]), cat([p.row for p in parts]), cat([p.col for p in parts]))
        self._interp = {}
        self._plan = {}

    def _band_plan(self, r0, r1, a, b):
        """Representative cells of a band and, for every cell, its nearest representative (cached per band). Representatives are the cells on
        a regular lattice of spacing `decimate` plus any cell farther than 2 x spacing from one (islands, coast). The change signal of the
        deltas is smooth (0.25 degree source), so it is computed on representatives only and added to every cell's own fine baseline;
        this cuts the cost of apply_deltas (about 140 microseconds per cell, measured) by decimate**2."""
        key = (r0, r1)
        if key in self._plan:
            return self._plan[key]
        from scipy.spatial import cKDTree
        st = self._stack
        row, col = st.row[a:b], st.col[a:b]
        f = self.decimate
        if f <= 1:
            idx = np.arange(b - a)
            near = idx
        else:
            idx = np.nonzero((row % f == 0) & (col % f == 0))[0]
            if len(idx) == 0:
                idx = np.array([0])
            xy = np.stack([row, col], 1).astype(float)
            d, _ = cKDTree(xy[idx]).query(xy)
            extra = np.nonzero(d > 2 * f)[0]
            if len(extra):
                idx = np.union1d(idx, extra)
            _, near = cKDTree(xy[idx]).query(xy)
        sub = st.subset(slice(a, b)).subset(idx)
        base = CS.predict({k: sub.monthly[k] for k in CS.PRED_VARS})                  # baseline predictors from the same monthly data
        self._plan[key] = (idx, near, sub, base)
        return self._plan[key]

    def future_band(self, ssp, period, model, r0, r1, names=None):
        names = tuple(names or self.names)
        if self._stack is None:
            raise RuntimeError("call prepare(domain) before future_band")
        st = self._stack
        a, b = np.searchsorted(st.row, [r0, r1])
        out = np.full((len(names), r1 - r0, self.spec.W), np.nan, np.float32)
        if b <= a:
            return out
        idx, near, sub, base = self._band_plan(r0, r1, a, b)
        d = self._lib.get_model(model)
        it = self._interp.get((r0, r1))
        if it is None:
            it = self._interp[(r0, r1)] = CS.PointInterp(d.lat, d.lon, sub.lat, sub.lon)
        res = CS.apply_deltas(sub, d, model, SSP_NAME[ssp], period, interp=it)
        full = st.subset(slice(a, b))
        pb = self._base_full(r0, r1, a, b, names)
        for k, n in enumerate(names):
            j = CS.NAMES.index(n)
            delta = (res[n] - base[j])[near]
            v = pb[k] + delta
            if n in NONNEG:
                v = np.maximum(v, 0)
            out[k, full.row - r0, full.col] = v
        return out

    def _base_full(self, r0, r1, a, b, names):
        """The fine baseline predictors (from W1's pred files) at the band's stack cells, (len(names), n)."""
        k = ("pb", r0, r1, names)
        if k not in self._plan:
            st = self._stack
            row, col = st.row[a:b], st.col[a:b]
            self._plan[k] = self.baseline_band(r0, r1, names)[:, row - r0, col]
        return self._plan[k]


NONNEG = {"bio12", "bio15", "bio17", "gdd", "cwd", "aet", "bio4"}


# Tiles (rows from 90N in steps of 45 degrees, columns from 180W in steps of 90 degrees) that cover a continent plus a margin for the
# projection buffer. A tile that is missing from the climate directory silently truncates the domain, so over-include rather than under-include.
CONTINENT_TILES = {
    "NORTH_AMERICA": ("r0c0", "r0c1", "r1c0", "r1c1"),
    "SOUTH_AMERICA": ("r1c1", "r2c0", "r2c1", "r3c0", "r3c1"),
    "EUROPE": ("r0c1", "r0c2", "r1c1", "r1c2"),
    "AFRICA": ("r1c1", "r1c2", "r2c1", "r2c2", "r3c2"),
    "ASIA": ("r0c2", "r0c3", "r1c2", "r1c3", "r2c2", "r2c3"),
    "OCEANIA": ("r1c3", "r2c3", "r3c3"),
}


def tiles_for(native_continents: str) -> list:
    """Tile names to download for a pilot-table row's native_continents_curated ('NORTH_AMERICA;EUROPE;ASIA(W)')."""
    out = []
    for c in (native_continents or "").split(";"):
        c = c.split("(")[0].strip().upper()
        for t in CONTINENT_TILES.get(c, ()):
            if t not in out:
                out.append(t)
    return out or sorted(CS.ALL_TILES)


def climate_source(root: str = None):
    src = W1Source(root)
    return src, src.spec


def _load_grid(path):
    """A boolean / float grid from .npy or .npz (first array) or .npz with key 'mask' / 'density'."""
    if path.endswith(".npy"):
        return np.load(path)
    z = np.load(path)
    for k in ("mask", "native", "density", "data"):
        if k in z.files:
            return z[k]
    return z[z.files[0]]


def species_inputs(meta: dict, spec: GridSpec, root: str = None):
    """(Occurrences, native mask or None, target-group density or None, DOIs) for one species from W2's release assets in $W3_OCC:
      w2-cells-<Genus_species>.parquet   one row per occupied cell: row, col, year_min, year_max, n_records, n_events, n_1970_1999, n_2000_2020, n_2021_plus
      w2-report-<Genus_species>.json     cleaning report with the GBIF download `doi`
      w2-native-<Genus_species>.(npy|npz)  native-range mask   [file name is a GUESS until W2 documents it; None when absent]
      w2-tg-<group>.(npy|npz)            target-group record density grid [same caveat]
    A missing native mask leaves the mandatory range check 'missing' (Tier 3) rather than silently skipping it."""
    import glob
    import json
    import pandas as pd
    from .grid import Occurrences
    root = root or os.environ.get("W3_OCC", "work/occ")
    tag = meta["scientific_name"].replace(" ", "_")
    df = pd.read_parquet(os.path.join(root, f"w2-cells-{tag}.parquet"))
    occ = Occurrences(df["row"].to_numpy(int), df["col"].to_numpy(int), years=df["year_max"].to_numpy(int))
    native = density = None
    for pat, which in ((f"w2-native-{tag}.*", "native"), (f"w2-tg-{meta.get('group')}.*", "density")):
        f = sorted(glob.glob(os.path.join(root, pat)))
        if f:
            g = _load_grid(f[0])
            if which == "native":
                native = g.astype(bool)
            else:
                density = g.astype(np.float32)
    dois = []
    rp = os.path.join(root, f"w2-report-{tag}.json")
    if os.path.exists(rp):
        r = json.load(open(rp))
        if r.get("doi"):
            dois.append("https://doi.org/" + r["doi"])
    return occ, native, density, dois
