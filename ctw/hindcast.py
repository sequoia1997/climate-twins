"""Hindcast test of the analog method with ERA5 (weak by construction: the observed change is small).

At each sampled place we stand in 1961-1990 and ask for the place's climate in 1991-2020:
  P    projected climate = the place's 1961-90 climate + the change of its 5° neighbourhood (the change a coarse
       model would give), with the production rules (temperature added, precipitation and humidity ratios clipped)
  V1   what actually happened at the place, 1991-2020
Pool: 1961-90 climates on a 0.5° land grid (the stand-in for "present-day climates elsewhere"). Distances use the
production sigma metric with the place's own 1961-90 year-to-year variability (Ledoit-Wolf shrinkage, 14 measures).
  predicted analog  = pool cell nearest to P
  oracle analog     = pool cell nearest to V1 (best any search could do)
Questions: (1) is the projected climate closer to the truth than "nothing changes"? (2) is the predicted analog a
good analog of what happened (sigma of V1 to it), and how close to the oracle? (3) does it beat the naive
alternative, the cell on the same meridian, equatorward of the place, whose annual mean temperature is closest?
Writes data/hindcast.json (small, committed; site.py puts it in methods.html)."""
from __future__ import annotations
import json, time
import numpy as np
from . import common as C
from . import era5 as E

MON = ("tmax", "tmin", "ppt", "vap")


def _sigma(sm, midx, A, B):
    """Sigma distance from each row of A to each row of B (A: (n,16) raw, B: (m,16) raw) under model sm."""
    pa = sm.project(C.transform(A)[:, midx]); pb = sm.project(C.transform(B)[:, midx])
    D = np.sqrt(np.maximum((pa ** 2).sum(1)[:, None] - 2 * pa @ pb.T + (pb ** 2).sum(1)[None], 0))
    return C.chi_to_sigma(D.ravel(), sm.k).reshape(D.shape)


def _box_mean(grid, lat0, lon0, w, half=2.5):
    """Land-weighted mean of a (12, 360, 720) field within +-half degrees of (lat0, lon0)."""
    la = 90 - (np.arange(360) + .5) * .5
    lo = -180 + (np.arange(720) + .5) * .5
    i = np.where(np.abs(la - lat0) <= half)[0]
    dl = (lo - lon0 + 180) % 360 - 180
    j = np.where(np.abs(dl) <= half / max(np.cos(np.radians(lat0)), 0.2))[0]
    ww = w[np.ix_(i, j)]
    if ww.sum() < 1e-6:
        ww = np.ones_like(ww)
    return (grid[:, i][:, :, j] * ww).sum((1, 2)) / ww.sum()


def run(cfg=None):
    cfg = cfg or C.config()
    t0 = time.time()
    T = C.targets()
    d = E.load_series(T)
    assert d is not None, "run the era5 step first (four variables)"
    hc, mc = cfg["hindcast"], cfg["matching"]
    (a0, a1), (b0, b1) = hc["windows"]
    midx = C.match_idx(cfg)
    years = d["tmax"]["years"]; yl = set(years.tolist())
    ys0 = [y for y in range(a0, a1 + 1) if y in yl and y - 1 in yl]
    ys1 = [y for y in range(b0, b1 + 1) if y in yl and y - 1 in yl]
    NT = len(T)
    yi = {int(y): i for i, y in enumerate(years)}

    def monthly(k, ys):
        return {v: d[v]["series"][k][[yi[y] for y in ys]].astype("float64").mean(0) for v in MON}

    # ---- pool: 1961-90 climates on the 0.5 degree land grid
    lsm = d["tmax"]["lsm05"].astype("float64")
    la = 90 - (np.arange(360) + .5) * .5
    LA, LO = np.meshgrid(la, -180 + (np.arange(720) + .5) * .5, indexing="ij")
    # ERA5 longitudes run 0..360: roll to -180..180
    def roll(a):
        return np.roll(a, 360, axis=-1)
    lsm = roll(lsm)
    w0 = {v: roll(d[v]["w0"]).astype("float64") for v in MON}
    w1 = {v: roll(d[v]["w1"]).astype("float64") for v in MON}
    m12 = {v: w0[v].reshape(12, -1) for v in MON}
    S0 = C.seasonalize(m12).T                                                   # (cells, 16)
    valid = (lsm.ravel() >= 0.25) & np.isfinite(S0).all(1) & (LA.ravel() > cfg["grids"]["world_lat_min"])
    cells = np.nonzero(valid)[0]
    pool = S0[cells]; plat, plon = LA.ravel()[cells], LO.ravel()[cells]
    C.log.info("hindcast pool: %d land cells (%.0fs)", len(cells), time.time() - t0)

    # ---- places: 1961-90 and 1991-2020 climates from ERA5
    ok, V0, V1 = [], np.full((NT, C.NV), np.nan), np.full((NT, C.NV), np.nan)
    M0, M1 = [None] * NT, [None] * NT
    for k in range(NT):
        if len(ys0) < 20 or len(ys1) < 20:
            continue
        M0[k], M1[k] = monthly(k, ys0), monthly(k, ys1)
        V0[k], V1[k] = C.seasonalize({v: M0[k][v] for v in MON}), C.seasonalize({v: M1[k][v] for v in MON})
    good = np.where(np.isfinite(V0).all(1) & np.isfinite(V1).all(1) & (np.abs(T.lat.values) < 66))[0]
    # diverse sample: half farthest-point in standardised climate space, half random
    n = min(hc["n_places"], len(good)); rng = np.random.default_rng(hc["seed"])
    Z = C.transform(V0[good])[:, midx]; Z = (Z - Z.mean(0)) / Z.std(0)
    sel = [int(rng.integers(len(good)))]
    dmin = np.linalg.norm(Z - Z[sel[0]], axis=1)
    while len(sel) < n // 2:
        j = int(np.argmax(dmin)); sel.append(j); dmin = np.minimum(dmin, np.linalg.norm(Z - Z[j], axis=1))
    rest = np.setdiff1d(np.arange(len(good)), sel)
    sel += rng.choice(rest, n - len(sel), replace=False).tolist()
    sample = good[np.array(sel)]

    lo_r, hi_r = mc["ppt_ratio"]; vlo, vhi = mc["vap_ratio"]
    rows = []
    for k in sample:
        sv = C.seasonal_years({v: d[v]["series"][k] for v in MON}, years, list(range(a0, a1 + 1)))
        sv = sv[np.isfinite(sv[:, midx]).all(1)]
        if len(sv) < 20:
            continue
        L = C.transform(sv); Lm, _ = C.floor_icv(L[:, midx], mc["floor"])
        sm = C.ShrinkSigmaModel(Lm)
        lat, lon = float(T.lat[k]), float(T.lon[k])
        dm = {v: _box_mean(w1[v] - w0[v], lat, lon, lsm) for v in ("tmax", "tmin")}
        rp = _box_mean(w1["ppt"], lat, lon, lsm) / np.maximum(_box_mean(w0["ppt"], lat, lon, lsm), 1e-6)
        rv = _box_mean(w1["vap"], lat, lon, lsm) / np.maximum(_box_mean(w0["vap"], lat, lon, lsm), 1e-6)
        tx = M0[k]["tmax"] + dm["tmax"]; tn = np.minimum(M0[k]["tmin"] + dm["tmin"], tx - 0.1)
        P = C.seasonalize({"tmax": tx, "tmin": tn, "ppt": M0[k]["ppt"] * np.clip(rp, lo_r, hi_r),
                           "vap": M0[k]["vap"] * np.clip(rv, vlo, vhi)})
        v0, v1 = V0[k][None], V1[k][None]
        sP = _sigma(sm, midx, P[None], pool)[0]            # predicted-climate to every pool cell
        sT = _sigma(sm, midx, v1, pool)[0]                 # truth to every pool cell
        ip, io = int(np.argmin(sP)), int(np.argmin(sT))
        # naive: same meridian (within 1 deg), equatorward of the place (or level), closest annual mean temperature
        ann = lambda X: X[..., 0:8].mean(-1)
        cand = np.where((np.abs((plon - lon + 180) % 360 - 180) <= 1.0) & (np.abs(plat) <= abs(lat) + 0.5))[0]
        if len(cand) == 0:
            cand = np.array([int(np.argmin(C.haversine_km(plat, plon, lat, lon)))])
        inaive = int(cand[np.argmin(np.abs(ann(pool[cand]) - ann(V1[k])))])
        iown = int(np.argmin(C.haversine_km(plat, plon, lat, lon)))
        rows.append(dict(
            place=str(T.label[k]), lat=round(lat, 2), lon=round(lon, 2),
            dT=round(float(ann(V1[k]) - ann(V0[k])), 2),
            persist=float(_sigma(sm, midx, v0, v1)[0, 0]),
            proj_err=float(_sigma(sm, midx, P[None], v1)[0, 0]),
            at_pred=float(sT[ip]), oracle=float(sT[io]), naive=float(sT[inaive]), own=float(sT[iown]),
            km_pred_oracle=float(C.haversine_km(plat[ip], plon[ip], plat[io], plon[io])),
            km_move=float(C.haversine_km(plat[ip], plon[ip], lat, lon)),
            equatorward=bool(abs(plat[ip]) < abs(lat) - 0.25), pred_sigma=float(sP[ip])))
    q = lambda x, p: float(np.percentile(x, p))
    col = lambda key, r=rows: np.array([x[key] for x in r])
    det = [r for r in rows if r["persist"] >= 1.0]
    def summ(r):
        if not r:
            return {}
        return dict(n=len(r),
                    persistence_sigma_median=q(col("persist", r), 50), projection_sigma_median=q(col("proj_err", r), 50),
                    share_projection_beats_persistence=float(np.mean(col("proj_err", r) < col("persist", r))),
                    at_predicted_analog=dict(p25=q(col("at_pred", r), 25), median=q(col("at_pred", r), 50), p75=q(col("at_pred", r), 75), p90=q(col("at_pred", r), 90),
                                             share_under_1=float(np.mean(col("at_pred", r) < 1)), share_under_2=float(np.mean(col("at_pred", r) < 2))),
                    oracle_median=q(col("oracle", r), 50), naive_lat_shift_median=q(col("naive", r), 50), own_cell_median=q(col("own", r), 50),
                    share_beats_naive=float(np.mean(col("at_pred", r) < col("naive", r))),
                    share_beats_own_cell=float(np.mean(col("at_pred", r) < col("own", r))),
                    skill_vs_naive=float(1 - np.median(col("at_pred", r)) / np.median(col("naive", r))),
                    skill_vs_own_cell=float(1 - np.median(col("at_pred", r)) / np.median(col("own", r))),
                    km_predicted_to_oracle_median=q(col("km_pred_oracle", r), 50),
                    share_predicted_within_500km_of_oracle=float(np.mean(col("km_pred_oracle", r) < 500)),
                    median_move_km=q(col("km_move", r), 50), share_equatorward=float(np.mean([x["equatorward"] for x in r])),
                    median_warming_C=q(col("dT", r), 50))
    out = dict(windows=hc["windows"], pool_cells=int(len(cells)), n_candidates=int(len(good)), all=summ(rows), detectable_change=summ(det),
               places=[{k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in r.items()} for r in rows],
               source="ERA5 daily (ARCO-ERA5 aggregation), 0.25 degree, place values bilinear, pool 0.5 degree block means")
    (C.DATA / "hindcast.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    C.log.info("hindcast: %d places; all=%s (%.0fs)", len(rows), json.dumps(out["all"])[:600], time.time() - t0)
