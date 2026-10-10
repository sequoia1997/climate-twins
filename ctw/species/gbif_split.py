"""GBIF before and after split (workstream W4, the free test for species outside North America; protocol in docs/pilot/W4-hindcast.md).

Input contract (the W2 time-split product; adapt the column names here when docs/pilot/W2-occurrences.md fixes them):
  occ : DataFrame(species, row, col, year)   cleaned, thinned-per-cell records on the 1/24 degree grid (row 0 north)
  tg  : DataFrame(group, row, col, year, n)  record counts of the whole target group (all birds, all vascular plants, ...)
Periods 1970-1999 and 2000-2020. Analysis blocks are BLOCK x BLOCK native cells (12 = 0.5 degree). A block is well sampled when the target group has at
least MIN_TG records in BOTH periods (C-validation 4.3, N = 20, a proposal). Presence = at least one record of the species in the period; absence =
a well-sampled block with no record. Record counts are never compared between periods.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import hindcast as H

P1, P2 = (1970, 1999), (2000, 2020)
BLOCK = 12
MIN_TG = 20


def _blocks(df: pd.DataFrame, block: int) -> pd.DataFrame:
    df = df.copy()
    df["br"], df["bc"] = df.row // block, df.col // block
    return df


def well_sampled(tg: pd.DataFrame, group: str, block: int = BLOCK, min_tg: int = MIN_TG, p1=P1, p2=P2) -> pd.DataFrame:
    """Blocks with at least min_tg target-group records in both periods: columns br, bc, n1, n2."""
    t = _blocks(tg[tg.group == group], block)
    a = t[t.year.between(*p1)].groupby(["br", "bc"]).n.sum().rename("n1")
    b = t[t.year.between(*p2)].groupby(["br", "bc"]).n.sum().rename("n2")
    w = pd.concat([a, b], axis=1).dropna().reset_index()
    return w[(w.n1 >= min_tg) & (w.n2 >= min_tg)]


def species_cellset(occ: pd.DataFrame, tg: pd.DataFrame, species: str, group: str, *, block: int = BLOCK, min_tg: int = MIN_TG, well_only: bool = True,
                    p1=P1, p2=P2, scores: pd.DataFrame | None = None, thr: float | None = None) -> H.CellSet:
    """CellSet on well-sampled blocks (well_only) or on every block with any target-group record in both periods (the 'all cells' variant, whose gap to
    the well-sampled result measures the effort bias). scores: optional DataFrame(row, col, score1, score2) at native cells, averaged per block."""
    allb = well_sampled(tg, group, block, 1, p1, p2)
    blocks = well_sampled(tg, group, block, min_tg, p1, p2) if well_only else allb
    o = _blocks(occ[occ.species == species], block)
    pr1 = o[o.year.between(*p1)].groupby(["br", "bc"]).size().rename("o1")
    pr2 = o[o.year.between(*p2)].groupby(["br", "bc"]).size().rename("o2")
    g = blocks.set_index(["br", "bc"]).join(pr1).join(pr2).fillna({"o1": 0, "o2": 0}).reset_index()
    la = H_lat(g.br.values, block)
    lo = H_lon(g.bc.values, block)
    g["s1"] = g["s2"] = np.nan
    if scores is not None:
        s = _blocks(scores.rename(columns={}), block).groupby(["br", "bc"]).agg(s1=("score1", "mean"), s2=("score2", "mean")).reset_index()
        g = g.drop(columns=["s1", "s2"]).merge(s, on=["br", "bc"], how="inner")
        la, lo = H_lat(g.br.values, block), H_lon(g.bc.values, block)
    cs = H.CellSet(la, lo, np.ones(len(g)), g.o1.values > 0, g.o2.values > 0, g.s1.values if scores is not None else None, g.s2.values if scores is not None else None, thr)
    cs.cluster = g.br.values.astype(np.int64) * 100000 + g.bc.values
    return cs


def H_lat(br, block, nlat: int = 4320):
    return 90.0 - (np.asarray(br) * block + block / 2.0) * (180.0 / nlat)


def H_lon(bc, block, nlon: int = 8640):
    return -180.0 + (np.asarray(bc) * block + block / 2.0) * (360.0 / nlon)


def effort_gap(cs_well: H.CellSet, cs_all: H.CellSet) -> dict:
    """Observed-change difference between the well-sampled and the all-cells analyses (km, northward km): a measure of the effort bias."""
    a, b = H.range_change(cs_well.lat, cs_well.lon, cs_well.area, cs_well.obs1, cs_well.obs2), H.range_change(cs_all.lat, cs_all.lon, cs_all.area, cs_all.obs1, cs_all.obs2)
    return dict(well_km=a["km"], all_km=b["km"], well_north=a["north"], all_north=b["north"], n_well=len(cs_well.lat), n_all=len(cs_all.lat))
