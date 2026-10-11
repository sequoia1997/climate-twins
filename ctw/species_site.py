"""Build the species data for the static site: release assets (w3_*/s1_* summaries and CTS zips) -> site/species/data/.

    python -m ctw.species_site build --src DIR_WITH_ASSETS --out site/species/data

Adding species is only a data change: drop `<prefix>_<slug>_summary.json` + `<prefix>_<slug>_cts.zip` into the source folder and rebuild.
Output (all under --out; every file except index.json is content-hashed, so it can be cached for ever):
  index.json                         names, group, tier, bounding box, file names and sizes (loaded at start)
  places.json                        per species and place: loses / keeps / gains (loaded when the place list is opened)
  <id>/info.<hash>.json              one species' numbers, flags, DOIs (loaded on demand)
  <id>/base.<hash>.cts, <id>/<ssp>.<hash>.cts   the CTS map files (loaded on demand)
Selection rule per species: birds use the breeding-season run (`<slug>_breeding_*`) when it exists, everything else the all-year run;
tier C or `published: false` species are left out and listed in the log.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, zipfile
from pathlib import Path
import numpy as np

SSP_LABEL = {"ssp126": "SSP1-2.6", "ssp245": "SSP2-4.5", "ssp370": "SSP3-7.0", "ssp585": "SSP5-8.5"}
PERIOD_KEY = {"2041-2060": "2050", "2081-2100": "2100"}
PERIOD_LABEL = {"2050": "2041–2060", "2100": "2081–2100"}
MODES = ("unlimited", "limited", "none")
# Cities for the "species where you are" list (name, lat, lon). Extend freely: it is only a data table.
PLACES = [
    ("Raleigh, USA", 35.78, -78.64), ("New York, USA", 40.71, -74.01), ("Chicago, USA", 41.88, -87.63), ("Miami, USA", 25.77, -80.19),
    ("Atlanta, USA", 33.75, -84.39), ("Minneapolis, USA", 44.98, -93.27), ("Denver, USA", 39.74, -104.99), ("Phoenix, USA", 33.45, -112.07),
    ("Seattle, USA", 47.61, -122.33), ("Los Angeles, USA", 34.05, -118.24), ("Anchorage, USA", 61.22, -149.90), ("Toronto, Canada", 43.65, -79.38),
    ("Vancouver, Canada", 49.28, -123.12), ("Winnipeg, Canada", 49.90, -97.14), ("Mexico City, Mexico", 19.43, -99.13), ("Havana, Cuba", 23.11, -82.37),
    ("Bogota, Colombia", 4.71, -74.07), ("Lima, Peru", -12.05, -77.04), ("Manaus, Brazil", -3.10, -60.02), ("Sao Paulo, Brazil", -23.55, -46.63),
    ("Buenos Aires, Argentina", -34.60, -58.38), ("Santiago, Chile", -33.45, -70.67), ("Reykjavik, Iceland", 64.15, -21.94), ("London, UK", 51.51, -0.13),
    ("Paris, France", 48.86, 2.35), ("Berlin, Germany", 52.52, 13.40), ("Madrid, Spain", 40.42, -3.70), ("Rome, Italy", 41.90, 12.50),
    ("Stockholm, Sweden", 59.33, 18.07), ("Moscow, Russia", 55.76, 37.62), ("Istanbul, Turkey", 41.01, 28.98), ("Cairo, Egypt", 30.04, 31.24),
    ("Lagos, Nigeria", 6.52, 3.38), ("Nairobi, Kenya", -1.29, 36.82), ("Kinshasa, DR Congo", -4.44, 15.27), ("Johannesburg, South Africa", -26.20, 28.05),
    ("Cape Town, South Africa", -33.92, 18.42), ("Dakar, Senegal", 14.72, -17.47), ("Delhi, India", 28.61, 77.21), ("Mumbai, India", 19.08, 72.88),
    ("Dubai, UAE", 25.20, 55.27), ("Beijing, China", 39.90, 116.41), ("Shanghai, China", 31.23, 121.47), ("Tokyo, Japan", 35.68, 139.69),
    ("Seoul, South Korea", 37.57, 126.98), ("Bangkok, Thailand", 13.76, 100.50), ("Singapore", 1.35, 103.82), ("Jakarta, Indonesia", -6.21, 106.85),
    ("Sydney, Australia", -33.87, 151.21), ("Perth, Australia", -31.95, 115.86), ("Brisbane, Australia", -27.47, 153.03), ("Auckland, New Zealand", -36.85, 174.76),
]
GROUP_ORDER = ["tree", "wild_plant", "bird", "mammal", "insect_arachnid", "reptile", "amphibian", "reptile_amphibian", "fish", "crop"]


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:10]


def pick_runs(src: Path) -> tuple[dict, list]:
    """{public id: (summary path, zip path, season)} and a list of (name, reason) for what was left out."""
    runs: dict[str, dict] = {}
    for f in sorted(src.glob("*_summary.json")):
        m = re.match(r"^(?:(?:s\d+|w\d+)_)+(.+?)(_breeding)?_summary\.json$", f.name)
        if not m:
            continue
        z = f.with_name(f.name.replace("_summary.json", "_cts.zip"))
        runs.setdefault(m.group(1), {})["breeding" if m.group(2) else "all"] = (f, z)
    chosen, skipped = {}, []
    for sid, v in runs.items():
        order = ("breeding", "all") if (json.load(open((v.get("breeding") or v["all"])[0]))["species"].get("group") == "bird") else ("all", "breeding")
        for k in order:
            if k not in v:
                continue
            f, z = v[k]
            S = json.load(open(f))
            if S.get("tier") not in ("A", "B") or not S.get("published", True) or not z.exists():
                skipped.append((f"{sid} ({k})", f"tier {S.get('tier')}, published {S.get('published')}, cts zip {'present' if z.exists() else 'missing'}"))
                continue
            chosen[sid] = (f, z, k)
            break
    return chosen, skipped


def _bbox(cts_mod, base: bytes, scen: dict) -> list:
    """Bounding box [west, south, east, north] of the suitable cells (now or later), trimming 1% of cells at each edge."""
    lev = 4
    d = cts_mod.decode(base, lev)
    m = d["S0"] > 0
    for b in scen.values():
        e = cts_mod.decode(b, lev)
        m |= (e["S1"] & 127) > 0
        m |= (e["S2"] & 127) > 0
    if not m.any():
        return [-180, -60, 180, 80]
    ys, xs = np.nonzero(m)
    H, W = m.shape
    lo, hi = np.percentile(xs, [1, 99]), np.percentile(ys, [1, 99])
    west, east = -180 + lo[0] * 360 / W, -180 + (lo[1] + 1) * 360 / W
    north, south = 90 - hi[0] * 180 / H, 90 - (hi[1] + 1) * 180 / H
    pad = 3.0
    return [round(float(max(-180, west - pad)), 2), round(float(max(-85, south - pad)), 2), round(float(min(180, east + pad)), 2), round(float(min(85, north + pad)), 2)]


def centre_inside(mask: np.ndarray, lat: float, lon: float, r: int = 6) -> bool:
    """True when the area-weighted centre (lat, lon) lies in the species' own suitable area (any suitable cell within +-6 cells, about 28 km, so a centre over a lake or a narrow gap still counts).
    A centre of a range split over several regions often falls where the species is not; the page then does not show it."""
    H, W = mask.shape
    i = min(H - 1, max(0, int((90 - lat) / 180 * H)))
    j = min(W - 1, max(0, int((lon + 180) / 360 * W)))
    return bool(mask[max(0, i - r):i + r + 1, max(0, j - r):j + r + 1].any())


def _place_codes(cts_mod, base: bytes, scen: dict, withheld: dict, by: dict = None) -> dict:
    """{"ssp|period|mode": string, one char per PLACES entry}: 0 not suitable, 1 loses, 2 keeps, 3 gains, 9 numbers withheld."""
    d0 = cts_mod.decode(base, 1)["S0"]
    H, W = d0.shape
    ij = []
    for _, la, lo in PLACES:
        ij.append((min(H - 1, max(0, int((90 - la) / 180 * H))), min(W - 1, max(0, int((lo + 180) / 360 * W)))))

    def near(a, r, c):                                      # any suitable cell within +-1 (about 5 km), so a coastal city is not read from an ocean cell
        return bool(a[max(0, r - 1):r + 2, max(0, c - 1):c + 2].any())
    out = {}
    now = [near(d0 > 0, r, c) for r, c in ij]
    for ssp, b in scen.items():
        e = cts_mod.decode(b, 1)
        for pi, band in (("2050", "S1"), ("2100", "S2")):
            s = e[band]
            fut_u, reach = (s & 127) > 0, (s >> 7) > 0
            for mode in MODES:
                fut = fut_u if mode == "unlimited" else (fut_u & ((d0 > 0) | reach) if mode == "limited" else fut_u & (d0 > 0))
                key = f"{ssp}|{pi}|{mode}"
                if by and by.get(key) and not by[key].get("withheld") and by[key].get("c0"):         # is the centre of the range inside the range, now and later?
                    by[key]["cok"] = centre_inside(d0 > 0, *by[key]["c0"]) and centre_inside(fut, *by[key]["c1"])
                if withheld.get(f"{ssp}|{pi}"):
                    out[key] = "9" * len(PLACES)
                    continue
                chars = []
                for k, (r, c) in enumerate(ij):
                    f_ = near(fut, r, c)
                    chars.append("2" if now[k] and f_ else "1" if now[k] else "3" if f_ else "0")
                out[key] = "".join(chars)
    return out


def info_json(S: dict, season: str, scen_keys: list, bbox: list, files: dict) -> dict:
    sp = S["species"]
    by, withheld = {}, {}
    for k, v in S["scenarios"].items():
        ssp = {"SSP1-2.6": "ssp126", "SSP2-4.5": "ssp245", "SSP3-7.0": "ssp370", "SSP5-8.5": "ssp585"}[v["ssp"]]
        pk = PERIOD_KEY[v["period"]]
        if v.get("withheld"):
            withheld[f"{ssp}|{pk}"] = v.get("withheld_reason", "high share of novel climate")
        for mode, m in v["modes"].items():
            key = f"{ssp}|{pk}|{mode}"
            if m.get("withheld"):
                by[key] = {"withheld": True, "now": m["area_now"], "novel": v["novel_share"]}
                continue
            by[key] = {"now": m["area_now"], "fut": m["area_fut"], "lost": m["loss"], "kept": m["stable"], "gained": m["gain"], "c0": m["centroid_now"],
                       "c1": m["centroid_fut"], "shift_km": m["shift_km"], "bearing": m["bearing"], "agree": m["agree_share"], "novel": v["novel_share"]}
    val = S.get("validation") or {}
    d = val.get("direct") if isinstance(val.get("direct"), dict) and val["direct"].get("available") else (val.get("w4_pipeline_evidence") or {})
    validation = None
    if val.get("kind"):
        validation = {"kind": val["kind"], "passed": bool(val.get("passed")), "auc": d.get("auc", d.get("cv_auc")), "tss": d.get("tss_best", d.get("cv_tss")),
                      "n_presence": d.get("n_presence", d.get("n_presence_routes")), "n_absence": d.get("n_absence", d.get("n_absence_routes")), "window": d.get("window")}
    rs = S.get("range_shift_test") or {}
    gr = S["gates"]
    return {
        "id": sp["id"].replace("_breeding", ""), "name": sp.get("common_name") or sp["scientific_name"], "sci": sp["scientific_name"], "group": sp["group"],
        "kind": S.get("species_kind", sp.get("kind", "wild")), "season": season if season == "breeding" else None,
        "tier": S["tier"], "confidence": S["confidence"], "soft_flags": S.get("soft_flags", []), "wording": S["wording"],
        "range_shifts": S.get("range_shifts_tested", "untested"), "range_shift_checks": rs.get("group_checks", []),
        "cv_kind": S.get("cv_kind"), "skill": {"auc": S["skill"].get("cv_auc"), "tss": S["skill"].get("cv_tss"), "boyce": S["skill"].get("cv_boyce"), "block_km": S["skill"].get("block_km")},
        "validation": validation, "records": {"cells": S["records"].get("thinned_cells"), "gate_cells": S["records"].get("gate_cells"), "used": S["records"].get("used_in_fit")},
        "dois": S.get("data_dois", []), "predictors": S["predictors"]["kept"], "n_models": next(iter(S["scenarios"].values()))["n_models"],
        "dispersal": {"km_per_decade": S["dispersal"]["km_per_decade"], "reach_km": S["dispersal"]["reach_km"], "calibrated": S["dispersal"].get("calibrated", False)},
        "range_check": {"status": gr.get("range_check", {}).get("status"), "commission": gr.get("range_check", {}).get("commission")},
        "novel_limit": gr.get("novelty", {}).get("threshold", 0.15), "area_now_km2": S["area_now_km2"], "bbox": bbox, "ssps": scen_keys, "withheld": withheld, "by": by,
        "code": S.get("provenance", {}).get("code"), "made": S.get("provenance", {}).get("made"),
    }


def build(src: Path, out: Path, log=print) -> dict:
    from .species import cts as cts_mod                      # read-only use of the shared CTS reader
    chosen, skipped = pick_runs(src)
    out.mkdir(parents=True, exist_ok=True)
    index, places, total = [], {}, 0
    for sid, (f, z, season) in sorted(chosen.items()):
        S = json.load(open(f))
        zf = zipfile.ZipFile(z)
        slug = S["species"]["id"]
        names = {n.rsplit("/", 1)[-1]: n for n in zf.namelist()}
        base = zf.read(names[f"{slug}_base.cts"])
        scen = {}
        for n in names:
            m = re.match(rf"^{re.escape(slug)}_(ssp\d+)\.cts$", n)
            if m:
                scen[m.group(1)] = zf.read(names[n])
        scen = dict(sorted(scen.items()))
        bbox = _bbox(cts_mod, base, scen)
        d = out / sid
        for old in d.glob("*") if d.exists() else []:
            old.unlink()
        d.mkdir(exist_ok=True)
        files = {}
        for k, b in {"base": base, **scen}.items():
            fn = f"{k}.{_h(b)}.cts"
            (d / fn).write_bytes(b)
            files[k] = [f"{sid}/{fn}", len(b)]
        info = info_json(S, season, list(scen), bbox, files)
        info["id"] = sid
        places[sid] = _place_codes(cts_mod, base, scen, info["withheld"], info["by"])
        ib = json.dumps(info, separators=(",", ":"), ensure_ascii=False).encode()
        ifn = f"info.{_h(ib)}.json"
        (d / ifn).write_bytes(ib)
        total += sum(v[1] for v in files.values()) + len(ib)
        index.append({"id": sid, "name": info["name"], "sci": info["sci"], "group": info["group"], "kind": info["kind"], "tier": info["tier"],
                      "confidence": info["confidence"], "dois": info["dois"], "range_shifts": info["range_shifts"], "season": info["season"], "bbox": bbox,
                      "info": [f"{sid}/{ifn}", len(ib)], "files": files})
        log(f"{sid:28s} {season:8s} tier {info['tier']} {info['confidence']:8s} {sum(v[1] for v in files.values()) / 1e6:5.2f} MB  bbox {bbox}")
    index.sort(key=lambda r: (GROUP_ORDER.index(r["group"]) if r["group"] in GROUP_ORDER else 99, r["name"]))
    pb = json.dumps({"places": [[n, a, o] for n, a, o in PLACES], "sp": places}, separators=(",", ":")).encode()
    pfn = f"places.{_h(pb)}.json"
    for old in out.glob("places.*.json"):
        old.unlink()
    (out / pfn).write_bytes(pb)
    idx = {"v": 1, "ssps": {k: SSP_LABEL[k] for k in sorted({s for r in index for s in r["files"] if s != "base"})}, "periods": PERIOD_LABEL,
           "places": [pfn, len(pb)], "species": index}
    (out / "index.json").write_text(json.dumps(idx, separators=(",", ":"), ensure_ascii=False))
    live = {r["id"] for r in index}
    for d in out.iterdir():                                  # a species that is no longer chosen leaves the folder
        if d.is_dir() and d.name not in live:
            for p in d.glob("*"):
                p.unlink()
            d.rmdir()
    log(f"{len(index)} species, {total / 1e6:.1f} MB of species files (+ {len(pb) / 1e3:.0f} kB places, index {(out / 'index.json').stat().st_size / 1e3:.0f} kB); skipped: {skipped}")
    return idx


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="site/species/data")
    a = ap.parse_args()
    build(Path(a.src), Path(a.out))
