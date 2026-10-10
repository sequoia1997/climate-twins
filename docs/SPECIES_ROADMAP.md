# Climate Twins: species roadmap

Status: proposal, not yet started. Written 6 October 2026.
Goal: show how **where organisms can live** changes with the climate, worldwide, for a few hundred familiar species, and how that depends on the species they rely on. Make it as authoritative as a free public tool can be.

Anything marked **[verify]** is my recollection of an external dataset or service and must be confirmed in Phase 0 before we build on it.

---

## 1. What we are actually claiming

The honest, defensible claim is:

> "The climate in this area is projected to become more or less like the climate where this species is found today."

That is **climate suitability**, not a forecast of where the species will be. The gap between the two is real:

| Not captured | Effect | How we handle it |
|---|---|---|
| Dispersal (trees move far slower than climate does) | Overstates new range | Show bounds: *unlimited* vs *limited by dispersal* vs *stays put*, using trait data |
| Soil, terrain, land cover, land use | Over-predicts where a species can actually grow | Use soil and terrain predictors held constant; mask to natural range; say so |
| Other species (food, hosts, pollinators) | Over-predicts for dependent species | Layer 3, curated and limited to tight dependencies |
| Adaptation, plasticity, CO2 effects | Unknown, can go either way | Stated as a limitation, not modelled |
| Climates with no present-day analog | Model extrapolates | Flag cells outside the species' training climate (we already have the σ machinery for this) |
| Microclimate | Real refuges are smaller than a grid cell | State the cell size on every map |

Every map and sentence in the product follows from this. The wording "climate suitability" is non-negotiable; "will live in" is never used.

---

## 2. Your question: higher-resolution climate data

What we have today (from `web/methods.html` and `config.toml`):

| Use | Data | Native resolution | What we use |
|---|---|---|---|
| North America, present | AdaptWest / ClimateNA 1991–2020 | **1 km** | Averaged to 15 km blocks for matching |
| World, present | TerraClimate 1991–2020 | ~4 km | Averaged to 0.5° (~55 km) for matching |
| Future changes | NASA NEX-GDDP-CMIP6 | 25 km | Applied as change factors (20 of 24 models) |
| Cross-checks only | CHELSA v2.1 (1 km, 1981–2010), WorldClim 2.1 (future, 10 arc-minute), AdaptWest 8-model future, ERA5, CHIRPS | various | Reported, not used for the main answer |

So we did try higher resolution, but only as **checks**. The matching grids are coarse on purpose: the twin search compares every place against every cell, and cost grows with cell count.

Species modelling is a different job and does not have that limit. We fit a model and predict each cell once, so cost grows linearly. That makes native-resolution climate affordable.

**What higher resolution does and does not buy.** The climate models themselves resolve about 100 km. Statistical downscaling (NEX-GDDP, WorldClim, CHELSA, AdaptWest) adds terrain detail, mostly elevation and coast effects, but it does not add new physics. The *change* signal carries roughly 25–100 km of real information; the *baseline* at 1–4 km carries real topographic detail. For species this matters a lot, because a mountain slope can span several climate zones inside one coarse cell.

### Options for the global climate stack

| Tier | Grid | Baseline | Futures | Notes |
|---|---|---|---|---|
| **A (recommended)** | 2.5 arc-minute (~4.5 km) | TerraClimate 1991–2020 at native ~4 km, plus its water-balance variables | NEX-GDDP change factors, same as the rest of the site | Same method and period as the site. About 6 million land cells, cheap. Includes climatic water deficit and actual evapotranspiration, which matter most for plants |
| **B (later, regional)** | 30 arc-second (~1 km) | CHELSA v2.1 or WorldClim 2.1 baseline, possibly adjusted to 1991–2020 using TerraClimate | Their own CMIP6 futures, or our NEX deltas applied | About 150 million land cells globally, so process in tiles. Valuable in mountains. Baseline period (1981–2010 or 1970–2000) differs from our 1991–2020, which must be bridged |
| **C (North America only)** | 1 km | AdaptWest 1991–2020 | AdaptWest 8-model future, or our NEX deltas | Already in the pipeline; just not used at native resolution |

**Recommendation:** build Tier A for everything, because it keeps one consistent method and period across the site and is cheap to run for hundreds of species. Add Tier B/C tiles later for mountainous regions, and as a *sensitivity check* during Phase 3 (does a species' projected area change differ much between 4.5 km and 1 km?). If it does, that is itself a finding worth reporting.

The GitHub Actions runners have reached WorldClim and CHELSA before (the cross-check jobs). The sandbox cannot reach CHELSA, so any 1 km work runs in Actions. Runners are free for a public repo but limited (about 7 GB RAM, 14 GB disk, 6 hours per job), so every step must be tile-based. **[verify]** CHELSA future-climate file availability and size.

---

## 3. Authoritative-by-design: the scientific method

"Authoritative" here means following accepted species-distribution-modelling (SDM) practice, testing against history, publishing everything, and having it reviewed. The pieces:

### 3.1 Occurrence data
- **Source:** GBIF (includes iNaturalist research-grade). eBird for birds if its terms allow **[verify]**.
- **Use the GBIF Occurrence Download API, not scraping.** Each download gets a DOI, which gives us a clean, citable provenance trail. A bulk copy of GBIF also sits in open cloud storage in Parquet **[verify]**, useful for exploration. Needs a free GBIF account stored as a repository secret.
- **Licence filter:** keep only CC0 and CC-BY records. This loses some data but avoids non-commercial restrictions if the site ever has revenue.
- **Cleaning:** drop records with bad coordinates, country-centroid and institution-centroid points, ocean points for land species, large coordinate uncertainty, fossils, escaped or cultivated records, and dates before ~1970 (for the baseline fit). CoordinateCleaner-style checks.
- **Taxonomy:** one backbone (GBIF Backbone plus World Flora Online for plants), resolve synonyms, record the mapping.
- **Sampling bias:** records cluster near roads and cities. Thin to one record per cell and build the background sample from records of the *same taxonomic group* (target-group background), a standard bias correction.
- **Accessible area:** model within the region the species could plausibly have reached (native range, biogeographic region), using expert range data where licences allow (Plants of the World Online, BONAP, Little tree range maps, eBird ranges **[verify licences]**; IUCN range maps are not redistributable, so use only as a private check). Do not project a native North American species onto Africa unless explicitly modelling invasion.
- **Minimum data rule:** at least ~50–100 thinned records, otherwise the species is excluded. This also keeps rare species out, which is the stated scope.

### 3.2 Predictors
Uncorrelated, biologically meaningful variables:
- Climate: annual mean temperature, temperature seasonality, coldest-month minimum, warmest-month maximum, annual and seasonal precipitation, growing degree days, frost days.
- Water balance (TerraClimate): climatic water deficit, actual evapotranspiration, soil moisture. For plants these often beat precipitation.
- Fixed (held constant into the future): elevation and terrain (SRTM or Copernicus DEM), soil properties (SoilGrids). Land cover is used only as a mask, since we cannot project it.

### 3.3 Modelling
- An **ensemble of algorithms** (for example Maxent, boosted regression trees, random forest, a GAM), averaged, rather than one method. Standard in practice (biomod2-style).
- **Spatial block cross-validation**, so test records are not next to training records. Metrics: AUC, TSS and the Boyce index.
- **Our existing strength:** a Mahalanobis (σ) niche distance as an additional, transparent model. It gives a "how typical is this climate for the species" number in the same units the site already uses, and a natural novelty flag.
- **Future projection:** the same 24-model ensemble, same scenarios, same warming levels as the rest of the site. Report agreement across climate models, and separately across SDM algorithms.
- **Dispersal bounds:** unlimited, limited (a distance per decade from trait data: seed dispersal, bird movement), and none.
- **Extrapolation control:** flag cells where any predictor lies outside the training range (MESS-style) and shade them on the map.

### 3.4 Validation: the credibility step
1. **Skill gate per species.** Spatial-CV AUC/TSS above a threshold, or the species is not published.
2. **Hindcast.** Fit on earlier climate and records, then test whether the model reproduces documented shifts. Good public data:
   - North American Breeding Bird Survey (from 1966).
   - European Breeding Bird Atlases (1980s vs 2010s).
   - US Forest Service Forest Inventory plots for tree range shifts.
   - The site already has a hindcast routine for the twin method that can be extended. **[verify]** each dataset's access and terms.
3. **Comparison with published projections.** For species that others have modelled (for example USFS tree atlas, Audubon climate birds), compare and explain differences. We should not be an outlier without a reason.
4. **Expert review.** Ask at least one practising SDM ecologist to review the method before launch, and a botanist/ornithologist for the species lists. Budget time for this.

### 3.5 Transparency
- Per-species page lists records used, DOIs, predictors, algorithms, skill scores, caveats.
- Code, species list, parameters and outputs versioned in the repo; releases archived with a DOI (Zenodo).
- A methods section, and ideally a short methods paper, so the work can be cited.

---

## 4. Species selection (global, popular, not rare)

Popularity score = a blend of iNaturalist observation counts, GBIF record counts and Wikipedia page views (all public). Then apply **quotas** so the list is not all North America and Europe.

Indicative targets (about 350):

| Group | ~Count | Examples (illustrative only) |
|---|---|---|
| Trees | 90 | oaks, maples, pines, eucalypts, baobab, teak, olive, cedar of Lebanon |
| Other wild plants | 40 | grasses, familiar wildflowers, cacti |
| Crops and horticulture | 40 | wine grape, coffee, cacao, wheat, rice, citrus (EcoCrop-style requirements as a cross-check) |
| Birds | 90 | familiar migratory and resident birds across continents |
| Mammals | 40 | elephants, wolves, deer, big cats (only widespread, non-threatened to begin) |
| Reptiles and amphibians | 20 | common frogs, snakes, tortoises |
| Insects and arachnids | 30 | monarch, honeybee, bumblebees, mosquitoes, ticks (public-health interest) |
| Freshwater fish | 10 | trout, bass (air-temperature proxy for water temperature; flag it) |

Excluded to start: threatened species, narrow endemics, marine species (they need ocean temperature data and a separate pipeline), and anything with sensitive location data. The 0.5°-scale presentation also protects exact locations.

Coverage will be uneven, because tropical regions have far fewer records. Reliability is labelled per species and per region; we do not pretend otherwise.

---

## 5. Layer 3: dependencies between species

- **Data:** GloBI (open interaction records), HOSTS (butterfly and moth host plants), diet and trait databases (EltonTraits, AVONET and similar), plant–pollinator datasets, FungalRoot for mycorrhizal links. **[verify]** each.
- **Curate, don't mass-generate.** Interaction databases are patchy and mostly record generalists. Only claim a dependency where it is obligate or near-obligate and documented in the literature (monarch and milkweed, specialist pollinators, host-specific insects). Start with ~100 hand-checked pairs.
- **Metric:** *exposure*. For a dependent species, the share of its future suitable area that also overlaps the future suitable area of at least one of its required partners, compared with today. Reported with the dispersal bounds from section 3.3.
- **Not claimed:** timing mismatches (phenology), cascading effects, or the stability of food webs. Those are listed as research frontiers.

---

## 6. Architecture

### Pipeline (GitHub Actions, like the existing rebuild)
New workflows alongside the current ones:
1. `species-climate`: build the global predictor grid (Tier A) and ensemble futures. Tile-based.
2. `species-occ`: fetch and clean occurrences (GBIF download, cached by DOI).
3. `species-fit`: matrix job, one species per job. Fit, cross-validate, project, run gates.
4. `species-validate`: hindcast and comparison reports.
5. `species-publish`: assemble outputs, run the page test, open a PR with a report (same "routine / needs review" pattern as `rebuild.yml`).

Each job writes a report row (skill, records, area change, agreement, flags) and the PR fails visibly if a gate fails, matching how `validate.py` works for the climate data.

### Data volume and hosting
- Projection at ~4.5 km: ~6 million land cells. Per species per scenario, three time slices plus agreement fit in a few MB as quantised raster tiles; most cells are empty so compression is strong. Estimate: **1–3 MB per species per scenario**, so roughly **a few hundred MB to ~1 GB** for 350 species and four scenarios. **[verify with the pilot]**
- That is too much for the current static site bundle. Put species files on **Cloudflare R2** (the site is already on Cloudflare) and load only the species opened, the same lazy-loading idea as the place shards. Use a range-readable tile archive (PMTiles) or value-encoded PNG tiles coloured in the browser, so toggling scenarios is instant.
- A small `species/index.json` (names, groups, popularity, bounding boxes, skill) loads at startup; species detail loads on demand.

### Cost
- Compute: free runners for a public repo, within time and size limits.
- Storage: cents per month at this scale.
- GBIF: free.
- Dominant cost: agent and model time, plus expert review. I can't price this precisely; I'd set a budget per phase and track it on the status board, stopping at gates.

---

## 7. Product design

### Entry points
1. **Place-centred** (extends what exists): a "Species" section in the data pane. "At Raleigh, 14 of 350 tracked species lose suitable climate by ~2070; 22 gain it." Sorted, filterable by group, with confidence.
2. **Species-centred:** search a species. Map shows range now, future and change (lost / kept / gained, colour-blind-safe), with the twin-style arrow for the range shift, area change, centroid shift in km and direction, and model agreement.
3. **Layer 1 shortcut** (fast to ship, see Phase 4): species recorded around the climate twin's location but not near the home place, as "possible newcomers". Labelled clearly as analog-based, not modelled.

### Controls
Scenario and period (reusing the existing controls and the warming-level view), dispersal bounds, show/hide low-confidence areas, novelty shading, side-by-side now vs future.

### Dependencies view
On a species page: "Depends on" and "Depended on by", each with now vs future overlap bars, in the same Values / Change style as the data pane figures.

### Quality and trust cues
Reliability badge per species, cell-size note, "climate suitability, not a forecast" line, link to the species methods page, records DOI.

### Mobile and access
Same bottom-sheet pattern. Maps must work without colour alone, and charts need text equivalents, as already required elsewhere on the site.

### Requests
The existing "Request a place" form becomes "Request a place or species". Rare or sensitive requests are declined with an explanation.

---

## 8. Phased roadmap

Effort is given in rough working sessions and is a guess; the plan has a stop/go gate after each phase.

### Phase 0: spikes and decisions (1–2 sessions)
Run four investigations in parallel, each producing a short written finding:
- **A. Occurrences:** GBIF download API with credentials; open-data Parquet access; fetch and clean 5 pilot species; check licence filtering and record counts.
- **B. Climate stack:** TerraClimate native-resolution and water-balance reads; Tier A grid build for one region; WorldClim and CHELSA 1 km availability and throughput from Actions; how to bridge baseline periods.
- **C. Validation data:** access and terms for BBS, European atlases, Forest Inventory data; define the hindcast test.
- **D. Species and licences:** rank candidate species by popularity with quotas; audit licences for range maps, photos, trait and interaction datasets.

Exit: written decisions on climate tier, occurrence route, species list v1, licences, and an ecologist reviewer identified.

### Phase 1: global predictor grid (2–3 sessions)
Build the Tier A grid: baseline, ensemble future changes for all scenarios and periods, warming levels, water balance, terrain, soil. QA against the existing site's own numbers. Output as Cloud-Optimized rasters on R2.
Exit: grid passes consistency checks against the site's present data (matching present climate within tolerance) with a QA report.

### Phase 2: occurrence pipeline (2 sessions, overlaps Phase 1)
Taxonomy mapping, GBIF download, cleaning, thinning, accessible-area masks, trait tables. Reproducible by one command per species.
Exit: cleaned datasets for the 25 pilot species with counts, DOIs and logged exclusions.

### Phase 3: model engine, pilot and validation (3–4 sessions)
Ensemble SDM, spatial CV, novelty flags, dispersal bounds, summary statistics. **Pilot on ~25 species** (trees and birds, where validation data is best). Hindcast tests. Compare with published projections. Tier A vs 1 km sensitivity check.
Exit gate (important): skill thresholds met, hindcast reproduces observed shifts reasonably, no unexplained disagreement with the literature, and the ecologist signs off the method. **If this fails, we stop or change approach before building any UI.**

### Phase 4: delivery and first product (3 sessions)
R2 hosting, species index, species page and map, place-centred species list for the pilot species, **Layer 1 "possible newcomers"**, methods and changelog entries, accessibility pass, page tests (extend `tests/test_page.py`), live check.
Exit: pilot species live, with reliability labels and caveats, and measured page-load budget.

### Phase 5: scale to ~350 species (4–6 sessions, in waves of ~50)
Each wave: fit, validate, review the gate report, publish. Track coverage by region and group against the quotas and shift effort to gaps. Automate the "needs review" path as in the data rebuild.
Exit: target list published or consciously trimmed where skill is poor; coverage report.

### Phase 6: dependencies layer (3–4 sessions)
Curate the first ~100 dependency pairs, compute exposure, build the dependency view. Literature check on every claim shown.
Exit: pairs published with citations and the limits stated.

### Phase 7: hardening and publication (2–3 sessions)
Performance, cost review, security and licence review, a methods paper or preprint, a Zenodo release, and folding species into the yearly rebuild (new species become rows in a config file).

### Phase 8+: growth
More species (user requests), marine and freshwater temperature models, 1 km regional tiles in mountains, phenology, invasion-risk views, crop suitability tools, community-level summaries.

---

## 9. Parallel workstreams (how agents help)

| Workstream | Can run alongside |
|---|---|
| Climate grid | Occurrence pipeline, species list, licence audit |
| Occurrence pipeline | Climate grid, UI design |
| Model engine | UI scaffolding using fixture data |
| Validation datasets | Everything |
| UI and R2 delivery | Model engine (against synthetic outputs, as we did for the extremes chart) |

Lessons from this project to apply: a visible status board; never trust a synthetic-data screenshot for real values; keep gates in the pipeline so a bad run fails loudly; and pin library versions (an unpinned xarray release broke a run).

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Scientific criticism of climate-envelope models | Hindcast validation, published method, ecologist review, wording, dispersal bounds |
| Sparse tropical data | Minimum-data rule, regional reliability labels, quotas, accept a thinner tropical list |
| Resolution too coarse in mountains | Tier B/C tiles, explicit cell-size note |
| Licence or citation problems | Licence filter, GBIF DOIs, audit before any photo or range map is shown |
| Misuse for land or planting decisions | Clear wording, links to methods, no recommendations |
| File sizes and load time | Lazy loading from R2, per-species budgets, pilot measurement |
| Dependency claims overreach | Curated and obligate-only, citations shown |
| Cost overrun | Gates and budgets per phase |
| Data source changes (like the xarray release) | Pin versions, the monthly watch job, tests |

---

## 11. Decisions needed from you

1. **Climate tier:** go with Tier A for the first release (my recommendation)?
2. **Intended use:** education and curiosity only, or might people use it for planting, farming or land decisions? That sets the strictness of the wording and the validation bar.
3. **Reviewer:** do you know an ecologist who would review the method? If not, I'd draft a short review brief.
4. **Crops and pests:** include them in v1 (high interest, but ticks, mosquitoes and crops draw closer scrutiny)?
5. **Budget and stopping points:** a spending ceiling per phase.
6. **GBIF account:** needs a free account and credentials saved as a repository secret.

---

## 12. First session plan (when compute resets)

1. Create a status board for this project.
2. Launch the four Phase 0 spikes in parallel (A–D above).
3. Draft the species list v1 with quotas and the licence audit table.
4. Report back with a go/no-go on the climate tier and occurrence route, and a refined schedule.

---

## 13. Decisions recorded (6 October 2026)

- Intended use: education only. Wording stays "climate suitability, not a forecast". Revisit if use for planting or land decisions is ever wanted.
- Crops and pests (ticks, mosquitoes) are in the first release.
- Scope: global from the start. Rare and threatened species excluded to begin with.
- Budget: no ceiling per phase. Spending is still tracked on the status board.
- Ecologist reviewer: none identified yet. Until one is found, the Phase 3 validation gate (skill scores, hindcast, comparison with published projections) is the main quality control, and a one-page review brief will be prepared.
- GBIF: account created. Needs repository secrets `GBIF_USER`, `GBIF_PWD`, `GBIF_EMAIL` (Settings, Secrets and variables, Actions). A short Actions job will confirm the login works without printing it.

---

## 14. Updates after the Phase 0 spikes (10 October 2026)

- **European Breeding Bird Atlas data is paid, so it is dropped.** The planned second validation test is gone. Europe and other regions outside North America can only be checked with weaker free tests (GBIF before/after splits restricted to well-sampled cells, transfer tests to other continents, free national monitoring data to be investigated).
- **Validation is tiered, and every species page states its tier:** Tier 1, tested against real observed change (North American birds from the Breeding Bird Survey, plus whatever else the free tests support); Tier 2, spatial hold-out skill only, clearly labelled; Tier 3, below the skill gate, not shown. Pilot species without a verified validation dataset (monarch, blacklegged tick, wine grape) start at Tier 2.
- **Do not use in the public pipeline:** eBird Status and Trends (no redistribution without written permission), Christmas Bird Count (not open), eBMS (signed licence). Optional private sanity checks only, kept out of the repo.
- **Dependencies layer (Layer 3) is smaller than planned.** Expect roughly 25 to 40 reviewed obligate or near-obligate pairs, not 100. The big interaction database (GloBI) is too noisy to ingest as a source; every pair shown needs a person-read citation and a specialist reviewer. A mycorrhizal dataset is non-commercial only and conflicts with the licence filter. The "limited dispersal" bound is uncalibrated (about 10 times uncertain) until the hindcast calibrates it.
- **iNaturalist data comes through GBIF.** The CC0 and CC-BY filter drops observations licensed CC-BY-NC. Spike A is counting the loss; whether non-commercial records may be used as model inputs for a free educational site that publishes only derived outputs is a legal question to settle before relaxing the filter.
- **Spikes A, B, D, F and G were interrupted by a usage limit and restarted on 10 October.**

---

## 15. Phase 0 outcome (spikes A to G, 10 October 2026)

Overall: **GO WITH CHANGES.** The method works on virtual species; the data routes work; the main risks are licensing, native-range handling, validation outside North America, and the dependency layer being small. Detailed findings: `docs/spikes/A` to `G`.

### Corrections to this roadmap
- **Cell counts were understated:** global land is about 12.5 million cells at 2.5 arc-minute (not 6 million) and about 313 million at 30 arc-second (not 150 million). Build globally in latitude bands (a whole-globe read peaked at ~8 GB RAM).
- **Water balance:** use TerraClimate's own deficit and evapotranspiration for the baseline (our own deficit calculation runs about 25% low).
- **Baseline periods:** WorldClim 1970 to 2000 is 0.87 C cooler than TerraClimate 1991 to 2020, and CHELSA 1981 to 2010 is 0.73 C cooler, so 1 km sources need explicit period bridging. Seasonality predictors (bio15, bio17) agree poorly between sources (r 0.67 to 0.94).
- **Native range is mandatory.** GBIF rarely records native versus introduced (about 1%), so introduced populations (sugar maple in Europe, monarch in Oceania) survive cleaning. Restrict training to native-range polygons.
- **Check the duplicate-removal step** (it removed 87% of monarch records) before trusting the cleaning.
- **Modelling defaults (from virtual-species tests):** at least 100 thinned records (narrow-range species about 500); target-group background to correct sampling bias; choose predictors by ecology, not "all 16"; one boosted-tree model matched the four-model ensemble; do not rely on AUC alone; flag novel climate (withhold shift numbers when more than 15% of the area is novel). Resolution matters most for narrow species. The method misses non-climatic range limits, so expert-range or hindcast checks are mandatory.
- **Licence filter:** CC0 and CC-BY only loses 46% of sugar maple, 47% of monarch and 52% of tick records (68 to 78% of occupied cells for those three). Decide on CC-BY-NC for model inputs (legal question) before relaxing it.
- **Delivery:** custom compact binary format drawn on the GPU (about 226 KB per species for one scenario; about 265 MB for 350 species by 4 scenarios) on a Cloudflare R2 bucket, separate publish workflow. Tested on synthetic data only.
- **Species list:** `data/species/shortlist_v1.csv` (381 species, balanced by region and group), with known fixes needed: one vulnerable bumblebee still in candidates, 19 species failed name matching, insects over quota (48 versus 30). Show silhouettes by default, not photos.
- **Dependencies:** about 25 to 40 reviewed pairs, not 100 (see section 14).

### Decisions still needed from the owner
1. Whether CC-BY-NC records may be used as model inputs (legal check).
2. Silhouettes by default instead of photos (recommended).
3. Accept a custom file format for map delivery, a continuous versus classed colour ramp, and the data value range.
4. Whether to go straight to the Phase 1 to 3 pilot (grid, occurrence pipeline, model engine and hindcast on about 25 species).

### Proposed next step: the pilot (Phases 1 to 3)
Build the global Tier A grid in bands; the occurrence pipeline with native-range masks; the modelling engine with the gates above; hindcast on North American birds (Breeding Bird Survey) and trees (forest plots); about 25 pilot species including the seven spike species. Exit gate: skill thresholds met and hindcast reproduces observed shifts reasonably, or we stop before any interface work.
