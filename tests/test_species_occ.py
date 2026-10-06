"""Unit tests for the occurrence cleaning (ctw/species/occ.py) on synthetic records. Run: pytest tests/test_species_occ.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw.species import occ  # noqa: E402


def recs(rows):
    cols = ["decimallatitude", "decimallongitude", "coordinateuncertaintyinmeters", "countrycode", "eventdate", "recordedby", "establishmentmeans"]
    return pd.DataFrame(rows, columns=cols[:len(rows[0])])


def land_everywhere():
    return np.ones((360, 720), bool)


def test_cell_id_is_2p5_arcmin_and_roundtrips():
    cid = occ.cell_id([0.001, 0.001 + 2.5 / 60], [0.001, 0.001])
    assert cid[1] - cid[0] == occ.NCOL
    la, lo = occ.cell_center(cid[0])
    assert abs(la - 0.001) < 2.5 / 60 and abs(lo - 0.001) < 2.5 / 60
    assert occ.cell_id(90, 180) == occ.NROW * occ.NCOL - 1          # edges stay in range


def test_coordinate_sanity():
    df = recs([(45.5, 10.5, None), (0.0, 0.0, None), (91, 10.5, None), (12.3, 12.3, None), (np.nan, 3.1, None),
               (40.0, 20.0, None), (30.5, 200.5, None), (35.31, -80.22, None)])
    out, rep = occ.clean(df)
    assert sorted(zip(out["lat"], out["lon"])) == [(35.31, -80.22), (45.5, 10.5)]
    assert rep[0] == {"step": "input", "left": 8, "removed": 0}
    assert rep[1]["left"] == 2


def test_uncertainty_keeps_missing_and_drops_large():
    df = recs([(45.5, 10.5, 50.0), (46.5, 11.5, 20000.0), (47.5, 12.5, None)])
    out, _ = occ.clean(df, max_unc_m=10_000)
    assert len(out) == 2 and 46.5 not in set(out["lat"])


def test_centroid_radius_rule_by_kind():
    ref = pd.DataFrame({"lat": [50.0, 10.0, 20.0], "lon": [8.0, 20.0, 30.0], "kind": ["country", "capital", "institution"]})
    d_km = lambda km: km / 111.19                    # degrees of latitude
    df = recs([(50.0 + d_km(0.5), 8.0, None),         # inside the 1 km country radius: dropped
               (50.0 + d_km(3.0), 8.0, None),         # outside: kept
               (10.0 + d_km(1.5), 20.0, None),        # inside 2 km capital radius: dropped
               (10.0 + d_km(5.0), 20.0, None),        # kept
               (20.0 + d_km(0.05), 30.0, None),       # inside 100 m institution radius: dropped
               (20.0 + d_km(0.5), 30.0, None)])       # kept
    out, rep = occ.clean(df, ref=ref)
    assert len(out) == 3 and rep[3]["removed"] == 3
    assert occ.near_reference([1.0], [1.0], None).tolist() == [False]


def test_land_step_drops_ocean_points_and_keeps_coastal_neighbours():
    m = np.zeros((360, 720), bool)
    m[(90 - 45 - 1) * 2:(90 - 45) * 2, 0:2] = False
    r, c = int((90 - 45.25) / 0.5), int((10.25 + 180) / 0.5)
    m[r, c] = True                                    # one land cell around (45.25, 10.25)
    df = recs([(45.25, 10.25, None), (45.6, 10.25, None), (-30.5, -150.5, None)])
    out, rep = occ.clean(df, land=m)
    assert len(out) == 2                              # the one in the cell and its northern neighbour; mid-Pacific point dropped
    assert rep[4]["removed"] == 1


def test_establishment_modes():
    df = recs([(45.5, 10.5, None, "IT", "2020-01-01", "a", "NATIVE"), (46.5, 11.5, None, "IT", "2020-01-02", "a", "MANAGED"),
               (47.5, 12.5, None, "IT", "2020-01-03", "a", "introduced"), (48.5, 13.5, None, "IT", "2020-01-04", "a", None)])
    out, _ = occ.clean(df, kind="tree")
    assert sorted(out["lat"]) == [45.5, 48.5]
    v = recs([(45.5, 10.5, None, "IT", "2020-01-01", "a", "introducedAssistedColonisation"), (46.5, 11.5, None, "IT", "2020-01-02", "a", "nativeReintroduced")])
    assert len(occ.clean(v, kind="tree")[0]) == 1                  # GBIF's camelCase vocabulary values
    out, _ = occ.clean(df, kind="tree", drop_introduced=False)
    assert len(out) == 3
    out, _ = occ.clean(df, kind="crop", establishment="flag")
    assert len(out) == 4 and int(out["escaped"].sum()) == 2
    out, _ = occ.clean(df, kind="animal")             # animals: step off
    assert len(out) == 4


def test_duplicates_only_when_everything_matches():
    base = (45.5, 10.5, None, "IT", "2020-05-05", "smith", None)
    df = recs([base, base, (45.5, 10.5, None, "IT", "2020-05-06", "smith", None)])
    c = occ.Cleaner()
    c.feed(df)
    out = c.finish()
    rep = {r["step"]: r for r in c.report()}
    assert rep["duplicates"]["removed"] == 1 and rep["duplicates"]["left"] == 2
    assert len(out) == 1                              # thinned to one cell afterwards


def test_thinning_keeps_best_uncertainty_one_per_cell_across_chunks():
    c = occ.Cleaner()
    c.feed(recs([(45.5001, 10.5001, 500.0, "IT", "2020-01-01", "a", None), (45.5002, 10.5002, 20.0, "IT", "2020-01-02", "b", None)]))
    c.feed(recs([(45.5003, 10.5003, None, "IT", "2020-01-03", "c", None), (52.5, 13.5, None, "DE", "2020-01-04", "c", None)]))
    out = c.finish()
    assert len(out) == 2
    kept = out[out["lat"] < 50].iloc[0]
    assert kept["unc"] == 20.0
    rep = {r["step"]: r for r in c.report()}
    assert rep["input"]["left"] == 4 and rep["thin"]["left"] == 2 and rep["thin"]["removed"] == 2


def test_chunked_equals_one_shot():
    rng = np.random.default_rng(3)
    n = 500
    df = pd.DataFrame({"decimallatitude": rng.uniform(-50, 60, n), "decimallongitude": rng.uniform(-120, 120, n),
                       "coordinateuncertaintyinmeters": rng.choice([np.nan, 30.0, 5000.0, 50000.0], n),
                       "countrycode": "XX", "eventdate": "2020-01-01", "recordedby": "r"})
    one, rep1 = occ.clean(df)
    c = occ.Cleaner()
    for i in range(0, n, 70):
        c.feed(df.iloc[i:i + 70])
    two = c.finish()
    assert rep1 == c.report() and len(one) == len(two)


def test_empty_input_and_continent_counts():
    out, rep = occ.clean(recs([(0.0, 0.0, None)]))
    assert len(out) == 0 and rep[-1]["left"] == 0
    d = pd.DataFrame({"countrycode": ["US", "US", "FR", None, "ZZ"]})
    assert occ.continent_counts(d, {"US": "North America", "FR": "Europe"}) == {"North America": 2, "Unknown": 2, "Europe": 1}


def test_reference_points_from_capitals_and_geojson(tmp_path):
    p = tmp_path / "w.csv"
    p.write_text("label,country,country_name,admin1,lat,lon,pop,capital\nA,AA,Aa,x,1.5,2.5,10,True\nB,AA,Aa,x,3.5,4.5,10,False\n")
    gj = {"features": [{"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [4, 0], [4, 2], [0, 2], [0, 0]]]}}]}
    ref = occ.reference_points(p, gj, pd.DataFrame({"lat": [9.0], "lon": [9.0]}))
    assert sorted(ref["kind"]) == ["capital", "country", "institution"]
    c = ref[ref["kind"] == "country"].iloc[0]
    assert abs(c["lat"] - 1.0) < 1e-9 and abs(c["lon"] - 2.0) < 1e-9
