# W4: real-history validation (hindcast) for the species pilot

Status: **in progress.** Last update: 10 October 2026. Owner: workstream W4. This document extends and updates `docs/spikes/C-validation.md`
(spike C) and `docs/spikes/C-reviewer-brief.md`; it does not replace them. Every claim is marked **[V run N]** (verified in a GitHub Actions run or a
local command) or **[U]** (unverified).

## 0. Summary of the current state

| item | state |
|---|---|
| Metrics, nulls, thresholds, minimum-species rule, verdicts, report generator (`ctw/species/hindcast.py`) | done, unit-tested on synthetic data (`tests/test_species_hindcast.py`) |
| BBS ingest and observed-change metrics (`bbs.py`, `w4_bbs_run.py`, workflow `pilot-w4-bbs.yml`) | done, real run verified (section 3) |
| FIA ingest and tree change test (`fia.py`, `w4_fia_run.py`, workflow `pilot-w4-fia.yml`) | code done and tested on synthetic data; first real run: see section 4 |
| Comparison with published tree projections | species presence verified in RDS-2024-0020 (section 5); comparison with our model waits for W3 |
| GBIF before and after for the two European species (`gbif_split.py`, `w4_gbif_run.py`, workflow `pilot-w4-gbif.yml`) | protocol and code done and tested; real run executes end to end but **waits for W2's target-group grids**: the `w2-tg-bird.npz` and `w2-tg-plant.npz` on the release are all zeros at 18:55 UTC (run 38077216009, diagnostics in `docs/pilot/W4-hindcast-report-gbif.md`), so no block can be called well sampled and no absence defined |
| Full BBS model hindcast (`hindcast_run.py`, `w4_hindcast_run.py`, workflow `pilot-w4-hindcast.yml`) | **done: group test FAILS (change), static skill good, no Tier 1** (section 3b) |

**Key structural finding (important for the pilot exit gate).** The minimum-species rules of C-validation 4.7 (30 species for BBS, 20 for FIA) cannot be
met by the pilot list: `data/species/pilot_v1.csv` has **10 birds** with a BBS plan and **5 trees** with an FIA plan, and the two European species
have no free before and after test of any strength. Applied as written, the pilot hindcast therefore returns **"insufficient data"** for every group, which is
by design not a pass. To get a conclusive test the validation needs a larger **validation-only species set** (about 40 widespread BBS birds and about
20 FIA trees) fitted by the same pipeline; these need not be published pilot species. Section 8 lists them once the data run has chosen them.

## 1. Rules for this work

Data downloads run only in Actions (`.github/workflows/pilot-w4-*.yml`, each triggered by a push to its own file `.github/run/pilot-w4-<name>`, plus manual dispatch;
the roadmap's single trigger path was split so one workflow can be re-run without the others). Large outputs go to the assets of the release tagged
`species-pilot-data`; small tables are committed to `data/species/w4/`. Public-pipeline exclusions (owner decisions): European atlas data (paid), eBird Status and Trends,
Christmas Bird Count and eBMS are **not used**.

## 2. Verified data facts

BBS (ScienceBase item 691cfb53d4be021d1d89b482), probe run 38072387399:
- Title "2025 Release - North American Breeding Bird Survey Dataset (1966 - 2024)"; `rights` field: CC0 1.0; last updated 2026-09-28. **[V 38072387399]**
- Files: `Routes.csv` (0.39 MB), `SpeciesList.csv` (74 KB), `Weather.csv` (13.8 MB), `VehicleData.csv` (60.5 MB), `States.zip` (63 MB), `50-StopData.zip` (64.6 MB, `Fifty1.csv` to
  `Fifty10.csv`), `MigrantNonBreeder.zip`, two PDFs (RunType, completeness report) and FGDC XML. **[V 38072387399]**
- `Routes.csv` columns: CountryNum, StateNum, Route, RouteName, Active, Latitude, Longitude, Stratum, BCR, RouteTypeID, RouteTypeDetailID; values are space padded. **[V]**
- `SpeciesList.csv` columns: Seq, AOU, English_Common_Name, French_Common_Name, Order, Family, Genus, Species. **[V]**
- Count files: columns RouteDataID, CountryNum, StateNum, Route, RPID, Year, AOU, Stop1 to Stop50 (50-stop file). Contents of `States.zip` members: see section 3 (run log). **[V for 50-stop]**

FIA DataMart (`https://apps.fs.usda.gov/fia/datamart/CSV/<ST>_<TABLE>.csv`), same probe run:
- `DE_PLOT.csv` (2093 rows): columns include CN, PREV_PLT_CN, INVYR, STATECD, PLOT_STATUS_CD, MEASYEAR, DESIGNCD, KINDCD, LAT, LON, CYCLE, SUBCYCLE. **[V]**
- Delaware shows the pattern for every state: periodic cycles 3 (MEASYEAR 1985 to 1987) and 4 (1999), then annual cycles 5 to 8 from 2004 (MEASYEAR up to 2026). DESIGNCD values 1, 101, 111, 112,
  113, 115, 999 (older designs exist). **[V]** So "first complete cycle" is a periodic inventory with a different plot design than the annual one; design is carried in the output and a
  DESIGNCD = 1 only variant is run.
- `DE_TREE.csv` has PLT_CN, STATUSCD, SPCD, DIA; `DE_SEEDLING.csv` has PLT_CN, SPCD, TREECOUNT, CYCLE. `REF_SPECIES.csv` exists. **[V]** SPCD of the five pilot trees (sugar maple 318, red maple 316,
  eastern white pine 129, quaking aspen 746, white oak 802) is checked against `REF_SPECIES` in the FIA run log (section 4); SPCD 802 appears as white oak in the DE sample. **[V partly]**
- Coordinate fuzzing: `LAT`/`LON` are the public coordinates. The FIA documentation pages I could reach did not state the fuzzing distance; the commonly cited rule (about 1 mile, with swapping of some
  private plots within the county) is **[U]**. Mitigation that does not depend on the exact rule: analysis cells are 0.5 degrees (about 55 km), 30 times the largest rule quoted.

USFS tree projections, probe runs 38072387399 and 38072731571:
- RDS-2019-0029 (DISTRIB-II): "habitat suitability of eastern United States trees", 125 species, baseline 1981-2010 and 2070-2099 under eight scenarios; shapefiles (`Data/spNNN_hybrid_2100.*`), US government data "can be used
  without additional permissions or fees", citation required. **[V]** Which pilot species are in it: section 5.
- RDS-2024-0020: 326 species, 1991-2020 baseline, two scenarios (SSP2-4.5, SSP5-8.5) to 2070-2100; zip of 412 MB with 13,102 entries, one folder per species, e.g. `Data/Acer_saccharum/` with `Actual_sp318.tif`,
  `CurrentPredicted_Consensus_sp318.tif`, `SSP2-45_Predicted_Consensus_sp318.tif`, `SSP5-85_Predicted_Consensus_sp318.tif`, HQCL (habitat quality/colonisation) rasters. Sugar maple is present. **[V 38072731571]**

## 3. Test 1: North American Breeding Bird Survey

Pipeline (`ctw/species/bbs.py`, `w4_bbs_run.py`):
1. A route-year is **acceptable** when `Weather.RunType == 1` and `RPID == 101`. A route **qualifies** with at least 10 acceptable years in each of 1966-1985 and 2005-2024.
2. A species is **present on a route** in a window with detections in at least 3 acceptable route-years of that window (proposal of C-validation 4.3).
3. Routes are placed on the 1/24 degree grid (4320 x 8640, row 0 north, `grid_rc`, same convention as `climategrid.py`) by their **start point**. Limitation: a route is about 40 km long, so one start
   cell stands for a transect that crosses roughly ten cells; model predictions at the start cell are therefore a coarse stand-in, and the analysis can be repeated at 0.5 degree blocks (`block=12`).
4. Observed change per species on the qualifying route cells (weight one per cell): centroid shift (km, bearing), northward component, leading (95th percentile latitude) and trailing (5th) edge shifts,
   occupancy change, with bootstrap over cells (500 replicates by default; 200 in the Actions run), and two nulls for the observed signal: the **2 SE rule** (a shift smaller than twice its bootstrap SE
   is treated as noise) and a **label-swap permutation test** (swap window labels per cell, share of null shifts at least as large).
5. Eligible species for a group test: at least 100 route-presences in both windows.

Results (first real run, Actions run 38072944625, all values **[V 38072944625]**; table `data/species/w4/bbs_observed_change.csv`, full files in release `species-pilot-data`):

- 5,838 routes in `Routes.csv`; 127,646 acceptable route-years (1966 to 2024); 5,130 routes have any acceptable year; **1,062 qualify** (at least 10 acceptable years in both windows): 956 US, 106 Canada, all
  standard roadside routes (RouteTypeID 1), on 1,061 distinct 1/24 degree cells. `States.zip` holds 62 state and province CSVs with columns RouteDataID, CountryNum, StateNum, Route, RPID, Year, AOU,
  Count10 to Count50, StopTotal, SpeciesTotal (route-year totals are used). 726 species have detections; 335 have at least 20 route-presences in one window; **150 are eligible** (at least 100 route-presences in both windows).
- Only 1,062 routes meet the strict sampling rule, so the test has about one thousand comparable cells. Statistical power per species is moderate.
- The 10 pilot birds that have a BBS plan are all eligible (the European robin and kookaburra are not in the BBS list, as expected). Observed change of the pilot birds (km, bearing, northward component km):

| species | routes present w1 / w2 | shift km | bearing | north km (SE) | detectable | perm. p |
|---|---|---|---|---|---|---|
| Mourning dove | 1005 / 1035 | 47 | 61 | +22 (5) | yes | 0.00 |
| Blue jay | 840 / 856 | 22 | 257 | -5 (6) | no | 0.02 |
| Red-winged blackbird | 1039 / 1019 | 4 | 48 | +3 (5) | no | 0.83 |
| American goldfinch | 815 / 845 | 23 | 251 | -8 (8) | no | 0.20 |
| Song sparrow | 726 / 756 | 32 | 228 | -21 (7) | yes | 0.05 |
| Northern cardinal | 709 / 778 | 66 | 26 | +59 (8) | yes | 0.00 |
| Barn swallow | 998 / 999 | 53 | 170 | -52 (8) | yes | 0.00 |
| Carolina wren | 410 / 542 | 140 | 27 | +125 (13) | yes | 0.00 |
| American robin | 955 / 962 | 22 | 283 | +5 (5) | no | 0.02 |
| Eastern bluebird | 617 / 768 | 82 | 23 | +76 (11) | yes | 0.00 |

  Carolina wren, northern cardinal and eastern bluebird moved north-north-east, as the literature expects (Carolina wren: verified here from the data; literature expectation **[U]**). The American robin, the
  headline pilot bird, has **no detectable shift** on this route set; its hindcast can only test static transfer, not the change.
- Across all 150 eligible species, 87 have a detectable northward component; only 46 of those 87 (53 percent, binomial p = 0.67) moved north. The real continental signal is therefore **mixed**, not a uniform poleward shift,
  so the proposed "direction of shift" test has a stringent bar: the model must predict species moving south or east as well. This is a finding about the data, not a result for the model. The report also scores bearing agreement
  within 90 degrees (any direction) as an additional, unscored line.
- Proposed validation set: `data/species/w4/bbs_validation_species.csv` lists the 145 eligible native species (introduced species such as House Sparrow, European Starling, House Finch removed because the pipeline fits
  native-range data) and marks 40 as recommended: the 10 pilot birds plus 30 drawn at random (seed 20261010) from native species with at least 150 route-presences in each window. Random draw, so the choice cannot depend on the
  species' observed shift. 24 of the 40 have a detectable shift. W2 would need GBIF occurrences for the 30 extra species and W3 would fit them (the same pipeline, not published as species pages).


## 3b. Full BBS hindcast, first result (Actions run 38076609110; report `docs/pilot/W4-hindcast-report-bbs.md`, numbers `data/species/w4/bbs_hindcast_results.json`)

**Result: the change test FAILS and no species earns Tier 1. This is a conclusive fail, not insufficient data** (40 eligible species against a minimum of 30). **[V 38076609110]**

Set-up: 40 species (the 10 pilot birds and the 30 randomly drawn validation birds, `bbs_validation_species.csv`), fitted on window 1 only (BBS routes with at least 10 acceptable years in 1966-1985, about 1,600 route cells; W1 TerraClimate
hindcast climate 1966-1985; W3 `fit_species` predictors and LightGBM), scored under 1966-1985 and 2005-2024 climate at the 1,062 comparable route cells. Two variants, both without any window-2 information in the fit:
- **blocked** (strict): spatial 400 km blocks, every comparable cell scored by a model that never saw that place;
- **fit_cells**: the pipeline's own fit scored at the comparable cells (most of which it saw in window 1).

| group check | blocked | fit_cells | needed |
|---|---|---|---|
| direction of shift (species with a detectable observed shift) | 12 of 25 agree, p = 0.66 | 11 of 25, p = 0.79 | at least 70 percent, p < 0.05 |
| median modelled / observed shift distance | 0.84 | 0.81 | 0.5 to 2 |
| median shift error vs no-change error | 103 km vs 75 km | 93 km vs 75 km | model below no-change |
| area change: sign agreement, median per-cell correlation | 18 of 40, r = -0.01 | 16 of 40, r = 0.12 | majority, r >= 0.3 |
| beats the no-change model in TSS on window 2 | 12 of 40 | 6 of 40 | at least 60 percent |
| bearing within 90 degrees (reported, not scored) | 11 of 33 | 11 of 33 | - |

What this says, and what it does not:
- **Static skill is good.** Median AUC on window 2 is 0.88 to 0.89; 38 to 40 of 40 species keep AUC within 0.1 of the window-1 value; Boyce is at least 0.5 for 37 to 38. The spatial-block presence-absence skill gate (AUC 0.7, TSS 0.4) is passed by 31 of 40 species
  in the blocked variant. So the model describes where these birds are, in space, and carries that description to a later period.
- **The model does not predict how ranges changed.** Direction of shift is at chance (12 of 25, binomial p = 0.66); the shift-vector error is larger than assuming nothing moved; the per-cell change correlation is about zero. This is the Rapacciuolo et al. (2012) pattern
  (good transferability, poor range-change prediction) that C-validation 4.6 told us to expect. For the headline pilot species: American robin has no detectable observed shift, so only static transfer can be judged (AUC 0.97); Carolina wren, northern cardinal
  and mourning dove are predicted in the right direction; song sparrow and barn swallow in the wrong one.
- **Why this is hard, not necessarily a model fault.** The real BBS signal is mixed (section 3: half of the detectable shifts are not northward), many shifts follow land-use and population dynamics, and one window difference of about 1 C of warming moves a
  threshold model by tens of km while the survey has about 1,000 usable cells. The "no-change" model (same fit, window-1 climate) is hard to beat on TSS because most species hardly moved. These are reasons to read a fail cautiously, not to relax the thresholds after the fact.
- **Consequence under the interpretation rules (C-validation 4.6): "static pass, change fail" - publish current suitability, hide future projections for birds** (or label them "suitable climate, not expected range"), and species fall back to Tier 2 (skill gate passed) or Tier 3
  (barn swallow, others below the gate). Nothing here tests projections to 2050 or 2100.
- **The pipeline's own CV is not a usable gate for BBS-trained fits.** `fit_species` scores presence against background drawn in proportion to route density, so for widespread species presence and background overlap and AUC is about 0.5 to 0.6 (W3 background CV in the
  `fit_cells` columns) even though the same species are discriminated from true absences with AUC 0.93. The blocked variant therefore uses true route absences for the gate. Neither measure is meaningful for species present at more than about 90 percent of routes (prevalence limits TSS).
- Limitations to carry into any reading of this: route start cell stands for a 40 km route; 1,062 comparable routes; hindcast climate is a window mean, not year by year; model predictors are W3's default priority list; introduced species were excluded; no sensitivity run at 0.5 degree blocks yet (`--block 12`).

## 4. Test 2: Forest Inventory and Analysis trees (change test with a lag caveat)

Pipeline (`ctw/species/fia.py`, `w4_fia_run.py`): per conterminous state, first complete cycle against the latest complete cycle (a periodic cycle is complete by construction; an annual cycle must have at
least 85 percent of the median annual plot count); states with fewer than 15 years between the median measurement years are dropped; forested sampled plots (`PLOT_STATUS_CD` 1) and live trees of at
least 5.0 inches DBH only; plots aggregated to 0.5 degree blocks with at least 8 plots in each cycle, **rarefied to the same number of plots in each cycle** so a denser later design cannot fake an expansion;
presence = at least one adult in the rarefied sample; weight one per block. Seedlings versus adults in the latest cycle (SEEDLING table) gives a lower-lag signal: centroid of seedling blocks minus centroid of adult blocks.
Per-block measurement years (t1, t2) are output so the climate windows (30 years ending at each measurement) can be chosen by W3; proposed: bin the window end to the nearest 5 years.

Results: **[waiting for first real run]**

## 5. Test 4: comparison with published tree projections

Verified (probe run 38072865229, ranged reads of the zip central directories and extraction of the five species):
- **RDS-2019-0029 (DISTRIB-II, eastern US, 167 MB zip, 1,041 entries):** contains all five pilot trees as `Data/sp<SPCD>_hybrid_2100.shp` (SPCD 318 sugar maple, 316 red maple, 129 eastern white pine, 746 quaking aspen, 802 white oak) plus
  `_Species_List.csv`; shapefiles on the hybrid 10/20 km lattice. Eastern US only, so aspen is only partly covered. **[V 38072865229]**
- **RDS-2024-0020 (North America, 412 MB zip, 13,102 entries):** one folder per species (`Data/Acer_saccharum/` and the other four all present). Per species: `Actual_sp<SPCD>.tif` (uint8 observed index),
  `CurrentPredicted_Consensus_sp<SPCD>.tif` (float32, relative abundance, 1991-2020), `SSP2-45_Predicted_Consensus_*.tif` and `SSP5-85_Predicted_Consensus_*.tif` (float32, 2070-2100) and `*_HQCL_*.tif`
  (habitat quality and colonisation likelihood). All rasters: Albers Equal Area (centre 40N, 96W, standard parallels 20 and 60), 378 x 409 cells of 20 km, bounds (-5105795, -2951323, 3074205, 4608677) m.
  Value ranges, e.g. sugar maple current 0 to 52, SSP2-45 0 to 30, SSP5-85 0 to 28 (relative abundance falls under warming in the model). **[V 38072865229]**
- Both are US government data, "can be used without additional permissions or fees", citation required (Peters et al. 2019; Prasad et al. 2024). **[V 38072387399]**
- `ctw/species/w4_distrib_run.py` (workflow `pilot-w4-distrib.yml`) summarises RDS-2024-0020 for the five trees: centroid, leading and trailing edge, area change and shift between 1991-2020 and 2070-2100 for both scenarios at
  two presence cutoffs (relative abundance 1 and 5). Output `data/species/w4/distrib2024_summary.csv`. **[V run 38073318194]** Published model, 1991-2020 to 2070-2100, cells with relative abundance of at least 5 (20 km equal-area cells; cutoff 1 gives similar shifts, see the csv):

| species | scenario | cells now / future | centroid shift km | bearing | leading edge km | trailing edge km | area change |
|---|---|---|---|---|---|---|---|
| Acer saccharum | SSP2-45 | 4154 / 4749 | 575 | 360 | 622 | 447 | +14% |
| Acer saccharum | SSP5-85 | 4154 / 6454 | 894 | 358 | 1048 | 585 | +55% |
| Acer rubrum | SSP2-45 | 6106 / 6127 | 458 | 28 | 403 | 104 | +0% |
| Acer rubrum | SSP5-85 | 6106 / 6917 | 753 | 16 | 802 | 85 | +13% |
| Pinus strobus | SSP2-45 | 2389 / 3093 | 493 | 30 | 395 | 612 | +29% |
| Pinus strobus | SSP5-85 | 2389 / 3329 | 812 | 19 | 759 | 857 | +39% |
| Populus tremuloides | SSP2-45 | 9711 / 15448 | 630 | 335 | 559 | 382 | +59% |
| Populus tremuloides | SSP5-85 | 9711 / 17900 | 863 | 342 | 739 | 574 | +84% |
| Quercus alba | SSP2-45 | 3996 / 3657 | 302 | 62 | 241 | 13 | -8% |
| Quercus alba | SSP5-85 | 3996 / 3782 | 521 | 36 | 546 | 36 | -5% |

  These are the benchmark numbers our W3 projections must be near or explain (sugar maple and quaking aspen move 500 to 900 km north-north-west to north by 2100; white oak moves north-east and loses area at the 5 cutoff).
- Comparison plan: for each species compare that summary with our W3 projection for the same period and scenario (centroid shift in km and bearing, area change, edges) and explain or flag differences. Not a hindcast, and the two
  models are not independent in what they were fitted on (both use FIA). **[waiting for W3 projections]**

## 6. Test 3: GBIF before and after, European species (European robin, English oak)

Protocol (code runs; waits for W2's target-group grids, `docs/pilot/W2-occurrences.md`; per-species cell tables for the robin and the oak are on the release: `w2-cells-Erithacus_rubecula.parquet` has 24,849 native cells with records in 1970-1999 and 144,096 in 2000-2020 [V 38077216009], a sixfold rise in effort that is exactly why raw counts must never be compared):
- Split 1970-1999 versus 2000-2020 (C-validation 4.2). Records only from CC0 and CC-BY sources as the W2 filter delivers.
- Analysis cell 0.5 degree. A cell is **well sampled** when the number of target-group records (all birds for the robin, all vascular plants for the oak) is at least 20 in **both** periods
  (C-validation 4.3, N = 20, a proposal). Presence = at least one record of the species in the period; absence = well-sampled cell with no record.
- Report two analyses, well-sampled cells and all cells; the gap measures the bias. Never compare raw counts between periods.
- Because the group has 2 species (minimum 40 per group), this test **cannot reach a conclusion at the group level**. It is reported species by species as illustrative and cannot award Tier 1 on its own.
- Observed change metrics and the model comparison reuse exactly the functions of section 7 with `CellSet`s built from the well-sampled cells.

## 7. Hindcast engine, thresholds and verdict rules (`ctw/species/hindcast.py`)

Input per species: a `CellSet` of comparable cells with observed presence in both windows and the model score in both windows (model fitted on window 1 only; window 2 uses window 2 climate). Outputs per species:

| quantity | definition |
|---|---|
| AUC, TSS, Boyce on window 2 | static transfer; threshold chosen on window 1 only; Boyce from `sdm.boyce` |
| observed and modelled shift | centroid shift (km, bearing, north and east components), leading and trailing edge shift (km), occupancy change |
| shift error | length of the difference of the modelled and observed shift vectors (km); bearing error in degrees |
| nulls | (A) **no-change model**: the same fitted model scored with window 1 climate (isolates what the climate update adds; used for "beats null"); (B) persistence of the observed window-1 map (reported, a very strong benchmark that the SDM cannot beat cell by cell because it does not see window-1 occupancy); (C) random shift of the observed magnitude (median error $\sqrt{2}$ times the shift) |
| direction | sign of the northward component agrees, only for species whose observed shift is detectable (larger than 2 bootstrap SE) |
| per-cell change | correlation of observed occupancy change and modelled score change |

**Thresholds** (all proposals from C-validation 4.6, kept in one dataclass, `Thresholds`; none is an accepted standard):

| check | pass mark | justification |
|---|---|---|
| spatial-block CV TSS, AUC (skill gate) | at least 0.4 and 0.7 | rule-of-thumb bands in the SDM literature [U: from memory, per Spike C]; both reported because AUC depends on prevalence (Lobo et al. 2008) |
| AUC on window 2 | not more than 0.1 below the window-1 CV AUC | Rapacciuolo et al. 2012 found good temporal transferability |
| Boyce on window 2 | at least 0.5 | arbitrary positive mark |
| direction of shift | at least 70 percent of species with a detectable observed shift agree, one-sided binomial p below 0.05 | weakest claim defensible on the site; 15 of 20 gives p = 0.021 (checked in `test_direction_binomial_threshold`) |
| median shift ratio (model / observed) | between 0.5 and 2 | species lag climate (Devictor et al., Zhu et al.), so exactly 1 is not required |
| shift error | median model error below the median no-change error (zero shift predicted) | the model must beat "nothing moved" |
| area change | sign agreement in a majority and median per-cell correlation at least 0.3 | weak because per-cell change is noisy |
| beats null | TSS on window 2 above the no-change model in at least 60 percent of species | the model must add information beyond persistence |
| minimum species (eligible) | BBS 30, FIA 20, GBIF 40 per group; eligibility: at least 100 route-presences (BBS), 500 plots (FIA) or 20 records (GBIF) per window | binomial arithmetic of C-validation 4.7 |

Verdicts: a group is **pass**, **fail** or **insufficient data** (fewer eligible species than the minimum; never a pass). A species earns **Tier 1** only if its group test passed **and** it passes its own skill gate, window-2
transfer, Boyce, beats the no-change null and is not detectably in the wrong direction; otherwise it falls to Tier 2 (skill gate passed or not supplied) or Tier 3 (below skill gate). Interpretation text follows C-validation 4.6
(static pass and change fail: publish current suitability only; both fail: caveat or do not publish).

Interpretation choices made here that the reviewer should check: (1) "beats no-change null" is measured against the model with window-1 climate, not against the observed persistence map; both are reported.
(2) The group change checks use medians over species rather than requiring each species to pass. (3) The bootstrap resamples cells (or blocks), not individual routes or plots within them.

Report generator: `hindcast.report(...)` and `observed_table(...)` write markdown tables per test (group checks, species metrics, Tier verdicts).

## 8. Waiting on others (nothing blocks the data side)

- W1 (`docs/pilot/W1-climate.md`): hindcast tiles `pred_hind_1966-1985_<tile>.npz` and `pred_hind_2005-2024_<tile>.npz`. North American tiles r0c0, r0c1, r1c0, r1c1 were on the release by 18:30 UTC and were used for the BBS hindcast. **Done for NA; not needed for other tests.**
- W2 (`docs/pilot/W2-occurrences.md`): thinned occurrences, native-range masks, time-split product for the two European species. **Waiting.**
- W3 pipeline landed (`pipeline.fit_species`, `FitConfig.window`, `inputs.W1Source`). `hindcast_run.py` fits with it on window-1 climate and BBS window-1 route presences (target-group density = route density), scores both windows at the route cells and runs `hindcast.run_test`. **[V: unit test on the synthetic climate, `tests/test_species_hindcast_run.py`]**
