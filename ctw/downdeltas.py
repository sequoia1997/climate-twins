"""Downscaled CMIP6 changes from two more sources, for the multi-source model-resolution cross-check (`nexcheck`).

  wc  WorldClim 2.1 CMIP6 (Fick & Hijmans 2017): statistically downscaled (delta method + WorldClim baseline) monthly
      tmin / tmax / prec for many GCMs, SSP1-2.6 ... 5-8.5, 2041-2060 and 2081-2100, plus the WorldClim 2.1 baseline
      (1970-2000). Global.  https://geodata.ucdavis.edu/cmip6/<res>/<GCM>/<ssp>/wc2.1_<res>_<var>_<GCM>_<ssp>_<period>.tif
  aw  AdaptWest downscaled CMIP6 (Wang et al. 2016 method, AdaptWest Project 2022): 1 km monthly ClimateNA-style
      products for North America, in the bucket that holds the 1991-2020 normals ctw/adaptwest.py uses.  The layout is
      discovered by listing the bucket (`--list`), so the file names need not be known in advance.

Both are used as a *change*: future minus baseline (temperature), future / baseline (precipitation), each source
against its own baseline, then applied to our observed present climate by the same analogs.apply_delta step as every
other change (ratios clipped to the configured range in nexcheck.project). Humidity is not provided: it is kept at
constant relative humidity, exactly as the main pipeline does for a model without huss.

Baseline periods differ (WorldClim 1970-2000, AdaptWest 1991-2020, main pipeline 1995-2014), so a WorldClim change also
contains the ~15-20 years of warming between its baseline and ours: a small, systematic overstatement (about 0.3-0.5 C)
that the methods page states.

Jobs (one runner each, in a matrix):  wc-base | wc:<GCM> | aw-base | aw:<label>.  Each writes work/downdeltas/<job>.npz with the
absolute monthly values per place (tmax, tmin, ppt: (P, S, NT, 12); base jobs (NT, 12)); `--aggregate` turns them into
changes in data/downdeltas.npz. Files are read one at a time and deleted, so a job needs < 1 GB of disk.

    python -m ctw downdeltas --list [--source wc|aw]      what exists (the smoke workflow starts with this)
    python -m ctw downdeltas --plan                        JSON list of jobs
    python -m ctw downdeltas --job wc:MIROC6
    python -m ctw downdeltas --aggregate"""
from __future__ import annotations
import json, os, re, time
import xml.etree.ElementTree as ET
import numpy as np
from . import common as C

VARS = ("tmax", "tmin", "ppt")
WC_VAR = {"tmax": "tmax", "tmin": "tmin", "ppt": "prec"}
AW_VAR = {"tmax": "tmax", "tmin": "tmin", "ppt": "ppt"}
OUTDIR = "downdeltas"
OUT = C.DATA / "downdeltas.npz"
DEFAULTS = {
    "scenarios": ["ssp245", "ssp585"],
    "wc_res": "10m",
    "wc_url": "https://geodata.ucdavis.edu/cmip6/{res}/{gcm}/{ssp}/wc2.1_{res}_{var}_{gcm}_{ssp}_{per}.tif",
    "wc_index": "https://geodata.ucdavis.edu/cmip6/{res}/",
    "wc_base_url": "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_{res}_{var}.zip",
    "wc_gcms": ["ACCESS-CM2", "BCC-CSM2-MR", "CMCC-ESM2", "EC-Earth3-Veg", "FIO-ESM-2-0", "GFDL-ESM4", "GISS-E2-1-G", "HadGEM3-GC31-LL",
                "INM-CM5-0", "IPSL-CM6A-LR", "MIROC6", "MPI-ESM1-2-HR", "MRI-ESM2-0", "UKESM1-0-LL"],      # fallback if the index cannot be read
    "aw_bucket": "https://s3-us-west-2.amazonaws.com/www.cacpd.org",
    "aw_prefix": "CMIP6v73/",
    "aw_exclude": "normals|Normal_",
    "aw_max_gb": 3.0,                  # skip a single AdaptWest file larger than this (a runner has 14 GB)
    "radius_px": 3,                    # WorldClim: nearest valid pixel within this many pixels (coastal places)
    "aw_radius_m": 10000,              # AdaptWest: mean of the 1 km cells within this distance (as adaptwest.py)
}
PERIODS = {"2050": "2041-2060", "2100": "2081-2100"}


def settings(cfg) -> dict:
    return {**DEFAULTS, **cfg.get("downdeltas", {})}


# --------------------------------------------------------------------------- pure numpy
def make_delta(fut, base, dry_mm=0.5):
    """Change from absolute monthly values. fut (..., NT, 12) for tmax, tmin, ppt as a dict; base the same without leading axes.
    Returns dtx, dtn (deg C) and rp (ratio, 1 where the base month is drier than dry_mm, clipped to [0.01, 100])."""
    b = {k: np.asarray(base[k], "float64") for k in VARS}
    f = {k: np.asarray(fut[k], "float64") for k in VARS}
    with np.errstate(invalid="ignore", divide="ignore"):
        rp = np.where(b["ppt"] > dry_mm, f["ppt"] / b["ppt"], 1.0)
    rp = np.where(np.isfinite(f["ppt"]) & np.isfinite(b["ppt"]), rp, np.nan)
    return f["tmax"] - b["tmax"], f["tmin"] - b["tmin"], np.clip(rp, 0.01, 100)


def nearest_valid(valid, lat, lon, x0, y0, dx, dy, radius=3):
    """Pixel (row, col) per place of the nearest valid pixel within `radius` pixels of the place's own pixel on a north-up
    lon/lat grid (upper-left corner x0, y0, pixel size dx, dy > 0). (-1, -1) where there is none."""
    H, W = valid.shape
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    j0 = np.clip(np.floor((lon - x0) / dx).astype(int), 0, W - 1)
    i0 = np.clip(np.floor((y0 - lat) / dy).astype(int), 0, H - 1)
    offs = sorted(((di, dj) for di in range(-radius, radius + 1) for dj in range(-radius, radius + 1)), key=lambda o: (o[0] ** 2 + o[1] ** 2, o))
    ri, rj = np.full(len(lat), -1), np.full(len(lat), -1)
    for di, dj in offs:
        i, j = i0 + di, (j0 + dj) % W                     # the world grid wraps around the date line
        ok = (ri < 0) & (i >= 0) & (i < H)
        ok[ok] = valid[i[ok], j[ok]]
        ri[ok], rj[ok] = i[ok], j[ok]
    return ri, rj


def sample_pixels(arr, ri, rj):
    """arr (12, H, W) -> (NT, 12) at the pixels chosen by nearest_valid; NaN where none."""
    out = np.full((len(ri), arr.shape[0]), np.nan)
    ok = ri >= 0
    out[ok] = arr[:, ri[ok], rj[ok]].T
    return out


def neighbours(x, y, X, Y, tr, H, W, radius_m):
    """AdaptWest: for each projected place (X, Y) the row/col arrays of cells within radius_m, plus the whole 23 x 23 window (fallback)."""
    nb = []
    for px, py in zip(X, Y):
        j0, i0 = int((px - tr.c) / tr.a), int((py - tr.f) / tr.e)
        ii, jj = np.mgrid[i0 - 11:i0 + 12, j0 - 11:j0 + 12]
        ok = (ii >= 0) & (ii < H) & (jj >= 0) & (jj < W)
        ii, jj = ii[ok], jj[ok]
        d = np.hypot(x[jj] - px, y[ii] - py) if len(ii) else np.array([])
        nb.append((ii[d <= radius_m], jj[d <= radius_m], ii, jj, d))
    return nb


def neighbour_mean(a, nb):
    """Mean of a (H, W) over each place's neighbourhood; the nearest valid cell in the window when the disc is empty."""
    out = np.full(len(nb), np.nan)
    for n, (i, j, ia, ja, d) in enumerate(nb):
        v = a[i, j] if len(i) else np.array([])
        v = v[np.isfinite(v)]
        if v.size == 0 and len(ia):
            va = a[ia, ja]
            okk = np.isfinite(va)
            v = va[okk][np.argsort(d[okk])[:1]] if okk.any() else v
        if v.size:
            out[n] = v.mean()
    return out


def parse_aw_key(key, gcms=()):
    """(label, ssp, period start year) of an AdaptWest object key, any part None if not recognised. label is a known GCM name in
    the path, else "ensemble" for multi-model products."""
    k = key
    m = re.search(r"ssp[-_ ]?(126|245|370|585)", k, re.I) or re.search(r"(?<![\d.])(?:ssp)?([1235])[-_.]?(?:2\.6|4\.5|7\.0|8\.5|26|45|70|85)(?!\d)", k, re.I)
    ssp = None
    if m:
        g = m.group(1)
        ssp = {"126": "ssp126", "245": "ssp245", "370": "ssp370", "585": "ssp585", "1": "ssp126", "2": "ssp245", "3": "ssp370", "5": "ssp585"}.get(g)
    m = re.search(r"(2041|2071|2081)[-_](2060|2070|2100)", k)
    per = int(m.group(1)) if m else None
    label = next((g for g in sorted(gcms, key=len, reverse=True) if g in k), None)
    if label is None and re.search(r"ensemble|\d+GCMs?|multi", k, re.I):
        label = "ensemble"
    return label, ssp, per


# --------------------------------------------------------------------------- discovery (network)
def _get(url, **kw):
    r = C.http().get(url, timeout=kw.pop("timeout", 60), **kw)
    r.raise_for_status()
    return r


def wc_gcms(s):
    try:
        html = _get(s["wc_index"].format(res=s["wc_res"])).text
        g = sorted(set(re.findall(r'href="([A-Za-z0-9][A-Za-z0-9._-]*)/"', html)))
        if g:
            return g
    except Exception as e:  # noqa: BLE001
        C.log.warning("WorldClim index unreadable (%s); using the configured GCM list", e)
    return list(s["wc_gcms"])


def aw_keys(s, prefix=None):
    """[(key, size)] of the AdaptWest bucket under the prefix (S3 ListObjectsV2, paginated)."""
    out, tok = [], None
    while True:
        p = {"list-type": "2", "prefix": prefix or s["aw_prefix"], "max-keys": "1000"}
        if tok:
            p["continuation-token"] = tok
        root = ET.fromstring(_get(s["aw_bucket"], params=p).content)
        ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
        for c in root.findall(f"{ns}Contents"):
            out.append((c.findtext(f"{ns}Key"), int(c.findtext(f"{ns}Size") or 0)))
        if root.findtext(f"{ns}IsTruncated") == "true":
            tok = root.findtext(f"{ns}NextContinuationToken")
        else:
            return out


def aw_products(s, cfg, keys=None):
    """{label: {(ssp, period key): (key, size)}} for the configured scenarios and the two periods; only what parses."""
    keys = keys if keys is not None else aw_keys(s)
    ex = re.compile(s["aw_exclude"], re.I) if s["aw_exclude"] else None
    gcms = [m["name"] for m in C.models(cfg)] + list(s["wc_gcms"])
    starts = {int(v.split("-")[0]): k for k, v in PERIODS.items()}
    out = {}
    for key, size in keys:
        if ex and ex.search(key) or not re.search(r"\.(zip|tif)$", key, re.I):
            continue
        label, ssp, per = parse_aw_key(key, gcms)
        if label and ssp in s["scenarios"] and per in starts:
            # a monthly product is a zip of monthly tifs; prefer zips whose name says monthly
            cur = out.setdefault(label, {}).get((ssp, starts[per]))
            if cur is None or ("monthly" in key.lower() and "monthly" not in cur[0].lower()):
                out[label][(ssp, starts[per])] = (key, size)
    return out


def list_sources(cfg, source="all"):
    s = settings(cfg)
    if source in ("all", "wc"):
        g = wc_gcms(s)
        print(f"WorldClim CMIP6 {s['wc_res']}: {len(g)} GCMs: {' '.join(g)}")
        for ssp in ("ssp126", "ssp245", "ssp370", "ssp585"):
            have = []
            for gc in g[:40]:
                url = s["wc_url"].format(res=s["wc_res"], gcm=gc, ssp=ssp, var="tmax", per="2041-2060")
                try:
                    have.append(gc) if C.http().head(url, timeout=30, allow_redirects=True).status_code == 200 else None
                except Exception:  # noqa: BLE001
                    pass
            print(f"  {ssp} 2041-2060 tmax present for {len(have)}/{len(g)} GCMs")
        for v in ("tmax", "prec"):
            url = s["wc_base_url"].format(res=s["wc_res"], var=v)
            r = C.http().head(url, timeout=30, allow_redirects=True)
            print(f"  base {v}: HTTP {r.status_code} {int(r.headers.get('content-length', 0)) / 1e6:.1f} MB  {url}")
    if source in ("all", "aw"):
        keys = aw_keys(s)
        print(f"AdaptWest {s['aw_prefix']}: {len(keys)} objects, {sum(k[1] for k in keys) / 1e9:.1f} GB")
        tops = {}
        for k, z in keys:
            t = "/".join(k.split("/")[:3])
            a = tops.setdefault(t, [0, 0]); a[0] += 1; a[1] += z
        for t, (n, z) in sorted(tops.items())[:60]:
            print(f"  {t:70s} {n:5d} objects {z / 1e6:9.0f} MB")
        pr = aw_products(s, cfg, keys)
        print(f"parsed products (scenarios {s['scenarios']}, periods {list(PERIODS.values())}): {len(pr)} labels")
        for lab, d in sorted(pr.items()):
            print(f"  {lab}: {len(d)} of {len(s['scenarios']) * len(PERIODS)}; e.g. {next(iter(d.values()))[0]}")
        if not pr:
            print("  nothing parsed; sample keys:")
            for k, z in keys[:40]:
                print("   ", k, z)


def plan(cfg, source="all"):
    s = settings(cfg)
    jobs = []
    if source in ("all", "wc"):
        jobs += ["wc-base"] + [f"wc:{g}" for g in wc_gcms(s)]
    if source in ("all", "aw"):
        pr = aw_products(s, cfg)
        if pr:
            jobs += ["aw-base"] + [f"aw:{lab}" for lab in sorted(pr)]
    return jobs


# --------------------------------------------------------------------------- extraction (network + rasterio)
def _places():
    T = C.targets()
    return T


def _wc_arr(src):
    import rasterio
    with rasterio.open(src) as r:
        a = r.read(masked=True).astype("float32").filled(np.nan)
        tr = r.transform
        return a, (tr.c, tr.f, tr.a, -tr.e)


def _wc_read(url, tmp, tries=4):
    for a in range(tries):
        try:
            return C.download(url, tmp)
        except PermissionError:
            return None                                   # 403/404: the file does not exist
        except Exception:  # noqa: BLE001
            if a == tries - 1:
                raise
            time.sleep(10)


class WCSampler:
    """Nearest-valid-pixel sampling with the pixel choice fixed from the first raster read (so base and future use the same pixel)."""

    def __init__(self, T, radius):
        self.T, self.radius, self.pix = T, radius, None

    def __call__(self, a, grid):
        if self.pix is None:
            self.pix = nearest_valid(np.isfinite(a[0]), self.T.lat.values, self.T.lon.values, *grid, radius=self.radius)
        return sample_pixels(a, *self.pix)


def run_wc_base(cfg, T=None):
    s = settings(cfg)
    T = T if T is not None else _places()
    sm, out, t0 = WCSampler(T, s["radius_px"]), {}, time.time()
    for v in VARS:
        zp = C.download(s["wc_base_url"].format(res=s["wc_res"], var=WC_VAR[v]), C.work("downloads", f"wc_base_{v}.zip"))
        cols = []
        for m in range(1, 13):
            a, grid = _wc_arr(f"zip://{zp}!wc2.1_{s['wc_res']}_{WC_VAR[v]}_{m:02d}.tif")
            cols.append(sm(a[None], grid)[:, 0])
        out[v] = np.stack(cols, axis=1)
        zp.unlink()
        C.log.info("wc base %s %.0fs", v, time.time() - t0)
    C.save(C.work(OUTDIR, "wc-base.npz"), labels=T.label.values.astype(str), **out)
    return out


def run_wc(gcm, cfg, T=None):
    s = settings(cfg)
    T = T if T is not None else _places()
    scen, per = list(s["scenarios"]), list(PERIODS)
    sm, t0 = WCSampler(T, s["radius_px"]), time.time()
    out = {v: np.full((len(per), len(scen), len(T), 12), np.nan, "float32") for v in VARS}
    missing = []
    for si, ssp in enumerate(scen):
        for pi, pk in enumerate(per):
            for v in VARS:
                url = s["wc_url"].format(res=s["wc_res"], gcm=gcm, ssp=ssp, var=WC_VAR[v], per=PERIODS[pk])
                tmp = _wc_read(url, C.work("downloads", f"wc_{gcm}.tif"))
                if tmp is None:
                    missing.append(f"{ssp}/{pk}/{v}")
                    continue
                a, grid = _wc_arr(tmp)
                out[v][pi, si] = sm(a, grid)
                tmp.unlink()
            C.log.info("wc %s %s %s %.0fs", gcm, ssp, pk, time.time() - t0)
    if missing:
        C.log.warning("wc %s: %d files missing: %s", gcm, len(missing), ", ".join(missing[:6]))
    if not any(np.isfinite(out[v]).any() for v in VARS):
        raise RuntimeError(f"WorldClim: no file found for {gcm}")
    C.save(C.work(OUTDIR, f"wc-{gcm}.npz"), labels=T.label.values.astype(str), scen=np.array(scen), periods=np.array(per), **out)


class AWSampler:
    """Mean of the 1 km cells within radius of each North American place; built from the first raster's grid."""

    def __init__(self, T, radius_m):
        self.na = np.where(T.g.values == 0)[0]
        self.T, self.radius, self.nb = T, radius_m, None

    def __call__(self, path):
        import rasterio
        from pyproj import Transformer
        with rasterio.open(path) as r:
            a = r.read(1).astype("float32")
            tr, crs, nd = r.transform, r.crs, r.nodata
        a[a < -1000] = np.nan
        if nd is not None:
            a[a == nd] = np.nan
        if self.nb is None:
            H, W = a.shape
            x = tr.c + (np.arange(W) + .5) * tr.a
            y = tr.f + (np.arange(H) + .5) * tr.e
            X, Y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(self.T.lon.values[self.na], self.T.lat.values[self.na])
            self.nb = neighbours(x, y, X, Y, tr, H, W, self.radius)
        out = np.full(len(self.T), np.nan)
        out[self.na] = neighbour_mean(a, self.nb)
        return out


def _aw_members(names):
    """{(var, month): member name} from a zip's member list (names like ..._Tmax01.tif, ..._PPT12.tif)."""
    got = {}
    for n in names:
        m = re.search(r"(Tmax|Tmin|PPT)[_-]?(\d{2})\.tif$", n, re.I)
        if m and 1 <= int(m.group(2)) <= 12:
            got[({"tmax": "tmax", "tmin": "tmin", "ppt": "ppt"}[m.group(1).lower()], int(m.group(2)))] = n
    return got


def aw_extract(url_or_key, size, sm, s, tag):
    """(3 vars) monthly values (NT, 12) from one AdaptWest product (a zip of monthly tifs, streamed member by member)."""
    from remotezip import RemoteZip
    url = url_or_key if url_or_key.startswith("http") else f"{s['aw_bucket']}/{url_or_key}"
    out = {v: np.full((len(sm.T), 12), np.nan) for v in VARS}
    if not url.lower().endswith(".zip"):
        raise RuntimeError(f"not a zip: {url}")
    with RemoteZip(url) as rz:
        mem = _aw_members(rz.namelist())
        if len(mem) < 36:
            raise RuntimeError(f"{url}: {len(mem)} monthly tmax/tmin/ppt members (need 36); is it a monthly product?")
        tmp = C.work("downloads", f"aw_{tag}.tif")
        for (v, m), name in sorted(mem.items()):
            with rz.open(name) as src, open(tmp, "wb") as dst:
                while chunk := src.read(1 << 22):
                    dst.write(chunk)
            out[v][:, m - 1] = sm(tmp)
            tmp.unlink()
    return out


def run_aw_base(cfg, T=None):
    s = settings(cfg)
    T = T if T is not None else _places()
    t0 = time.time()
    out = aw_extract(cfg["sources"]["adaptwest"], 0, AWSampler(T, s["aw_radius_m"]), s, "base")
    C.log.info("aw base %.0fs", time.time() - t0)
    C.save(C.work(OUTDIR, "aw-base.npz"), labels=T.label.values.astype(str), **out)


def run_aw(label, cfg, T=None):
    s = settings(cfg)
    T = T if T is not None else _places()
    prods = aw_products(s, cfg)[label]
    scen, per = list(s["scenarios"]), list(PERIODS)
    sm, t0 = AWSampler(T, s["aw_radius_m"]), time.time()
    out = {v: np.full((len(per), len(scen), len(T), 12), np.nan, "float32") for v in VARS}
    for (ssp, pk), (key, size) in sorted(prods.items()):
        if size > s["aw_max_gb"] * 1e9:
            C.log.warning("aw %s: %s is %.1f GB, skipped", label, key, size / 1e9)
            continue
        try:
            r = aw_extract(key, size, sm, s, label)
        except Exception as e:  # noqa: BLE001
            C.log.warning("aw %s %s %s failed: %s", label, ssp, pk, e)
            continue
        for v in VARS:
            out[v][per.index(pk), scen.index(ssp)] = r[v]
        C.log.info("aw %s %s %s %.0fs (%s)", label, ssp, pk, time.time() - t0, key)
    if not any(np.isfinite(out[v]).any() for v in VARS):
        raise RuntimeError(f"AdaptWest: nothing extracted for {label}")
    C.save(C.work(OUTDIR, f"aw-{label}.npz"), labels=T.label.values.astype(str), scen=np.array(scen), periods=np.array(per), **out)


def run_job(job, cfg=None):
    cfg = cfg or C.config()
    kind, _, name = job.partition(":")
    if kind == "wc-base": return run_wc_base(cfg)
    if kind == "aw-base": return run_aw_base(cfg)
    if kind == "wc": return run_wc(name, cfg)
    if kind == "aw": return run_aw(name, cfg)
    raise ValueError(f"unknown job {job}")


# --------------------------------------------------------------------------- aggregate
def fold(files, base, names, labels, dry_mm=0.5):
    """Changes for one source. files: list of dict-likes (tmax, tmin, ppt: (P, S, NT, 12)); base: dict (NT, 12).
    Returns dtx, dtn, rp (M, P, S, NT, 12) float32."""
    d = [make_delta(z, base, dry_mm) for z in files]
    return tuple(np.stack([x[k] for x in d]).astype("float32") for k in range(3))


def aggregate(cfg=None, out=None, work=None):
    cfg = cfg or C.config()
    s = settings(cfg)
    T = C.targets()
    wd = work or (C.WORK / OUTDIR)
    res, meta = {}, {}
    for src in ("wc", "aw"):
        bp = wd / f"{src}-base.npz"
        fs = sorted(f for f in wd.glob(f"{src}-*.npz") if f.name != f"{src}-base.npz")
        if not bp.exists() or not fs:
            C.log.info("downdeltas: no %s data (%s base, %d models)", src, "with" if bp.exists() else "no", len(fs))
            continue
        B = C.load(bp)
        Zs = [C.load(f) for f in fs]
        good = [k for k, z in enumerate(Zs) if "tmax" in z and [str(x) for x in z["labels"]] == [str(x) for x in B["labels"]]]
        ok, names = [Zs[k] for k in good], [fs[k].name[len(src) + 1:-4] for k in good]
        dtx, dtn, rp = fold(ok, B, names, B["labels"], 1.0)             # months drier than 1 mm keep ratio 1
        res[src] = (names, [str(x) for x in ok[0]["scen"]], dtx, dtn, rp)
        C.log.info("downdeltas %s: %d models", src, len(names))
    if not res:
        raise RuntimeError("downdeltas: nothing to aggregate")
    payload = {"labels": np.array(T.label.values.astype(str)), "lat": T.lat.values.astype("float32"), "lon": T.lon.values.astype("float32"),
               "periods": np.array(cfg["periods"]["keys"])}
    for src, (names, scen, dtx, dtn, rp) in res.items():
        payload |= {f"{src}_models": np.array(names), f"{src}_scen": np.array(scen), f"{src}_dtx": dtx.astype("float16"),
                    f"{src}_dtn": dtn.astype("float16"), f"{src}_rp": rp.astype("float16")}
    path = out or OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)
    C.log.info("downdeltas.npz: %s, %.1f MB", {k: len(v[0]) for k, v in res.items()}, path.stat().st_size / 1e6)
    return path


def table(path=None, n=12):
    """Compact per-place table for the smoke run: mean annual change (deg C tmax, ppt ratio) per source, first and last period."""
    Z = C.load(path or OUT)
    lab = [str(x) for x in Z["labels"]]
    print(f"{'place':34s}" + "".join(f"{src + ' dT50':>10s}{src + ' dT100':>10s}{src + ' P50':>9s}{src + ' P100':>9s}" for src in ("wc", "aw") if f"{src}_dtx" in Z))
    for i in range(min(n, len(lab))):
        row = f"{lab[i][:33]:34s}"
        for src in ("wc", "aw"):
            if f"{src}_dtx" not in Z:
                continue
            for k, f in (("dtx", "{:10.2f}"), ("rp", "{:9.2f}")):
                a = Z[f"{src}_{k}"].astype("float64")[:, :, -1, i]                        # (M, P, 12) for the last scenario
                for p in range(a.shape[1]):
                    v = np.nanmean(a[:, p]) if np.isfinite(a[:, p]).any() else np.nan
                    row += f.format(v)
        print(row)
