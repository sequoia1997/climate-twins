"""CMIP6 monthly climatologies at every place, one model per job (Eyring et al. 2016; Pangeo archive,
Abernathey et al. 2021). Variables: tasmax, tasmin, pr and huss (specific humidity, for the humidity change).

Windows: baseline = historical 1991-2014 joined to each scenario's 2015-2020 (weighted by years), and the
future periods of every scenario. Each place gets a land-weighted Gaussian average of nearby model cells
(length scale one grid spacing, cut off at two). Writes work/cmip6/<model>.npz:
  base (nssp, 4, NT, 12)   fut (nper, nssp, 4, NT, 12)   variable order tasmax, tasmin, pr, huss
A variable a model does not provide for a scenario is NaN; the analog step fills humidity by
constant relative humidity (Clausius-Clapeyron) in that case."""
from __future__ import annotations
import json, math, re, time, warnings
import numpy as np
import pandas as pd
from . import common as C

VARS = ("tasmax", "tasmin", "pr", "huss")
warnings.filterwarnings("ignore")


class Archive:
    def __init__(self, cfg):
        slim = C.work("downloads", "pangeo_cmip6_slim.csv")
        if not slim.exists():
            raw = C.download(cfg["sources"]["pangeo_catalog"], C.work("downloads", "pangeo-cmip6.csv"))
            cols = ["source_id", "experiment_id", "member_id", "table_id", "variable_id", "grid_label", "zstore", "version"]
            df = pd.read_csv(raw, usecols=cols)
            keep = ((df.table_id == "Amon") & df.variable_id.isin(VARS)) | ((df.table_id == "fx") & (df.variable_id == "sftlf"))
            df = df[keep & df.experiment_id.isin(("historical", "piControl") + tuple(cfg["scenarios"]["ids"]))]
            df = df.sort_values("version").groupby(["source_id", "experiment_id", "member_id", "table_id", "variable_id", "grid_label"]).tail(1)
            df.to_csv(slim, index=False)
            raw.unlink(missing_ok=True)
        self.df = pd.read_csv(slim)

    def row(self, src, exp, mem, var, grid, table="Amon"):
        d = self.df
        s = d[(d.source_id == src) & (d.experiment_id == exp) & (d.member_id == mem) & (d.table_id == table)
              & (d.variable_id == var) & (d.grid_label == grid)]
        return None if s.empty else s.iloc[-1]

    def url(self, *a, **k):
        r = self.row(*a, **k)
        return None if r is None else r.zstore.replace("gs://", "https://storage.googleapis.com/")

    def versions(self, models, scen):
        """Dataset versions in use, recorded so the monthly watcher can spot corrections or retractions."""
        out = {}
        for m in models:
            for e in ("historical",) + tuple(scen):
                for v in VARS:
                    r = self.row(m["name"], e, m["member"], v, m["grid"])
                    if r is not None:
                        out[f"{m['name']}|{e}|{v}"] = int(r.version)
        return out


def open_da(url, var):
    import aiohttp, xarray as xr
    so = {"client_kwargs": {"timeout": aiohttp.ClientTimeout(total=1800, sock_connect=60, sock_read=300)}}
    for attempt in range(6):
        try:
            ds = xr.open_zarr(url, consolidated=True, chunks={}, storage_options=so)
            break
        except Exception as e:  # noqa: BLE001
            C.log.warning("open failed %s (%s), retrying", url, e)
            time.sleep(30 * (attempt + 1))
    else:
        raise RuntimeError(f"cannot open {url}")
    da = ds[var]
    ren = {k: v for k, v in (("latitude", "lat"), ("longitude", "lon"), ("nav_lat", "lat"), ("nav_lon", "lon")) if k in da.coords or k in da.dims}
    da = da.rename(ren) if ren else da
    if da["lat"].ndim != 1:
        raise ValueError("curvilinear grid not supported")
    return da


def clims(da, wins: dict) -> dict:
    """Monthly climatologies for several year windows, reading each zarr time-chunk once (low memory)."""
    yrs = da["time"].dt.year.values
    mon = da["time"].dt.month.values
    acc = {w: np.zeros((12,) + da.shape[1:], "float64") for w in wins}
    cnt = {w: np.zeros(12) for w in wins}
    edges = np.cumsum((0,) + da.chunks[0])
    for a, b in zip(edges[:-1], edges[1:]):
        need = [w for w, (y0, y1) in wins.items() if ((yrs[a:b] >= y0) & (yrs[a:b] <= y1)).any()]
        if not need:
            continue
        for attempt in range(6):
            try:
                blk = np.asarray(da.isel(time=slice(a, b)).values, "float32")
                break
            except Exception as e:  # noqa: BLE001
                C.log.warning("chunk read failed (%s), retrying", e)
                time.sleep(20 * (attempt + 1))
        else:
            raise RuntimeError("chunk read failed repeatedly")
        for w in need:
            y0, y1 = wins[w]
            for i in np.where((yrs[a:b] >= y0) & (yrs[a:b] <= y1))[0]:
                acc[w][mon[a + i] - 1] += blk[i]
                cnt[w][mon[a + i] - 1] += 1
        del blk
    out = {}
    for w, (y0, y1) in wins.items():
        n, need = cnt[w], y1 - y0 + 1
        if n.min() < 0.95 * need:
            raise ValueError(f"{w}: only {n.min():.0f}/{need} years")
        out[w] = (acc[w].T / n).T
        out[w + "_n"] = int(n.min())
    return out


_REF = {}


def landfrac(arch, src, grid, lat, lon):
    """sftlf (0-1) on the model grid; a high-resolution model's mask interpolated if the model has none."""
    import xarray as xr
    r = arch.df[(arch.df.source_id == src) & (arch.df.variable_id == "sftlf") & (arch.df.grid_label == grid)]
    try:
        if len(r):
            lf = open_da(r.zstore.iloc[-1].replace("gs://", "https://storage.googleapis.com/"), "sftlf")
            lf = lf.sel(lat=xr.DataArray(lat, dims="lat"), lon=xr.DataArray(lon, dims="lon"), method="nearest").values.astype(float)
            return (lf / 100.0 if np.nanmax(lf) > 1.5 else lf), "sftlf"
    except Exception as e:  # noqa: BLE001
        C.log.warning("%s: sftlf failed (%s); using reference mask", src, e)
    if "ref" not in _REF:
        s = arch.df[(arch.df.source_id == "CNRM-CM6-1-HR") & (arch.df.variable_id == "sftlf")]
        ref = open_da(s.zstore.iloc[-1].replace("gs://", "https://storage.googleapis.com/"), "sftlf").load()
        _REF["ref"] = ref / 100.0 if float(ref.max()) > 1.5 else ref
    ref = _REF["ref"]
    rl = np.where(lon > 180, lon - 360, lon) if float(ref.lon.max()) <= 180 else np.mod(lon, 360)
    lf = ref.interp(lat=xr.DataArray(lat, dims="lat"), lon=xr.DataArray(rl, dims="lon"), method="linear").values
    return np.nan_to_num(lf, nan=0.0), "reference-mask"


def weights(lat, lon, lf, tlat, tlon):
    """Sparse land-weighted Gaussian kernel around one place: (rows, cols, w) with w summing to 1."""
    wrap = lon.max() > 180
    tl = tlon + 360 if (wrap and tlon < 0) else tlon
    dy = np.median(np.abs(np.diff(lat))) * 111.2
    dx = np.median(np.abs(np.diff(lon))) * 111.2 * math.cos(math.radians(tlat))
    L = max(dx, dy)
    ii = np.where(np.abs(lat - tlat) * 111.2 <= 2 * L + 1)[0]
    LAT, LON = np.meshgrid(lat[ii], lon, indexing="ij")
    d = C.haversine_km(tlat, tl, LAT, LON)
    w = np.exp(-(d / L) ** 2) * (d <= 2 * L)
    wl = w * lf[ii]
    if wl.sum() > 0.05 * w.sum():
        w = wl
    r, c = np.nonzero(w)
    return ii[r], c, w[r, c] / w.sum()


def run(model: str, cfg=None):
    cfg = cfg or C.config()
    m = next(x for x in C.models(cfg) if x["name"] == model)
    out_f = C.work("cmip6", f"{model}.npz")
    if out_f.exists():
        C.log.info("%s already done", model)
        return
    arch = Archive(cfg)
    T = C.targets()
    scen, pers = cfg["scenarios"]["ids"], cfg["periods"]["years"]
    b0, b1 = cfg["baseline"]["years"]
    hist_end = min(b1, 2014)
    NT = len(T)
    base = np.full((len(scen), len(VARS), NT, 12), np.nan, "float32")
    fut = np.full((len(pers), len(scen), len(VARS), NT, 12), np.nan, "float32")
    W = None
    t0 = time.time()
    missing = []
    for vi, var in enumerate(VARS):
        u = arch.url(model, "historical", m["member"], var, m["grid"])
        if u is None:
            missing.append(f"historical:{var}")
            continue
        h = open_da(u, var)
        if W is None:
            lat, lon = h["lat"].values.astype("float64"), h["lon"].values.astype("float64")
            lf, lfsrc = landfrac(arch, model, m["grid"], lat, lon)
            W = [weights(lat, lon, lf, a, o) for a, o in zip(T.lat.values, T.lon.values)]
        at = lambda F: np.stack([(F[:, r, c] * w).sum(1) for r, c, w in W], 0)     # (12, ...) -> (NT, 12)
        hc = clims(h, {"hist": (b0, hist_end)})
        for si, s in enumerate(scen):
            u = arch.url(model, s, m["member"], var, m["grid"])
            if u is None:
                missing.append(f"{s}:{var}")
                continue
            wins = {"early": (2015, b1)} if b1 >= 2015 else {}
            wins.update({f"p{pi}": tuple(p) for pi, p in enumerate(pers)})
            sc = clims(open_da(u, var), wins)
            if "early" in sc:
                bf = (hc["hist"] * hc["hist_n"] + sc["early"] * sc["early_n"]) / (hc["hist_n"] + sc["early_n"])
            else:
                bf = hc["hist"]
            base[si, vi] = at(bf)
            for pi in range(len(pers)):
                fut[pi, si, vi] = at(sc[f"p{pi}"])
        C.log.info("%s %s done %.0fs", model, var, time.time() - t0)
    if W is None:
        raise RuntimeError(f"{model}: no data")
    if any(x.split(":")[1] != "huss" for x in missing):
        raise RuntimeError(f"{model}: missing required data {missing}")
    C.save(out_f, base=base, fut=fut, vars=np.array(VARS), labels=T.label.values.astype(str),
           missing=np.array(missing), landfrac_src=np.array(lfsrc), grid=np.array([len(lat), len(lon)]),
           versions=np.array(json.dumps(arch.versions([m], scen))))
    C.log.info("%s written (%s) missing=%s %.0fs", model, lfsrc, missing, time.time() - t0)
