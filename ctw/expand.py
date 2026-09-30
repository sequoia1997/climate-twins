"""Expand data/world_targets.csv from the committed GeoNames snapshot (data/places_snapshot.json.gz).

Not part of the default workflow: run it by hand, review the diff, commit the CSV.

    python -m ctw.expand            # print the report, change nothing
    python -m ctw.expand --write    # append the selected places to data/world_targets.csv

Rules (same spirit as the original list: greedy by population with a minimum spacing that widens as population falls):
  1. Every country or territory the snapshot knows gets at least MIN_PER_COUNTRY places (largest first, at least
     SMALL_KM apart), so single-place countries are no longer a single point.
  2. Then places are added greedily by population. A candidate is accepted when it is at least
     spacing(population, region) km from every place already on the list. Regions in regions.PRIORITY (Africa,
     Latin America, Central Asia, Oceania, Middle East) use tighter spacing and lower population floors.
  3. Grid check: the 0.5 degree world grid ends at 60 S (config [grids] world_lat_min), and a place is kept only if its
     0.5 degree cell, or one of the eight around it, is a land cell of the world pool. Places on tiny islands that
     fail this (the original list has 17 such, e.g. Tarawa, Funafuti; TerraClimate's 1/24 degree pixels still
     cover them, but the 0.5 degree pool has no cell there) are added only to reach the per-country minimum, and are
     flagged in the report. Everything else that fails is dropped.
The land mask is read from site/data/world.dat (either data format) or, if present, work/results.npz."""
from __future__ import annotations
import argparse, csv, gzip, json, sys
import numpy as np
import pandas as pd
from . import common as C
from .regions import PRIORITY, region

MIN_PER_COUNTRY = 3
SMALL_KM = 10.0                     # minimum spacing inside the per-country minimum (small island states, city states)
DUP_KM = 6.0                        # a candidate this close to an existing place is the same town
LAT_MIN = -60.0

# (population floor, spacing km): the first row whose floor the population reaches gives the spacing;
# below the last floor a place is not considered. Tuned to add about 700-800 places.
TIERS_PRIORITY = [(300_000, 70), (100_000, 125), (40_000, 195), (15_000, 285), (5_000, 400)]
TIERS_OTHER = [(1_000_000, 80), (300_000, 170), (100_000, 300), (40_000, 480)]

# Countries and territories in the snapshot that are not in the original CSV (ISO codes for their snapshot names).
EXTRA_ISO = {"Slovakia": "SK", "Greenland": "GL", "French Guiana": "GF", "New Caledonia": "NC", "Palestine": "PS",
             "Hong Kong": "HK", "Réunion": "RE", "Faeroe Is.": "FO", "Åland": "AX", "Curaçao": "CW",
             "St. Pierre and Miquelon": "PM", "Isle of Man": "IM", "U.S. Virgin Is.": "VI", "Falkland Is.": "FK",
             "Montserrat": "MS", "Turks and Caicos Is.": "TC"}


def land_mask() -> np.ndarray:
    """(360, 720) boolean: cells of the world pool (rows from 90 N, columns from 180 W)."""
    r = C.WORK / "results.npz"
    if r.exists():
        z = np.load(r, allow_pickle=True)
        m = np.zeros(360 * 720, bool); m[z["w_cells"]] = True
        return m.reshape(360, 720)
    raw = gzip.decompress((C.SITE / "data" / "world.dat").read_bytes())
    n = int.from_bytes(raw[4:8], "little")
    h = json.loads(raw[8:8 + n])
    o, ln, _ = h["mask"]["$b"]
    bits = np.unpackbits(np.frombuffer(raw[8 + n + o:8 + n + o + ln], np.uint8))[:360 * 720]
    return bits.reshape(360, 720).astype(bool)


def grid_class(mask, lat, lon) -> np.ndarray:
    """2 = own 0.5 degree cell is a pool cell, 1 = a neighbouring cell is, 0 = neither (tiny island or open sea)."""
    r = np.clip(np.floor((90 - np.asarray(lat)) / 0.5).astype(int), 0, 359)
    c = np.clip(np.floor((np.asarray(lon) + 180) / 0.5).astype(int), 0, 719)
    pad = np.pad(mask, ((1, 1), (0, 0)))
    pad = np.concatenate([pad[:, -1:], pad, pad[:, :1]], axis=1)       # longitude wraps
    nb = np.zeros(len(r), bool)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            nb |= pad[r + 1 + dr, c + 1 + dc]
    return np.where(mask[r, c], 2, np.where(nb, 1, 0))


def spacing(pop, reg) -> float | None:
    for floor, km in (TIERS_PRIORITY if reg in PRIORITY else TIERS_OTHER):
        if pop >= floor:
            return float(km)
    return None


def candidates(existing: pd.DataFrame) -> pd.DataFrame:
    snap = json.load(gzip.open(C.DATA / "places_snapshot.json.gz", "rt"))
    n2i = dict(zip(existing.country_name, existing.country)) | EXTRA_ISO
    rows = []
    for label, lat, lon, pop in snap["world"]:
        cn = label.rsplit(", ", 1)[-1]
        iso = n2i.get(cn)
        if iso is None or iso in ("US", "CA", "MX") or lat < LAT_MIN:        # North American labels carry state codes
            continue
        rows.append((label, iso, cn, "", round(lat, 5), round(lon, 5), int(pop), False))
    c = pd.DataFrame(rows, columns=list(existing.columns))
    c = c[~c.label.isin(set(existing.label))]
    return c.sort_values(["pop", "label"], ascending=[False, True], kind="stable").reset_index(drop=True)


def select(existing: pd.DataFrame, cand: pd.DataFrame, mask) -> tuple[pd.DataFrame, dict]:
    cand = cand.assign(grid=grid_class(mask, cand.lat.values, cand.lon.values),
                       reg=[region(i, la) for i, la in zip(cand.country, cand.lat)])
    lat = list(existing.lat); lon = list(existing.lon)
    have = dict(existing.country.value_counts())
    names = set(existing.label)
    picked, flagged, dropped = [], [], []
    la_a, lo_a = cand.lat.values, cand.lon.values
    # a candidate that is the same town as an existing place (different spelling) is never picked
    near_ex = np.zeros(len(cand), bool)
    for la, lo in zip(existing.lat, existing.lon):
        near_ex |= C.haversine_km(la, lo, la_a, lo_a) < DUP_KM
    ok_name = ~cand.label.isin(names).values & ~near_ex

    def far(k, km):
        if not lat:
            return True
        return bool((C.haversine_km(la_a[k], lo_a[k], np.array(lat), np.array(lon)) >= km).all())

    def take(k, why):
        lat.append(la_a[k]); lon.append(lo_a[k]); names.add(cand.label[k])
        have[cand.country[k]] = have.get(cand.country[k], 0) + 1
        picked.append((k, why))
        ok_name[k] = False

    # 1. minimum per country: largest first, on land cells first, tiny islands only if nothing else is left
    for iso in sorted(set(cand.country) | set(existing.country)):
        for allow_tiny in (False, True):
            for k in np.where((cand.country == iso).values & ok_name)[0]:
                if have.get(iso, 0) >= MIN_PER_COUNTRY:
                    break
                g = cand.grid[k]
                if g == 0 and not allow_tiny:
                    continue
                if far(k, SMALL_KM):
                    take(k, "minimum")
                    if g == 0:
                        flagged.append(k)
    # 2. greedy by population with region-dependent spacing
    for k in range(len(cand)):
        if not ok_name[k]:
            continue
        km = spacing(int(cand["pop"][k]), cand.reg[k])
        if km is None:
            continue
        if cand.grid[k] == 0:
            dropped.append(k)
            continue
        if far(k, km):
            take(k, "spacing")
    out = cand.loc[[k for k, _ in picked], list(existing.columns)].reset_index(drop=True)
    info = dict(flagged=cand.loc[flagged, ["label", "lat", "lon", "pop"]], dropped=cand.loc[dropped, ["label", "lat", "lon", "pop"]],
                reasons=[w for _, w in picked], reg=cand.reg[[k for k, _ in picked]].tolist(), grid=cand.grid[[k for k, _ in picked]].tolist())
    return out, info


def report(existing, new, info):
    allp = pd.concat([existing, new], ignore_index=True)
    cnt = allp.country.value_counts()
    print(f"existing {len(existing)}, added {len(new)}, total {len(allp)}; countries {allp.country.nunique()} "
          f"(was {existing.country.nunique()}); with fewer than {MIN_PER_COUNTRY} places: {int((cnt < MIN_PER_COUNTRY).sum())} "
          f"{sorted(cnt[cnt < MIN_PER_COUNTRY].index)}")
    print("added by region:", pd.Series(info["reg"]).value_counts().to_dict())
    print("added by rule:", pd.Series(info["reasons"]).value_counts().to_dict())
    print("added on own land cell / coastal neighbour / tiny island:", {int(k): v for k, v in pd.Series(info["grid"]).value_counts().items()})
    print("tiny islands kept only for the per-country minimum (no pool cell within 0.5 degrees):")
    print(info["flagged"].to_string(index=False) if len(info["flagged"]) else "  none")
    print(f"candidates dropped for having no land cell nearby: {len(info['dropped'])}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ctw.expand")
    ap.add_argument("--write", action="store_true", help="append the selection to data/world_targets.csv")
    a = ap.parse_args(argv)
    path = C.DATA / "world_targets.csv"
    ex = pd.read_csv(path, keep_default_na=False)
    new, info = select(ex, candidates(ex), land_mask())
    report(ex, new, info)
    if a.write:
        with open(path, "a", newline="") as f:
            w = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
            for r in new.itertuples(index=False):
                w.writerow([r.label, r.country, r.country_name, r.admin1, r.lat, r.lon, r.pop, r.capital])
        print("appended", len(new), "rows to", path)
    return new


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
