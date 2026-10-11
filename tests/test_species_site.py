"""Data builder for the species pages (ctw/species_site.py) on real pilot outputs in tests/fixtures/species (sugar maple, kookaburra, American robin
breeding fit, plus the wine-grape summary alone for the crop wording). Run: pytest tests/test_species_site.py"""
import json, re
from pathlib import Path
import pytest

from ctw import species_site as SS

FIX = Path(__file__).parent / "fixtures" / "species"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("sd")
    idx = SS.build(FIX, out, log=lambda *a: None)
    return out, idx


def test_selection_rule_prefers_breeding_for_birds():
    chosen, skipped = SS.pick_runs(FIX)
    assert chosen["turdus_migratorius"][2] == "breeding" and chosen["acer_saccharum"][2] == "all"
    assert "vitis_vinifera" not in chosen and any("vitis_vinifera" in n for n, _ in skipped)       # summary without a CTS zip is never shown


def test_index_and_hashed_files(built):
    out, idx = built
    ids = {s["id"]: s for s in idx["species"]}
    assert set(ids) == {"acer_saccharum", "dacelo_novaeguineae", "turdus_migratorius"}
    assert idx["ssps"] == {"ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}
    r = ids["turdus_migratorius"]
    assert r["tier"] == "A" and r["range_shifts"] == "fail" and r["season"] == "breeding" and r["dois"] == ["https://doi.org/10.15468/dl.j78pf6"]
    w, s, e, n = r["bbox"]; assert -180 <= w < e <= 180 and -85 <= s < n <= 85
    for sid, rec in ids.items():
        for k, (path, size) in rec["files"].items():
            assert re.search(r"\.[0-9a-f]{10}\.cts$", path) and (out / path).stat().st_size == size
            assert (out / path).read_bytes()[:4] == b"CTS1"
        assert (out / rec["info"][0]).exists()


def test_withheld_numbers_carry_the_reason(built):
    out, idx = built
    rec = next(s for s in idx["species"] if s["id"] == "dacelo_novaeguineae")
    info = json.load(open(out / rec["info"][0]))
    assert info["withheld"] == {"ssp585|2100": info["withheld"]["ssp585|2100"]} and "novel climate" in info["withheld"]["ssp585|2100"]
    assert all(info["by"][f"ssp585|2100|{m}"].get("withheld") for m in SS.MODES) and "fut" not in info["by"]["ssp585|2100|unlimited"]
    assert info["by"]["ssp245|2100|unlimited"]["fut"] > 0


def test_place_table(built):
    out, idx = built
    pl = json.load(open(out / idx["places"][0]))
    assert len(pl["places"]) == len(SS.PLACES)
    for sid, d in pl["sp"].items():
        assert len(d) == 12 and all(len(v) == len(SS.PLACES) and set(v) <= set("01239") for v in d.values())
    assert set(pl["sp"]["dacelo_novaeguineae"]["ssp585|2100|none"]) == {"9"}
    i = [p[0] for p in pl["places"]].index("Sydney, Australia")
    assert pl["sp"]["dacelo_novaeguineae"]["ssp245|2050|unlimited"][i] == "2"                       # Sydney is kookaburra country now and later


def test_crop_wording_is_kept_verbatim():
    S = json.load(open(FIX / "w3_vitis_vinifera_summary.json"))
    info = SS.info_json(S, "all", ["ssp245"], [-10, 30, 40, 60], {})
    assert info["kind"] == "crop" and info["wording"].startswith("climate like where grapevines are recorded") and "not verified as cultivated" in info["wording"]


def test_s1_asset_names_and_prefix_stripping(tmp_path):
    import shutil
    for f in FIX.glob("w3_acer_saccharum_*"):
        shutil.copy(f, tmp_path / f.name.replace("w3_", "s1_w3_"))
    for f in FIX.glob("w3_turdus_migratorius_breeding_*"):
        shutil.copy(f, tmp_path / f.name.replace("w3_", "w3_"))
    chosen, _ = SS.pick_runs(tmp_path)
    assert set(chosen) == {"acer_saccharum", "turdus_migratorius"}


def test_centre_inside_the_range():
    import numpy as np
    m = np.zeros((4320, 8640), bool)
    m[1000:1100, 1000:1100] = True; m[1000:1100, 3000:3100] = True                # two separate regions
    lon = lambda j: -180 + j * 360 / 8640; lat = lambda i: 90 - i * 180 / 4320
    assert SS.centre_inside(m, lat(1050), lon(1050))
    assert not SS.centre_inside(m, lat(1050), lon(2050))                          # the midpoint between the regions is outside both


def test_real_centres_flagged(built):
    out, idx = built
    info = json.load(open(out / next(s for s in idx["species"] if s["id"] == "acer_saccharum")["info"][0]))
    flags = [v["cok"] for v in info["by"].values() if "cok" in v]
    assert flags and all(isinstance(f, bool) for f in flags) and info["by"]["ssp245|2050|unlimited"]["cok"] is True   # a compact range: centre inside it
