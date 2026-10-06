"""Spike F: turn the experiment CSVs into the tables (printed as markdown) and figures of docs/spikes/F-sdm-engine.md.

    python docs/spikes/F-analysis.py RESULTS_DIR [maps]     # 'maps' also re-runs two species to draw docs/spikes/img/F-maps.png
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
IMG = Path(__file__).resolve().parent / "img"
RES = Path(sys.argv[1])
P1, P2 = "2-4_2050_", "5-8_2100_"
OKABE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000"]


def load(n):
    f = RES / f"{n}.csv"
    return pd.read_csv(f) if f.exists() else None


def med_iqr(s, d=2):
    s = s.dropna()
    if len(s) == 0:
        return "n/a"
    q = np.quantile(s, [.25, .5, .75])
    return f"{q[1]:.{d}f} ({q[0]:.{d}f}-{q[2]:.{d}f})"


def md(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, [df.index.name or ""] + cols)) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, r in df.iterrows():
        out.append("| " + " | ".join([str(i)] + [str(v) for v in r.values]) + " |")
    return "\n".join(out)


def add(d):
    d = d.copy()
    for p in (P1, P2):
        d[p + "abs_change_err"] = d[p + "change_err"].abs()
    d["bad"] = (d[P1 + "sorensen"] < .8) | (d[P2 + "sorensen"] < .8) | (d[P2 + "abs_change_err"] > 20) | (d["now_sorensen"] < .8)
    return d


def table(d, by, cols, names=None, fn=med_iqr):
    names = names or cols
    return md(pd.DataFrame({nm: d.groupby(by)[c].apply(fn) for nm, c in zip(names, cols)}))


HEAD = ["now_sorensen", "now_tss", "now_area_ratio", P1 + "sorensen", P2 + "sorensen", P2 + "abs_change_err", P2 + "shift_err_km", P2 + "bearing_err", P2 + "class_agree"]
HN = ["present Sorensen", "present TSS", "area ratio", "2050 Sorensen", "2100 Sorensen", "2100 area-change error (pp)", "2100 centroid error (km)", "bearing error (deg)", "change-class agreement"]


def fig_n(d):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(11, 3.4), constrained_layout=True)
    for k, (c, t) in enumerate([("now_sorensen", "Present range overlap (Sorensen)"), (P2 + "sorensen", "2100 range overlap (Sorensen)"), (P2 + "abs_change_err", "2100 area-change error (pp)")]):
        for i, (sp, g) in enumerate(d.groupby("species")):
            m = g.groupby("n_req")[c].mean()
            ax[k].plot(m.index, m.values, "o-", color=OKABE[i % 7], label=sp, lw=1.6, ms=4)
        ax[k].set_xscale("log"); ax[k].set_title(t, fontsize=10); ax[k].set_xlabel("records requested")
        ax[k].grid(alpha=.25)
    ax[0].legend(fontsize=7, frameon=False)
    fig.savefig(IMG / "F-records.png", dpi=130)


def fig_gate(d):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.6), constrained_layout=True)
    for k, (x, xl) in enumerate([("cv_auc", "spatial-CV AUC (target-group background)"), ("cv_boyce", "spatial-CV Boyce index")]):
        for i, (sp, g) in enumerate(d.groupby("species")):
            ax[k].scatter(g[x], g[P2 + "sorensen"], s=14, color=OKABE[i % 7], label=sp, alpha=.8)
        ax[k].set_xlabel(xl); ax[k].set_ylabel("true 2100 range overlap (Sorensen)"); ax[k].grid(alpha=.25)
        ax[k].axhline(.8, color="grey", lw=.8, ls="--")
    ax[0].legend(fontsize=7, frameon=False)
    fig.savefig(IMG / "F-gates.png", dpi=130)


def fig_nov(d):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.6), constrained_layout=True)
    for i, (sp, g) in enumerate(d.groupby("species")):
        ax[0].scatter(g[P2 + "novel_share"] * 100, g[P2 + "novel_err"] * 100, s=16, color=OKABE[i % 7], label=sp)
        ax[1].scatter(g[P2 + "novel_share"] * 100, g[P2 + "sorensen"], s=16, color=OKABE[i % 7])
    ax[0].set_xlabel("share of cells flagged novel by MESS (%)"); ax[0].set_ylabel("misclassified share of flagged cells (%)")
    ax[1].set_xlabel("share of cells flagged novel by MESS (%)"); ax[1].set_ylabel("2100 range overlap (Sorensen)")
    for a in ax:
        a.grid(alpha=.25)
    ax[0].legend(fontsize=7, frameon=False)
    fig.savefig(IMG / "F-novelty.png", dpi=130)


def maps():
    import matplotlib.pyplot as plt
    from ctw.species import virtual as V, sdm
    g = V.load_grid("na")
    cat = V.catalog(g)
    bias = V.bias_surface(g)
    fig, ax = plt.subplots(2, 4, figsize=(13, 6.4), constrained_layout=True)
    for r, nm in enumerate(["cold_limited", "heat_limited"]):
        sp = cat[nm]
        rng = np.random.default_rng(3)
        rec = V.sample_occurrences(g, sp.present(g), sp.suitability(g), 500, rng, bias)
        bg = V.target_group_background(g, bias, 10000, rng)
        res = sdm.run_sdm(g, rec, bg, sp.drivers, sdm.Settings(seed=3), [("SSP5-8.5", "2100")])
        f = res.future[("SSP5-8.5", "2100")]
        tn, tf = sp.present(g), sp.present(g, "SSP5-8.5", "2100")
        for c, (title, cls) in enumerate([("true now", 2 * tn), ("predicted now", 2 * res.present_now), ("true SSP5-8.5 2100", 2 * tf), ("predicted 2100 (grey = novel climate)", 2 * f["present"])]):
            a = ax[r, c]
            col = np.where(cls > 0, "#0072B2", "#dddddd")
            if c == 3:
                col = np.where(f["novel"], "#888888", col)
            a.scatter(g.lon, g.lat, c=col, s=0.6, marker="s", linewidths=0, rasterized=True)
            if c == 0:
                a.scatter(g.lon[rec], g.lat[rec], s=3, c="#D55E00", linewidths=0)
            a.set_title(f"{nm}: {title}", fontsize=8); a.set_xticks([]); a.set_yticks([]); a.set_aspect(1.3)
    fig.savefig(IMG / "F-maps.png", dpi=110)


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    e1 = load("E1")
    if e1 is not None:
        e1 = add(e1)
        print("### E1 by number of records (median and quartiles over 6 species x 3 seeds)\n")
        print(table(e1, "n_req", ["n_rec", "cv_auc", "cv_tss", "cv_boyce"] + HEAD, ["records used", "CV AUC", "CV TSS", "CV Boyce"] + HN), "\n")
        s5 = e1[e1.n_req == 500]
        print("### E1 per species at 500 records (mean of 3 seeds)\n")
        print(md(s5.groupby("species")[["cv_auc", "cv_boyce"] + HEAD + [P2 + "true_change", P2 + "pred_change"]].mean().round(2)), "\n")
        print("### E1 per species at 50 records\n")
        print(md(e1[e1.n_req == 50].groupby("species")[["cv_auc", "cv_boyce"] + HEAD].mean().round(2)), "\n")
        print("### E1 dispersal assumptions (500 records, 2100): Sorensen of limited projection vs the same assumption applied to truth; area ratio\n")
        rows = {m: [s5[f"{P2}{m}_disp_sorensen"].mean().round(2), s5[f"{P2}{m}_disp_area_ratio"].median().round(2)] for m in ("unlimited", "fast", "slow", "none")}
        print(md(pd.DataFrame(rows, index=["Sorensen", "area ratio (median)"]).T), "\n")
        print("### thresholds (E1, 500 records)\n")
        rows = {m: [s5[f"thr_{m}_now_tss"].median().round(2), s5[f"thr_{m}_now_area_ratio"].median().round(2), s5[f"thr_{m}_fut_sorensen"].median().round(2), s5[f"thr_{m}_change_err"].abs().median().round(1)] for m in ("maxtss", "p10", "p05", "minpres")}
        print(md(pd.DataFrame(rows, index=["present TSS", "present area ratio", "2100 Sorensen", "|area-change error| pp"]).T), "\n")
        fig_n(e1)
    pool = [add(x) for x in (load(n) for n in ("E1", "E2", "E3", "E4", "E5", "E7")) if x is not None]
    if pool:
        ok = []
        for x in pool:
            if "label" in x:
                x = x[x.label.isin(["bias/target", "drivers", "uncorr", "ens4"]) | x.label.isna()]
            ok.append(x)
        d = pd.concat(ok)
        d = d[d.get("domain", pd.Series("na", index=d.index)).fillna("na") == "na"] if "domain" in d else d
        d = d.dropna(subset=["cv_auc"])
        print(f"### gate analysis: {len(d)} runs with default settings\n")
        rows = []
        for lab, mask in [("no gate", d.cv_auc > -1), ("n >= 50", d.n_rec >= 50), ("n >= 100", d.n_rec >= 100), ("CV AUC >= 0.7", d.cv_auc >= .7), ("CV AUC >= 0.75", d.cv_auc >= .75),
                          ("CV Boyce >= 0.6", d.cv_boyce >= .6), ("CV Boyce >= 0.7", d.cv_boyce >= .7), ("CV Boyce >= 0.8", d.cv_boyce >= .8),
                          ("n >= 100 & Boyce >= 0.7", (d.n_rec >= 100) & (d.cv_boyce >= .7)),
                          ("n >= 100 & Boyce >= 0.7 & AUC >= 0.6", (d.n_rec >= 100) & (d.cv_boyce >= .7) & (d.cv_auc >= .6)),
                          ("n >= 100 & Boyce >= 0.7 & novel <= 15%", (d.n_rec >= 100) & (d.cv_boyce >= .7) & (d[P2 + "novel_share"] <= .15))]:
            k = d[mask]
            rows.append([lab, f"{len(k)/len(d):.0%}", f"{k.bad.mean():.0%}" if len(k) else "n/a", f"{k[P2 + 'sorensen'].median():.2f}" if len(k) else "n/a",
                         f"{k[P2 + 'abs_change_err'].quantile(.9):.0f}" if len(k) else "n/a"])
        print(md(pd.DataFrame(rows, columns=["gate", "published", "unacceptable among published", "median 2100 Sorensen", "90th pct |area-change error| pp"]).set_index("gate")), "\n")
        fig_gate(d)
    for n, by, cols, names in [("E2", "label", None, None), ("E3", "label", None, None), ("E4", "label", None, None), ("E5", "label", None, None)]:
        x = load(n)
        if x is None:
            continue
        x = add(x)
        print(f"### {n} (median and quartiles; 6 species x 3 seeds)\n")
        print(table(x, by, ["n_rec", "cv_auc", "cv_boyce"] + HEAD, ["records", "CV AUC", "CV Boyce"] + HN), "\n")
        print(f"### {n} per species, present Sorensen / 2100 Sorensen (mean of 3 seeds)\n")
        pt = x.groupby(["label", "species"])[["now_sorensen", P2 + "sorensen"]].mean().round(2)
        pt["v"] = pt.now_sorensen.astype(str) + " / " + pt[P2 + "sorensen"].astype(str)
        print(md(pt["v"].unstack("species")), "\n")
    x = load("E6")
    if x is not None:
        x = add(x)
        print("### E6 trained on the cooler half only, projected everywhere (mean of 3 seeds)\n")
        cols = ["now_sorensen", "now_area_ratio", P1 + "sorensen", P2 + "sorensen", P2 + "novel_share", P2 + "novel_err", P2 + "other_err", P2 + "shift_err_km"]
        print(md(x.groupby("species")[cols].mean().round(2)), "\n")
        fig_nov(x)
    x = load("E7")
    if x is not None:
        x = add(x)
        print("### E7 world 0.5 degree grid\n")
        print(table(x, "n_req", ["n_rec", "cv_auc", "cv_boyce"] + HEAD, ["records", "CV AUC", "CV Boyce"] + HN), "\n")
    if "maps" in sys.argv:
        maps()
