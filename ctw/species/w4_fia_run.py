"""W4: FIA state CSVs -> plot table for the first and latest complete cycles, observed change per pilot tree. Run in Actions."""
import argparse, os, sys, time, urllib.request, json
import numpy as np, pandas as pd
from ctw.species import fia, hindcast as H

BASE = "https://apps.fs.usda.gov/fia/datamart/CSV/"
UA = {"User-Agent": "climate-twins-w4/0.1 (mailto:forest4science@gmail.com)"}
def fetch(name, dest):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=600) as r, open(dest, "wb") as f:
                while (b := r.read(1 << 22)): f.write(b)
            return True
        except Exception as e:
            code = getattr(e, "code", None)
            if code == 404: return False
            print("  retry", name, k, type(e).__name__, e, flush=True); time.sleep(5 * (k + 1))
    return False

ap = argparse.ArgumentParser(); ap.add_argument("--out", default="w4-out"); ap.add_argument("--work", default="w4-work"); ap.add_argument("--states", default="")
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); os.makedirs(a.work, exist_ok=True)
fetch("REF_SPECIES.csv", f"{a.work}/REF_SPECIES.csv")
ref = pd.read_csv(f"{a.work}/REF_SPECIES.csv", usecols=["SPCD", "COMMON_NAME", "SCIENTIFIC_NAME"])
print(ref[ref.SPCD.isin(fia.PILOT_TREES)].to_string(), flush=True)
PCOLS = ["CN", "STATECD", "PLOT_STATUS_CD", "MEASYEAR", "CYCLE", "SUBCYCLE", "LAT", "LON", "DESIGNCD"]
tables, infos = [], []
for st in (a.states.split() or fia.CONUS):
    t0 = time.time()
    pf, tf, sf = (f"{a.work}/{st}_{k}.csv" for k in ("PLOT", "TREE", "SEEDLING"))
    if not fetch(f"{st}_PLOT.csv", pf) or not fetch(f"{st}_TREE.csv", tf):
        print(st, "missing PLOT or TREE", flush=True); continue
    has_seed = fetch(f"{st}_SEEDLING.csv", sf)
    plot = pd.read_csv(pf, usecols=PCOLS, low_memory=False)
    tc = pd.read_csv(tf, usecols=["PLT_CN", "STATUSCD", "SPCD", "DIA"], chunksize=500_000, low_memory=False)
    sc = pd.read_csv(sf, usecols=["PLT_CN", "SPCD", "TREECOUNT"], chunksize=500_000, low_memory=False) if has_seed else None
    tab, info = fia.state_plot_table(plot, tc, sc)
    g = info["table"]
    print(st, "OK" if info["ok"] else "DROPPED " + info["why"], "cycles", dict(zip(g.CYCLE, g.n)), "first", info["first"], "last", info["last"],
          "t1", info["t1"], "t2", info["t2"], "plots kept", len(tab), "%.0fs" % (time.time() - t0), flush=True)
    infos.append(dict(state=st, ok=info["ok"], why=info["why"], first=info["first"], last=info["last"], t1=info["t1"], t2=info["t2"], plots=len(tab)))
    if len(tab): tables.append(tab)
    for f in (pf, tf, sf):
        if os.path.exists(f): os.remove(f)
plots = pd.concat(tables, ignore_index=True)
plots.to_csv(f"{a.out}/fia_plots.csv.gz", index=False)
pd.DataFrame(infos).to_csv(f"{a.out}/fia_cycles.csv", index=False)
print("plots", len(plots), "by window", plots.window.value_counts().to_dict(), "states", plots.state.nunique())
rows = []
for spcd, nm in fia.PILOT_TREES.items():
    for variant, kw in (("all designs", {}), ("DESIGNCD 1 only", dict(designcd1_only=True))):
        cs, cnt = fia.species_cellset(plots, spcd, seed=spcd, **kw)
        if len(cs.lat) < 10:
            rows.append(dict(spcd=spcd, species=nm, variant=variant, blocks=len(cs.lat))); continue
        o = H.observed_change(cs, n_boot=300, seed=spcd)
        perm = H.permutation_p(cs, n=500, seed=spcd)
        sa = fia.seedling_adult(plots, spcd, seed=spcd) if variant == "all designs" else None
        rows.append(dict(spcd=spcd, species=nm, variant=variant, eligible=H.eligible(cnt["plots_w1"], cnt["plots_w2"], "fia"), perm_p=perm, **cnt,
                         **{k: o[k] for k in ("km", "km_lo", "km_hi", "bearing", "north", "north_se", "north_lo", "north_hi", "edge_hi_km", "edge_lo_km", "area_change", "detectable")},
                         seedling_adult_north_km=(sa or {}).get("north"), seedling_adult_north_se=(sa or {}).get("north_se"), seedling_adult_blocks=(sa or {}).get("n_cells")))
res = pd.DataFrame(rows); res.to_csv(f"{a.out}/fia_observed_change.csv", index=False)
pd.set_option("display.width", 250, "display.max_columns", 50)
print(res.round(2).to_string())
