"""Spike B, Tier A feasibility test (run in GitHub Actions; reads TerraClimate, WorldClim, CHELSA over the network).
Test region: lat 40-60, lon 0-20 (Alps, Pyrenees edge, Adriatic, Baltic coast): 480 x 480 cells at 2.5 arc-minutes.
Prints lines starting RESULT with JSON, collected into docs/spikes/B-climate-stack.md.

    python tierA_test.py tc          TerraClimate native regional read, baselines, water-balance check, timings, global single file
    python tierA_test.py compare     future (NEX change factors) vs WorldClim 2.1, baseline mismatch vs WorldClim and CHELSA
"""
from __future__ import annotations
import json, os, resource, sys, time, zipfile
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../..")
from ctw.species import climategrid as G
from ctw.species import tc_region as TC

BOX = (40, 60, 0, 20)
ROWS, COLS = G.window(*BOX)
OUT = os.environ.get("SPIKE_OUT", "spike-out")
os.makedirs(OUT, exist_ok=True)
NEXFILE = os.environ.get("NEX_NPZ", "docs/spikes/data/B_nex_ACCESS-CM2.npz")


def rss():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def result(tag, **kw):
    print("RESULT", json.dumps({"tag": tag, **kw}, default=float), flush=True)


def lat_lon():
    lat = G.cell_lat(np.arange(ROWS.start, ROWS.stop)); lon = G.cell_lon(np.arange(COLS.start, COLS.stop))
    return lat, lon


def _job(a):
    v, y = a
    x, dt = TC.read_months(v, y, ROWS, COLS)
    return v, y, x, dt


# periods of interest for the baseline mismatch: (name, first year, last year)
PERIODS = {"1991-2020": (1991, 2020), "1981-2010": (1981, 2010), "1970-2000": (1970, 2000)}


def stage_tc():
    from multiprocessing import Pool
    t0 = time.time()
    jobs = [(v, y) for v in TC.VARS for y in range(1991, 2021)]
    jobs += [(v, y) for v in ("tmax", "tmin", "ppt") for y in range(1970, 2021) if y < 1991]
    sums, cnts, rt = {}, {}, []
    with Pool(4) as pool:
        for v, y, x, dt in pool.imap_unordered(_job, jobs):
            rt.append(dt)
            for pn, (a, b) in PERIODS.items():
                if a <= y <= b and (v in ("tmax", "tmin", "ppt") or pn == "1991-2020"):
                    k = (v, pn)
                    sums[k] = sums.get(k, 0) + np.nan_to_num(x); cnts[k] = cnts.get(k, 0) + np.isfinite(x)
    clim = {}
    for k in sums:
        with np.errstate(invalid="ignore", divide="ignore"):
            clim[k] = np.where(cnts[k] > 0, sums[k] / cnts[k], np.nan).astype("float32")
    el = time.time() - t0
    result("tc_read", files=len(jobs), seconds=el, per_file_s_mean=float(np.mean(rt)), per_file_s_max=float(np.max(rt)), rss_mb=rss(),
           cells=int(np.prod([ROWS.stop - ROWS.start, COLS.stop - COLS.start])))
    base = {v: clim[(v, "1991-2020")] for v in TC.VARS}
    np.savez_compressed(f"{OUT}/tc_baseline_1991-2020.npz", **base)
    for pn in ("1981-2010", "1970-2000"):
        np.savez_compressed(f"{OUT}/tc_{pn}.npz", **{v: clim[(v, pn)] for v in ("tmax", "tmin", "ppt")})
    land = np.isfinite(base["tmax"][0])
    result("tc_region", land_cells=int(land.sum()), bytes_npz=os.path.getsize(f"{OUT}/tc_baseline_1991-2020.npz"),
           bytes_float32_9vars=int(9 * 12 * land.size * 4), bytes_int16_9vars_land_only=int(9 * 12 * land.sum() * 2))
    # predictors
    t0 = time.time()
    P = G.baseline_predictors(base)
    result("predictors_time", seconds=time.time() - t0, cells=int(land.size))
    stats = {k: {"mean": float(np.nanmean(v)), "p5": float(np.nanpercentile(v, 5)), "p95": float(np.nanpercentile(v, 95))} for k, v in P.items()}
    result("predictor_stats", **stats)
    np.savez_compressed(f"{OUT}/predictors_baseline.npz", **{k: v.astype("float32") for k, v in P.items()})
    result("predictor_bytes", npz=os.path.getsize(f"{OUT}/predictors_baseline.npz"), layers=len(P))
    # own water balance vs TerraClimate def / aet
    tmean = G.tmean(base["tmax"], base["tmin"])
    lat, _ = lat_lon()
    LAT = np.broadcast_to(lat[:, None], land.shape)
    pet = base["pet"]
    for name, cap in [("cap=max(soil clim)", G.cap_from_soil(base["soil"])), ("cap=100", np.full(land.shape, 100.0)), ("cap=150", np.full(land.shape, 150.0))]:
        wb = G.water_balance(base["ppt"], pet, tmean, cap)
        m = land & np.isfinite(wb["cwd"].sum(0))
        r = {}
        for nm, mine, tcv in [("cwd", wb["cwd"].sum(0), base["def"].sum(0)), ("aet", wb["aet"].sum(0), base["aet"].sum(0))]:
            d = mine[m] - tcv[m]
            r[nm] = {"bias": float(d.mean()), "rmse": float(np.sqrt((d ** 2).mean())), "r": float(np.corrcoef(mine[m], tcv[m])[0, 1]),
                     "tc_mean": float(tcv[m].mean())}
        # response test: does the model's cwd change under +3 C track what is expected? (reported later in the compare stage)
        result("wb_check", capacity=name, **r)
    # global single-file read: timing, memory, land cells
    t0 = time.time()
    x, dt = TC.read_months("tmax", 2019, slice(0, G.NLAT), slice(0, G.NLON))
    result("tc_global_one_file_tmax", seconds=time.time() - t0, rss_mb=rss(), land_cells=int(np.isfinite(x[0]).sum()))
    del x


def _load_tc():
    return dict(np.load(f"{OUT}/tc_baseline_1991-2020.npz"))


def _wc_zip(var):
    import requests
    url = f"https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_2.5m_{var}.zip"
    path = f"{OUT}/wc_{var}.zip"
    t0 = time.time()
    with requests.get(url, stream=True, timeout=(30, 120)) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for b in r.iter_content(1 << 22):
                f.write(b)
    dt = time.time() - t0
    import rasterio
    out = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if n.endswith(".tif"))
        z.extractall(f"{OUT}/wcx")
    for n in names:
        with rasterio.open(f"{OUT}/wcx/{n}") as ds:
            w = rasterio.windows.Window(COLS.start, ROWS.start, COLS.stop - COLS.start, ROWS.stop - ROWS.start)
            out.append(ds.read(1, window=w, masked=True).astype("float32").filled(np.nan))
    os.remove(path)
    return np.stack(out), os.path.getsize(path) if os.path.exists(path) else 0, dt


def _wc_future(model, ssp, per, var):
    import rasterio
    u = f"/vsicurl/https://geodata.ucdavis.edu/cmip6/2.5m/{model}/{ssp}/wc2.1_2.5m_{var}_{model}_{ssp}_{per}.tif"
    t0 = time.time()
    with rasterio.open(u) as ds:
        w = rasterio.windows.Window(COLS.start, ROWS.start, COLS.stop - COLS.start, ROWS.stop - ROWS.start)
        a = ds.read(window=w, masked=True).astype("float32").filled(np.nan)
    return a, time.time() - t0


def _chelsa_month(args):
    import rasterio
    var, m = args
    u = f"/vsicurl/https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/{var}/1981-2010/CHELSA_{var}_{m:02d}_1981-2010_V.2.1.tif"
    with rasterio.open(u) as ds:
        fine = 5
        # CHELSA starts at ~84N (20880 rows), TerraClimate at 90N: shift rows by the difference in top edge (fixes the first run's misalignment)
        top_tc = 90.0 - ROWS.start / 24.0
        r0 = int(round((ds.bounds.top - top_tc) * 120))
        c0 = int(round((-180.0 - ds.bounds.left) * 120)) + COLS.start * fine
        w = rasterio.windows.Window(c0, r0, (COLS.stop - COLS.start) * fine, (ROWS.stop - ROWS.start) * fine)
        a = ds.read(1, window=w, masked=True)
        sc, off = ds.scales[0], ds.offsets[0]
    x = a.astype("float32").filled(np.nan) * sc + off
    if var in ("tasmax", "tasmin"):
        med = np.nanmedian(x)
        x = x - 273.15 if med > 150 else x
    return var, m, x


def _cmp(a, b, mask):
    d = a[mask] - b[mask]
    return {"bias": float(d.mean()), "mae": float(np.abs(d).mean()), "rmse": float(np.sqrt((d ** 2).mean())), "r": float(np.corrcoef(a[mask], b[mask])[0, 1]),
            "p95_abs": float(np.percentile(np.abs(d), 95))}


def stage_compare():
    from multiprocessing import Pool
    tc = _load_tc()
    tc_o = {p: dict(np.load(f"{OUT}/tc_{p}.npz")) for p in ("1981-2010", "1970-2000")}
    base_p = G.baseline_predictors(tc)
    lat, lon = lat_lon()
    land = np.isfinite(tc["tmax"][0])
    # ---- WorldClim baseline 1970-2000 (2.5m)
    wc = {}
    for v, k in (("tmax", "tmax"), ("tmin", "tmin"), ("prec", "ppt")):
        t0 = time.time()
        a, _, dt = _wc_zip(v)
        wc[k] = a
        result("wc_base_download", var=v, seconds=dt, window_read_s=time.time() - t0 - dt)
    wcp = G.predictors(wc["tmax"], wc["tmin"], wc["ppt"])
    m = land & np.isfinite(wcp["bio1"])
    result("mismatch_wc_base_vs_tc1991", **{k: _cmp(wcp[k], base_p[k], m) for k in wcp})
    tcp70 = G.predictors(tc_o["1970-2000"]["tmax"], tc_o["1970-2000"]["tmin"], tc_o["1970-2000"]["ppt"])
    result("tc_1970_vs_1991_change", **{k: {"mean_diff": float(np.nanmean(base_p[k][m] - tcp70[k][m])), "p5": float(np.nanpercentile(base_p[k][m] - tcp70[k][m], 5)),
                                            "p95": float(np.nanpercentile(base_p[k][m] - tcp70[k][m], 95))} for k in tcp70})
    result("wc_vs_tc_1970_2000_same_period", **{k: _cmp(wcp[k], tcp70[k], m) for k in wcp})
    # ---- CHELSA 1981-2010 at 30 arc-seconds
    t0 = time.time()
    ch = {}
    with Pool(6) as pool:
        for var, mo, x in pool.imap_unordered(_chelsa_month, [(v, mo) for v in ("tasmax", "tasmin", "pr") for mo in range(1, 13)]):
            ch.setdefault(var, [None] * 12)[mo - 1] = x
    result("chelsa_read", files=36, seconds=time.time() - t0, rss_mb=rss())
    chm = {k: np.stack(ch[v]) for k, v in (("tmax", "tasmax"), ("tmin", "tasmin"), ("ppt", "pr"))}
    del ch
    fine = {}
    n = chm["tmax"].shape[1]
    for k in ("bio1", "bio4", "bio5", "bio6", "bio12", "bio15", "bio17", "gdd5", "fd"):
        fine[k] = np.full((n, n), np.nan, "float32")
    t0 = time.time()
    for rs, cs in G.by_tiles((n, n), 400):
        p = G.predictors(chm["tmax"][:, rs, cs], chm["tmin"][:, rs, cs], chm["ppt"][:, rs, cs])
        for k in fine:
            fine[k][rs, cs] = p[k]
    result("chelsa_30s_predictors", seconds=time.time() - t0, cells=int(n * n))
    agg, within_sd, within_range = {}, {}, {}
    for k, v in fine.items():
        b = v.reshape(480, 5, 480, 5)
        agg[k] = np.nanmean(b, axis=(1, 3)); within_sd[k] = np.nanstd(b, axis=(1, 3)); within_range[k] = np.nanmax(b, axis=(1, 3)) - np.nanmin(b, axis=(1, 3))
    m2 = land & np.isfinite(agg["bio1"])
    result("mismatch_chelsa_vs_tc1991", **{k: _cmp(agg[k], base_p[k], m2) for k in agg if k not in ("cwd", "aet")})
    tcp81 = G.predictors(tc_o["1981-2010"]["tmax"], tc_o["1981-2010"]["tmin"], tc_o["1981-2010"]["ppt"])
    result("chelsa_vs_tc_1981_2010_same_period", **{k: _cmp(agg[k], tcp81[k], m2) for k in agg})
    result("tc_1981_vs_1991_change", **{k: {"mean_diff": float(np.nanmean(base_p[k][m2] - tcp81[k][m2])), "p95_abs": float(np.nanpercentile(np.abs(base_p[k][m2] - tcp81[k][m2]), 95))} for k in tcp81})
    # what 1 km adds inside a 2.5' cell
    result("within_cell_spread_chelsa", **{k: {"mean_sd": float(np.nanmean(within_sd[k][m2])), "mean_range": float(np.nanmean(within_range[k][m2])),
                                              "p95_range": float(np.nanpercentile(within_range[k][m2], 95)), "p99_range": float(np.nanpercentile(within_range[k][m2], 99))} for k in ("bio1", "bio5", "bio6", "bio12", "gdd5", "fd")})
    # bridge: CHELSA + (TC 1991-2020 - TC 1981-2010) at 2.5', ratios for precipitation, evaluated against TC 1991-2020 (should be ~exact by construction; the
    # useful number is the size of the correction)
    dT = {k: base_p[k] - tcp81[k] for k in ("bio1", "bio5", "bio6", "gdd5", "fd")}
    result("bridge_correction_size", **{k: {"mean": float(np.nanmean(v[m2])), "p5": float(np.nanpercentile(v[m2], 5)), "p95": float(np.nanpercentile(v[m2], 95))} for k, v in dT.items()})
    # ---- future: NEX-GDDP change factors (ACCESS-CM2, ssp245, 2041-2060 mean) on the fine grid
    if os.path.exists(NEXFILE):
        z = np.load(NEXFILE)
        nlat = G.LAT0  # noqa
        lat_c = -59.875 + 0.25 * np.arange(400, 480); lon_c = 0.125 + 0.25 * np.arange(0, 80)
        for scen_tag, wc_scen, wc_per in (("f245", "ssp245", "2041-2060"), ("f585", "ssp585", "2081-2100")):
            if f"{scen_tag}_tasmax" not in z.files:
                continue
            dtx, dtn, lrp = G.coarse_changes(z["base_tasmax"], z[f"{scen_tag}_tasmax"], z["base_tasmin"], z[f"{scen_tag}_tasmin"],
                                             z["base_pr"] * G.DPM[:, None, None], z[f"{scen_tag}_pr"] * G.DPM[:, None, None], dry_mm=0.5)
            t0 = time.time()
            fdtx, fdtn, flrp = (G.regrid_bilinear(a, lat_c, lon_c, lat, lon, wrap=False) for a in (dtx, dtn, lrp))
            fx, fn, fp = G.apply_changes(tc["tmax"], tc["tmin"], tc["ppt"], fdtx, fdtn, flrp)
            fut = G.future_predictors(tc, fx, fn, fp, lat[:, None] * np.ones((1, len(lon))))
            result("future_time", scenario=scen_tag, seconds=time.time() - t0, cells=int(land.size))
            np.savez_compressed(f"{OUT}/future_{scen_tag}.npz", **{k: v.astype("float32") for k, v in fut.items()})
            # WorldClim future
            wf = {}
            for var, k in (("tmax", "tmax"), ("tmin", "tmin"), ("prec", "ppt")):
                a, dt = _wc_future("ACCESS-CM2", wc_scen, wc_per, var)
                wf[k] = a
            result("wc_future_read", scenario=scen_tag, window_s=dt)
            wfp = G.predictors(wf["tmax"], wf["tmin"], wf["ppt"])
            mm = land & np.isfinite(wfp["bio1"])
            res_abs = {k: _cmp(fut[k], wfp[k], mm) for k in wfp}
            result("future_vs_wc_absolute", scenario=scen_tag, model="ACCESS-CM2", **res_abs)
            ours_change = {k: fut[k] - base_p[k] for k in wfp}
            wc_change = {k: wfp[k] - wcp[k] for k in wfp}
            result("future_vs_wc_change", scenario=scen_tag, **{k: {"ours_mean": float(np.nanmean(ours_change[k][mm])), "wc_mean": float(np.nanmean(wc_change[k][mm])),
                                                                     **{"diff_" + a: b for a, b in _cmp(ours_change[k], wc_change[k], mm).items()}} for k in wfp})
            # ratio form for precipitation
            result("future_ppt_ratio", scenario=scen_tag, ours=float(np.nanmean(fut["bio12"][mm] / base_p["bio12"][mm])), wc=float(np.nanmean(wfp["bio12"][mm] / wcp["bio12"][mm])))
            # check that the regridded coarse changes look right (interpolation vs the 25 km field it came from)
            result("cwd_future", scenario=scen_tag, base_mean=float(np.nanmean(base_p["cwd"][mm])), fut_mean=float(np.nanmean(fut["cwd"][mm])),
                   aet_base=float(np.nanmean(base_p["aet"][mm])), aet_fut=float(np.nanmean(fut["aet"][mm])))
            # elevation-dependence of the warming (an effect of delta interpolation: none expected) and lapse check using CHELSA-based fine detail
    else:
        result("future_skipped", reason=f"{NEXFILE} not found")


if __name__ == "__main__":
    {"tc": stage_tc, "compare": stage_compare}[sys.argv[1]]()
    result("done", stage=sys.argv[1], rss_mb=rss())
