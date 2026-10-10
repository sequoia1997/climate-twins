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


def hindcast_bbs(species: dict, routes_fit: pd.DataFrame, routes_q: pd.DataFrame, pres: pd.DataFrame, spec, src, *, cfg: PL.FitConfig | None = None,
                 block: int = 1, n_boot: int = 300, w1=W1, w2=W2, test="bbs", th=H.TH, native=None, log=print):
    """species: {display name: AOU}. routes_fit: routes with enough window-1 years (columns country, state, route, lat, lon, row, col) used for
    the fit; routes_q: routes qualifying in both windows (the comparable cells); pres: bbs.route_presence output over routes_fit and routes_q.
    Returns (results, group verdict, species verdicts, cellsets, fits)."""
    density = route_density(spec, routes_fit.row.values, routes_fit.col.values)
    cellsets, cv, fits, n_el = {}, {}, {}, 0
    for name, aou in species.items():
        p = pres[(pres.AOU == aou) & pres.p1].merge(routes_fit[["country", "state", "route", "row", "col"]], on=["country", "state", "route"])
        cells = p[["row", "col"]].drop_duplicates()
        if len(cells) < 20:
            log(f"{name}: only {len(cells)} window-1 presence cells, skipped")
            continue
        fit = fit_window1(name, spec, src, cells.row.values, cells.col.values, density=density, native=native, cfg=cfg, w1=w1)
        sc = score_cells(fit, src, routes_q.row.values, routes_q.col.values, w1, w2)
        cs = bbs.species_cellset(routes_q, pres, aou, block=block, scores=sc, thr=fit.thr)
        cellsets[name], cv[name], fits[name] = cs, cv_of(fit), fit
        q = pres[(pres.AOU == aou)].merge(routes_q[["country", "state", "route"]], on=["country", "state", "route"])
        n_el += int(H.eligible(int(q.p1.sum()), int(q.p2.sum()), test, th))
        log(f"{name}: fit on {len(cells)} cells, cv {cv[name]}, thr {fit.thr:.3f}")
    results, g, verdicts = H.run_test(cellsets, test, cv=cv, th=th, n_eligible=n_el, n_boot=n_boot)
    return results, g, verdicts, cellsets, fits
