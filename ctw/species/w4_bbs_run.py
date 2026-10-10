"""W4: download BBS from ScienceBase, build route table, detections and observed change; write to --out. Run in Actions."""
import argparse, json, os, sys, urllib.request, time
import pandas as pd
from ctw.species import bbs, hindcast as H

ITEM = "https://www.sciencebase.gov/catalog/item/691cfb53d4be021d1d89b482?format=json"
UA = {"User-Agent": "climate-twins-w4/0.1 (mailto:forest4science@gmail.com)"}

def fetch(url, dest):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(dest, "wb") as f:
                while (b := r.read(1 << 20)):
                    f.write(b)
            return
        except Exception as e:
            print("retry", k, type(e).__name__, e, flush=True); time.sleep(5 * (k + 1))
    raise SystemExit("download failed " + url)

ap = argparse.ArgumentParser(); ap.add_argument("--out", default="w4-out"); ap.add_argument("--work", default="w4-work")
ap.add_argument("--boot", type=int, default=200)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True); os.makedirs(a.work, exist_ok=True)
item = json.load(urllib.request.urlopen(urllib.request.Request(ITEM, headers=UA), timeout=60))
files = {f["name"]: f["url"] for f in item["files"]}
for n in ("Routes.csv", "SpeciesList.csv", "Weather.csv", "States.zip"):
    fetch(files[n], os.path.join(a.work, n)); print("downloaded", n, os.path.getsize(os.path.join(a.work, n)), flush=True)
import zipfile
z = zipfile.ZipFile(os.path.join(a.work, "States.zip")); print("States.zip members", len(z.namelist()), z.namelist()[:6])
with z.open([m for m in z.namelist() if m.lower().endswith(".csv")][0]) as fh: print("first member header:", fh.readline().decode("latin-1")[:400])
print("Weather header:", open(os.path.join(a.work, "Weather.csv"), encoding="latin-1").readline()[:400])
routes = bbs.read_routes(os.path.join(a.work, "Routes.csv"))
species = bbs.read_species(os.path.join(a.work, "SpeciesList.csv"))
runs = bbs.acceptable_runs(os.path.join(a.work, "Weather.csv"))
print("routes", len(routes), "acceptable route-years", len(runs), "years", runs.year.min(), runs.year.max(), flush=True)
q = bbs.qualifying_routes(runs)
print("routes with runs", len(q), "qualifying (>=10 yr in both windows)", int(q.qualifies.sum()))
rq = routes.merge(q[q.qualifies], on=["country", "state", "route"])
print("qualifying routes with coordinates", len(rq), "unique 1/24 cells", rq[["row", "col"]].drop_duplicates().shape[0])
print("by country", rq.groupby("country").size().to_dict(), "route types", rq.route_type.value_counts().to_dict())
det = bbs.detections(os.path.join(a.work, "States.zip"), runs)
pres = bbs.route_presence(det)
print("detection rows", len(det), "species", det.AOU.nunique(), flush=True)
rq.to_csv(os.path.join(a.out, "bbs_route_cells.csv"), index=False)
# routes used to FIT the hindcast model: at least 10 acceptable years in window 1 (more routes than the comparable set above)
rf = routes.merge(q[q.n1 >= bbs.MIN_YEARS], on=["country", "state", "route"])
rf.to_csv(os.path.join(a.out, "bbs_routes_fit.csv"), index=False)
print("routes with >=10 acceptable years in window 1 (fit set):", len(rf), "cells", rf[["row", "col"]].drop_duplicates().shape[0])
keep = pres[(pres.p1 | pres.p2)].merge(rf[["country", "state", "route"]].drop_duplicates(), on=["country", "state", "route"])
keep.to_csv(os.path.join(a.out, "bbs_presence_long.csv.gz"), index=False)
t = bbs.observed_table(rq, pres, species, n_boot=a.boot)
t.to_csv(os.path.join(a.out, "bbs_observed_change.csv"), index=False)
# coarse (0.5 degree) variant for the eligible species
print("eligible species (>=100 route-presences in both windows):", int(t.eligible.sum()), "of", len(t))
cols = ["english", "sci", "routes_w1", "routes_w2", "km", "bearing", "north", "north_se", "detectable", "perm_p", "edge_hi_km", "edge_lo_km", "area_change"]
pd.set_option("display.width", 250, "display.max_rows", 500)
print(t[t.eligible].sort_values("km", ascending=False)[cols].round(2).to_string())
pilot = pd.read_csv("data/species/pilot_v1.csv")
names = set(pilot.scientific_name) | set(pilot.common_name)
print("\nPILOT SPECIES IN BBS:\n", t[t.sci.isin(names) | t.english.isin(names)][["english", "sci"] + cols[2:]].round(2).to_string())
print("pilot birds NOT found:", [s for s in pilot[pilot.group == "bird"].scientific_name if s not in set(t.sci)])
print("\nSci names of all species in SpeciesList matching pilot birds (any):", species[species.sci.isin(pilot.scientific_name) | species.english.isin(pilot.common_name)][["AOU", "english", "sci"]].to_string())
