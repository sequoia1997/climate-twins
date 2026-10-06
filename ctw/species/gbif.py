"""Minimal GBIF API client for the occurrence spike: species match, facet counts, download requests, polling and fetching.
Credentials come only from the environment (GBIF_USER, GBIF_PWD, GBIF_EMAIL) and are never printed or logged. Run it only where
api.gbif.org is reachable (GitHub Actions). Used by ctw/species/spike_a.py."""
from __future__ import annotations
import os, time
import requests

API = "https://api.gbif.org/v1"
LICENCES_OK = ["CC0_1_0", "CC_BY_4_0"]
BASIS_OK = ["HUMAN_OBSERVATION", "PRESERVED_SPECIMEN", "OBSERVATION", "MACHINE_OBSERVATION"]
PILOT = [("Acer saccharum", "sugar maple", "tree"), ("Quercus robur", "English oak", "tree"),
         ("Danaus plexippus", "monarch", "animal"), ("Turdus migratorius", "American robin", "animal"),
         ("Erithacus rubecula", "European robin", "animal"), ("Ixodes scapularis", "blacklegged tick", "animal"),
         ("Vitis vinifera", "wine grape", "crop")]


def auth():
    return (os.environ["GBIF_USER"], os.environ["GBIF_PWD"])


def get(path, **params):
    r = requests.get(f"{API}{path}", params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def match(name: str) -> dict:
    return get("/species/match", name=name, strict="true", verbose="false")


def predicate(taxon_key: int, licences=LICENCES_OK, basis=BASIS_OK, year_min=1970, max_unc_m=10_000) -> dict:
    """The download filter. Missing coordinate uncertainty is allowed (most records have none); the cleaning step treats it the same."""
    p = [{"type": "equals", "key": "TAXON_KEY", "value": str(taxon_key)},
         {"type": "equals", "key": "HAS_COORDINATE", "value": "true"},
         {"type": "equals", "key": "HAS_GEOSPATIAL_ISSUE", "value": "false"},
         {"type": "equals", "key": "OCCURRENCE_STATUS", "value": "PRESENT"},
         {"type": "in", "key": "LICENSE", "values": list(licences)},
         {"type": "greaterThanOrEquals", "key": "YEAR", "value": str(year_min)},
         {"type": "in", "key": "BASIS_OF_RECORD", "values": list(basis)}]
    if max_unc_m:
        p.append({"type": "or", "predicates": [
            {"type": "isNull", "parameter": "COORDINATE_UNCERTAINTY_IN_METERS"},
            {"type": "lessThanOrEquals", "key": "COORDINATE_UNCERTAINTY_IN_METERS", "value": str(max_unc_m)}]})
    return {"type": "and", "predicates": p}


def facet_counts(taxon_key: int, facet: str, **filters) -> dict:
    """Counts per facet value (e.g. LICENSE) for a taxon under extra occurrence-search filters."""
    d = get("/occurrence/search", taxonKey=taxon_key, limit=0, facet=facet, facetLimit=50, **filters)
    f = d.get("facets", [])
    return {"total": d["count"], "values": {c["name"]: c["count"] for x in f for c in x["counts"]}}


def request_download(taxon_key: int, fmt="SIMPLE_PARQUET", **pred_kw) -> str:
    body = {"creator": os.environ["GBIF_USER"], "notificationAddresses": [os.environ["GBIF_EMAIL"]], "sendNotification": False,
            "format": fmt, "predicate": predicate(taxon_key, **pred_kw)}
    r = requests.post(f"{API}/occurrence/download/request", json=body, auth=auth(), timeout=120)
    if r.status_code >= 400:
        # do not echo the request body (it holds the address); the response says what was wrong
        raise RuntimeError(f"download request refused: HTTP {r.status_code} {r.text[:500]}")
    return r.text.strip().strip('"')


def status(key: str) -> dict:
    return get(f"/occurrence/download/{key}")


def wait(key: str, every=30, limit_s=4 * 3600) -> dict:
    t0 = time.time()
    while True:
        s = status(key)
        if s["status"] in ("SUCCEEDED", "FAILED", "CANCELLED", "KILLED", "FILE_ERASED"):
            s["_waited_s"] = time.time() - t0
            return s
        if time.time() - t0 > limit_s:
            s["_waited_s"] = time.time() - t0
            return s
        time.sleep(every)


def citation(key: str, s: dict) -> str:
    """GBIF's own citation text if the API gives one, otherwise the documented pattern."""
    try:
        r = requests.get(f"{API}/occurrence/download/{key}/citation", timeout=60)
        if r.ok and r.text.strip():
            return r.text.strip()
    except requests.RequestException:
        pass
    day = (s.get("created") or "")[:10]
    return f"GBIF.org ({day}) GBIF Occurrence Download https://doi.org/{s.get('doi')}"
