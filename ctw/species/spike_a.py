"""Spike A runner (GitHub Actions only: it talks to api.gbif.org). Steps: login | probe | download | clean.
  python -m ctw.species.spike_a login       one authenticated call; prints only the HTTP status
  python -m ctw.species.spike_a probe       taxonKeys and licence / basis / year facet counts for the pilot species (no login)
  python -m ctw.species.spike_a download    request, wait for, fetch and clean one download per species; writes work/spike-a/*.json
Secrets are read from the environment by gbif.py and never printed."""
from __future__ import annotations
import glob, io, json, os, sys, time, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from . import gbif, occ
from .. import common as C

OUT = Path(os.environ.get("SPIKE_OUT", "work/spike-a"))
COLS = ["decimallatitude", "decimallongitude", "coordinateuncertaintyinmeters", "countrycode", "eventdate", "recordedby",
        "datasetkey", "establishmentmeans", "basisofrecord", "license", "year", "specieskey", "taxonkey"]


def dump(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=1, default=str))


def login() -> int:
    r = requests.get(f"{gbif.API}/user/login", auth=gbif.auth(), timeout=60)
    print("login HTTP", r.status_code)
    if r.status_code == 401:
        print("GBIF rejected GBIF_USER / GBIF_PWD (use the GBIF username, not the email address, and the account password)")
    out = {"status": r.status_code, "email_secret_set": bool(os.environ.get("GBIF_EMAIL"))}
    dump("login.json", out)
    return 0 if r.status_code == 200 else 1


def probe() -> int:
    res = []
    for sci, common, kind in gbif.PILOT:
        m = gbif.match(sci)
        key = m.get("usageKey")
        row = {"name": sci, "common": common, "kind": kind, "taxonKey": key, "matchType": m.get("matchType"),
               "status": m.get("status"), "rank": m.get("rank"), "acceptedKey": m.get("acceptedUsageKey")}
        base = {"hasCoordinate": "true", "hasGeospatialIssue": "false", "occurrenceStatus": "PRESENT", "year": "1970,*"}
        row["all_records"] = gbif.facet_counts(key, "LICENSE")["total"]
        row["licence_all"] = gbif.facet_counts(key, "LICENSE", **base)
        row["licence_by_basis"] = {}
        for lic in ["CC0_1_0", "CC_BY_4_0", "CC_BY_NC_4_0"]:
            row["licence_by_basis"][lic] = gbif.facet_counts(key, "BASIS_OF_RECORD", license=lic, **base)
        row["basis_all_licences"] = gbif.facet_counts(key, "BASIS_OF_RECORD", **base)
        row["establishment"] = gbif.facet_counts(key, "ESTABLISHMENT_MEANS", license=["CC0_1_0", "CC_BY_4_0"], **base)
        res.append(row)
        print(sci, key, row["matchType"], row["licence_all"]["total"], flush=True)
    dump("probe.json", res)
    return 0


def fetch(link: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    f = dest / "dl.zip"
    with requests.get(link, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(f, "wb") as o:
            for ch in r.iter_content(1 << 22):
                o.write(ch)
    try:
        with zipfile.ZipFile(f) as z:
            z.extractall(dest)
        f.unlink()
    except zipfile.BadZipFile:
        f.rename(dest / "dl.parquet")
    return dest


def read_batches(folder: Path):
    import pyarrow.parquet as pq
    files = sorted(glob.glob(str(folder / "**" / "*.parquet"), recursive=True)) + sorted(glob.glob(str(folder / "**" / "0*"), recursive=True))
    files = [f for f in dict.fromkeys(files) if os.path.isfile(f)]
    if files:
        for f in files:
            pf = pq.ParquetFile(f)
            have = {n.lower(): n for n in pf.schema_arrow.names}
            for b in pf.iter_batches(batch_size=2_000_000, columns=[have[c] for c in COLS if c in have]):
                d = b.to_pandas()
                d.columns = [c.lower() for c in d.columns]
                yield d
        return
    for f in sorted(glob.glob(str(folder / "**" / "*.csv"), recursive=True)):   # SIMPLE_CSV fallback (tab separated)
        for d in pd.read_csv(f, sep="\t", chunksize=2_000_000, quoting=3, on_bad_lines="skip", low_memory=False):
            d.columns = [c.lower() for c in d.columns]
            yield d[[c for c in COLS if c in d.columns]]


def continents(cfg) -> dict:
    gj = json.load(open(C.download(cfg["sources"]["natural_earth"], C.work("downloads", "ne_50m_countries.geojson"))))
    out = {}
    for f in gj["features"]:
        p = f["properties"]
        for k in ("ISO_A2_EH", "ISO_A2"):
            if p.get(k) and p[k] != "-99":
                out.setdefault(p[k], p.get("CONTINENT") or "Unknown")
    return out, gj


def institutions() -> pd.DataFrame:
    rows, off = [], 0
    try:
        while off < 20000:
            d = requests.get(f"{gbif.API}/grscicoll/institution", params={"limit": 1000, "offset": off}, timeout=120).json()
            for x in d.get("results", []):
                la, lo = x.get("latitude"), x.get("longitude")
                if la is None:
                    a = x.get("address") or x.get("mailingAddress") or {}
                    la, lo = a.get("latitude"), a.get("longitude")
                if la is not None and lo is not None:
                    rows.append((float(la), float(lo)))
            if d.get("endOfRecords", True):
                break
            off += 1000
    except Exception as e:                                               # optional input: the step then runs with centroids and capitals only
        print("institutions unavailable:", type(e).__name__)
    return pd.DataFrame(rows, columns=["lat", "lon"])


def download_and_clean() -> int:
    cfg = C.config()
    kf = C.ROOT / ".github" / "run" / "spike-a-keys.json"                # keys of downloads already requested (reuse, do not repeat)
    keys_in = json.loads(os.environ.get("DOWNLOAD_KEYS") or (kf.read_text() if kf.exists() else "{}"))        # reuse earlier downloads: {"Acer saccharum": "0001234-..."}
    probe_file = OUT / "probe.json"
    taxa = {r["name"]: r["taxonKey"] for r in json.load(open(probe_file))} if probe_file.exists() else {s: gbif.match(s)["usageKey"] for s, _, _ in gbif.PILOT}
    t0 = time.time()
    keys = {}
    cont, gj = continents(cfg)
    inst = institutions()
    ref = occ.reference_points(C.ROOT / "data" / "world_targets.csv", gj, inst)
    print("reference points", ref["kind"].value_counts().to_dict(), flush=True)
    land = occ.land_mask_default()
    results, pending = {}, {}
    queue = [sci for sci, _, _ in gbif.PILOT]
    while pending or queue:
        for sci in list(queue):                                          # GBIF allows 3 simultaneous downloads per user (HTTP 420 beyond)
            if len(pending) >= 3 and sci not in keys_in:
                break
            try:
                keys[sci] = keys_in.get(sci) or gbif.request_download(taxa[sci])
            except RuntimeError as e:
                if "420" in str(e):
                    break
                raise
            pending[sci] = keys[sci]
            queue.remove(sci)
            dump("download_keys.json", keys)
            print("requested", sci, keys[sci], f"t+{round(time.time() - t0)}s", flush=True)
        for sci, key in list(pending.items()):
            s = gbif.status(key)
            if s["status"] in ("PREPARING", "RUNNING", "SUSPENDED"):
                continue
            del pending[sci]
            row = {"key": key, "status": s["status"], "doi": s.get("doi"), "records": s.get("totalRecords"), "size_bytes": s.get("size"),
                   "created": s.get("created"), "modified": s.get("modified"), "format": (s.get("request") or {}).get("format"),
                   "licence": s.get("license"), "link": s.get("downloadLink"), "wall_s_since_submit": round(time.time() - t0),
                   "citation": gbif.citation(key, s)}
            if s["status"] == "SUCCEEDED":
                dest = fetch(s["downloadLink"], Path(os.environ.get("SPIKE_TMP", "/tmp/spike-a")) / sci.replace(" ", "_"))
                kind = dict((a, k) for a, _, k in gbif.PILOT)[sci]
                cl = occ.Cleaner(kind=kind, land=land, ref=ref, establishment="drop" if kind != "animal" else "off")
                lic, bas = {}, {}
                for d in read_batches(dest):
                    for col, acc in (("license", lic), ("basisofrecord", bas)):
                        if col in d:
                            for k, v in d[col].value_counts().items():
                                acc[k] = acc.get(k, 0) + int(v)
                    cl.feed(d)
                out = cl.finish()
                row.update({"licences_in_file": lic, "basis_in_file": bas, "cleaning": cl.report(),
                            "continents_after": occ.continent_counts(out, cont),
                            "countries_after": int(out["countrycode"].nunique()) if "countrycode" in out else None})
                out.to_csv(OUT / f"thinned_{sci.replace(' ', '_')}.csv.gz", index=False, compression="gzip")
                os.system(f"rm -rf '{dest}'")
            results[sci] = row
            dump("results.json", results)
            print("done", sci, row["status"], row.get("records"), flush=True)
        if pending:
            time.sleep(30)
    return 0


if __name__ == "__main__":
    sys.exit({"login": login, "probe": probe, "download": download_and_clean}[sys.argv[1]]())
