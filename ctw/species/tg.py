"""Target-group record density on the TerraClimate native grid (workstream W2).

Sampling-bias correction (target-group background, Phillips et al. 2009) needs, for every cell, how many records of the SAME taxonomic group
exist. Route chosen: ONE aggregating GBIF SQL download per group (format SQL_TSV_ZIP, a normal download with its own DOI, 3 concurrent per
account like any other). GBIF's cluster does the counting; what comes back is a few million (row, col, period, n) lines, not billions of records.
Same record filter as the species downloads (coordinates, no geospatial issue, PRESENT, CC0 / CC-BY, 1970-2020, the four basis-of-record values,
coordinate uncertainty missing or <= 10 km). Not cleaned further (centroids etc.), so it is a record-effort density, not a clean point set.

Periods: 1 = 1970-1999, 2 = 2000-2020. Well-sampled rule (C-validation.md section 4.3, N = 20): a 1/24 degree cell is well sampled when the
0.5 degree block (12 x 12 cells) that holds it has >= N target-group records in BOTH periods (N = 20, strict variant N = 100).
"""
from __future__ import annotations
import io, zipfile
import numpy as np

NROW, NCOL = 4320, 8640
BLOCK = 12                       # 12 cells of 1/24 degree = 0.5 degree
GROUPS = {   # target group -> SQL taxon condition (GBIF backbone keys: Aves 212, Mammalia 359, Insecta 216, Arachnida 367, Tracheophyta 7707728)
    "bird": "classKey = 212",
    "mammal": "classKey = 359",
    "insect_arachnid": "classKey IN (216, 367)",
    "plant": "phylumKey = 7707728",
}
PILOT_GROUP_TO_TG = {"bird": "bird", "mammal": "mammal", "insect_arachnid": "insect_arachnid", "tree": "plant", "crop": "plant"}


def sql_for(group: str, year_q: str = '"year"') -> str:
    return (f"SELECT FLOOR((90 - decimalLatitude) * 24) AS r, FLOOR((decimalLongitude + 180) * 24) AS c, "
            f"IF({year_q} <= 1999, 1, 2) AS p, COUNT(*) AS n FROM occurrence WHERE {GROUPS[group]} AND hasCoordinate = TRUE "
            f"AND hasGeospatialIssues = FALSE AND occurrenceStatus = 'PRESENT' AND license IN ('CC0_1_0', 'CC_BY_4_0') "
            f"AND {year_q} >= 1970 AND {year_q} <= 2020 "
            f"AND basisOfRecord IN ('HUMAN_OBSERVATION', 'PRESERVED_SPECIMEN', 'OBSERVATION', 'MACHINE_OBSERVATION') "
            f"AND (coordinateUncertaintyInMeters IS NULL OR coordinateUncertaintyInMeters <= 10000) GROUP BY r, c, p")


def parse_tsv_zip(data: bytes | str) -> np.ndarray:
    """Read the SQL download (zip with one TSV: header r, c, p, n) into uint32 (3, NROW, NCOL): [all, 1970-1999, 2000-2020]."""
    import pandas as pd
    z = zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data)
    name = [n for n in z.namelist() if not n.endswith("/")][0]
    df = pd.read_csv(z.open(name), sep="\t")
    df.columns = [c.lower() for c in df.columns]
    return grid_from_rows(df["r"].to_numpy(), df["c"].to_numpy(), df["p"].to_numpy(), df["n"].to_numpy())


def grid_from_rows(r, c, p, n) -> np.ndarray:
    r, c, p, n = (np.asarray(x) for x in (r, c, p, n))
    ok = (r >= 0) & (r < NROW) & (c >= 0) & (c < NCOL)
    r, c, p, n = r[ok].astype(np.int64), c[ok].astype(np.int64), p[ok].astype(int), n[ok].astype(np.int64)
    g = np.zeros((3, NROW, NCOL), np.uint32)
    for per in (1, 2):
        s = p == per
        np.add.at(g[per], (r[s], c[s]), n[s].astype(np.uint32))
    g[0] = g[1] + g[2]
    return g


def block_sums(grid2d: np.ndarray) -> np.ndarray:
    """(NROW/12, NCOL/12) sums over 12 x 12 cell blocks (0.5 degree)."""
    return grid2d.reshape(NROW // BLOCK, BLOCK, NCOL // BLOCK, BLOCK).sum(axis=(1, 3), dtype=np.int64)


def well_sampled(grid: np.ndarray, n_min: int = 20) -> np.ndarray:
    """bool (NROW, NCOL): the cell's 0.5 degree block has >= n_min target-group records in both periods."""
    ok = (block_sums(grid[1]) >= n_min) & (block_sums(grid[2]) >= n_min)
    return np.kron(ok.astype(np.uint8), np.ones((BLOCK, BLOCK), np.uint8)).astype(bool)


def lookup(grid: np.ndarray, rows, cols, n_min=(20, 100)) -> dict:
    """Per point (row, col): block counts of both periods and the well-sampled flags, without building full-size masks."""
    b1, b2 = block_sums(grid[1]), block_sums(grid[2])
    br, bc = np.asarray(rows) // BLOCK, np.asarray(cols) // BLOCK
    out = {"tg_block_p1": b1[br, bc], "tg_block_p2": b2[br, bc]}
    for n in n_min:
        out[f"ws{n}"] = (out["tg_block_p1"] >= n) & (out["tg_block_p2"] >= n)
    return out
