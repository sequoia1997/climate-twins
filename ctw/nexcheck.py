"""Is the ensemble's projected climate sensitive to the coarse resolution of the CMIP6 models?  (step `nexcheck`)

The main pipeline applies each CMIP6 model's monthly change (temperature added, precipitation and humidity scaled) to
the observed present climate. NASA NEX-GDDP-CMIP6 (~25 km, bias-corrected, daily) offers the same models at higher
resolution. This step repeats the projection with the NEX-GDDP changes and compares:

  * sigma distance between the two projected climates, in the place's own year-to-year variability metric (the same
    shrinkage-covariance metric that scores every match), and
  * whether the best present-day analog moves by more than `moved_km`.

Both projections use the same models (those NEX-GDDP publishes), the same present climate and the same delta method,
so what differs is the source of the change: the coarse native grid and its members vs the downscaled, bias-corrected
single member. Flag per place, worst case over the periods and the two scenarios NEX-GDDP is processed for:
  high      distance >= sigma_high (default 1.0), or distance >= sigma_moderate with an analog that moved > moved_km
  moderate  distance >= sigma_moderate (default 0.5), or an analog that moved > moved_km
  ok        otherwise
1 sigma is "as alike as two ordinary years" (the badge on the page); 0.5 is well inside that noise.

Inputs: work/results.npz (analogs step), data/nexdeltas.npz (written by `extremes --aggregate`, committed by the
Extreme days job). Output: site/data/nexcheck.json (only moderate/high places are listed; absent = ok or no data) and
work/nexcheck.npz. If the deltas file is missing the step logs that and does nothing."""
from __future__ import annotations
import json, time
import numpy as np
from . import common as C

MON = ("tmax", "tmin", "ppt", "vap")
DEFAULTS = {"sigma_moderate": 0.5, "sigma_high": 1.0, "moved_km": 500.0, "min_models": 6, "high_share_note": 0.15}
DELTAS = C.DATA / "nexdeltas.npz"
OUT = C.SITE / "data" / "nexcheck.json"


def settings(cfg) -> dict:
    return {**DEFAULTS, **cfg.get("nexcheck", {})}


# --------------------------------------------------------------------------- monthly changes (pure numpy)
def pack_deltas(mon_base, mon_fut):
    """Per-model monthly changes from the extremes pass' climatologies.
    mon_base (M, 4, NT, 12) and mon_fut (M, P, S, 4, NT, 12); variables tasmax, tasmin (deg C), pr (mm/day), hurs (%).
    Returns dtx, dtn (deg C), rp (precipitation ratio; 1 where the base month is dry), rv (vapour-pressure ratio from
    relative humidity at the mean temperature), each (M, P, S, NT, 12), ratios unclipped except to [0.01, 100]."""
    b, f = np.asarray(mon_base, "float64")[:, None, None], np.asarray(mon_fut, "float64")
    dtx, dtn = f[:, :, :, 0] - b[:, :, :, 0], f[:, :, :, 1] - b[:, :, :, 1]
    with np.errstate(invalid="ignore", divide="ignore"):
        rp = np.where(b[:, :, :, 2] > 0, f[:, :, :, 2] / b[:, :, :, 2], 1.0)
        eb = b[:, :, :, 3] / 100 * C.sat_vap((b[:, :, :, 0] + b[:, :, :, 1]) / 2)
        ef = f[:, :, :, 3] / 100 * C.sat_vap((f[:, :, :, 0] + f[:, :, :, 1]) / 2)
        rv = ef / eb
    return dtx, dtn, np.clip(rp, 0.01, 100), np.clip(rv, 0.01, 100)


def write_deltas(Z, names, T, cfg, path=None):
    """Called by extremes.aggregate: fold the per-model npz dicts Z into data/nexdeltas.npz (float16, labelled)."""
    mb = np.stack([z["mon_base"] for z in Z])
    mf = np.stack([z["mon_fut"] for z in Z])
    dtx, dtn, rp, rv = pack_deltas(mb, mf)
    path = path or DELTAS
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, dtx=dtx.astype("float16"), dtn=dtn.astype("float16"), rp=rp.astype("float16"), rv=rv.astype("float16"),
                        models=np.array(names), scen=np.array([str(x) for x in Z[0]["scen"]]), periods=np.array(cfg["periods"]["keys"]),
                        labels=np.array(T.label.values.astype(str)), lat=T.lat.values.astype("float32"), lon=T.lon.values.astype("float32"))
    C.log.info("nexdeltas.npz: %d models, %d places, %.1f MB", len(names), len(T), path.stat().st_size / 1e6)
    return path


def project(base_mon, d, mcfg):
    """One model's projected 16-value seasonal vectors (NT, 16): the main pipeline's own delta step (analogs.apply_delta)
    on the present monthly climate base_mon {tmax, tmin, ppt, vap: (NT, 12)} with this model's changes d = (dtx, dtn, rp, rv),
    precipitation and humidity ratios limited to the configured ranges."""
    from .analogs import apply_delta
    lo, hi = mcfg["ppt_ratio"]
    vlo, vhi = mcfg["vap_ratio"]
    dtx, dtn, rp, rv = (np.asarray(x, "float64") for x in d)
    mon = apply_delta(base_mon, (dtx, dtn, np.clip(rp, lo, hi), np.clip(rv, vlo, vhi)))
    return C.seasonalize({v: mon[v].T for v in MON}).T


def sigma_between(A, B, Mx, midx):
    """Sigma distance between two raw 16-value climates per place. A, B (NT, 16); Mx (NT, K, K) the places' metric
    (Msh: coordinates -> whitened principal components, K = len(midx)). One-dimensional z-score equivalent, like every
    sigma on the page."""
    dz = C.transform(A)[:, midx] - C.transform(B)[:, midx]
    D = np.linalg.norm(np.einsum("nk,nkj->nj", dz, Mx), axis=1)
    return C.chi_to_sigma(D, Mx.shape[-1])


def best_cell(q, Mk, pool_tr, midx):
    """Index of the pool cell nearest the raw 16-value climate q in the place's metric Mk (K, K)."""
    Pp = pool_tr @ Mk
    Q = C.transform(q)[midx] @ Mk
    return int(((Pp - Q) ** 2).sum(1).argmin())


def classify(dsig, moved, sm=0.5, sh=1.0):
    """Flag for one place: dsig (P, S) sigma distances, moved (P, S) bool. "ok" / "moderate" / "high", None without data."""
    dsig, moved = np.asarray(dsig, float), np.asarray(moved, bool)
    if not np.isfinite(dsig).any():
        return None
    d = np.where(np.isfinite(dsig), dsig, 0.0)
    if ((d >= sh) | (moved & (d >= sm))).any():
        return "high"
    if ((d >= sm) | moved).any():
        return "moderate"
    return "ok"


def summary_line(doc) -> str:
    """One line for validate's report."""
    S = doc["summary"]
    n = S["ok"] + S["moderate"] + S["high"]
    if not n:
        return "Sensitivity to model resolution (NEX-GDDP-CMIP6 vs main deltas): no places compared"
    th = doc["thresholds"]
    return (f"Sensitivity to model resolution (NEX-GDDP-CMIP6 changes vs the main CMIP6 changes, {doc['n_models']} models, {n} places): "
            f"{S['ok'] / n:.0%} ok, {S['moderate'] / n:.0%} moderate (≥ {th['sigma_moderate']}σ or best match moved > {th['moved_km']:.0f} km), "
            f"{S['high'] / n:.0%} high (≥ {th['sigma_high']}σ); median difference {S['median_dsigma']}σ, 95th percentile {S['p95_dsigma']}σ")


# --------------------------------------------------------------------------- the step
def run(cfg=None, deltas_path=None, out=None):
    cfg = cfg or C.config()
    s = settings(cfg)
    deltas_path = deltas_path or DELTAS
    if not deltas_path.exists():
        C.log.warning("nexcheck: %s not found (the Extreme days job has not produced it yet); skipped", deltas_path)
        return None
    t0 = time.time()
    R = C.load(C.work("results.npz"))
    if "base_mon" not in R:
        raise RuntimeError("results.npz has no base_mon: rerun the analogs step")
    Z = C.load(deltas_path)
    T = C.targets()
    names = [str(x) for x in Z["models"]]
    mnames = [m["name"] for m in C.models(cfg)]
    use = [(j, mnames.index(n)) for j, n in enumerate(names) if n in mnames]
    if len(use) < s["min_models"]:
        C.log.warning("nexcheck: only %d NEX-GDDP models, need %d; skipped", len(use), s["min_models"])
        return None
    nj, mj = [u[0] for u in use], [u[1] for u in use]
    lab = [str(x) for x in Z["labels"]]
    src = np.array([lab.index(l) if l in lab else -1 for l in T.label])           # place order of the file -> current order
    have = src >= 0
    src0 = np.where(have, src, 0)
    sc_ids = cfg["scenarios"]["ids"]
    scen = [str(x) for x in Z["scen"]]
    sidx = [sc_ids.index(x) for x in scen]
    NT, P, S = len(T), len(cfg["periods"]["keys"]), len(scen)
    mcfg, midx = cfg["matching"], R["midx"]
    bm = {v: R["base_mon"][i].astype("float64") for i, v in enumerate(MON)}
    Msh, bad, G = R["Msh"].astype("float64"), R["bad"], T.g.values
    pools = {0: (C.transform(R["na_raw"].astype("float64"))[:, midx], R["na_lat"], R["na_lon"]),
             1: (C.transform(R["w_raw"].astype("float64"))[:, midx], R["w_lat"], R["w_lon"])}
    dsig = np.full((NT, P, S), np.nan, "float32")
    moved_km = np.full((NT, P, S), np.nan, "float32")
    for p in range(P):
        for si, s_main in enumerate(sidx):
            ens_nex, ens_main = [], []
            for j, m in zip(nj, mj):
                d = tuple(np.where(have[:, None], Z[k][j, p, si].astype("float64")[src0], np.nan) for k in ("dtx", "dtn", "rp", "rv"))
                ens_nex.append(project(bm, d, mcfg))
                ens_main.append(R["fut"][:, p, s_main, m].astype("float64"))
            A, B = np.mean(ens_nex, axis=0), np.mean(ens_main, axis=0)          # NEX-based and main projection, same models
            with np.errstate(invalid="ignore"):
                dsig[:, p, si] = sigma_between(A, B, Msh, midx)
            for k in np.where(have & ~bad & np.isfinite(A).all(1) & np.isfinite(B).all(1))[0]:
                tr, la, lo = pools[int(G[k])]
                i1, i2 = best_cell(A[k], Msh[k], tr, midx), best_cell(B[k], Msh[k], tr, midx)
                moved_km[k, p, si] = float(C.haversine_km(la[i1], lo[i1], la[i2], lo[i2]))
        C.log.info("nexcheck: period %d done (%.0fs)", p, time.time() - t0)
    from .extremes import place_key
    places, counts = {}, {"ok": 0, "moderate": 0, "high": 0, "nodata": 0}
    for k in range(NT):
        f = None if (bad[k] or not have[k]) else classify(dsig[k], moved_km[k] > s["moved_km"], s["sigma_moderate"], s["sigma_high"])
        if f is None:
            counts["nodata"] += 1
            continue
        counts[f] += 1
        if f != "ok":
            places[place_key(T.lat[k], T.lon[k])] = {"gcm_res_sensitivity": f, "dsig": round(float(np.nanmax(dsig[k])), 2),
                                                     "moved_km": int(np.nanmax(moved_km[k])) if np.isfinite(moved_km[k]).any() else 0}
    fin = dsig[np.isfinite(dsig)]
    doc = {"generated": time.strftime("%Y-%m-%d"), "n_models": len(use), "models": [names[j] for j in nj],
           "scenarios": scen, "thresholds": {k: s[k] for k in ("sigma_moderate", "sigma_high", "moved_km")},
           "summary": {**counts, "median_dsigma": round(float(np.median(fin)), 3) if len(fin) else None,
                       "p95_dsigma": round(float(np.percentile(fin, 95)), 3) if len(fin) else None},
           "places": places}
    out = out or OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(doc, open(out, "w"), separators=(",", ":"), ensure_ascii=False)
    C.save(C.work("nexcheck.npz"), dsig=dsig, moved_km=moved_km, labels=T.label.values.astype(str))
    C.log.info(summary_line(doc))
    return doc
