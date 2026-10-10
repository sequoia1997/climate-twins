"""Per-species JSON summary (W3): area now and future, change, gain / loss / stable, centroid shift and bearing, per scenario, period
and dispersal bound; the gates, the tier, skill, records and data DOIs. Gate decisions that withhold numbers are applied here."""
from __future__ import annotations
import json
import math
import numpy as np

from .grid import GridSpec
from .pipeline import Fit
from .project import Projection, MODES, THR7, AGREE_MIN, area_of, range_stats
from . import gates as G

SCHEMA = "ctw-species-summary/1"


def _clean(o):
    """JSON-safe copy: numpy scalars to Python, NaN / inf to None, tuples to lists."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def key(ssp: str, period: str) -> str:
    return f"{ssp}|{period}"


def build_summary(fit: Fit, proj: Projection, meta: dict, *, expert: np.ndarray = None, expert_kind: str = "native_range",
                  validation: dict = None, gate_cfg: G.GateConfig = G.GateConfig(), dois: list = None) -> dict:
    """meta: species table row (scientific_name, common_name, group, validation_plan, gbif_taxon_key, ...)."""
    spec = fit.spec
    now = proj.now
    a_now = area_of(now, spec)
    rng = G.range_check(now, spec, fit.pres_rc, expert, expert_kind, gate_cfg)
    by, audit, novel_shares, main_change, check_change = {}, {}, {}, {}, {}
    for (ssp, period), sc in proj.scen.items():
        k = key(ssp, period)
        fut_unl = sc.S >= THR7
        union = fut_unl | now
        a_u = area_of(union, spec)
        novel_shares[k] = area_of((sc.N > 0) & union, spec) / a_u if a_u > 0 else 0.0
        modes = {}
        for mode in MODES:
            fut = proj.binary((ssp, period), mode)
            st = range_stats(spec, now, fut)
            a_f = st["area_fut"]
            agree = area_of(fut & (sc.A >= round(15 * AGREE_MIN)), spec) / a_f if a_f > 0 else None
            st.update(agree_share=agree, novel_share=area_of((sc.N > 0) & fut, spec) / a_f if a_f > 0 else None)
            modes[mode] = st
        main_change[k] = modes["unlimited"]["change_pct"]
        if sc.check is not None and proj.check0 is not None:
            a0, a1 = area_of(proj.check0, spec), area_of(sc.check, spec)
            check_change[k] = (a1 / a0 - 1) * 100 if a0 > 0 else float("nan")
        by[k] = dict(ssp=ssp, period=period, n_models=sc.n_models, novel_share=novel_shares[k], mahalanobis_beyond_share=sc.mahal_share,
                     reach_km=proj.reach_km.get(period), modes=modes)
    cv = fit.cv
    auc = cv["metrics"]["gbm"]["auc"]
    ev = G.evaluate(n_gate=fit.records["n_gate"], n_used=fit.records["n_used"], cv_auc=auc, area_now=a_now, novel_shares=novel_shares,
                    check_change=check_change, main_change=main_change, rng_check=rng, validation=validation, cfg=gate_cfg)
    # withhold shift numbers where novel climate dominates (numbers kept under 'audit' for reviewers, not for display)
    for k, w in ev["withheld"].items():
        if w:
            audit[k] = by[k]["modes"]
            by[k]["modes"] = {m: dict(withheld=True, area_now=v["area_now"]) for m, v in by[k]["modes"].items()}
            by[k]["withheld"] = True
            by[k]["withheld_reason"] = (f"{novel_shares[k]:.0%} of the area is novel climate "
                                        f"(limit {gate_cfg.novel_max:.0%}): shift numbers withheld")
    summ = dict(
        schema=SCHEMA,
        species=dict(id=meta.get("id") or _slug(meta.get("scientific_name", fit.species)), scientific_name=meta.get("scientific_name", fit.species),
                     common_name=meta.get("common_name"), group=meta.get("group"), gbif_taxon_key=meta.get("gbif_taxon_key"),
                     validation_plan=meta.get("validation_plan")),
        tier=ev["tier"], confidence=ev["confidence"], published=ev["published"], hard_failures=ev["hard_failures"], soft_flags=ev["soft_flags"],
        wording=ev["wording"],
        area_now_km2=a_now,
        records=dict(raw=fit.records["n_raw"], flagged_excluded=fit.records["n_flagged"], thinned_cells=fit.records["n_cells"],
                     gate_cells=fit.records["n_gate"], used_in_fit=fit.records["n_used"], background=fit.records["n_bg"],
                     no_climate=fit.records.get("n_no_climate")),
        skill=dict(cv_auc=auc, cv_tss=cv["metrics"]["gbm"]["tss"], cv_boyce=cv["metrics"]["gbm"]["boyce"], cv_auc_domain=cv["metrics"]["gbm"]["auc_dom"],
                   check_model=cv["metrics"].get("gam"), folds_used=cv["folds_used"], folds=cv["folds"], block_km=cv["block_km"],
                   threshold=fit.thr, threshold_method=fit.note["threshold_method"], threshold_source=fit.note["threshold_source"],
                   thresholds_all=fit.thr_all, note="AUC is against a target-group background and rewards niche specificity; Boyce is reported, not gated"),
        predictors=fit.selection,
        domain=dict(train_km2=area_of(fit.train, spec), projection_km2=area_of(fit.proj, spec), native_range_used=expert is not None,
                    train_buffer_km=fit.cfg.train_buffer_km, proj_buffer_km=fit.cfg.proj_buffer_km),
        dispersal=dict(proj.dispersal, reach_km=proj.reach_km),
        scenarios=by,
        audit_withheld=audit,
        gates=ev["gates"],
        gate_config=ev["config"],
        validation=validation,
        model=dict(main="LightGBM", check="penalised-spline GAM (logistic)", background=fit.cfg.bias, seed=fit.cfg.seed),
        data_dois=dois or [],
    )
    return _clean(summ)


def _slug(s: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in s).strip("_")


def dumps(summary: dict) -> str:
    return json.dumps(summary, indent=1, sort_keys=False)
