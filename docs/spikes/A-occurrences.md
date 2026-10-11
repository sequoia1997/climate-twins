# Spike A: GBIF occurrences

Resumed 10 October 2026 after the first agent was cut off. Status: complete except where marked.

Tags: **[V: source]** verified against the named run, log or command. **[U]** unverified (reasoning, memory or documentation not re-checked here).
Main source: GitHub Actions run 37527451337 (workflow spike-a-gbif, run number 6, commit e9b03a9, 6 Oct 2026 20:34 to 21:43 UTC), jobs login (112487950462), probe (112487950914), download (112488344519). Raw numbers parsed from those job logs are saved in `docs/spikes/data/spike-a/run6-results.json` and `run6-probe.json`. (The run's artifacts could not be fetched from this sandbox, GitHub's blob host is not reachable; the same JSON is printed in the job logs.)

## 1. Login and credentials
- Authenticated call `GET /user/login` with the repository secrets returned **HTTP 200** [V: run 37527451337, job login, log line "login HTTP 200"]. Secret values are masked as `***` in the log [V: same log].
- Seven real downloads were then requested with the account and all SUCCEEDED [V: download job].
- Practical note: GBIF wants the username, not the email address, in `GBIF_USER` (the runner prints a hint on HTTP 401) [V: code, ctw/species/spike_a.py].

## 2. Downloads (7 pilot species)
Filter used (ctw/species/gbif.py `predicate`) [V: code]: taxonKey, hasCoordinate, no geospatial issue, occurrenceStatus PRESENT, licence in {CC0, CC-BY 4.0}, year >= 1970, basisOfRecord in {HUMAN_OBSERVATION, PRESERVED_SPECIMEN, OBSERVATION, MACHINE_OBSERVATION}, coordinate uncertainty missing or <= 10 km. Format SIMPLE_PARQUET [V: results.json "format"].

| Species | DOI | Download key | Records | Zip size MB | GBIF prep time, min | Our fetch + clean, s |
|---|---|---|---|---|---|---|
| Acer saccharum (sugar maple) | 10.15468/dl.wfs6tc | 0013294-260928105237408 | 29,892 | 8.0 | 18 | 21 |
| Quercus robur (English oak) | 10.15468/dl.nkfygt | 0013295-260928105237408 | 1,024,406 | 85.2 | 22 | 78 |
| Danaus plexippus (monarch) | 10.15468/dl.j58smz | 0013296-260928105237408 | 421,120 | 19.3 | 22 | 30 |
| Turdus migratorius (American robin) | 10.15468/dl.j78pf6 | 0013336-260928105237408 | 29,022,774 | 2,107.0 | 32 | 670 |
| Erithacus rubecula (European robin) | 10.15468/dl.ta47bg | 0013337-260928105237408 | 7,967,704 | 562.1 | 33 | 253 |
| Ixodes scapularis (blacklegged tick) | 10.15468/dl.6jg2d3 | 0013342-260928105237408 | 8,412 | 4.5 | 30 | 15 |
| Vitis vinifera (wine grape) | 10.15468/dl.wk7m62 | 0013410-260928105237408 | 88,968 | 14.4 | 16 | 31 |

[V: run 37527451337, download job, results.json printed in log.] "Prep time" is `modified - created` from the GBIF download record. The first three downloads were requested at 20:15 UTC in the earlier failed run 5 and reused here via `.github/run/spike-a-keys.json` [V: results.json created timestamps, repo file].

- Prep time is dominated by GBIF's queue, not by size: the 8,412-record tick download took 30 min, the 29-million-record robin 32 min. A request-to-ready time of 15 to 35 minutes should be assumed per batch; with the limit of 3 concurrent downloads, 350 species is about 117 rounds, so roughly 2 to 3 days if run serially at ~30 min, less if prep is shorter outside peak [U, extrapolation].
- Each download record carries a DOI; citation text returned by GBIF: `GBIF.org (6 October 2026) GBIF Occurrence Download https://doi.org/<DOI>` [V: results.json "citation"; the text comes from the fallback pattern or GBIF's endpoint, the code cannot tell which].
- Counts in the downloads are below the "probe" facet counts (e.g. oak 1,024,406 vs 1,138,424) because the probe did not apply the basis-of-record or uncertainty parts of the filter [V: code vs logs; the reason is inferred, U].
- 3-concurrent limit: the runner queues the rest and handled it [V: log, requests staggered over 275 s, no HTTP 420 error surfaced].
- Largest download (robin, 2.1 GB zip, 29 M records) fetched and cleaned in 11 minutes on a standard runner [V: fetch_and_clean_s 670]. A pipeline needs to stream, not load, such files (the Cleaner does) [V: code].

## 3. Cleaning (ctw/species/occ.py), before and after
Records left after each step (removed in brackets). Animals skip the establishment step; trees and crops drop MANAGED/CULTIVATED/INTRODUCED. [V: run 37527451337, results.json "cleaning"]

| Species | input | coords | uncertainty | centroids | land | establishment | duplicates | thinned (final) | final / input |
|---|---|---|---|---|---|---|---|---|---|
| Acer saccharum | 29,892 | -3 | 0 | -10 | 0 | -1 | -4,743 | **3,739** | 12.5% |
| Quercus robur | 1,024,406 | -8 | 0 | -556 | -296 | -2,199 | -198,843 | **71,796** | 7.0% |
| Danaus plexippus | 421,120 | -9 | 0 | -667 | -1,412 | 0 | -367,109 | **15,157** | 3.6% |
| Turdus migratorius | 29,022,774 | -242 | 0 | -33,721 | -13,194 | 0 | -1,088,162 | **303,558** | 1.05% |
| Erithacus rubecula | 7,967,704 | -113 | 0 | -36,412 | -31,227 | 0 | -1,820,920 | **191,789** | 2.4% |
| Ixodes scapularis | 8,412 | 0 | 0 | -30 | 0 | 0 | -3,777 | **1,275** | 15.2% |
| Vitis vinifera | 88,968 | 0 | 0 | -73 | -60 | -1,117 | -29,933 | **14,997** | 16.9% |

Continent spread of the final thinned cells (one record per 2.5 arc-minute cell) and number of countries [V: same source]:

| Species | Final cells | Spread | Countries |
|---|---|---|---|
| Sugar maple | 3,739 | N America 98.3%, Europe 1.5%, Asia 0.1%, Oceania 0.1% | 17 |
| English oak | 71,796 | Europe 98.7%, N America 0.6%, Oceania 0.5%, Africa 0.1%, Asia 0.1% | 61 |
| Monarch | 15,157 | N America 89.7%, Oceania 6.7%, Europe 1.7%, S America 1.3%, Unknown 0.4% | 60 |
| American robin | 303,558 | N America 100.0% (55 in Europe, 1 in Asia) | 19 |
| European robin | 191,789 | Europe 96.3%, Asia 3.2%, Africa 0.5% | 89 |
| Blacklegged tick | 1,275 | N America 99.7%, Europe 3, Asia 1 | 6 |
| Wine grape | 14,997 | Europe 94.5%, Asia 1.8%, N America 1.7%, Oceania 0.7%, Africa 0.7%, S America 0.6% | 90 |

Observations:
- Every species is far above the minimum-data rule (50 to 100 thinned records) [V].
- The coordinate, uncertainty, centroid and land steps remove under 1% to 4% of records; the big reductions come from duplicate removal and thinning, as intended [V].
- The uncertainty step removed 0 records everywhere, because the download filter already limits uncertainty to 10 km; the step is therefore a safeguard only [V, inferred].
- Duplicate removal is very strong for the monarch (87% of the records, 367k of 419k). The key is (rounded coordinates, event date, recorder, dataset). Likely causes are obscured/masked coordinates and hidden recorder names in citizen-science data, which would make different observations look identical; not investigated [U]. It does not affect the thinned count much (thinning keeps one per cell anyway), but it should be checked before the key is trusted.
- Contamination outside the native range survives for species where establishmentMeans is mostly empty: sugar maple has 56 final cells in Europe (planted trees), oak 0.5% in Oceania and 0.6% in North America (introduced), monarch 6.7% in Oceania (an established introduced population). The establishment step caught only 1 / 2,199 / 1,117 records for maple / oak / grape [V]. Probe: only about 1.2% of the oak records have any establishmentMeans value; 10 for maple; 0 for tick [V: probe.json "establishment" counts]. Conclusion: native-range polygons (accessible-area step in roadmap 3.1) are required; the GBIF flag alone is not enough [V + reasoning].
- The American robin is 100% North America and the European robin 96% Europe, as expected for their ranges [V].

## 4. Licence loss: CC0 + CC-BY (kept) versus including CC-BY-NC
Counts from the public occurrence-search facets, with the same coordinate / no-issue / present / year >= 1970 conditions, but without the basis and uncertainty conditions [V: run 37527451337, probe job, probe.json]. No other licence appeared among the records meeting these conditions (CC0 + CC-BY + CC-BY-NC = total in all 7 cases) [V].

| Species | Eligible records | CC0 | CC-BY | CC-BY-NC | Kept (CC0 + BY) | Lost by dropping NC |
|---|---|---|---|---|---|---|
| Sugar maple | 56,565 | 25,475 | 5,055 | 26,035 | 30,530 | **46.0%** |
| English oak | 1,470,194 | 406,703 | 731,721 | 331,770 | 1,138,424 | **22.6%** |
| Monarch | 814,783 | 391,452 | 37,306 | 386,025 | 428,758 | **47.4%** |
| American robin | 29,328,446 | 222,387 | 28,806,170 | 299,889 | 29,028,557 | **1.0%** |
| European robin | 10,821,277 | 2,106,811 | 5,944,061 | 2,770,405 | 8,050,872 | **25.6%** |
| Blacklegged tick | 18,212 | 826 | 7,852 | 9,534 | 8,678 | **52.4%** |
| Wine grape | 95,930 | 1,530 | 88,483 | 5,917 | 90,013 | **6.2%** |

- Records of the whole group: GBIF holds 68,779 / 1.73 M / 827 k / 29.4 M / 11.0 M / 20.2 k / 163 k records for these species in total [V: probe "all_records"]. The gap to "eligible" is missing coordinates, issues, absent records and pre-1970.
- Verified in the downloads themselves: they contain only CC0 and CC-BY records [V: results.json "licences_in_file"; no CC-BY-NC in any file].
- The loss is raw records, not cells. After thinning to one record per 2.5' cell the effect on the modelled area will be smaller (many NC records are repeat sightings in already-covered cells) but **it was not measured** [U]. Measuring it needs a second download including CC-BY-NC (see open questions). The geographic bias of the loss is also unmeasured: iNaturalist NC observations may concentrate in particular countries or user groups [U].
- Reading: for the two birds, the bulk of data is CC-BY (eBird, iNaturalist); for monarch, tick and sugar maple, roughly half is lost, which matters most for the species with the fewest records (maple 3.7k final cells, tick 1.3k).
- Licensing/legal: whether a non-commercial licence blocks use as an input to published derived outputs on a free, educational site is a legal question, left to the owner (roadmap section 14) [U].

### 4b. Licence loss measured after cleaning and thinning (the number that matters for modelling)
Follow-up run 38055782451 (workflow spike-a-nc, commit b3f5034, 10 Oct 2026): one extra download per species that also includes CC-BY-NC, cleaned twice with the same pipeline, once with all licences and once restricted to CC0 + CC-BY. Three species were chosen: the two with the largest record-level loss and the sugar maple [V: run 38055782451; data in `docs/spikes/data/spike-a/nc-run-results.json`].

| Species | Download DOI (with NC) | Records, all licences | Cells (2.5 arc-min), all licences | Cells, CC0 + CC-BY | Cells that exist only because of CC-BY-NC | Cell loss |
|---|---|---|---|---|---|---|
| Sugar maple | 10.15468/dl.26u9mg | 54,907 | 11,611 | 3,749 | 7,862 | **67.7%** |
| Monarch | 10.15468/dl.bwmrn5 | 763,891 | 56,132 | 15,201 | 40,931 | **72.9%** |
| Blacklegged tick | 10.15468/dl.9y2662 | 16,837 | 5,669 | 1,276 | 4,393 | **77.5%** |

- Record-level loss was 46% / 47% / 52%; cell-level loss is **68% to 78%**: the NC records are not redundant repeats, they cover most of the occupied cells. Dropping CC-BY-NC cuts the number of occupied cells to roughly a quarter to a third [V].
- Where the lost cells are: sugar maple 7,812 of 7,862 in North America (44 in Europe); monarch 37,149 NA, 2,254 Oceania, 846 Europe, 637 South America; tick 4,392 of 4,393 in NA [V: continents_only_nc]. The continent mix is therefore about the same; the licence loss thins the coverage, not the geography [V].
- The CC0 + CC-BY side reproduced the earlier run (maple 3,749 cells vs 3,739; monarch 15,201 vs 15,157; tick 1,276 vs 1,275): the slight differences are new records since 6 Oct [V, compare section 3].
- What is NOT known: whether a model fitted to the quarter of cells is worse. All three still exceed the 50 to 100 cell minimum, so the species would not be excluded; the effect on skill needs a test (fit both, compare held-out AUC/TSS) once the SDM engine exists [U].
- Not measured for the robins, oak and grape; by the record-level loss (1% to 26%) they are far less affected [V for record level; cell level U].

## 5. GBIF open data on AWS S3 (tested from this sandbox, 10 Oct 2026)
- The bucket `gbif-open-data-us-east-1` is reachable anonymously from this sandbox: S3 listing, ranged GET and DuckDB 1.5.6 (`httpfs`) all work [V: curl and DuckDB runs in this sandbox, 10 Oct 2026]. Practical trap: this sandbox injects dummy AWS credentials into the environment, which make DuckDB fail with HTTP 403 "InvalidAccessKeyId"; unset them or create an empty S3 secret (`CREATE SECRET (TYPE s3, PROVIDER config, KEY_ID '', SECRET '', REGION 'us-east-1')`) [V].
- Monthly snapshots from 2021-04-13 to 2026-10-01 [V: listing]. The latest, `occurrence/2026-10-01/`, is 9,927 objects and 288 GB of Parquet (`occurrence.parquet/000001` to `010448`) plus `citation.txt` containing a GBIF download citation with DOI 10.15468/dl.tup2g6, i.e. one DOI for the whole snapshot [V: listing, file content].
- Schema: 50 lowercase columns (gbifid, datasetkey, species, scientificname, countrycode, decimallatitude, decimallongitude, coordinateuncertaintyinmeters, eventdate, year, taxonkey, specieskey, basisofrecord, license, recordedby, establishmentmeans, issue, ...) [V: DuckDB describe]. All three licences are present (CC0, CC-BY, CC-BY-NC) so the licence filter is applied by us [V: distinct license on file 000001].
- **Gotcha: in this snapshot `taxonkey` and `specieskey` are short strings (for example `D5KCG`), not the integer keys the occurrence API uses (e.g. 5133088)** [V: sample rows from file 000001]. API taxon keys therefore cannot be used to filter; filter on the `species` column (name string) instead, after resolving names through the backbone [V + reasoning]. `hasgeospatialissues` is not a column; the `issue` string must be parsed [V: column list].
- Speed: a ranged scan of 40 files (5.86 M rows) with DuckDB took 7.5 s for `count(*), count(distinct species)` and 5.7 s for a `species IN (...)` filter with group by [V: DuckDB, this sandbox]. The files are not sorted by species (first file mixes seabirds with others; min/max species across 40 files span the alphabet) [V], so no row-group pruning is possible and every query reads the species and licence columns of all 10,448 files. Linear extrapolation of the 40-file timing suggested 25 to 30 minutes per pass [U]. A first full-glob `count(*)` (10 k footers) completed within the 20-minute limit I set, exact time not recorded; a full pass with a `species IN (...)` filter and group by was still running after 20 minutes in this sandbox, so a full pass takes more than 20 minutes here (the 40-file extrapolation of 25 to 30 minutes was too optimistic) [V]. A runner in AWS us-east-1 should be much faster, but that is untested [U].
- **Practical alternative?** Yes for the bulk: one pass with `species IN (<~350 names>)` and the licence/year/coordinate filter would give all species at once into one compact Parquet, with no per-species queue, no 3-download limit and no account. Costs: (1) one DOI (the snapshot's) instead of one per species, which is less specific, though acceptable under GBIF's own rules for open-data snapshots [U]; (2) the snapshot is monthly and a 288 GB scan per refresh; (3) taxon-key encoding as above; (4) you cannot get a per-species download citation that lists exactly the records used. For the 7-species pilot the API route already works and is documented; the S3 route is recommended as the production route for Phase 5 (350 species) and for refreshes [U, judgement].

## 6. Citation and GBIF's derived-dataset procedure
Status of the evidence: GBIF's web documentation could not be fetched from this sandbox (only GitHub, GCS and S3 are reachable), so the rules below are from memory of GBIF's "citing" and "derived datasets" guidance and are **[U]** unless stated; the live API shape is checked in the follow-up run (see 6.3).

1. **What we hold [V]:** every occurrence download has a DOI and a ready citation string `GBIF.org (<date>) GBIF Occurrence Download https://doi.org/<DOI>` (section 2). The S3 snapshot has the same style of citation for the whole snapshot (section 5).
2. **What GBIF asks [U]:** (a) when a publication uses a download as is, cite the download DOI. (b) When the data used is a *subset or combination of several downloads*, or has been processed so that the original DOI no longer describes it, GBIF asks you to register a **derived dataset**: you supply a title, description, the URL or DOI where the derived data is stored (for example a Zenodo deposit), and the list of source download DOIs (or dataset keys) with the number of records each contributed. GBIF issues a new DOI (pattern 10.15468/dd.xxxxxx) and, through it, credits the contributing datasets in their citation counts. Registration requires a GBIF login; the target data must itself be citable and stable.
3. **What this means for us [U, reasoning]:** the public product publishes thinned cell lists and model outputs derived from about 350 downloads, i.e. exactly case (b). The pipeline should:
   - request one download per species (or use the snapshot) and store, per species, the download key, DOI, request date and the exact predicate JSON (all already returned by the runner);
   - keep the cleaning report per species (before/after counts, section 3) and publish it with the data;
   - deposit each release's derived occurrence table (thinned cells per species, with the source DOI per species) on Zenodo, or at least as a versioned release artifact with its own DOI;
   - register that deposit as one GBIF derived dataset per release, listing the 350 download DOIs with record counts, and print the derived-dataset DOI plus the individual download DOIs on the site's data/credits page; each species page shows its own download DOI;
   - never describe the outputs as GBIF data itself, only as derived from it, and keep the CC0 / CC-BY attribution requirement: CC-BY needs credit to the dataset publishers; the DOI route covers this at dataset level, and the publisher names can be listed from the download's dataset table [U].
4. **Open points:** whether GBIF accepts a derived dataset for which the source is "S3 snapshot DOI" rather than download DOIs [U]; whether registering requires the deposit to exist first [U]; the exact API fields (checked below).

6.3 **Live API check [V: run 38055782451].** `GET https://api.gbif.org/v1/derivedDataset` and `?limit=2` return HTTP 405 "Method Not Allowed", so the endpoint exists but takes POST only (registration needs authentication; we did not register anything). The exact request fields are unconfirmed [U]; the GBIF web form at gbif.org (Derived dataset) is the documented route and should be tried once manually before the pipeline automates it.

## 7. Recommendation: GO WITH CHANGES
The pipeline works end to end: login, request, download, clean, cite, for 7 species ranging from 8 k to 29 M records, with no failures in run 6 [V].

Changes required before Phase 2 is built on it:
1. **Decide the licence question with the cell-level numbers in hand.** Keeping only CC0 + CC-BY costs 1% to 52% of records but 68% to 78% of occupied cells for the three species tested (section 4b). For maple, monarch and tick that leaves 1.3 to 15 k cells, still above the minimum, but the model is fitted on a quarter of the observed area. Options: (a) keep the filter (safest, accept lower coverage for citizen-science-heavy species); (b) include CC-BY-NC as model input if legal advice says published derived maps for a free educational site are allowed; (c) keep the filter by default and, per species, run the model both ways during validation and report the skill difference before deciding. Recommend (c), then the owner's legal call.
2. **Add native-range polygons to the cleaning.** The establishmentMeans step catches almost nothing (about 1% of records carry a value), and planted or introduced populations survive in the thinned cells (maple in Europe, oak in Oceania, monarch in Oceania). Section 3.1's accessible-area step is therefore mandatory, not optional.
3. **Re-check the duplicate key.** It removed 87% of monarch records; verify it is not collapsing distinct citizen-science observations with hidden recorder names.
4. **For the 350-species phase, use the S3 snapshot** as the bulk source (one pass, no queue, no 3-download limit, no account), matching on the `species` string not the integer key, and keep the API download route for per-species DOIs on the pilot and for any species needing an exact citation. Decide with the owner whether one snapshot DOI plus a registered derived dataset is acceptable citation practice.
5. **Operational:** budget 15 to 35 minutes of GBIF queue time per batch of three and about 11 minutes of fetch and clean for a 2 GB robin-sized download; run downloads in a dedicated workflow with `workflow_dispatch` and a keys file so interrupted runs resume (the existing runner already does this); store each species' DOI, request date and predicate with the data.

No NO-GO reason found. Not tested: cell-level licence loss for oak, robins and grape; effect of the loss on model skill; GBIF derived-dataset registration; whether `eBird`-sourced records in iNaturalist-like datasets duplicate each other across datasets (GBIF does not deduplicate across datasets) [U].

## 8. Open questions for the owner
1. Is a CC-BY-NC record acceptable as a *model input* when only derived maps and thinned cell lists are published, for a free educational site? (Legal.)
2. Are per-species page citations to individual GBIF download DOIs wanted, or a single release-level derived-dataset DOI?
3. Who will be the GBIF contact for the derived-dataset registration (it needs the account used for the downloads)?
4. Should rare-species exclusion use the thinned cell count (rule: at least 50 to 100) or the raw record count? With the cell count, the licence filter may exclude species that raw counts would keep.
5. The Zenodo (or equivalent) deposit for each release: which account and licence for the derived table?

## Appendix: how to reproduce
- Probe and download: `.github/workflows/spike-a-gbif.yml` (push to `.github/run/spike-a`, put `[download]` in the commit message for real downloads; reuse keys via `.github/run/spike-a-keys.json` or the `download_keys` input). Cell-level licence test: `.github/workflows/spike-a-nc.yml`. Code: `ctw/species/gbif.py`, `occ.py`, `spike_a.py`, `spike_a_nc.py`.
- Job logs, not artifacts, are the readable source of the numbers from the Claude sandbox, since the GitHub artifact host is not reachable from it.
