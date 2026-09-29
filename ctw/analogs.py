"""Sigma-dissimilarity analogs for every place (Mahony et al. 2017; Fitzpatrick & Dunn 2019).

North American places search the 15 km North American pool (AdaptWest temperature and precipitation,
TerraClimate humidity); world cities search the 0.5° global pool (TerraClimate). North American places whose
best match is poor are also searched worldwide (outside the US, Canada and Mexico) using their TerraClimate
present climate, so both sides of that comparison come from one dataset.
Every search runs twice over: for each (period, scenario) and, in the warming-level view, for each global warming level
(gwl.py, cmip6.py): each model's change over the 20-year window centred on the year it reaches the level, pooled over
the scenarios that reach it; ensembles average the models that reach the level.
Writes work/results.npz, which export.py packs for the page."""
from __future__ import annotations
import json, time
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from . import common as C
from . import features as F
from . import era5 as ERA5                            # (not E: run() uses E for the number of ensembles)

MON = ("tmax", "tmin", "ppt", "vap")
CORE3 = ("tmax", "tmin", "ppt")


def fill_nearest(A, valid_cells):
    """Fill NaNs of A (12, N) at valid_cells from the nearest finite column (humidity at coastal edge cells)."""
    fin = np.isfinite(A).all(0)
    need = valid_cells & ~fin
    if need.any() and fin.any():
        idx = np.nonzero(fin)[0]
        return idx, np.nonzero(need)[0]
    return None, None


def monthly_fill(mon, lat, lon, need_mask):
    """For each var in mon {(12, N)}, fill NaN columns inside need_mask with the nearest finite column."""
    xyz = C.unit_xyz(lat, lon)
    for v, A in mon.items():
        fin = np.isfinite(A).all(0)
        need = need_mask & ~fin
        if need.any() and fin.any():
            _, j = cKDTree(xyz[fin]).query(xyz[need])
            A[:, need] = A[:, np.nonzero(fin)[0][j]]
    return mon


def extras_future(names, bm, tx, tn, rsds_ratio, lat, pet_lim=(0.5, 3.0), srad_lim=(0.8, 1.25)):
    """Projected monthly extras (NT, 12) for the optional matched variables, as change factors on the observed
    TerraClimate baseline (like humidity). bm: baseline monthly {var: (NT, 12)} with tmax, tmin and the extras;
    tx, tn: projected monthly tmax, tmin (NT, 12).
      pet:  baseline PET x [HS(projected tmax, tmin) + 1] / [HS(baseline tmax, tmin) + 1], HS = Hargreaves-Samani
            monthly PET (mm; +1 keeps the ratio finite where PET is ~0), ratio limited to pet_lim.
      srad: baseline srad x the model's rsds ratio (projected / baseline), limited to srad_lim."""
    out = {}
    if "pet" in names:
        hb = C.hargreaves_pet(bm["tmax"].T, bm["tmin"].T, lat).T
        hf = C.hargreaves_pet(tx.T, tn.T, lat).T
        out["pet"] = bm["pet"] * np.clip((hf + 1.0) / (hb + 1.0), *pet_lim)
    if "srad" in names:
        out["srad"] = bm["srad"] * np.clip(rsds_ratio, *srad_lim)
    return out


def countries(cfg, lat, lon):
    """ISO code and name of each world cell (Natural Earth 1:50m; nearest country within 1° for coastal cells)."""
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    gj = json.load(open(C.download(cfg["sources"]["natural_earth"], C.work("downloads", "ne_50m_countries.geojson"))))["features"]
    geoms = [shape(f["geometry"]) for f in gj]
    iso = [f["properties"].get("ISO_A2_EH") or f["properties"].get("ISO_A2") for f in gj]
    tree = STRtree(geoms)
    pts = [Point(o, a) for a, o in zip(lat, lon)]
    ci = np.full(len(pts), -1)
    hit = tree.query(pts, predicate="intersects")
    ci[hit[0]] = hit[1]
    miss = np.where(ci < 0)[0]
    if len(miss):
        near = tree.query_nearest([pts[k] for k in miss], max_distance=1.0)
        ci[miss[near[0]]] = near[1]
    return np.array([iso[c] if c >= 0 else "" for c in ci])


def deltas(b, f, mcfg, ri=False):
    """A model's change from b to f (each (4, NT, 12): tmax, tmin, pr, huss): temperature differences and the
    precipitation and humidity ratios (limited to the configured range; humidity NaN where the model has none)."""
    lo_r, hi_r = mcfg["ppt_ratio"]; vlo, vhi = mcfg["vap_ratio"]
    with np.errstate(invalid="ignore", divide="ignore"):
        rp = np.clip(np.where(b[2] > 0, f[2] / b[2], 1.0), lo_r, hi_r)
        rv = np.clip(f[3] / b[3], vlo, vhi)
    if ri is False:
        return f[0] - b[0], f[1] - b[1], rp, rv
    with np.errstate(invalid="ignore", divide="ignore"):                # extras on: also the model's rsds ratio (1 = no change)
        rr = np.ones_like(b[0]) if ri is None else np.where(np.isfinite(f[ri] / b[ri]), f[ri] / b[ri], 1.0)
    return f[0] - b[0], f[1] - b[1], rp, rv, rr


def apply_delta(bm, d, xn=(), lat=None, mcfg=None):
    """Present monthly climate bm {tmax, tmin, ppt, vap: (NT, 12)} plus a model change -> projected monthly climate."""
    dtx, dtn, rp, rv = d[:4]
    tx = bm["tmax"] + dtx
    tn = np.minimum(bm["tmin"] + dtn, tx - 0.1)
    tm0 = (bm["tmax"] + bm["tmin"]) / 2
    rvv = np.where(np.isfinite(rv), rv, C.sat_vap(tm0 + (dtx + dtn) / 2) / C.sat_vap(tm0))   # constant RH
    mon = {"tmax": tx, "tmin": tn, "ppt": bm["ppt"] * rp, "vap": bm["vap"] * rvv}
    if xn:                                                              # optional extras (pet, srad), see extras_future
        mcfg = mcfg or {}
        mon |= extras_future(xn, bm, tx, tn, d[4], lat, mcfg.get("pet_ratio", (0.5, 3.0)), mcfg.get("srad_ratio", (0.8, 1.25)))
    return mon


def pick_sites(D, plat, plon, n, sep_km, first):
    order = np.argpartition(D, min(first, len(D) - 1))[:first]
    order = order[np.argsort(D[order])]
    alive = np.ones(len(order), bool)
    picked = []
    while len(picked) < n and alive.any():
        j = order[np.argmax(alive)]
        picked.append(int(j))
        alive &= C.haversine_km(plat[order], plon[order], plat[j], plon[j]) >= sep_km
    return picked


def extra_sensitivity(cfg, T, bad, LMS, na, wl, fut, ens, EN, best_idx, best_sig, SH, Kc, stride=None):
    """How much do the extras change the answer? Refits the standard (no extras) metric for each place, searches its
    pool again for every period x scenario x ensemble, and compares the best match with the one found with extras
    (best_idx/best_sig, method 0). Returns the summary that validate.py prints. Kc = number of standard measures."""
    mcfg = cfg["matching"]
    stride = stride or int(mcfg.get("extra_report_stride", 1))
    midx_core = C.match_idx(cfg)[:Kc]                        # standard measures come first in the matched set
    G = T.g.values
    P, S = fut.shape[1], fut.shape[2]
    km = np.full((len(T), P, S, len(EN)), np.nan); ds = np.full_like(km, np.nan)
    a_core, a_ext, k_core, k_ext = [], [], [], []
    for k in [k for k in np.where(~bad)[0] if k % stride == 0]:
        pool = na if G[k] == 0 else wl
        sm = C.ShrinkSigmaModel(LMS[k][:, :Kc])
        a_core.append(sm.alpha); a_ext.append(SH[k].alpha); k_core.append(sm.k); k_ext.append(SH[k].k)
        Pp = sm.project(pool["tr"][:, :Kc]).astype("float32")
        pn = (Pp ** 2).sum(1)
        for p in range(P):
            for s in range(S):
                fv = fut[k, p, s].astype("float64")
                evs = np.stack([fv[ens[en]].mean(0) for en in EN])
                Q = sm.project(C.transform(evs)[:, midx_core]).astype("float32")
                D2 = pn[:, None] - 2 * Pp @ Q.T + (Q ** 2).sum(1)[None]
                i0 = D2.argmin(0)
                for e in range(len(EN)):
                    i1 = int(best_idx[k, p, s, e, 0])
                    km[k, p, s, e] = C.haversine_km(pool["lat"][i0[e]], pool["lon"][i0[e]], pool["lat"][i1], pool["lon"][i1])
                    ds[k, p, s, e] = best_sig[k, p, s, e, 0] - C.chi_to_sigma(np.sqrt(max(D2[i0[e], e], 0)), sm.k)[0]
    thr = cfg["gates"]["moved_km"]
    ok = np.isfinite(km)

    def stat(m):
        if not (ok & m).any():
            return None
        x, d = km[ok & m], ds[ok & m]
        return dict(n=int(x.size), moved_share=float((x > thr).mean()), median_moved_km=float(np.median(x)),
                    median_abs_dsigma=float(np.median(np.abs(d))), median_dsigma=float(np.median(d)))
    grp = lambda g: np.broadcast_to((G == g)[:, None, None, None], km.shape)
    tot = stat(np.ones_like(ok))
    per_place = np.nanmean(np.where(ok, km > thr, np.nan), axis=(1, 2, 3))
    return dict(extras=list(C.extra_names(cfg)), seasons=list(mcfg.get("extra_seasons", [0, 2])), k_core=int(np.median(k_core)) if k_core else 0,
                k_with_extras=int(np.median(k_ext)) if k_ext else 0, alpha_core=float(np.median(a_core)) if a_core else None,
                alpha_with_extras=float(np.median(a_ext)) if a_ext else None, moved_km=thr, places=int(np.isfinite(per_place).sum()),
                places_moved_share=float(np.nanmean(per_place > 0.5)) if np.isfinite(per_place).any() else None,
                moved_share=tot["moved_share"] if tot else None, median_moved_km=tot["median_moved_km"] if tot else None,
                median_abs_dsigma=tot["median_abs_dsigma"] if tot else None, median_dsigma=tot["median_dsigma"] if tot else None,
                north_america=stat(grp(0)), world=stat(grp(1)))


def run(cfg=None):
    cfg = cfg or C.config()
    t0 = time.time()
    T = C.targets(); NT = len(T)
    G = T.g.values
    mcfg, g = cfg["matching"], cfg["grids"]
    XN = C.extra_names(cfg); C.use_extras(XN)                      # optional extra matched variables (default none)
    ALLM = MON + tuple(XN); NVX = C.nvx()
    midx = C.match_idx(cfg); K = len(midx)
    ms = C.models(cfg); NM = len(ms); ens = C.ensembles(cfg); EN = list(ens)
    P, S = len(cfg["periods"]["keys"]), len(cfg["scenarios"]["ids"])
    b0, b1 = cfg["baseline"]["years"]
    cal = F.calibration()
    tc = {v: C.load(C.work("terraclimate", f"{v}.npz")) for v in ALLM}
    for v in ALLM:
        assert list(tc[v]["labels"]) == T.label.tolist(), f"TerraClimate {v} was built for different places"
    y_first = int(tc["tmax"]["y_first"]); latest = int(tc["tmax"]["latest"])
    aw = C.load(C.work("adaptwest.npz"))
    pr = C.load(C.work("prism.npz"))

    # ---------------------------------------------------------------- pools
    lf = aw["landfrac"]
    ny, nx = lf.shape
    monNA = {v: aw[v].reshape(12, -1).astype("float64") for v in ("tmax", "tmin", "ppt")}
    for v in ("vap",) + tuple(XN):                                 # AdaptWest lacks these: TerraClimate on the 15 km grid
        monNA[v] = tc[v]["laea"].reshape(12, -1).astype("float64")
    xc = g["na_x0"] + (np.arange(nx) + .5) * g["na_cell_m"]
    yc = g["na_y0"] - (np.arange(ny) + .5) * g["na_cell_m"]
    XX, YY = np.meshgrid(xc, yc)
    glon, glat = Transformer.from_crs(g["na_crs"], "EPSG:4326", always_xy=True).transform(XX.ravel(), YY.ravel())
    s12 = C.seasonalize({v: monNA[v] for v in ("tmax", "tmin", "ppt")})[:12]
    validNA = (lf.ravel() >= g["na_landfrac_min"]) & np.isfinite(s12).all(0)
    monNA = monthly_fill({v: monNA[v] for v in ALLM[3:]}, glat, glon, validNA) | {v: monNA[v] for v in CORE3}
    cellsNA = np.nonzero(validNA)[0]
    na = dict(cells=cellsNA, rows=cellsNA // nx, cols=cellsNA % nx, lat=glat[cellsNA], lon=glon[cellsNA],
              mon={v: monNA[v][:, cellsNA] for v in ALLM}, km2=(g["na_cell_m"] / 1000) ** 2 * lf.ravel()[cellsNA])
    na["raw"] = C.seasonalize(na["mon"]).T
    NGY, NGX = tc["tmax"]["normals05"].shape[1:]
    la05 = 90 - (np.arange(NGY) + .5) * g["world_res"]
    lo05 = -180 + (np.arange(NGX) + .5) * g["world_res"]
    LA, LO = np.meshgrid(la05, lo05, indexing="ij")
    land = tc["tmax"]["land05"]
    monW = {v: tc[v]["normals05"].reshape(12, -1).astype("float64") for v in ALLM}
    w12 = C.seasonalize({v: monW[v] for v in ("tmax", "tmin", "ppt")})[:12]
    validW = (land.ravel() >= g["world_landfrac_min"]) & np.isfinite(w12).all(0) & (LA.ravel() > g["world_lat_min"])
    monW = monthly_fill({v: monW[v] for v in ALLM[3:]}, LA.ravel(), LO.ravel(), validW) | {v: monW[v] for v in CORE3}
    cellsW = np.nonzero(validW)[0]
    wl = dict(cells=cellsW, rows=cellsW // NGX, cols=cellsW % NGX, lat=LA.ravel()[cellsW], lon=LO.ravel()[cellsW],
              mon={v: monW[v][:, cellsW] for v in ALLM}, land=land.ravel()[cellsW])
    wl["km2"] = (g["world_res"] * 111.195) ** 2 * np.cos(np.radians(wl["lat"])) * wl["land"]
    wl["raw"] = C.seasonalize(wl["mon"]).T
    wl["iso"] = countries(cfg, wl["lat"], wl["lon"])
    for pool in (na, wl):
        pool["feat"] = F.all_features(pool["mon"]["tmax"], pool["mon"]["tmin"], pool["mon"]["ppt"], cal)
        pool["tr"] = C.transform(pool["raw"])[:, midx]
    C.log.info("pools: North America %d cells, world %d cells (%.0fs)", len(cellsNA), len(cellsW), time.time() - t0)

    # ---------------------------------------------------------------- baselines and year-to-year variability
    years_tc = tc["tmax"]["years"]
    bsel = (years_tc >= b0) & (years_tc <= b1)
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        tcbase = {v: np.nanmean(tc[v]["series"][:, bsel], axis=1).astype("float64") for v in ALLM}      # (NT, 12)
    base_m = {v: tcbase[v].copy() for v in ALLM}
    naT = G == 0
    for v in ("tmax", "tmin", "ppt"):
        base_m[v][naT] = aw["t_" + v][naT]
    base = C.seasonalize({v: base_m[v].T for v in ALLM}).T                                   # (NT, 16)
    tcvec = C.seasonalize({v: tcbase[v].T for v in ALLM}).T
    base_years = list(range(b0, b1 + 1))
    icv_src = np.where(T.domain.values == "conus", "PRISM", "TerraClimate")
    icv = []
    for k in range(NT):
        sv = C.seasonal_years({v: tc[v]["series"][k] for v in ALLM}, years_tc, base_years)
        if icv_src[k] == "PRISM":
            sy = C.seasonal_years({v: pr[v][k] for v in ("tmax", "tmin", "ppt")}, pr["years"], base_years)
            sy[:, 12:] = sv[:, 12:]                                # dewpoint and any extras: TerraClimate
            sv = sy
        icv.append(sv[np.isfinite(sv[:, midx]).all(1)])        # the baseline years present in every source
    n_icv = np.array([len(x) for x in icv])
    bad = (n_icv < (5 if C.SMOKE else 20)) | ~np.isfinite(base).all(1)
    LMS = {}
    SH, TR, icvsd, floored = [None] * NT, [None] * NT, np.full((NT, NVX), np.nan), []
    for k in np.where(~bad)[0]:
        L = C.transform(icv[k])
        Lm, nfl = C.floor_icv(L[:, midx], mcfg["floor"])
        if nfl:
            floored.append((T.label[k], nfl))
        if XN:
            LMS[k] = Lm
        SH[k] = C.ShrinkSigmaModel(Lm)
        TR[k] = C.TruncSigmaModel(Lm, mcfg["min_var_frac"])
        full = L.copy(); full[:, midx] = Lm
        icvsd[k] = C.detrend(full).std(0, ddof=1)
    C.log.info("variability: %d places floored, %d unusable: %s; years used median %d", len(floored), int(bad.sum()), T.label[bad].tolist(), int(np.median(n_icv)))

    # ---------------------------------------------------------------- projected climates
    fut = np.full((NT, P, S, NM, NVX), np.nan, "float32")
    futTC = np.full((NT, P, S, NM, NVX), np.nan, "float32")          # North American places on TerraClimate footing
    ens_mon = np.zeros((P, S, len(EN), 3, NT, 12))                     # ensemble-mean monthly tmax, tmin, ppt
    cc_fill = []; x_fill = []
    levels = list(cfg["gwl"]["levels"]); NG = len(levels); gmin = int(cfg["gwl"]["min_models"])
    gfut = np.full((NT, NG, NM, NVX), np.nan, "float32"); gfutTC = np.full((NT, NG, NM, NVX), np.nan, "float32")
    gens_mon = np.zeros((NG, len(EN), 3, NT, 12)); greach = np.zeros((NG, NM), bool)
    gyear = np.zeros((NG, NM, S), "int16"); gwl_now = np.full(NM, np.nan)
    for mi, m in enumerate(ms):
        cm = C.load(C.work("cmip6", f"{m['name']}.npz"))
        assert list(cm["labels"]) == T.label.tolist(), f"{m['name']} was built for different places"
        ri = list(cm["vars"]).index("rsds") if "rsds" in list(cm["vars"]) else None
        if "srad" in XN and (ri is None or not np.isfinite(cm["fut"][:, :, ri]).all()):
            x_fill.append(m["name"])
        for p in range(P):
            for s in range(S):
                b, f = cm["base"][s].astype("float64"), cm["fut"][p, s].astype("float64")     # (4, NT, 12)
                d = deltas(b, f, mcfg, ri if XN else False); rv = d[3]
                for which, bm in ((fut, base_m), (futTC, tcbase)):
                    mon = apply_delta(bm, d, XN, T.lat.values, mcfg); tx, tn = mon["tmax"], mon["tmin"]
                    which[:, p, s, mi] = C.seasonalize({v: mon[v].T for v in ALLM}).T
                    if which is fut:
                        for e, en in enumerate(EN):
                            if mi in ens[en]:
                                ens_mon[p, s, e, 0] += tx / len(ens[en]); ens_mon[p, s, e, 1] += tn / len(ens[en])
                                ens_mon[p, s, e, 2] += mon["ppt"] / len(ens[en])
                if not np.isfinite(rv).all() and p == 0:
                    cc_fill.append(f"{m['name']} {cfg['scenarios']['labels'][s]}")
        # warming levels: pool the change over the scenarios in which this model reaches each level
        assert np.allclose(cm["gwl_levels"], levels), f"{m['name']} was built for different warming levels"
        gyear[:, mi] = cm["gwl_year"]; gwl_now[mi] = float(cm["gwl_now"])
        for gi in range(NG):
            ds = [deltas(cm["base"][s].astype("float64"), cm["gwl_fut"][gi, s].astype("float64"), mcfg, ri if XN else False) for s in range(S) if cm["gwl_year"][gi, s] > 0]
            if not ds:
                continue
            with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
                __import__("warnings").simplefilter("ignore")
                d = tuple(np.nanmean([x[j] for x in ds], axis=0) for j in range(len(ds[0])))
            greach[gi, mi] = True
            for which, bm in ((gfut, base_m), (gfutTC, tcbase)):
                mon = apply_delta(bm, d, XN, T.lat.values, mcfg)
                which[:, gi, mi] = C.seasonalize({v: mon[v].T for v in ALLM}).T
                if which is gfut:
                    for e, en in enumerate(EN):
                        if mi in ens[en]:
                            gens_mon[gi, e, 0] += mon["tmax"]; gens_mon[gi, e, 1] += mon["tmin"]; gens_mon[gi, e, 2] += mon["ppt"]
    gn = np.array([[int(sum(greach[gi, mi] for mi in ens[en])) for en in EN] for gi in range(NG)])       # models per level and ensemble
    gok = gn >= gmin                                                    # levels too few models reach are not offered
    for gi in range(NG):
        for e in range(len(EN)):
            gens_mon[gi, e] /= max(gn[gi, e], 1)
    C.log.info("projections done (%.0fs); humidity filled by constant relative humidity for: %s", time.time() - t0, cc_fill)
    C.log.info("warming levels %s: models reaching each (all, tcr_likely): %s", levels, gn.tolist())

    # ---------------------------------------------------------------- searches
    E = len(EN)
    best_idx = np.full((NT, P, S, E, 2), -1, "int32"); best_sig = np.full((NT, P, S, E, 2), np.nan, "float32")
    sites = np.full((NT, P, S, E, mcfg["sites"]), -1, "int32"); site_sig = np.full((NT, P, S, E, mcfg["sites"]), np.nan, "float32")
    area2 = np.zeros((NT, P, S, E), "float32"); own = np.full((NT, P, S, E), np.nan, "float32")
    agree = np.full((NT, P, S, E), np.nan, "float32"); selfchk = np.full(NT, np.nan, "float32")
    gbest_idx = np.full((NT, NG, E, 2), -1, "int32"); gbest_sig = np.full((NT, NG, E, 2), np.nan, "float32")
    garea2 = np.zeros((NT, NG, E), "float32")
    glob, gglob = {}, {}
    notNA = ~np.isin(wl["iso"], ["US", "CA", "MX"]) & (wl["iso"] != "")
    gsub = np.nonzero(notNA)[0]
    for k in np.where(~bad)[0]:
        pool = na if G[k] == 0 else wl
        sep = mcfg["sep_km_na"] if G[k] == 0 else mcfg["sep_km_world"]
        first = 20000 if G[k] == 0 else 5000
        for meth, sm in enumerate((SH[k], TR[k])):
            Pp = sm.project(pool["tr"]).astype("float32")
            pn = (Pp ** 2).sum(1)
            own_p = sm.project(C.transform(base[k])[midx])[0]
            if meth == 0:
                Ds = np.sqrt(np.maximum(pn - 2 * Pp @ own_p.astype("float32") + (own_p ** 2).sum(), 0))
                selfchk[k] = C.chi_to_sigma(Ds.min(), sm.k)[0]
            dthr = C.d_at_sigma(2.0, sm.k)
            for p in range(P):
                for s in range(S):
                    fv = fut[k, p, s].astype("float64")
                    evs = np.stack([fv[ens[en]].mean(0) for en in EN])
                    Q = sm.project(C.transform(np.vstack([fv, evs]))[:, midx]).astype("float32")
                    D2 = pn[:, None] - 2 * Pp @ Q.T + (Q ** 2).sum(1)[None]
                    am = D2.argmin(0)
                    for e, en in enumerate(EN):
                        D = np.sqrt(np.maximum(D2[:, NM + e], 0))
                        i = int(am[NM + e])
                        best_idx[k, p, s, e, meth] = i
                        best_sig[k, p, s, e, meth] = C.chi_to_sigma(D[i], sm.k)[0]
                        if meth:
                            continue
                        own[k, p, s, e] = C.chi_to_sigma(np.sqrt(((Q[NM + e] - own_p) ** 2).sum()), sm.k)[0]
                        mb = am[ens[en]]
                        agree[k, p, s, e] = np.mean(C.haversine_km(pool["lat"][mb], pool["lon"][mb], pool["lat"][i], pool["lon"][i]) < mcfg["agree_km"])
                        area2[k, p, s, e] = pool["km2"][D < dthr].sum()
                        pk = pick_sites(D, pool["lat"], pool["lon"], mcfg["sites"], sep, first)
                        sites[k, p, s, e, :len(pk)] = pk
                        site_sig[k, p, s, e, :len(pk)] = C.chi_to_sigma(D[pk], sm.k)
            for gi in range(NG):                                     # warming levels: ensembles of the models that reach each
                fv = gfut[k, gi].astype("float64")
                evs = np.stack([np.nanmean(fv[[i for i in ens[en] if greach[gi, i]]], 0) if gok[gi, e] else np.full(NVX, np.nan)
                                for e, en in enumerate(EN)])
                Q = sm.project(C.transform(np.where(np.isfinite(evs), evs, 0.0))[:, midx]).astype("float32")
                D2 = pn[:, None] - 2 * Pp @ Q.T + (Q ** 2).sum(1)[None]
                for e in range(E):
                    if not gok[gi, e]:
                        continue
                    D = np.sqrt(np.maximum(D2[:, e], 0)); i = int(D.argmin())
                    gbest_idx[k, gi, e, meth] = i
                    gbest_sig[k, gi, e, meth] = C.chi_to_sigma(D[i], sm.k)[0]
                    if not meth:
                        garea2[k, gi, e] = pool["km2"][D < dthr].sum()
        # worldwide matches for North American places whose best North American match is poor
        if G[k] == 0:
            need = [(p, s, e) for p in range(P) for s in range(S) for e in range(E) if best_sig[k, p, s, e, 0] >= mcfg["glob_trigger_sigma"]]
            if need:
                sm = SH[k]
                Pg = sm.project(wl["tr"][gsub]).astype("float32")
                pg = (Pg ** 2).sum(1)
                glat, glon = wl["lat"][gsub], wl["lon"][gsub]
                for p, s, e in need:
                    fv = futTC[k, p, s].astype("float64")
                    ev = fv[ens[EN[e]]].mean(0)
                    Q = sm.project(C.transform(np.vstack([fv, ev]))[:, midx]).astype("float32")
                    D2 = pg[:, None] - 2 * Pg @ Q.T + (Q ** 2).sum(1)[None]
                    am = D2.argmin(0)
                    D = np.sqrt(np.maximum(D2[:, -1], 0))
                    i = int(am[-1])
                    mb = am[ens[EN[e]]]
                    pk = pick_sites(D, glat, glon, mcfg["sites"], mcfg["sep_km_world"], 3000)
                    glob[(k, p, s, e)] = dict(s=float(C.chi_to_sigma(D[i], sm.k)[0]), n=len(ens[EN[e]]),
                                              a=int((C.haversine_km(glat[mb], glon[mb], glat[i], glon[i]) < mcfg["agree_km_world"]).sum()),
                                              cells=[int(gsub[j]) for j in pk], sig=[float(x) for x in C.chi_to_sigma(D[pk], sm.k)])
            gneed = [(gi, e) for gi in range(NG) for e in range(E) if gok[gi, e] and gbest_sig[k, gi, e, 0] >= mcfg["glob_trigger_sigma"]]
            if gneed:                                              # the same worldwide search for the warming levels
                sm = SH[k]
                Pg = sm.project(wl["tr"][gsub]).astype("float32")
                pg = (Pg ** 2).sum(1)
                glat, glon = wl["lat"][gsub], wl["lon"][gsub]
                for gi, e in gneed:
                    rm = [i for i in ens[EN[e]] if greach[gi, i]]
                    fv = gfutTC[k, gi].astype("float64")
                    Q = sm.project(C.transform(np.vstack([fv, fv[rm].mean(0)]))[:, midx]).astype("float32")
                    D2 = pg[:, None] - 2 * Pg @ Q.T + (Q ** 2).sum(1)[None]
                    am = D2.argmin(0)
                    D = np.sqrt(np.maximum(D2[:, -1], 0))
                    i = int(am[-1])
                    mb = am[rm]
                    pk = pick_sites(D, glat, glon, mcfg["sites"], mcfg["sep_km_world"], 3000)
                    gglob[(k, gi, e)] = dict(s=float(C.chi_to_sigma(D[i], sm.k)[0]), n=len(rm),
                                             a=int((C.haversine_km(glat[mb], glon[mb], glat[i], glon[i]) < mcfg["agree_km_world"]).sum()),
                                             cells=[int(gsub[j]) for j in pk], sig=[float(x) for x in C.chi_to_sigma(D[pk], sm.k)])
        if k % 100 == 0:
            C.log.info("searched %d/%d %s (%.0fs)", k, NT, T.label[k], time.time() - t0)

    # ---------------------------------------------------------------- sensitivity to the extra variables
    if XN and mcfg.get("extra_report", True):
        sens = extra_sensitivity(cfg, T, bad, LMS, na, wl, fut, ens, EN, best_idx, best_sig, SH, len(midx) - len(XN) * len(mcfg.get("extra_seasons", [0, 2])))
        json.dump(sens, open(C.work("extra_sensitivity.json"), "w"), indent=1)
        C.log.info("extras %s: %.1f%% of best matches moved > %d km, median |dsigma| %.2f (%.0fs)", XN,
                   100 * sens["moved_share"], cfg["gates"]["moved_km"], sens["median_abs_dsigma"], time.time() - t0)

    # ---------------------------------------------------------------- features, recent climate, checks
    fnow = F.all_features(base_m["tmax"].T, base_m["tmin"].T, base_m["ppt"].T, cal)
    ffut = {kk: np.zeros((NT, P, S, E), v.dtype) for kk, v in fnow.items()}
    for p in range(P):
        for s in range(S):
            for e in range(E):
                fe = F.all_features(ens_mon[p, s, e, 0].T, ens_mon[p, s, e, 1].T, ens_mon[p, s, e, 2].T, cal)
                for kk in fe:
                    ffut[kk][:, p, s, e] = fe[kk]
    gffut = {kk: np.zeros((NT, NG, E), v.dtype) for kk, v in fnow.items()}          # warming-level features
    for gi in range(NG):
        for e in range(E):
            if gok[gi, e]:
                fe = F.all_features(gens_mon[gi, e, 0].T, gens_mon[gi, e, 1].T, gens_mon[gi, e, 2].T, cal)
                for kk in fe:
                    gffut[kk][:, gi, e] = fe[kk]
    n_rec = cfg["recent"]["years"]
    rec_years = [y for y in range(latest - n_rec + 1, latest + 1) if y in set(years_tc.tolist())]
    base_have = [y for y in base_years if y in set(years_tc.tolist())]
    recent = np.full((NT, NVX), np.nan)
    rec_sig = np.full(NT, np.nan, "float32")
    tc_check = np.full(NT, np.nan, "float32")
    for k in np.where(~bad)[0]:
        ser = {v: tc[v]["series"][k] for v in ALLM}
        rv = np.nanmean(C.seasonal_years(ser, years_tc, rec_years), 0)
        bv = np.nanmean(C.seasonal_years(ser, years_tc, base_have), 0)
        recent[k] = rv - bv
        a, b = SH[k].project(C.transform(rv)[midx])[0], SH[k].project(C.transform(bv)[midx])[0]
        rec_sig[k] = C.chi_to_sigma(np.sqrt(((a - b) ** 2).sum()), SH[k].k)[0]
        if G[k] == 0:
            a = SH[k].project(C.transform(base[k])[midx])[0]
            b = SH[k].project(C.transform(tcvec[k])[midx])[0]
            tc_check[k] = C.chi_to_sigma(np.sqrt(((a - b) ** 2).sum()), SH[k].k)[0]
    recent[:, C.NV:] = 0.0                                               # the page shows recent change for the 16 standard measures only
    ref = C.transform(recent)                                            # precipitation anomaly as a log ratio
    ref[:, C.PPT] = np.log((np.maximum(tcvec[:, C.PPT] + recent[:, C.PPT], 0) + 1) / (tcvec[:, C.PPT] + 1))
    C.log.info("recent climate %d-%d; self-check median %.2f sigma; TerraClimate vs AdaptWest median %.2f sigma",
               rec_years[0], rec_years[-1], np.nanmedian(selfchk), np.nanmedian(tc_check))

    # ---------------------------------------------------------------- baseline agreement with ERA5 (independent dataset)
    era5_sig = np.full(NT, np.nan, "float32"); era5_diff = np.full((NT, NVX), np.nan, "float32")   # BEGIN era5-agreement
    e5 = ERA5.load_series(T)
    if e5 is None:
        C.log.warning("no ERA5 files in work/era5: baseline agreement not computed")
    else:
        eb = ERA5.baseline_vectors(e5, b0, b1)
        eb[:, C.NV:] = base[:, C.NV:]                       # extras (pet, srad) have no ERA5 counterpart here: zero difference, so agreement reflects the standard measures
        ok5 = ~bad & np.isfinite(eb[:, midx]).all(1) & np.isfinite(base[:, midx]).all(1)
        e5off = ERA5.offsets(base[ok5], eb[ok5], G[ok5])
        era5_raw = np.full(NT, np.nan, "float32")
        for k in np.where(ok5)[0]:
            era5_sig[k] = ERA5.agreement(SH[k], midx, base[k], eb[k], e5off[G[k]])
            era5_raw[k] = ERA5.agreement(SH[k], midx, base[k], eb[k])
            era5_diff[k] = eb[k] - base[k]
        C.log.info("ERA5 typical offsets (transformed units) NA %s | world %s", np.round(e5off[0], 2).tolist(), np.round(e5off[1], 2).tolist())
        C.log.info("ERA5 raw agreement median %.2f sigma", np.nanmedian(era5_raw))
        C.log.info("ERA5 baseline agreement: median %.2f sigma, %d places over %.1f, %d over %.1f", np.nanmedian(era5_sig),
                   int((era5_sig > cfg["era5"]["agree_fair"]).sum()), cfg["era5"]["agree_fair"],
                   int((era5_sig > cfg["era5"]["agree_poor"]).sum()), cfg["era5"]["agree_poor"])   # END era5-agreement

    gk = sorted(glob)
    ggk = sorted(gglob)
    ns = mcfg["sites"]
    C.save(C.work("results.npz"),
           midx=midx, bad=bad, icv_src=icv_src, base=base.astype("float32"), base_mon=np.stack([base_m[v] for v in MON]).astype("float32"), fut=fut, icvsd=icvsd.astype("float32"),
           Msh=np.array([SH[k].M() if SH[k] else np.full((K, K), np.nan) for k in range(NT)], "float32"),
           Mtr=np.array([TR[k].M(K) if TR[k] else np.full((K, K), np.nan) for k in range(NT)], "float32"),
           kdef=np.array([TR[k].k if TR[k] else 0 for k in range(NT)]), alpha=np.array([SH[k].alpha if SH[k] else np.nan for k in range(NT)]),
           best_idx=best_idx, best_sig=best_sig, sites=sites, site_sig=site_sig, area2=area2, own=own, agree=agree, selfchk=selfchk,
           tc_check=tc_check, era5_sig=era5_sig, era5_diff=era5_diff, era5_raw=era5_raw if e5 is not None else np.full(NT, np.nan, "float32"), recent=ref.astype("float32"), rec_sig=rec_sig, rec_years=np.array([rec_years[0], rec_years[-1]]), n_icv=n_icv,
           floored=np.array([f"{a}:{b}" for a, b in floored]), cc_fill=np.array(cc_fill), x_names=np.array(XN, dtype=str), x_fill=np.array(x_fill, dtype=str),
           f_now_kg=fnow["kg"], f_now_zone=fnow["zone"], f_now_ffp=fnow["ffp"],
           f_fut_kg=ffut["kg"], f_fut_zone=ffut["zone"], f_fut_ffp=ffut["ffp"],
           na_cells=na["cells"], na_lat=na["lat"], na_lon=na["lon"], na_raw=na["raw"].astype("float32"),
           na_kg=na["feat"]["kg"], na_zone=na["feat"]["zone"], na_ffp=na["feat"]["ffp"],
           w_cells=wl["cells"], w_lat=wl["lat"], w_lon=wl["lon"], w_raw=wl["raw"].astype("float32"), w_land=wl["land"].astype("float32"),
           w_iso=wl["iso"], w_kg=wl["feat"]["kg"], w_zone=wl["feat"]["zone"], w_ffp=wl["feat"]["ffp"],
           glob_keys=np.array(gk, "int32").reshape(-1, 4), glob_s=np.array([glob[x]["s"] for x in gk], "float32"),
           glob_a=np.array([glob[x]["a"] for x in gk], "int32"), glob_n=np.array([glob[x]["n"] for x in gk], "int32"),
           glob_cells=np.array([glob[x]["cells"] + [-1] * (mcfg["sites"] - len(glob[x]["cells"])) for x in gk], "int32").reshape(-1, mcfg["sites"]),
           glob_sig=np.array([glob[x]["sig"] + [np.nan] * (mcfg["sites"] - len(glob[x]["sig"])) for x in gk], "float32").reshape(-1, mcfg["sites"]),
           gwl_levels=np.array(levels, "float64"), gwl_fut=gfut, gwl_reach=greach, gwl_year=gyear, gwl_n=gn, gwl_ok=gok, gwl_now=gwl_now,
           gwl_best_idx=gbest_idx, gwl_best_sig=gbest_sig, gwl_area2=garea2,
           gf_kg=gffut["kg"], gf_zone=gffut["zone"], gf_ffp=gffut["ffp"],
           gglob_keys=np.array(ggk, "int32").reshape(-1, 3), gglob_s=np.array([gglob[x]["s"] for x in ggk], "float32"),
           gglob_a=np.array([gglob[x]["a"] for x in ggk], "int32"), gglob_n=np.array([gglob[x]["n"] for x in ggk], "int32"),
           gglob_cells=np.array([gglob[x]["cells"] + [-1] * (ns - len(gglob[x]["cells"])) for x in ggk], "int32").reshape(-1, ns),
           gglob_sig=np.array([gglob[x]["sig"] + [np.nan] * (ns - len(gglob[x]["sig"])) for x in ggk], "float32").reshape(-1, ns),
           latest=np.array(latest), data_years=np.array([b0, b1]))
    C.log.info("analogs done (%.0fs)", time.time() - t0)
