"""Production fitting pipeline of the species pilot (W3): records + climate -> a fitted, cross-validated suitability model.

Design (each choice is justified by a measured result in docs/spikes/F-sdm-engine.md):
  * predictors   an ecologically ordered list, pruned greedily at |Spearman r| > 0.7 against variables already kept (F E3: raw / all
                 variables degrade the future range; blind pruning can drop a true driver, so the order is biological and every drop
                 is recorded with the variable that caused it).
  * main model   LightGBM (F E4: as good as the 4-model ensemble). Check model: penalised-spline GAM (transparent response curves);
                 its disagreement with the main model is a flag, not a vote.
  * background   cells sampled in proportion to the target-group record density inside the accessible area (F E2: area-change error
                 10 -> 2 points under moderate sampling bias), with a small uniform share so no cell has zero chance.
  * validation   spatial-block cross-validation; AUC (held-out presences vs held-out target-group background), TSS, Boyce, domain AUC.
  * threshold    p05 of the out-of-fold presence scores (F: TSS 0.94, 2100 area error 1.9 points; `minpres` is unusable).
  * accessible   native range (W2) plus a buffer for training, a larger buffer for projection; never the rest of the globe.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from scipy import stats

from . import sdm
from .grid import GridSpec, ClimateSource, Occurrences, land_mask, within_km, PREDICTORS

# Priority order, most to least biologically informative for range limits (mean temperature, cold limit, heat limit, water balance,
# annual rain, then dry-season rain, rain seasonality, temperature seasonality, actual evapotranspiration, growing degree days).
DEFAULT_PRIORITY = ("bio1", "bio6", "bio5", "cwd", "bio12", "bio17", "bio15", "bio4", "aet", "gdd")
GROUP_PRIORITY = {
    "tree": ("bio6", "bio1", "cwd", "bio5", "bio12", "bio17", "gdd", "bio15", "bio4", "aet"),
    "crop": ("gdd", "bio6", "cwd", "bio1", "bio5", "bio12", "bio17", "bio15", "bio4", "aet"),
    "insect_arachnid": ("bio6", "bio1", "bio5", "cwd", "bio12", "gdd", "bio17", "bio15", "bio4", "aet"),
}


@dataclass(frozen=True)
class FitConfig:
    priority: tuple = DEFAULT_PRIORITY
    corr_thr: float = 0.7
    max_pred: int = 5
    min_pred: int = 2
    n_pres_max: int = 20000          # presences used per fit (random subset above this)
    n_bg_min: int = 10000
    n_bg_max: int = 50000
    bg_per_pres: float = 3.0
    tg_floor: float = 0.05           # share of the background drawn uniformly over the accessible area
    bias: str = "target_group"       # or "uniform"
    cv_folds: int = 5
    block_km: float = None           # None = automatic from the extent of the records, 100 to 400 km
    threshold: str = "p05"
    train_buffer_km: float = 300.0
    proj_buffer_km: float = 1000.0
    no_native_buffer_km: float = 500.0    # extra training buffer when no native-range mask exists (records only)
    n_eval: int = 10000
    allow_flags: int = 0             # record flag bits that are tolerated; any other bit excludes the record
    check_model: bool = True
    gate_cell_deg: float = 0.125     # records are counted per cell of this size for the record-count gate (F counted 15 km cells)
    seed: int = 0
    n_jobs: int = 1


def priority_for(group: str, cfg: FitConfig = FitConfig()) -> tuple:
    return GROUP_PRIORITY.get(group, cfg.priority) if cfg.priority == DEFAULT_PRIORITY else cfg.priority


# --------------------------------------------------------------------------- helpers
def grid_at(arr: np.ndarray, spec: GridSpec, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Values of a global grid (possibly coarser than `spec`, row 0 north) at fine-grid cells, without resampling the whole array."""
    h, w = arr.shape
    if (h, w) == (spec.H, spec.W):
        return arr[rows, cols]
    return arr[np.minimum((rows + 0.5) * h / spec.H, h - 1).astype(int), np.minimum((cols + 0.5) * w / spec.W, w - 1).astype(int)]


def spearman_matrix(X: np.ndarray) -> np.ndarray:
    R = np.apply_along_axis(stats.rankdata, 0, X)
    return np.abs(np.corrcoef(R.T))


def select_predictors(X_ref: np.ndarray, names, priority, thr: float = 0.7, max_pred: int = 5):
    """Greedy collinearity pruning in biological priority order on reference (accessible-area) climate. Returns (kept, report) where
    report lists every dropped variable with the kept variable that correlated with it and the correlation, or 'cap' if the
    maximum number was reached."""
    names = list(names)
    order = [n for n in priority if n in names] + [n for n in names if n not in priority]
    rho = spearman_matrix(X_ref)
    kept, dropped = [], {}
    for n in order:
        j = names.index(n)
        if len(kept) >= max_pred:
            dropped[n] = dict(reason="cap")
            continue
        clash = [(k, rho[j, names.index(k)]) for k in kept if rho[j, names.index(k)] > thr]
        if clash:
            k, r = max(clash, key=lambda t: t[1])
            dropped[n] = dict(reason="correlated", with_=k, rho=round(float(r), 3))
        else:
            kept.append(n)
    return kept, dropped


def auto_block_km(km_xy: np.ndarray, lo: float = 100.0, hi: float = 400.0) -> float:
    ext = max(np.ptp(km_xy[:, 0]), np.ptp(km_xy[:, 1])) if len(km_xy) else hi
    return float(np.clip(ext / 6.0, lo, hi))


def prepare_records(occ: Occurrences, spec: GridSpec, cfg: FitConfig) -> dict:
    """Clean record list -> unique cells. Returns dict(rc (k,2), n_raw, n_flagged, n_cells, n_gate) where n_gate counts distinct
    cells of `gate_cell_deg` (the unit of the minimum-records gate)."""
    n_raw = len(occ.rows)
    ok = (occ.flags & ~cfg.allow_flags) == 0
    o = occ.select(ok)
    rc = o.unique_cells()
    f = spec.coarse_factor(cfg.gate_cell_deg)
    n_gate = len(np.unique(rc[:, 0] // f * (spec.W // f + 2) + rc[:, 1] // f)) if len(rc) else 0
    return dict(rc=rc, n_raw=n_raw, n_flagged=int(n_raw - ok.sum()), n_cells=len(rc), n_gate=int(n_gate))


def domains(spec: GridSpec, land: np.ndarray, rc: np.ndarray, native: np.ndarray, cfg: FitConfig):
    """(train, proj) boolean masks. train = native range + train_buffer (land); proj = native range + proj_buffer. Without a native
    mask the record cells stand in for the range with a wider training buffer (and are inside both). With a native mask, records
    outside native + buffer are not part of the domain; fit_species drops them (counted as n_outside_domain)."""
    rec = np.zeros((spec.H, spec.W), bool)
    rec[rc[:, 0], rc[:, 1]] = True
    if native is not None:
        base = np.zeros((spec.H, spec.W), bool)
        base |= (native if native.shape == (spec.H, spec.W) else _resample_bool(native, spec))
        tb = cfg.train_buffer_km
    else:
        base = rec
        tb = max(cfg.train_buffer_km, cfg.no_native_buffer_km)
    train = within_km(base, spec, tb) & land
    proj = within_km(base, spec, max(cfg.proj_buffer_km, tb)) & land
    if native is None:
        train, proj = train | rec, proj | rec
    return train, proj


def _resample_bool(m, spec):
    from .grid import resample
    return resample(m.astype(np.uint8), spec).astype(bool)


def sample_cells(domain: np.ndarray, weight_fn, n: int, rng: np.random.Generator, floor: float = 0.0):
    """Draw n cells (with replacement) from `domain` with probability proportional to weight_fn(rows, cols), mixed with `floor` of
    uniform probability. weight_fn None = uniform. Returns (rows, cols)."""
    r, c = np.nonzero(domain)
    if len(r) == 0:
        return r, c
    if weight_fn is None:
        p = np.full(len(r), 1.0 / len(r))
    else:
        w = np.nan_to_num(np.asarray(weight_fn(r, c), float), nan=0.0)
        w = np.clip(w, 0, None)
        p = (1 - floor) * w / w.sum() + floor / len(r) if w.sum() > 0 else np.full(len(r), 1.0 / len(r))
    cum = np.cumsum(p)
    idx = np.minimum(np.searchsorted(cum, rng.random(n) * cum[-1]), len(r) - 1)
    return r[idx], c[idx]


# --------------------------------------------------------------------------- cross-validation
def _pct(ref_sorted: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.searchsorted(ref_sorted, x, "right") / len(ref_sorted)


def cross_validate(Xp, Xb, kmp, kmb, Xe, kme, block_km, cfg: FitConfig):
    """Spatial-block CV of the LightGBM main model and the GAM check model. Returns dict with per-model metric means
    (auc, tss, boyce, auc_dom), the out-of-fold LightGBM scores at presences / background, and folds_used."""
    allkm = np.vstack([kmp, kmb])
    X = np.vstack([Xp, Xb])
    y = np.r_[np.ones(len(Xp), int), np.zeros(len(Xb), int)]
    fold = sdm.block_folds(allkm, block_km, cfg.cv_folds, y.astype(float), cfg.seed)
    fold_e = sdm.block_folds_like(kme, allkm, fold, block_km)
    algos = ("gbm", "gam") if cfg.check_model else ("gbm",)
    rec = {a: dict(auc=[], tss=[], boyce=[], auc_dom=[]) for a in algos}
    oof = np.full(len(y), np.nan)
    used = 0
    for f in range(cfg.cv_folds):
        te, tr = fold == f, fold != f
        if (te & (y == 1)).sum() < 3 or (tr & (y == 1)).sum() < 10 or (te & (y == 0)).sum() < 3:
            continue
        used += 1
        ev = np.nonzero(fold_e == f)[0]
        ev = ev[:: max(1, len(ev) // 3000)]
        for a in algos:
            m = sdm.MODELS[a](seed=cfg.seed + 100 * f, n_jobs=cfg.n_jobs).fit(X[tr], y[tr])
            s_te, s_tr = m.raw(X[te]), m.raw(X[tr])
            yte, ytr = y[te], y[tr]
            rec[a]["auc"].append(sdm.auc(s_te[yte == 1], s_te[yte == 0]))
            rec[a]["tss"].append(sdm.tss(s_te[yte == 1], s_te[yte == 0], sdm.best_threshold(s_tr[ytr == 1], s_tr[ytr == 0])))
            if len(ev):
                ref = np.sort(m.raw(Xe))                          # percentile scale over the whole evaluation sample
                s_ev = m.raw(Xe[ev])
                rec[a]["boyce"].append(sdm.boyce(_pct(ref, s_te[yte == 1]), _pct(ref, s_ev)))
                rec[a]["auc_dom"].append(sdm.auc(s_te[yte == 1], s_ev))
            if a == "gbm":
                oof[te] = s_te
    mean = lambda v: float(np.nanmean(v)) if len(v) and not np.all(np.isnan(v)) else float("nan")      # noqa: E731
    out = {a: {k: mean(v) for k, v in r.items()} for a, r in rec.items()}
    ok = ~np.isnan(oof)
    return dict(metrics=out, oof_pos=oof[ok & (y == 1)], oof_bg=oof[ok & (y == 0)], folds_used=used, folds=cfg.cv_folds, block_km=block_km)


# --------------------------------------------------------------------------- the fit
@dataclass
class Fit:
    species: str
    spec: GridSpec
    pred: list                       # selected predictor names (column order of every X below)
    selection: dict                  # kept / dropped report
    model: object                    # sdm.GBM
    check: object                    # sdm.GAM or None
    thr: float
    thr_all: dict
    cv: dict
    records: dict                    # counts
    ref: np.ndarray                  # training predictors (presence + background) for MESS / Mahalanobis
    mahal: dict                      # location, precision, cutoff
    check_thr: float = None          # threshold of the GAM check model (5th percentile of its presence scores)
    train: np.ndarray = field(repr=False, default=None)
    proj: np.ndarray = field(repr=False, default=None)
    pres_rc: np.ndarray = field(repr=False, default=None)
    cfg: FitConfig = FitConfig()
    note: dict = field(default_factory=dict)

    def score(self, X: np.ndarray, chunk: int = 2_000_000) -> np.ndarray:
        """LightGBM suitability in [0, 1] (float32)."""
        return _batched(self.model.raw, X, chunk)

    def check_score(self, X: np.ndarray, chunk: int = 1_000_000) -> np.ndarray:
        return _batched(self.check.raw, X, chunk)

    def set_jobs(self, n_jobs: int):
        self.cfg = FitConfig(**{**self.cfg.__dict__, "n_jobs": n_jobs})
        try:
            self.model.m.set_params(n_jobs=n_jobs)
        except Exception:
            pass


def _batched(fn, X, chunk):
    if len(X) == 0:
        return np.zeros(0, np.float32)
    return np.concatenate([fn(X[i:i + chunk]) for i in range(0, len(X), chunk)]).astype(np.float32)


def fit_species(name: str, spec: GridSpec, src: ClimateSource, occ: Occurrences, *, land: np.ndarray = None,
                native: np.ndarray = None, density: np.ndarray = None, group: str = None, cfg: FitConfig = FitConfig(),
                log=lambda *a: None) -> Fit:
    """Fit one species. `native` is the native-range mask (bool, global grid, may be coarser), `density` the target-group record
    density for the species' group (float, global grid, may be coarser; None or cfg.bias == 'uniform' gives a uniform background)."""
    rng = np.random.default_rng(cfg.seed)
    land = land_mask(src) if land is None else land
    rec = prepare_records(occ, spec, cfg)
    rc = rec.pop("rc")
    train, proj = domains(spec, land, rc, native, cfg)
    names = list(src.names)
    inside = train[rc[:, 0], rc[:, 1]]
    rec["n_outside_domain"] = int((~inside).sum())
    rc = rc[inside]
    # presences on cells with data
    P_all = src.baseline_points(rc[:, 0], rc[:, 1], names)
    okp = np.isfinite(P_all).all(1)
    rc, P_all = rc[okp], P_all[okp]
    rec["n_no_climate"] = int((~okp).sum())
    if len(rc) > cfg.n_pres_max:
        keep = np.sort(rng.choice(len(rc), cfg.n_pres_max, replace=False))
        rc, P_all = rc[keep], P_all[keep]
    rec["n_used"] = len(rc)
    n_bg = int(np.clip(cfg.bg_per_pres * len(rc), cfg.n_bg_min, cfg.n_bg_max))
    wfn = None
    if cfg.bias == "target_group" and density is not None:
        wfn = lambda r, c: grid_at(density, spec, r, c)                      # noqa: E731
    br, bc = sample_cells(train, wfn, n_bg, rng, cfg.tg_floor if wfn else 0.0)
    er, ec = sample_cells(train, None, cfg.n_eval, rng)                       # uniform reference / evaluation cells
    B_all = src.baseline_points(br, bc, names)
    E_all = src.baseline_points(er, ec, names)
    okb, oke = np.isfinite(B_all).all(1), np.isfinite(E_all).all(1)
    br, bc, B_all = br[okb], bc[okb], B_all[okb]
    er, ec, E_all = er[oke], ec[oke], E_all[oke]
    rec["n_bg"] = len(br)
    # predictors
    kept, dropped = select_predictors(E_all, names, priority_for(group, cfg), cfg.corr_thr, cfg.max_pred)
    if len(kept) < cfg.min_pred:
        kept = [n for n in priority_for(group, cfg) if n in names][:cfg.min_pred]
    ix = [names.index(n) for n in kept]
    Xp, Xb, Xe = P_all[:, ix].astype(float), B_all[:, ix].astype(float), E_all[:, ix].astype(float)
    log(f"{name}: {len(Xp)} presences, {len(Xb)} background, predictors {kept}")
    kmp, kmb, kme = spec.km_xy(rc[:, 0], rc[:, 1]), spec.km_xy(br, bc), spec.km_xy(er, ec)
    block_km = cfg.block_km or auto_block_km(kmp)
    cv = cross_validate(Xp, Xb, kmp, kmb, Xe, kme, block_km, cfg) if len(Xp) >= 20 else dict(
        metrics={"gbm": dict(auc=np.nan, tss=np.nan, boyce=np.nan, auc_dom=np.nan)}, oof_pos=np.zeros(0), oof_bg=np.zeros(0), folds_used=0,
        folds=cfg.cv_folds, block_km=block_km)
    X = np.vstack([Xp, Xb])
    y = np.r_[np.ones(len(Xp), int), np.zeros(len(Xb), int)]
    model = sdm.GBM(seed=cfg.seed, n_jobs=cfg.n_jobs).fit(X, y)
    check = sdm.GAM(seed=cfg.seed).fit(X, y) if cfg.check_model and len(Xp) >= 20 else None
    if len(cv["oof_pos"]) >= 5:
        pos, neg = cv["oof_pos"], cv["oof_bg"]
        thr_src = "out-of-fold"
    else:
        s = model.raw(X)
        pos, neg = s[y == 1], s[y == 0]
        thr_src = "in-sample"
    thr_all = {m: sdm.threshold(pos, neg, m) for m in sdm.THRESHOLDS}
    check_thr = None
    if check is not None:
        sc = check.raw(X)
        check_thr = float(np.quantile(sc[y == 1], 0.05))
    from sklearn.covariance import LedoitWolf
    lw = LedoitWolf().fit(X)
    d = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", X - lw.location_, lw.precision_, X - lw.location_), 0))
    mahal = dict(loc=lw.location_, prec=lw.precision_, cut=float(np.quantile(d, 0.999)))
    return Fit(name, spec, kept, dict(kept=kept, dropped=dropped, considered=names), model, check, thr_all[cfg.threshold], thr_all, cv, rec,
               X, mahal, check_thr, train, proj, rc, cfg, dict(threshold_source=thr_src, threshold_method=cfg.threshold, group=group))
