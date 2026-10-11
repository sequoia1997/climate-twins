"""S1 batch 1: the species table, the multi-species download split, the OCEANIA(AU) region and the s1 input product. Run: pytest tests/test_species_s1.py"""
import csv
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw.species import s1run, native as N, w2cells, inputs as IN, tg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ROWS = list(csv.DictReader(open(ROOT / "data" / "species" / "batch1.csv", encoding="utf-8")))
SEL = [r for r in ROWS if r["status"] == "selected"]


def test_batch_table_is_consistent():
    assert len(SEL) == 35
    assert len({r["id"] for r in ROWS}) == len(ROWS) and len({r["gbif_taxon_key"] for r in ROWS}) == len(ROWS)
    pilot = {r["scientific_name"] for r in csv.DictReader(open(ROOT / "data" / "species" / "pilot_v1.csv"))}
    assert not pilot & {r["scientific_name"] for r in ROWS}                       # nothing from the pilot
    for r in SEL:
        assert r["group"] in tg.PILOT_GROUP_TO_TG                                  # every group has a pilot target-group grid (no herp / fish in batch 1)
        assert r["iucn"] in ("LC", "NE") and r["dl_batch"]
        assert (r["kind"] == "crop") == (r["group"] == "crop")
        N.parse_spec(r["native_continents_curated"])                               # grammar accepted
        assert IN.tiles_for(r["native_continents_curated"])
        if r["group"] == "bird":
            assert (ROOT / "data" / "species" / "batch1_evidence" / "shift" / f"{r['id']}.json").exists()
    assert sum(r["group"] == "crop" for r in SEL) in (2, 3)
    assert all(r["status"] in ("selected", "reserve") for r in ROWS)
    big = {}
    for r in SEL:
        big[r["dl_batch"]] = big.get(r["dl_batch"], 0) + int(r["gbif_records_unfiltered"])
    assert max(big.values()) < 25_000_000                                          # the 25 M record cap per download


def test_oceania_au_region_is_australia_only():
    assert N.parse_spec("OCEANIA(AU)") == [("OCEANIA", "AU")]
    aus = {"CONTINENT": "Oceania", "ADM0_A3": "AUS"}
    assert N.unit_matches(aus, ("OCEANIA", "AU")) == (True, False)
    assert N.unit_matches({"CONTINENT": "Oceania", "ADM0_A3": "NZL"}, ("OCEANIA", "AU"))[0] is False
    assert N.unit_matches({"CONTINENT": "Oceania", "ADM0_A3": "PNG"}, ("OCEANIA", "AU"))[0] is False
    assert N.unit_matches({"CONTINENT": "Asia", "ADM0_A3": "AUS"}, ("OCEANIA", "AU"))[0] is False


def test_multi_species_predicate_keeps_the_pilot_filters():
    p = s1run.predicate_multi([1, 2, 3])
    first = p["predicates"][0]
    assert first == {"type": "in", "key": "TAXON_KEY", "values": ["1", "2", "3"]}
    from ctw.species import gbif
    one = gbif.predicate(7)
    assert p["predicates"][1:] == one["predicates"][1:]


def _fake(n, key, seed, lat0):
    r = np.random.default_rng(seed)
    return pd.DataFrame({"gbifid": np.arange(n) + key * 1000, "decimallatitude": lat0 + r.uniform(0.01, 3, n) + 0.00317, "decimallongitude": 10 + r.uniform(0.01, 3, n) + 0.00291,
                         "year": r.integers(1975, 2020, n), "month": r.integers(1, 13, n), "license": "CC0_1_0", "basisofrecord": "HUMAN_OBSERVATION",
                         "specieskey": key, "datasetkey": "d", "occurrenceid": [f"o{key}_{i}" for i in range(n)]})


def test_split_download_equals_separate_cleaning(tmp_path):
    a, b = _fake(300, 11, 1, 40.0), _fake(500, 22, 2, 45.0)
    noise = _fake(40, 99, 3, 50.0)                                                # a record that belongs to none of the species
    both = pd.concat([a, noise, b], ignore_index=True).sample(frac=1, random_state=0)
    both.to_parquet(tmp_path / "x.parquet")
    rows = [{"gbif_taxon_key": "11", "group": "bird", "scientific_name": "A a"}, {"gbif_taxon_key": "22", "group": "crop", "scientific_name": "B b"}]
    cl, unmatched = s1run.route_and_clean(tmp_path, rows)
    assert unmatched == 40
    for k, solo in ((11, a), (22, b)):
        ref = w2cells.CellCleaner(keep_cultivated=(k == 22))
        ref.feed(solo)
        c1, r1 = cl[k].finish()
        c2, r2 = ref.finish()
        pd.testing.assert_frame_equal(c1, c2)
        assert r1["steps"] == r2["steps"]


def test_split_falls_back_to_the_species_name_column(tmp_path):
    a, b = _fake(100, 11, 1, 40.0), _fake(120, 22, 2, 45.0)
    a["species"], b["species"] = "A a", "B b"
    pd.concat([a, b]).drop(columns=["specieskey"]).to_parquet(tmp_path / "x.parquet")
    rows = [{"gbif_taxon_key": "11", "group": "bird", "scientific_name": "A a"}, {"gbif_taxon_key": "22", "group": "bird", "scientific_name": "B b"}]
    cl, unmatched = s1run.route_and_clean(tmp_path, rows)
    assert unmatched == 0 and cl[11].finish()[1]["n_cells"] > 0 and cl[22].finish()[1]["n_cells"] > 0


def test_species_inputs_reads_the_s1_product(tmp_path, monkeypatch):
    sci = "Pica pica"
    df = pd.DataFrame({"species": sci, "row": [100, 101, 102], "col": [200, 201, 202], "year_max": [2001, 2010, 2015], "tg_group": "bird"})
    df.to_parquet(tmp_path / "s1_occ_cells_v1.parquet")
    m = np.zeros((4320, 8640), bool); m[90:110, 190:210] = True
    np.savez_compressed(tmp_path / "s1_native_masks_v1.npz", **{"Pica_pica__final": np.packbits(m, axis=1)})
    g = np.ones((3, 4320, 8640), np.float32)
    np.savez_compressed(tmp_path / "tg_density_bird_v1.npz", all=g[0], p1_1970_1999=g[1], p2_2000_2020=g[2])
    json.dump({"species": {sci: {"doi": "10.15468/dl.xxxxx"}}}, open(tmp_path / "s1_w2_report_v1.json", "w"))
    monkeypatch.setenv("W3_PRODUCT", "s1")
    occ, native, density, dois = IN.species_inputs({"scientific_name": sci, "group": "bird"}, IN.SPEC, root=str(tmp_path))
    assert len(occ.rows) == 3 and native is not None and native[95, 195] and not native[0, 0]
    assert density is not None and dois == ["https://doi.org/10.15468/dl.xxxxx"]
