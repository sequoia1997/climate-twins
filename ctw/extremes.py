"""Extreme-day indicators at every place from NASA NEX-GDDP-CMIP6 (Thrasher et al. 2022): bias-corrected daily
tasmax, tasmin, pr and hurs on a 0.25 degree global grid, historical plus SSP scenarios. A separate, optional
yearly job (workflow "Extreme days"); it never blocks the main rebuild.

Why whole files are downloaded: each NetCDF holds one variable-year (~245 MB, gzip) chunked as ONE FULL GLOBE PER
DAY (1, 600, 1440), so a point read still fetches and inflates every day chunk; ranged reads of a single cell
cost about as much as the file and are far slower (24 s vs 7 s). Each worker therefore streams a file to local
disk, reads all places out of every daily chunk in one pass and deletes it (~5 s decode for 1,600 places).

Per model (one matrix job): for every sampled year of baseline / period / scenario, four files -> seven annual
indices per place (see INDICES) -> window means. Writes work/extremes/<model>.npz:
  base (NI, NT)   fut (nper, nscen, NI, NT)
`aggregate` folds the models into site/data/extremes.json (ensemble median and min-max)."""
from __future__ import annotations
import json, math, os, re, time, warnings
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from . import common as C

warnings.filterwarnings("ignore")
BUCKET = "https://nex-gddp-cmip6.s3-us-west-2.amazonaws.com/"
ROOT = "NEX-GDDP-CMIP6/"
LAT0, LON0, RES, NLAT, NLON = -59.875, 0.125, 0.25, 600, 1440
FILL = 1e19                                                       # fill value is 1e20

# id, label, unit, definition
INDICES = [
    ("tx35", "Days over 35 °C (95 °F)", "days", "daily high at or above 35 °C"),
    ("tx30", "Days over 30 °C (86 °F)", "days", "daily high at or above 30 °C"),
    ("tr20", "Tropical nights (low above 20 °C)", "nights", "daily low at or above 20 °C"),
    ("fd", "Frost days (low below 0 °C)", "days", "daily low below 0 °C"),
    ("wb28", "Hot-humid days (wet-bulb 28 °C+)", "days", "wet-bulb temperature from daily high and mean humidity at or above 28 °C"),
    ("cdd", "Longest dry spell", "days", "longest run of days under 1 mm of precipitation"),
    ("rx1", "Wettest day", "mm", "largest one-day precipitation total"),
]
IDS = [i[0] for i in INDICES]
NI = len(INDICES)
COUNT = ("tx35", "tx30", "tr20", "fd", "wb28")                    # counts are scaled to a 365-day year


def settings(cfg) -> dict:
    e = {"scenarios": ["ssp245", "ssp585"], "year_stride": 2, "ensemble": "tcr_likely", "workers": 3,
         "wet_bulb_c": 28.0, "dry_mm": 1.0}
    e.update(cfg.get("extremes", {}))
    return e


# --------------------------------------------------------------------------- index math (pure numpy)
def wet_bulb(t_c, rh):
    """Wet-bulb temperature (deg C) from air temperature (deg C) and relative humidity (%), Stull (2011).
    Fitted for RH 5-99 % and T -20 to 50 deg C; inputs are clipped to that range."""
    t = np.clip(t_c, -20.0, 50.0)
    rh = np.clip(rh, 5.0, 99.0)
    return (t * np.arctan(0.151977 * np.sqrt(rh + 8.313659)) + np.arctan(t + rh) - np.arctan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh) - 4.686035)


def sat_vap_hpa(t_c):
    """Saturation vapour pressure (hPa), Magnus form."""
    return 6.112 * np.exp(17.62 * t_c / (243.12 + t_c))


def rh_at_tmax(rh_mean, tx_c, tn_c):
    """Humidity at the time of the daily high. NEX-GDDP hurs is a daily mean, which is far higher than the
    afternoon value; holding the vapour pressure fixed (dewpoint conserved through the day) and evaluating it at
    the daily maximum gives the afternoon relative humidity. Daily mean temperature is taken as (tmax+tmin)/2."""
    tm = 0.5 * (tx_c + tn_c)
    return np.clip(rh_mean * sat_vap_hpa(tm) / sat_vap_hpa(tx_c), 0.0, 100.0)


def longest_run(mask):
    """Longest run of True along axis 0 for a (days, places) boolean array."""
    best = np.zeros(mask.shape[1], "float32")
    cur = np.zeros(mask.shape[1], "float32")
    for row in mask:
        cur = np.where(row, cur + 1, 0)
        np.maximum(best, cur, out=best)
    return best


def annual_indices(tx_c, tn_c, pr_mm, rh, wb_thresh=28.0, dry_mm=1.0):
    """The seven indices for one year. Inputs (days, places): tasmax and tasmin in deg C, precipitation in
    mm/day, daily-mean relative humidity in %. Returns (NI, places). Counts are scaled to a 365-day year, so models with
    360-day calendars compare."""
    n = tx_c.shape[0]
    k = 365.0 / n
    out = np.empty((NI, tx_c.shape[1]), "float32")
    out[0] = (tx_c >= 35).sum(0) * k
    out[1] = (tx_c >= 30).sum(0) * k
    out[2] = (tn_c >= 20).sum(0) * k
    out[3] = (tn_c < 0).sum(0) * k
    out[4] = (wet_bulb(tx_c, rh_at_tmax(rh, tx_c, tn_c)) >= wb_thresh).sum(0) * k
    out[5] = longest_run(pr_mm < dry_mm) * k
    out[6] = pr_mm.max(0)
    bad = np.isnan(tx_c).any(0) | np.isnan(tn_c).any(0) | np.isnan(pr_mm).any(0) | np.isnan(rh).any(0)
    out[:, bad] = np.nan
    return out


def cell_index(lat, lon):
    lon = np.mod(np.asarray(lon, float), 360.0)
    return (np.clip(np.rint((np.asarray(lat, float) - LAT0) / RES), 0, NLAT - 1).astype(int),
            np.mod(np.rint((lon - LON0) / RES), NLON).astype(int))


def snap_to_land(ii, jj, valid, radius=3):
    """Move a place on an ocean (fill) cell to the nearest valid cell within `radius` cells; else -1."""
    oi, oj = ii.copy(), jj.copy()
    for p in np.nonzero(~valid[ii, jj])[0]:
        best, bd = None, 1e9
        for di in range(-radius, radius + 1):
            for dj in range(-radius, radius + 1):
                a, b = ii[p] + di, (jj[p] + dj) % NLON
                if 0 <= a < NLAT and valid[a, b] and di * di + dj * dj < bd:
                    best, bd = (a, b), di * di + dj * dj
        oi[p], oj[p] = best if best else (-1, -1)
    return oi, oj


# --------------------------------------------------------------------------- the archive
def _list(prefix, delim="/"):
    import requests
    keys, pre, tok = [], [], None
    while True:
        p = {"list-type": 2, "prefix": prefix, "delimiter": delim}
        if tok:
            p["continuation-token"] = tok
        for attempt in range(5):
            try:
                r = requests.get(BUCKET, params=p, timeout=60)
                r.raise_for_status()
                break
            except Exception as e:  # noqa: BLE001
                C.log.warning("list failed (%s)", e)
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"cannot list {prefix}")
        keys += re.findall(r"<Key>([^<]*)</Key>", r.text)
        pre += [x for x in re.findall(r"<Prefix>([^<]*)</Prefix>", r.text) if x != prefix]
        m = re.search(r"<NextContinuationToken>([^<]*)</NextContinuationToken>", r.text)
        if not m:
            return keys, pre
        tok = m.group(1)


def files_for(model, exp) -> dict:
    """{var: {year: key}} for one model and experiment; the newest version wins where a year has several."""
    _, mem = _list(f"{ROOT}{model}/{exp}/")
    if not mem:
        return {}
    out = {}
    for var in ("tasmax", "tasmin", "pr", "hurs"):
        keys, _ = _list(f"{ROOT}{model}/{exp}/{mem[0].split('/')[-2]}/{var}/", delim="")
        best = {}
        for k in keys:
            m = re.search(r"_(\d{4})(?:_v(\d+)\.(\d+))?\.nc$", k)
            if m:
                v = (int(m.group(2) or 0), int(m.group(3) or 0))
                if m.group(1) not in best or v > best[m.group(1)][0]:
                    best[m.group(1)] = (v, k)
        out[var] = {int(y): k for y, (v, k) in best.items()}
    return out


def available_models(cfg) -> list[str]:
    """Configured models (likely-TCR set unless ensemble = "all") that NEX-GDDP-CMIP6 publishes with all four variables."""
    s = settings(cfg)
    idx = C.ensembles(cfg)[s["ensemble"]]
    names = [C.models(cfg)[i]["name"] for i in idx]
    _, top = _list(ROOT)
    have = {p.split("/")[-2] for p in top}
    ok = []
    for n in names:
        if n not in have:
            continue
        _, mem = _list(f"{ROOT}{n}/ssp245/")
        if not mem:
            continue
        _, vs = _list(mem[0])
        if {"tasmax", "tasmin", "pr", "hurs"} <= {v.split("/")[-2] for v in vs}:
            ok.append(n)
    return ok


# --------------------------------------------------------------------------- reading one file
def fetch(key, dest, tries=6):
    import requests
    for attempt in range(tries):
        try:
            with requests.get(BUCKET + key, stream=True, timeout=(30, 120)) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for b in r.iter_content(1 << 20):
                        f.write(b)
            return
        except Exception as e:  # noqa: BLE001
            C.log.warning("download failed %s (%s), retry", key.rsplit("/", 1)[-1], e)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"cannot download {key}")


def read_cells(path, var, ii, jj):
    """(days, places) values at the given cells, read one daily chunk at a time. Fill values become NaN."""
    import h5py
    with h5py.File(path, "r") as h:
        d = h[var]
        out = np.empty((d.shape[0], len(ii)), "float32")
        for k in range(d.shape[0]):
            out[k] = d[k][ii, jj]
    out[out > FILL] = np.nan
    return out


def read_var(key, var, ii, jj, tmp):
    dest = os.path.join(tmp, f"{os.getpid()}_{var}.nc")
    try:
        fetch(key, dest)
        a = read_cells(dest, var, ii, jj)
    finally:
        if os.path.exists(dest):
            os.remove(dest)
    if var in ("tasmax", "tasmin"):
        return a - 273.15
    if var == "pr":
        return a * 86400.0
    return a


def year_job(args):
    """All four variables of one year -> (NI, places) indices."""
    keys, ii, jj, tmp, wb, dry = args
    v = {var: read_var(k, var, ii, jj, tmp) for var, k in keys.items()}
    n = min(x.shape[0] for x in v.values())
    return annual_indices(v["tasmax"][:n], v["tasmin"][:n], v["pr"][:n], v["hurs"][:n], wb, dry)


def valid_mask(key, tmp):
    dest = os.path.join(tmp, "mask.nc")
    try:
        fetch(key, dest)
        import h5py
        with h5py.File(dest, "r") as h:
            a = h["tasmax"][0]
    finally:
        if os.path.exists(dest):
            os.remove(dest)
    return np.isfinite(a) & (a < FILL)


# --------------------------------------------------------------------------- one model
def window_years(y0, y1, stride, origin):
    return [y for y in range(y0, y1 + 1) if (y - origin) % stride == 0]


def run(model: str, cfg=None, years_override=None):
    """years_override = {"base": [...], "periods": [[...], ...]} limits the years (tests)."""
    cfg = cfg or C.config()
    s = settings(cfg)
    out_f = C.work("extremes", f"{model}.npz")
    if out_f.exists():
        C.log.info("%s already done", model)
        return
    T = C.targets()
    ii, jj = cell_index(T.lat.values, T.lon.values)
    scen = s["scenarios"]
    pers = cfg["periods"]["years"]
    b0, b1 = cfg["baseline"]["years"]
    st = s["year_stride"]
    hist = files_for(model, "historical")
    fs = {sc: files_for(model, sc) for sc in scen}
    fs["ssp245"] = fs.get("ssp245") or files_for(model, "ssp245")          # baseline 2015-2020 always from SSP2-4.5
    for e, f in [("historical", hist)] + list(fs.items()):
        if not f or any(len(f[v]) == 0 for v in f):
            raise RuntimeError(f"{model}: no {e} data in NEX-GDDP-CMIP6")
    tmp = str(C.work("extremes", "tmp", model))
    os.makedirs(tmp, exist_ok=True)
    t0 = time.time()
    mask = valid_mask(hist["tasmax"][min(hist["tasmax"])], tmp)
    ii, jj = snap_to_land(ii, jj, mask)
    ok = ii >= 0
    ii2, jj2 = np.where(ok, ii, 0), np.where(ok, jj, 0)
    C.log.info("%s: %d/%d places on land cells", model, ok.sum(), len(ok))

    def keys_of(exp_files, y):
        return {v: exp_files[v][y] for v in ("tasmax", "tasmin", "pr", "hurs")}

    ov = years_override or ({"base": [2013], "periods": [[(a + b) // 2] for a, b in pers]} if C.SMOKE else {})
    base_years = ov.get("base") or window_years(b0, b1, st, b0)
    jobs, tags = [], []                       # tags: ("base", y) or ("fut", pi, si, y)
    for y in base_years:
        src = hist if y <= 2014 else fs["ssp245"]
        jobs.append(keys_of(src, y)); tags.append(("base", y))
    for pi, (y0, y1) in enumerate(pers):
        yrs = (ov.get("periods") or [None] * len(pers))[pi] or window_years(y0, y1, st, y0)
        for si, sc in enumerate(scen):
            for y in yrs:
                jobs.append(keys_of(fs[sc], y)); tags.append(("fut", pi, si, y))
    C.log.info("%s: %d year-jobs (4 files each)", model, len(jobs))
    args = [(k, ii2, jj2, tmp, s["wet_bulb_c"], s["dry_mm"]) for k in jobs]
    res = []
    with ProcessPoolExecutor(max_workers=int(s["workers"])) as ex:
        for n, r in enumerate(ex.map(year_job, args)):
            res.append(r)
            if n % 10 == 0:
                C.log.info("%s: %d/%d years, %.0fs", model, n + 1, len(jobs), time.time() - t0)
    NT = len(T)
    base = np.nanmean([r for r, t in zip(res, tags) if t[0] == "base"], axis=0)
    fut = np.full((len(pers), len(scen), NI, NT), np.nan, "float32")
    for pi in range(len(pers)):
        for si in range(len(scen)):
            sel = [r for r, t in zip(res, tags) if t[0] == "fut" and t[1] == pi and t[2] == si]
            fut[pi, si] = np.nanmean(sel, axis=0)
    base[:, ~ok] = np.nan
    fut[..., ~ok] = np.nan
    C.save(out_f, base=base.astype("float32"), fut=fut, ids=np.array(IDS), scen=np.array(scen),
           labels=T.label.values.astype(str), n_years=np.array([len(base_years), len(jobs)]))
    try:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)
    except OSError:
        pass
    C.log.info("%s written %.0fs", model, time.time() - t0)


# --------------------------------------------------------------------------- ensemble -> JSON
def place_key(lat, lon) -> str:
    """Key the page can rebuild from a target's coordinates (export rounds them to 4 decimals)."""
    return f"{round(float(lat), 4) or 0.0:.4f},{round(float(lon), 4) or 0.0:.4f}"


def aggregate(cfg=None, out=None):
    """Median and min-max across models -> site/data/extremes.json (values rounded; NaN -> null).
    places["<lat>,<lon>"] = {"b": [median x NI], "br": [[lo, hi] x NI], "f": {period: {scenario: [[med, lo, hi] x NI]}}}
    in the order of "indices"; the key is place_key(lat, lon) (4 decimals)."""
    cfg = cfg or C.config()
    s = settings(cfg)
    T = C.targets()
    files = sorted(C.work("extremes").glob("*.npz"))
    if not files:
        raise RuntimeError("no extremes/<model>.npz files")
    Z = [C.load(f) for f in files]
    names = [f.stem for f in files]
    base = np.stack([z["base"] for z in Z])                    # (M, NI, NT)
    fut = np.stack([z["fut"] for z in Z])                      # (M, nper, nscen, NI, NT)
    med = lambda a: np.nanmedian(a, 0)
    lo, hi = np.nanmin, np.nanmax
    keys = cfg["periods"]["keys"]
    scen = list(Z[0]["scen"])
    places = {}

    def r(x, i):
        return None if not np.isfinite(x) else round(float(x), 1)
    for p, (lat, lon) in enumerate(zip(T.lat.values, T.lon.values)):
        if not np.isfinite(base[:, :, p]).any():
            continue
        lab = place_key(lat, lon)
        bm = med(base[:, :, p])
        f = {}
        for pi, k in enumerate(keys):
            f[k] = {sc: [[r(med(fut[:, pi, si, i, p]), i), r(lo(fut[:, pi, si, i, p], 0), i), r(hi(fut[:, pi, si, i, p], 0), i)]
                         for i in range(NI)] for si, sc in enumerate(scen)}
        places[lab] = {"b": [r(bm[i], i) for i in range(NI)],
                       "br": [[r(lo(base[:, i, p], 0), i), r(hi(base[:, i, p], 0), i)] for i in range(NI)], "f": f}
    doc = {"generated": time.strftime("%Y-%m-%d"), "source": "NASA NEX-GDDP-CMIP6 (Thrasher et al. 2022)",
           "models": names, "n_models": len(names), "scenarios": [str(x) for x in scen],
           "labels": {sc: cfg["scenarios"]["labels"][cfg["scenarios"]["ids"].index(sc)] for sc in map(str, scen)},
           "periods": keys, "baseline": cfg["baseline"]["years"], "year_stride": s["year_stride"],
           "indices": [{"id": a, "label": b, "unit": u, "def": d} for a, b, u, d in INDICES], "places": places}
    path = out or (C.SITE / "data" / "extremes.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(doc, open(path, "w"), separators=(",", ":"), ensure_ascii=False)
    C.log.info("extremes.json: %d places, %d models, %.0f kB", len(places), len(names), path.stat().st_size / 1024)
    return path
