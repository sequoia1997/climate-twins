"""S3 batch 2: species table, routing with months for migrants, seasonal product, s2 inputs, extra target groups. Run: pytest tests/test_species_s3.py"""
import csv
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw.species import s2run, s3select, native as N, w2cells, inputs as IN, tg, project  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ROWS = list(csv.DictReader(open(ROOT / "data" / "species" / "batch2.csv", encoding="utf-8")))
SEL = [r for r in ROWS if r["status"] == "selected"]
SHORT = {r["scientific_name"]: r for r in csv.DictReader(open(ROOT / "data" / "species" / "shortlist_v1.csv", encoding="utf-8"))}


def _names(path, status=None):
    return {r["scientific_name"] for r in csv.DictReader(open(ROOT / "data" / "species" / path, encoding="utf-8")) if status is None or r["status"] == status}


def test_batch2_table_is_consistent():
    assert 95 <= len(SEL) <= 110
    assert len({r["id"] for r in ROWS}) == len(ROWS) and len({r["gbif_taxon_key"] for r in ROWS}) == len(ROWS)
    pilot = {r["scientific_name"] for r in csv.DictReader(open(ROOT / "data" / "species" / "pilot_v1.csv"))}
    b1 = _names("batch1.csv", "selected")
    assert not (pilot | b1) & {r["scientific_name"] for r in ROWS}                      # nothing from the pilot or batch 1
    assert not {"Azadirachta indica", "Tamarindus indica", "Cecropia peltata", "Pseudotsuga menziesii"} & {r["scientific_name"] for r in ROWS}      # gate failures are not retried
    assert _names("batch1.csv", "reserve") <= {r["scientific_name"] for r in SEL}       # the six batch-1 reserves are included
    for r in ROWS:
        s = SHORT[r["scientific_name"]]                                                 # the key and the name come from the shortlist (accepted GBIF match)
        assert r["gbif_taxon_key"] == s["gbif_taxon_key"]
    for r in SEL:
        assert r["iucn"] in ("LC", "NE") and r["dl_batch"]
        assert r["group"] in tg.S2_GROUP_TO_TG and r["group"] in project.DISPERSAL_KM_PER_DECADE or r["group"] in ("crop", "wild_plant", "tree", "bird", "mammal", "insect_arachnid")
        assert (r["kind"] == "crop") == (r["group"] == "crop")
        N.parse_spec(r["native_continents_curated"])
        assert IN.tiles_for(r["native_continents_curated"])
        if r["group"] == "bird":
            assert (ROOT / "data" / "species" / "batch2_evidence" / "shift" / f"{r['id']}.json").exists()
        if r["native_source"] == "curated":
            assert r["native_continents_curated"]
    big = {}
    for r in SEL:
        big[r["dl_batch"]] = big.get(r["dl_batch"], 0) + int(r["gbif_records_unfiltered"])
    assert all(v <= 24_000_000 or sum(1 for r in SEL if r["dl_batch"] == k) == 1 for k, v in big.items())
    for r in ROWS:
        if r["status"] == "reserve":
            assert r["scientific_name"] not in {x["scientific_name"] for x in SEL}


def test_every_animal_has_a_curated_row_with_second_pass():
    cur = {r["scientific_name"]: r for r in csv.DictReader(open(ROOT / "data" / "species" / "native" / "curated_native_v2.csv", encoding="utf-8"))}
    animals = [r for r in SEL if r["native_source"] == "curated"]
    assert animals and {r["scientific_name"] for r in animals} <= set(cur)        # the table also keeps rows for organisms dropped later (the fish)
    for r in animals:
        c = cur[r["scientific_name"]]
        assert c["native_spec"] == r["native_continents_curated"] and c["second_pass"] and c["second_pass"] != "CHECK" and c["introduced_or_migration_note"]
        assert bool(c["season_scheme"]) == bool(r["season"])
        if r["season"]:
            N.parse_spec(c["breeding_native_spec"]); N.parse_spec(c["winter_native_spec"])
            assert r["group"] == "bird"
        assert float(c["share_outside_mask"]) < 0.03 or c["second_pass"] != "consistent: GBIF record shares by continent all inside the curated continents"


def test_extra_target_groups_have_sql_and_mapping():
    for g in ("herp", "fish"):
        assert g in tg.EXTRA_GROUPS and "FROM occurrence WHERE" in tg.sql_for(g)
        assert g not in tg.GROUPS                                                       # the pilot's acquire stage is unchanged
    assert tg.S2_GROUP_TO_TG["reptile"] == tg.S2_GROUP_TO_TG["amphibian"] == "herp" and tg.S2_GROUP_TO_TG["fish"] == "fish"
    assert "Reptilia" in tg.sql_for("herp") and "Actinopterygii" in tg.sql_for("fish") and "Aves" in tg.sql_for("bird")


def _fake(n, key, seed, lat0, month=None):
    r = np.random.default_rng(seed)
    return pd.DataFrame({"gbifid": np.arange(n) + key * 1000, "decimallatitude": lat0 + r.uniform(0.01, 3, n) + 0.00317, "decimallongitude": 10 + r.uniform(0.01, 3, n) + 0.00291,
                         "year": r.integers(1975, 2020, n), "month": r.integers(1, 13, n) if month is None else month, "license": "CC0_1_0", "basisofrecord": "HUMAN_OBSERVATION",
                         "specieskey": key, "datasetkey": "d", "occurrenceid": [f"o{key}_{i}" for i in range(n)]})


def test_routing_keeps_months_only_for_migrants(tmp_path):
    a, b = _fake(300, 11, 1, 40.0), _fake(400, 22, 2, 45.0)
    pd.concat([a, b]).to_parquet(tmp_path / "x.parquet")
    rows = [{"gbif_taxon_key": "11", "group": "bird", "scientific_name": "A a", "season": "breeding"},
            {"gbif_taxon_key": "22", "group": "bird", "scientific_name": "B b", "season": ""}]
    cl, unmatched = s2run.route_and_clean(tmp_path, rows)
    assert unmatched == 0 and cl[11].keep_months and not cl[22].keep_months
    cells, _ = cl[11].finish()
    sea = cl[11].finish_seasonal("N")
    assert len(sea) == len(cells) and int(sea["n_breeding"].sum()) > 0 and {"m01", "m12", "n_winter", "m00"} <= set(sea.columns)


def test_species_inputs_reads_the_s2_product_with_seasonal_cells(tmp_path, monkeypatch):
    sci = "Turdus merula"
    df = pd.DataFrame({"species": sci, "row": [100, 101, 102], "col": [200, 201, 202], "year_max": [2001, 2010, 2015], "tg_group": "bird"})
    df.to_parquet(tmp_path / "s2_occ_cells_v1.parquet")
    sea = pd.DataFrame({"species": sci, "row": [100, 101, 102], "col": [200, 201, 202], "breeding_cell": [True, False, True], "n_breeding": [5, 0, 7]})
    sea.to_parquet(tmp_path / "s2_occ_cells_seasonal_v1.parquet")
    json.dump({sci: {"season_scheme": "N", "breeding_native_spec": "EUROPE", "cells_all": 3, "breeding_cells": 2, "records_breeding_months": 12, "records_without_month": 0}},
              open(tmp_path / "s2_w2_seasonal_report_v1.json", "w"))
    m = np.zeros((4320, 8640), bool); m[90:110, 190:210] = True
    np.save(tmp_path / "nat_dummy.npy", m)
    g = np.ones((3, 4320, 8640), np.float32)
    np.savez_compressed(tmp_path / "tg_density_bird_v1.npz", all=g[0], p1_1970_1999=g[1], p2_2000_2020=g[2])
    json.dump({"species": {sci: {"doi": "10.15468/dl.yyyyy"}}}, open(tmp_path / "s2_w2_report_v1.json", "w"))
    monkeypatch.setenv("W3_PRODUCT", "s2")
    monkeypatch.setattr(IN, "seasonal_mask", lambda spec, root: m)
    occ, native, density, dois = IN.species_inputs({"scientific_name": sci, "group": "bird"}, IN.SPEC, root=str(tmp_path), season="breeding")
    assert len(occ.rows) == 2 and native is not None and native[95, 195] and density is not None and dois == ["https://doi.org/10.15468/dl.yyyyy"]


def test_new_herp_and_fish_tg_grid_is_found_under_the_s2_name(tmp_path, monkeypatch):
    sci = "Rana temporaria"
    pd.DataFrame({"species": sci, "row": [100, 101], "col": [200, 201], "year_max": [2001, 2010], "tg_group": "herp"}).to_parquet(tmp_path / "s2_occ_cells_v1.parquet")
    g = np.full((4320, 8640), 3, np.float32)
    np.savez_compressed(tmp_path / "s2_tg_density_herp_v1.npz", all=g, p1_1970_1999=g, p2_2000_2020=g)
    monkeypatch.setenv("W3_PRODUCT", "s2")
    occ, native, density, dois = IN.species_inputs({"scientific_name": sci, "group": "amphibian"}, IN.SPEC, root=str(tmp_path))
    assert density is not None and float(density[0, 0]) == 3.0
