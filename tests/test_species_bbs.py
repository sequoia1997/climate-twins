"""BBS ingest tests on a synthetic miniature of the real file layout (headers seen in the Actions probe, run 38072387399)."""
import io, zipfile
import numpy as np
import pandas as pd
from ctw.species import bbs, climategrid as G


def test_grid_rc_matches_climategrid():
    r, c = bbs.grid_rc([89.979166667, 0.0, -89.99], [-179.979166667, 0.0, 179.99])
    assert (r[0], c[0]) == (0, 0) and r[2] == G.NLAT - 1 and c[2] == G.NLON - 1
    assert abs(G.cell_lat(r[1]) - 0.0) < G.RES and abs(G.cell_lon(c[1]) - 0.0) < G.RES


def make_world(tmp_years1=range(1970, 1982), tmp_years2=range(2008, 2020)):
    routes = ["CountryNum,StateNum,Route,RouteName,Active,Latitude,Longitude,Stratum,BCR,RouteTypeID,RouteTypeDetailID"]
    weather = ["RouteDataID,CountryNum,StateNum,Route,RPID,Year,Month,Day,RunType"]
    rows = ["RouteDataID,CountryNum,StateNum,Route,RPID,Year,AOU,Count10,Count20,Count30,Count40,Count50,StopTotal,SpeciesTotal"]
    rid = 0
    for k in range(40):                               # 40 routes along a latitude gradient
        lat = 35 + k * 0.25
        routes.append(f"840,02,{k+1:03d},R{k},1   ,{lat:.6f}  ,-87.5 ,14  ,27  ,1,1")
        for y in list(tmp_years1) + list(tmp_years2):
            rid += 1
            weather.append(f"{rid},840,02,{k+1:03d},101,{y},6,1,1")
            # species 100 occupies lat < 40 early and lat < 42 later; species 200 everywhere
            lim = 40 if y < 2000 else 42
            if lat < lim:
                rows.append(f"{rid},840,02,{k+1:03d},101,{y},00100,1,0,0,0,0,1,1")
            rows.append(f"{rid},840,02,{k+1:03d},101,{y},00200,5,0,0,0,0,5,5")
        rid += 1                                      # an unacceptable year (RunType 0) with a detection that must be ignored
        weather.append(f"{rid},840,02,{k+1:03d},101,1990,6,1,0")
        rows.append(f"{rid},840,02,{k+1:03d},101,1990,00300,9,0,0,0,0,9,9")
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w") as z:
        z.writestr("States/Alabama.csv", "\n".join(rows))
    return "\n".join(routes), "\n".join(weather), zb


def test_ingest_and_cellset():
    r, w, zb = make_world()
    routes = bbs.read_routes(io.StringIO(r))
    assert len(routes) == 40 and routes.lat.iloc[0] == 35.0
    runs = bbs.acceptable_runs(io.StringIO(w))
    assert (runs.year == 1990).sum() == 0                  # RunType 0 dropped
    q = bbs.qualifying_routes(runs)
    assert q.qualifies.all() and (q.n1 == 12).all()
    det = bbs.detections(zb, runs, log=lambda *a: None)
    assert 300 not in set(det.AOU)                         # unacceptable survey ignored
    pres = bbs.route_presence(det)
    rq = routes.merge(q[q.qualifies], on=["country", "state", "route"])
    cs = bbs.species_cellset(rq, pres, 100)
    assert cs.obs1.sum() < cs.obs2.sum() and cs.obs1.sum() == 20 and cs.obs2.sum() == 28
    from ctw.species import hindcast as H
    o = H.observed_change(cs, n_boot=40)
    assert o["north"] > 0 and o["detectable"]
    cs200 = bbs.species_cellset(rq, pres, 200)
    assert cs200.obs1.all() and cs200.obs2.all()


def test_min_years_rule():
    r, w, zb = make_world(tmp_years1=range(1970, 1976))   # only 6 years in window 1
    runs = bbs.acceptable_runs(io.StringIO(w))
    assert not bbs.qualifying_routes(runs).qualifies.any()


def test_observed_table_runs():
    r, w, zb = make_world()
    routes = bbs.read_routes(io.StringIO(r)); runs = bbs.acceptable_runs(io.StringIO(w))
    q = bbs.qualifying_routes(runs)
    rq = routes.merge(q[q.qualifies], on=["country", "state", "route"])
    pres = bbs.route_presence(bbs.detections(zb, runs, log=lambda *a: None))
    sp = pd.DataFrame({"AOU": [100, 200], "english": ["a", "b"], "sci": ["A a", "B b"], "Order": ["", ""], "Family": ["", ""]})
    t = bbs.observed_table(rq, pres, sp, n_boot=20, min_routes=5, log=lambda *a: None)
    assert set(t.AOU) == {100, 200} and not t.eligible.any() and t.set_index("AOU").loc[100, "north"] > 0
