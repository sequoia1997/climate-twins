"""Place requests from the site's "Don't see your place?" form.

triage():  runs when a request arrives. Looks the place up in GeoNames, lists likely matches, says whether one is
           already on the map (or very close to a place that is) and whether the datasets cover it. Writes the
           issue body (request.md) with the candidates in a hidden JSON block for add().
add():     runs when the owner comments "/add" or "/add N" on the issue. Appends candidate N (default 1) to
           data/targets.csv (US, Canada, Mexico except Hawaii) or data/world_targets.csv, in the same format as the
           existing rows. The rebuild then computes everything for it."""
from __future__ import annotations
import csv, io, json, os, re, sys, unicodedata, zipfile
import numpy as np
import pandas as pd
from . import common as C
from .names import label as na_label

NEAR_KM = 20.0                       # a candidate this close to an existing place is "already covered"
LOWER48_EXCLUDE = {"Alaska", "Hawaii"}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _gazetteer(cfg):
    z = C.download(cfg["sources"]["geonames"], C.work("downloads", "cities500.zip"))
    a1 = C.download(cfg["sources"]["geonames_admin1"], C.work("downloads", "admin1CodesASCII.txt"))
    cols = ["id", "name", "ascii", "alt", "lat", "lon", "fc", "fcode", "country", "cc2", "a1", "a2", "a3", "a4",
            "pop", "elev", "dem", "tz", "mod"]
    with zipfile.ZipFile(z) as zz:
        g = pd.read_csv(io.BytesIO(zz.read("cities500.txt")), sep="\t", header=None, names=cols, quoting=3,
                        keep_default_na=False, na_values={"lat": [""], "lon": [""], "pop": [""]}, low_memory=False)
    adm = pd.read_csv(a1, sep="\t", header=None, names=["code", "name", "ascii", "gid"], keep_default_na=False, quoting=3)
    amap = dict(zip(adm.code, adm.name))
    g["admin1"] = [amap.get(f"{c}.{a}", "") for c, a in zip(g.country, g.a1)]
    return g


def _country_names(cfg):
    from .gazetteer import country_names
    return country_names(cfg)


def candidates(place: str, region: str, cfg, n: int = 5) -> list[dict]:
    g = _gazetteer(cfg)
    cn = _country_names(cfg)
    q = _fold(place)
    if not q:
        return []
    names = g["name"].map(_fold)
    asc = g["ascii"].map(_fold)
    exact = (names == q) | (asc == q)
    alt = g["alt"].str.lower().str.contains(r"(?:^|,)" + re.escape(place.strip().lower()) + r"(?:,|$)", regex=True, na=False)
    hit = g[exact | alt].copy()
    if hit.empty:                                    # fall back to names that start with the query
        hit = g[names.str.startswith(q) | asc.str.startswith(q)].copy()
    if hit.empty:
        return []
    hit["exact"] = exact[hit.index]
    r = _fold(region)
    if r:
        cname = hit.country.map(lambda c: _fold(cn.get(c, c)))
        hit["region_hit"] = (hit.admin1.map(_fold).str.contains(r, regex=False) | cname.str.contains(r, regex=False)
                             | hit.country.str.lower().eq(r) | hit.a1.str.lower().eq(r))
    else:
        hit["region_hit"] = False
    hit = hit.sort_values(["region_hit", "exact", "pop"], ascending=[False, False, False]).head(n)
    out = []
    for _, x in hit.iterrows():
        out.append(dict(geonameid=int(x.id), name=x["name"], admin1=x.admin1, country=x.country,
                        country_name=cn.get(x.country, x.country), lat=round(float(x.lat), 5), lon=round(float(x.lon), 5),
                        pop=int(x["pop"]) if pd.notna(x["pop"]) else 0))
    return out


def assess(c: dict, T: pd.DataFrame, cfg) -> dict:
    """Where the place would go, whether it's already covered, and whether the data reach it."""
    in_na = c["country"] in ("US", "CA", "MX") and c["admin1"] != "Hawaii"
    d = C.haversine_km(c["lat"], c["lon"], T.lat.values, T.lon.values)
    k = int(np.argmin(d))
    notes, ok = [], True
    if d[k] <= NEAR_KM:
        notes.append(f"Already on the map nearby: **{T.label[k]}**, {d[k]:.0f} km away.")
        ok = False
    if in_na:
        from pyproj import Transformer
        g = cfg["grids"]
        x, y = Transformer.from_crs("EPSG:4326", g["na_crs"], always_xy=True).transform(c["lon"], c["lat"])
        inside = g["na_x0"] <= x <= g["na_x0"] + g["na_nx"] * g["na_cell_m"] and g["na_y0"] - g["na_ny"] * g["na_cell_m"] <= y <= g["na_y0"]
        if not inside:
            notes.append("Outside the North American climate grid.")
            ok = False
        domain = "conus" if c["country"] == "US" and c["admin1"] not in LOWER48_EXCLUDE else "na"
        notes.append("Would join the North American places" + (" (contiguous US: PRISM variability)." if domain == "conus" else "."))
    else:
        domain = "world"
        if c["lat"] < cfg["grids"]["world_lat_min"]:
            notes.append("South of the world climate grid.")
            ok = False
        notes.append("Would join the world cities (TerraClimate). Very small islands can lack land data; the build checks.")
    return dict(ok=ok, domain=domain, nearest=T.label[k], nearest_km=round(float(d[k]), 1), notes=notes)


def triage(place: str, region: str, note: str, cfg=None) -> int:
    cfg = cfg or C.config()
    T = C.targets()
    place, region = place.strip()[:120], region.strip()[:120]
    note = re.sub(r"[<>`]", "", note.strip())[:500]
    cands = candidates(place, region, cfg)
    title = f"Place request: {place}" + (f", {region}" if region else "")
    lines = [f"**Requested:** {place}" + (f" — {region}" if region else ""), ""]
    if note:
        lines += ["> " + note.replace("\n", "\n> "), ""]
    if not cands:
        lines += ["No match in GeoNames (places with 500+ people). It may be spelled differently or be very small.",
                  "", "Close this issue to decline."]
        verdict = "not found"
    else:
        lines += ["| # | Place | Region | Country | Population | Lat, lon | Check |", "|---|---|---|---|---|---|---|"]
        for i, c in enumerate(cands, 1):
            a = assess(c, T, cfg)
            c["domain"] = a["domain"]
            mark = "✅ can add" if a["ok"] else "⚠️ see notes"
            lines.append(f"| {i} | {c['name']} | {c['admin1']} | {c['country_name']} | {c['pop']:,} | {c['lat']:.3f}, {c['lon']:.3f} | {mark} |")
            c["notes"] = a["notes"]
        lines += ["", "**Notes on #1:** " + " ".join(cands[0]["notes"]), "",
                  "To add a place, comment `/add` (the first row) or `/add 2`, `/add 3`… A data rebuild starts and its pull",
                  "request adds the place to the map when merged. To decline, close this issue."]
        verdict = "can add" if assess(cands[0], T, cfg)["ok"] else "check"
    lines += ["", f"<!-- ctw:candidates {json.dumps(cands, ensure_ascii=True)} -->"]
    open("request.md", "w").write("\n".join(lines) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"title={title.replace(chr(10), ' ')}\nverdict={verdict}\n")
    print(title, "|", verdict)
    return 0


def add(body: str, command: str, cfg=None) -> int:
    cfg = cfg or C.config()
    m = re.search(r"<!-- ctw:candidates (.*?) -->", body or "", re.S)
    if not m:
        print("No candidates found in this issue.")
        return 1
    cands = json.loads(m.group(1))
    k = re.match(r"\s*/add\s*(\d+)?", command or "")
    i = int(k.group(1)) if k and k.group(1) else 1
    if not 1 <= i <= len(cands):
        print(f"There is no candidate {i}.")
        return 1
    c = cands[i - 1]
    T = C.targets()
    if (C.haversine_km(c["lat"], c["lon"], T.lat.values, T.lon.values) < 1.0).any():
        print(f"{c['name']} is already on the map.")
        return 1
    if c.get("domain") in ("conus", "na"):
        lab = na_label(c["name"], c["country"], c["admin1"])
        row = [lab, c["country"], c["admin1"], c["lat"], c["lon"], c["pop"], c["domain"]]
        path = C.DATA / "targets.csv"
    else:
        lab = f"{c['name']}, HI" if (c["country"] == "US" and c["admin1"] == "Hawaii") else f"{c['name']}, {c['country_name']}"
        row = [lab, c["country"], c["country_name"], c["admin1"], c["lat"], c["lon"], c["pop"], False]
        path = C.DATA / "world_targets.csv"
    existing = pd.read_csv(path, keep_default_na=False)
    if lab in set(existing.label):
        print(f"A place labelled {lab} already exists.")
        return 1
    raw = path.read_text()
    with open(path, "a", newline="") as f:
        if not raw.endswith("\n"):
            f.write("\n")
        csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n").writerow(row)
    print(lab)
    return 0
