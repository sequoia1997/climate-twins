"""Species distribution modelling engine (spike F).

Presence records and a background sample go in; an ensemble of presence-background models, spatial-block cross-validation,
a presence threshold, extrapolation flags (MESS), dispersal-bounded projection and range-shift summaries come out.
Everything is deterministic given the seed. It is tested on virtual species (virtual.py), so the accuracy numbers in
docs/spikes/F-sdm-engine.md are measured against known truth.

Conventions: climate predictors are (n_cells, n_pred) float arrays; "cells" are rows of a virtual.Grid; models return a
raw score and the ensemble works on *domain percentile scores* in [0, 1] (the share of present-day domain cells that
score lower, per model, fixed at fit time), so a future cell hotter than any present cell can score above everything
today without the scale moving.

Models: glm (quadratic logistic), gam (penalised spline logistic), maxent (L1-penalised logistic on hinge, linear and
quadratic features, a Maxent-like model), gbm (LightGBM), rf (down-sampled random forest) and mahal (Mahalanobis
distance from the presence centroid in climate space; the sigma machinery of the twin search, presence-only).
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
import warnings
import numpy as np
from scipy import stats
from scipy.spatial import cKDTree

from .. import common as C

ALGOS = ("glm", "gam", "maxent", "gbm", "rf", "mahal")
THRESHOLDS = ("maxtss", "p10", "p05", "minpres")


@dataclass(frozen=True)
class Settings:
    """Pipeline settings (the recommended defaults, justified in docs/spikes/F-sdm-engine.md)."""
    algos: tuple = ("gam", "maxent", "gbm", "rf")
    n_bg: int = 10000
    threshold: str = "p10"
    cv: bool = True
    cv_folds: int = 5
    block_km: float = 400.0
    min_auc: float = 0.6               # a model whose spatial-CV AUC is lower is dropped from the ensemble
    n_ref: int = 20000                 # cells used for each model's percentile reference
    seed: int = 0
    n_jobs: int = 1


# --------------------------------------------------------------------------- metrics
def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Area under the ROC curve (Mann-Whitney U), ties count half."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = stats.rankdata(np.concatenate([pos, neg]))
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def best_threshold(pos: np.ndarray, neg: np.ndarray) -> float:
    """Threshold maximising sensitivity + specificity (max TSS) of pos vs neg scores."""
    cand = np.unique(np.concatenate([pos, neg]))
    if len(cand) > 400:
        cand = np.quantile(np.concatenate([pos, neg]), np.linspace(0, 1, 401))
    sens = (pos[None, :] >= cand[:, None]).mean(1)
    spec = (neg[None, :] < cand[:, None]).mean(1)
    return float(cand[np.argmax(sens + spec)])


def tss(pos: np.ndarray, neg: np.ndarray, thr: float) -> float:
    """True skill statistic sensitivity + specificity - 1 at threshold thr."""
    return float((pos >= thr).mean() + (neg < thr).mean() - 1)


def threshold(pos: np.ndarray, neg: np.ndarray, method: str = "p10") -> float:
    """Presence threshold from scores at (preferably out-of-fold) presences and background:
    maxtss (best TSS), p10 / p05 (10th / 5th percentile of presence scores: omits the 10% / 5% least typical records, which is
    robust to false positives), minpres (lowest presence score)."""
    if method == "maxtss":
        return best_threshold(pos, neg)
    if method == "p10":
        return float(np.quantile(pos, 0.10))
    if method == "p05":
        return float(np.quantile(pos, 0.05))
    if method == "minpres":
        return float(pos.min())
    raise ValueError(method)


def boyce(pres: np.ndarray, allcells: np.ndarray, nbins: int = 100, width: float = 0.1) -> float:
    """Continuous Boyce index (Hirzel et al. 2006) of presence scores against the scores of all available cells:
    Spearman correlation between the predicted-to-expected frequency ratio and the score, over moving windows. In [-1, 1];
    near 1 = presences sit where the score is high. Scores must be in [0, 1]."""
    if len(pres) < 5:
        return float("nan")
    ps, es = np.sort(pres), np.sort(allcells)
    lo = np.linspace(0, 1 - width, nbins)
    hi = lo + width
    P = (np.searchsorted(ps, hi, "right") - np.searchsorted(ps, lo, "left")) / len(ps)
    E = (np.searchsorted(es, hi, "right") - np.searchsorted(es, lo, "left")) / len(es)
    ok = E > 0
    if ok.sum() < 5:
        return float("nan")
    f = P[ok] / E[ok]
    if np.ptp(f) == 0:
        return float("nan")
    return float(stats.spearmanr(f, (lo[ok] + hi[ok]) / 2)[0])


def range_agreement(pred: np.ndarray, truth: np.ndarray, area: np.ndarray) -> dict:
    """Agreement of a predicted and a true range (bool per cell): area-weighted sensitivity, specificity, TSS,
    Sorensen overlap, area ratio (predicted / true) and commission / omission shares of the true range."""
    a = area
    tp, fp = a[pred & truth].sum(), a[pred & ~truth].sum()
    fn, tn = a[~pred & truth].sum(), a[~pred & ~truth].sum()
    sens, spec = tp / max(tp + fn, 1e-9), tn / max(tn + fp, 1e-9)
    return dict(sens=float(sens), spec=float(spec), tss=float(sens + spec - 1), sorensen=float(2 * tp / max(2 * tp + fp + fn, 1e-9)),
                area_ratio=float((tp + fp) / max(tp + fn, 1e-9)), commission=float(fp / max(tp + fn, 1e-9)), omission=float(fn / max(tp + fn, 1e-9)))


# --------------------------------------------------------------------------- spatial blocks and cross-validation
def block_folds(km: np.ndarray, block_km: float, k: int, weights: np.ndarray, seed: int = 0) -> np.ndarray:
    """Assign every point (planar km coordinates) to one of k folds by square spatial blocks of side block_km. Blocks go
    to folds greedily, heaviest first (weights = presences, so folds hold similar numbers of presences), with random
    tie-breaking. Returns fold index per point."""
    bx, by = np.floor(km[:, 0] / block_km).astype(int), np.floor(km[:, 1] / block_km).astype(int)
    key = bx * 100003 + by
    u, inv = np.unique(key, return_inverse=True)
    wt = np.bincount(inv, weights)
    rng = np.random.default_rng(seed)
    order = np.lexsort((rng.random(len(u)), -wt))
    load = np.zeros(k)
    fold_of_block = np.zeros(len(u), int)
    for b in order:
        f = int(np.argmin(load + rng.random(k) * 1e-6))
        fold_of_block[b] = f
        load[f] += wt[b] + 1e-3                      # empty blocks still spread out
    return fold_of_block[inv]


class _Model:
    """Common wrapper: fit(X, y) with y 1 = presence, 0 = background; raw(X) -> higher means more suitable."""
    name = ""

    def __init__(self, seed=0, n_jobs=1):
        self.seed, self.n_jobs = seed, n_jobs


class _Sk(_Model):
    def fit(self, X, y):
        self.m = self._build()
        self.m.fit(X, y)
        return self

    def raw(self, X):
        return self.m.predict_proba(X)[:, 1] if hasattr(self.m, "predict_proba") else self.m.decision_function(X)


def _balanced_sw(y):
    w = np.where(y == 1, 1.0, y.sum() / max((y == 0).sum(), 1))
    return w * len(y) / w.sum()


def _quad(X):
    """Linear + squared terms, no interactions (a response curve per variable)."""
    return np.hstack([X, X ** 2])


class GLM(_Sk):
    """Logistic regression on linear and quadratic terms (the classic niche-response-curve model)."""
    name = "glm"

    def _build(self):
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler, FunctionTransformer
        from sklearn.linear_model import LogisticRegression
        return make_pipeline(StandardScaler(), FunctionTransformer(_quad), LogisticRegression(C=1.0, class_weight="balanced", max_iter=500))


class GAM(_Sk):
    """Penalised spline logistic regression: a smooth additive response curve per variable (cubic B-splines, 6 knots,
    ridge penalty; flat beyond the training range)."""
    name = "gam"

    def _build(self):
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import SplineTransformer, StandardScaler
        from sklearn.linear_model import LogisticRegression
        return make_pipeline(StandardScaler(), SplineTransformer(n_knots=6, degree=3, extrapolation="constant"),
                             LogisticRegression(C=0.2, class_weight="balanced", max_iter=1000))


class Maxent(_Model):
    """Maxent-like: L1-penalised logistic regression on linear, quadratic and hinge features with background weighted to
    equal the presences (the equivalence of Maxent and an infinitely weighted Poisson model; Renner & Warton 2013)."""
    name = "maxent"

    def _feat(self, X):
        Z = (X - self.mu) / self.sd
        F = [Z, Z ** 2]
        for j in range(Z.shape[1]):
            F.append(np.clip(Z[:, [j]] - self.knots[j][None, :], 0, None) / self.span[j])
        return np.hstack(F)

    def fit(self, X, y):
        from sklearn.linear_model import LogisticRegression
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.knots = [np.quantile(Z[:, j], np.linspace(0.1, 0.9, 7)) for j in range(Z.shape[1])]
        self.span = np.ptp(Z, 0) + 1e-9
        self.m = LogisticRegression(penalty="l1", solver="liblinear", C=0.08, class_weight="balanced", max_iter=300)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.m.fit(self._feat(X), y)
        return self

    def raw(self, X):
        return self.m.decision_function(self._feat(X))


class GBM(_Model):
    """LightGBM, small regularised trees (8 leaves, 150 rounds, learning rate 0.05, bagging), balanced classes."""
    name = "gbm"

    def fit(self, X, y):
        import lightgbm as lgb
        self.m = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.05, num_leaves=8, min_child_samples=20, subsample=0.7,
                                    subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, class_weight="balanced",
                                    random_state=self.seed, n_jobs=self.n_jobs, verbose=-1)
        self.m.fit(X, y)
        return self

    def raw(self, X):
        return self.m.predict_proba(X)[:, 1]


class RF(_Model):
    """Random forest, 200 trees, min leaf 10, balanced subsampling (the down-sampled RF recommended for presence-background data)."""
    name = "rf"

    def fit(self, X, y):
        from sklearn.ensemble import RandomForestClassifier
        self.m = RandomForestClassifier(n_estimators=200, min_samples_leaf=10, max_features="sqrt", class_weight="balanced_subsample",
                                        random_state=self.seed, n_jobs=self.n_jobs)
        self.m.fit(X, y)
        return self

    def raw(self, X):
        return self.m.predict_proba(X)[:, 1]


class Mahal(_Model):
    """Mahalanobis niche model: distance of a cell's climate from the centroid of the presence climates (shrunk covariance,
    5% most distant records trimmed once so false positives do not inflate the niche). Presence-only; the distance is
    the same quantity as the twin search's, and `sigma(X)` expresses it in the site's sigma units."""
    name = "mahal"

    def _d(self, X):
        Z = X - self.mu
        return np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", Z, self.P, Z), 0))

    def fit(self, X, y):
        from sklearn.covariance import LedoitWolf
        Xp = X[y == 1]
        self.k = X.shape[1]
        keep = np.ones(len(Xp), bool)
        for _ in range(2):
            lw = LedoitWolf().fit(Xp[keep])
            self.mu, self.P = lw.location_, lw.precision_
            d = self._d(Xp)
            keep = d <= np.quantile(d, 0.95)
        return self

    def raw(self, X):
        return -self._d(X)

    def sigma(self, X):
        """Distance in the site's sigma units (percentile of the chi distribution re-expressed as a half-normal z)."""
        return C.chi_to_sigma(self._d(X), self.k)


MODELS = {"glm": GLM, "gam": GAM, "maxent": Maxent, "gbm": GBM, "rf": RF, "mahal": Mahal}


# --------------------------------------------------------------------------- ensemble
@dataclass
class Ensemble:
    """Fitted models plus their present-day percentile references. `score(X)` -> ensemble score in [0, 1]."""
    names: tuple
    models: list
    refs: list                          # sorted raw scores of reference cells, per model
    weights: np.ndarray

    def raw(self, X: np.ndarray) -> np.ndarray:
        """(n, n_models) raw scores."""
        return np.stack([m.raw(X) for m in self.models], 1)

    def percentile(self, X: np.ndarray) -> np.ndarray:
        """(n, n_models) domain-percentile scores in [0, 1]."""
        R = self.raw(X)
        return np.stack([np.searchsorted(r, R[:, j], "right") / len(r) for j, r in enumerate(self.refs)], 1)

    def score(self, X: np.ndarray, per_model: bool = False):
        P = self.percentile(X)
        s = P @ self.weights
        return (s, P) if per_model else s


def fit_ensemble(X: np.ndarray, y: np.ndarray, X_ref: np.ndarray, algos=("gam", "maxent", "gbm", "rf"), seed: int = 0,
                 weights: dict = None, n_jobs: int = 1) -> Ensemble:
    """Fit each algorithm on (X, y) and build percentile references on X_ref (present-day cells of the domain). Weights are
    equal unless a {algo: weight} dict is given."""
    models = [MODELS[a](seed=seed + i, n_jobs=n_jobs).fit(X, y) for i, a in enumerate(algos)]
    refs = [np.sort(m.raw(X_ref)) for m in models]
    w = np.array([1.0 if weights is None else weights.get(a, 0.0) for a in algos])
    return Ensemble(tuple(algos), models, refs, w / w.sum())


def select_uncorrelated(X: np.ndarray, names, thr: float = 0.7, priority=None) -> list:
    """Greedy collinearity filter: walk the variables in `priority` order (default the given order) and keep one unless
    its absolute Spearman correlation with an already kept variable exceeds thr. Returns kept names."""
    names = list(names)
    order = [names.index(p) for p in (priority or names)]
    rho = np.abs(stats.spearmanr(X)[0])
    kept = []
    for j in order:
        if all(rho[j, k] <= thr for k in kept):
            kept.append(j)
    return [names[j] for j in kept]


def vif(X: np.ndarray) -> np.ndarray:
    """Variance inflation factor of each column (1 = independent; above ~5-10 = collinear)."""
    Z = (X - X.mean(0)) / (X.std(0) + 1e-12)
    R = np.corrcoef(Z.T)
    return np.diag(np.linalg.inv(R + 1e-9 * np.eye(len(R))))


# --------------------------------------------------------------------------- extrapolation
def mess(ref: np.ndarray, X: np.ndarray):
    """Multivariate environmental similarity surface (Elith et al. 2010). ref: (m, p) reference climates (training points);
    X: (n, p). Returns (mess, most_dissimilar_variable): negative MESS = at least one predictor outside the reference range
    (novel climate); the value is the worst univariate similarity in percent."""
    sim = np.empty(X.shape, float)
    for j in range(X.shape[1]):
        r = np.sort(ref[:, j])
        mn, mx = r[0], r[-1]
        f = np.searchsorted(r, X[:, j], "right") / len(r) * 100
        x = X[:, j]
        s = np.where(f <= 50, 2 * f, 2 * (100 - f))
        s = np.where(x < mn, (x - mn) / max(mx - mn, 1e-12) * 100, s)
        s = np.where(x > mx, (mx - x) / max(mx - mn, 1e-12) * 100, s)
        sim[:, j] = s
    return sim.min(1), sim.argmin(1)


def mahal_novelty(ref: np.ndarray, X: np.ndarray, q: float = 0.999):
    """Multivariate novelty: Mahalanobis distance of each row of X from the reference cloud, and a flag for distances beyond
    the q-quantile of the reference's own distances. Catches climate *combinations* never seen even when every variable is in range."""
    from sklearn.covariance import LedoitWolf
    lw = LedoitWolf().fit(ref)
    f = lambda A: np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", A - lw.location_, lw.precision_, A - lw.location_), 0))   # noqa: E731
    cut = np.quantile(f(ref), q)
    d = f(X)
    return d, d > cut


# --------------------------------------------------------------------------- dispersal and summaries
def dispersal_limit(xyz: np.ndarray, now: np.ndarray, suitable: np.ndarray, km: float = None) -> np.ndarray:
    """Cells a species can occupy in the future given dispersal. now: present range (bool); suitable: future suitable (bool).
    km None -> unlimited (all suitable cells); km 0 -> none (suitable cells it already occupies); km > 0 -> suitable cells
    within km of the present range (great-circle). Cells of the present range that stop being suitable are lost in every mode."""
    if km is None:
        return suitable.copy()
    if km <= 0 or not now.any():
        return suitable & now
    d, _ = cKDTree(xyz[now]).query(xyz)
    return suitable & (d * C.R_EARTH <= km)


def centroid(lat: np.ndarray, lon: np.ndarray, area: np.ndarray, sel: np.ndarray):
    """Area-weighted centroid (lat, lon) of the selected cells via the mean unit vector; (nan, nan) if empty."""
    if not sel.any():
        return float("nan"), float("nan")
    v = (C.unit_xyz(lat[sel], lon[sel]) * area[sel, None]).sum(0)
    return float(np.degrees(np.arctan2(v[2], np.hypot(v[0], v[1])))), float(np.degrees(np.arctan2(v[1], v[0])))


def bearing(lat1, lon1, lat2, lon2) -> float:
    """Initial great-circle bearing in degrees clockwise from north (0-360)."""
    p1, p2, dl = np.radians(lat1), np.radians(lat2), np.radians(lon2 - lon1)
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return float((np.degrees(np.arctan2(y, x)) + 360) % 360)


def summarise(lat, lon, area, now: np.ndarray, fut: np.ndarray) -> dict:
    """Range summary: areas (km2), change %, centroids, centroid shift (km) and bearing, gain / loss / stable area."""
    a0, a1 = float(area[now].sum()), float(area[fut].sum())
    c0, c1 = centroid(lat, lon, area, now), centroid(lat, lon, area, fut)
    ok = np.isfinite(c0[0]) and np.isfinite(c1[0])
    return dict(area_now=a0, area_fut=a1, change_pct=(a1 / a0 - 1) * 100 if a0 else float("nan"),
                centroid_now=c0, centroid_fut=c1,
                shift_km=float(C.haversine_km(c0[0], c0[1], c1[0], c1[1])) if ok else float("nan"),
                bearing=bearing(*c0, *c1) if ok else float("nan"),
                gain=float(area[fut & ~now].sum()), loss=float(area[now & ~fut].sum()), stable=float(area[now & fut].sum()))


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, degrees (0-180)."""
    d = abs(a - b) % 360
    return float(min(d, 360 - d))


# --------------------------------------------------------------------------- cross-validation and the pipeline
@dataclass
class CVResult:
    per_algo: dict                      # algo -> dict(auc, tss, boyce) means over folds
    ensemble: dict                      # same for the ensemble of algorithms that pass min_auc
    oof_pos: np.ndarray                 # out-of-fold ensemble scores at presences
    oof_bg: np.ndarray
    kept: tuple                         # algorithms passing min_auc
    folds_used: int


def spatial_cv(Xp: np.ndarray, Xb: np.ndarray, km_p: np.ndarray, km_b: np.ndarray, X_ref: np.ndarray, X_eval: np.ndarray, km_eval: np.ndarray,
               s: Settings) -> CVResult:
    """Spatial-block cross-validation. Blocks of s.block_km are dealt into s.cv_folds folds (balanced by presences); each fold
    is held out in turn, the ensemble refit on the rest, and AUC (held-out presences vs held-out background), TSS (threshold
    chosen on the training fold) and the Boyce index (held-out presences vs sampled cells of the held-out blocks) computed.
    Folds with fewer than 3 presences are skipped."""
    allkm = np.vstack([km_p, km_b])
    X = np.vstack([Xp, Xb])
    y = np.r_[np.ones(len(Xp), int), np.zeros(len(Xb), int)]
    fold = block_folds(allkm, s.block_km, s.cv_folds, y.astype(float), s.seed)
    fold_eval = block_folds_like(km_eval, allkm, fold, s.block_km)
    rec = {a: dict(auc=[], tss=[], boyce=[]) for a in s.algos}
    rec["ens"] = dict(auc=[], tss=[], boyce=[])
    oof_s = np.full((len(y), len(s.algos)), np.nan)
    used = 0
    for f in range(s.cv_folds):
        te, tr = fold == f, fold != f
        if (te & (y == 1)).sum() < 3 or (tr & (y == 1)).sum() < 10 or (te & (y == 0)).sum() < 3:
            continue
        used += 1
        ens = fit_ensemble(X[tr], y[tr], X_ref, s.algos, s.seed + 100 * f, n_jobs=s.n_jobs)
        Ptr, Pte = ens.percentile(X[tr]), ens.percentile(X[te])
        ev = np.nonzero(fold_eval == f)[0]
        ev = ev[:: max(1, len(ev) // 3000)]
        Pev = ens.percentile(X_eval[ev]) if len(ev) else None
        oof_s[te] = Pte
        ytr, yte = y[tr], y[te]
        for j, a in enumerate(s.algos):
            rec[a]["auc"].append(auc(Pte[yte == 1, j], Pte[yte == 0, j]))
            t = best_threshold(Ptr[ytr == 1, j], Ptr[ytr == 0, j])
            rec[a]["tss"].append(tss(Pte[yte == 1, j], Pte[yte == 0, j], t))
            if Pev is not None:
                rec[a]["boyce"].append(boyce(Pte[yte == 1, j], Pev[:, j]))
        # ensemble over all algorithms of this fold (the min_auc filter is applied afterwards, on the means)
        etr, ete = Ptr.mean(1), Pte.mean(1)
        rec["ens"]["auc"].append(auc(ete[yte == 1], ete[yte == 0]))
        rec["ens"]["tss"].append(tss(ete[yte == 1], ete[yte == 0], best_threshold(etr[ytr == 1], etr[ytr == 0])))
        if Pev is not None:
            rec["ens"]["boyce"].append(boyce(ete[yte == 1], Pev.mean(1)))
    mean = lambda v: float(np.nanmean(v)) if len(v) else float("nan")                       # noqa: E731
    per = {a: {k: mean(v) for k, v in r.items()} for a, r in rec.items() if a != "ens"}
    kept = tuple(a for a in s.algos if per[a]["auc"] >= s.min_auc) or tuple(s.algos)
    cols = [s.algos.index(a) for a in kept]
    sc = np.nanmean(oof_s[:, cols], 1)
    ens_metrics = {k: mean(v) for k, v in rec["ens"].items()}
    ok = ~np.isnan(sc)
    return CVResult(per, ens_metrics, sc[ok & (y == 1)], sc[ok & (y == 0)], kept, used)


def block_folds_like(km_new: np.ndarray, km_old: np.ndarray, fold_old: np.ndarray, block_km: float) -> np.ndarray:
    """Fold of new points given the fold of the blocks seen in `km_old`; unseen blocks get -1 (never evaluated)."""
    key = lambda k: np.floor(k[:, 0] / block_km).astype(np.int64) * 100003 + np.floor(k[:, 1] / block_km).astype(np.int64)   # noqa: E731
    ko, kn = key(km_old), key(km_new)
    u, first = np.unique(ko, return_index=True)
    fb = fold_old[first]
    pos = np.clip(np.searchsorted(u, kn), 0, len(u) - 1)
    return np.where(u[pos] == kn, fb[pos], -1)


@dataclass
class SDMResult:
    """Output of `run_sdm`."""
    settings: Settings
    names: tuple
    n_pres: int
    ensemble: Ensemble
    kept: tuple
    cv: CVResult
    thr: float
    score_now: np.ndarray
    present_now: np.ndarray
    future: dict = field(default_factory=dict)       # (ssp, period) -> dict(score, present, mess, novel_mahal)
    mess_now: np.ndarray = None


def run_sdm(grid, pres_idx: np.ndarray, bg_idx: np.ndarray, names, settings: Settings = Settings(), scenarios=()) -> SDMResult:
    """The full pipeline on a virtual.Grid.
    pres_idx / bg_idx: cell indices of (thinned) presence records and of the background sample.
    names: predictor names (virtual.BIO_NAMES subset). scenarios: iterable of (ssp, period) to project.
    Steps: spatial CV (if settings.cv) -> drop algorithms below min_auc -> final fit on all data -> percentile scores for the present
    domain -> threshold from out-of-fold presence scores (in-sample if cv is off) -> binary present range -> per scenario the
    score, the binary map and the MESS extrapolation flags (reference = training presences + background)."""
    s = settings
    P_now = grid.predictors(None, names)
    rng = np.random.default_rng(s.seed)
    ref_idx = rng.choice(grid.n, min(s.n_ref, grid.n), replace=False)
    Xp, Xb = P_now[pres_idx], P_now[bg_idx]
    km = grid.km
    cv = None
    algos = tuple(s.algos)
    if s.cv:
        cv = spatial_cv(Xp, Xb, km[pres_idx], km[bg_idx], P_now[ref_idx], P_now, km, s)
        algos = cv.kept
    X = np.vstack([Xp, Xb])
    y = np.r_[np.ones(len(Xp), int), np.zeros(len(Xb), int)]
    ens = fit_ensemble(X, y, P_now[ref_idx], algos, s.seed, n_jobs=s.n_jobs)
    score_now = ens.score(P_now)
    if cv is not None and len(cv.oof_pos) >= 5:
        thr = threshold(cv.oof_pos, cv.oof_bg, s.threshold)
    else:
        sc = ens.score(X)
        thr = threshold(sc[y == 1], sc[y == 0], s.threshold)
    res = SDMResult(s, tuple(names), len(pres_idx), ens, tuple(algos), cv, thr, score_now, score_now >= thr)
    res.mess_now = mess(X, P_now)[0]
    for ssp, period in scenarios:
        Pf = grid.predictors(grid.climate(ssp, period), names)
        sc = ens.score(Pf)
        m = mess(X, Pf)[0]
        res.future[(ssp, period)] = dict(score=sc, present=sc >= thr, mess=m, novel=m < 0)
    return res
