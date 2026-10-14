"""Records GBIF tags as introduced / naturalised / invasive, for the organisms where they are at least 5 percent of the records (data/species/intro_species.csv).
One small GBIF download (only those tagged records, same licence / year / coordinate filters), cleaned with the usual cleaner except that these tags are kept
(managed, cultivated and vagrant records are still dropped). Output: intro_occ_cells_v1.parquet (species + the usual cell columns), added to all-records fits by
ctw.species.inputs. Run: python -m ctw.species.introrun  (GBIF_USER, GBIF_EMAIL and the GBIF password in the environment; needs network)."""
from __future__ import annotations
import csv, os, shutil, tempfile, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from . import gbif, w2cells, w2run as W

ROOT = Path(__file__).resolve().parents[2]
TAGS = ["introduced", "introducedAssistedColonisation", "naturalised", "invasive"]          # GBIF vocabulary values are camel-case; upper-case matches nothing


def main() -> int:
    rows = list(csv.DictReader(open(ROOT / "data/species/intro_species.csv", encoding="utf-8")))
    keys = [int(r["gbif_taxon_key"]) for r in rows]
    p = gbif.predicate(keys[0])
    p["predicates"][0] = {"type": "in", "key": "TAXON_KEY", "values": [str(k) for k in keys]}
    p["predicates"].append({"type": "in", "key": "ESTABLISHMENT_MEANS", "values": TAGS})
    body = {"creator": os.environ["GBIF_USER"], "notificationAddresses": [os.environ["GBIF_EMAIL"]], "sendNotification": False, "format": "SIMPLE_PARQUET", "predicate": p}
    r = requests.post(f"{gbif.API}/occurrence/download/request", json=body, auth=gbif.auth(), timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"download request refused: HTTP {r.status_code}")
    key = r.text.strip().strip('"')
    print("requested", key, flush=True)
    s = gbif.wait(key)
    if s["status"] != "SUCCEEDED":
        raise RuntimeError(f"download {key} ended as {s['status']}")
    tmp = Path(tempfile.mkdtemp())
    z = W.fetch_zip(s["downloadLink"], tmp)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(tmp)
    z.unlink()
    print("download records:", s.get("totalRecords"), "doi", s.get("doi"), flush=True)
    ref, land = W.ref_set()
    cc = {int(r["gbif_taxon_key"]): w2cells.CellCleaner(land=land, ref=ref, keep_introduced=True) for r in rows}
    first = True
    names = {int(r["gbif_taxon_key"]): r["scientific_name"] for r in rows}
    first = True
    for d in w2cells.read_batches(tmp, extra=("specieskey", "taxonkey", "species")):
        if first:
            print("columns:", list(d.columns), "rows in first batch:", len(d), flush=True)
            first = False
        sp = d["species"].astype("string").fillna("").to_numpy() if "species" in d else np.full(len(d), "")
        for k, c in cc.items():          # GBIF's SIMPLE_PARQUET keys are now short codes (e.g. "94H3"), so match on the species name
            m = sp == names[k]
            if m.any():
                c.feed(d[m])
    shutil.rmtree(tmp, ignore_errors=True)
    out = []
    for r in rows:
        cells, rep = cc[int(r["gbif_taxon_key"])].finish()
        print(r["scientific_name"], len(cells), "cells; steps left", dict(cc[int(r["gbif_taxon_key"])].left), flush=True)
        if len(cells):
            out.append(cells.assign(species=r["scientific_name"]))
    if not out:
        raise RuntimeError("no cells for any species")
    df = pd.concat(out, ignore_index=True)
    df.to_parquet("intro_occ_cells_v1.parquet", compression="zstd", index=False)
    print("download", key, "doi", s.get("doi"), "species with cells", df["species"].nunique(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
