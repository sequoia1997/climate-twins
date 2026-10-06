"""Occurrence cleaning for species distribution modelling (CoordinateCleaner-style, self-contained).

Input: a DataFrame with GBIF columns (lower case, as in GBIF's SIMPLE_PARQUET / SIMPLE_CSV downloads):
  decimallatitude, decimallongitude, coordinateuncertaintyinmeters, countrycode, eventdate, recordedby, datasetkey,
  establishmentmeans, basisofrecord. Missing optional columns are tolerated.

Steps, in order (each one's loss is recorded in Cleaner.report()):
  coords        finite and in range; drops (0, 0) "null island" (both |value| < 0.0001), lat == lon, and points whose latitude and
                longitude are both whole degrees (typical of coarse or converted coordinates)
  uncertainty   drops coordinateuncertaintyinmeters > max_unc_m (default 10 km); a missing value is kept
  centroids     drops points within a radius of a reference point: country centroids (default 1 km), capitals (2 km, CoordinateCleaner
                uses 10 km, too harsh for city-dwelling birds) and biodiversity institutions (100 m); the reference table is passed in
  land          drops points on no land cell of the 0.5 degree world pool and with no land neighbour (ocean / open sea); for land species
  establishment for kind "tree" and "crop": drops MANAGED / CULTIVATED, and (drop_introduced) INTRODUCED / NATURALISED / INVASIVE records;
                mode "flag" keeps them and adds a bool column `escaped`; mode "off" skips the step (animals: default)
  duplicates    drops exact repeats of (rounded coordinates, event date, recorder, dataset), which are the same observation sent twice
  thin          one record per 2.5 arc-minute cell (1/24 degree, ~4.5 km at the equator), keeping the one with the smallest uncertainty

The row-level steps work chunk by chunk (feed), so a download of tens of millions of records never has to sit in memory with all
its columns; duplicates and thinning run once at the end (finish) on the compact survivors (latitude, longitude, cell, hash)."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

CELL_DEG = 2.5 / 60.0                       # 2.5 arc-minutes
NCOL = int(round(360 / CELL_DEG))           # 8640
NROW = int(round(180 / CELL_DEG))           # 4320
EARTH_M = 6_371_008.8
RADIUS_M = {"country": 1000.0, "capital": 2000.0, "institution": 100.0}
MANAGED = {"MANAGED", "CULTIVATED"}
INTRODUCED = {"INTRODUCED", "NATURALISED", "NATURALIZED", "INVASIVE"}
STEPS = ["input", "coords", "uncertainty", "centroids", "land", "establishment", "duplicates", "thin"]


def cell_id(lat, lon) -> np.ndarray:
    """int64 id of the 2.5' cell: row from the south pole, column from 180 W. Clipped so lat 90 / lon 180 fall in the last cell."""
    r = np.clip(np.floor((np.asarray(lat, float) + 90.0) / CELL_DEG).astype(np.int64), 0, NROW - 1)
    c = np.clip(np.floor((np.asarray(lon, float) + 180.0) / CELL_DEG).astype(np.int64), 0, NCOL - 1)
    return r * NCOL + c


def cell_center(cid) -> tuple[np.ndarray, np.ndarray]:
    cid = np.asarray(cid, np.int64)
    return (cid // NCOL + 0.5) * CELL_DEG - 90.0, (cid % NCOL + 0.5) * CELL_DEG - 180.0


def _xyz(lat, lon) -> np.ndarray:
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def _chord(metres: float) -> float:
    return 2.0 * math.sin(min(metres / EARTH_M, math.pi) / 2.0)


def near_reference(lat, lon, ref: pd.DataFrame, radius_m: dict | None = None) -> np.ndarray:
    """bool array: the point lies within the kind's radius of any reference point. ref has columns lat, lon, kind."""
    out = np.zeros(len(lat), bool)
    if ref is None or len(ref) == 0 or len(lat) == 0:
        return out
    radius_m = {**RADIUS_M, **(radius_m or {})}
    pts = _xyz(lat, lon)
    for kind, g in ref.groupby("kind"):
        tree = cKDTree(_xyz(g["lat"].to_numpy(), g["lon"].to_numpy()))
        d, _ = tree.query(pts, k=1, distance_upper_bound=_chord(radius_m.get(kind, 1000.0)) * 1.0000001)
        out |= np.isfinite(d)
    return out


def land_mask_default() -> np.ndarray:
    from ..expand import land_mask          # imported late: it pulls in the whole pipeline
    return land_mask()


def on_land(lat, lon, mask: np.ndarray) -> np.ndarray:
    """True where the point's 0.5 degree cell, or a neighbour, is a land cell of `mask` ((360, 720), rows from 90 N, columns from 180 W).
    The neighbour allowance keeps coastal records whose coordinates round into the sea (the pool is itself coarse)."""
    from ..expand import grid_class
    return grid_class(mask, lat, lon) >= 1


def _hash(df: pd.DataFrame) -> np.ndarray:
    key = pd.DataFrame({
        "a": np.round(df["decimallatitude"].to_numpy(float), 5), "b": np.round(df["decimallongitude"].to_numpy(float), 5),
        "d": df["eventdate"].astype(str).to_numpy() if "eventdate" in df else "",
        "r": df["recordedby"].astype(str).to_numpy() if "recordedby" in df else "",
        "s": df["datasetkey"].astype(str).to_numpy() if "datasetkey" in df else ""})
    return pd.util.hash_pandas_object(key, index=False).to_numpy()


class Cleaner:
    """Feed it chunks of one species' records, then call finish().

    kind: "tree" | "crop" | "animal" | "plant" (decides the establishment step); land: (360, 720) bool mask or None to skip the land step;
    ref: reference points (lat, lon, kind) or None; establishment: "drop" | "flag" | "off" or None for the kind's default."""

    def __init__(self, kind="animal", land=None, ref=None, max_unc_m=10_000.0, establishment=None, drop_introduced=True,
                 radius_m=None):
        self.kind, self.land, self.ref, self.max_unc_m = kind, land, ref, max_unc_m
        self.establishment = establishment or ("drop" if kind in ("tree", "crop") else "off")
        self.drop_introduced, self.radius_m = drop_introduced, radius_m
        self.n = dict.fromkeys(STEPS, 0)
        self.n["input"] = 0
        self._after = {s: 0 for s in STEPS}
        self._parts: list[pd.DataFrame] = []
        self._finished = False

    def _count(self, step, kept):
        self._after[step] += int(kept)

    def feed(self, df: pd.DataFrame) -> None:
        self.n["input"] += len(df)
        self._after["input"] += len(df)
        lat = pd.to_numeric(df["decimallatitude"], errors="coerce").to_numpy(float)
        lon = pd.to_numeric(df["decimallongitude"], errors="coerce").to_numpy(float)
        unc = (pd.to_numeric(df["coordinateuncertaintyinmeters"], errors="coerce").to_numpy(float)
               if "coordinateuncertaintyinmeters" in df else np.full(len(df), np.nan))
        df = df.assign(decimallatitude=lat, decimallongitude=lon, coordinateuncertaintyinmeters=unc)
        # 1 coordinate sanity
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
            ok &= ~((np.abs(lat) < 1e-4) & (np.abs(lon) < 1e-4))
            ok &= ~(lat == lon)
            ok &= ~((lat == np.round(lat)) & (lon == np.round(lon)))
        df = df[ok]; self._count("coords", len(df))
        # 2 uncertainty
        with np.errstate(invalid="ignore"):
            keep = ~(df["coordinateuncertaintyinmeters"].to_numpy() > self.max_unc_m)
        df = df[keep]; self._count("uncertainty", len(df))
        # 3 centroids / capitals / institutions
        if self.ref is not None and len(df):
            df = df[~near_reference(df["decimallatitude"].to_numpy(), df["decimallongitude"].to_numpy(), self.ref, self.radius_m)]
        self._count("centroids", len(df))
        # 4 land
        if self.land is not None and len(df):
            df = df[on_land(df["decimallatitude"].to_numpy(), df["decimallongitude"].to_numpy(), self.land)]
        self._count("land", len(df))
        # 5 establishment means
        est = (df["establishmentmeans"].astype(str).str.upper() if "establishmentmeans" in df
               else pd.Series("", index=df.index))
        bad = est.isin(MANAGED | INTRODUCED) if self.drop_introduced else est.isin(MANAGED)
        df = df.assign(escaped=bad.to_numpy())
        if self.establishment == "drop":
            df = df[~df["escaped"].to_numpy()]
        self._count("establishment", len(df))
        # compact survivors; duplicates and thinning need all chunks
        part = pd.DataFrame({
            "lat": df["decimallatitude"].to_numpy(np.float64), "lon": df["decimallongitude"].to_numpy(np.float64),
            "unc": df["coordinateuncertaintyinmeters"].to_numpy(np.float32),
            "cell": cell_id(df["decimallatitude"].to_numpy(), df["decimallongitude"].to_numpy()),
            "hash": _hash(df), "escaped": df["escaped"].to_numpy(bool)})
        if "countrycode" in df:
            part["countrycode"] = df["countrycode"].astype("string").to_numpy()
        self._parts.append(part.reset_index(drop=True))

    def finish(self) -> pd.DataFrame:
        """Duplicates, then thinning. Returns one row per 2.5' cell: lat, lon (the kept record's), cell, unc, escaped, countrycode."""
        if self._parts:
            d = pd.concat(self._parts, ignore_index=True)
        else:
            d = pd.DataFrame({"lat": [], "lon": [], "unc": [], "cell": [], "hash": [], "escaped": []})
        self._parts = []
        d = d.drop_duplicates("hash")
        self._count("duplicates", len(d))
        d = d.assign(_u=d["unc"].fillna(np.inf)).sort_values(["cell", "_u"], kind="stable").drop_duplicates("cell").drop(columns=["_u", "hash"])
        self._count("thin", len(d))
        self._finished = True
        return d.reset_index(drop=True)

    def report(self) -> list[dict]:
        """One row per step: records left after it and the records it removed."""
        rows, prev = [], None
        for s in STEPS:
            left = self._after[s]
            rows.append({"step": s, "left": left, "removed": 0 if prev is None else prev - left})
            prev = left
        return rows


def clean(df: pd.DataFrame, **kw) -> tuple[pd.DataFrame, list[dict]]:
    """One-shot form of Cleaner for data that fits in memory."""
    c = Cleaner(**kw)
    c.feed(df)
    out = c.finish()
    return out, c.report()


def continent_counts(df: pd.DataFrame, continent_of: dict) -> dict:
    """Records per continent from a country-code column and an ISO2 -> continent table; missing codes count as 'Unknown'."""
    if "countrycode" not in df:
        return {"Unknown": int(len(df))}
    c = df["countrycode"].map(continent_of).fillna("Unknown")
    return {k: int(v) for k, v in c.value_counts().items()}


def reference_points(world_targets_csv, countries_geojson=None, institutions=None) -> pd.DataFrame:
    """Reference table (lat, lon, kind). Capitals come from data/world_targets.csv (capital == True). Country centroids come from a
    Natural Earth geojson (centroid of the whole country and of its largest part); institutions is an optional DataFrame (lat, lon)."""
    rows = []
    wt = pd.read_csv(world_targets_csv)
    cap = wt[wt["capital"].astype(str).str.lower() == "true"]
    rows += [(la, lo, "capital") for la, lo in zip(cap["lat"], cap["lon"])]
    if countries_geojson:
        from shapely.geometry import shape
        for f in countries_geojson["features"]:
            g = shape(f["geometry"])
            c = g.centroid
            rows.append((c.y, c.x, "country"))
            if g.geom_type == "MultiPolygon":
                c = max(g.geoms, key=lambda p: p.area).centroid
                rows.append((c.y, c.x, "country"))
    if institutions is not None and len(institutions):
        rows += [(la, lo, "institution") for la, lo in zip(institutions["lat"], institutions["lon"])]
    return pd.DataFrame(rows, columns=["lat", "lon", "kind"])
