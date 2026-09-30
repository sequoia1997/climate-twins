"""Smoke check for the matched-resolution ERA5 baseline agreement (run by .github/workflows/smoke-era5match.yml after the
terraclimate and era5 steps for a set of places, CTW_SMOKE=1 with CTW_SMOKE_PLACES). Every place uses its TerraClimate
baseline and TerraClimate year-to-year variability (no AdaptWest here). Prints the sigma distribution of three variants:
  point     10 km point baseline vs ERA5 interpolated to the point (the original check)
  cell/pt   10 km point baseline vs the place's ERA5 land cell (cell choice only)
  matched   baseline averaged over the ERA5 cell's footprint vs that cell (the new check, ERA5.matched)
each after the same median-offset removal, and the worst 15 places of the matched check.
    python -m ctw.smoke_era5match"""
from __future__ import annotations
import sys
import numpy as np
from . import common as C
from . import era5 as ERA5

MON = ("tmax", "tmin", "ppt", "vap")


def sigmas(SH, midx, ref, other, G, ok):
    ok = ok & np.isfinite(ref[:, midx]).all(1) & np.isfinite(other[:, midx]).all(1)
    off = ERA5.offsets(ref[ok], other[ok], G[ok])
    s = np.full(len(ref), np.nan); raw = np.full(len(ref), np.nan)
    for k in np.where(ok)[0]:
        s[k] = ERA5.agreement(SH[k], midx, ref[k], other[k], off[G[k]])
        raw[k] = ERA5.agreement(SH[k], midx, ref[k], other[k])
    return s, raw


def dist(name, s, raw, fair, poor):
    f = s[np.isfinite(s)]
    if not len(f):
        print(f"{name:8s} no places")
        return None
    print(f"{name:8s} n={len(f):3d}  median {np.median(f):5.2f}  p90 {np.percentile(f, 90):5.2f}  >{fair:g}: {np.mean(f > fair):5.1%}  "
          f">{poor:g}: {np.mean(f > poor):5.1%}  (no offset removal: median {np.nanmedian(raw):5.2f})")
    return float(np.median(f)), float(np.mean(f > poor))


def main() -> int:
    cfg = C.config()
    C.use_extras([])
    T = C.targets()
    NT = len(T)
    G = T.g.values
    b0, b1 = cfg["baseline"]["years"]
    fair, poor = cfg["era5"]["agree_fair"], cfg["era5"]["agree_poor"]
    midx = C.match_idx(cfg)
    tc = {v: C.load(C.work("terraclimate", f"{v}.npz")) for v in MON}
    e5 = ERA5.load_series(T)
    if e5 is None:
        print("no ERA5 output")
        return 1
    years = tc["tmax"]["years"]
    sel = (years >= b0) & (years <= b1)
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        tcbase = {v: np.nanmean(tc[v]["series"][:, sel], axis=1) for v in MON}
    base = C.seasonalize({v: tcbase[v].T for v in MON}).T
    print(f"{NT} places; TerraClimate years {years.min()}-{years.max()}; ERA5 years {e5['tmax']['years'].min()}-{e5['tmax']['years'].max()}")
    SH = [None] * NT
    ok = np.zeros(NT, bool)
    for k in range(NT):
        sv = C.seasonal_years({v: tc[v]["series"][k] for v in MON}, years, list(range(b0, b1 + 1)))
        sv = sv[np.isfinite(sv[:, midx]).all(1)]
        if len(sv) < 10:
            continue
        Lm, _ = C.floor_icv(C.transform(sv)[:, midx], cfg["matching"]["floor"])
        SH[k] = C.ShrinkSigmaModel(Lm)
        ok[k] = True
    print(f"places with a variability model: {int(ok.sum())} of {NT}")

    s_pt, r_pt = sigmas(SH, midx, base, ERA5.baseline_vectors(e5, b0, b1), G, ok)
    ev = ERA5.cell_vectors(e5, b0, b1)
    ref, eb, nocell, mode = ERA5.matched(e5, tc, base, base, b0, b1, MON, "cell")
    if mode != "cell":
        print("matched comparison unavailable (per-cell output missing)")
        return 1
    s_cp, r_cp = sigmas(SH, midx, base, ev, G, ok)
    s_m, r_m = sigmas(SH, midx, ref, eb, G, ok)
    print()
    dist("point", s_pt, r_pt, fair, poor)
    dist("cell/pt", s_cp, r_cp, fair, poor)
    res = dist("matched", s_m, r_m, fair, poor)
    print(f"no ERA5 land cell within {ERA5.land_params(cfg)[1]:g} km: {int(nocell.sum())}: {T.label[nocell].tolist()}")
    nobox = ~nocell & ~np.isfinite(ref[:, 0])
    if nobox.any():
        print(f"land cell but no TerraClimate land pixel in it: {T.label[nobox].tolist()}")

    d = e5["tmax"]
    blandf = {}
    cells = tc["tmax"]["box_cells"].astype(np.int64)
    for k in range(NT):
        if d["cell_i"][k] >= 0:
            f = int(d["cell_i"][k]) * ERA5.NLON + int(d["cell_j"][k])
            p = np.searchsorted(cells, f)
            blandf[k] = float(tc["tmax"]["box_land"][p]) if p < len(cells) and cells[p] == f else np.nan
    diff = eb - ref
    order = [k for k in np.argsort(-np.nan_to_num(s_m, nan=-1)) if np.isfinite(s_m[k])][:15]
    print("\nworst 15 (matched):")
    print(f"{'place':34s} {'lat':>6s} {'lon':>7s} {'km':>4s} {'lsm':>4s} {'tcland':>6s} {'point':>6s} {'cell/pt':>7s} {'matched':>7s}"
          f"  dTx JJA/DJF  dTn JJA/DJF  P ratio JJA/DJF  dDew JJA/DJF (ERA5 cell - footprint)")
    for k in order:
        pr = (eb[k, C.PPT] + 1) / (ref[k, C.PPT] + 1)
        print(f"{T.label[k][:34]:34s} {T.lat[k]:6.2f} {T.lon[k]:7.2f} {d['cell_km'][k]:4.0f} {d['cell_lsm'][k]:4.2f} {blandf.get(k, np.nan):6.2f} "
              f"{s_pt[k]:6.2f} {s_cp[k]:7.2f} {s_m[k]:7.2f}  {diff[k, 2]:+5.1f}/{diff[k, 0]:+5.1f}  {diff[k, 6]:+5.1f}/{diff[k, 4]:+5.1f}  "
              f"{pr[2]:6.2f}/{pr[0]:6.2f}  {diff[k, 14]:+5.1f}/{diff[k, 12]:+5.1f}")
    print("\nall places (point -> matched):")
    for k in range(NT):
        print(f"  {T.label[k][:34]:34s} {s_pt[k]:6.2f} -> {s_m[k]:6.2f}" + ("  no land cell" if nocell[k] else ""))
    if res is None:
        return 1
    med, share = res
    met = med < 0.8 and share < 0.10
    print(f"\nTARGET (median < 0.8 sigma and < 10% over {poor:g} sigma): {'MET' if met else 'NOT MET'} (median {med:.2f}, {share:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
