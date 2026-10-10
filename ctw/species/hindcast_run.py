"""Run the BBS hindcast with the W3 pipeline (workstream W4): fit on window 1 only, score window 1 and window 2 climate at the route
cells, compare with the observed change (ctw/species/hindcast.py).

The fit is the production fit (`pipeline.fit_species`: same predictor selection, LightGBM, target-group background, spatial-block CV, p05
threshold) with two differences that are the point of the test: the climate it sees is the window-1 climate (`WindowSource`), and the
presence records are the BBS window-1 route presences instead of GBIF records. The target-group density is the BBS window-1 route density,
which is the sampling effort, so the background corrects for where routes exist. Window-2 information (observations or climate) is never
used in the fit, the predictor selection or the threshold.
"""
from __future__ import annotations
import dataclasses
import numpy as np
import pandas as pd

from . import grid, pipeline as PL, bbs, hindcast as H

W1, W2 = "1966-1985", "2005-2024"          # W1 climate products hind_1966-1985 and hind_2005-2024


class WindowSource(grid.ClimateSource):
    """A ClimateSource whose default window is a hindcast window (so the pipeline fits on that climate without code changes)."""

    def __init__(self, src: grid.ClimateSource, window: str):
        self._src, self.window, self.spec, self.names = src, window, src.spec, src.names

    def baseline_band(self, r0, r1, names=None, window=None):
        return self._src.baseline_band(r0, r1, names, self.window if window in (None, grid.BASELINE) else window)

    def baseline_points(self, rows, cols, names=None, window=None, band_rows=256):
        return self._src.baseline_points(rows, cols, names, self.window if window in (None, grid.BASELINE) else window, band_rows)

    def land_band(self, r0, r1):
        return self._src.land_band(r0, r1)

    def future_models(self, ssp, period):
        return self._src.future_models(ssp, period)

    def future_band(self, ssp, period, model, r0, r1, names=None):
        return self._src.future_band(ssp, period, model, r0, r1, names)


def route_density(spec: grid.GridSpec, rows, cols) -> np.ndarray:
    """Sampling-effort surface: 1 on cells that hold a route start, 0 elsewhere (the pipeline mixes in a uniform floor)."""
    d = np.zeros((spec.H, spec.W), np.float32)
    d[np.asarray(rows), np.asarray(cols)] = 1.0
    return d


def fit_window1(name, spec, src, rows, cols, density=None, native=None, group="bird", cfg: PL.FitConfig | None = None, w1=W1, log=lambda *a: None):
    """Production fit on window-1 climate and window-1 route presences (rows, cols of the cells where the species is present)."""
    occ = grid.Occurrences(rows, cols)
    cfg = cfg or PL.FitConfig()
    if hasattr(cfg, "window"):                               # W3's own hook (FitConfig.window); WindowSource below keeps older pipelines working
        cfg = dataclasses.replace(cfg, window=w1)
    return PL.fit_species(name, spec, WindowSource(src, w1), occ, native=native, density=density, group=group, cfg=cfg, log=log)


def score_cells(fit, src: grid.ClimateSource, rows, cols, w1=W1, w2=W2) -> pd.DataFrame:
    """Suitability at cells under window-1 and window-2 climate (same fitted model and predictors). Cells without climate data are dropped."""
    rows, cols = np.asarray(rows), np.asarray(cols)
    X1 = src.baseline_points(rows, cols, fit.pred, window=w1)
    X2 = src.baseline_points(rows, cols, fit.pred, window=w2)
    ok = np.isfinite(X1).all(1) & np.isfinite(X2).all(1)
    return pd.DataFrame(dict(row=rows[ok], col=cols[ok], score1=fit.score(X1[ok].astype(float)), score2=fit.score(X2[ok].astype(float))))


def cv_of(fit) -> dict:
    m = fit.cv["metrics"].get("gbm", {})
    return dict(tss=m.get("tss", np.nan), auc=m.get("auc", np.nan), boyce=m.get("boyce", np.nan))


def blocked_scores(spec, src, routes_fit: pd.DataFrame, routes_q: pd.DataFrame, pres_cells: pd.DataFrame, pred, w1=W1, w2=W2, k=5, block_km=400.0, seed=0):
    """Spatially blocked cross-fitted hindcast scores (the strict variant). Training cells are the window-1 route cells with a true presence (species
    detected) or true absence (route surveyed, not detected). Cells are split into spatial blocks of block_km; for each fold a LightGBM model of the
    production class (`sdm.GBM`, the pipeline's predictors `pred`) is fitted on window-1 climate and window-1 labels OUTSIDE the block and scores the
    comparable (evaluation) cells INSIDE the block under window-1 and window-2 climate. Every evaluation cell is therefore scored by a model that never
    saw that place or window 2: this removes the memorisation of local climate that makes the fit-cell variant look better than it is. The presence
    threshold is the 5th percentile of the out-of-fold presence scores (as production). Returns (scores DataFrame row, col, score1, score2; threshold;
    cv dict with presence-absence AUC, TSS and Boyce from the same out-of-fold scores)."""
    from . import sdm
    tr = routes_fit[["row", "col"]].drop_duplicates().reset_index(drop=True)
    X = src.baseline_points(tr.row.values, tr.col.values, pred, window=w1).astype(float)
    ok = np.isfinite(X).all(1)
    tr, X = tr[ok].reset_index(drop=True), X[ok]
    key = set(zip(pres_cells.row, pres_cells.col))
    y = np.array([(r, c) in key for r, c in zip(tr.row, tr.col)], int)
    ev = routes_q[["row", "col"]].drop_duplicates().reset_index(drop=True)
    X1 = src.baseline_points(ev.row.values, ev.col.values, pred, window=w1).astype(float)
    X2 = src.baseline_points(ev.row.values, ev.col.values, pred, window=w2).astype(float)
    oke = np.isfinite(X1).all(1) & np.isfinite(X2).all(1)
    ev, X1, X2 = ev[oke].reset_index(drop=True), X1[oke], X2[oke]
    nan = dict(tss=np.nan, auc=np.nan)
    if y.sum() < 20 or (y == 0).sum() < 20:
        return pd.DataFrame(columns=["row", "col", "score1", "score2"]), np.nan, nan
    allrc = pd.concat([tr[["row", "col"]], ev[["row", "col"]]], ignore_index=True)
    km = spec.km_xy(allrc.row.values, allrc.col.values)
    wts = np.r_[y.astype(float), np.zeros(len(ev))]
    folds = sdm.block_folds(km, block_km, k, wts, seed)
    ftr, fev = folds[:len(tr)], folds[len(tr):]
    oof = np.full(len(tr), np.nan)
    s1, s2 = np.full(len(ev), np.nan), np.full(len(ev), np.nan)
    for f in range(k):
        te, ee = ftr == f, fev == f
        if y[~te].sum() < 10 or (y[~te] == 0).sum() < 10:
            continue
        m = sdm.GBM(seed=seed, n_jobs=1).fit(X[~te], y[~te])
        if te.any():
            oof[te] = m.raw(X[te])
        if ee.any():
            s1[ee], s2[ee] = m.raw(X1[ee]), m.raw(X2[ee])
    mk = np.isfinite(oof)
    pos, neg = oof[mk & (y == 1)], oof[mk & (y == 0)]
    if len(pos) < 10 or len(neg) < 10:
        return pd.DataFrame(columns=["row", "col", "score1", "score2"]), np.nan, nan
    thr = sdm.threshold(pos, neg, "p05")
    cv = dict(auc=sdm.auc(pos, neg), tss=sdm.tss(pos, neg, thr), boyce=sdm.boyce(pos, oof[mk]), n_pres=int(len(pos)), n_abs=int(len(neg)), source="presence-absence spatial-block CV")
    good = np.isfinite(s1) & np.isfinite(s2)
    return pd.DataFrame(dict(row=ev.row.values[good], col=ev.col.values[good], score1=s1[good], score2=s2[good])), thr, cv


def hindcast_bbs(species: dict, routes_fit: pd.DataFrame, routes_q: pd.DataFrame, pres: pd.DataFrame, spec, src, *, cfg: PL.FitConfig | None = None,
                 block: int = 1, n_boot: int = 300, w1=W1, w2=W2, test="bbs", th=H.TH, native=None, modes=("blocked", "fit_cells"), log=print):
    """species: {display name: AOU}. routes_fit: routes with enough window-1 years (columns country, state, route, lat, lon, row, col) used for
    the fit; routes_q: routes qualifying in both windows (the comparable cells); pres: bbs.route_presence output over routes_fit and routes_q.
    Two variants per species, both fitted on window 1 only:
      fit_cells  the production fit (pipeline.fit_species on BBS window-1 presences, target-group density = route density), scored at the comparable
                 cells, most of which it saw in window 1 (optimistic for static skill);
      blocked    spatially blocked cross-fitting (`blocked_scores`): every comparable cell is scored by a model that never saw it (strict).
    Returns {mode: (results, group verdict, species verdicts, cellsets)} and the fits."""
    density = route_density(spec, routes_fit.row.values, routes_fit.col.values)
    sets = {m: {} for m in modes}
    cvs = {m: {} for m in modes}
    fits, n_el = {}, 0
    for name, aou in species.items():
        p = pres[(pres.AOU == aou) & pres.p1].merge(routes_fit[["country", "state", "route", "row", "col"]], on=["country", "state", "route"])
        cells = p[["row", "col"]].drop_duplicates()
        if len(cells) < 20:
            log(f"{name}: only {len(cells)} window-1 presence cells, skipped")
            continue
        fit = fit_window1(name, spec, src, cells.row.values, cells.col.values, density=density, native=native, cfg=cfg, w1=w1)
        fits[name] = fit
        q = pres[(pres.AOU == aou)].merge(routes_q[["country", "state", "route"]], on=["country", "state", "route"])
        n_el += int(H.eligible(int(q.p1.sum()), int(q.p2.sum()), test, th))
        w3cv = cv_of(fit)
        if "fit_cells" in modes:
            sc = score_cells(fit, src, routes_q.row.values, routes_q.col.values, w1, w2)
            sets["fit_cells"][name] = bbs.species_cellset(routes_q, pres, aou, block=block, scores=sc, thr=fit.thr)
            cvs["fit_cells"][name] = dict(w3cv, w3_background_cv=w3cv, source="W3 presence-vs-background spatial CV")
        if "blocked" in modes:
            sc, thr, cv_pa = blocked_scores(spec, src, routes_fit, routes_q, cells, fit.pred, w1, w2)
            if len(sc):
                sets["blocked"][name] = bbs.species_cellset(routes_q, pres, aou, block=block, scores=sc, thr=thr)
                cvs["blocked"][name] = dict(cv_pa, w3_background_cv=w3cv)
        log(f"{name}: fit on {len(cells)} cells, W3 cv {w3cv}, blocked PA cv {cvs['blocked'].get(name, {}).get('auc')}/{cvs['blocked'].get(name, {}).get('tss')}, thr {fit.thr:.3f}")
    out = {}
    for m in modes:
        out[m] = H.run_test(sets[m], test, cv=cvs[m], th=th, n_eligible=n_el, n_boot=n_boot) + (sets[m],)
    return out, fits
