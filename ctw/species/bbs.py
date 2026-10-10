"""North American Breeding Bird Survey ingest and observed-change metrics (workstream W4).

Source: USGS ScienceBase item 691cfb53d4be021d1d89b482 (2025 release, 1966-2024), DOI 10.5066/P14SNUV4, CC0 1.0.
Files used: Routes.csv (route start points), SpeciesList.csv, Weather.csv (run type per route-year), States.zip (counts per route-year
and species). Stop-level counts (50-StopData.zip) are not needed: presence uses route-year totals.

Rules (C-validation 4.3, proposals): a route-year counts when Weather.RunType == 1 (acceptable survey) and RPID == 101 (standard
protocol). A route qualifies when it has at least MIN_YEARS acceptable years in BOTH windows. A species is present on a route in a
window when it was detected in at least MIN_DET acceptable route-years of that window. Routes map to the 1/24 degree grid (row 0 =
north, as ctw/species/climategrid.py) by their START point; routes are about 40 km long, so a route covers many cells and the start
cell is only a representative location (documented limitation).
"""
from __future__ import annotations
import io, zipfile, math
import numpy as np
import pandas as pd

from . import climategrid as G
from . import hindcast as H

W1, W2 = (1966, 1985), (2005, 2024)
MIN_YEARS = 10
MIN_DET = 3


def grid_rc(lat, lon):
    """Row (0 = north) and column on the 1/24 degree TerraClimate grid for lat/lon (cell i spans [90 - RES(i+1), 90 - RES i))."""
    r = np.clip(np.floor((90.0 - np.asarray(lat, float)) / G.RES), 0, G.NLAT - 1).astype(np.int64)
    c = np.clip(np.floor((np.asarray(lon, float) + 180.0) / G.RES), 0, G.NLON - 1).astype(np.int64)
    return r, c


def read_routes(src) -> pd.DataFrame:
    d = pd.read_csv(src, dtype=str)
    d.columns = [c.strip() for c in d.columns]
    for c in d.columns:
        d[c] = d[c].str.strip()
    out = pd.DataFrame({"country": d["CountryNum"].astype(int), "state": d["StateNum"].astype(int), "route": d["Route"].astype(int),
                        "name": d["RouteName"], "lat": d["Latitude"].astype(float), "lon": d["Longitude"].astype(float),
                        "route_type": d.get("RouteTypeID", pd.Series(["1"] * len(d))).astype(int)})
    out = out[(out.lat.abs() <= 90) & (out.lon.abs() <= 180) & (out.lat != 0)].copy()
    out["row"], out["col"] = grid_rc(out.lat.values, out.lon.values)
    return out


def read_species(src) -> pd.DataFrame:
    d = pd.read_csv(src, dtype=str, encoding="latin-1")
    d.columns = [c.strip() for c in d.columns]
    d["AOU"] = d["AOU"].astype(int)
    d["sci"] = (d["Genus"].str.strip() + " " + d["Species"].str.strip()).str.strip()
    d["english"] = d["English_Common_Name"].str.strip()
    return d[["AOU", "english", "sci", "Order", "Family"]]


def acceptable_runs(src) -> pd.DataFrame:
    """Route-years with an acceptable survey: columns RouteDataID, country, state, route, year."""
    w = pd.read_csv(src, dtype=str)
    w.columns = [c.strip() for c in w.columns]
    for c in w.columns:
        w[c] = w[c].str.strip()
    ok = pd.Series(True, index=w.index)
    if "RunType" in w:
        ok &= w["RunType"].astype(float) == 1
    if "RPID" in w:
        ok &= w["RPID"].astype(float) == 101
    w = w[ok]
    return pd.DataFrame({"RouteDataID": w["RouteDataID"].astype(np.int64), "country": w["CountryNum"].astype(int),
                         "state": w["StateNum"].astype(int), "route": w["Route"].astype(int), "year": w["Year"].astype(int)})


def qualifying_routes(runs: pd.DataFrame, min_years: int = MIN_YEARS, w1=W1, w2=W2) -> pd.DataFrame:
    """Routes with at least min_years acceptable years in each window."""
    k = ["country", "state", "route"]
    a = runs[runs.year.between(*w1)].groupby(k).year.nunique().rename("n1")
    b = runs[runs.year.between(*w2)].groupby(k).year.nunique().rename("n2")
    q = pd.concat([a, b], axis=1).fillna(0).astype(int).reset_index()
    q["qualifies"] = (q.n1 >= min_years) & (q.n2 >= min_years)
    return q


def detections(zip_src, runs: pd.DataFrame, w1=W1, w2=W2, chunksize=1_000_000, log=print) -> pd.DataFrame:
    """Per route, species and window: number of acceptable route-years with a detection. Streams the state files in States.zip."""
    okid = set(runs.RouteDataID.values)
    parts = []
    with zipfile.ZipFile(zip_src) as z:
        for m in z.namelist():
            if not m.lower().endswith(".csv"):
                continue
            with z.open(m) as fh:
                head = pd.read_csv(fh, nrows=0).columns
            cols = [c.strip() for c in head]
            use = [c for c in head if c.strip() in ("RouteDataID", "CountryNum", "StateNum", "Route", "Year", "AOU", "SpeciesTotal")]
            stops = [c for c in head if c.strip().startswith("Stop")]
            if "SpeciesTotal" not in [c.strip() for c in use]:
                use += stops
            log("  member", m, "columns", len(cols), "using", len(use))
            with z.open(m) as fh:
                for ch in pd.read_csv(fh, usecols=use, chunksize=chunksize, skipinitialspace=True):
                    ch.columns = [c.strip() for c in ch.columns]
                    ch = ch[ch.RouteDataID.isin(okid) & (ch.Year.between(w1[0], w1[1]) | ch.Year.between(w2[0], w2[1]))]
                    tot = ch["SpeciesTotal"] if "SpeciesTotal" in ch else ch[[c for c in ch.columns if c.startswith("Stop")]].sum(axis=1)
                    ch = ch[tot > 0]
                    ch = ch.assign(win=np.where(ch.Year <= w1[1], 1, 2))
                    parts.append(ch.groupby(["CountryNum", "StateNum", "Route", "AOU", "win"]).Year.nunique().rename("n").reset_index())
    d = pd.concat(parts)
    d = d.groupby(["CountryNum", "StateNum", "Route", "AOU", "win"]).n.sum().reset_index()
    d = d.pivot_table(index=["CountryNum", "StateNum", "Route", "AOU"], columns="win", values="n", fill_value=0).reset_index()
    d.columns = ["country", "state", "route", "AOU"] + [f"det{int(c)}" for c in d.columns[4:]]
    for c in ("det1", "det2"):
        if c not in d:
            d[c] = 0
    return d


def route_presence(det: pd.DataFrame, min_det: int = MIN_DET) -> pd.DataFrame:
    det = det.copy()
    det["p1"], det["p2"] = det.det1 >= min_det, det.det2 >= min_det
    return det


def species_cellset(routes_q: pd.DataFrame, pres: pd.DataFrame, aou: int, block: int = 1) -> H.CellSet:
    """CellSet of one species on the qualifying routes' start cells. routes_q: qualifying routes with row, col, lat, lon;
    pres: route_presence output. Routes in the same cell are merged (present when any route is). block > 1 coarsens the grid to
    block x block native cells (for example 12 = 0.5 degrees). Cell weight is 1 (the sampling unit), not area."""
    p = pres[pres.AOU == aou][["country", "state", "route", "p1", "p2"]]
    r = routes_q.merge(p, on=["country", "state", "route"], how="left")
    r["p1"], r["p2"] = r.p1.fillna(False).astype(bool), r.p2.fillna(False).astype(bool)
    r["crow"], r["ccol"] = r.row // block, r.col // block
    g = r.groupby(["crow", "ccol"]).agg(lat=("lat", "mean"), lon=("lon", "mean"), o1=("p1", "max"), o2=("p2", "max"), n=("route", "size")).reset_index()
    cs = H.CellSet(g.lat.values, g.lon.values, np.ones(len(g)), g.o1.values, g.o2.values)
    cs.cluster = (g.crow.values.astype(np.int64) * 100000 + g.ccol.values)
    return cs


def observed_table(routes_q: pd.DataFrame, pres: pd.DataFrame, species: pd.DataFrame, n_boot: int = 200, min_routes: int = 20, block: int = 1, log=print) -> pd.DataFrame:
    """Observed change for every species with at least min_routes route-presences in either window; bootstrap only when the species is
    eligible (>= 100 route-presences in each window, C-validation 4.7)."""
    agg = pres.groupby("AOU").agg(routes_w1=("p1", "sum"), routes_w2=("p2", "sum")).reset_index()
    qk = set(zip(routes_q.country, routes_q.state, routes_q.route))
    pres = pres[[k in qk for k in zip(pres.country, pres.state, pres.route)]]
    agg = pres.groupby("AOU").agg(routes_w1=("p1", "sum"), routes_w2=("p2", "sum")).reset_index()
    agg = agg[(agg.routes_w1 >= min_routes) | (agg.routes_w2 >= min_routes)].merge(species, on="AOU", how="left")
    rows = []
    for i, a in enumerate(agg.itertuples()):
        cs = species_cellset(routes_q, pres, a.AOU, block)
        el = H.eligible(a.routes_w1, a.routes_w2, "bbs")
        o = H.observed_change(cs, n_boot=n_boot if el else 0, seed=a.AOU, noise_se=H.TH.noise_se)
        perm = H.permutation_p(cs, n=500, seed=a.AOU) if el else math.nan
        rows.append(dict(AOU=a.AOU, english=a.english, sci=a.sci, routes_w1=a.routes_w1, routes_w2=a.routes_w2, eligible=el, n_cells=len(cs.lat),
                         cells_w1=int(cs.obs1.sum()), cells_w2=int(cs.obs2.sum()), perm_p=perm, **{k: o[k] for k in o if not isinstance(o[k], dict)}))
        if i % 50 == 0:
            log("  observed change", i, "/", len(agg))
    return pd.DataFrame(rows)
