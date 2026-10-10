"""Native-range masks for the species pilot (workstream W2).

Everything is evaluated on the TerraClimate native grid (4320 x 8640 cells of 1/24 degree, row 0 = north, cell (r, c) has its centre at
lat 90 - (r + 0.5) / 24, lon -180 + (c + 0.5) / 24) by rasterising polygons into a label grid, so a mask is just a boolean (4320, 8640) array and
an occurrence cell is native when its (row, col) is True. The same raster is used for the cell test and for the published mask.

Which mask comes from where (the pilot report says so per species):
  CURATED   the `native_continents_curated` column of data/species/pilot_v1.csv (our judgement), turned into Natural Earth 1:50m map
            subunit polygons by `curated_units`. Used for every animal and as the fallback for a plant without a WCVP entry.
  DATA      plants: the Kew World Checklist of Vascular Plants (WCVP, CC BY 3.0) distribution, i.e. the TDWG WGSRPD level 3 "botanical
            countries" where the accepted species is recorded native (not introduced, not extinct, not doubtful). Polygons: the TDWG
            WGSRPD level 3 geojson. Used as the final mask of every plant it covers; the curated mask is then only a cross-check.
  CHECK     animals and plants: the Global Register of Introduced and Invasive Species (GRIIS, via the GBIF checklist datasets) lists
            countries where the species is introduced. Cells in such a country get the flag `griis_intro`; they are NOT removed by it
            (the register can be wrong about parts of a country and is incomplete), only reported.
Cells outside every polygon but within `FILL_CELLS` cells (about 0.15 degrees, 15 km) of one take that polygon's label, so coastal records whose
centre falls in the sea are not lost.
"""
from __future__ import annotations
import json, re
from pathlib import Path
import numpy as np

NROW, NCOL = 4320, 8640
RES = 1 / 24
FILL_CELLS = 3.6
NE_SUBUNITS = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_map_subunits.geojson"
NE_COUNTRIES = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
TDWG_L3 = "https://raw.githubusercontent.com/tdwg/wgsrpd/master/geojson/level3.geojson"
WCVP_ZIP = "https://sftp.kew.org/pub/data-repositories/WCVP/wcvp.zip"
CONTINENT = {"NORTH_AMERICA": "North America", "SOUTH_AMERICA": "South America", "EUROPE": "Europe", "ASIA": "Asia",
             "AFRICA": "Africa", "OCEANIA": "Oceania"}
OCEANIA_N_LAT = -25.0          # "OCEANIA(N)": Oceania land north of 25 degrees S (northern Australia, New Guinea, Pacific islands)
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "species" / "native"


# --------------------------------------------------------------------------- grid helpers
def cell_centres():
    lat = 90 - (np.arange(NROW) + 0.5) * RES
    lon = -180 + (np.arange(NCOL) + 0.5) * RES
    return lat, lon


def rc(lat, lon):
    """Row (from the north) and column (from 180 W) of the 1/24 degree cell holding each point."""
    r = np.clip(np.floor((90 - np.asarray(lat, float)) / RES).astype(np.int64), 0, NROW - 1)
    c = np.clip(np.floor((np.asarray(lon, float) + 180) / RES).astype(np.int64), 0, NCOL - 1)
    return r, c


def centre(r, c):
    return 90 - (np.asarray(r) + 0.5) * RES, -180 + (np.asarray(c) + 0.5) * RES


def fetch(url: str, dest: Path, tries: int = 6) -> Path:
    import time, requests
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    for i in range(tries):
        try:
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return dest
        except Exception:
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"could not fetch {url}")


# --------------------------------------------------------------------------- label rasters
def label_raster(features: list, fill_cells: float = FILL_CELLS) -> np.ndarray:
    """uint16 (NROW, NCOL): 1 + index of the feature whose polygon holds the cell centre, 0 where none; cells with no polygon within
    `fill_cells` cells take the label of the nearest labelled cell if that is closer than `fill_cells`, else stay 0.
    Later features win overlaps, so list the larger polygons first if that matters."""
    from rasterio import features as rf
    from rasterio.transform import from_origin
    from scipy import ndimage
    tr = from_origin(-180.0, 90.0, RES, RES)
    shapes = [(f["geometry"], i + 1) for i, f in enumerate(features) if f.get("geometry")]
    lab = rf.rasterize(shapes, out_shape=(NROW, NCOL), transform=tr, fill=0, dtype="uint16", all_touched=False)
    if fill_cells > 0:
        empty = lab == 0
        d, (ri, ci) = ndimage.distance_transform_edt(empty, return_indices=True)
        near = empty & (d <= fill_cells)
        lab[near] = lab[ri[near], ci[near]]
    return lab


def subunits(cache: Path) -> list:
    return json.load(open(fetch(NE_SUBUNITS, cache / "ne_50m_admin_0_map_subunits.geojson")))["features"]


def tdwg_units(cache: Path) -> list:
    return json.load(open(fetch(TDWG_L3, cache / "tdwg_level3.geojson")))["features"]


# --------------------------------------------------------------------------- curated masks
def parse_spec(spec: str) -> list[tuple[str, str]]:
    """'NORTH_AMERICA;EUROPE;ASIA(W);AFRICA(N)' -> [('NORTH_AMERICA', ''), ('EUROPE', ''), ('ASIA', 'W'), ('AFRICA', 'N')]."""
    out = []
    for tok in re.split(r"[;,]", spec or ""):
        tok = tok.strip()
        if not tok:
            continue
        m = re.fullmatch(r"([A-Z_]+)(?:\(([A-Z]+)\))?", tok)
        if not m or m.group(1) not in CONTINENT:
            raise ValueError(f"unknown native spec token: {tok!r}")
        out.append((m.group(1), m.group(2) or ""))
    return out


def unit_matches(props: dict, token: tuple[str, str]) -> tuple[bool, bool]:
    """(unit is in the token's region, unit additionally needs the latitude test of OCEANIA(N))."""
    cont, q = token
    if props.get("CONTINENT") != CONTINENT[cont]:
        return False, False
    if not q:
        return True, False
    if cont == "ASIA" and q == "W":
        return props.get("SUBREGION") == "Western Asia" or props.get("ADM0_A3") == "IRN", False
    if cont == "AFRICA" and q == "N":
        return props.get("SUBREGION") == "Northern Africa", False
    if cont == "OCEANIA" and q == "N":
        return True, True
    raise ValueError(f"unsupported qualifier {cont}({q})")


def curated_mask(spec: str, feats: list, lab: np.ndarray) -> np.ndarray:
    """Boolean (NROW, NCOL) native mask from the curated continent spec, using the Natural Earth subunit label raster `lab`."""
    toks = parse_spec(spec)
    plain = np.zeros(len(feats) + 1, bool)
    lat_limited = np.zeros(len(feats) + 1, bool)
    for i, f in enumerate(feats):
        for t in toks:
            ok, needs_lat = unit_matches(f["properties"], t)
            if ok and not needs_lat:
                plain[i + 1] = True
            elif ok:
                lat_limited[i + 1] = True
    m = plain[lab]
    if lat_limited.any():
        lat, _ = cell_centres()
        m |= lat_limited[lab] & (lat[:, None] >= OCEANIA_N_LAT)
    return m


# --------------------------------------------------------------------------- plants: WCVP + TDWG
def build_wcvp_pilot(names: list[str], work: Path, out: Path | None = None) -> dict:
    """Extract the WCVP native / introduced TDWG level 3 areas of accepted species `names` from the Kew download (about 85 MB zip)."""
    import io, zipfile
    import pandas as pd
    z = fetch(WCVP_ZIP, work / "wcvp.zip")
    zf = zipfile.ZipFile(z)
    readme = [n for n in zf.namelist() if n.lower().startswith("readme")]
    nm = pd.read_csv(zf.open("wcvp_names.csv"), sep="|", usecols=["plant_name_id", "taxon_rank", "taxon_status", "taxon_name", "powo_id"],
                     low_memory=False)
    nm = nm[(nm.taxon_status == "Accepted") & (nm.taxon_rank == "Species") & nm.taxon_name.isin(names)]
    ds = pd.read_csv(zf.open("wcvp_distribution.csv"), sep="|", low_memory=False)
    ds = ds[ds.plant_name_id.isin(nm.plant_name_id)]
    res = {"_source": {"dataset": "WCVP: World Checklist of Vascular Plants (Govaerts R, ed.), Royal Botanic Gardens, Kew, v16 extracted 2026-06-04",
                       "doi": "10.34885/egs6-cp24", "licence": "CC BY 3.0 (README_WCVP.xlsx of wcvp.zip)", "url": WCVP_ZIP,
                       "readme_in_zip": readme, "rule": "native = introduced 0, extinct 0, location_doubtful 0; areas are TDWG WGSRPD level 3 codes"}}
    for _, r in nm.iterrows():
        d = ds[ds.plant_name_id == r.plant_name_id]
        nat = d[(d.introduced == 0) & (d.extinct == 0) & (d.location_doubtful == 0)]
        res[r.taxon_name] = {"plant_name_id": int(r.plant_name_id), "powo_id": r.powo_id, "native": sorted(nat.area_code_l3),
                             "introduced": sorted(d[d.introduced == 1].area_code_l3), "extinct_or_doubtful_native": sorted(
                                 d[(d.introduced == 0) & ((d.extinct == 1) | (d.location_doubtful == 1))].area_code_l3)}
    if out:
        Path(out).write_text(json.dumps(res, indent=1))
    return res


def tdwg_mask(codes: list[str], feats: list, lab: np.ndarray) -> np.ndarray:
    sel = np.zeros(len(feats) + 1, bool)
    cs = set(codes)
    for i, f in enumerate(feats):
        if f["properties"].get("LEVEL3_COD") in cs:
            sel[i + 1] = True
    return sel[lab]


# --------------------------------------------------------------------------- GRIIS via GBIF checklist datasets
def build_griis_pilot(names: list[str], out: Path | None = None) -> dict:
    """For each name, the GRIIS checklists (GBIF datasets titled 'Global Register of Introduced and Invasive Species ...') that list it, with the
    distribution record (country, locality, establishmentMeans, status). Needs api.gbif.org (no login)."""
    import time, requests
    api = "https://api.gbif.org/v1"

    def get(path, **p):
        for i in range(6):
            try:
                r = requests.get(api + path, params=p, timeout=90)
                r.raise_for_status()
                return r.json()
            except Exception:
                time.sleep(3 * (i + 1))
        raise RuntimeError(path)

    ds = get("/dataset", q="Global Register of Introduced and Invasive Species", type="CHECKLIST", limit=500)["results"]
    griis = {x["key"]: {"title": x["title"], "licence": x.get("license"), "doi": x.get("doi")} for x in ds if "Introduced and Invasive" in x["title"]}
    res = {"_source": {"dataset": "Global Register of Introduced and Invasive Species (GRIIS), country checklists published through GBIF",
                       "n_checklists": len(griis), "licences": sorted({v["licence"] for v in griis.values() if v["licence"]}),
                       "retrieved": time.strftime("%Y-%m-%d", time.gmtime())}}
    for n in names:
        u = get("/species", name=n, limit=1000)
        rows = []
        for x in u.get("results", []):
            if x.get("datasetKey") in griis:
                for d in get(f"/species/{x['key']}/distributions", limit=50).get("results", []):
                    rows.append({"dataset": griis[x["datasetKey"]]["title"], "dataset_key": x["datasetKey"], "country": d.get("country"),
                                 "locality": d.get("locality"), "establishmentMeans": d.get("establishmentMeans"), "status": d.get("status"),
                                 "taxon_status": x.get("taxonomicStatus")})
        res[n] = rows
    if out:
        Path(out).write_text(json.dumps(res, indent=1))
    return res


def griis_units(rows: list[dict], feats: list) -> set[int]:
    """Indices (into NE subunit `feats`) of the units a species' GRIIS rows mark as introduced: whole-country rows (no locality or locality
    equal to the country) select every subunit of that country; a locality equal to a subunit name selects that subunit only.
    Rows with another locality (a state, an island group we cannot place) are skipped and reported by the caller."""
    sel = set()
    for r in rows:
        if (r.get("status") or "PRESENT") != "PRESENT":
            continue
        est = (r.get("establishmentMeans") or "").upper()
        if est and not (est.startswith("INTRODUCED") or est in ("INVASIVE", "NATURALISED", "NATURALIZED")):
            continue
        cc, loc = r.get("country"), (r.get("locality") or "").strip().lower()
        by_name = [i for i, f in enumerate(feats) if (f["properties"].get("NAME") or "").lower() == loc and loc]
        in_country = [i for i, f in enumerate(feats) if f["properties"].get("ISO_A2_EH") == cc or f["properties"].get("ISO_A2") == cc]
        country_names = {(feats[i]["properties"].get("ADMIN") or "").lower() for i in in_country} | {(feats[i]["properties"].get("NAME") or "").lower() for i in in_country}
        if by_name:
            sel.update(by_name)
        elif not loc or loc in country_names:
            sel.update(in_country)
    return sel
