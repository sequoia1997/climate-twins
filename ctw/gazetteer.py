"""Place names for labelling grid cells, and country outlines.
GeoNames cities500 (CC BY 4.0) with admin-1 names; Natural Earth 1:50m countries (public domain) for country
names and for assigning each world grid cell to a country. If GeoNames cannot be reached, the committed snapshot
of the names used by the last release (data/places_snapshot.json.gz) is used instead.
Writes work/gazetteer.json: {"na": [[label, lat, lon, pop], ...], "world": [...], "source": ...}
and work/countries.geojson."""
from __future__ import annotations
import gzip, io, json, zipfile
import pandas as pd
from . import common as C
from .names import label as na_label
from .country_names import FIX


def country_names(cfg) -> dict:
    gj = json.load(open(C.download(cfg["sources"]["natural_earth"], C.work("downloads", "ne_50m_countries.geojson"))))
    cn = {}
    for f in gj["features"]:
        p = f["properties"]
        for k in ("ISO_A2_EH", "ISO_A2"):
            if p.get(k) and p[k] != "-99":
                cn.setdefault(p[k], p["NAME"])
    cn.update(FIX)
    return cn


def run(cfg=None):
    cfg = cfg or C.config()
    cn = country_names(cfg)
    try:
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
        g = g[g["pop"] >= 1000]
        nam = g[g.country.isin(["US", "CA", "MX"]) & (g["pop"] >= 2500)]
        na = [[na_label(n, c, a), round(la, 3), round(lo, 3), int(p)] for n, c, a, la, lo, p in
              zip(nam.name, nam.country, nam.admin1, nam.lat, nam.lon, nam["pop"])]

        def wl(n, c, a):
            if c == "US" and a == "Hawaii":
                return f"{n}, HI"
            if c in ("US", "CA", "MX"):
                return na_label(n, c, a)
            return f"{n}, {cn.get(c, c)}"
        wg = g[g.country.isin(list(cn) + ["US", "CA", "MX"])]
        world = [[wl(n, c, a), round(la, 3), round(lo, 3), int(p)] for n, c, a, la, lo, p in
                 zip(wg.name, wg.country, wg.admin1, wg.lat, wg.lon, wg["pop"])]
        src = "GeoNames cities500"
    except Exception as e:  # noqa: BLE001
        C.log.warning("GeoNames unavailable (%s); using the committed snapshot", e)
        s = json.load(gzip.open(C.DATA / "places_snapshot.json.gz", "rt"))
        na, world, src = s["na"], s["world"], s["source"]
    json.dump({"na": na, "world": world, "source": src, "countries": cn}, open(C.work("gazetteer.json"), "w"))
    C.log.info("gazetteer: %d North American, %d world places (%s)", len(na), len(world), src)
