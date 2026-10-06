"""Builds prototypes/species/data/ for the prototype page from the SYNTHETIC arrays made by synth.py:
  <id>_base.cts, <id>_<ssp>.cts (classified 'lite' product, see encode.py), novel_<ssp>.cts, and stats.json
(areas, centroids, agreement, dependency overlaps and the place-by-species table, for every scenario x period x dispersal mode).
Usage: python build_site_data.py WORKDIR OUTDIR"""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import numpy as np
import encode as E
import synth

PLACES = ["Raleigh, NC", "New York City, NY", "Phoenix, AZ", "Anchorage, AK", "Miami, FL", "Seattle, WA", "Mexico City, MX",
          "London, UK", "Madrid, Spain", "Moscow, Russia", "Reykjavík, Iceland", "Cairo, Egypt", "Nairobi, Kenya", "Mumbai, India",
          "Singapore, Singapore", "Beijing, China", "Tokyo, Japan", "Manaus, Brazil", "Lima, Peru", "São Paulo, Brazil",
          "Cape Town, South Africa", "Sydney, Australia", "Perth, Australia", "Berlin, Germany"]
SSPS, SS_LABEL = synth.SSPS, ["SSP1-2.6", "SSP2-4.5", "SSP3-7.0", "SSP5-8.5"]
PERIODS = ["2050", "2100"]
DISP = ["unlimited", "limited", "none"]
THR = E.THR
INVOLVED = {s['id'] for s in synth.SPECIES if s['deps']} | {d for s in synth.SPECIES for d in s['deps']}


def state(S0, Sk, d):
    now = (S0 & 127) >= THR
    fr = (Sk & 127) >= THR
    reach = (Sk >> 7).astype(bool)
    fut = fr if d == 0 else (fr & (now | reach) if d == 1 else fr & now)
    return now, fut


def centroid(mask, w, lat, lon):
    ww = (mask * w)
    s = ww.sum()
    if s == 0:
        return None
    la, lo = np.radians(lat)[:, None], np.radians(lon)[None, :]
    x = (ww * np.cos(la) * np.cos(lo)).sum() / s; y = (ww * np.cos(la) * np.sin(lo)).sum() / s; z = (ww * np.sin(la)).sum() / s
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def bearing_km(a, b):
    if not a or not b:
        return None
    p1, p2, dl = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    km = 6371 * 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))
    br = (math.degrees(math.atan2(math.sin(dl) * math.cos(p2), math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) + 360) % 360
    return km, br


def main(work: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    z = np.load(work / "world.npz"); lat_full = z["lat"]
    sub = 3
    lat = lat_full[::sub]; lon = ((np.arange(synth.NX) + 0.5) * 360 / synth.NX - 180)[::sub]
    w = synth.cell_km2(lat_full)[::sub, ::sub] * sub * sub
    sites = json.load(open(Path(__file__).resolve().parents[2] / "site/data/index.json"))["rows"]
    places = []
    for n in PLACES:
        r = next(r for r in sites if r[0] == n)
        places.append(dict(name=n, lat=r[1], lon=r[2]))
    rows = [int((90 - p["lat"]) / 180 * synth.NY) for p in places]
    cols = [int((p["lon"] + 180) / 360 * synth.NX) % synth.NX for p in places]
    stats = dict(ssps=SSPS, ssp_labels=SS_LABEL, periods=PERIODS, dispersal=DISP, places=places, species={}, dep={}, synthetic=True,
                 reach_km=list(synth.REACH_KM), thr=THR, nmem=synth.NMEM)
    (out / "land.cts").write_bytes(E.enc_cts({"N": z["land"].astype(np.uint8)}, ["N"]))
    for ssp in SSPS:
        N = np.load(work / f"novel_{ssp}.npz")["N"]
        (out / f"novel_{ssp}.cts").write_bytes(E.enc_cts({"N": N}, ["N"]))
    sets = {}
    for sp in synth.SPECIES:
        sid = sp["id"]
        base = E.load_base(work, sid)
        (out / f"{sid}_base.cts").write_bytes(E.enc_cts(E.lite(base), ["S0"]))
        S0 = base["S0"]
        S0c = S0[::sub, ::sub]
        info = dict(id=sid, name=sp["name"], sci=sp["sci"], group=sp["group"], deps=sp["deps"], niche=dict(t=sp["T"], p=sp["P"]), by={}, place={})
        union = (S0c & 127) >= THR
        info["area_now_km2"] = float((w * ((S0c & 127) >= THR)).sum())
        for ssp in SSPS:
            sc = E.load(work, sid, ssp)
            (out / f"{sid}_{ssp}.cts").write_bytes(E.enc_cts(E.lite(sc), ["S1", "S2", "A"]))
            for k, per in enumerate(PERIODS):
                Sk = sc["S1" if k == 0 else "S2"]
                A = (sc["A"] >> 4) if k == 0 else (sc["A"] & 15)
                for d in range(3):
                    now, fut = state(S0c, Sk[::sub, ::sub], d)
                    an, af, lost, kept, gain = (float((w * m).sum()) for m in (now, fut, now & ~fut, now & fut, ~now & fut))
                    c0, c1 = centroid(now, w, lat, lon), centroid(fut, w, lat, lon)
                    bk = bearing_km(c0, c1)
                    agr = float((w * (fut & (A[::sub, ::sub] >= 6))).sum() / af) if af > 0 else None
                    info["by"][f"{ssp}|{per}|{DISP[d]}"] = dict(now=an, fut=af, lost=lost, kept=kept, gained=gain, c0=c0, c1=c1,
                                                              shift_km=bk[0] if bk else None, bearing=bk[1] if bk else None, agree_share=agr)
                    union |= fut
                    if sid in INVOLVED:
                        sets[(sid, ssp, k, d)] = (now, fut)
                    nowf, futf = state(S0[rows, cols], Sk[rows, cols], d)
                    info["place"].setdefault(f"{ssp}|{per}|{DISP[d]}", [int(1 if (n and not f) else 2 if (n and f) else 3 if f else 0) for n, f in zip(nowf, futf)])
        ys, xs = np.nonzero(union)
        info["bbox"] = [float(lon[xs.min()]) - 2, float(lat[ys.max()]) - 2, float(lon[xs.max()]) + 2, float(lat[ys.min()]) + 2] if len(ys) else [-180, -60, 180, 80]
        stats["species"][sid] = info
    # dependency overlap: share of the dependent species' range that the partner's range also covers, now vs future
    for sp in synth.SPECIES:
        for dep in sp["deps"]:
            for ssp in SSPS:
                for k, per in enumerate(PERIODS):
                    for d in range(3):
                        an, af = sets[(sp["id"], ssp, k, d)]
                        bn, bf = sets[(dep, ssp, k, d)]
                        v = [float((w * (an & bn)).sum() / max(1, (w * an).sum())), float((w * (af & bf)).sum() / max(1, (w * af).sum()))]
                        stats["dep"].setdefault(f"{sp['id']}>{dep}", {})[f"{ssp}|{per}|{DISP[d]}"] = v
    (out / "stats.json").write_text(json.dumps(stats, separators=(",", ":")))
    tot = sum(f.stat().st_size for f in out.glob("*"))
    print("data bytes", tot)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
