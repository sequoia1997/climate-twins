"""Streamed projection of a fitted species over scenarios, periods and the climate-model ensemble (W3).

Memory rule: no per-model fine grid for the globe is ever held. The projection domain is walked in latitude bands (default 128 rows);
for each band and each scenario/period every climate model's fine-grid predictors are produced on demand by the climate source
(W1's apply_deltas), scored, reduced to the median suitability, the model-agreement count and the novelty vote, and discarded.
Only uint8 arrays (H x W) per scenario/period are kept.

Encoding (shared with the CTS writer, cts.py):
  S   7 bit suitability, rescaled per species so that its presence threshold maps to THR7 = 44 (the prototype's constant):
      below the threshold 0..43 linearly, above 44..127 linearly. So 'suitable' is S >= 44 for every species.
  A   model agreement 0..15 = round(15 * share of climate models whose suitability is >= threshold)
  N   1 where at least half of the climate models put the cell outside the training range of some predictor (MESS < 0)
Dispersal bounds are derived from S, the present range and the reach masks:  unlimited = S >= 44,  limited = unlimited AND (now OR
within reach of the present range),  none = unlimited AND now.  Cells of the present range that stop being suitable are lost in all modes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

from . import sdm
from .grid import GridSpec, ClimateSource, within_km, period_mid_year, BASELINE, R_EARTH
from .pipeline import Fit

THR7 = 44
AGREE_MIN = 0.75                      # a cell counts as 'models agree' when at least this share of climate models say suitable
MODES = ("unlimited", "limited", "none")

# Trait-based dispersal rule: potential range-expansion rate in km per decade by group. UNCALIBRATED: these are order-of-magnitude
# values (post-glacial tree migration 10-50 km per decade, birds and mammals can move much faster than they colonise), about 10x
# uncertain, to be calibrated by the hindcast. Species-specific values can be given in the species table and override these.
DISPERSAL_KM_PER_DECADE = {"tree": 15.0, "plant": 15.0, "crop": 10.0, "bird": 100.0, "mammal": 50.0,
                           "insect_arachnid": 40.0, "reptile": 10.0, "amphibian": 5.0, "fish": 50.0}
DISPERSAL_DEFAULT = 20.0


def dispersal_rule(group: str, override: float = None):
    """(km per decade, note). Always marked uncalibrated."""
    if override is not None and np.isfinite(override):
        return float(override), "species-specific value from the species table; uncalibrated"
    v = DISPERSAL_KM_PER_DECADE.get(group, DISPERSAL_DEFAULT)
    return v, f"group rule for '{group}'; uncalibrated, about 10x uncertain until calibrated by the hindcast"


def quantise(score: np.ndarray, thr: float) -> np.ndarray:
    """Suitability in [0, 1] -> 7 bit with the threshold at THR7 (see module doc). Monotone; (q >= THR7) == (score >= thr)."""
    s = np.clip(np.nan_to_num(score, nan=0.0), 0.0, 1.0)
    thr = float(np.clip(thr, 1e-6, 1 - 1e-6))
    lo = np.floor(s / thr * THR7)
    lo = np.minimum(lo, THR7 - 1)
    hi = THR7 + np.floor((s - thr) / (1 - thr) * (127 - THR7 + 1))
    q = np.where(s >= thr, np.minimum(hi, 127), lo)
    return q.astype(np.uint8)


@dataclass
class ProjConfig:
    band_rows: int = 128
    check_models: int = 5             # climate models used for the GAM check projection
    novel_vote: float = 0.5
    km_per_decade: float = None       # override of the group rule
    n_jobs: int = 1


@dataclass
class Scenario:
    ssp: str
    period: str
    n_models: int
    S: np.ndarray                     # uint8 (H, W)
    A: np.ndarray                     # uint8 (H, W), 0..15
    N: np.ndarray                     # uint8 (H, W), 0/1
    check: np.ndarray = None          # bool (H, W): GAM check model suitable (median over a few models)
    mahal_share: float = float("nan")   # share of (model, cell) pairs beyond the Mahalanobis cutoff, informational


@dataclass
class Projection:
    spec: GridSpec
    thr: float
    S0: np.ndarray                    # uint8 (H, W) present suitability
    novel_now: np.ndarray = None      # bool (H, W) present climate outside the training range (rare)
    check0: np.ndarray = None
    scen: dict = field(default_factory=dict)       # (ssp, period) -> Scenario
    reach: dict = field(default_factory=dict)      # period -> bool (H, W) within reach of the present range
    reach_km: dict = field(default_factory=dict)
    dispersal: dict = field(default_factory=dict)

    @property
    def now(self) -> np.ndarray:
        return self.S0 >= THR7

    def unlimited(self, key) -> np.ndarray:
        return self.scen[key].S >= THR7

    def binary(self, key, mode: str) -> np.ndarray:
        fut = self.unlimited(key)
        if mode == "unlimited":
            return fut
        if mode == "limited":
            return fut & (self.now | self.reach[key[1]])
        if mode == "none":
            return fut & self.now
        raise ValueError(mode)


def row_areas(spec: GridSpec) -> np.ndarray:
    return spec.row_area_km2()


def area_of(mask: np.ndarray, spec: GridSpec) -> float:
    """Area (km2) of a boolean (H, W) mask."""
    return float((mask.sum(1).astype(np.float64) * spec.row_area_km2()).sum())


def _outside(ref_min, ref_max, X):
    return ((X < ref_min) | (X > ref_max)).any(1)


def project_species(fit: Fit, src: ClimateSource, ssps, periods, *, group: str = None, cfg: ProjConfig = ProjConfig(),
                    log=lambda *a: None, only=None) -> Projection:
    """Project `fit` over the present and every (ssp, period). `only` (set of (ssp, period)) restricts the future work (resuming)."""
    spec = fit.spec
    H, W = spec.H, spec.W
    ref_min, ref_max = fit.ref.min(0), fit.ref.max(0)
    mu, P, cut = fit.mahal["loc"], fit.mahal["prec"], fit.mahal["cut"]
    dom = fit.proj
    rows_with = np.nonzero(dom.any(1))[0]
    bands = []
    if len(rows_with):
        for r0 in range(0, H, cfg.band_rows):
            r1 = min(r0 + cfg.band_rows, H)
            if dom[r0:r1].any():
                bands.append((r0, r1))
    S0 = np.zeros((H, W), np.uint8)
    nov0 = np.zeros((H, W), bool)
    chk0 = np.zeros((H, W), bool) if fit.check is not None else None
    for r0, r1 in bands:
        d = dom[r0:r1]
        X = src.baseline_band(r0, r1, fit.pred)[:, d].T.astype(np.float64)
        ok = np.isfinite(X).all(1)
        s = np.zeros(len(X), np.float32)
        if ok.any():
            s[ok] = fit.score(X[ok])
        tmp = np.zeros(d.shape, np.uint8)
        tmp[d] = quantise(s, fit.thr)
        S0[r0:r1] = tmp
        t2 = np.zeros(d.shape, bool)
        t2[d] = ok & _outside(ref_min, ref_max, X)
        nov0[r0:r1] = t2
        if chk0 is not None and ok.any():
            c = np.zeros(len(X), bool)
            c[ok] = fit.check_score(X[ok]) >= fit.check_thr
            t3 = np.zeros(d.shape, bool)
            t3[d] = c
            chk0[r0:r1] = t3
    proj = Projection(spec, fit.thr, S0, nov0, chk0)
    now = proj.now
    rate, note = dispersal_rule(group, cfg.km_per_decade)
    proj.dispersal = dict(km_per_decade=rate, note=note, calibrated=False)
    base_mid = period_mid_year(BASELINE)
    for period in periods:
        km = rate * max(period_mid_year(period) - base_mid, 0.0) / 10.0
        proj.reach_km[period] = km
        cell_km = spec.dlat * 111.2
        f = int(np.clip(km / (4 * cell_km), 1, 6))                  # coarse block no wider than a quarter of the reach
        proj.reach[period] = within_km(now, spec, km, factor=f)
    combos = [(ssp, period) for ssp in ssps for period in periods if only is None or (ssp, period) in only]
    models = list(src.future_models(*combos[0])) if combos else []
    for c in combos[1:]:
        if list(src.future_models(*c)) != models:
            raise ValueError("the climate-model list must be the same for every scenario / period")
    M = len(models)
    # Model-outer loop: a source that has to load a big per-model file (W1's deltas) loads it once per model, not once per band.
    # Only one uint8 (quantised) score per model and domain cell is kept, never a fine-grid float field per model.
    offs = np.cumsum([0] + [int(dom[r0:r1].sum()) for r0, r1 in bands])
    ntot = int(offs[-1])
    chk_models = models[:: max(1, M // max(cfg.check_models, 1))][:cfg.check_models] if fit.check is not None and M else []
    Q = {c: np.zeros((M, ntot), np.uint8) for c in combos}
    NV = {c: np.zeros(ntot, np.int16) for c in combos}
    CQ = {c: np.zeros((len(chk_models), ntot), bool) for c in combos} if chk_models else {}
    mah = {c: [0.0, 0] for c in combos}
    for mi, m in enumerate(models):
        for c in combos:
            ssp, period = c
            for bi, (r0, r1) in enumerate(bands):
                d = dom[r0:r1]
                sl = slice(int(offs[bi]), int(offs[bi + 1]))
                X = src.future_band(ssp, period, m, r0, r1, fit.pred)[:, d].T.astype(np.float64)
                ok = np.isfinite(X).all(1)
                if not ok.any():
                    continue
                q = np.zeros(len(X), np.uint8)
                q[ok] = quantise(fit.score(X[ok]), fit.thr)
                Q[c][mi, sl] = q
                nv = np.zeros(len(X), np.int16)
                nv[ok] = _outside(ref_min, ref_max, X[ok])
                NV[c][sl] += nv
                Z = X[ok] - mu
                dm = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", Z, P, Z), 0))
                mah[c][0] += float((dm > cut).sum())
                mah[c][1] += int(ok.sum())
                if m in chk_models:
                    cs = np.zeros(len(X), bool)
                    cs[ok] = fit.check_score(X[ok]) >= fit.check_thr
                    CQ[c][chk_models.index(m), sl] = cs
        log(f"projected {fit.species} with climate model {m} ({mi + 1}/{M})")
    for c in combos:
        ssp, period = c
        S = np.zeros((H, W), np.uint8)
        A = np.zeros((H, W), np.uint8)
        N = np.zeros((H, W), np.uint8)
        Cc = np.zeros((H, W), bool) if chk_models else None
        for bi, (r0, r1) in enumerate(bands):
            d = dom[r0:r1]
            sl = slice(int(offs[bi]), int(offs[bi + 1]))
            q = Q[c][:, sl]
            med = np.rint(np.median(q, axis=0)).astype(np.uint8)       # monotone in the score, so the median of quantised = quantised median
            agree = (q >= THR7).sum(0)
            vote = (NV[c][sl] >= max(1, int(np.ceil(cfg.novel_vote * M)))).astype(np.uint8)
            for arr, vals in ((S, med), (A, np.rint(15.0 * agree / M).astype(np.uint8)), (N, vote)):
                t = np.zeros(d.shape, np.uint8)
                t[d] = vals
                arr[r0:r1] = t
            if Cc is not None:
                t = np.zeros(d.shape, bool)
                t[d] = np.median(CQ[c][:, sl], axis=0) >= 0.5
                Cc[r0:r1] = t
        proj.scen[c] = Scenario(ssp, period, M, S, A, N, Cc, mah[c][0] / mah[c][1] if mah[c][1] else float("nan"))
        log(f"projected {fit.species} {ssp} {period}: {M} models, suitable {area_of(S >= THR7, spec):.3e} km2")
    return proj


def range_stats(spec: GridSpec, now: np.ndarray, fut: np.ndarray) -> dict:
    """Areas, change, centroid shift and bearing, gain / loss / stable (km2) for two boolean (H, W) ranges (via sdm.summarise)."""
    u = now | fut
    r, c = np.nonzero(u)
    if len(r) == 0:
        return dict(area_now=0.0, area_fut=0.0, change_pct=float("nan"), centroid_now=(float("nan"),) * 2, centroid_fut=(float("nan"),) * 2,
                    shift_km=float("nan"), bearing=float("nan"), gain=0.0, loss=0.0, stable=0.0)
    return sdm.summarise(spec.lat(r), spec.lon(c), spec.row_area_km2()[r], now[r, c], fut[r, c])
