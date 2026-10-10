"""Unit tests for the W2 occurrence pipeline (ctw/species/w2cells.py, native.py, tg.py) on synthetic data. Run: pytest tests/test_species_w2.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw.species import native as N, tg, w2cells as W  # noqa: E402


def recs(rows):
    cols = ["gbifid", "decimallatitude", "decimallongitude", "year", "eventdate", "recordedby", "datasetkey", "occurrenceid", "establishmentmeans"]
    return pd.DataFrame(rows, columns=cols)


def test_grid_matches_climate_stack_convention():
    # row 0 = north, centre of cell (0, 0) = (89.979166.., -179.979166..) as in ctw/species/climategrid.py
    r, c = N.rc([89.99, -89.99], [-179.99, 179.99])
    assert (r[0], c[0]) == (0, 0) and (r[1], c[1]) == (4319, 8639)
    la, lo = N.centre(0, 0)
    assert abs(la - 89.979166667) < 1e-6 and abs(lo + 179.979166667) < 1e-6
    assert W.cell_index(89.99, -179.99) == 0 and W.cell_index(-89.99, 179.99) == 4320 * 8640 - 1


def test_duplicates_are_same_record_not_same_event():
    # three tagged butterflies, same place/date/recorder/dataset, different occurrenceIDs: kept as records, one event.
    # a fourth row repeats an occurrenceID: a true duplicate.
    rows = [(1, 40.51, -75.51, 1995, "1995", "Watch", "ds", "A1", None), (2, 40.51, -75.51, 1995, "1995", "Watch", "ds", "A2", None),
            (3, 40.51, -75.51, 1995, "1995", "Watch", "ds", "A3", None), (4, 40.51, -75.51, 1995, "1995", "Watch", "ds", "A3", None)]
    cc = W.CellCleaner()
    cc.feed(recs(rows))
    cells, rep = cc.finish()
    assert len(cells) == 1
    assert cells.n_records.iloc[0] == 3 and cells.n_events.iloc[0] == 1
    assert [s["removed"] for s in rep["steps"] if s["step"] == "duplicates"] == [1]


def test_periods_years_and_row_col():
    rows = [(1, 40.51, -75.51, 1980, "1980", "a", "d", "o1", None), (2, 40.512, -75.512, 2010, "2010", "b", "d", "o2", None),
            (3, 40.511, -75.511, 2023, "2023", "c", "d", "o3", None), (4, 10.51, 20.51, 1971, "1971", "c", "d", "o4", None)]
    cc = W.CellCleaner()
    cc.feed(recs(rows))
    cells, _ = cc.finish()
    a = cells[cells.lat > 40].iloc[0]
    assert (a.year_min, a.year_max, a.n_records) == (1980, 2023, 3)
    assert (a.n_1970_1999, a.n_2000_2020, a.n_2021_plus) == (1, 1, 1)
    r, c = N.rc(a.lat, a.lon)
    assert (r, c) == (a.row, a.col)


def test_establishment_means_dropped():
    rows = [(1, 40.51, -75.51, 1990, "1990", "a", "d", "o1", "INTRODUCED"), (2, 41.51, -75.51, 1990, "1990", "a", "d", "o2", "NATIVE"),
            (3, 42.51, -75.51, 1990, "1990", "a", "d", "o3", "MANAGED")]
    cc = W.CellCleaner()
    cc.feed(recs(rows))
    cells, rep = cc.finish()
    assert len(cells) == 1 and rep["establishment_dropped"] == {"INTRODUCED": 1, "MANAGED": 1}


def test_parse_spec():
    assert N.parse_spec("NORTH_AMERICA;ASIA(W);AFRICA(N);OCEANIA(N)") == [("NORTH_AMERICA", ""), ("ASIA", "W"), ("AFRICA", "N"), ("OCEANIA", "N")]
    with pytest.raises(ValueError):
        N.parse_spec("ATLANTIS")


def box(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def test_curated_mask_and_label_fill():
    feats = [{"geometry": box(-100, 30, -80, 50), "properties": {"CONTINENT": "North America", "NAME": "A"}},
             {"geometry": box(0, 40, 20, 60), "properties": {"CONTINENT": "Europe", "NAME": "B"}},
             {"geometry": box(130, -20, 150, 0), "properties": {"CONTINENT": "Oceania", "NAME": "C"}},
             {"geometry": box(130, -40, 150, -30), "properties": {"CONTINENT": "Oceania", "NAME": "D"}}]
    lab = N.label_raster(feats)
    m = N.curated_mask("NORTH_AMERICA", feats, lab)
    r, c = N.rc(40, -90); assert m[r, c]
    r, c = N.rc(50, 10); assert not m[r, c]
    r, c = N.rc(30.05, -90.0); assert m[r, c]                 # inside
    r, c = N.rc(29.95, -90.0); assert m[r, c]                 # just in the sea: filled from the nearest polygon (< 0.15 degrees)
    r, c = N.rc(29.5, -90.0); assert not m[r, c]              # too far from the coast
    mo = N.curated_mask("OCEANIA(N)", feats, lab)
    r, c = N.rc(-10, 140); assert mo[r, c]
    r, c = N.rc(-35, 140); assert not mo[r, c]


def test_target_group_grid_and_well_sampled():
    r = np.array([100, 101, 102, 500]); c = np.array([200, 200, 201, 700]); p = np.array([1, 2, 1, 1]); n = np.array([30, 25, 5, 100])
    g = tg.grid_from_rows(r, c, p, n)
    assert g.shape == (3, 4320, 8640) and g[0].sum() == 160 and g[1].sum() == 135 and g[2].sum() == 25
    lk = tg.lookup(g, [100, 500, 3000], [200, 700, 10])
    assert list(lk["ws20"]) == [True, False, False]           # first block has 35 and 25; second has no period 2 record
    assert not lk["ws100"][0]
    ws = tg.well_sampled(g)
    assert ws[100, 200] and ws[107, 203] and not ws[500, 700] and ws.sum() == 144


def test_griis_units_requires_explicit_introduced():
    feats = [{"properties": {"NAME": "Hawaii", "ADMIN": "United States of America", "ISO_A2_EH": "US"}},
             {"properties": {"NAME": "United States of America", "ADMIN": "United States of America", "ISO_A2_EH": "US"}},
             {"properties": {"NAME": "Australia", "ADMIN": "Australia", "ISO_A2_EH": "AU"}}]
    rows = [{"country": "US", "locality": "Hawaii", "establishmentMeans": "INTRODUCED", "status": "PRESENT"},
            {"country": "AU", "locality": None, "establishmentMeans": None, "status": "PRESENT"}]
    assert N.griis_units(rows, feats) == {0}


def test_crops_keep_cultivated_records_and_dataset_counts():
    rows = [(1, 40.51, -75.51, 1990, "1990", "a", "d1", "o1", "CULTIVATED"), (2, 41.51, -75.51, 1990, "1990", "a", "d2", "o2", "INTRODUCED")]
    cc = W.CellCleaner(keep_cultivated=True)
    cc.feed(recs(rows))
    cells, rep = cc.finish()
    assert len(cells) == 2 and rep["establishment_dropped"] == {} and cc.datasets == {"d1": 1, "d2": 1}
