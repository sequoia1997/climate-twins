# W2: pilot occurrence pipeline

Tags: **[V: how]** verified by the named run or command, **[U]** unverified.

## Status log (newest first)
- 2026-10-10 18:20 UTC: workflow `pilot-w2-run` run 38073761140 (stage acquire) is running: the 3 target-group SQL downloads (bird 0019445-260928105237408, mammal 0019446-..., insect_arachnid 0019447-...) were accepted by GBIF and queued, the 7 spike-A downloads are being re-fetched and cleaned (3 done and stored as release assets `w2-cells-*`). The plant group and the 18 new species follow as slots free (GBIF allows 3 at once). The first three runs failed only because of an invalid workflow file (a `runner` context at top level), fixed in commit 1ea7572 [V: run list, release asset list].
- GBIF accepts the SQL download syntax with a double-quoted `"year"` (the bare word `year` is a reserved word and is refused with HTTP 400 "Encountered year <=") [V: probe run 38072862321 log (400 on bare year) and the accepted requests in run 38073761140's state file `w2-state.json`].
- The Claude sandbox CAN reach api.gbif.org, download.gbif.org, sftp.kew.org (WCVP) and raw.githubusercontent.com (Natural Earth, TDWG), so taxon keys, GRIIS, WCVP and the cached spike-A downloads were processed locally for development; only authenticated download requests need Actions [V: curl / requests from the sandbox].
- 6 missing taxon keys resolved with the GBIF match API (all EXACT / ACCEPTED / SPECIES) and the 19 given ones re-checked (all equal): `data/species/native/pilot_taxa_resolved.csv` [V].

## 1. What is produced (release `species-pilot-data`, assets named below)
Grid for every table: TerraClimate native 1/24 degree, 4320 x 8640, row 0 = north, `lat = 90 - (row + 0.5) / 24`, `lon = -180 + (col + 0.5) / 24` (same as `ctw/species/climategrid.py`).

| Asset | Content |
|---|---|
| `occ_cells_pilot_v1.parquet` / `.csv.gz` | thinned cells of the 25 species, NATIVE cells only (columns below) |
| `occ_cells_pilot_v1_excluded_non_native.parquet` | the cells the native mask removed (audit; do not model with them) |
| `occ_cells_pilot_v1_p1_1970_1999_wellsampled.parquet`, `..._p2_2000_2020_wellsampled.parquet` | hindcast time split: native cells with records in the period, restricted to well-sampled cells |
| `tg_density_{bird,mammal,insect_arachnid,plant}_v1.npz` | target-group record counts per cell, uint32 (4320, 8640) arrays `all`, `p1_1970_1999`, `p2_2000_2020` |
| `native_masks_pilot_v1.npz` | per species `<Genus_species>__final` and `__curated` boolean masks, packed with `np.packbits(axis=1)` |
| `w2_report_pilot_v1.json` | per-species step counts, mask effects, DOIs, citations |
| `manifest_w2_v1.json` | sizes and sha256 of every file |
| `w2-*` | intermediate resumable state (per-species cells before masking, reports, target-group grids, download keys). Not for use |

Columns: `species_key` (GBIF taxon key), `species`, `group`, `tg_group`, `row`, `col`, `lat`, `lon`, `year_min`, `year_max`, `n_records` (records in the cell after cleaning and removing repeated occurrenceIDs), `n_events` (distinct coordinates + date + recorder + dataset), `n_1970_1999`, `n_2000_2020`, `n_2021_plus`, flags `native_curated` (cell inside our curated mask), `native_wcvp` (1/0 for plants, -1 = no WCVP entry), `griis_intro` (cell lies in a unit where GRIIS lists the species as introduced), `tg_block_p1`, `tg_block_p2` (target-group records in the 0.5 degree block, per period), `ws20`, `ws100` (well sampled, see 5), `tg_source`.

## 2. Occurrence method
Downloads: GBIF occurrence download per species (SIMPLE_PARQUET), filter in `ctw/species/gbif.py` `predicate`: taxonKey, hasCoordinate, no geospatial issue, PRESENT, licence CC0 or CC-BY 4.0, year >= 1970, basis of record in (human observation, preserved specimen, observation, machine observation), coordinate uncertainty missing or <= 10 km. The seven spike-A downloads (6 Oct 2026, erase date 2027-04-06) are reused; the other 18 are requested by the workflow. CC-BY-NC counts are kept only in the spike A documentation (`docs/spikes/A-occurrences.md` section 4); no CC-BY-NC record enters any table [V: the files contain only CC0 and CC-BY, see `licences_in_file` in the report].

Cleaning (`ctw/species/w2cells.py`), in order: coordinate sanity, uncertainty, country / capital / institution centroids, land (0.5 degree pool with neighbour allowance), establishmentMeans (INTRODUCED*, NATURALISED, INVASIVE, MANAGED, CULTIVATED, VAGRANT dropped for all species, plants and animals), year present, duplicates, then aggregation to cells. The first steps reproduce spike A exactly (monarch: 667 centroid, 1,412 land removals as in spike A) [V: local run on download 0013296-260928105237408].

Changes against spike A: the grid is the climate grid (row 0 = north; spike A's `occ.cell_id` counted rows from the south pole), counts and years are kept per cell instead of one record per cell, the institution list is fetched with retries (spike A silently used a partial list when a connection dropped), and the duplicate rule changed as follows.

## 3. The monarch duplicate step: explained and fixed [V: local analysis of download 0013296-260928105237408, 421,120 records]
Spike A's key (coordinates rounded to 5 decimals, event date, recorder, dataset) removed 367,503 records (87.3%). 357,517 of them are in one dataset, **Monarch Watch** (dataset cf7d6c01-309b-4545-8319-3d53b1e8bfd0, 363,582 records): tag-and-release records, one record per tagged butterfly, with a year-only date, the recorder fixed as "Monarch Watch", and the release site's coordinates. Many butterflies released at one site in one year therefore share the key. Of the 7,062 groups sharing a key, 99.97% have all-different occurrenceIDs (MW0338391, MW0195956, ...), so they are different records, not the same observation sent twice. Adding the occurrenceID to the key removes 2 records. Verdict: the old step was an event-level key mislabelled as a duplicate step; it did not harm the one-record-per-cell result, but it destroyed the record counts (needed for sampling effort). New rule: a duplicate is the same dataset and the same occurrenceID (or gbifID when none); repeated events are kept and counted in `n_events` (monarch: 418,855 records, 51,750 events, 15,076 cells). Cross-dataset duplicates (the same sighting in eBird and iNaturalist) are not removed by either rule [U, not measured].

## 4. Native range
Which mask comes from where:
- **Curated by us**: the `native_continents_curated` column of `pilot_v1.csv` (continent names, qualifiers W = Western Asia plus Iran, N = Northern Africa per Natural Earth subregion, and for Oceania north of 25 degrees S), realised with Natural Earth 1:50m **map subunit** polygons (`ne_50m_admin_0_map_subunits`, public domain), which already split Russia into its European and Asian parts and give Hawaii, French Guiana etc. their own continent. Used as the final mask for every animal.
- **From data (plants)**: WCVP (Kew World Checklist of Vascular Plants v16, CC BY 3.0, doi 10.34885/egs6-cp24): the TDWG level 3 areas where the accepted species is native (introduced = 0, extinct = 0, location_doubtful = 0), polygons from `tdwg/wgsrpd` level3 geojson (licence of the polygons not verified here [U]). Extract kept in `data/species/native/wcvp_pilot.json`. Final mask for the 8 plants; the curated mask is only a cross-check.
- **Cross-check only, never removes**: GRIIS (Global Register of Introduced and Invasive Species, 381 country checklists on GBIF, licence CC-BY 4.0 for 379 of them and CC0 for 4; the brief said CC0) through the GBIF species API: `data/species/native/griis_pilot.json`. Only rows with an explicit INTRODUCED/INVASIVE status are applied, whole-country rows to all subunits of the country, a locality equal to a subunit name (Hawaii) to that subunit; rows without status (for example Australia for the kookaburra) are reported as ambiguous. Result: flag `griis_intro` and the count in the report.
- Cells whose centre is in the sea but within 0.15 degrees (3.6 cells) of a polygon take that polygon's label, so coastal records are not lost [V: unit test].
- Not used: IUCN, BirdLife, eBird ranges (licence), iNaturalist place lists (licence). Known weaknesses: the curated Hirundo rustica list has no South America although the swallow winters there (those records are non-breeding); Danaus plexippus erippus in South America is cut; cultivated wine grapes inside the WCVP native area cannot be told from wild ones.

Per-species effect of the mask (cells in, kept, removed, by continent of the removed cells, curated-versus-WCVP disagreement, GRIIS flags) is in the table in section 7 and in `w2_report_pilot_v1.json` (`native_mask`).

## 5. Target-group background and well-sampled cells
Feasible free route chosen: **one aggregating GBIF SQL download per group** (format SQL_TSV_ZIP; bird = class Aves, mammal = Mammalia, insect_arachnid = Insecta + Arachnida, plant = Tracheophyta, used for trees and the grape). GBIF counts per 1/24 degree cell and period with the same record filter as the species downloads, so only a few million lines come back instead of billions of records. Cost: 4 downloads in the same queue as the species ones (3 at a time), no storage problem, each with a DOI; limit: counts are not cleaned beyond the GBIF filter (centroid and institution records are included), so it is an effort density, not a clean point set. Alternatives: the S3 snapshot with DuckDB (one pass of 288 GB, more than 20 minutes in spike A [V in that spike], no per-group DOI); pooling the pilot species (kept as a flagged fallback, weak: 13 birds are not the bird sampling process).
Well-sampled rule (C-validation 4.3, N = 20): a cell is well sampled when the 0.5 degree block (12 x 12 cells) around it has at least 20 target-group records in **both** 1970-1999 and 2000-2020 (`ws20`; `ws100` is the strict variant). Time-split files contain only `ws20` cells. Report results for these cells and for all cells (C-validation 4.3).

## 6. Provenance and citation
Each species table row carries its download in `w2_report_pilot_v1.json` (`download_state`: key, DOI, created, records, citation, predicate). Citation text per download: `GBIF.org (<date>) GBIF Occurrence Download https://doi.org/<DOI>`. The outputs are a derived dataset (thinned, masked, aggregated): GBIF asks for a registered **derived dataset** (title, description, DOI of the deposited data, list of source download DOIs with record counts) when a product combines or subsets several downloads. What could be verified: the `/v1/derivedDataset` endpoint exists and takes POST only (HTTP 405 on GET, spike A section 6.3 [V]); the exact fields and the web form were not verified, GBIF documentation is not what the sandbox is allowed to cite from memory [U]. Plan: deposit the release assets on Zenodo (CC-BY 4.0) at release time, register one derived dataset listing the 25 + 4 download DOIs, print its DOI and the per-species DOIs on each species page, and keep the CC-BY attribution by listing the dataset publishers.

## 7. Per-species counts and mask effects
(To be filled from `w2_report_pilot_v1.json` when the assemble stage has run.)

## 8. Loading
```python
import pandas as pd, numpy as np, urllib.request
base = "https://github.com/sequoia1997/climate-twins/releases/download/species-pilot-data/"
cells = pd.read_parquet(base + "occ_cells_pilot_v1.parquet")          # native cells, all species
sm = cells[cells.species == "Acer saccharum"]
rows, cols = sm.row.to_numpy(), sm.col.to_numpy()                      # index W1's climate arrays [row, col]
urllib.request.urlretrieve(base + "native_masks_pilot_v1.npz", "masks.npz")
mask = np.unpackbits(np.load("masks.npz")["Acer_saccharum__final"], axis=1)[:, :8640].astype(bool)   # accessible area (4320, 8640)
urllib.request.urlretrieve(base + "tg_density_plant_v1.npz", "tg_plant.npz")
bg = np.load("tg_plant.npz")["all"]                                    # target-group record counts: weight for background sampling
```

## 9. Remaining
Wait for the GBIF queue (16 to 35 minutes per download, 3 at once), then run stage assemble, fill section 7, add DOIs.
