"""CMIP6 monthly climatologies at every place, one model per job (Eyring et al. 2016; Pangeo archive,
Abernathey et al. 2021). Variables: tasmax, tasmin, pr and huss (specific humidity, for the humidity change).

Windows: baseline = historical 1991-2014 joined to each scenario's 2015-2020 (weighted by years), and the
future periods of every scenario. Each place gets a land-weighted Gaussian average of nearby model cells
(length scale one grid spacing, cut off at two). Writes work/cmip6/<model>.npz:
  base (nssp, 4, NT, 12)   fut (nper, nssp, 4, NT, 12)   variable order tasmax, tasmin, pr, huss
A variable a model does not provide for a scenario is NaN; the analog step fills humidity by
constant relative humidity (Clausius-Clapeyron) in that case.

Ensemble members: config.toml [models] members_max (and an optional per-model members_max) sets how many
initial-condition members are averaged per model, so 20-year windows carry less internal variability. The configured
member always comes first; the others share its physics and forcing indices (p, f) and must have every core variable
in the historical run and all scenarios. Climatologies are averaged over members before anything else, and the members
used are recorded in the file and the manifest. members_max = 1 gives the earlier single-member behaviour.

Global warming levels (gwl.py): the global mean annual tas of each model (member mean) is read for 1850-1900 and
1985-2100, the year each level in [gwl] is reached is found for every scenario, and the 20-year windows centred on
those years are averaged like the fixed periods:
  gwl_fut (nlev, nssp, 4, NT, 12)  NaN where the scenario never reaches the level   gwl_year (nlev, nssp)  0 = never"""
from __future__ import annotations
import json, math, re, time, warnings
import numpy as np
import pandas as pd
from . import common as C
from . import gwl as G

VARS = ("tasmax", "tasmin", "pr", "huss")
CORE = ("tasmax", "tasmin", "pr")                 # a member needs these in every run to be used (huss may be missing)
GVARS = VARS + ("tas",)                            # tas: global mean, for warming levels only
TAS_YEARS = np.r_[np.arange(1850, 1901), np.arange(1985, 2101)]      # years read for the global mean
_MEM = re.compile(r"r(\d+)i(\d+)p(\d+)f(\d+)$")
warnings.filterwarnings("ignore")


class Archive:
    def __init__(self, cfg):
        slim = C.work("downloads", "pangeo_cmip6_slim_v2.csv")
        if not slim.exists():
            raw = C.download(cfg["sources"]["pangeo_catalog"], C.work("downloads", "pangeo-cmip6.csv"))
            cols = ["source_id", "experiment_id", "member_id", "table_id", "variable_id", "grid_label", "zstore", "version"]
            df = pd.read_csv(raw, usecols=cols)
            keep = ((df.table_id == "Amon") & df.variable_id.isin(GVARS)) | ((df.table_id == "fx") & (df.variable_id == "sftlf"))
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

    def members(self, m, nmax, scen):
        """Members to average for model m: the configured member first, then others with the same physics and forcing
        indices that have tasmax, tasmin and pr in the historical run and every scenario, in run-number order."""
        first = m["member"]
        if nmax <= 1:
            return [first]
        d = self.df[(self.df.source_id == m["name"]) & (self.df.grid_label == m["grid"]) & (self.df.table_id == "Amon")]
        mm = _MEM.match(first)
        ok = None
        for e in ("historical",) + tuple(scen):
            for v in CORE:
                have = set(d[(d.experiment_id == e) & (d.variable_id == v)].member_id)
                ok = have if ok is None else ok & have
        cand = []
        for x in ok or ():
            q = _MEM.match(x)
            if x != first and q and mm and q.group(3) == mm.group(3) and q.group(4) == mm.group(4):
                cand.append((int(q.group(1)), int(q.group(2)), x))
        return [first] + [x for _, _, x in sorted(cand)][:nmax - 1]

    def versions(self, m, members, scen):
        """Dataset versions in use, recorded so the monthly watcher can spot corrections or retractions.
        Keys are model|experiment|variable for the configured member (as before) and model|experiment|variable|member
        for the others."""
        out = {}
        for mem in members:
            for e in ("historical",) + tuple(scen):
                for v in GVARS:
                    r = self.row(m["name"], e, mem, v, m["grid"])
                    if r is not None:
                        out[f"{m['name']}|{e}|{v}" + ("" if mem == m["member"] else f"|{mem}")] = int(r.version)
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


def annual_gmean(da, years) -> dict:
    """Area-weighted global mean of a monthly field as {year: annual mean}, reading only the time chunks that hold
    the wanted years. A year needs all 12 months."""
    yrs = da["time"].dt.year.values
    lat = da["lat"].values.astype("float64")
    w = np.cos(np.radians(lat)); w /= w.sum()
    want = np.isin(yrs, list(years))
    tot, cnt = {}, {}
    edges = np.cumsum((0,) + da.chunks[0])
    for a, b in zip(edges[:-1], edges[1:]):
        if not want[a:b].any():
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
        gm = (np.nanmean(blk, axis=2) * w[None, :]).sum(1)
        for i in np.where(want[a:b])[0]:
            y = int(yrs[a + i])
            tot[y] = tot.get(y, 0.0) + float(gm[i]); cnt[y] = cnt.get(y, 0) + 1
        del blk
    return {y: tot[y] / 12 for y in tot if cnt[y] == 12}


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


def _combine(parts):
    """Weighted mean of (climatology, n_years) parts, e.g. the historical and scenario halves of a window."""
    return sum(c * n for c, n in parts) / sum(n for _, n in parts)


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
    levels, ref = list(cfg["gwl"]["levels"]), tuple(cfg["gwl"]["reference"])
    NT, NS, NL = len(T), len(scen), len(levels)
    nmax = int(m.get("members_max", cfg["models"].get("members_max", 1)))
    members = arch.members(m, nmax, scen)
    C.log.info("%s: %d member(s): %s", model, len(members), members)

    # ---- global mean tas per member and scenario -> the year each warming level is reached
    tas_years = np.arange(1850, 2101)
    tas_all = np.full((len(members), NS, len(tas_years)), np.nan)
    for mi, mem in enumerate(members):
        u = arch.url(model, "historical", mem, "tas", m["grid"])
        if u is None:
            continue
        hg = annual_gmean(open_da(u, "tas"), TAS_YEARS)
        for si, s in enumerate(scen):
            us = arch.url(model, s, mem, "tas", m["grid"])
            if us is None:
                continue
            sg = annual_gmean(open_da(us, "tas"), TAS_YEARS)
            both = {**hg, **sg}
            tas_all[mi, si] = [both.get(int(y), np.nan) for y in tas_years]
    full = np.isfinite(tas_all[..., TAS_YEARS - 1850]).all(-1)                  # (members, scenarios): complete series
    tas_mem = [members[i] for i in range(len(members)) if full[i].any()]
    tas_ann = np.full((NS, len(tas_years)), np.nan)
    gwl_year = np.zeros((NL, NS), int)
    for si in range(NS):
        ok = np.nonzero(full[:, si])[0]
        if len(ok):
            tas_ann[si] = tas_all[ok, si].mean(0)
            gwl_year[:, si] = G.crossing_years(tas_years, tas_ann[si], levels, ref)
    now = [np.nanmean(tas_ann[si, (tas_years >= b0) & (tas_years <= b1)]) - G.reference(tas_years, tas_ann[si], ref)
           for si in range(NS) if np.isfinite(tas_ann[si]).any()]
    gwl_now = float(np.mean(now)) if now else float("nan")
    C.log.info("%s warming levels %s reached (rows: levels; columns: %s): %s; %d-%d mean is %+.2f above %d-%d", model, levels, scen,
               gwl_year.tolist(), b0, b1, gwl_now, *ref)
    gwin = {(li, si): G.window(gwl_year[li, si]) for li in range(NL) for si in range(NS) if gwl_year[li, si]}

    # ---- local monthly climatologies, averaged over members
    bsum = np.zeros((NS, len(VARS), NT, 12)); psum = np.zeros((len(pers), NS, len(VARS), NT, 12))
    gsum = np.zeros((NL, NS, len(VARS), NT, 12)); cnt = np.zeros((NS, len(VARS)))
    W = None
    t0 = time.time()
    missing = []
    for mem in members:
        for vi, var in enumerate(VARS):
            u = arch.url(model, "historical", mem, var, m["grid"])
            if u is None:
                missing.append(f"{mem}:historical:{var}")
                continue
            h = open_da(u, var)
            if W is None:
                lat, lon = h["lat"].values.astype("float64"), h["lon"].values.astype("float64")
                lf, lfsrc = landfrac(arch, model, m["grid"], lat, lon)
                W = [weights(lat, lon, lf, a, o) for a, o in zip(T.lat.values, T.lon.values)]
            at = lambda F: np.stack([(F[:, r, c] * w).sum(1) for r, c, w in W], 0)     # (12, ...) -> (NT, 12)
            hwins = {"hist": (b0, hist_end)}
            hwins.update({f"g{y0}_{y1}": (y0, min(y1, 2014)) for y0, y1 in gwin.values() if y0 <= 2014})
            hc = clims(h, hwins)
            for si, s in enumerate(scen):
                u = arch.url(model, s, mem, var, m["grid"])
                if u is None:
                    missing.append(f"{mem}:{s}:{var}")
                    continue
                wins = {"early": (2015, b1)} if b1 >= 2015 else {}
                wins.update({f"p{pi}": tuple(p) for pi, p in enumerate(pers)})
                wins.update({f"g{li}": (max(y0, 2015), y1) for (li, sj), (y0, y1) in gwin.items() if sj == si and y1 >= 2015})
                sc = clims(open_da(u, var), wins)
                if "early" in sc:
                    bf = (hc["hist"] * hc["hist_n"] + sc["early"] * sc["early_n"]) / (hc["hist_n"] + sc["early_n"])
                else:
                    bf = hc["hist"]
                bsum[si, vi] += at(bf)
                for pi in range(len(pers)):
                    psum[pi, si, vi] += at(sc[f"p{pi}"])
                for (li, sj), (y0, y1) in gwin.items():
                    if sj != si:
                        continue
                    parts = []
                    if y0 <= 2014:
                        k = f"g{y0}_{y1}"; parts.append((hc[k], hc[k + "_n"]))
                    if y1 >= 2015:
                        parts.append((sc[f"g{li}"], sc[f"g{li}_n"]))
                    gsum[li, si, vi] += at(_combine(parts))
                cnt[si, vi] += 1
            C.log.info("%s %s %s done %.0fs", model, mem, var, time.time() - t0)
    if W is None:
        raise RuntimeError(f"{model}: no data")
    bad = [f"{scen[si]}:{VARS[vi]}" for si in range(NS) for vi in range(len(VARS)) if cnt[si, vi] == 0 and VARS[vi] != "huss"]
    if bad:
        raise RuntimeError(f"{model}: missing required data {bad} {missing}")
    with np.errstate(invalid="ignore", divide="ignore"):
        n = cnt.astype("float64")
        base = np.where(n[..., None, None] > 0, bsum / n[..., None, None], np.nan).astype("float32")
        fut = np.where(n[None, ..., None, None] > 0, psum / n[None, ..., None, None], np.nan).astype("float32")
        gfut = np.where(n[None, ..., None, None] > 0, gsum / n[None, ..., None, None], np.nan).astype("float32")
    gfut[gwl_year == 0] = np.nan                                       # scenario never reaches the level
    used = {"used": members, "tas": tas_mem,
            "per_scenario_var": {f"{scen[si]}:{VARS[vi]}": int(cnt[si, vi]) for si in range(NS) for vi in range(len(VARS))}}
    C.save(out_f, base=base, fut=fut, vars=np.array(VARS), labels=T.label.values.astype(str),
           missing=np.array(missing), landfrac_src=np.array(lfsrc), grid=np.array([len(lat), len(lon)]),
           versions=np.array(json.dumps(arch.versions(m, members, scen))), members=np.array(json.dumps(used)),
           gwl_levels=np.array(levels, "float64"), gwl_year=gwl_year, gwl_fut=gfut, gwl_now=np.array(gwl_now),
           tas_years=tas_years, tas_ann=tas_ann.astype("float32"), gwl_ref=np.array(ref))
    C.log.info("%s written (%s) members=%d missing=%s %.0fs", model, lfsrc, len(members), missing, time.time() - t0)
