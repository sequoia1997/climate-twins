"""Records under the CC BY-NC licence (iNaturalist observers mostly choose it) for the organisms where they are a large share of what GBIF holds (data/species/nc_species.csv).
The site is educational and non-commercial, which that licence allows with attribution. Same filters as every other download except the licence; cleaned with the usual
cleaner except that introduced / naturalised / invasive records are kept (all-records fits). One to a few GBIF downloads; output nc_occ_cells_v1.parquet (species + the usual cell
columns) and nc_downloads_v1.json (DOIs for the credits). Run: python -m ctw.species.ncrun (GBIF credentials in the environment)."""
from __future__ import annotations
import csv, json, os, shutil, tempfile, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from . import gbif, w2cells, w2run as W

ROOT = Path(__file__).resolve().parents[2]
CAP = 15_000_000


def main() -> int:
    rows = list(csv.DictReader(open(ROOT / "data/species/nc_species.csv", encoding="utf-8")))
    bins, cur, n = [], [], 0
    for r in rows:
        k = int(r["nc_records"])
        if cur and n + k > CAP:
            bins.append(cur); cur, n = [], 0
        cur.append(r); n += k
    bins.append(cur)
    keys = []
    for b in bins:
        p = gbif.predicate(int(b[0]["gbif_taxon_key"]), licences=gbif.LICENCES_NC)
        p["predicates"][0] = {"type": "in", "key": "TAXON_KEY", "values": [r["gbif_taxon_key"] for r in b]}
        body = {"creator": os.environ["GBIF_USER"], "notificationAddresses": [os.environ["GBIF_EMAIL"]], "sendNotification": False, "format": "SIMPLE_PARQUET", "predicate": p}
        r = requests.post(f"{gbif.API}/occurrence/download/request", json=body, auth=gbif.auth(), timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"download request refused: HTTP {r.status_code}")
        keys.append(r.text.strip().strip('"')); print("requested", keys[-1], len(b), "species", flush=True)
    ref, land = W.ref_set()
    out, dls = [], []
    for key, b in zip(keys, bins):
        s = gbif.wait(key)
        if s["status"] != "SUCCEEDED":
            raise RuntimeError(f"download {key} ended as {s['status']}")
        print("download", key, "records", s.get("totalRecords"), "doi", s.get("doi"), flush=True)
        dls.append(dict(key=key, doi=s.get("doi"), records=s.get("totalRecords")))
        tmp = Path(tempfile.mkdtemp())
        z = W.fetch_zip(s["downloadLink"], tmp)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(tmp)
        z.unlink()
        names = {r["scientific_name"]: w2cells.CellCleaner(land=land, ref=ref, keep_introduced=True) for r in b}
        for d in w2cells.read_batches(tmp, extra=("specieskey", "taxonkey", "species")):        # GBIF keys are short codes now: match on the species name
            sp = d["species"].astype("string").fillna("").to_numpy() if "species" in d else np.full(len(d), "")
            for nm, c in names.items():
                m = sp == nm
                if m.any():
                    c.feed(d[m])
        shutil.rmtree(tmp, ignore_errors=True)
        for nm, c in names.items():
            cells, rep = c.finish()
            if len(cells):
                out.append(cells.assign(species=nm))
        print("cleaned", len(names), "species", flush=True)
    if not out:
        raise RuntimeError("no cells for any species")
    df = pd.concat(out, ignore_index=True)
    df.to_parquet("nc_occ_cells_v1.parquet", compression="zstd", index=False)
    json.dump(dls, open("nc_downloads_v1.json", "w"))
    print("species with cells", df["species"].nunique(), "cells", len(df), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
