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

Multi-source: the same comparison is repeated for each downscaled source that exists and the flag is the worst case
over sources (combine); the entry lists which source(s) flagged it ("flagged_by") and each source's own flag:
  nex  NASA NEX-GDDP-CMIP6 (data/nexdeltas.npz; also humidity)
  wc   WorldClim 2.1 CMIP6 (data/downdeltas.npz; change = future - WorldClim baseline 1970-2000, see ctw/downdeltas.py)
  aw   AdaptWest downscaled CMIP6, North America (data/downdeltas.npz)
Models: a source's models that the main pipeline also has (mode "overlap", needs [nexcheck] min_models of them), else the
source's own multi-model mean against the main ensemble mean over the likely-TCR models (mode "mean", e.g. an ensemble product).

Inputs: work/results.npz (analogs step), data/nexdeltas.npz (Extreme days job) and data/downdeltas.npz (Downscaled changes job),
whichever exist. Output: site/data/nexcheck.json (only moderate/high places are listed; absent = ok or no data) and
work/nexcheck.npz. With no deltas file the step logs that and does nothing."""
from __future__ import annotations
import json, time
import numpy as np
from . import common as C

MON = ("tmax", "tmin", "ppt", "vap")
DEFAULTS = {"sigma_moderate": 0.5, "sigma_high": 1.0, "moved_km": 500.0, "min_models": 6, "high_share_note": 0.15}
DELTAS = C.DATA / "nexdeltas.npz"
DOWN = C.DATA / "downdeltas.npz"
SRC_LABEL = {"nex": "NEX-GDDP-CMIP6", "wc": "WorldClim 2.1", "aw": "AdaptWest"}
RANK = {"ok": 0, "moderate": 1, "high": 2}
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


# --------------------------------------------------------------------------- sources
class Source:
    """One downscaled set of monthly changes: name, model names, scenarios, place labels (file order) and get(k, j, p, si) ->
    (n_places_in_file, 12) array of change k in ("dtx", "dtn", "rp", "rv") of model j; rv is NaN where the source has no humidity
    (constant relative humidity is then assumed by analogs.apply_delta, as the main pipeline does for a model without huss)."""

    def __init__(self, name, models, scen, labels, arrays):
        self.name, self.models, self.scen, self.labels, self.arrays = name, list(models), list(scen), list(labels), arrays

    def get(self, k, j, p, si):
        a = self.arrays.get(k)
        if a is None:
            return np.full(self.arrays["dtx"].shape[-2:], np.nan)
        return a[j, p, si].astype("float64")


def load_sources(nex_path=None, down_path=None):
    """The available sources: NEX-GDDP (data/nexdeltas.npz) and WorldClim / AdaptWest (data/downdeltas.npz), whichever exist."""
    out = []
    nex_path, down_path = nex_path or DELTAS, down_path or DOWN
    if nex_path.exists():
        Z = C.load(nex_path)
        out.append(Source("nex", [str(x) for x in Z["models"]], [str(x) for x in Z["scen"]], [str(x) for x in Z["labels"]],
                          {k: Z[k] for k in ("dtx", "dtn", "rp", "rv")}))
    if down_path.exists():
        Z = C.load(down_path)
        for n in ("wc", "aw"):
            if f"{n}_dtx" in Z:
                out.append(Source(n, [str(x) for x in Z[f"{n}_models"]], [str(x) for x in Z[f"{n}_scen"]], [str(x) for x in Z["labels"]],
                                  {k: Z[f"{n}_{k}"] for k in ("dtx", "dtn", "rp")}))
    return out


def combine(flags):
    """Worst case over sources. flags {name: "ok"/"moderate"/"high"/None} -> (flag, [names at that level]); (None, []) without data."""
    f = {k: v for k, v in flags.items() if v}
    if not f:
        return None, []
    w = max(f.values(), key=RANK.get)
    return w, [k for k, v in f.items() if v == w]


def select_models(src, mnames, ens, min_models):
    """Which models to compare: the source's models that the main pipeline also has (mode "overlap"), or, when fewer than
    min_models overlap (a multi-model product such as an AdaptWest ensemble), the source's own mean against the main
    ensemble mean over its likely-TCR models (mode "mean"). Returns (source indices, main indices, mode)."""
    use = [(j, mnames.index(n)) for j, n in enumerate(src.models) if n in mnames]
    if len(use) >= min_models:
        return [u[0] for u in use], [u[1] for u in use], "overlap"
    return list(range(len(src.models))), list(ens), "mean"


def compare(src, ctx, s):
    """Sigma distance and best-analog movement between the main projection and one source's, per place, period and scenario.
    ctx: dict with R, T, cfg, bm, Msh, bad, G, pools, midx. Returns dsig, moved_km (NT, P, S_src) and info, or None."""
    import warnings
    R, T, cfg = ctx["R"], ctx["T"], ctx["cfg"]
    mnames = [m["name"] for m in C.models(cfg)]
    nj, mj, mode = select_models(src, mnames, C.ensembles(cfg)["tcr_likely"], s["min_models"])
    if not nj:
        return None
    ix = {l: i for i, l in enumerate(src.labels)}
    srcx = np.array([ix.get(l, -1) for l in T.label])                       # place order of the file -> current order
    have = srcx >= 0
    src0 = np.where(have, srcx, 0)
    sc_ids = cfg["scenarios"]["ids"]
    NT, P, S = len(T), len(cfg["periods"]["keys"]), len(src.scen)
    mcfg, midx, bm, Msh, bad, G, pools = cfg["matching"], ctx["midx"], ctx["bm"], ctx["Msh"], ctx["bad"], ctx["G"], ctx["pools"]
    dsig = np.full((NT, P, S), np.nan, "float32")
    moved = np.full((NT, P, S), np.nan, "float32")
    t0 = time.time()
    for p in range(P):
        for si, ssp in enumerate(src.scen):
            if ssp not in sc_ids:
                continue
            s_main = sc_ids.index(ssp)
            A = np.array([project(bm, tuple(np.where(have[:, None], src.get(k, j, p, si)[src0], np.nan) for k in ("dtx", "dtn", "rp", "rv")), mcfg)
                          for j in nj])
            B = np.array([R["fut"][:, p, s_main, m].astype("float64") for m in mj])
            fa, fb = np.isfinite(A).all(-1), np.isfinite(B).all(-1)
            if mode == "overlap":
                fa = fb = fa & fb                                             # the same models on both sides at every place
            with warnings.catch_warnings(), np.errstate(invalid="ignore"):
                warnings.simplefilter("ignore")
                Am = np.nanmean(np.where(fa[..., None], A, np.nan), axis=0)
                Bm = np.nanmean(np.where(fb[..., None], B, np.nan), axis=0)
                dsig[:, p, si] = sigma_between(Am, Bm, Msh, midx)
            for k in np.where(have & ~bad & np.isfinite(Am).all(1) & np.isfinite(Bm).all(1))[0]:
                tr, la, lo = pools[int(G[k])]
                i1, i2 = best_cell(Am[k], Msh[k], tr, midx), best_cell(Bm[k], Msh[k], tr, midx)
                moved[k, p, si] = float(C.haversine_km(la[i1], lo[i1], la[i2], lo[i2]))
        C.log.info("nexcheck %s: period %d done (%.0fs)", src.name, p, time.time() - t0)
    info = {"name": src.name, "label": SRC_LABEL.get(src.name, src.name), "mode": mode, "n_models": len(nj),
            "models": [src.models[j] for j in nj], "scenarios": [x for x in src.scen if x in sc_ids]}
    return dsig, moved, info


def summary_line(doc) -> str:
    """One line for validate's report."""
    S = doc["summary"]
    n = S["ok"] + S["moderate"] + S["high"]
    if not n:
        return "Sensitivity to model resolution (downscaled CMIP6 changes vs the main CMIP6 changes): no places compared"
    th = doc["thresholds"]
    srcs = doc.get("sources")
    names = " + ".join(f"{x['label']} ({x['n_models']} {'models' if x['mode'] == 'overlap' else 'model mean'})" for x in srcs) if srcs \
        else f"NEX-GDDP-CMIP6 ({doc['n_models']} models)"
    line = (f"Sensitivity to model resolution (downscaled changes vs the main CMIP6 changes; {names}; worst case over sources; {n} places): "
            f"{S['ok'] / n:.0%} ok, {S['moderate'] / n:.0%} moderate (≥ {th['sigma_moderate']}σ or best match moved > {th['moved_km']:.0f} km), "
            f"{S['high'] / n:.0%} high (≥ {th['sigma_high']}σ); median difference {S['median_dsigma']}σ, 95th percentile {S['p95_dsigma']}σ")
    if srcs and len(srcs) > 1:
        tot = lambda m: max(m["ok"] + m["moderate"] + m["high"], 1)
        line += "; high by source: " + ", ".join(f"{x['label']} {x['summary']['high'] / tot(x['summary']):.0%}" for x in srcs)
    return line


# --------------------------------------------------------------------------- the step
def run(cfg=None, deltas_path=None, out=None, down_path=None):
    cfg = cfg or C.config()
    s = settings(cfg)
    if C.extra_names(cfg):
        C.log.warning("nexcheck: skipped while [matching] extra is set (the downscaled changes cover tmax, tmin, precipitation and, for NEX-GDDP, humidity only; pet and srad are not checked)")
        return None
    sources = load_sources(deltas_path, down_path)
    if not sources:
        C.log.warning("nexcheck: neither %s nor %s found (the Extreme days / Downscaled changes jobs have not produced them yet); skipped", DELTAS, DOWN)
        return None
    R = C.load(C.work("results.npz"))
    if "base_mon" not in R:
        raise RuntimeError("results.npz has no base_mon: rerun the analogs step")
    T = C.targets()
    midx = R["midx"]
    ctx = {"R": R, "T": T, "cfg": cfg, "midx": midx, "bm": {v: R["base_mon"][i].astype("float64") for i, v in enumerate(MON)},
           "Msh": R["Msh"].astype("float64"), "bad": R["bad"], "G": T.g.values,
           "pools": {0: (C.transform(R["na_raw"].astype("float64"))[:, midx], R["na_lat"], R["na_lon"]),
                     1: (C.transform(R["w_raw"].astype("float64"))[:, midx], R["w_lat"], R["w_lon"])}}
    NT, bad = len(T), R["bad"]
    res = {}
    for src in sources:
        r = compare(src, ctx, s)
        if r is None:
            C.log.warning("nexcheck: source %s has no models; skipped", src.name)
        else:
            res[src.name] = r
    if not res:
        return None
    from .extremes import place_key
    places, counts = {}, {"ok": 0, "moderate": 0, "high": 0, "nodata": 0}
    per = {n: {"ok": 0, "moderate": 0, "high": 0, "nodata": 0} for n in res}

    def mx(a):
        return float(np.nanmax(a)) if np.isfinite(a).any() else 0.0
    for k in range(NT):
        fl = {}
        for n, (dsig, moved, info) in res.items():
            f = None if bad[k] else classify(dsig[k], moved[k] > s["moved_km"], s["sigma_moderate"], s["sigma_high"])
            fl[n] = f
            per[n]["nodata" if f is None else f] += 1
        worst, by = combine(fl)
        if worst is None:
            counts["nodata"] += 1
            continue
        counts[worst] += 1
        if worst != "ok":
            places[place_key(T.lat[k], T.lon[k])] = {
                "gcm_res_sensitivity": worst, "flagged_by": by,
                "dsig": round(max(mx(res[n][0][k]) for n in res), 2), "moved_km": int(max(mx(res[n][1][k]) for n in res)),
                "sources": {n: {"f": f, "dsig": round(mx(res[n][0][k]), 2), "moved_km": int(mx(res[n][1][k]))} for n, f in fl.items() if f and f != "ok"}}

    def stat(a, q):
        a = a[np.isfinite(a)]
        return round(float(np.percentile(a, q)), 3) if len(a) else None
    allfin = np.concatenate([r[0][np.isfinite(r[0])] for r in res.values()])
    srcs = [{**info, "summary": {**per[n], "median_dsigma": stat(dsig, 50), "p95_dsigma": stat(dsig, 95)}} for n, (dsig, moved, info) in res.items()]
    doc = {"generated": time.strftime("%Y-%m-%d"), "n_models": max(x["n_models"] for x in srcs),
           "models": srcs[0]["models"], "scenarios": srcs[0]["scenarios"],
           "thresholds": {k: s[k] for k in ("sigma_moderate", "sigma_high", "moved_km")},
           "summary": {**counts, "median_dsigma": stat(allfin, 50), "p95_dsigma": stat(allfin, 95)},
           "sources": srcs, "places": places}
    out = out or OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(doc, open(out, "w"), separators=(",", ":"), ensure_ascii=False)
    C.save(C.work("nexcheck.npz"), labels=T.label.values.astype(str),
           **{f"dsig_{n}": r[0] for n, r in res.items()}, **{f"moved_km_{n}": r[1] for n, r in res.items()})
    C.log.info(summary_line(doc))
    return doc
