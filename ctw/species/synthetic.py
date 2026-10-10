"""Virtual species on the synthetic climate source (tests and dry runs of the pilot pipeline; no real data).

Truth is known: suitability is a product of Gaussians in two predictors, the range is suitability above a cut, records are drawn with
probability proportional to suitability times an effort surface, plus a few false positives. The target-group density is the
effort surface itself (the best case for bias correction, as in spike F)."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from .grid import GridSpec, Occurrences, SyntheticClimate, land_mask, within_km, BASELINE


@dataclass
class Virtual:
    name: str
    drivers: tuple          # (predictor, optimum, width) x2
    cut: float = 0.35
    n_records: int = 400
    bias: float = 1.0       # effort exponent
    fp: float = 0.03
    group: str = "tree"
    region: tuple = None    # (lat0, lat1, lon0, lon1): the only place it can occur, a non-climatic limit the climate model cannot see


def suitability(X: dict, v: Virtual) -> np.ndarray:
    s = 1.0
    for name, mu, sd in v.drivers:
        s = s * np.exp(-0.5 * ((X[name] - mu) / sd) ** 2)
    return s


def make(src: SyntheticClimate, v: Virtual, seed: int = 0, window: str = BASELINE):
    """Returns dict(occ, native, density, truth_now, land, suit) for virtual species `v` on `src`."""
    spec = src.spec
    rng = np.random.default_rng(seed)
    land = land_mask(src)
    names = [d[0] for d in v.drivers]
    B = src.baseline_band(0, spec.H, names, window)
    X = {n: B[i] for i, n in enumerate(names)}
    suit = np.nan_to_num(suitability(X, v), nan=0.0)
    la, lo = spec.lat()[:, None], spec.lon()[None, :]
    box = np.ones((spec.H, spec.W), bool) if v.region is None else (
        (la >= v.region[0]) & (la <= v.region[1]) & (lo >= v.region[2]) & (lo <= v.region[3]))
    truth = (suit >= v.cut) & land & box
    lat = spec.lat()[:, None] * np.ones((1, spec.W))
    effort = (0.2 + 0.8 * (np.cos(np.radians(lat)) ** 2) * (0.5 + 0.5 * np.sin(np.radians(spec.lon())[None, :] * 2 + 1))) ** v.bias
    effort = np.where(land, effort, 0.0)
    p = np.where(truth, suit * effort, 0.0).ravel()
    n_fp = int(v.fp * v.n_records)
    idx = rng.choice(p.size, v.n_records - n_fp, p=p / p.sum()) if p.sum() > 0 else np.zeros(0, int)
    pe = np.where(land, effort, 0.0).ravel()
    fp = rng.choice(pe.size, n_fp, p=pe / pe.sum())
    allc = np.r_[idx, fp]
    occ = Occurrences(allc // spec.W, allc % spec.W, years=rng.integers(1990, 2024, len(allc)))
    native = within_km(truth, spec, 150.0) & land
    return dict(occ=occ, native=native, density=effort, truth=truth, land=land, suit=suit)


CATALOGUE = [
    Virtual("broad", (("bio1", 12.0, 4.0), ("bio12", 700.0, 350.0)), 0.30, 600),                 # large range: low AUC, good range (as F)
    Virtual("moderate", (("bio1", 12.0, 2.0), ("bio12", 700.0, 200.0)), 0.35, 500),
    Virtual("cold_limited", (("bio6", 0.0, 3.0), ("bio12", 900.0, 300.0)), 0.35, 500),
    Virtual("narrow", (("bio1", 18.0, 1.5), ("bio12", 800.0, 250.0)), 0.40, 250),
    Virtual("region_excluded", (("bio1", 12.0, 2.0), ("bio12", 700.0, 200.0)), 0.35, 500, region=(0.0, 90.0, -180.0, -30.0)),
]
