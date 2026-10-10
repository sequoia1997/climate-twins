# Spike A: GBIF occurrences

Resumed 10 October 2026 after the first agent was cut off. Status: sections 1 to 5 written from run logs; sections 6 to 8 (S3/DuckDB test, derived-dataset citation, recommendation) being completed below.

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
- Sampling bias is visible: the American robin is 100% North America, as expected for its range, but the species is a good test of the cap on records per cell; the thinned 303k cells is plenty [V].

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

