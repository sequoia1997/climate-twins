"""US Forest Service Forest Inventory and Analysis (FIA) ingest and the tree CHANGE test (workstream W4).

Source: FIA DataMart state CSVs (https://apps.fs.usda.gov/fia/datamart/CSV/<ST>_PLOT.csv, _TREE.csv, _SEEDLING.csv). US federal data.
Columns used (verified in the Actions probe, run 38072387399): PLOT: CN, STATECD, PLOT_STATUS_CD (1 = forest, sampled), MEASYEAR, CYCLE,
SUBCYCLE, LAT, LON, DESIGNCD, KINDCD; TREE: PLT_CN, STATUSCD (1 = live), SPCD, DIA (inches); SEEDLING: PLT_CN, SPCD, TREECOUNT.

Design decisions (all proposals, documented in docs/pilot/W4-hindcast.md):
 * First complete cycle versus latest complete cycle per state. A periodic cycle (every plot SUBCYCLE 0) is complete by construction; an
   annual cycle is complete when it has at least COMPLETE_FRAC of the median number of sampled plots of the state's annual cycles.
 * Only forested sampled plots (PLOT_STATUS_CD 1) and live trees of at least 5.0 inches DBH (the size every cycle tallies).
 * Coordinates are the public, fuzzed ones. Plots are aggregated to blocks of BLOCK native cells (12 = 0.5 degree, about 55 km), far
   larger than the fuzzing distance, and each block needs MIN_PLOTS plots in both cycles. Both cycles are rarefied to the same number of
   plots per block (random, seeded) so a denser later design cannot create apparent range expansion.
 * States whose two cycles are less than MIN_INTERVAL years apart (median MEASYEAR) are dropped.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import bbs, hindcast as H

PILOT_TREES = {318: "Acer saccharum", 316: "Acer rubrum", 129: "Pinus strobus", 746: "Populus tremuloides", 802: "Quercus alba"}
CONUS = ("AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
COMPLETE_FRAC = 0.85
MIN_INTERVAL = 15
BLOCK = 12
MIN_PLOTS = 8
CAP = 30


def complete_cycles(plots: pd.DataFrame, complete_frac: float = COMPLETE_FRAC, min_interval: int = MIN_INTERVAL) -> dict:
    """plots: PLOT rows of one state (PLOT_STATUS_CD 1 or 2) with CYCLE, SUBCYCLE, MEASYEAR. Returns dict(first, last, ok, why, t1, t2, table)."""
    plots = plots.dropna(subset=["CYCLE", "MEASYEAR"]).assign(SUBCYCLE=lambda d: d.SUBCYCLE.fillna(0))
    g = plots.groupby("CYCLE").agg(n=("MEASYEAR", "size"), nsub=("SUBCYCLE", "nunique"), maxsub=("SUBCYCLE", "max"), t=("MEASYEAR", "median")).reset_index()
    periodic = g.maxsub == 0
    ann = g[~periodic]
    ref = ann.n.median() if len(ann) else np.nan
    g["complete"] = periodic | (g.n >= complete_frac * ref if len(ann) else False)
    c = g[g.complete].sort_values("CYCLE")
    out = dict(table=g, first=None, last=None, ok=False, why="", t1=np.nan, t2=np.nan)
    if len(c) < 2:
        out["why"] = "fewer than two complete cycles"; return out
    f, l = c.iloc[0], c.iloc[-1]
    out.update(first=int(f.CYCLE), last=int(l.CYCLE), t1=float(f.t), t2=float(l.t))
    if l.t - f.t < min_interval:
        out["why"] = f"interval {l.t - f.t:.0f} y < {min_interval}"; return out
    out["ok"] = True
    return out


def tree_flags(tree_chunks, plot_cns: set, spcds=tuple(PILOT_TREES)) -> pd.DataFrame:
    """Adult counts: live trees of at least 5 inches per (PLT_CN, SPCD) over iterable chunks of the TREE table."""
    parts = []
    for ch in tree_chunks:
        ch = ch[(ch.STATUSCD == 1) & (ch.DIA >= 5.0) & ch.SPCD.isin(spcds) & ch.PLT_CN.isin(plot_cns)]
        parts.append(ch.groupby(["PLT_CN", "SPCD"]).size().rename("n").reset_index())
    if not parts:
        return pd.DataFrame(columns=["PLT_CN", "SPCD", "n"])
    d = pd.concat(parts)
    return d.groupby(["PLT_CN", "SPCD"]).n.sum().reset_index()


def seedling_flags(seed_chunks, plot_cns: set, spcds=tuple(PILOT_TREES)) -> pd.DataFrame:
    parts = []
    for ch in seed_chunks:
        ch = ch[ch.SPCD.isin(spcds) & ch.PLT_CN.isin(plot_cns) & (ch.TREECOUNT > 0)]
        parts.append(ch.groupby(["PLT_CN", "SPCD"]).TREECOUNT.sum().rename("n").reset_index())
    if not parts:
        return pd.DataFrame(columns=["PLT_CN", "SPCD", "n"])
    d = pd.concat(parts)
    return d.groupby(["PLT_CN", "SPCD"]).n.sum().reset_index()


def state_plot_table(plot: pd.DataFrame, tree_chunks, seed_chunks=None, spcds=tuple(PILOT_TREES)) -> tuple[pd.DataFrame, dict]:
    """One state: select the first and last complete cycles, keep forested sampled plots, attach adult and seedling counts per species.
    Returns (plot-level table with columns state, window, cn, lat, lon, measyear, designcd, a<SPCD>, s<SPCD>) and the cycle info."""
    p = plot[plot.PLOT_STATUS_CD.isin([1, 2])]
    info = complete_cycles(p)
    if not info["ok"]:
        return pd.DataFrame(), info
    p = p[(p.PLOT_STATUS_CD == 1) & p.CYCLE.isin([info["first"], info["last"]]) & p.LAT.notna() & p.LON.notna()].copy()
    p["window"] = np.where(p.CYCLE == info["first"], 1, 2)
    cns = set(p.CN)
    a = tree_flags(tree_chunks, cns, spcds)
    out = p[["STATECD", "window", "CN", "LAT", "LON", "MEASYEAR", "DESIGNCD", "CYCLE"]].rename(
        columns={"STATECD": "state", "CN": "cn", "LAT": "lat", "LON": "lon", "MEASYEAR": "measyear", "DESIGNCD": "designcd", "CYCLE": "cycle"})
    for sp in spcds:
        m = a[a.SPCD == sp].set_index("PLT_CN").n
        out[f"a{sp}"] = out.cn.map(m).fillna(0).astype(int)
    if seed_chunks is not None:
        s = seedling_flags(seed_chunks, cns, spcds)
        for sp in spcds:
            m = s[s.SPCD == sp].set_index("PLT_CN").n
            out[f"s{sp}"] = out.cn.map(m).fillna(0).astype(int)
    return out, info


def block_ids(lat, lon, block: int = BLOCK, rc_of=None):
    r, c = (rc_of or bbs.grid_rc)(lat, lon)
    return r // block, c // block


def species_cellset(plots: pd.DataFrame, spcd: int, block: int = BLOCK, min_plots: int = MIN_PLOTS, cap: int = CAP, seed: int = 0,
                    designcd1_only: bool = False, min_interval: float = MIN_INTERVAL, scores: pd.DataFrame | None = None,
                    thr: float | None = None, rc_of=None) -> tuple[H.CellSet, dict]:
    """CellSet of adult presence in the first versus the latest cycle on blocks with at least min_plots plots in both cycles, rarefied to
    n = min(n1, n2, cap) random plots per block and window. Weight 1 per block. Also returns counts (plots with the species in each window,
    blocks) for the eligibility rule (>= 500 plots with the species in each cycle, C-validation 4.7)."""
    d = plots[plots.designcd == 1] if designcd1_only else plots
    if scores is not None:      # model scores per 1/24 degree cell (row, col, score1, score2); a block's score is the mean over its plots' cells
        rr, cc = (rc_of or bbs.grid_rc)(d.lat.values, d.lon.values)
        d = d.assign(row=rr, col=cc).merge(scores[["row", "col", "score1", "score2"]], on=["row", "col"], how="left")
    bid = block_ids(d.lat.values, d.lon.values, block, rc_of)
    d = d.assign(br=bid[0], bc=bid[1])
    rng = np.random.default_rng(seed)
    rows = []
    for (br, bc), g in d.groupby(["br", "bc"]):
        g1, g2 = g[g.window == 1], g[g.window == 2]
        n = min(len(g1), len(g2), cap)
        if n < min_plots:
            continue
        s1, s2 = g1.sample(n, random_state=int(rng.integers(1 << 30))), g2.sample(n, random_state=int(rng.integers(1 << 30)))
        t1, t2 = g1.measyear.median(), g2.measyear.median()
        if t2 - t1 < min_interval:
            continue
        row = dict(br=br, bc=bc, lat=g.lat.mean(), lon=g.lon.mean(), o1=bool((s1[f"a{spcd}"] > 0).any()), o2=bool((s2[f"a{spcd}"] > 0).any()),
                   n=n, t1=t1, t2=t2)
        if scores is not None:
            row.update(m1=g.score1.mean(), m2=g.score2.mean())
        rows.append(row)
    r = pd.DataFrame(rows)
    if r.empty:
        cs = H.CellSet(np.array([]), np.array([]), np.array([]), np.array([], bool), np.array([], bool))
    else:
        if scores is not None:
            r = r.dropna(subset=["m1", "m2"])
        cs = H.CellSet(r.lat.values, r.lon.values, np.ones(len(r)), r.o1.values, r.o2.values, r.m1.values if scores is not None else None,
                       r.m2.values if scores is not None else None, thr)
        cs.cluster = r.br.values.astype(np.int64) * 100000 + r.bc.values
    cnt = dict(plots_w1=int((d[d.window == 1][f"a{spcd}"] > 0).sum()), plots_w2=int((d[d.window == 2][f"a{spcd}"] > 0).sum()), blocks=len(r),
               t1=float(r.t1.median()) if len(r) else np.nan, t2=float(r.t2.median()) if len(r) else np.nan)
    return cs, cnt


def seedling_adult(plots: pd.DataFrame, spcd: int, block: int = BLOCK, min_plots: int = MIN_PLOTS, n_boot: int = 300, seed: int = 0) -> dict:
    """Space-for-time check in the LATEST cycle: where are seedlings present versus adults? A seedling centroid north of the adult centroid
    suggests regeneration expanding poleward (Woodall et al.; Zhu et al.), a smaller-lag signal than adult change. Returns range_change
    metrics of (adults -> seedlings) with bootstrap, or None without seedling data."""
    d = plots[(plots.window == 2)]
    if f"s{spcd}" not in d:
        return None
    br, bc = block_ids(d.lat.values, d.lon.values, block)
    d = d.assign(br=br, bc=bc)
    g = d.groupby(["br", "bc"]).agg(lat=("lat", "mean"), lon=("lon", "mean"), n=("cn", "size"), a=(f"a{spcd}", lambda x: (x > 0).any()), s=(f"s{spcd}", lambda x: (x > 0).any())).reset_index()
    g = g[g.n >= min_plots]
    cs = H.CellSet(g.lat.values, g.lon.values, np.ones(len(g)), g.a.values, g.s.values)
    cs.cluster = g.br.values.astype(np.int64) * 100000 + g.bc.values
    o = H.observed_change(cs, n_boot=n_boot, seed=seed)
    o["n_cells"] = len(g)
    return o
