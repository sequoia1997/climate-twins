"""Download predicate for the GBIF client (ctw/species/gbif.py); no network. Run: pytest tests/test_species_gbif.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw.species import gbif  # noqa: E402


def test_predicate_has_every_filter_and_only_open_licences():
    p = gbif.predicate(3189834)
    keys = [x.get("key") or x.get("type") for x in p["predicates"]]
    assert p["type"] == "and"
    for k in ("TAXON_KEY", "HAS_COORDINATE", "HAS_GEOSPATIAL_ISSUE", "OCCURRENCE_STATUS", "LICENSE", "YEAR", "BASIS_OF_RECORD", "or"):
        assert k in keys
    lic = next(x for x in p["predicates"] if x.get("key") == "LICENSE")
    assert lic["values"] == ["CC0_1_0", "CC_BY_4_0"]
    assert next(x for x in p["predicates"] if x.get("key") == "YEAR")["value"] == "1970"


def test_predicate_without_uncertainty_limit():
    assert all(x["type"] != "or" for x in gbif.predicate(1, max_unc_m=0)["predicates"])


def test_pilot_list():
    assert len(gbif.PILOT) == 7 and {k for _, _, k in gbif.PILOT} == {"tree", "animal", "crop"}
