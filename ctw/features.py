"""Descriptive features computed from monthly normals, identically for present, projected and matched climates.

Köppen-Geiger class: the criteria of Beck et al. (2018), which follow Peel et al. (2007) with a 0 °C boundary
between temperate (C) and cold (D) climates. Summer is the warmer half-year (Apr-Sep or Oct-Mar).
Hardiness zone: estimated mean annual extreme minimum temperature, calibrated against the official 1991-2020
USDA/PRISM grid; not the official USDA map. Growing season: estimated frost-free period, calibrated against
ClimateNA. Snowfall is deliberately not estimated: monthly normals cannot separate rain from snow reliably
(even ClimateNA puts Denver's snow near 3% of its precipitation, far below what falls)."""
from __future__ import annotations
import json
import numpy as np
from . import common as C

KG = ["Af", "Am", "Aw", "BWh", "BWk", "BSh", "BSk", "Csa", "Csb", "Csc", "Cwa", "Cwb", "Cwc", "Cfa", "Cfb", "Cfc",
      "Dsa", "Dsb", "Dsc", "Dsd", "Dwa", "Dwb", "Dwc", "Dwd", "Dfa", "Dfb", "Dfc", "Dfd", "ET", "EF"]
KG_NAME = {
    "Af": "Tropical rainforest", "Am": "Tropical monsoon", "Aw": "Tropical savanna",
    "BWh": "Hot desert", "BWk": "Cold desert", "BSh": "Hot semi-arid", "BSk": "Cold semi-arid",
    "Csa": "Hot-summer Mediterranean", "Csb": "Warm-summer Mediterranean", "Csc": "Cool-summer Mediterranean",
    "Cwa": "Humid subtropical, dry winter", "Cwb": "Subtropical highland, dry winter", "Cwc": "Cold subtropical highland",
    "Cfa": "Humid subtropical", "Cfb": "Oceanic", "Cfc": "Subpolar oceanic",
    "Dsa": "Hot-summer continental, dry summer", "Dsb": "Warm-summer continental, dry summer",
    "Dsc": "Subarctic, dry summer", "Dsd": "Very cold subarctic, dry summer",
    "Dwa": "Hot-summer continental, dry winter", "Dwb": "Warm-summer continental, dry winter",
    "Dwc": "Subarctic, dry winter", "Dwd": "Very cold subarctic, dry winter",
    "Dfa": "Hot-summer humid continental", "Dfb": "Warm-summer humid continental", "Dfc": "Subarctic", "Dfd": "Very cold subarctic",
    "ET": "Tundra", "EF": "Ice cap"}
_IDX = {c: i for i, c in enumerate(KG)}
SUMMER_N = [3, 4, 5, 6, 7, 8]           # Apr-Sep
SUMMER_S = [9, 10, 11, 0, 1, 2]         # Oct-Mar


def koppen(tmax, tmin, ppt):
    """(12, N) monthly arrays -> (N,) uint8 index into KG (255 where input is missing)."""
    T = (np.asarray(tmax, "float64") + np.asarray(tmin, "float64")) / 2
    P = np.maximum(np.asarray(ppt, "float64"), 0)
    N = T.shape[1]
    out = np.full(N, 255, "uint8")
    ok = np.isfinite(T).all(0) & np.isfinite(P).all(0)
    MAT, MAP = T.mean(0), P.sum(0)
    Tc, Th, T10 = T.min(0), T.max(0), (T > 10).sum(0)
    north = T[SUMMER_N].mean(0) >= T[SUMMER_S].mean(0)
    S = np.where(north, np.array(SUMMER_N)[:, None], np.array(SUMMER_S)[:, None])
    Wn = np.where(north, np.array(SUMMER_S)[:, None], np.array(SUMMER_N)[:, None])
    cols = np.arange(N)[None]
    Ps, Pw = P[S, cols], P[Wn, cols]
    Psdry, Pswet, Pwdry, Pwwet = Ps.min(0), Ps.max(0), Pw.min(0), Pw.max(0)
    Pdry = P.min(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        pthr = np.where(Pw.sum(0) >= 0.7 * MAP, 2 * MAT, np.where(Ps.sum(0) >= 0.7 * MAP, 2 * MAT + 28, 2 * MAT + 14))
    code = np.empty(N, dtype=object)
    for n in np.where(ok)[0]:
        if Th[n] < 10:
            c = "ET" if Th[n] > 0 else "EF"
        elif MAP[n] < 10 * pthr[n]:
            c = ("BW" if MAP[n] < 5 * pthr[n] else "BS") + ("h" if MAT[n] >= 18 else "k")
        elif Tc[n] >= 18:
            c = "Af" if Pdry[n] >= 60 else ("Am" if Pdry[n] >= 100 - MAP[n] / 25 else "Aw")
        else:
            g = "C" if Tc[n] > 0 else "D"
            if Psdry[n] < 40 and Psdry[n] < Pwwet[n] / 3:
                s2 = "s"
            elif Pwdry[n] < Pswet[n] / 10:
                s2 = "w"
            else:
                s2 = "f"
            if Th[n] >= 22:
                s3 = "a"
            elif T10[n] >= 4:
                s3 = "b"
            elif g == "D" and Tc[n] < -38:
                s3 = "d"
            else:
                s3 = "c"
            c = g + s2 + s3
        code[n] = c
        out[n] = _IDX[c]
    return out


def calibration() -> dict:
    return json.load(open(C.DATA / "feature_calibration.json"))


def extreme_min(tmax, tmin, ppt, cal=None):
    """Estimated mean annual extreme minimum temperature (°C), the quantity behind USDA hardiness zones.
    Linear in the coldest month's mean low, the annual range and log annual precipitation, fitted to the
    PRISM/USDA 1991-2020 grid over the contiguous US (see calibrate())."""
    c = np.asarray((cal or calibration())["hardiness"]["coef"])
    tx, tn, p = (np.asarray(a, "float64") for a in (tmax, tmin, ppt))
    return c[0] + c[1] * tn.min(0) + c[2] * (tx.max(0) - tn.min(0)) + c[3] * np.log1p(np.maximum(p, 0).sum(0))


def zone_index(emt_c):
    """USDA-style half zone as an integer: 2*zone + (0 for 'a', 1 for 'b'); zone 1a starts at -60 °F."""
    f = np.asarray(emt_c, "float64") * 9 / 5 + 32
    h = np.floor((f + 60) / 5).astype(int)          # half-zones of 5 °F above -60 °F
    return np.clip(h + 2, 2, 27)                    # 2 -> 1a ... 27 -> 13b


def frost_free_period(tmin, cal=None):
    """Estimated days between the last spring and first autumn frost, from monthly mean lows, fitted to
    ClimateNA's frost-free period (FFP) over North America."""
    from scipy.stats import norm
    c0, w = (cal or calibration())["ffp"]["coef"]
    return (C.DPM[:, None] * norm.cdf((np.asarray(tmin, "float64").reshape(12, -1) - c0) / w)).sum(0)


def all_features(tmax, tmin, ppt, cal=None):
    """(12, N) monthly -> dict of (N,) arrays: kg (uint8 index into KG), zone (uint8 half-zone), ffp (uint16 days)."""
    cal = cal or calibration()
    tmax, tmin, ppt = (np.asarray(a, "float64").reshape(12, -1) for a in (tmax, tmin, ppt))
    bad = ~(np.isfinite(tmax).all(0) & np.isfinite(tmin).all(0) & np.isfinite(ppt).all(0))
    z = zone_index(np.nan_to_num(extreme_min(tmax, tmin, ppt, cal))).astype("uint8")
    f = np.round(np.nan_to_num(frost_free_period(tmin, cal))).clip(0, 366).astype("uint16")
    z[bad] = 0; f[bad] = 0
    return {"kg": koppen(tmax, tmin, ppt), "zone": z, "ffp": f}


def calibrate(cfg=None):
    """Fit the hardiness and frost-free-period estimators. Needs work/adaptwest.npz, work/adaptwest_bioclim.npz
    and the PRISM/USDA 2023 hardiness grid; writes data/feature_calibration.json (committed)."""
    import zipfile
    from pyproj import Transformer
    from scipy.optimize import least_squares
    from scipy.stats import norm
    cfg = cfg or C.config()
    g = cfg["grids"]
    aw, bc = C.load(C.work("adaptwest.npz")), C.load(C.work("adaptwest_bioclim.npz"))
    zp = C.download("https://prism.oregonstate.edu/phzm/data/2023/phzm_us_grid_2023.zip", C.work("downloads", "phzm_us_grid_2023.zip"))
    H = np.frombuffer(zipfile.ZipFile(zp).read("phzm_us_grid_2023.bil"), "<f4").reshape(3105, 7025).astype(float)
    H[H < -9000] = np.nan
    xc = g["na_x0"] + (np.arange(g["na_nx"]) + .5) * g["na_cell_m"]
    yc = g["na_y0"] - (np.arange(g["na_ny"]) + .5) * g["na_cell_m"]
    X, Y = np.meshgrid(xc, yc)
    lon, lat = Transformer.from_crs(g["na_crs"], "EPSG:4326", always_xy=True).transform(X, Y)
    i0 = np.round((49.933333333333 - lat) / 0.008333333333).astype(int)
    j0 = np.round((lon + 125.016666666666) / 0.008333333333).astype(int)
    ok = (aw["landfrac"] >= g["na_landfrac_min"]) & np.isfinite(aw["tmax"]).all(0)
    r, c = np.nonzero(ok)
    E = np.full(len(r), np.nan)
    for n, (a, b) in enumerate(zip(r, c)):
        if 9 <= i0[a, b] < 3105 - 9 and 9 <= j0[a, b] < 7025 - 9:
            w = H[i0[a, b] - 9:i0[a, b] + 10, j0[a, b] - 9:j0[a, b] + 10]
            if np.isfinite(w).mean() > 0.5:
                E[n] = (np.nanmean(w) - 32) * 5 / 9
    tx, tn, pp = (aw[v][:, r, c].astype(float) for v in ("tmax", "tmin", "ppt"))
    Xh = np.c_[np.ones(len(r)), tn.min(0), tx.max(0) - tn.min(0), np.log1p(pp.sum(0))]
    m = np.isfinite(E)
    ch = np.linalg.lstsq(Xh[m], E[m], rcond=None)[0]
    eh = Xh[m] @ ch - E[m]
    ffp = bc["ffp"][r, c].astype(float)
    sub = np.random.default_rng(1).choice(len(r), min(30000, len(r)), replace=False)
    fp = lambda p, T: (C.DPM[:, None] * norm.cdf((T - p[0]) / p[1])).sum(0)
    cf = least_squares(lambda p: fp(p, tn[:, sub]) - ffp[sub], [3, 3], bounds=([-10, .3], [15, 15])).x
    ef = fp(cf, tn) - ffp
    zi = zone_index(Xh[m] @ ch) == zone_index(E[m])
    out = {
        "hardiness": {"coef": ch.round(5).tolist(), "n": int(m.sum()), "r2": round(float(1 - eh.var() / E[m].var()), 3),
                      "median_abs_err_c": round(float(np.median(np.abs(eh))), 2), "same_half_zone": round(float(zi.mean()), 3),
                      "within_one_half_zone": round(float((np.abs(zone_index(Xh[m] @ ch) - zone_index(E[m])) <= 1).mean()), 3),
                      "reference": "PRISM Climate Group / USDA-ARS 2023 Plant Hardiness Zone Map grid, 1991-2020 mean annual extreme minimum"},
        "ffp": {"coef": cf.round(4).tolist(), "n": int(len(r)), "r2": round(float(1 - ef.var() / ffp.var()), 3),
                "median_abs_err_days": round(float(np.median(np.abs(ef))), 1), "reference": "ClimateNA v7.30 frost-free period (AdaptWest 2022)"},
    }
    json.dump(out, open(C.DATA / "feature_calibration.json", "w"), indent=1)
    C.log.info("feature calibration: %s", out)
