"""Shared pieces: configuration, paths, downloads, geography, the climate measures and the sigma metric.

Climate vector (16 values per place, in this order):
  0-3   mean daily maximum temperature, °C          DJF MAM JJA SON
  4-7   mean daily minimum temperature, °C          DJF MAM JJA SON
  8-11  total precipitation, mm (log(mm+1) in the metric)
  12-15 mean dewpoint, °C (from mean vapour pressure)
Matching uses 0-11, plus 12 (DJF) and 14 (JJA) when humidity is on. 13 and 15 are shown, not matched.
Optional extra variables ([matching] extra = ["pet", "srad"], default none) append 4 seasonal columns each
(16-19 for the first, 20-23 for the second); [matching] extra_seasons (default DJF and JJA) picks which are matched.
"""
from __future__ import annotations
import logging, math, os, time, tomllib
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from scipy import special

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE = ROOT / "site"
WORK = Path(os.environ.get("CTW_WORK", ROOT / "work"))
SMOKE = os.environ.get("CTW_SMOKE", "") not in ("", "0")        # small, fast runs for testing the code paths

log = logging.getLogger("ctw")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
for _n in ("urllib3", "fsspec", "asyncio", "rasterio"):
    logging.getLogger(_n).setLevel(logging.WARNING)


def config() -> dict:
    with open(ROOT / "config.toml", "rb") as f:
        c = tomllib.load(f)
    if os.environ.get("CTW_EXTRA") is not None and os.environ["CTW_EXTRA"].strip() != "":
        c["matching"]["extra"] = [x.strip() for x in os.environ["CTW_EXTRA"].split(",") if x.strip()]   # workflow_dispatch override
    if SMOKE:                                                     # a couple of models is enough to test the code
        keep = os.environ.get("CTW_SMOKE_MODELS", "MIROC6,MRI-ESM2-0").split(",")
        c["models"]["list"] = [m for m in c["models"]["list"] if m["name"] in keep]
    return c


def models(cfg) -> list[dict]:
    return cfg["models"]["list"]


def ensembles(cfg) -> dict:
    lo, hi = cfg["models"]["tcr_likely"]
    ms = models(cfg)
    return {"tcr_likely": [i for i, m in enumerate(ms) if lo <= m["tcr"] <= hi], "all": list(range(len(ms)))}


def work(*parts) -> Path:
    p = WORK.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# --------------------------------------------------------------------------- places
def targets() -> pd.DataFrame:
    """All places, North America first (g=0), then the world cities (g=1). Order is fixed: it is the page's order."""
    na = pd.read_csv(DATA / "targets.csv")
    w = pd.read_csv(DATA / "world_targets.csv", keep_default_na=False, na_values={"lat": [""], "lon": [""]})
    na = na.assign(g=0)
    w = w.assign(g=1, domain="world")
    cols = ["label", "country", "admin1", "lat", "lon", "pop", "domain", "g"]
    t = pd.concat([na[cols], w[cols]], ignore_index=True)
    if SMOKE:
        pick = os.environ.get("CTW_SMOKE_PLACES", "Shallotte, NC|Raleigh, NC|Phoenix, AZ|Anchorage, AK|Vancouver, British Columbia, CA|Monterrey, Nuevo León, MX"
                              "|Lisbon, Portugal|Singapore, Singapore|Cairo, Egypt|Sydney, Australia|Reykjavík, Iceland|Lima, Peru")
        t = t[t.label.isin(pick.split("|"))].reset_index(drop=True)
    return t


# --------------------------------------------------------------------------- IO
def http() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "climate-twins-pipeline (+https://github.com)"
    return s


def download(url: str, dest: Path, tries: int = 8, timeout: int = 300) -> Path:
    """Streamed download with retries; resumes a partial file where the server allows it."""
    dest = Path(dest)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(tries):
        try:
            have = part.stat().st_size if part.exists() else 0
            hdr = {"Range": f"bytes={have}-"} if have else {}
            with http().get(url, stream=True, timeout=timeout, headers=hdr) as r:
                if r.status_code == 416:           # already complete
                    break
                if r.status_code in (401, 403, 404, 410):
                    raise PermissionError(f"{r.status_code} for {url}")   # permanent: do not keep retrying
                r.raise_for_status()
                mode = "ab" if (have and r.status_code == 206) else "wb"
                with open(part, mode) as fh:
                    for ch in r.iter_content(1 << 22):
                        fh.write(ch)
            break
        except PermissionError:
            raise
        except Exception as e:                      # noqa: BLE001 - network errors of every kind get a retry
            wait = min(300, 15 * 2 ** attempt)
            log.warning("download failed (%s) %s; retry in %ss", e, url, wait)
            time.sleep(wait)
    else:
        raise RuntimeError(f"could not download {url}")
    os.replace(part, dest)
    return dest


def save(path: Path, **arrays):
    """Atomic npz write, so an interrupted job never leaves a half-written file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)


def load(path: Path) -> dict:
    with np.load(path, allow_pickle=True) as z:
        return {k: z[k] for k in z.files}


# --------------------------------------------------------------------------- geography
R_EARTH = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(np.minimum(1.0, a)))


def unit_xyz(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]


# --------------------------------------------------------------------------- climate measures
SEASONS = ((12, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11))
MONTHLY = ("tmax", "tmin", "ppt", "vap")
NV = 16
PPT = slice(8, 12)
DPM = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


# Optional extra matched variables. Each is a TerraClimate variable turned into 4 seasonal columns appended after
# the 16 standard ones. "log": matched as log(x+1) like precipitation; "div": matched as x / div (so that the
# seasonal SD is of order 1 and the shared variability floor means something). ENC_SCALE: int16 scale on the page.
EXTRAS = {"pet": {"log": True, "div": 1.0, "sum": True}, "srad": {"log": False, "div": 10.0, "sum": False}}
ENC_SCALE = 500.0
_ACTIVE: list = []


def extra_names(cfg) -> list:
    names = list(cfg["matching"].get("extra", []) or [])
    bad = [n for n in names if n not in EXTRAS]
    if bad:
        raise ValueError(f"unknown [matching] extra {bad}; choose from {sorted(EXTRAS)}")
    return names


def use_extras(names) -> list:
    """Declare which extras the vectors carry (module state, so seasonalize/transform/enc need no new arguments)."""
    _ACTIVE[:] = list(names)
    return _ACTIVE


def nvx(names=None) -> int:
    return NV + 4 * len(_ACTIVE if names is None else names)


def match_idx(cfg) -> np.ndarray:
    idx = np.r_[np.arange(12), [12, 14]] if cfg["matching"]["humidity"] else np.arange(12)
    seas = cfg["matching"].get("extra_seasons", [0, 2])
    ex = [NV + 4 * j + int(s) for j in range(len(extra_names(cfg))) for s in seas]
    return np.r_[idx, ex].astype(int)


def hargreaves_pet(tmax, tmin, lat):
    """Hargreaves & Samani (1985) monthly PET (mm/month) from monthly tmax, tmin (12, N) and latitude (N,).
    Extraterrestrial radiation from FAO-56 (Allen et al. 1998, eq. 21) at mid-month. Used only as a ratio between
    a projected and a baseline climate, so its known bias against Penman-Monteith cancels to first order."""
    tx, tn = np.asarray(tmax, "float64"), np.asarray(tmin, "float64")
    phi = np.radians(np.asarray(lat, "float64"))[None, :]
    J = (np.cumsum(DPM) - DPM / 2)[:, None]
    dr = 1 + 0.033 * np.cos(2 * np.pi * J / 365)
    dec = 0.409 * np.sin(2 * np.pi * J / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    ra_mm = np.maximum(ra, 0) / 2.45
    return 0.0023 * ra_mm * np.maximum((tx + tn) / 2 + 17.8, 0) * np.sqrt(np.maximum(tx - tn, 0.1)) * DPM[:, None]


def dewpoint(e_kpa):
    """Dewpoint (°C) from vapour pressure (kPa): Magnus form over water, Alduchov & Eskridge (1996)."""
    x = np.log(np.maximum(np.asarray(e_kpa, "float64"), 1e-4) / 0.61094)
    return 243.04 * x / (17.625 - x)


def sat_vap(t_c):
    """Saturation vapour pressure (kPa) at temperature t (°C), same Magnus constants."""
    t = np.asarray(t_c, "float64")
    return 0.61094 * np.exp(17.625 * t / (t + 243.04))


def seasonalize(mon: dict) -> np.ndarray:
    """Monthly normals {var: (12, ...)} -> the 16-value seasonal vector (16, ...). vap may be absent (NaN)."""
    out = []
    for v in ("tmax", "tmin", "ppt"):
        a = np.asarray(mon[v], "float64")
        for ms in SEASONS:
            idx = [m - 1 for m in ms]
            out.append(a[idx].sum(0) if v == "ppt" else a[idx].mean(0))
    vap = mon.get("vap")
    for ms in SEASONS:
        if vap is None:
            out.append(np.full_like(out[0], np.nan))
        else:
            out.append(dewpoint(np.asarray(vap, "float64")[[m - 1 for m in ms]].mean(0)))
    for n in _ACTIVE:                                               # optional extras: seasonal sum (pet) or mean (srad)
        a = mon.get(n)
        for ms in SEASONS:
            if a is None:
                out.append(np.full_like(out[0], np.nan))
            else:
                b = np.asarray(a, "float64")[[m - 1 for m in ms]]
                out.append(b.sum(0) if EXTRAS[n]["sum"] else b.mean(0))
    return np.stack(out)


def seasonal_years(series: dict, row_years, years) -> np.ndarray:
    """Per-year seasonal vectors from monthly series {var: (nrows, 12)} whose rows are the years in row_years.
    DJF of year y uses December of y-1. Missing years give NaN. Returns (len(years), 16 + 4 * extras)."""
    pos = {int(y): i for i, y in enumerate(row_years)}
    out = np.full((len(years), nvx()), np.nan)
    for n, y in enumerate(years):
        if y not in pos or (y - 1) not in pos:
            continue
        mon = {}
        for v, a in series.items():
            if a is None:
                continue
            m12 = np.array(a[pos[y]], "float64").copy()
            m12[11] = a[pos[y - 1], 11]              # December of the previous year stands in for DJF
            mon[v] = m12
        out[n] = seasonalize(mon)
    return out


def transform(X):
    X = np.array(X, dtype="float64", copy=True)
    X[..., PPT] = np.log(np.maximum(X[..., PPT], 0) + 1.0)
    for j, n in enumerate(_ACTIVE):
        if X.shape[-1] >= NV + 4 * (j + 1):
            c = slice(NV + 4 * j, NV + 4 * j + 4)
            X[..., c] = np.log(np.maximum(X[..., c], 0) + 1.0) if EXTRAS[n]["log"] else X[..., c] / EXTRAS[n]["div"]
    return X


def enc(X) -> np.ndarray:
    """Raw vectors -> int16 for the page: temperatures and dewpoints x100, precipitation log(mm+1) x1000."""
    X_in = X
    X = np.asarray(X, "float64").copy()
    X[..., :8] *= 100
    X[..., 12:NV] *= 100
    X[..., PPT] = np.log(np.maximum(X[..., PPT], 0) + 1) * 1000
    if X.shape[-1] > NV:                                            # extras: transformed value x ENC_SCALE
        X[..., NV:] = transform(np.asarray(X_in, "float64"))[..., NV:] * ENC_SCALE
    return np.round(np.nan_to_num(X, nan=0.0)).astype("int16")


# --------------------------------------------------------------------------- sigma dissimilarity
def chi_to_sigma(D, k: int):
    """Percentile of Mahalanobis distance D in a chi(k) distribution, re-expressed as the 1-D (half-normal) z-score
    with the same percentile (Mahony et al. 2017). Log space, so large distances do not saturate."""
    D = np.atleast_1d(np.asarray(D, "float64"))
    sf = special.chdtrc(k, D ** 2)
    with np.errstate(divide="ignore"):
        lsf = np.log(sf)
    bad = ~np.isfinite(lsf)
    if bad.any():
        x = D[bad] ** 2
        lsf[bad] = (k / 2 - 1) * np.log(x / 2) - x / 2 - special.gammaln(k / 2)
    return -special.ndtri_exp(lsf - np.log(2.0))


def d_at_sigma(s, k):
    return np.sqrt(special.chdtri(k, special.erfc(s / np.sqrt(2))))


def detrend(X):
    t = np.arange(len(X)) - (len(X) - 1) / 2
    return X - np.outer(t, (t @ (X - X.mean(0))) / (t @ t))


class ShrinkSigmaModel:
    """Ledoit-Wolf shrinkage of the detrended year-to-year correlation matrix toward the identity; all components."""
    def __init__(self, icv):
        X = detrend(np.asarray(icv, "float64"))
        n, p = X.shape
        self.sd = X.std(0, ddof=1)
        Z = (X - X.mean(0)) / self.sd
        C = Z.T @ Z / n
        d2 = ((C - np.eye(p)) ** 2).sum()
        b2 = sum(((np.outer(z, z) - C) ** 2).sum() for z in Z) / n ** 2
        self.alpha = float(min(1.0, b2 / d2)) if d2 > 0 else 1.0
        Cs = (1 - self.alpha) * C * n / (n - 1) + self.alpha * np.eye(p)
        lam, V = np.linalg.eigh(Cs)
        o = np.argsort(lam)[::-1]
        self.V, self.pc_sd, self.k = V[:, o], np.sqrt(lam[o]), p

    def project(self, X):
        return (np.atleast_2d(X) / self.sd) @ self.V / self.pc_sd

    def M(self):
        return (self.V / self.sd[:, None]) / self.pc_sd[None, :]


class TruncSigmaModel:
    """Second method: principal components of the detrended series, dropping those under min_var_frac of variance."""
    def __init__(self, icv, min_var_frac):
        X = detrend(np.asarray(icv, "float64"))
        self.sd = X.std(0, ddof=1)
        Z = (X - X.mean(0)) / self.sd
        _, S, Vt = np.linalg.svd(Z, full_matrices=False)
        var = S ** 2 / (len(Z) - 1)
        frac = var / var.sum()
        self.k = int((frac > min_var_frac).sum())
        self.V = Vt[: self.k].T
        self.pc_sd = np.sqrt(var[: self.k])

    def project(self, X):
        return (np.atleast_2d(X) / self.sd) @ self.V / self.pc_sd

    def M(self, p):
        m = (self.V / self.sd[:, None]) / self.pc_sd[None, :]
        return np.pad(m, ((0, 0), (0, p - self.k)))


def floor_icv(L, floor, seed=20260924):
    """Lift near-constant columns (a season with no rain in any year) to a minimum SD with a fixed, seeded,
    zero-mean, detrended series uncorrelated with the rest, so the metric stays defined. Returns (L, n_floored)."""
    n, p = L.shape
    rng = np.random.default_rng(seed)
    J = detrend(rng.standard_normal((n, p)))
    J -= J.mean(0)
    J /= J.std(0, ddof=1)
    sd = detrend(L).std(0, ddof=1)
    low = sd < floor
    if low.any():
        L = L.copy()
        L[:, low] += J[:, low] * np.sqrt(np.maximum(floor ** 2 - sd[low] ** 2, 0))
    return L, int(low.sum())
