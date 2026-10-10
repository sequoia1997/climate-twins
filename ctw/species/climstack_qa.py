"""QA of the global predictor stack (workstream W1), run in Actions after the tiles are on the release.

    python -m ctw.species.climstack_qa --out DIR [--upload] [--parts places,hindcast,future,deltas,box]

parts:
  places    seasonal tmax, tmin, precipitation and annual means of the stack vs the site's present climate at its 2,386 places
            (site/data/p/*.dat shards, `base` vector: 4 seasonal tmax, 4 seasonal tmin, 4 log seasonal precipitation, ...)
  hindcast  area-weighted land change between the windows (baseline vs 1966-1985 and 2005-2024) per latitude band
  future    area-weighted land change baseline -> ensemble-median futures per latitude band
  deltas    our coarse deltas (interpolated to the places) vs data/nexdeltas.npz (the repo's own NEX-GDDP deltas at the places)
  box       the Spike B test box (lat 40-60, lon 0-20): stack vs a direct TerraClimate read computed with the spike's method
Writes qa_report.json (and prints a summary).
"""
from __future__ import annotations
import argparse, gzip, json, os, time
import numpy as np

from . import climategrid as G
from . import climstack as S
from . import climstack_run as R

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SEASONS = ((11, 0, 1), (2, 3, 4), (5, 6, 7), (8, 9, 10))
BANDS = ((-90, -45), (-45, -23.5), (-23.5, 0), (0, 23.5), (23.5, 45), (45, 66.5), (66.5, 90))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def stats(mine, ref):
    ok = np.isfinite(mine) & np.isfinite(ref)
    if ok.sum() < 3:
        return {"n": int(ok.sum())}
    d = mine[ok] - ref[ok]
    return {"n": int(ok.sum()), "bias": float(d.mean()), "mae": float(np.abs(d).mean()), "rmse": float(np.sqrt((d ** 2).mean())),
            "r": float(np.corrcoef(mine[ok], ref[ok])[0, 1]), "ref_mean": float(ref[ok].mean())}


# --------------------------------------------------------------------------- the site's places
def site_places(site=None):
    """dict(label, lat, lon, g, icv, base (N, 16) float: seasonal tx (4), tn (4), precipitation mm per season (4), dewpoint (4))."""
    site = site or os.path.join(ROOT, "site", "data")
    idx = json.load(open(os.path.join(site, "index.json")))
    rows = idx["rows"]
    col = {c: i for i, c in enumerate(idx["cols"])}
    n = len(rows)
    base = np.full((n, 16), np.nan)
    for f in sorted(os.listdir(os.path.join(site, "p"))):
        raw = gzip.decompress(open(os.path.join(site, "p", f), "rb").read())
        hl = int.from_bytes(raw[4:8], "little")
        h = json.loads(raw[8:8 + hl]); body = raw[8 + hl:]
        off, ln, _ = h["base"]["$b"]
        a = np.frombuffer(body[off:off + ln], dtype="<i2").reshape(len(h["ids"]), -1).astype("float64")
        v = np.empty_like(a[:, :16])
        v[:, :8] = a[:, :8] / 100; v[:, 8:12] = np.expm1(a[:, 8:12] / 1000); v[:, 12:16] = a[:, 12:16] / 100
        base[h["ids"]] = v[:, :16]
    return {"label": [r[col["n"]] for r in rows], "lat": np.array([r[col["lat"]] for r in rows]), "lon": np.array([r[col["lon"]] for r in rows]),
            "g": np.array([r[col["g"]] for r in rows]), "icv": np.array([r[col["icv"]] for r in rows]), "base": base}


def stack_at_places(root, lat, lon, fetch=None, radius=3):
    """Seasonal tx, tn, ppt (N, 12) and bio predictors (N, 10) of the stack at points (nearest land cell within `radius` cells of the
    cell containing the point). fetch(name) makes a missing file available in `root`."""
    i, j = S.point_cells(lat, lon)
    n = len(lat)
    seas = np.full((n, 12), np.nan); pred = np.full((n, 10), np.nan); moved = np.zeros(n, int)
    for t in sorted(set(zip((i // S.TH).tolist(), (j // S.TW).tolist()))):
        tile = f"r{t[0]}c{t[1]}"
        sel = np.where((i // S.TH == t[0]) & (j // S.TW == t[1]))[0]
        for nm in (f"basem_{tile}.npz", f"pred_base_1991-2020_{tile}.npz"):
            if not os.path.exists(os.path.join(root, nm)) and fetch:
                fetch(nm)
        land, _, mon = S.load_basem(os.path.join(root, f"basem_{tile}.npz"))
        p = S.load_pred(os.path.join(root, f"pred_base_1991-2020_{tile}.npz"))
        vec = np.cumsum(land.ravel()) - 1
        for k in sel:
            ii, jj = i[k] - t[0] * S.TH, j[k] - t[1] * S.TW
            best = None
            for r in range(radius + 1):
                cand = [(ii + a, jj + b) for a in range(-r, r + 1) for b in range(-r, r + 1) if max(abs(a), abs(b)) == r]
                cand = [(a, b) for a, b in cand if 0 <= a < S.TH and 0 <= b < S.TW and land[a, b]]
                if cand:
                    best = min(cand, key=lambda c: (c[0] - ii) ** 2 + (c[1] - jj) ** 2); moved[k] = r; break
            if best is None:
                continue
            q = vec[best[0] * S.TW + best[1]]
            for v, o in (("tmax", 0), ("tmin", 4)):
                seas[k, o:o + 4] = [mon[v][list(m), q].mean() for m in SEASONS]
            seas[k, 8:12] = [mon["ppt"][list(m), q].sum() for m in SEASONS]
            pred[k] = p["data"][:, q]
        if fetch:
            for nm in (f"basem_{tile}.npz", f"pred_base_1991-2020_{tile}.npz"):
                os.remove(os.path.join(root, nm))
    return seas, pred, moved


def qa_places(root, fetch=None):
    pl = site_places()
    seas, pred, moved = stack_at_places(root, pl["lat"], pl["lon"], fetch)
    b = pl["base"]
    out = {"n_places": int(len(pl["lat"])), "n_on_land_cell": int(np.isfinite(seas[:, 0]).sum()), "n_moved_to_neighbour_cell": int((moved > 0).sum())}
    names = [f"tmax_{s}" for s in ("DJF", "MAM", "JJA", "SON")] + [f"tmin_{s}" for s in ("DJF", "MAM", "JJA", "SON")] + [f"ppt_{s}" for s in ("DJF", "MAM", "JJA", "SON")]
    tmean_site = (b[:, :4] + b[:, 4:8]).mean(1) / 2; tmean_me = (seas[:, :4] + seas[:, 4:8]).mean(1) / 2
    ppt_site, ppt_me = b[:, 8:12].sum(1), seas[:, 8:12].sum(1)
    groups = {"all": np.ones(len(pl["lat"]), bool), "north_america(g=0)": pl["g"] == 0, "world(g=1)": pl["g"] == 1}
    for s in sorted(set(pl["icv"])):
        groups[f"source={s}"] = pl["icv"] == s
    res = {}
    for gname, m in groups.items():
        r = {"annual_tmean": stats(np.where(m, tmean_me, np.nan), tmean_site), "annual_ppt_mm": stats(np.where(m, ppt_me, np.nan), ppt_site)}
        r["annual_ppt_ratio_median"] = float(np.nanmedian((ppt_me / np.maximum(ppt_site, 1))[m]))
        for k, nm in enumerate(names):
            r[nm] = stats(np.where(m, seas[:, k], np.nan), b[:, k])
        res[gname] = r
    out["vs_site_present_climate"] = res
    out["bio_means_at_places"] = {nm: float(np.nanmean(pred[:, k])) for k, nm in enumerate(S.NAMES)}
    out["bio12_vs_site_sum"] = stats(pred[:, S.NAMES.index("bio12")], ppt_site)
    out["bio1_vs_site_seasonal_mean"] = stats(pred[:, S.NAMES.index("bio1")], tmean_site)
    return out


# --------------------------------------------------------------------------- area-weighted changes
def tile_weights(tile, land):
    rows, _ = S.tile_window(tile)
    lat = G.cell_lat(np.arange(rows.start, rows.stop))
    w = np.broadcast_to(G.cell_area_km2(lat)[:, None], land.shape)
    return w[land], np.broadcast_to(lat[:, None], land.shape)[land]


def change_table(root, a, b, fetch=None, rel=("bio12", "gdd")):
    """Area-weighted land mean of (product b - product a) per predictor and latitude band over all tiles."""
    acc = {}
    for t in S.ALL_TILES:
        names = [f"pred_{a}_{t}.npz", f"pred_{b}_{t}.npz"]
        for nm in names:
            if not os.path.exists(os.path.join(root, nm)) and fetch:
                fetch(nm)
        pa, pb = S.load_pred(os.path.join(root, names[0])), S.load_pred(os.path.join(root, names[1]))
        if pa["data"].shape[1]:
            w, lat = tile_weights(t, pa["land"])
            for bi, (lo, hi) in enumerate(list(BANDS) + [(-90, 90)]):
                m = (lat >= lo) & (lat < hi) if bi < len(BANDS) else np.ones(len(lat), bool)
                if not m.any():
                    continue
                for k, nm in enumerate(S.NAMES):
                    x, y = pa["data"][k][m], pb["data"][k][m]
                    ok = np.isfinite(x) & np.isfinite(y)
                    key = (bi, nm)
                    s = acc.setdefault(key, [0.0, 0.0, 0.0, 0.0])
                    ww = w[m][ok]
                    s[0] += float((ww * (y[ok] - x[ok])).sum()); s[1] += float(ww.sum()); s[2] += float((ww * x[ok]).sum()); s[3] += float((ww * y[ok]).sum())
        if fetch:
            for nm in names:
                os.remove(os.path.join(root, nm))
    out = {}
    for (bi, nm), s in sorted(acc.items()):
        lab = f"{BANDS[bi][0]}..{BANDS[bi][1]}" if bi < len(BANDS) else "global_land"
        out.setdefault(lab, {})[nm] = {"mean_change": s[0] / s[1], "mean_a": s[2] / s[1], "mean_b": s[3] / s[1],
                                       **({"ratio_of_means": s[3] / s[2]} if nm in rel and s[2] else {})}
    return out


# --------------------------------------------------------------------------- deltas vs the repo's nexdeltas
def qa_deltas(root, fetch=None):
    z = np.load(os.path.join(ROOT, "data", "nexdeltas.npz"), allow_pickle=True)
    models = [str(m) for m in z["models"]]; scen = [str(s) for s in z["scen"]]
    lat, lon = z["lat"].astype(float), z["lon"].astype(float)
    res = {}
    for m in models:
        p = os.path.join(root, f"deltas_{m}.npz")
        if not os.path.exists(p) and fetch:
            try:
                fetch(f"deltas_{m}.npz")
            except Exception as e:  # noqa: BLE001
                res[m] = {"error": str(e)[:100]}; continue
        if not os.path.exists(p):
            continue
        d = S.Deltas.load(p)
        it = S.PointInterp(d.lat, d.lon, lat, lon)
        r = {}
        for s in ("ssp245", "ssp585"):
            for pi, (pk, per) in enumerate(zip(("2050", "2100"), S.PERIODS)):
                mine_tx, mine_tn, mine_rp = (it(x) for x in d.get(s, per))
                j = models.index(m)
                ref_tx, ref_tn, ref_rp = (z[k][j, pi, scen.index(s)].astype("float64").T for k in ("dtx", "dtn", "rp"))
                r[f"{s}_{per}"] = {"tmean_change": stats(((mine_tx + mine_tn) / 2).mean(0), ((ref_tx + ref_tn) / 2).mean(0)),
                                   "ppt_ratio_annual_mean": stats(mine_rp.mean(0), ref_rp.mean(0))}
        res[m] = r
        if fetch:
            os.remove(p)
    return res


# --------------------------------------------------------------------------- Spike B box
def qa_box(root, fetch=None, procs=4):
    """Direct TerraClimate read of the Spike B box for 1991-2020 (the spike's method: climategrid.baseline_predictors) vs the stack."""
    from multiprocessing import get_context
    box = (40, 60, 0, 20)
    rs, cs = G.window(*box)
    t0 = time.time()
    jobs = [(v, y, rs, cs) for v in S.PRED_VARS for y in range(1991, 2021)]
    sums = {v: 0 for v in S.PRED_VARS}; cnt = {v: 0 for v in S.PRED_VARS}
    with get_context("fork").Pool(procs) as pool:
        for v, y, x, dtm in pool.imap_unordered(R._read, jobs):
            sums[v] = sums[v] + np.nan_to_num(x); cnt[v] = cnt[v] + np.isfinite(x)
    m = {v: np.where(cnt[v] > 0, sums[v] / np.maximum(cnt[v], 1), np.nan) for v in S.PRED_VARS}
    log("box read", f"{time.time() - t0:.0f}s")
    P = G.baseline_predictors(m)                                  # the spike's function: also gdd5, fd
    grids, la, lo = S.read_box(root, "base_1991-2020", box) if all(os.path.exists(os.path.join(root, f"pred_base_1991-2020_{t}.npz")) for t in ("r0c2", "r1c2")) else (None, None, None)
    if grids is None and fetch:
        for t in ("r0c2", "r1c2"):
            fetch(f"pred_base_1991-2020_{t}.npz")
        grids, la, lo = S.read_box(root, "base_1991-2020", box)
    land = np.isfinite(m["tmax"]).all(0) & np.isfinite(m["def"]).all(0) & np.isfinite(m["aet"]).all(0) & np.isfinite(m["ppt"]).all(0)
    out = {"land_cells_spike_method": int(land.sum()), "land_cells_stack": int(np.isfinite(grids["bio1"]).sum()), "variables": {}}
    for nm in S.NAMES:
        mine = grids[nm][land]
        ref = P["gdd5" if nm == "gdd" else nm][land]
        out["variables"][nm] = {**stats(mine, ref), "max_abs_diff": float(np.nanmax(np.abs(mine - ref))),
                                "mean": float(np.nanmean(mine)), "p5": float(np.nanpercentile(mine, 5)), "p95": float(np.nanpercentile(mine, 95))}
    return out


# --------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="pilot-out"); ap.add_argument("--upload", action="store_true")
    ap.add_argument("--parts", default="box,places,hindcast,future,deltas")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    fetch = (lambda nm: R.release_download(nm, a.out)) if a.upload else None
    rep = {"built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for part in a.parts.split(","):
        t0 = time.time()
        if part == "box":
            rep["spike_b_box"] = qa_box(a.out, fetch)
        elif part == "places":
            rep["places"] = qa_places(a.out, fetch)
        elif part == "hindcast":
            rep["hindcast"] = {"base_minus_1966-1985": change_table(a.out, "hind_1966-1985", "base_1991-2020", fetch),
                               "2005-2024_minus_1966-1985": change_table(a.out, "hind_1966-1985", "hind_2005-2024", fetch)}
        elif part == "future":
            rep["future"] = {p: change_table(a.out, "base_1991-2020", p, fetch) for p in S.future_products()}
        elif part == "deltas":
            rep["deltas_vs_nexdeltas"] = qa_deltas(a.out, fetch)
        log(part, f"{time.time() - t0:.0f}s")
        with open(os.path.join(a.out, "qa_report.json"), "w") as f:
            json.dump(rep, f, indent=1)
    if a.upload:
        R.release_upload([os.path.join(a.out, "qa_report.json")])
    print(json.dumps({k: (v if k != "deltas_vs_nexdeltas" else "...") for k, v in rep.items()}, indent=1)[:6000])


if __name__ == "__main__":
    main()
