"""Spike F experiment runner: virtual-species tests of the SDM engine. Reproduces every table in docs/spikes/F-sdm-engine.md.

    python docs/spikes/F-experiments.py OUT_DIR E1 E2 ...      # writes OUT_DIR/E1.csv ...  (4 worker processes)

Experiments (all on the 15 km North America grid unless noted; seeds 0-2 per cell of the design):
  E1 records     7 species x n in {50,100,500,5000}, biased records, target-group background, true-driver predictors
  E2 bias        7 species x n=500 x {no bias, bias+uniform bg, bias+target bg, strong bias+uniform, strong bias+target}
  E3 predictors  7 species x n=500 x six predictor sets (oracle, uncorrelated, all derived, raw seasonal, with / without the drivers)
  E4 algorithm   7 species x n=500 x each algorithm alone, and ensembles
  E5 resolution  7 species x n=500 x grid coarsened 2x, 4x, 8x (30, 60, 120 km)
  E6 novelty     7 species x n=500 trained only on the cooler half of the domain, projected everywhere
  E7 world       7 species x n in {100,500} on the 0.5 degree world grid
"""
import sys, time, csv, traceback
from multiprocessing import Pool
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ctw.species import virtual as V, sdm  # noqa: E402

SEEDS = (0, 1, 2)
SPECIES = ("broad", "narrow", "cold_limited", "drought_limited", "heat_limited", "region_excluded", "patchy")
_G = {}


def grid(domain, f=1):
    k = (domain, f)
    if k not in _G:
        if (domain, 1) not in _G:
            g = V.load_grid(domain)
            _G[(domain, 1)] = g
            _G[(domain, "bias")] = V.bias_surface(g)
            _G[(domain, "cat")] = V.catalog(g)
            B = V.bio(g.X)
            _G[(domain, "uncorr")] = sdm.select_uncorrelated(B, V.BIO_NAMES, 0.7, ["mat", "tcold", "twarm", "lpann", "wbal", "tseas", "lpdry", "vpd", "vpdmax", "lpwet"])
        if f > 1:
            _G[k] = _G[(domain, 1)].coarsen(f)
    return _G[k]


def names_for(domain, sp, key):
    if key == "drivers":
        return tuple(sp.drivers)
    un = tuple(_G[(domain, "uncorr")])
    return {"uncorr": un, "all10": V.BIO_NAMES, "raw16": tuple(f"x{j}" for j in range(16)),
            "all10_minus_drivers": tuple(v for v in V.BIO_NAMES if v not in sp.drivers),
            "uncorr_minus_drivers": tuple(v for v in un if v not in sp.drivers)}[key]


def work(t):
    t0 = time.time()
    try:
        dom = t.get("domain", "na")
        g = grid(dom)
        sp = _G[(dom, "cat")][t["species"]]
        fit = grid(dom, t["res"]) if t.get("res", 1) > 1 else None
        mask = None
        if t.get("mask") == "cool":
            mat = V.bio(g.X)[:, 0]
            mask = mat < np.median(mat)
        s = sdm.Settings(seed=t["seed"], algos=tuple(t.get("algos", sdm.Settings().algos)), threshold=t.get("threshold", "p05"))
        r = V.evaluate(g, sp, n=t["n"], seed=t["seed"], bias_power=t.get("bias_power", 1.0), background=t.get("background", "target"),
                       names=names_for(dom, sp, t.get("pred", "drivers")), settings=s, fit_grid=fit, bias=_G[(dom, "bias")], train_mask=mask)
        r.update({k: v for k, v in t.items() if k not in r}, secs=round(time.time() - t0, 1))
        return r
    except Exception:
        traceback.print_exc()
        return dict(t, error=1)


def design(name):
    T = []
    for sp in SPECIES:
        for seed in SEEDS:
            if name == "E1":
                T += [dict(exp=name, species=sp, seed=seed, n=n) for n in (50, 100, 500, 5000)]
            elif name == "E2":
                T += [dict(exp=name, species=sp, seed=seed, n=500, label=lab, bias_power=bp, background=bg)
                      for lab, bp, bg in (("none/uniform", 0.0, "uniform"), ("bias/uniform", 1.0, "uniform"), ("bias/target", 1.0, "target"),
                                           ("strong/uniform", 2.0, "uniform"), ("strong/target", 2.0, "target"))]
            elif name == "E3":
                T += [dict(exp=name, species=sp, seed=seed, n=500, label=k, pred=k)
                      for k in ("drivers", "uncorr", "all10", "raw16", "all10_minus_drivers", "uncorr_minus_drivers")]
            elif name == "E4":
                T += [dict(exp=name, species=sp, seed=seed, n=500, label=lab, algos=al)
                      for lab, al in [(a, (a,)) for a in sdm.ALGOS] + [("ens4", ("gam", "maxent", "gbm", "rf")), ("ens6", sdm.ALGOS), ("ens_glm_gam_maxent", ("glm", "gam", "maxent"))]]
            elif name == "E5":
                T += [dict(exp=name, species=sp, seed=seed, n=500, res=f, label=f"{15 * f} km") for f in (2, 4, 8)]
            elif name == "E6":
                T += [dict(exp=name, species=sp, seed=seed, n=500, mask="cool", label="cool half")]
            elif name == "E7":
                T += [dict(exp=name, species=sp, seed=seed, n=n, domain="world") for n in (100, 500)]
    return T


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[2:]:
        tasks = design(name)
        t0 = time.time()
        with Pool(4) as pool:
            rows = pool.map(work, tasks, chunksize=1)
        keys = sorted({k for r in rows for k in r})
        with open(out / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, keys)
            w.writeheader()
            w.writerows([{k: (",".join(map(str, v)) if isinstance(v, (tuple, list)) else v) for k, v in r.items()} for r in rows])
        print(name, len(rows), "runs", sum("error" in r for r in rows), "errors", round(time.time() - t0), "s", flush=True)
