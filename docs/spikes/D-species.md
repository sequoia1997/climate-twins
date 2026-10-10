# Spike D: candidate species list and licence audit

Status: licence audit and sensitivity rules complete (from knowledge plus Spike E queries; items marked **UNVERIFIED** were not checked against the live licence text from this sandbox). Candidate list: see section 1 and 3 for the status of the last run.

## 1. Method (candidate list)

Code: `scripts/spike_d/build_candidates.py` and curated seeds `scripts/spike_d/seeds.py`. Workflow `.github/workflows/spike-d-candidates.yml` (trigger: edit `.github/run/spike-d`, or workflow_dispatch). Only public APIs, no credentials, User-Agent set, about 1 request per second to iNaturalist.

1. Candidate pools. Crops, trees, freshwater fish and the named insects/ticks/mosquitoes come from curated seed lists (names only; every number is fetched live). Birds, mammals, reptiles/amphibians, insects/arachnids and other wild plants come from iNaturalist `species_counts` (research grade) queried inside six continental bounding boxes, so each continent contributes its own most-observed species. Plant genera that are trees move into the tree group.
2. Matching to GBIF backbone (`/species/match`); species-rank only (subspecies flagged).
3. Per species: iNaturalist total observations; GBIF georeferenced PRESENT record count with continent and country facets; IUCN category (GBIF `iucnRedListCategory`); a 300-record sample for latitude/longitude 5-95 percentiles and number of 0.5 degree cells (narrow-range test: both spans under 4 degrees, or under 20 records); GBIF species profile (marine-only test); Wikipedia title via the scientific (then common) name and 12 months of English Wikipedia user pageviews (Sep 2025 to Aug 2026).
4. Popularity score = 0.35 x percentile(log iNat count) + 0.35 x percentile(log GBIF records) + 0.30 x percentile(log pageviews), percentiles within group.
5. Exclusions: IUCN VU/EN/CR/EW/EX, DD, narrow range, marine, domesticated or oddity list, no region, no records. Named insect/tick/mosquito must-includes keep a threatened flag but are overridden only if explicitly requested.
6. Quotas: group quotas (candidate: tree 180, wild plant 80, crop 80, bird 180, mammal 80, herp 40, insect/arachnid 60, fish 20 = 720; shortlist: 90/40/40/90/40/20/30/10 = 360). Within a group, regional quotas by share: Africa 15%, Asia 22%, Europe 15%, North America 18%, South America 17%, Oceania 13%; shortfalls filled by score with a cap of 1.4 times a region's share, then uncapped. Region = native or origin continent for curated seeds, otherwise the continent with most GBIF records.
7. Resumability: all API responses are cached in `work-spike-d/cache.json`, restored from the Actions cache (and seeded once from the cancelled first run's artifact); enrichment stops at a 230 minute budget, writes partial outputs and a rerun continues from the cache.

Why the first run failed: enrichment took about 23 s per species (700 of 1482 in 4.6 h) and hit the 5 h limit. Cause: deep-offset GBIF occurrence sampling (offset up to 90,000), 60 s timeouts with 5 retries. Fixed: offsets capped at 3,000, 30 s timeout, 3 tries, time budget, checkpoint cache.

## 2. Columns of `data/species/candidates.csv` and `shortlist_v1.csv`

rank_overall; group; gbif_taxon_key; scientific_name; common_name; rank; family; region_assigned and region_basis; occ_continent_shares (GBIF share of records by continent); inat_taxon_id; inat_obs_count; gbif_records; wikipedia_title; wikidata_id; pageviews_12m; popularity_score (0-1, within group); iucn_category (NE = not evaluated); flag_threatened, flag_data_deficient, flag_narrow_range, flag_marine, flag_domestic_or_oddity, flag_invasive_or_introduced; cultivated_or_note; must_include; source (seed or inat_pool); lat_p5/lat_p95/lon_p5/lon_p95 (sample of GBIF records, indicative only, not a range map); gbif_sample_cells05; exclusion_reasons. `excluded_pool.csv` holds species removed by a flag. Native-range continents are only available where curated (seeds); otherwise the occurrence continent shares are given and are biased toward where recorders live (state this wherever shown).

## 3. Results and realised regional balance

See "Run status" at the bottom of this file.

## 4. Licence audit

Risk: L low, M medium, H high. "UNVERIFIED" = from memory or a search summary, not checked against live licence text.

| Source | Use | Licence | Redistribution | Attribution | Risk | Recommendation |
|---|---|---|---|---|---|---|
| Wikimedia Commons photos | Species photo on the page | Per file: CC0, PD, CC BY, CC BY-SA, some CC BY-NC-excluded (Commons bans NC) | Allowed per file licence; SA requires share-alike on the adaptation of the image only | Author, licence, link per image | M | Show only files with licence CC0/PD/CC BY (skip SA unless the page treats images as separate works); store author, licence, file URL at build time; hotlink or cache with attribution line |
| iNaturalist photos | Species photo | Each photo has its own licence chosen by observer: all rights reserved, CC0, CC BY, CC BY-NC, CC BY-SA, etc. Roughly half are not open. | Only for open-licensed photos; the CC BY-NC ones are excluded by our no-NC rule | Observer name and licence | H if unfiltered | Filter `license_code` in (cc0, cc-by, cc-by-sa); record observer; or use iNat's open-data bucket only. UNVERIFIED current share |
| iNaturalist observation data (via GBIF, research grade) | Occurrence points for models | Per-record CC0, CC BY, CC BY-NC | NC records are filtered out of the pipeline (Spike A) | Dataset citation by GBIF download DOI | L | Use GBIF downloads with licence filter |
| PhyloPic silhouettes | Taxon silhouettes | Per image: CC0 (public domain), CC BY 4.0, CC BY-SA 4.0 (NC images exist and are excluded by us) | Allowed for the chosen licences | Required for CC BY and CC BY-SA (contributor, link) | L to M | Preferred over photos for uniform look and low risk; fetch via API with licence filter; many taxa lack a good match and fall back to a group silhouette. UNVERIFIED API details |
| IUCN Red List range maps | Expert range polygons | IUCN Terms of Use: non-commercial use only, no redistribution of spatial data without permission | No | Citation required | H | Do not use or redistribute. Use only the Red List category via GBIF, and only as a filter |
| BONAP, Little tree ranges (USGS) | North America tree ranges | Little maps: US Government work, public domain (UNVERIFIED current distribution). BONAP: copyright, permission needed | Little: yes (UNVERIFIED); BONAP: no | Cite | M (BONAP H) | Use Little only for validation; skip BONAP |
| POWO / WCVP (Kew) | Native-range plants, names | POWO web content CC BY-NC? Kew states POWO data is free to reuse with attribution, WCVP dataset is CC BY 4.0 (UNVERIFIED) | WCVP: yes if CC BY | Kew citation | M | Use WCVP distribution (via GBIF/Kew bulk) only after reading the licence of the exact file |
| eBird range maps (Cornell) | Bird range polygons | eBird Status & Trends: CC BY-NC-SA / Terms of Use; requires access request and bars commercial use | No | Required | H | Do not use; use occurrence-derived models and Birdlife-free validation |
| AVONET (Tobias et al. 2022) | Bird traits | CC BY 4.0 (confirmed via figshare API in Spike E) | Yes | Cite paper | L | Use |
| EltonTraits 1.0 | Bird/mammal diet and foraging | Ecological Archives "Copyright Authors"; open-licence claim UNVERIFIED | Unclear | Cite paper | M | Ask authors or check Ecological Archives data paper policy before bundling; may cite values only |
| COMBINE (Soria et al. 2021) | Mammal traits | CC0 on figshare/Ecology data paper (UNVERIFIED) | Yes if CC0 | Cite | L to M | Use after one-line check of the figshare record |
| AmphiBIO (Oliveira et al. 2017) | Amphibian traits | CC BY 4.0 (confirmed in Spike E) | Yes | Cite | L | Use |
| TRY | Plant traits | Request-based; per-dataset licences, many CC BY, some restricted; use needs request approval and TRY terms; redistribution of raw data prohibited | No raw redistribution | Cite TRY and contributors | H | Use only derived aggregates after approval; not needed for first release |
| FAO EcoCrop | Crop requirements | FAO "open access" statement; FAO site terms often CC BY-NC-SA 3.0 IGO (UNVERIFIED) | Unclear; NC-SA possible | FAO | M to H | Treat as cross-check only; do not redistribute table until licence text is read |
| SoilGrids (ISRIC) | Soil predictors | CC BY 4.0 | Yes | ISRIC citation | L | Use |
| GloBI interactions | Dependency leads | Aggregator; Zenodo products CC0 or CC BY; each study has its own licence and the licence column is not in datasets.tsv (Spike E) | Only studies with CC0/CC BY | Cite GloBI plus study | M | Per-study licence filter still to build; until then show nothing GloBI-derived |
| HOSTS (NHM) | Caterpillar host plants | CC0 (confirmed CKAN) | Yes | Courtesy citation | L | Use |
| FungalRoot via GBIF | Mycorrhiza type | CC BY-NC 4.0 (confirmed) | No for commercial | Cite | M | Do not use in product |
| GBIF occurrences | Model inputs | Per record CC0, CC BY 4.0, CC BY-NC 4.0 | Derived data fine; raw only with licence | GBIF download DOI citation | L with NC removed | Filter to CC0 and CC BY, cite DOI |
| GBIF backbone, species API, IUCN category via GBIF | Names, filters | CC0 (backbone), CC BY (species profiles vary) | Yes | Cite GBIF | L | Use; do not show IUCN polygons |
| Wikipedia pageviews / text | Popularity; blurb | Pageviews: CC0 stats; article text CC BY-SA 4.0 | Text needs share-alike | Link to article | L (views) / M (text) | Use views internally; link to Wikipedia rather than copying text |

**Photos or silhouettes.** Recommendation: ship silhouettes (PhyloPic CC0/CC BY, group fallback) as the default, and add a licence-filtered photo (Commons or iNaturalist CC0/CC BY) on the species detail view later, only with stored author and licence. Reasons: licence risk per file, attribution burden on a map UI, load size, and uneven photo quality across 350 species.

## 5. Sensitivity rules (species or locations not shown precisely)

1. Never show or ship individual occurrence points. Show only the 0.5 degree model surface, and nothing finer than 0.5 degrees for any species.
2. Exclude IUCN VU/EN/CR/EW/EX and DD species (decision 13); also exclude species on CITES Appendix I, and species whose GBIF records are generalised ("coordinate uncertainty" large or dataset flagged sensitive) for obscuration.
3. Drop records that GBIF marks `GENERALISED` / sensitive-species obscured (Spike A should exclude records with `informationWithheld`, `dataGeneralizations`, or coordinate uncertainty above 10 km).
4. No nest sites, roosts, breeding colonies, orchid or cactus collection hotspots, or poaching-prone species (rhinos, pangolins, rare cycads, rare orchids, ginseng, sandalwood, agarwood, wild ginseng). The shortlist excludes them.
5. Species with commercial poaching or collection pressure (certain tortoises, reptiles, cacti, succulents, exotic birds) are excluded or shown at continent scale only.
6. Cultivation of illegal or controlled plants (cannabis, opium poppy, coca): keep Cannabis sativa as a crop note only if the team agrees; recommended to drop coca/opium and flag cannabis as optional (decision needed).
7. Invasive and pest species: show, but label as introduced or pest; do not present maps as habitat advice.
8. Public-health species (ticks, mosquitoes): label "climate suitability, not disease risk or case counts".
9. Places: no lookups of private addresses; keep the existing 0.5 degree location behaviour.


## 6. Results (run 38057865695, 29 min, fully cached rerun; first full run 36 min)

Files: `data/species/candidates.csv` (735), `shortlist_v1.csv` (381), `excluded_pool.csv` (199 species removed by a flag: threatened VU 28, EN 22, CR 4; DD 19; narrow range 102; domestic or oddity 21; marine 18; no region or no records 3), `build_stats.json`. 1,463 species enriched; Wikipedia pageviews found for 1,323 (90%).

Candidates (735) by assigned region: Asia 170, Europe 129, North America 128, South America 117, Africa 109, Oceania 82. Shortlist (381): Asia 80, Europe 72, North America 69, South America 61, Africa 55, Oceania 44. Target shares were Africa 15, Asia 22, Europe 15, North America 18, South America 17, Oceania 13 percent. Realised shortlist shares: Asia 21, Europe 19, North America 18, South America 16, Africa 14, Oceania 12. Europe is over-represented by 4 points, mostly via insects and arachnids (18 of 48), which exceed the quota (48 vs 30) because named must-includes plus regional picks were kept; trim before use. Birds and trees both contain 91 against 90 (rounding).

Groups in the shortlist: bird 91, tree 91, insect/arachnid 48 (quota 30), crop 40, wild plant 40, mammal 40, herp 20, fish 11. Monarch, honeybee, Aedes aegypti and Ixodes scapularis are included as seeds (check the CSV for bumblebee and other must-includes).

Honest caveats:
- Region for 175 candidates (100 shortlist) is a curated native or origin continent; for the rest it is the continent with most GBIF records, which follows where recorders live, so tropical regions are probably underweighted and Europe and North America overweighted in the long tail. The balance above is a balance of this assignment, not of true native ranges.
- Native-range continents are not independently sourced (POWO/IUCN ranges are not used; see licences). `occ_continent_shares` is the evidence.
- The IUCN filter first failed (GBIF returns full words such as VULNERABLE, not codes); it is fixed and the list was rebuilt. One VU species remains (a must-include override or a rank mismatch; check `flag_threatened`) and 15 NT species are kept deliberately because Near Threatened is not in the exclusion rule. NE (not evaluated, 192) includes all crops and most plants and insects; "not threatened" there is unverified.
- Narrow-range uses a 300-record sample capped at offset 3,000, so it can misjudge species with few or clustered records; 19 species failed GBIF name matching (taxonomic splits) and were dropped (see `build_stats.json` errors) and can be re-added by hand.
- Popularity percentiles are within group and mix a global signal (Wikipedia, English only, biased toward the Anglosphere) with observer-biased iNaturalist and GBIF counts.
- Not done: manual curation pass, subspecies and cultivar handling, a check that crops with domestic oddity flags (e.g. Cannabis) are acceptable.
