"""Occurrence records -> thinned cells on the TerraClimate native grid (workstream W2).

Input: the SIMPLE_PARQUET of one GBIF download (lower case columns). Output: one row per 1/24 degree cell (4320 x 8640, row 0 = north) with the
record count, earliest / latest year and per-period counts, plus a step-by-step loss report.

Row-level steps, in order (same checks as ctw/species/occ.py, spike A, but with the grid of the climate stack and a different duplicate rule):
  coords         finite, in range, not (0, 0), lat != lon, not both whole degrees
  uncertainty    coordinateuncertaintyinmeters > 10 km dropped (missing kept)
  centroids      near a country centroid (1 km), capital (2 km) or biodiversity institution (100 m)
  land           own 0.5 degree cell or a neighbour is in the land pool
  establishment  establishmentMeans INTRODUCED* / NATURALISED / INVASIVE / MANAGED / CULTIVATED / VAGRANT dropped
  year           a record without a year is dropped (the download already restricts year >= 1970)
  duplicates     the SAME record seen twice: same dataset and same occurrenceID (or, if the record has none, the same gbifID). Spike A used
                 (coordinates, date, recorder, dataset) which is an EVENT key: it removed 87% of the monarch records, but 99.97% of those
                 groups hold different occurrenceIDs (Monarch Watch tags, one record per tagged butterfly released at a site in a year).
                 Repeated events are kept as records and counted separately in `n_events`.
Then the cell table: n_records (after duplicates), n_events (distinct coordinates + date + recorder + dataset), year_min, year_max,
n_1970_1999, n_2000_2020, n_2021_plus.
"""
from __future__ import annotations
import glob, os
from pathlib import Path
import numpy as np
import pandas as pd
from . import occ

NROW, NCOL = 4320, 8640
RES = 1 / 24
COLS = ["gbifid", "decimallatitude", "decimallongitude", "coordinateuncertaintyinmeters", "eventdate", "recordedby", "datasetkey", "occurrenceid",
        "year", "month", "establishmentmeans", "countrycode", "basisofrecord", "license"]
STEPS = ["input", "coords", "uncertainty", "centroids", "land", "establishment", "year", "duplicates"]
DROP_EST = {"MANAGED", "CULTIVATED", "VAGRANT", "INVASIVE", "NATURALISED", "NATURALIZED"}
SEASONS = {   # breeding / winter calendar months by the hemisphere the species BREEDS in (scheme N = northern, S = southern)
    "N": {"breeding": (5, 6, 7), "winter": (12, 1, 2)},
    "S": {"breeding": (11, 12, 1), "winter": (6, 7, 8)},
}
P1 = (1970, 1999)
P2 = (2000, 2020)


def cell_index(lat, lon) -> np.ndarray:
    """int64 row * NCOL + col of the 1/24 degree cell (row 0 = north, column 0 = 180 W)."""
    r = np.clip(np.floor((90 - np.asarray(lat, float)) / RES).astype(np.int64), 0, NROW - 1)
    c = np.clip(np.floor((np.asarray(lon, float) + 180) / RES).astype(np.int64), 0, NCOL - 1)
    return r * NCOL + c


def parquet_files(folder: Path) -> list[str]:
    out = []
    for f in sorted(glob.glob(str(Path(folder) / "**" / "*"), recursive=True)):
        if os.path.isfile(f) and os.path.getsize(f) > 8:
            with open(f, "rb") as h:
                if h.read(4) == b"PAR1":
                    out.append(f)
    return out


def read_batches(folder: Path, batch_size: int = 1_000_000):
    """Yield pandas DataFrames with the columns of COLS that exist; recordedby (a list column in SIMPLE_PARQUET) is joined into one string."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    for f in parquet_files(folder):
        pf = pq.ParquetFile(f)
        have = {n.lower(): n for n in pf.schema_arrow.names}
        want = [have[c] for c in COLS if c in have]
        for b in pf.iter_batches(batch_size=batch_size, columns=want):
            t = pa.Table.from_batches([b])
            t = t.rename_columns([n.lower() for n in t.column_names])
            if "recordedby" in t.column_names and pa.types.is_list(t.schema.field("recordedby").type):
                j = pc.binary_join(t["recordedby"].cast(pa.list_(pa.string())), "|")
                t = t.set_column(t.column_names.index("recordedby"), "recordedby", j)
            yield t.to_pandas()


def _hash(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return pd.util.hash_pandas_object(df[cols], index=False).to_numpy()


class CellCleaner:
    """Feed it chunks of one species' records, then call finish() -> (cells, report)."""

    def __init__(self, land=None, ref=None, max_unc_m=10_000.0, radius_m=None, keep_cultivated=False):
        """keep_cultivated: crops are modelled where they are cultivated, so the establishmentMeans step only counts, never drops."""
        self.land, self.ref, self.max_unc_m, self.radius_m = land, ref, max_unc_m, radius_m
        self.keep_cultivated = keep_cultivated
        self.keep_months = False          # set True to keep the month of each record for finish_seasonal()
        self._deduped = None
        self.datasets: dict[str, int] = {}
        self.cultivated_seen = 0          # records with establishmentMeans MANAGED or CULTIVATED (kept for crops, dropped otherwise)
        self.left = dict.fromkeys(STEPS, 0)
        self.est_dropped: dict[str, int] = {}
        self.licences: dict[str, int] = {}
        self.countries: dict[str, int] = {}
        self._parts: list[pd.DataFrame] = []

    def feed(self, df: pd.DataFrame) -> None:
        L = self.left
        L["input"] += len(df)
        if "license" in df:
            for k, v in df["license"].value_counts().items():
                self.licences[str(k)] = self.licences.get(str(k), 0) + int(v)
        lat = pd.to_numeric(df["decimallatitude"], errors="coerce").to_numpy(float)
        lon = pd.to_numeric(df["decimallongitude"], errors="coerce").to_numpy(float)
        unc = (pd.to_numeric(df["coordinateuncertaintyinmeters"], errors="coerce").to_numpy(float)
               if "coordinateuncertaintyinmeters" in df else np.full(len(df), np.nan))
        df = df.assign(decimallatitude=lat, decimallongitude=lon, coordinateuncertaintyinmeters=unc)
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
            ok &= ~((np.abs(lat) < 1e-4) & (np.abs(lon) < 1e-4)) & ~(lat == lon) & ~((lat == np.round(lat)) & (lon == np.round(lon)))
        df = df[ok]; L["coords"] += len(df)
        with np.errstate(invalid="ignore"):
            df = df[~(df["coordinateuncertaintyinmeters"].to_numpy() > self.max_unc_m)]
        L["uncertainty"] += len(df)
        if self.ref is not None and len(df):
            df = df[~occ.near_reference(df["decimallatitude"].to_numpy(), df["decimallongitude"].to_numpy(), self.ref, self.radius_m)]
        L["centroids"] += len(df)
        if self.land is not None and len(df):
            df = df[occ.on_land(df["decimallatitude"].to_numpy(), df["decimallongitude"].to_numpy(), self.land)]
        L["land"] += len(df)
        if "establishmentmeans" in df and len(df):
            est = df["establishmentmeans"].astype("string").str.upper().fillna("")
            bad = est.isin(DROP_EST) | est.str.startswith("INTRODUCED")
            self.cultivated_seen += int(est.isin({"MANAGED", "CULTIVATED"}).sum())
            for k, v in est[bad].value_counts().items():
                self.est_dropped[str(k)] = self.est_dropped.get(str(k), 0) + int(v)
            if not self.keep_cultivated:
                df = df[~bad.to_numpy()]
        L["establishment"] += len(df)
        yr = pd.to_numeric(df["year"], errors="coerce") if "year" in df else pd.Series(np.nan, index=df.index)
        df = df[yr.notna().to_numpy()]; yr = yr[yr.notna()]
        L["year"] += len(df)
        if not len(df):
            return
        if "datasetkey" in df:
            for k, v in df["datasetkey"].value_counts().items():
                self.datasets[str(k)] = self.datasets.get(str(k), 0) + int(v)
        d = pd.DataFrame({"lat5": np.round(df["decimallatitude"].to_numpy(), 5), "lon5": np.round(df["decimallongitude"].to_numpy(), 5),
                          "ev": df["eventdate"].astype("string").fillna("").to_numpy() if "eventdate" in df else "",
                          "rec": df["recordedby"].astype("string").fillna("").to_numpy() if "recordedby" in df else "",
                          "ds": df["datasetkey"].astype("string").fillna("").to_numpy() if "datasetkey" in df else "",
                          "oid": df["occurrenceid"].astype("string").fillna("").to_numpy() if "occurrenceid" in df else "",
                          "gid": df["gbifid"].astype("string").fillna("").to_numpy() if "gbifid" in df else ""})
        d["identity"] = np.where(d["oid"].to_numpy() != "", d["oid"].to_numpy(), "gbif:" + d["gid"].to_numpy().astype(str))
        part = pd.DataFrame({"cell": cell_index(df["decimallatitude"].to_numpy(), df["decimallongitude"].to_numpy()).astype(np.int32),
                             "month": (pd.to_numeric(df["month"], errors="coerce").fillna(0).clip(0, 12).to_numpy().astype(np.int8) if "month" in df else np.zeros(len(df), np.int8)),
                             "year": yr.to_numpy().astype(np.int16), "hid": _hash(d, ["ds", "identity"]), "hev": _hash(d, ["lat5", "lon5", "ev", "rec", "ds"])})
        if "countrycode" in df:
            for k, v in df["countrycode"].value_counts().items():
                self.countries[str(k)] = self.countries.get(str(k), 0) + int(v)
        self._parts.append(part.reset_index(drop=True))

    def finish(self) -> tuple[pd.DataFrame, dict]:
        cols = ["cell", "year", "month", "hid", "hev"]
        d = pd.concat(self._parts, ignore_index=True) if self._parts else pd.DataFrame({c: [] for c in cols})
        self._parts = []
        d = d.drop_duplicates("hid")
        self.left["duplicates"] = len(d)
        if self.keep_months:
            self._deduped = d[["cell", "year", "month"]].copy()
        ev = d.drop_duplicates(["cell", "hev"]).groupby("cell").size().rename("n_events")
        y = d["year"].to_numpy()
        d = d.assign(p1=(y >= P1[0]) & (y <= P1[1]), p2=(y >= P2[0]) & (y <= P2[1]), p3=y > P2[1])
        g = d.groupby("cell")
        cells = g.agg(year_min=("year", "min"), year_max=("year", "max"), n_records=("year", "size"),
                      n_1970_1999=("p1", "sum"), n_2000_2020=("p2", "sum"), n_2021_plus=("p3", "sum")).join(ev).reset_index()
        cells["row"] = (cells["cell"] // NCOL).astype(np.int16)
        cells["col"] = (cells["cell"] % NCOL).astype(np.int16)
        cells["lat"] = (90 - (cells["row"].astype(float) + 0.5) * RES).round(6)
        cells["lon"] = (-180 + (cells["col"].astype(float) + 0.5) * RES).round(6)
        for c in ("n_events", "n_1970_1999", "n_2000_2020", "n_2021_plus", "n_records"):
            cells[c] = cells[c].fillna(0).astype(np.int32)
        cells["year_min"] = cells["year_min"].astype(np.int16)
        cells["year_max"] = cells["year_max"].astype(np.int16)
        cells = cells[["row", "col", "lat", "lon", "year_min", "year_max", "n_records", "n_events", "n_1970_1999", "n_2000_2020", "n_2021_plus"]]
        rep = self.report()
        rep["n_cells"] = int(len(cells))
        rep["n_events"] = int(cells["n_events"].sum())
        return cells.sort_values(["row", "col"], ignore_index=True), rep

    def finish_seasonal(self, scheme: str = "N") -> pd.DataFrame:
        """Per-cell month counts (m01..m12, m00 = record without month) and season counts for the deduplicated records of the SAME cells that
        finish() returned. Needs keep_months = True before feed(). Season counts: n_breeding, n_winter, and per period (1970-1999, 2000-2020)."""
        d = self._deduped
        if d is None:
            raise RuntimeError("set keep_months = True before feeding")
        sc = SEASONS[scheme]
        mo = d["month"].to_numpy()
        y = d["year"].to_numpy()
        out = pd.DataFrame({"cell": d["cell"].to_numpy()})
        for m in range(0, 13):
            out[f"m{m:02d}"] = (mo == m)
        br, wi = np.isin(mo, sc["breeding"]), np.isin(mo, sc["winter"])
        p1, p2 = (y >= P1[0]) & (y <= P1[1]), (y >= P2[0]) & (y <= P2[1])
        out["n_breeding"], out["n_winter"] = br, wi
        out["n_breeding_1970_1999"], out["n_breeding_2000_2020"] = br & p1, br & p2
        out["n_winter_1970_1999"], out["n_winter_2000_2020"] = wi & p1, wi & p2
        g = out.groupby("cell").sum().astype(np.int32).reset_index()
        g["row"] = (g["cell"] // NCOL).astype(np.int16)
        g["col"] = (g["cell"] % NCOL).astype(np.int16)
        g["lat"] = (90 - (g["row"].astype(float) + 0.5) * RES).round(6)
        g["lon"] = (-180 + (g["col"].astype(float) + 0.5) * RES).round(6)
        g["season_scheme"] = scheme
        first = ["row", "col", "lat", "lon", "season_scheme"]
        return g[first + [c for c in g.columns if c not in first + ["cell"]]].sort_values(["row", "col"], ignore_index=True)

    def report(self) -> dict:
        steps, prev = [], None
        for s in STEPS:
            left = int(self.left[s])
            steps.append({"step": s, "left": left, "removed": 0 if prev is None else prev - left})
            prev = left
        return {"steps": steps, "establishment_dropped": {} if self.keep_cultivated else self.est_dropped, "licences_in_file": self.licences,
                "countries_in_file": dict(sorted(self.countries.items(), key=lambda kv: -kv[1])[:15]),
                "establishment_flagged_" + ("kept" if self.keep_cultivated else "dropped"): self.est_dropped, "keep_cultivated": self.keep_cultivated,
                "cultivated_managed_records": {"kept" if self.keep_cultivated else "dropped": int(self.cultivated_seen)}}


def institutions(cache: Path, tries: int = 6) -> pd.DataFrame:
    """Biodiversity institution coordinates from GBIF's registry (GRSciColl), with retries; cached as a CSV so every run uses the same list.
    Raises if the list cannot be completed (spike A silently used a partial list when the API dropped a connection)."""
    import time, requests
    f = Path(cache) / "grscicoll_institutions.csv"
    if f.exists():
        return pd.read_csv(f)
    rows, off = [], 0
    while True:
        for i in range(tries):
            try:
                r = requests.get("https://api.gbif.org/v1/grscicoll/institution", params={"limit": 1000, "offset": off}, timeout=120)
                r.raise_for_status()
                d = r.json()
                break
            except Exception:
                if i == tries - 1:
                    raise
                time.sleep(3 * (i + 1))
        for x in d.get("results", []):
            la, lo = x.get("latitude"), x.get("longitude")
            if la is None:
                a = x.get("address") or x.get("mailingAddress") or {}
                la, lo = a.get("latitude"), a.get("longitude")
            if la is not None and lo is not None:
                rows.append((float(la), float(lo)))
        if d.get("endOfRecords", True) or off >= 30000:
            break
        off += 1000
    df = pd.DataFrame(rows, columns=["lat", "lon"])
    f.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(f, index=False)
    return df


def reference_set(cache: Path) -> tuple[pd.DataFrame, np.ndarray]:
    """Centroid / capital / institution reference points and the 0.5 degree land pool, as in spike A."""
    import json
    from .. import common as C
    from . import native as N
    gj = json.load(open(N.fetch(N.NE_COUNTRIES, Path(cache) / "ne_50m_admin_0_countries.geojson")))
    inst = institutions(cache)
    ref = occ.reference_points(C.ROOT / "data" / "world_targets.csv", gj, inst)
    return ref, occ.land_mask_default()
