# W2: pilot occurrence pipeline

Tags: **[V: how]** verified by the named run or command, **[U]** unverified.

## Status log (newest first)
- 2026-10-10 23:20 UTC: **COMPLETE.** Acquire run 38079352818 finished (25 of 25 species, 4 of 4 target groups, all non-empty); assemble run 38094283229 published the final assets to the release: `occ_cells_pilot_v1.parquet` (+ `.csv.gz`), `occ_cells_crops_cultivated_pilot_v1.parquet`, `occ_cells_pilot_v1_excluded_non_native.parquet`, `..._p1_1970_1999_wellsampled.parquet`, `..._p2_2000_2020_wellsampled.parquet`, `native_masks_pilot_v1.npz`, `tg_density_{bird,mammal,insect_arachnid,plant}_v1.npz`, `w2_report_pilot_v1.json`, `manifest_w2_v1.json` [V: release asset list]. Section 7 filled. Not done: Zenodo deposit and GBIF derived-dataset registration (section 6, 10).
- 2026-10-10 19:30 UTC: acquire run 38079352818 is in progress (first attempt 38079281206 died on a syntax error I introduced in the diag string, fixed in 503ab1e). New target-group SQL downloads by name requested: bird 0019517, mammal 0019518, insect_arachnid 0019519 (plant waits for a slot). Species stored with the new dataset-count asset so far: the 7 spike-A species (reprocessed), Cardinalis cardinalis, Zenaida macroura, Cyanocitta cristata; Agelaius phoeniceus and Hirundo rustica downloading, 13 species not yet requested [V: `w2-state.json` on the release]. After it finishes: push `[assemble]`, then fill section 7.
- 2026-10-10 19:25 UTC: **cause of the empty target-group downloads found**: even a taxon-only query (`speciesKey = 2182727`) returned 0 rows [V: diagnostic run 38077633418, download 0019501-260928105237408, log "status SUCCEEDED 0"]. Inference [U, consistent with spike A's S3 finding that taxon keys are now short strings]: GBIF's SQL engine no longer matches the legacy integer backbone keys. Fix: filter by NAME (`class = 'Aves'`, `phylum = 'Tracheophyta'`, ...) and apply licence / basis / issue / status / uncertainty / year in Python from grouping columns, so a wrong value format cannot empty the result again (`ctw/species/tg.py`; the distinct values seen are stored in the state file as `values_seen`). Empty results now raise instead of being stored. Run 38079281206 (`[acquire]`) re-requests the four groups and continues the species. Coordinator request (kind = wild or crop, cultivated records kept for crops, per-species counts) implemented: column `kind`, manifest `species_kind`, report `cultivated_managed_records` {kept or dropped}, unit tests. Caveat: the species downloads only contain the four observation-type basis values, so cultivated garden specimens recorded as LIVING_SPECIMEN or MATERIAL_SAMPLE are absent for crops; the grape download (spike A) cannot be widened without a new download [U whether that matters].
- 2026-10-10 18:55 UTC: **the four target-group SQL downloads came back EMPTY** (0 records, header line only: bird 0019445, mammal 0019446, insect_arachnid 0019447, plant 0019465) although GBIF accepted the SQL; the stored `w2-tg-*.npz` assets are empty grids and must be ignored (the sandbox cannot delete release assets; the next successful run overwrites them with `--clobber`). Some predicate value format is wrong (suspects: `license` string values, `hasGeospatialIssues`, `occurrenceStatus`). Diagnostic run 38077633418 (`[diag]`, workflow stage diag) asks GBIF for a taxon-only grouped query that prints the real value formats; once it finishes, fix `ctw/species/tg.py` `sql_for`, then push `[acquire]` (empty downloads are now discarded and re-requested automatically). I cancelled acquire run 38073761140 for this; it had stored cells for the 7 spike-A species plus Cardinalis cardinalis (26.9 M records) and had requested Zenaida, Cyanocitta, Agelaius, Hirundo (keys in `w2-state.json`, resumable).
- 2026-10-10 18:20 UTC: workflow `pilot-w2-run` run 38073761140 (stage acquire) is running: the 3 target-group SQL downloads (bird 0019445-260928105237408, mammal 0019446-..., insect_arachnid 0019447-...) were accepted by GBIF and queued, the 7 spike-A downloads are being re-fetched and cleaned (3 done and stored as release assets `w2-cells-*`). The plant group and the 18 new species follow as slots free (GBIF allows 3 at once). The first three runs failed only because of an invalid workflow file (a `runner` context at top level), fixed in commit 1ea7572 [V: run list, release asset list].
- GBIF accepts the SQL download syntax with a double-quoted `"year"` (the bare word `year` is a reserved word and is refused with HTTP 400 "Encountered year <=") [V: probe run 38072862321 log (400 on bare year) and the accepted requests in run 38073761140's state file `w2-state.json`].
- The Claude sandbox CAN reach api.gbif.org, download.gbif.org, sftp.kew.org (WCVP) and raw.githubusercontent.com (Natural Earth, TDWG), so taxon keys, GRIIS, WCVP and the cached spike-A downloads were processed locally for development; only authenticated download requests need Actions [V: curl / requests from the sandbox].
- 6 missing taxon keys resolved with the GBIF match API (all EXACT / ACCEPTED / SPECIES) and the 19 given ones re-checked (all equal): `data/species/native/pilot_taxa_resolved.csv` [V].

## 1. What is produced (release `species-pilot-data`, assets named below)
Grid for every table: TerraClimate native 1/24 degree, 4320 x 8640, row 0 = north, `lat = 90 - (row + 0.5) / 24`, `lon = -180 + (col + 0.5) / 24` (same as `ctw/species/climategrid.py`).

| Asset | Content |
|---|---|
| `occ_cells_pilot_v1.parquet` / `.csv.gz` | thinned cells of the 24 WILD species, NATIVE cells only (columns below) |
| `occ_cells_crops_cultivated_pilot_v1.parquet` | the crop (Vitis vinifera): where cultivated, no wild native-range mask, `kind = crop`; model target "where the climate suits growing it" |
| `occ_cells_pilot_v1_excluded_non_native.parquet` | the cells the native mask removed (audit; do not model with them) |
| `occ_cells_pilot_v1_p1_1970_1999_wellsampled.parquet`, `..._p2_2000_2020_wellsampled.parquet` | hindcast time split: native cells with records in the period, restricted to well-sampled cells |
| `tg_density_{bird,mammal,insect_arachnid,plant}_v1.npz` | target-group record counts per cell, uint32 (4320, 8640) arrays `all`, `p1_1970_1999`, `p2_2000_2020` |
| `native_masks_pilot_v1.npz` | per species `<Genus_species>__final` and `__curated` boolean masks, packed with `np.packbits(axis=1)` |
| `w2_report_pilot_v1.json` | per-species step counts, mask effects, DOIs, citations |
| `manifest_w2_v1.json` | sizes and sha256 of every file |
| `w2-*` | intermediate resumable state (per-species cells before masking, reports, target-group grids, download keys). Not for use |

Columns: `species_key` (GBIF taxon key), `species`, `group`, `kind` (wild or crop), `treatment`, `tg_group`, `row`, `col`, `lat`, `lon`, `year_min`, `year_max`, `n_records` (records in the cell after cleaning and removing repeated occurrenceIDs), `n_events` (distinct coordinates + date + recorder + dataset), `n_1970_1999`, `n_2000_2020`, `n_2021_plus`, flags `native_curated` (cell inside our curated mask), `native_wcvp` (1/0 for plants, -1 = no WCVP entry), `griis_intro` (cell lies in a unit where GRIIS lists the species as introduced), `tg_block_p1`, `tg_block_p2` (target-group records in the 0.5 degree block, per period), `ws20`, `ws100` (well sampled, see 5), `tg_source`.

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

### 6b. Owner decisions recorded (10 Oct 2026)
- **Crops are modelled where they are cultivated**, labelled "where the climate suits growing it", kept apart from wild species. Implemented: for group `crop` the establishmentMeans step keeps CULTIVATED / MANAGED / INTRODUCED records, no native-range mask is applied (the mask is all cells), the cells go to the separate asset `occ_cells_crops_cultivated_pilot_v1.parquet`, every row has `treatment = crop_cultivated` (wild species: `wild_native`), and the report has `native_mask.treatment` and `source` saying so. WCVP / curated flags are still written for information. In the pilot this is Vitis vinifera only. The spike-A grape table (cleaned with the wild rule) is therefore reprocessed.
- **Licence filter stays strictly CC0 and CC-BY** (no change).
- **Multi-species batch download and one DOI in a derived dataset** [partly verified]. Source read: the GBIF data blog post "Derived datasets" (https://data-blog.gbif.org/post/derived-datasets/, fetched 10 Oct 2026; the GBIF technical-docs page for it and gbif.org returned 404 / 403 from the sandbox). It says: a derived dataset is a citable record with its own DOI for a subset of GBIF-mediated data "for which a DOI doesn't exist or isn't representative"; to register one you need a GBIF.org account and a **list of contributing (parent) datasets, by datasetKey or DOI, with the number of records each contributed**; the form has two optional fields, "an original download DOI if the derived dataset represents a filtered version of that download" and a registration date; the data should be deposited publicly (for example Zenodo). Consequences [V for what the post says, U for how GBIF applies it]: (1) a derived dataset is defined by dataset keys and record counts, not by one download per species, so batch downloads are compatible; we need per-dataset record counts, which the pipeline now writes (`w2-datasets-<species>.json`, `dataset_counts` in the report). (2) A multi-species download has its own DOI and can be cited as it is when a product is that download unfiltered; our products are filtered and aggregated, so the registration route (parent datasets with counts) is the right one, and the optional "original download DOI" field takes ONE DOI, so for several batch downloads it should be left empty or used per batch [U]. (3) Not verified: the POST fields of `/v1/derivedDataset`, whether registration works with an API call rather than the web form, any size limit on the dataset list (our species draw on hundreds to thousands of publishers). Recommendation: do one manual registration with the pilot's data (owner's GBIF account) before scaling.

## 7. Per-species counts, mask effects, DOIs, citations [V: assemble run 38094283229, `w2_report_pilot_v1.json` on the release]
All 25 species and the 4 target-group grids are acquired and non-empty. Published tables: 2,843,633 native wild cells for 24 wild species in `occ_cells_pilot_v1.parquet`, 15,348 crop cells (Vitis vinifera) in `occ_cells_crops_cultivated_pilot_v1.parquet`; well-sampled time-split files: 455,134 cells in period 1 (1970-1999) and 2,167,791 in period 2 (2000-2020), 24 species each. Share of all native wild cells that are `ws20`: 96.1%; `ws100`: 90.2%. Extreme cells: lat -46.10 to 82.48, row 180 to 3266.

Counts at every step (records) and cells. "Records in download" is the GBIF download; "After cleaning" is after all row-level steps and duplicates; cells are 1/24 degree cells before and after the native mask; `p1/p2 cells` are the well-sampled native cells with records in 1970-1999 / 2000-2020.

| Species | Group | Kind | Download DOI | Records in download | After cleaning | Cells (all) | Native cells kept | Removed by mask | Mask source | Well-sampled kept (ws20) | p1 cells | p2 cells |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Turdus migratorius | bird | wild | 10.15468/dl.j78pf6 | 29,022,774 | 28,975,619 | 303,566 | 303,286 | 280 | curated | 293,302 | 51,900 | 240,844 |
| Cardinalis cardinalis | bird | wild | 10.15468/dl.kdtkgr | 26,936,188 | 26,880,460 | 176,766 | 176,012 | 754 | curated | 174,846 | 28,278 | 144,260 |
| Zenaida macroura | bird | wild | 10.15468/dl.hv7ht3 | 27,105,653 | 27,047,866 | 291,602 | 290,974 | 628 | curated | 284,894 | 45,934 | 233,903 |
| Cyanocitta cristata | bird | wild | 10.15468/dl.ysbd92 | 23,926,037 | 23,891,118 | 200,805 | 200,695 | 110 | curated | 198,265 | 33,827 | 164,243 |
| Agelaius phoeniceus | bird | wild | 10.15468/dl.xd7cz7 | 20,845,706 | 20,820,932 | 263,441 | 263,173 | 268 | curated | 257,699 | 41,768 | 208,056 |
| Hirundo rustica | bird | wild | 10.15468/dl.e29w6w | 15,135,574 | 15,055,454 | 519,754 | 502,606 | 17,148 | curated | 459,085 | 65,746 | 346,064 |
| Melospiza melodia | bird | wild | 10.15468/dl.mwndcv | 22,202,138 | 22,166,573 | 221,108 | 220,728 | 380 | curated | 217,059 | 37,081 | 176,489 |
| Thryothorus ludovicianus | bird | wild | 10.15468/dl.37gz54 | 12,842,857 | 12,830,427 | 113,223 | 113,161 | 62 | curated | 112,705 | 14,017 | 90,158 |
| Sialia sialis | bird | wild | 10.15468/dl.egcybv | 7,956,174 | 7,938,687 | 149,386 | 149,337 | 49 | curated | 148,292 | 18,366 | 121,202 |
| Spinus tristis | bird | wild | 10.15468/dl.wkzk6n | 20,139,596 | 20,106,745 | 209,982 | 209,813 | 169 | curated | 207,701 | 34,759 | 171,919 |
| Acer saccharum | tree | wild | 10.15468/dl.wfs6tc | 29,892 | 29,878 | 3,741 | 3,665 | 76 | WCVP | 3,537 | 577 | 1,388 |
| Acer rubrum | tree | wild | 10.15468/dl.uwhdz4 | 70,076 | 70,051 | 6,812 | 6,609 | 203 | WCVP | 6,376 | 886 | 2,421 |
| Pinus strobus | tree | wild | 10.15468/dl.eyf9jt | 37,689 | 36,549 | 11,239 | 7,862 | 3,377 | WCVP | 7,428 | 435 | 2,703 |
| Populus tremuloides | tree | wild | 10.15468/dl.5jq7gj | 17,051 | 17,032 | 8,232 | 8,119 | 113 | WCVP | 7,603 | 897 | 2,490 |
| Quercus alba | tree | wild | 10.15468/dl.dz32rd | 10,942 | 10,931 | 3,712 | 3,683 | 29 | WCVP | 3,571 | 451 | 1,257 |
| Odocoileus virginianus | mammal | wild | 10.15468/dl.h7neaf | 54,119 | 54,077 | 12,153 | 10,665 | 1,488 | curated | 5,128 | 304 | 2,184 |
| Danaus plexippus | insect_arachnid | wild | 10.15468/dl.j58smz | 421,120 | 418,855 | 15,076 | 13,509 | 1,567 | curated | 13,020 | 3,921 | 5,513 |
| Ixodes scapularis | insect_arachnid | wild | 10.15468/dl.6jg2d3 | 8,412 | 8,382 | 1,275 | 1,270 | 5 | curated | 1,243 | 72 | 373 |
| Erithacus rubecula | bird | wild | 10.15468/dl.ta47bg | 7,967,704 | 7,900,078 | 191,791 | 182,946 | 8,845 | curated | 175,387 | 23,752 | 135,573 |
| Quercus robur | tree | wild | 10.15468/dl.nkfygt | 1,024,406 | 1,018,395 | 71,786 | 70,660 | 1,126 | WCVP | 69,075 | 26,201 | 55,383 |
| Vitis vinifera | crop | crop | 10.15468/dl.wk7m62 | 88,968 | 88,774 | 15,348 | 15,348 | 0 | none | 0 | 0 | 0 |
| Vulpes vulpes | mammal | wild | 10.15468/dl.76nfw9 | 1,058,921 | 980,150 | 73,191 | 71,797 | 1,394 | curated | 55,300 | 14,152 | 39,196 |
| Dacelo novaeguineae | bird | wild | 10.15468/dl.ub5qn7 | 883,974 | 881,829 | 28,689 | 28,563 | 126 | curated | 28,351 | 11,239 | 20,347 |
| Adansonia digitata | tree | wild | 10.15468/dl.n7n7yq | 6,027 | 5,997 | 1,939 | 1,811 | 128 | WCVP | 1,493 | 266 | 1,089 |
| Danaus chrysippus | insect_arachnid | wild | 10.15468/dl.k9evm5 | 8,485 | 8,323 | 3,537 | 2,689 | 848 | curated | 1,683 | 305 | 736 |

Records removed at each cleaning step (the same steps for every species; crops keep cultivated / managed / introduced records, wild species drop them) and where the mask removed cells ('-' = cell centre not within 0.15 degrees of any polygon, e.g. open sea):

| Species | coords | uncertainty | centroids | land | establishment | year | duplicates | removed total | cultivated/managed records | removed cells by continent (top) |
|---|---|---|---|---|---|---|---|---|---|---|
| Turdus migratorius | 242 | 0 | 33,719 | 13,194 | 0 | 0 | 0 | 47,155 | {'dropped': 0} | - 225, Europe 53, Asia 2 |
| Cardinalis cardinalis | 39 | 0 | 27,445 | 28,244 | 0 | 0 | 0 | 55,728 | {'dropped': 0} | Oceania 645, - 95, Europe 13 |
| Zenaida macroura | 80 | 0 | 31,710 | 25,996 | 1 | 0 | 0 | 57,787 | {'dropped': 0} | - 365, Oceania 229, Europe 27 |
| Cyanocitta cristata | 45 | 0 | 22,863 | 12,011 | 0 | 0 | 0 | 34,919 | {'dropped': 0} | - 106, Europe 4 |
| Agelaius phoeniceus | 80 | 0 | 18,249 | 6,445 | 0 | 0 | 0 | 24,774 | {'dropped': 0} | - 262, Europe 6 |
| Hirundo rustica | 317 | 0 | 30,588 | 49,205 | 0 | 0 | 10 | 80,120 | {'dropped': 0} | South America 12935, - 3881, Oceania 220 |
| Melospiza melodia | 77 | 0 | 23,804 | 11,684 | 0 | 0 | 0 | 35,565 | {'dropped': 0} | - 365, Europe 15 |
| Thryothorus ludovicianus | 12 | 0 | 12,380 | 38 | 0 | 0 | 0 | 12,430 | {'dropped': 0} | - 62 |
| Sialia sialis | 11 | 0 | 8,262 | 9,214 | 0 | 0 | 0 | 17,487 | {'dropped': 0} | - 49 |
| Spinus tristis | 34 | 0 | 23,417 | 9,400 | 0 | 0 | 0 | 32,851 | {'dropped': 0} | - 163, Europe 5, Asia 1 |
| Acer saccharum | 3 | 0 | 10 | 0 | 1 | 0 | 0 | 14 | {'dropped': 0} | Europe 56, North America 12, Asia 5 |
| Acer rubrum | 0 | 0 | 24 | 0 | 1 | 0 | 0 | 25 | {'dropped': 0} | Europe 153, North America 36, Oceania 7 |
| Pinus strobus | 4 | 0 | 14 | 0 | 1,121 | 0 | 1 | 1,140 | {'dropped': 0} | Europe 3174, North America 151, Oceania 30 |
| Populus tremuloides | 1 | 0 | 16 | 2 | 0 | 0 | 0 | 19 | {'dropped': 0} | Europe 88, Asia 13, North America 5 |
| Quercus alba | 0 | 0 | 11 | 0 | 0 | 0 | 0 | 11 | {'dropped': 0} | North America 18, Europe 9, South America 1 |
| Odocoileus virginianus | 4 | 0 | 29 | 7 | 2 | 0 | 0 | 42 | {'dropped': 0} | Europe 1214, South America 230, - 28 |
| Danaus plexippus | 9 | 0 | 667 | 1,412 | 177 | 0 | 0 | 2,265 | {'dropped': 0} | Oceania 1005, South America 191, Europe 135 |
| Ixodes scapularis | 0 | 0 | 30 | 0 | 0 | 0 | 0 | 30 | {'dropped': 0} | Europe 3, - 1, Asia 1 |
| Erithacus rubecula | 113 | 0 | 36,036 | 31,227 | 0 | 0 | 250 | 67,626 | {'dropped': 0} | Asia 6368, - 1237, Africa 1180 |
| Quercus robur | 8 | 0 | 548 | 296 | 2,199 | 0 | 2,960 | 6,011 | {'dropped': 0} | North America 396, Oceania 350, Asia 130 |
| Vitis vinifera | 0 | 0 | 73 | 60 | 0 | 0 | 61 | 194 | {'kept': 0} |  |
| Vulpes vulpes | 162 | 0 | 763 | 12 | 77,673 | 0 | 161 | 78,771 | {'dropped': 0} | Oceania 1245, - 149 |
| Dacelo novaeguineae | 12 | 0 | 2,125 | 8 | 0 | 0 | 0 | 2,145 | {'dropped': 0} | - 104, Europe 16, North America 5 |
| Adansonia digitata | 2 | 0 | 13 | 15 | 0 | 0 | 0 | 30 | {'dropped': 0} | Africa 50, Asia 42, South America 16 |
| Danaus chrysippus | 0 | 0 | 137 | 25 | 0 | 0 | 0 | 162 | {'dropped': 0} | Oceania 433, Europe 371, Seven seas (open ocean) 30 |

Native mask cross-check (kept cells that the curated mask would not contain; curated cells the final mask removed; GRIIS flags):

| Species | WCVP/curated disagreement: kept but not in curated | curated but removed | kept cells in GRIIS-introduced units | GRIIS units |
|---|---|---|---|---|
| Turdus migratorius | 0 | 0 | 0 | - |
| Cardinalis cardinalis | 0 | 0 | 0 | Ascension, Brussels, Diego Garcia NSF, England, Flemish, Germany |
| Zenaida macroura | 0 | 0 | 0 | - |
| Cyanocitta cristata | 0 | 0 | 0 | Ascension, Diego Garcia NSF, England, N. Ireland, S. Georgia, S. Sandwich Is. |
| Agelaius phoeniceus | 0 | 0 | 0 | Ascension, Diego Garcia NSF, England, N. Ireland, S. Georgia, S. Sandwich Is. |
| Hirundo rustica | 0 | 0 | 0 | - |
| Melospiza melodia | 0 | 0 | 0 | Brussels, Flemish, Walloon |
| Thryothorus ludovicianus | 0 | 0 | 0 | - |
| Sialia sialis | 0 | 0 | 0 | Germany |
| Spinus tristis | 0 | 0 | 0 | Brussels, Flemish, Walloon |
| Acer saccharum | 0 | 12 | 0 | Armenia, Austria, Estonia, Poland, Slovenia, Turkey |
| Acer rubrum | 1 | 36 | 0 | Armenia, Brussels, Flemish, Walloon |
| Pinus strobus | 0 | 151 | 0 | Armenia, Ascension, Ashmore and Cartier Is., Australia, Austria, Belarus |
| Populus tremuloides | 0 | 5 | 0 | Estonia, Kaliningrad, Russia |
| Quercus alba | 0 | 18 | 0 | - |
| Odocoileus virginianus | 0 | 0 | 0 | Cuba, Czechia, Finland, Jamaica, St. Kitts and Nevis, Sweden |
| Danaus plexippus | 0 | 0 | 0 | Ashmore and Cartier Is., Australia, Bornholm, Brussels, Denmark, Flemish |
| Ixodes scapularis | 0 | 0 | 0 | - |
| Erithacus rubecula | 0 | 0 | 0 | - |
| Quercus robur | 122 | 54 | 435 | Andaman Is., Argentina, Armenia, Ashmore and Cartier Is., Australia, Azores |
| Vitis vinifera | 735 | 0 | 5,093 | Albania, Andaman Is., Angola, Argentina, Ascension, Ashmore and Cartier Is. |
| Vulpes vulpes | 0 | 0 | 89 | Argentina, Ashmore and Cartier Is., Australia, Cyprus, Macquarie I., Tasmania |
| Dacelo novaeguineae | 0 | 0 | 88 | Ascension, Brussels, Chatham Is., Colombia, Diego Garcia NSF, England |
| Adansonia digitata | 7 | 50 | 0 | Algeria, Madagascar, Seychelles |
| Danaus chrysippus | 0 | 0 | 0 | - |

Reading notes. Duplicates: 0 removed everywhere except a handful (the occurrenceID rule); the old event-level rule would have removed 87% of the monarch records. Establishment: 0 cultivated / managed records exist in the grape download (the filtered download contains none), so the crop treatment changes only the INTRODUCED records (kept) and the mask. The largest mask effects: white pine loses 3,377 of 11,239 cells (WCVP introduced range), barn swallow 17,148 (the curated list has no South America, see section 4), European robin 8,845 (Asia and Africa outside EUROPE), monarch 1,567 (Oceania 1,005), plain tiger 848.

Target-group grids (records counted by GBIF, CC0 and CC-BY, 1970-2020, same filter): bird 1,149,509,715 in 1,996,661 cells; mammal 20,353,254 in 1,147,155; insect_arachnid 101,134,333 in 572,919; plant 226,054,284 in 1,301,327 [V: `w2-state.json`; assets `tg_density_*_v1.npz`]. Downloads: bird 0019517-260928105237408 (doi 10.15468/dl.spdj4n), mammal 0019518-... (10.15468/dl.7xq6mb), insect_arachnid 0019519-... (10.15468/dl.at3mx7), plant 0019522-... (10.15468/dl.qqzta8). These are SQL downloads, so they carry their own DOIs.

Citations (GBIF's text pattern, taken from each download record; dates are the request dates):

- Turdus migratorius: GBIF.org (6 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.j78pf6
- Cardinalis cardinalis: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.kdtkgr
- Zenaida macroura: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.hv7ht3
- Cyanocitta cristata: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.ysbd92
- Agelaius phoeniceus: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.xd7cz7
- Hirundo rustica: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.e29w6w
- Melospiza melodia: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.mwndcv
- Thryothorus ludovicianus: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.37gz54
- Sialia sialis: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.egcybv
- Spinus tristis: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.wkzk6n
- Acer saccharum: GBIF.org (6 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.wfs6tc
- Acer rubrum: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.uwhdz4
- Pinus strobus: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.eyf9jt
- Populus tremuloides: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.5jq7gj
- Quercus alba: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.dz32rd
- Odocoileus virginianus: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.h7neaf
- Danaus plexippus: GBIF.org (6 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.j58smz
- Ixodes scapularis: GBIF.org (6 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.6jg2d3
- Erithacus rubecula: GBIF.org (6 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.ta47bg
- Quercus robur: GBIF.org (6 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.nkfygt
- Vitis vinifera: GBIF.org (6 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.wk7m62
- Vulpes vulpes: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.76nfw9
- Dacelo novaeguineae: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.ub5qn7
- Adansonia digitata: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.n7n7yq
- Danaus chrysippus: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.k9evm5
- target group bird: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.spdj4n (1,149,509,715 records counted, 1,996,661 cells)
- target group mammal: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.7xq6mb (20,353,254 records counted, 1,147,155 cells)
- target group insect_arachnid: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.at3mx7 (101,134,333 records counted, 572,919 cells)
- target group plant: GBIF.org (10 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.qqzta8 (226,054,284 records counted, 1,301,327 cells)

Licence of the data: every download holds only CC0 and CC-BY records (`licences_in_file` in the report). Source datasets (per species `dataset_counts`) are in the report; the CC-BY attribution at dataset level is carried by these DOIs.

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

## 9. Remaining (superseded: see status log, acquisition and assemble are complete)
At the last check (run 38073761140 still in progress, only the three small spike-A species stored as `w2-cells-*`; target-group downloads bird 0019445, mammal 0019446, insect_arachnid 0019447 queued at GBIF) nothing else had finished. Local development runs reproduced all 7 spike-A species end to end (cells for the two robins and oak, too), so the code path is proven; the published numbers must come from the Actions run. If the run ends by time limit, push any change to `.github/run/pilot-w2` with `[acquire]` in the commit message: it resumes from the release state. Then push with `[assemble]`.

Wait for the GBIF queue (16 to 35 minutes per download, 3 at once), then run stage assemble, fill section 7, add DOIs.


## 10. Scaling from 25 to about 380 species (design only, nothing run) 
Input: `data/species/shortlist_v1.csv`, 381 species, 19 of them already in the pilot, so **362 new**: tree 85, bird 84, insect_arachnid 45, wild_plant 40, crop 39, mammal 38, herp 20, fish 11 [V: pandas on the file]. GBIF record counts in the file: 613 M in total, 545 M of them birds; 29 species have more than 5 M records and carry 77% of all records; the median species has 93 k [V: same file; `gbif_records` is the unfiltered count, so the downloads will be smaller after the licence filter].

**Batching under the 3-download limit.** Queue time per download was 16 to 33 minutes in spike A and did not depend on size (8 k records took 30 min) [V: spike A section 2]. One download per species would be 362 requests = 121 rounds of 3, about 50 hours of queue time if the 3 slots stay full (362 x 25 min / 3) [U, extrapolation], i.e. about 9 resumable 5.6 hour Actions runs. Proposal, in three tiers:
1. **Light tier, 333 species (below 5 M records each)**: one multi-species download per batch of about 15 species (`taxonKey in [...]`, same predicate, SIMPLE_PARQUET), cap each batch at about 25 M records so the zip stays under 2 GB and the runner disk (14 GB free) is safe; split by `specieskey` while streaming (the cleaner already works chunk by chunk). About 25 batches = 9 rounds, about 4 to 5 hours of queue time, 1 to 2 resumable runs. Cost: one DOI per batch instead of per species; the per-species record count and the batch DOI go into the report and the derived-dataset record [U whether GBIF's derived-dataset form is happy with batch DOIs; ask before the production run].
2. **Heavy tier, the 29 species above 5 M (mostly birds)**: single-species downloads as in the pilot (robin: 2.1 GB zip, 29 M records, 11 minutes to clean on a runner [V: spike A]); 29 requests = 10 rounds, about 5 hours of queue. Candidate shortcut to test on the pilot robins first (we hold both record-level versions): a SQL download grouped by species, cell and year, which returns a few MB, with centroid and institution screening applied at cell level; if it reproduces the record-level cell tables within about 1% it removes most of the heavy tier [U, not tested].
3. **Target groups**: the pilot's four SQL downloads plus herp (Amphibia 131 and Reptilia 358) and fish (Actinopterygii 204), so 7 in total, if wanted.
Scheduling is already resumable (state in the release, `w2run acquire`); the only change is the job list. Storage: cell tables for 380 species are of the order of 100 MB in parquet (pilot: 8 species = 4.4 MB cells before masking, birds dominate) [V for the pilot figure, extrapolated]; release assets are limited to 2 GB each, so the final tables should be split per group. GBIF and Actions minutes cost nothing for a public repository; the real cost is wall time (about 10 to 12 hours of queue in total, spread over 3 to 4 runs) and the 6 hour job limit.

**Native range source per group** (who decides):
| Group (new species) | Source | Status |
|---|---|---|
| tree 85, wild_plant 40, crop 39 (164) | WCVP native TDWG level 3 areas, same code as the pilot plants (`build_wcvp_pilot` takes a list of names); matching is by accepted species name, so the file lists species with no WCVP entry (hybrids, cultivars) for manual handling | data, automatic |
| crop 39 | WCVP gives the wild ancestor's native range, not where the crop grows. Model target needs a decision: native range only (as the pilot grape, Tier 2) or "wild plus cultivated area" which is not a climate-niche statement | **owner decision** |
| bird 84, mammal 38, insect_arachnid 45, herp 20, fish 11 (198) | no free authoritative range polygons (IUCN, BirdLife, eBird ranges are not redistributable). GRIIS (CC-BY) removes introduced countries as a flag; the native region itself has to be curated | **curated by us: all 198** |

Which shortlist species need curated native regions: **all 198 new animals**. The shortlist `region_assigned` is the continent with most GBIF records for these (`gbif majority records` for all 248 animals incl. pilot overlap, none are manual), which follows where recorders live, so it must not be used as the native mask [V: crosstab of `region_basis` by group]. The 89 manual-basis trees and crops already have an origin continent but WCVP replaces it. Proposed workflow for the 198: draft native continent / subregion strings in the pilot's grammar (`NORTH_AMERICA;ASIA(W)`, extended with subregion tokens such as `EUROPE(S)` and country lists where a species is resident in one country only) from Wikipedia and IUCN text summaries, then a person reviews the list; store as `data/species/native/curated_native_v2.csv` with a source note per row; migratory birds need a breeding versus non-breeding decision per species (pilot barn swallow lesson). Species flagged `flag_invasive_or_introduced` (24 in the shortlist) need the native region to be explicit, since GBIF majority continent can be the introduced one. Marine and freshwater fish need a water mask instead of the land step (no fish is flagged marine in the file, but the 11 fish are not checked here [U]).

Checks to run before the production run: (1) fix the target-group SQL and compare one group against an independent count; (2) test the species-cell SQL shortcut on the two pilot robins; (3) ask GBIF about batch DOIs in derived datasets; (4) decide the crop question.


## 11. Seasonal cells for the 11 migratory species (added after W3's finding)
Problem: the v1 cell tables have years but no months, so breeding and wintering records of migrants are mixed. Fix, without replacing any v1 asset: `occ_cells_pilot_v1_seasonal.parquet` (+ `w2_seasonal_report_v1.json`, `manifest_w2_seasonal_v1.json`), built by workflow stages `[seasonal]` (re-read cached downloads, add month counts) and the `assemble-seasonal` step in the same job.

**Queue cost: none.** The SIMPLE_PARQUET downloads already contain `month` (verified in the monarch file: columns day, month, year). The 11 downloads are still valid on GBIF until early April 2027 (erase dates 2027-04-06 and later [V: download records]), so no new GBIF request and no waiting in the 3-slot queue. Cost is runner time: re-fetching about 10 GB of zips (American robin 2.1 GB, mourning dove, blue jay, red-winged blackbird, song sparrow, goldfinch each 1 to 2 GB) and re-cleaning with two threads, an estimated 1.5 to 2 hours in one job [U estimate from the 11 minute robin cleaning in spike A]. The cleaner is deterministic, so the cell set must equal v1's; each species writes a consistency check (`same_cells`, record counts) that the report carries [V for monarch locally: 15,076 cells and 418,855 records equal to v1].

**Season definition** (by the hemisphere the SPECIES breeds in, applied to the calendar month of every record wherever it was seen; a barn swallow in Argentina in January is therefore a non-breeding record): scheme N breeding May-Jul, winter Dec-Feb; scheme S (southern breeders, unused by these 11, tested) breeding Nov-Jan, winter Jun-Aug. All 11 use N. Months Mar-Apr, Aug-Nov are in the per-month counts only.

**Columns** (one row per species and cell, all cells of the v1 clean table, including cells outside any mask): `m00` (records without a month) and `m01..m12` (records per calendar month), `n_breeding`, `n_winter`, and the same per period `n_breeding_1970_1999`, `n_breeding_2000_2020`, `n_winter_1970_1999`, `n_winter_2000_2020`; `in_breeding_mask`, `in_winter_mask` (curated seasonal native masks), `breeding_cell` = in the breeding mask and `n_breeding > 0`, `winter_cell` likewise; `tg_block_p1`, `tg_block_p2`, `ws20`, `ws100` as in v1. Recommended use for a niche model of a migrant: the `breeding_cell` set (or `winter_cell` for a wintering-niche model), never the union.

**Seasonal native masks** (`data/species/native/curated_seasonal_v1.csv`, curated by us, one note per species): the barn swallow breeding mask is NORTH_AMERICA;EUROPE;ASIA;AFRICA(N) (v1 had all of Africa), the winter mask adds SOUTH_AMERICA, sub-Saharan Africa and northern Oceania. **Decision on the barn swallow:** the model target is the BREEDING range (breeding-season records inside the breeding mask); the v1 mask removed 17,148 cells mostly in South America, which are wintering records and now live in the winter set instead of being lost. European robin gets ASIA(W) (Caucasus, Anatolia) and N Africa added, which v1 cut. The other nine keep the v1 continents for both seasons (their winter ranges stay inside it). The winter masks are continent-level and coarse [U: not checked against range maps, which we cannot use].

**Limitation found while testing:** most monarch records have no month (372,341 of 418,855: Monarch Watch tags carry a year only), so the monarch breeding and winter sets rest on the other 46 k records, mostly iNaturalist / Journey North; `records_without_month` is in the report for every species.

**Result [V: run 38096880803, assets on the release: `occ_cells_pilot_v1_seasonal.parquet` 27 MB, `w2_seasonal_report_v1.json`, `manifest_w2_seasonal_v1.json`].** The cell set of every species equals v1 (`same_cells` true, record counts equal). A cell can be in both seasons.

| Species | cells | breeding cells | winter cells | both | records May-Jul | records Dec-Feb | other months | no month | same cells as v1 |
|---|---|---|---|---|---|---|---|---|---|
| Hirundo rustica | 519,754 | 371,192 | 63,470 | 11,324 | 7,410,605 | 751,729 | 6,471,379 | 421,741 | True |
| Turdus migratorius | 303,566 | 241,317 | 119,374 | 87,758 | 11,627,385 | 4,213,968 | 13,112,772 | 21,494 | True |
| Agelaius phoeniceus | 263,441 | 220,873 | 91,046 | 73,798 | 8,924,334 | 2,481,719 | 9,414,543 | 336 | True |
| Zenaida macroura | 291,602 | 236,545 | 133,393 | 112,320 | 8,818,545 | 5,478,552 | 12,750,749 | 20 | True |
| Spinus tristis | 209,982 | 158,516 | 109,062 | 78,432 | 7,070,310 | 3,839,571 | 9,196,836 | 28 | True |
| Sialia sialis | 149,386 | 108,594 | 79,475 | 58,730 | 2,308,918 | 1,811,456 | 3,818,293 | 20 | True |
| Cyanocitta cristata | 200,805 | 152,708 | 123,241 | 98,629 | 6,539,386 | 5,105,344 | 12,246,365 | 23 | True |
| Melospiza melodia | 221,108 | 163,704 | 92,907 | 57,769 | 7,955,693 | 3,893,175 | 10,316,046 | 1,659 | True |
| Erithacus rubecula | 191,791 | 129,836 | 99,173 | 69,646 | 1,553,063 | 1,718,169 | 4,013,488 | 615,358 | True |
| Danaus plexippus | 15,076 | 4,653 | 843 | 264 | 13,269 | 3,956 | 29,289 | 372,341 | True |
| Danaus chrysippus | 3,537 | 779 | 823 | 128 | 1,883 | 1,695 | 4,709 | 36 | True |

Note the European robin: 615 k of its records have no month, and for the barn swallow the breeding set (371 k cells) is three times larger than the strictly winter-only cells, because May-Jul records in the winter-range continents (oversummering and misdated records) are excluded only by the breeding mask, not by month alone. The queue cost was zero GBIF requests; the whole job (11 species, two threads) finished within about 30 minutes of runner time [V: run 38096880803 started and completed within the polling window].
