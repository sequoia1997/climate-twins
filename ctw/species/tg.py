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
GROUPS = {   # target group -> SQL taxon condition. By NAME: in GBIF's SQL downloads the integer backbone keys (212, 359, ...) match nothing
    # (first attempt: 0 rows, diagnostic run 38077633418 with speciesKey = 2182727 also 0 rows), so class / phylum names are used.
    "bird": "class = 'Aves'",
    "mammal": "class = 'Mammalia'",
    "insect_arachnid": "class IN ('Insecta', 'Arachnida')",
    "plant": "phylum = 'Tracheophyta'",
}
PILOT_GROUP_TO_TG = {"bird": "bird", "mammal": "mammal", "insect_arachnid": "insect_arachnid", "tree": "plant", "crop": "plant"}


BASIS_OK = {"HUMAN_OBSERVATION", "PRESERVED_SPECIMEN", "OBSERVATION", "MACHINE_OBSERVATION"}


def sql_for(group: str, year_q: str = '"year"') -> str:
    """Only the taxon is filtered by GBIF's SQL engine; licence, basis, geospatial issue, status, uncertainty and the year range are grouping
    columns and are applied in `parse_tsv_zip`, so a wrong guess at a value format cannot empty the result again."""
    ex = ["FLOOR((90 - decimalLatitude) * 24)", "FLOOR((decimalLongitude + 180) * 24)",
          f"IF({year_q} < 1970, 0, IF({year_q} <= 1999, 1, IF({year_q} <= 2020, 2, 3)))",
          "IF(coordinateUncertaintyInMeters IS NULL OR coordinateUncertaintyInMeters <= 10000, 1, 0)"]
    cols = ["license", "basisOfRecord", "hasGeospatialIssues", "occurrenceStatus"]
    sel = f"{ex[0]} AS r, {ex[1]} AS c, {ex[2]} AS p, {ex[3]} AS u, " + ", ".join(cols) + ", COUNT(*) AS n"
    return f"SELECT {sel} FROM occurrence WHERE {GROUPS[group]} GROUP BY " + ", ".join(ex + cols)


def keep_rows(df):
    """Boolean mask of the rows that pass the pilot filter, and the distinct values seen (for the audit trail)."""
    import pandas as pd
    df.columns = [c.lower() for c in df.columns]
    seen = {c: sorted(map(str, df[c].dropna().unique()))[:30] for c in ("license", "basisofrecord", "hasgeospatialissues", "occurrencestatus") if c in df}
    ok = df["r"].notna() & df["c"].notna() & df["p"].isin([1, 2])
    if "u" in df:
        ok &= df["u"] == 1
    if "license" in df:
        lic = df["license"].astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
        ok &= (lic.str.contains("CC0") | lic.str.contains("CCBY4") | lic.str.contains("CCBY40") | lic.isin(["CCBY"])) & ~lic.str.contains("NC")
    if "basisofrecord" in df:
        ok &= df["basisofrecord"].astype(str).str.upper().isin(BASIS_OK)
    if "hasgeospatialissues" in df:
        ok &= df["hasgeospatialissues"].astype(str).str.lower().isin(["false", "0"])
    if "occurrencestatus" in df:
        ok &= df["occurrencestatus"].astype(str).str.upper() == "PRESENT"
    return ok, seen


def parse_tsv_zip(data: bytes | str, with_seen: bool = False):
    """Read the SQL download (zip with one TSV: r, c, p, u, license, ..., n) into uint32 (3, NROW, NCOL): [all, 1970-1999, 2000-2020]."""
    import pandas as pd
    z = zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data)
    name = [n for n in z.namelist() if not n.endswith("/")][0]
    df = pd.read_csv(z.open(name), sep="\t", low_memory=False)
    ok, seen = keep_rows(df)
    d = df[ok]
    g = grid_from_rows(d["r"].to_numpy(), d["c"].to_numpy(), d["p"].to_numpy(), d["n"].to_numpy())
    return (g, seen, int(len(df))) if with_seen else g


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
