"""Jobs that build the global predictor stack (workstream W1) in GitHub Actions and publish it as assets of the release
`species-pilot-data`. Library code is in climstack.py; this file is the command line used by .github/workflows/pilot-w1-*.yml.

    python -m ctw.species.climstack_run tc   --tile r1c1 --out DIR [--upload]     TerraClimate -> basem + pred for base/hindcast windows
    python -m ctw.species.climstack_run nex-plan                                   JSON list of climate models for the matrix
    python -m ctw.species.climstack_run nex  --model M --out DIR [--upload]        NEX-GDDP coarse monthly climatologies -> deltas_<M>.npz
    python -m ctw.species.climstack_run ens  --out DIR [--upload]                  deltas_ensmedian.npz from the per-model files
    python -m ctw.species.climstack_run fut  --tile r1c1 --out DIR [--upload]      ensemble-median futures on the fine grid
    python -m ctw.species.climstack_run assemble --out DIR                          landmask.npz + manifest.json (uploaded)

Resumable: with --upload each job first lists the release assets and skips whatever is already published (the sidecar
meta_<job>.json is uploaded last, so its presence marks a finished job). Memory: a tile job keeps about 2-3 GB.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, subprocess, sys, time
import numpy as np

from . import climategrid as G
from . import climstack as S

TAG = "species-pilot-data"
REPO = "sequoia1997/climate-twins"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/" + "{name}"
TC_LAST_YEAR = int(os.environ.get("TC_LAST_YEAR", 2025))
NEX_ROWS, NEX_COLS = 600, 1440
NEX_LAT0, NEX_LON0, NEX_RES = -59.875, 0.125, 0.25
PR_DRY = 0.05                                 # mm/day: below this model baseline precipitation the ratio is set to 1


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# --------------------------------------------------------------------------- release helpers (gh CLI, GITHUB_TOKEN)
def _gh(*args, tries=4):
    for k in range(tries):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
        log("gh", args[:3], "failed:", r.stderr.strip()[:300])
        time.sleep(5 * (k + 1))
    raise RuntimeError(f"gh {' '.join(args[:3])} failed")


def release_assets() -> dict:
    try:
        out = _gh("release", "view", TAG, "--repo", REPO, "--json", "assets", "-q", ".assets[] | [.name, .size] | @tsv", tries=2)
    except RuntimeError:
        return {}
    return {l.split("\t")[0]: int(l.split("\t")[1]) for l in out.splitlines() if l}


def release_upload(paths):
    for p in paths:
        _gh("release", "upload", TAG, str(p), "--repo", REPO, "--clobber")
        log("uploaded", os.path.basename(p), f"{os.path.getsize(p) / 1e6:.1f} MB")


def release_download(name, dest):
    os.makedirs(dest, exist_ok=True)
    _gh("release", "download", TAG, "--repo", REPO, "-p", name, "-D", dest, "--clobber")
    return os.path.join(dest, name)


def sha256(path, block=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(block), b""):
            h.update(b)
    return h.hexdigest()


def write_meta(out, job, files, extra=None):
    meta = {"job": job, "built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": {
        os.path.basename(f): {"sha256": sha256(f), "bytes": os.path.getsize(f)} for f in files}}
    if extra:
        meta.update(extra)
    p = os.path.join(out, f"meta_{job}.json")
    with open(p, "w") as f:
        json.dump(meta, f, indent=1)
    return p


def finish(out, job, files, upload, extra=None):
    meta = write_meta(out, job, files, extra)
    if upload:
        release_upload(list(files) + [meta])          # meta last
    return meta


# --------------------------------------------------------------------------- TerraClimate tile
def tc_jobs(years=None, windows=None):
    """[(var, year, (windows...))] TerraClimate variable-years a tile needs."""
    windows = windows or S.WINDOWS
    jobs = {}
    for w, (a, b) in windows.items():
        vars_ = tuple(S.MONTHLY) if w.startswith("base") else S.PRED_VARS
        for y in range(a, b + 1):
            if years is not None and y not in years:
                continue
            for v in vars_:
                jobs.setdefault((v, y), []).append(w)
    return [(v, y, tuple(ws)) for (v, y), ws in sorted(jobs.items(), key=lambda kv: (kv[0][1], kv[0][0]))]


def _read(args):
    v, y, rows, cols = args
    from . import tc_region as TC
    for k in range(4):
        try:
            x, dtm = TC.read_months(v, y, rows, cols)
            if x.shape[0] != 12:
                raise RuntimeError(f"{v} {y}: {x.shape[0]} months")
            return v, y, x, dtm
        except Exception as e:  # noqa: BLE001
            log("read failed", v, y, repr(e)[:200], "retry", k)
            time.sleep(10 * (k + 1))
    raise RuntimeError(f"cannot read {v} {y}")


def build_window(rows, cols, tile, out, procs=4, years=None, windows=None, upload_cb=None):
    """Accumulate the climatologies of every window over a window of the native grid, then write basem and pred files.
    Returns (files, stats)."""
    from multiprocessing import get_context
    windows = windows or S.WINDOWS
    shape = (12, rows.stop - rows.start, cols.stop - cols.start)
    jobs = tc_jobs(years, windows)
    sums, cnts = {}, {}
    for v, y, ws in jobs:
        for w in ws:
            if (w, v) not in sums:
                sums[(w, v)] = np.zeros(shape, "float32"); cnts[(w, v)] = np.zeros(shape, "uint8")
    t0 = time.time(); done = 0
    with get_context("fork").Pool(procs) as pool:
        for v, y, x, dtm in pool.imap_unordered(_read, [(v, y, rows, cols) for v, y, _ in jobs], chunksize=1):
            ws = next(w for vv, yy, w in jobs if vv == v and yy == y)
            ok = np.isfinite(x)
            for w in ws:
                sums[(w, v)] += np.where(ok, x, 0); cnts[(w, v)] += ok
            done += 1
            if done % 10 == 0 or done == len(jobs):
                log(f"{tile}: {done}/{len(jobs)} var-years, {time.time() - t0:.0f}s (last {dtm:.0f}s)")
            del x, ok
    clim, ymax = {}, {}
    for key in list(sums):                                # free the accumulators as we go: peak memory stays near 3 GB
        s, c = sums.pop(key), cnts.pop(key)
        with np.errstate(invalid="ignore", divide="ignore"):
            clim[key] = np.where(c > 0, s / np.maximum(c, 1), np.nan).astype("float32")
        ymax[key] = int(c.max())
        del s, c
    nyear = {w: b - a + 1 for w, (a, b) in windows.items()}
    base = next(w for w in windows if w.startswith("base"))
    land = np.ones(shape[1:], bool)
    for v in S.PRED_VARS:
        land &= np.isfinite(clim[(base, v)]).all(0)
    n_land = int(land.sum())
    log(f"{tile}: land cells {n_land} of {land.size}")
    files, stats = [], {"tile": tile, "n_land": n_land, "tc_last_year": TC_LAST_YEAR, "products": {}}
    # baseline monthly (for futures), pet/soil gaps filled with 0
    mon = {v: clim[(base, v)][:, land] for v in S.MONTHLY}
    gaps = {v: int((~np.isfinite(mon[v])).any(0).sum()) for v in ("pet", "soil")}
    for v in gaps:
        mon[v] = np.nan_to_num(mon[v], nan=0.0)
    stats["pet_soil_gaps_filled"] = gaps
    p = os.path.join(out, f"basem_{tile}.npz"); S.save_basem(p, tile, land, mon); files.append(p)
    for w in windows:
        if not n_land:
            break
        m = {v: clim[(w, v)][:, land] for v in S.PRED_VARS}
        t1 = time.time()
        P = S.predict(m)
        prod = w
        p = os.path.join(out, f"pred_{prod}_{tile}.npz"); S.save_pred(p, tile, land, P, prod); files.append(p)
        stats["products"][prod] = {"seconds": round(time.time() - t1), "nan_cells": int((~np.isfinite(P)).any(0).sum()),
                                   "mean": {nm: float(np.nanmean(P[k])) for k, nm in enumerate(S.NAMES)},
                                   "years_per_var": {v: ymax[(w, v)] for v in S.PRED_VARS}, "expected_years": nyear[w]}
        log(f"{tile}: {prod} predicted in {time.time() - t1:.0f}s")
    if not n_land:                                   # an all-ocean tile still gets (tiny) files so that a rerun skips it
        for prod in list(windows):
            p = os.path.join(out, f"pred_{prod}_{tile}.npz"); S.save_pred(p, tile, land, np.zeros((len(S.NAMES), 0), "float32"), prod); files.append(p)
    return files, stats


def cmd_tc(a):
    os.makedirs(a.out, exist_ok=True)
    job = f"tc_{a.tile}"
    if a.upload and f"meta_{job}.json" in release_assets():
        log(job, "already published, skipping"); return
    rows, cols = S.tile_window(a.tile)
    files, stats = build_window(rows, cols, a.tile, a.out, procs=a.procs)
    finish(a.out, job, files, a.upload, {"stats": stats})
    log(job, "done")


# --------------------------------------------------------------------------- NEX-GDDP coarse climatologies and deltas
def nex_models():
    """Models that NEX-GDDP-CMIP6 publishes with historical, ssp245 and ssp585 (tasmax, tasmin, pr), in config.toml order."""
    from .. import common as C, extremes as X
    cfg = C.config()
    jobs = X.plan(cfg)
    have = {}
    for j in jobs:
        m, part = j.split("__")
        have.setdefault(m, set()).add(part)
    return [m for m in dict.fromkeys(j.split("__")[0] for j in jobs) if {"base", "ssp245", "ssp585"} <= have[m]]


def _nex_year(args):
    key, var, tmp = args
    import h5py
    from .. import extremes as X
    dest = os.path.join(tmp, f"{os.getpid()}_{var}.nc")
    try:
        X.fetch(key, dest)
        with h5py.File(dest, "r") as h:
            d = h[var]
            n = d.shape[0]
            mi = X.month_index(n)
            s = np.zeros((12, NEX_ROWS, NEX_COLS), "float64"); c = np.zeros((12, NEX_ROWS, NEX_COLS), "float32")
            for k in range(n):
                x = d[k].astype("float32")
                ok = x < X.FILL
                s[mi[k]] += np.where(ok, x, 0); c[mi[k]] += ok
    finally:
        if os.path.exists(dest):
            os.remove(dest)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(c > 0, s / np.maximum(c, 1), np.nan).astype("float32")
    if var in ("tasmax", "tasmin"):
        m = m - 273.15
    elif var == "pr":
        m = m * 86400.0
    return var, m


def nex_window(model, files_by_year, years, tmp, workers):
    """Monthly climatology (3, 12, 600, 1440) [tasmax C, tasmin C, pr mm/day] of `years`; files_by_year[y] = {var: key}."""
    from multiprocessing import get_context
    VARS = ("tasmax", "tasmin", "pr")
    tasks = [(files_by_year[y][v], v, tmp) for y in years for v in VARS]
    acc = {v: np.zeros((12, NEX_ROWS, NEX_COLS), "float64") for v in VARS}
    cnt = {v: np.zeros((12, NEX_ROWS, NEX_COLS), "float32") for v in VARS}
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool:
        for n, (v, m) in enumerate(pool.imap_unordered(_nex_year, tasks, chunksize=1)):
            ok = np.isfinite(m)
            acc[v] += np.where(ok, m, 0); cnt[v] += ok
            if n % 6 == 0:
                log(f"{model}: {n + 1}/{len(tasks)} files, {time.time() - t0:.0f}s")
    return np.stack([np.where(cnt[v] > 0, acc[v] / np.maximum(cnt[v], 1), np.nan) for v in VARS]).astype("float32")


def nex_part(model, part, tmp, workers=3, years_override=None):
    """part 'base' (1991-2020: historical to 2014, ssp245 after) or a scenario id (-> (n_periods, 3, 12, 600, 1440))."""
    from .. import extremes as X
    ov = years_override or {}
    hist = X.files_for(model, "historical")
    if part == "base":
        s245 = X.files_for(model, "ssp245")
        yrs = ov.get("base") or list(range(1991, 2021))
        fy = {y: {v: (hist if y <= 2014 else s245)[v][y] for v in ("tasmax", "tasmin", "pr")} for y in yrs}
        return nex_window(model, fy, yrs, tmp, workers)[None]
    fs = X.files_for(model, part)
    outs = []
    for pi, p in enumerate(S.PERIODS):
        a, b = (int(x) for x in p.split("-"))
        yrs = (ov.get("periods") or [None, None])[pi] or list(range(a, b + 1))
        fy = {y: {v: fs[v][y] for v in ("tasmax", "tasmin", "pr")} for y in yrs}
        outs.append(nex_window(model, fy, yrs, tmp, workers))
    return np.stack(outs)


def make_deltas(model, base, futs, meta=None):
    """base (3, 12, ny, nx) [tx, tn, pr]; futs {scenario: (nper, 3, 12, ny, nx)} -> Deltas. Ocean (no NEX value) is filled with
    the nearest land cell's change so the interpolation to coastal 2.5' cells has no gaps."""
    from scipy import ndimage
    ny, nx = base.shape[-2:]
    valid = np.isfinite(base).all((0, 1))
    for f in futs.values():
        valid &= np.isfinite(f).all((0, 1, 2))
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True) if valid.any() and not valid.all() else None
    scen = [s for s in S.SCEN if s in futs]
    dtx = np.zeros((len(scen), len(S.PERIODS), 12, ny, nx), "float32"); dtn = dtx.copy(); rp = np.ones_like(dtx)
    for si, s in enumerate(scen):
        for pi in range(len(S.PERIODS)):
            f = futs[s][pi]
            dtx[si, pi] = f[0] - base[0]; dtn[si, pi] = f[1] - base[1]
            with np.errstate(invalid="ignore", divide="ignore"):
                r = np.where(base[2] > PR_DRY, f[2] / base[2], 1.0)
            rp[si, pi] = np.clip(r, 0.01, 100)
    out = []
    for arr, fill in ((dtx, 0.0), (dtn, 0.0), (rp, 1.0)):
        a = np.where(np.isfinite(arr), arr, np.nan)
        if idx is not None:
            for si in range(a.shape[0]):
                for pi in range(a.shape[1]):
                    for m in range(12):
                        a[si, pi, m] = a[si, pi, m][tuple(idx)]
        out.append(np.nan_to_num(a, nan=fill))
    lat = NEX_LAT0 + NEX_RES * np.arange(ny); lon = NEX_LON0 + NEX_RES * np.arange(nx)
    return S.Deltas(model, tuple(scen), S.PERIODS, out[0], out[1], out[2], lat, lon, meta or {})


def model_tcr(model):
    from .. import common as C
    for m in C.models(C.config()):
        if m["name"] == model:
            return m["tcr"]
    return -1


def cmd_nex_plan(a):
    print(json.dumps(nex_models()))


def cmd_nex(a):
    os.makedirs(a.out, exist_ok=True)
    job = f"nex_{a.model}"
    have = release_assets() if a.upload else {}
    if f"meta_{job}.json" in have:
        log(job, "already published, skipping"); return
    tmp = os.path.join(a.out, "tmp"); os.makedirs(tmp, exist_ok=True)
    parts = {}
    for part in ("base", "ssp245", "ssp585"):
        name = f"nexclim_{a.model}__{part}.npz"
        path = os.path.join(a.out, name)
        if name in have:                                    # an earlier run finished this part
            release_download(name, a.out)
        if not os.path.exists(path):
            t0 = time.time()
            arr = nex_part(a.model, part, tmp, workers=a.procs)
            np.savez_compressed(path, clim=arr)
            log(a.model, part, f"{time.time() - t0:.0f}s")
            if a.upload:
                release_upload([path])
        parts[part] = np.load(path)["clim"]
    d = make_deltas(a.model, parts["base"][0], {s: parts[s] for s in ("ssp245", "ssp585")},
                    {"tcr": model_tcr(a.model), "baseline": "1991-2020 (historical to 2014, ssp245 2015-2020)", "source": "NEX-GDDP-CMIP6",
                     "pr_dry_mm_day": PR_DRY})
    p = os.path.join(a.out, f"deltas_{a.model}.npz"); d.save(p)
    finish(a.out, job, [p], a.upload, {"model": a.model, "tcr": d.meta["tcr"]})
    log(job, "done", f"{os.path.getsize(p) / 1e6:.0f} MB")


def cmd_ens(a):
    from .. import common as C
    os.makedirs(a.out, exist_ok=True)
    models = nex_models() if not a.models else a.models.split(",")
    cfg = C.config(); lo, hi = cfg["models"]["tcr_likely"]
    use, items = [], []
    for m in models:
        p = os.path.join(a.out, f"deltas_{m}.npz")
        if not os.path.exists(p):
            if not a.upload:
                continue
            try:
                release_download(f"deltas_{m}.npz", a.out)
            except RuntimeError:
                log("missing", m); continue
        d = S.Deltas.load(p)
        if lo <= d.meta.get("tcr", -1) <= hi:
            items.append(d); use.append(m)
        del d
    log("ensemble (tcr_likely):", use)
    e = S.ensemble_median(items, "ensemble_median")
    e.meta.update({"definition": f"median over models with TCR in [{lo}, {hi}] (config.toml [models] tcr_likely) of monthly changes", "models": use})
    p = os.path.join(a.out, "deltas_ensemble_median.npz"); e.save(p)
    finish(a.out, "ens", [p], a.upload, {"models": use})


# --------------------------------------------------------------------------- futures on the fine grid
def cmd_fut(a):
    os.makedirs(a.out, exist_ok=True)
    job = f"fut_{a.tile}"
    have = release_assets() if a.upload else {}
    if f"meta_{job}.json" in have:
        log(job, "already published, skipping"); return
    for n in (f"basem_{a.tile}.npz", "deltas_ensemble_median.npz"):
        if not os.path.exists(os.path.join(a.out, n)):
            if n.startswith("basem") and n not in have and a.upload:
                log("no baseline for", a.tile, "(all-ocean tile?)");
            release_download(n, a.out)
    land, _, mon = S.load_basem(os.path.join(a.out, f"basem_{a.tile}.npz")) if os.path.exists(os.path.join(a.out, f"basem_{a.tile}.npz")) else (None, None, None)
    files = []
    if land is None or not land.any():
        for prod in S.future_products():
            p = os.path.join(a.out, f"pred_{prod}_{a.tile}.npz"); S.save_pred(p, a.tile, np.zeros((S.TH, S.TW), bool), np.zeros((10, 0), "float32"), prod); files.append(p)
    else:
        i, j = S.land_index(land, a.tile)
        st = S.BaselineStack(mon, G.cell_lat(i), G.cell_lon(j), i, j)
        d = S.Deltas.load(os.path.join(a.out, "deltas_ensemble_median.npz"))
        it = S.PointInterp(d.lat, d.lon, st.lat, st.lon)
        for s in S.SCEN:
            for per in S.PERIODS:
                t0 = time.time()
                r = S.apply_deltas(st, d, "ensemble_median", s, per, interp=it)
                prod = f"fut_{s}_{per}_ensmedian"
                p = os.path.join(a.out, f"pred_{prod}_{a.tile}.npz")
                S.save_pred(p, a.tile, land, np.stack([r[n] for n in S.NAMES]), prod); files.append(p)
                log(a.tile, prod, f"{time.time() - t0:.0f}s")
    finish(a.out, job, files, a.upload)


# --------------------------------------------------------------------------- manifest
def grid_definition():
    return {"crs": "EPSG:4326 (WGS84 lon/lat), cell centres", "res_deg": G.RES, "res_arcmin": 2.5, "nlat": G.NLAT, "nlon": G.NLON,
            "row0_centre_lat": G.LAT0, "col0_centre_lon": G.LON0, "row_order": "north to south (row 0 = north)",
            "cell_lat": "89.979166667 - i/24", "cell_lon": "-179.979166667 + j/24",
            "tiles": {"rows": S.TH, "cols": S.TW, "grid": [S.NTR, S.NTC], "name": "r<i>c<j>, i = row block from the north, j = column block from 180W",
                      "priority": list(S.PRIORITY_TILES)},
            "land": "cells where TerraClimate tmax, tmin, ppt, def and aet are all valid in the 1991-2020 climatology"}


def cmd_assemble(a):
    os.makedirs(a.out, exist_ok=True)
    have = release_assets() if a.upload else {}
    metas = {}
    for n in sorted(have):
        if n.startswith("meta_") and n.endswith(".json"):
            metas[n] = json.load(open(release_download(n, os.path.join(a.out, "metas"))))
    files = {}
    for m in metas.values():
        files.update(m["files"])
    # land mask from the basem files (small to download compared with their use elsewhere)
    mask = np.zeros((G.NLAT, G.NLON), bool)
    missing = []
    for t in S.ALL_TILES:
        n = f"basem_{t}.npz"
        p = os.path.join(a.out, n)
        if not os.path.exists(p) and a.upload and n in have:
            release_download(n, a.out)
        if os.path.exists(p):
            land, _, _ = S.load_basem(p)
            r, c = S.tile_window(t)
            mask[r, c] = land
        else:
            missing.append(t)
        if os.path.exists(p) and a.upload:
            os.remove(p)
    mp = os.path.join(a.out, "landmask.npz")
    np.savez_compressed(mp, land_packed=S.pack_mask(mask), shape=np.array(mask.shape), row0_centre_lat=G.LAT0, col0_centre_lon=G.LON0, res_deg=G.RES)
    per = {}
    for n, m in files.items():
        per[n] = m
    expected = [f"pred_{p}_{t}.npz" for p in list(S.WINDOWS) + S.future_products() for t in S.ALL_TILES] + [f"basem_{t}.npz" for t in S.ALL_TILES]
    manifest = {
        "name": "species-pilot-data climate stack", "workstream": "W1", "built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release_tag": TAG, "url_pattern": URL, "grid": grid_definition(),
        "predictors": [{"name": n, "units": S.UNITS[n]} for n in S.NAMES], "dtype": "float32",
        "products": {**{w: {"kind": "observed", "years": list(y), "source": "TerraClimate climatology"} for w, y in S.WINDOWS.items()},
                     **{f"fut_{s}_{p}_ensmedian": {"kind": "future", "scenario": s, "period": p, "source": "TerraClimate 1991-2020 + NEX-GDDP ensemble-median change factors"}
                        for s in S.SCEN for p in S.PERIODS}},
        "terraclimate_last_full_year": TC_LAST_YEAR, "scenarios": list(S.SCEN), "periods": list(S.PERIODS),
        "coarse_deltas": {"grid": {"lat0": NEX_LAT0, "lon0": NEX_LON0, "res": NEX_RES, "shape": [NEX_ROWS, NEX_COLS]}, "files": "deltas_<model>.npz",
                          "ensemble_file": "deltas_ensemble_median.npz"},
        "files": per, "incomplete_tiles_for_landmask": missing,
        "missing_expected_files": [n for n in expected if n not in per], "loader": "ctw/species/climstack.py",
    }
    jp = os.path.join(a.out, "manifest.json")
    json.dump(manifest, open(jp, "w"), indent=1)
    meta = write_meta(a.out, "landmask", [mp])
    log("manifest:", len(per), "files;", len(manifest["missing_expected_files"]), "expected files missing")
    if a.upload:
        release_upload([mp, meta, jp])


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for c, fn in (("tc", cmd_tc), ("nex-plan", cmd_nex_plan), ("nex", cmd_nex), ("ens", cmd_ens), ("fut", cmd_fut), ("assemble", cmd_assemble)):
        p = sp.add_parser(c); p.set_defaults(fn=fn)
        p.add_argument("--tile"); p.add_argument("--model"); p.add_argument("--models"); p.add_argument("--out", default="pilot-out")
        p.add_argument("--procs", type=int, default=4); p.add_argument("--upload", action="store_true")
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
