"""Spike A follow-up (GitHub Actions only): how much does the CC0 + CC-BY filter cost AFTER cleaning and thinning?
For a few species it requests ONE download that also includes CC-BY-NC, cleans it twice (all licences; CC0 + CC-BY only) and
reports the thinned 2.5' cells in each, the cells that exist only because of CC-BY-NC records, and where those are.
Also prints GBIF's derived-dataset API shape (public GET). Secrets are read from the environment by gbif.py and never printed.
  python -m ctw.species.spike_a_nc            writes work/spike-a/nc_results.json"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
import requests
from . import gbif, occ, spike_a as A
from .. import common as C

SPECIES = ["Acer saccharum", "Danaus plexippus", "Ixodes scapularis"]          # the three with the largest record-level loss and the fewest records
ALL_LIC = ["CC0_1_0", "CC_BY_4_0", "CC_BY_NC_4_0"]


def derived_api():
    out = {}
    for path in ("/derivedDataset", "/derivedDataset?limit=2"):
        try:
            r = requests.get(gbif.API + path, timeout=60)
            out[path] = {"status": r.status_code, "body": r.text[:1500]}
        except Exception as e:
            out[path] = {"error": type(e).__name__}
    return out


def main() -> int:
    A.dump("derived_api.json", derived_api())
    print(json.dumps(derived_api(), indent=1)[:2500], flush=True)
    cfg = C.config()
    cont, gj = A.continents(cfg)
    ref = occ.reference_points(C.ROOT / "data" / "world_targets.csv", gj, A.institutions())
    land = occ.land_mask_default()
    taxa = {s: gbif.match(s)["usageKey"] for s in SPECIES}
    kinds = {a: k for a, _, k in gbif.PILOT}
    keys = {s: gbif.request_download(taxa[s], licences=ALL_LIC) for s in SPECIES}
    print("requested", keys, flush=True)
    A.dump("nc_keys.json", keys)
    res = {}
    for s, key in keys.items():
        st = gbif.wait(key, every=30, limit_s=3 * 3600)
        row = {"key": key, "status": st["status"], "doi": st.get("doi"), "records": st.get("totalRecords")}
        if st["status"] == "SUCCEEDED":
            dest = A.fetch(st["downloadLink"], Path(os.environ.get("SPIKE_TMP", "/tmp/spike-a-nc")) / s.replace(" ", "_"))
            mk = lambda: occ.Cleaner(kind=kinds[s], land=land, ref=ref, establishment="drop" if kinds[s] != "animal" else "off")
            c_all, c_ok = mk(), mk()
            n = {"CC0_1_0": 0, "CC_BY_4_0": 0, "CC_BY_NC_4_0": 0}
            for d in A.read_batches(dest):
                for k, v in d["license"].value_counts().items():
                    n[k] = n.get(k, 0) + int(v)
                c_all.feed(d)
                c_ok.feed(d[d["license"].isin(["CC0_1_0", "CC_BY_4_0"])])
            a, b = c_all.finish(), c_ok.finish()
            only = a[~a["cell"].isin(set(b["cell"]))]
            row.update({"licences_in_file": n, "cleaning_all": c_all.report(), "cleaning_ccby": c_ok.report(),
                        "cells_all": int(len(a)), "cells_ccby": int(len(b)), "cells_only_nc": int(len(only)),
                        "cells_lost_pct": round(100 * len(only) / max(len(a), 1), 1),
                        "continents_all": occ.continent_counts(a, cont), "continents_ccby": occ.continent_counts(b, cont),
                        "continents_only_nc": occ.continent_counts(only, cont)})
            os.system(f"rm -rf '{dest}'")
        res[s] = row
        A.dump("nc_results.json", res)
        print("done", s, json.dumps(row, default=str), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
