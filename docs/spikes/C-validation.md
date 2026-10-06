# Spike C: validation data and the hindcast protocol

Owner: Spike C agent. Date of evidence: 2026-10-06. Branch: claude/eloquent-ritchie-r7jjby.

## 0. Method and evidence status

The sandbox cannot fetch most websites (WebFetch returned `EGRESS_BLOCKED` for sciencebase.gov). Evidence therefore comes from three routes:

- **[A] Actions probe**: a GitHub Actions job (`.github/workflows/spike-c-probe.yml`, scripts `ctw/species/validate_probe.py`, `validate_probe2.py`, run 37524229446 and later) requested each URL from a GitHub runner and logged status, headers and page text. This is the strongest evidence.
- **[S] Search snippet**: a web-search result summary. The source page exists but I did not read the full text myself.
- **[K] Background knowledge, not verified in this session.** Everything marked [K] or "UNVERIFIED" must be checked before it is relied upon or published.

Reference citations were checked for existence against the Crossref API (route [A]); the Crossref record was matched to the title, authors and year given. Whether a paper says what I summarise is my reading and is not verified here.

Terms in this document are plain-language summaries, not legal advice. Anything that touches redistribution on the public site needs a human to read the full terms.

## 1. Validation sources

Legend for usability: High = can run a hindcast now with open data; Medium = usable with extra work or a data request; Low = not usable on the public pipeline.

| # | Source | Access route and format | Size | Licence / terms | Coverage | Hindcast usability | Status |
|---|---|---|---|---|---|---|---|
| a | **North American Breeding Bird Survey (USGS)**, 2025 release dataset 1966-2024 | ScienceBase item 691cfb53d4be021d1d89b482, DOI 10.5066/P14SNUV4. Plain CSVs: `Routes.csv` (0.39 MB), `SpeciesList.csv`, `Weather.csv` (13.8 MB), `VehicleData.csv` (60.5 MB), per-state count files in zips, `MigrantNonBreeder.zip`, completeness report. Direct file URLs listed in the item JSON (`.../catalog/item/<id>?format=json`). | About 100-200 MB all files [partly A: 4 files seen; full listing truncated in log] | **CC0 1.0** (item `rights` field) [A]. BBS site also states a "Terms of Use": users are obligated to formally recognise use of the data and acknowledge the participants [A, pwrc.usgs.gov/bbs/RawData/]. So no legal bar to redistribution of derived numbers; attribution requested. | Routes across US and Canada, 1966-2024; route start coordinates in `Routes.csv`; counts of each species on each 3-mile-stop segment per route per year | **High** for birds in the US/Canada. Gives presence and abundance by route-year with standardised effort (fixed route, 50 stops, one day). Best single dataset for a recorder-effort-free hindcast. Caveats: road-side sampling, observer effects, and start of the survey in 1966 gives only 25 years before 1991. | Verified [A] |
| a2 | BBS analysis results 1966-2025 (2026 release) and 2024 release | ScienceBase 6a39284a1ba49b4f9d9e0e99 (1966-2025) and 692f0fa7d4be026ff273a98e (1966-2024). CSVs: core indices 1966-2025 (42.7 MB), core trends (1.5 MB), expanded indices 1993-2025 (27 MB), decadal trends. | 1.5-43 MB per file | **CC0 1.0** [A] | Species trends and annual indices by region (country, state/province, BCR, strata) | Medium: gives regional abundance indices, so can test direction and sign of regional change, but not point locations. | Verified [A] |
| a3 | BBS mapping products 1966-2022 | usgs.gov/data page, DOI 10.5066/P1DPJPSI | not checked | not checked | Gridded distribution/abundance surfaces | Unknown | URL reachable [A]; contents UNVERIFIED |
| b | **European Breeding Bird Atlas 1 (EBBA1, 1980s) and 2 (EBBA2, mainly 2013-17)** | ebba2.info web viewer, "Data request" page. FAQ text confirms 50 km occurrence squares for both periods, breeding-evidence and abundance maps, modelled 10 km probability maps [A, ebba2.info/faq]. Maps downloadable as PNG; underlying tabular data by request. | 50 km occurrence data is small (a few MB) [K] | Per search snippet: free access to 50 km occurrence data under a Creative Commons licence; other data types are "(c) EBCC" and need EBCC approval [S]. **The exact CC variant (is it CC-BY, CC-BY-NC?) was not verified.** The FAQ page text fetched did not state a licence. | Europe, 596 breeding species [A, homepage]; EBBA1 mainly 1980s, EBBA2 mainly 2013-17 [A, FAQ] | **High** for the cleanest two-period test in this list: two atlases, about 30 years apart, same 50 km squares, change maps provided. Caveat: atlas effort differs between periods (EBBA2 has more coverage and better effort in some countries), so absences are not equal-quality; EBCC itself warns that modelled maps are for European scale. 50 km cells are coarse against a 0.5 degree climate grid (roughly comparable). | Existence and period verified [A]; licence UNVERIFIED |
| c1 | **USFS Forest Inventory and Analysis (FIA) DataMart** | apps.fs.usda.gov/fia/datamart; state CSVs such as `.../CSV/DE_TREE.csv` (13.6 MB) and `AK_TREE.csv` (126.7 MB) returned HTTP 206 with real sizes [A]. Tables: TREE, SEEDLING, PLOT, COND, etc. | Whole US tree tables several GB [K] | US federal data; the Research Data Archive pages state USFS data "can be used without additional permissions or fees" [A, RDS pages]; the DataMart page itself carried no licence text in my probe, so assume the same public-domain policy but **confirm**. Exact plot coordinates are **fuzzed and swapped by law**, so public coordinates are only approximate (about 1 mile, up to 5 miles for 20% of private plots) [K, UNVERIFIED]. | Eastern US plots from the 1930s-60s, annual design since 1999-2000s; repeat measurements on the same plots | **Medium-High** for trees. Repeat inventories allow testing change in presence or importance of a species by latitude/region; fuzzed locations are tolerable at 0.5 degrees. Literature shows tree range shifts are weak and noisy (see section 3); do not expect a strong signal for adult trees; seedlings versus adults is the more sensitive test (Woodall et al., Zhu et al.). | Download reachable and size verified [A]; coordinate fuzzing and tables UNVERIFIED |
| c2 | **DISTRIB-II eastern US trees (RDS-2019-0029)**, **North America tree models (RDS-2024-0020, 326 species)**, DISTRIB-II forest types (RDS-2024-0044) | Research Data Archive pages (DOIs 10.2737/RDS-2019-0029, 10.2737/RDS-2024-0020, 10.2737/RDS-2024-0044) [A]. 0029 and 0044: shapefiles on a 10/20 km hybrid lattice; 0020: rasters of relative abundance plus colonisation likelihood [A, abstracts]. | not checked | US government, "can be used without additional permissions or fees"; citation required (Peters et al. 2019 Ecology and Evolution plus the data DOI) [A] | Baseline 1981-2010 (0029, 0044) or 1991-2020 (0020); futures 2070-2100 under RCP4.5/8.5 or SSP2-4.5/5-8.5 [A] | This is a **published projection to compare against** (section 2), not a hindcast dataset. | Verified [A] |
| d | **Christmas Bird Count (Audubon)** | Audubon portal (audubon.org/community-science/christmas-bird-count/explore-christmas-bird-count-data): small self-service downloads for personal use; larger subsets by request for researchers, academics, government agencies [A + S]. Also via Birds Canada NatureCounts for Canada [A, terms page]. | n/a | **Not open data.** Terms (read from the page text [A]): analytical use for academic research, non-profit conservation, education, government; data "provided to you on a one-time basis"; "may not be shared with any third party, unless required by publication outlets with open data policies"; Audubon marks cannot be used without licence; citation formats prescribed. | US/Canada/Latin America, winter, from about 1900 (portal states "more than 120 years") [A]; trend products 1966-2023 [A] | **Low for the public pipeline**: cannot be redistributed, and our species pages would show derived outputs. **Medium for a private internal check** of winter ranges (a legitimate research use if requested), but the output would then depend on a non-shareable dataset, which conflicts with the "publish everything" principle in the roadmap. GBIF carries only other counts (a search returned a Taiwan count, not Audubon) [A]. | Terms verified [A] |
| e | **eBird Status and Trends** | Cornell Lab; access through the `ebirdst` R package or website after accepting the terms; products are GeoTIFF rasters of range, weekly relative abundance, trends [S for products; A for terms]. Registration and accepted terms needed. | large (multi-GB for all species) [K] | Terms of Use (30 Oct 2023) [A, ebird.org/about/products-access-terms-of-use]: free for non-commercial use; **commercial use needs prior written permission** (including non-profit uses with "any revenue generation"); must cite with DOI; **no redistribution of the Data Products via websites, APIs, software or visualisation tools without written permission**; modified products may be redistributed only if the result of a peer-reviewed publication and based on up to 25 products; non-peer-reviewed reports up to 50 species, more by permission; educational use up to 100 species. Raw eBird data have separate terms. | Global, annual 2007-2023 weekly products [S, UNVERIFIED years] | **Low for the public site** as it would involve redistribution of derived products for about 90 bird species and possibly revenue later. **Medium for a private sanity check** that stays out of the repo. Also the status products model 2007+ data only, so no long hindcast. | Terms verified [A]; years and size UNVERIFIED |
| f | **GBIF historical records for temporal splitting** | GBIF API / Occurrence Download (DOI per download). API count requests worked from Actions [A]. | n/a | Per-record licence CC0, CC-BY or CC-BY-NC; keep CC0 and CC-BY (roadmap rule). | Counts for two example taxon keys are given below the table [A] | **Medium, for a recorder-effort-biased temporal split.** Pre-1990 data are few, spatially sparse and mostly specimens, post-1990 data are dominated by iNaturalist/eBird. Not suitable as the primary test; useful for plants where herbarium data exist, and only with target-group background and effort correction. | Counts verified [A] |
| g1 | **UK Butterfly Monitoring Scheme (UKBMS)** | GBIF dataset "UK Butterfly Monitoring Scheme (UKBMS)", DOI 10.15468/gmqvmk [A, GBIF API]. Licence on the GBIF record not captured. | not checked | UNVERIFIED (read the GBIF record) | UK, 1976-present [K] | Medium for UK only (a small region; the 0.5 degree grid has about 15-25 land cells across Britain's latitudinal gradient [K]). Good for testing northward spread of common butterflies, not for monarch. | Dataset exists [A]; licence UNVERIFIED |
| g2 | **European Butterfly Monitoring Scheme (eBMS)** | butterfly-monitoring.net/ebms-data access: "refer to our data access policy and complete and sign this license form", then email [A]. | n/a | Signed licence form per request; acknowledgement of partner schemes required [A, S]. **Not open.** | 21 schemes officially in eBMS, 33 countries [S] | Medium for a private research test; Low for open publication. | Access route verified [A]; policy text UNVERIFIED |
| g3 | Devictor et al. 2012 (butterfly and bird climatic debt) | Journal article, DOI 10.1038/nclimate1347 (exists [A]). Supplement data: not checked | n/a | n/a | Europe 1990-2008 [K] | Provides the published **expected result**: both groups shifted north less than isotherms (butterflies ~114 km vs 249 km isotherm, birds ~37 km) [K, UNVERIFIED numbers]. Use as a qualitative benchmark only. | Existence verified [A]; numbers UNVERIFIED |
| h | Other open, machine-readable long-term datasets | (1) GBIF-hosted national monitoring datasets, e.g. Swedish National Forest Inventory vegetation data (appeared in a GBIF search [A]). (2) PECBMS (Pan-European Common Bird Monitoring Scheme): national indices, public summary indices [K, UNVERIFIED]. (3) eBird raw data, EBD, restricted terms (see e). (4) Zenodo-archived range-shift datasets, e.g. search returned "Data from: Contemporary climate-driven range shifts: putting evolution back on the table" [A], not assessed. (5) Species-specific historical resurveys (Grinnell resurvey, Tingley et al. 2009, data in MaNIS/VertNet [K UNVERIFIED]). (6) Fei et al. 2017 FIA-based tree range-shift analysis [paper exists A; supplement not checked]. (7) Lenoir et al. 2008 and related plant elevation datasets [paper exists A; data not checked]. | varies | varies | varies | Candidates only. None assessed in depth. | UNVERIFIED |

GBIF API test counts [A, 2026-10-06, no cleaning]. I queried two taxon keys that I had not yet matched to species names, so they are **not** pilot species and are shown only as an illustration of the pattern: key 3189815 had 24,331 records for 1970-1989 and 144,372 for 1990-2020 (total 356,989; 83% human observation, 14% living specimens, 1.5% preserved specimens). Key 2882316 had 53,869 records for 1900-1969, 959,805 for 1990-2020, and 19,686 preserved specimens in total.

The **pattern** (few pre-1990 records, dominated by recent human observation, about 6 times more records in 1990-2020 than in 1970-1989 for key 3189815) is verified for those two keys; it cannot be assumed for the pilot species. A proper count per pilot species is a small follow-up (keys matched [A]: sugar maple 3189859, monarch 5133088, American robin 9510564, European robin 2492462, English oak 2878688, blacklegged tick 2182727, wine grape 5372392).

## 2. Published projections to compare against (pilot species)

| Species | Source | Access / format | Licence | Status |
|---|---|---|---|---|
| Sugar maple (*Acer saccharum*) | **USFS DISTRIB-II** RDS-2019-0029: 125 eastern US tree species (the abstract states 125, and 135 in the paper title; the species list was not checked, so sugar maple's inclusion is UNVERIFIED but highly likely [K]); baseline 1981-2010, future 2070-2099, eight scenarios | Shapefiles on a 10/20 km hybrid lattice (importance values) [A] | US government, free without permission, citation required [A] | Dataset verified [A]; species presence UNVERIFIED |
| Sugar maple | **RDS-2024-0020**: 326 North American species, baseline 1991-2020, futures SSP2-4.5 and SSP5-8.5 (2070-2100), plus colonisation likelihood | Rasters [A] | same [A] | Verified [A]; species presence UNVERIFIED |
| Sugar maple | USFS Climate Change Tree Atlas web viewer (research.fs.usda.gov/nrs/products/dataandtools/forest-ecosystem-atlas): browse by species, download custom summaries [S+A] | Web viewer | US government | Page verified [A] |
| English oak (*Quercus robur*) | EU-Trees4F (Mauri et al. 2022 Scientific Data) [K]; Kew POWO/WCVP native ranges (POWO website returned 403 from Actions, so not verified) | UNVERIFIED | UNVERIFIED | UNVERIFIED. No downloadable English oak projection verified. |
| American robin (*Turdus migratorius*) | **Audubon climate-based bird distribution models** (604 species, 1 km suitability rasters, seasons winter and summer, current and RCP4.5/8.5 for 2025s, 2055s, 2085s; also +1.5, +2.0, +3.0 C scenarios) hosted on AdaptWest Databasin [A, page text]. American robin inclusion in the 604 UNVERIFIED but likely [K]. | GeoTIFF, Albers Equal Area, 1 km, 7-zip archives [A] | **Licence not found on the page.** Citation (Bateman et al.) is requested [A]. Treat as "ask before redistribution". | Dataset verified [A]; licence and species list UNVERIFIED |
| American robin | eBird Status and Trends | see 1e. Terms restrict redistribution | non-commercial only | Verified terms [A] |
| European robin (*Erithacus rubecula*) | EBBA2 modelled maps (10 km probability of breeding) and change maps | PNG download; data on request | see 1b | Exists [A]; data licence UNVERIFIED |
| European robin | Huntley et al. 2007 *A Climatic Atlas of European Breeding Birds* (Lynx/RSPB/BirdLife) [K] | Book; maps; **no verified downloadable data** | UNVERIFIED | UNVERIFIED |
| Monarch (*Danaus plexippus*) | Several published niche models [K] (e.g. Batalden et al. 2007 on climate and migration). No downloadable projection verified. | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| Blacklegged tick (*Ixodes scapularis*) | Published models, e.g. Brownstein et al. 2005 and Hahn et al. 2016 (US range expansion by county) [K]; county-level occurrence maps from CDC (CDC data are US federal) [K UNVERIFIED] | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| Wine grape (*Vitis vinifera*) | Hannah et al. 2013 PNAS "Climate change, wine, and conservation" [K, DOI not yet verified]; Moriondo et al. 2013 [K]. No downloadable data verified. | UNVERIFIED | UNVERIFIED | UNVERIFIED |

Conclusion: only **trees (USFS)** and **North American birds (Audubon, subject to licence)** have verified, downloadable, multi-scenario projections. For the other pilot species, comparison is with the published papers' maps and numbers, read by hand, not with machine-readable files.

## 3. Authoritative references

Every entry below was confirmed to exist via the Crossref API on 2026-10-06 (author, title, journal and year matched). The annotations are my summary from memory and should be checked by the reviewer.

**Sampling bias and presence-only data**
1. Phillips SJ, Dudik M, Elith J, Graham CH, Lehmann A, Leathwick J, Ferrier S (2009). Sample selection bias and presence-only distribution models: implications for background and pseudo-absence data. *Ecological Applications*. doi:10.1890/07-2153.1. Origin of the target-group background.
2. Fithian W, Elith J, Hastie T, Keith DA (2015, online 2014). Bias correction in species distribution models: pooling survey and collection data for multiple species. *Methods in Ecology and Evolution*. doi:10.1111/2041-210x.12242. Uses survey-quality data to correct opportunistic data.
3. Beck J, Boller M, Erhardt A, Schwanghart W (2014). Spatial bias in the GBIF database and its effect on modeling species' geographic distributions. *Ecological Informatics*. doi:10.1016/j.ecoinf.2013.11.002.
4. Hassall C, Thompson DJ (2010). Accounting for recorder effort in the detection of range shifts from historical data. *Methods in Ecology and Evolution*. doi:10.1111/j.2041-210x.2010.00039.x. Directly relevant to the effort problem in section 4.
5. Tingley MW, Beissinger SR (2009). Detecting range shifts from historical species occurrences: new perspectives on old data. *Trends in Ecology & Evolution*. doi:10.1016/j.tree.2009.05.009.

**Evaluation metrics and cross-validation**
6. Roberts DR et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*. doi:10.1111/ecog.02881. Why random CV is over-optimistic and blocked CV is needed.
7. Valavi R, Elith J, Lahoz-Monfort JJ, Guillera-Arroita G (2019). blockCV: an R package for generating spatially or environmentally separated folds for k-fold cross-validation of species distribution models. *Methods in Ecology and Evolution*. doi:10.1111/2041-210X.13107.
8. Hijmans RJ (2012). Cross-validation of species distribution models: removing spatial sorting bias and calibration with a null model. *Ecology*. doi:10.1890/11-0826.1.
9. Allouche O, Tsoar A, Kadmon R (2006). Assessing the accuracy of species distribution models: prevalence, kappa and the true skill statistic (TSS). *Journal of Applied Ecology*. doi:10.1111/j.1365-2664.2006.01214.x.
10. Lobo JM, Jimenez-Valverde A, Real R (2008). AUC: a misleading measure of the performance of predictive distribution models. *Global Ecology and Biogeography*. doi:10.1111/j.1466-8238.2007.00358.x. Also Jimenez-Valverde A (2012), doi:10.1111/j.1466-8238.2011.00683.x.
11. Hirzel AH, Le Lay G, Helfer V, Randin C, Guisan A (2006). Evaluating the ability of habitat suitability models to predict species presences. *Ecological Modelling*. doi:10.1016/j.ecolmodel.2006.05.017. Defines the Boyce index as used for presence-only data.
12. Bahn V, McGill BJ (2013). Testing the predictive performance of distribution models. *Oikos*. doi:10.1111/j.1600-0706.2012.00299.x. (Crossref gives the year as 2012 online.)

**Ensembles and model choice**
13. Thuiller W, Lafourcade B, Engler R, Araujo MB (2009). BIOMOD: a platform for ensemble forecasting of species distributions. *Ecography*. doi:10.1111/j.1600-0587.2008.05742.x.
14. Elith J et al. (2006). Novel methods improve prediction of species' distributions from occurrence data. *Ecography*. doi:10.1111/j.2006.0906-7590.04596.x.
15. Elith J, Leathwick JR (2009). Species distribution models: ecological explanation and prediction across space and time. *Annual Review of Ecology, Evolution, and Systematics*. doi:10.1146/annurev.ecolsys.110308.120159.
16. Brun P, Thuiller W, Chauvier Y et al. (2020, Crossref online 2019). Model complexity affects species distribution projections under climate change. *Journal of Biogeography*. doi:10.1111/jbi.13734.
17. Dormann CF et al. (2012). Collinearity: a review of methods to deal with it and a simulation study evaluating their performance. *Ecography*. doi:10.1111/j.1600-0587.2012.07348.x.

**Extrapolation and novelty (MESS and successors)**
18. Elith J, Kearney M, Phillips S (2010). The art of modelling range-shifting species. *Methods in Ecology and Evolution*. doi:10.1111/j.2041-210X.2010.00036.x. Introduces MESS (multivariate environmental similarity surface) in its commonly cited form.
19. Mesgaran MB, Cousens RD, Webber BL (2014). Here be dragons: a tool for quantifying novelty due to covariate range and correlation change when projecting species distribution models. *Diversity and Distributions*. doi:10.1111/ddi.12209. Introduces NT1 and NT2 and the ExDet tool; also flags correlation change that MESS misses.

**Transferability in time and hindcast evaluation**
20. Araujo MB, Pearson RG, Thuiller W, Erhard M (2005). Validation of species-climate impact models under climate change. *Global Change Biology*. doi:10.1111/j.1365-2486.2005.01000.x. The classic hindcast-style validation paper (British birds/ plants).
21. Rapacciuolo G et al. (2012). Climatic associations of British species distributions show good transferability in time but low predictive accuracy for range change. *PLoS ONE*. doi:10.1371/journal.pone.0040212. Highly relevant: the exact claim our hindcast will test.
22. Eskildsen A, le Roux PC, Heikkinen RK et al. (2013). Testing species distribution models across space and time: high latitude butterflies and recent warming. *Global Ecology and Biogeography*. doi:10.1111/geb.12078.
23. Zurell D, Thuiller W, Pagel J et al. (2016). Benchmarking novel approaches for modelling species range dynamics. *Global Change Biology*. doi:10.1111/gcb.13251.
24. Regos A et al. (2018). Hindcasting the impacts of land-use changes on bird communities with species distribution models of Bird Atlas data. *Ecological Applications*. doi:10.1002/eap.1784.

**Critiques of climate-envelope models**
25. Pearson RG, Dawson TP (2003). Predicting the impacts of climate change on the distribution of species: are bioclimate envelope models useful? *Global Ecology and Biogeography*. doi:10.1046/j.1466-822X.2003.00042.x.
26. Araujo MB, Peterson AT (2012). Uses and misuses of bioclimatic envelope modeling. *Ecology*. doi:10.1890/11-1930.1.
27. Guisan A, Thuiller W (2005). Predicting species distribution: offering more than simple habitat models. *Ecology Letters*. doi:10.1111/j.1461-0248.2005.00792.x.
28. Guillera-Arroita G et al. (2015). Is my species distribution model fit for purpose? Matching data and models to applications. *Global Ecology and Biogeography*. doi:10.1111/geb.12268.
29. Zurell D et al. (2020). A standard protocol for reporting species distribution models (ODMAP). *Ecography*. doi:10.1111/ecog.04960. We should publish an ODMAP record per species batch.
30. Sofaer HR et al. (2019). Development and delivery of species distribution models to inform decision-making. *BioScience*. doi:10.1093/biosci/biz045.

**Observed range shifts (what the hindcast should reproduce)**
31. Parmesan C, Yohe G (2003). A globally coherent fingerprint of climate change impacts across natural systems. *Nature*. doi:10.1038/nature01286.
32. Hickling R, Roy DB, Hill JK, Fox R, Thomas CD (2006). The distributions of a wide range of taxonomic groups are expanding polewards. *Global Change Biology*. doi:10.1111/j.1365-2486.2006.01116.x.
33. Chen I-C, Hill JK, Ohlemuller R, Roy DB, Thomas CD (2011). Rapid range shifts of species associated with high levels of climate warming. *Science*. doi:10.1126/science.1206432.
34. Devictor V et al. (2012). Differences in the climatic debts of birds and butterflies at a continental scale. *Nature Climate Change*. doi:10.1038/nclimate1347.
35. Lenoir J et al. (2020). Species better track climate warming in the oceans than on land. *Nature Ecology & Evolution*. doi:10.1038/s41559-020-1198-2. And Lenoir J, Gegout JC, Marquet PA, de Ruffray P, Brisse H (2008), *Science*, doi:10.1126/science.1156831 (plant elevation shifts).
36. Tingley MW, Monahan WB, Beissinger SR, Moritz C (2009). Birds track their Grinnellian niche through a century of climate change. *PNAS*. doi:10.1073/pnas.0901562106.
37. La Sorte FA, Thompson FR (2007). Poleward shifts in winter ranges of North American birds. *Ecology*. doi:10.1890/06-1072.1 (Christmas Bird Count based).
38. Zhu K, Woodall CW, Clark JS (2012). Failure to migrate: lack of tree range expansion in response to climate change. *Global Change Biology*. doi:10.1111/j.1365-2486.2011.02571.x. FIA based; the key warning that adult trees may not track climate.
39. Fei S et al. (2017). Divergence of species responses to climate change. *Science Advances*. doi:10.1126/sciadv.1603055. FIA based; trees shift in both directions.

**Tree projections**
40. Peters MP, Iverson LR, Prasad AM, Matthews SN (2019). Utilizing the density of inventory samples to define a hybrid lattice for species distribution models: DISTRIB-II for 135 eastern U.S. trees. *Ecology and Evolution*. doi:10.1002/ece3.5445 (DOI as printed on the RDS page [A]; Crossref lookup not run).

Not verified and so not listed: papers on MaxEnt specifics beyond Phillips et al. 2006/2008 (both exist per Crossref: doi:10.1016/j.ecolmodel.2005.03.026, doi:10.1111/j.0906-7590.2008.5203.x), Kramer-Schadt et al. 2013 (a Crossref lookup by title did not return it), Dormann et al. 2012 (J Biogeogr), Bahn and McGill.

## 4. The hindcast protocol

### 4.1 Principle

Fit the species model using only information from an **early period**, project to a **later period** using the later period's observed climate, and test whether the model reproduces the **observed change** in the species' distribution. This tests the thing we sell: that climate-driven suitability moves where species actually moved. It does not test future scenarios, dispersal, or land use.

Two kinds of tests, which must not be mixed:
- **Static transfer**: discrimination of a later presence/absence map using a model fitted on the earlier period (AUC, TSS, Boyce).
- **Change test**: do the **differences** between predictions in the two periods match the **differences** between observed distributions? This is the hard test. Rapacciuolo et al. (ref 21) found transferability was good but range-change prediction poor, so passing only the static test is not evidence of credibility.

### 4.2 Periods and climate

Using the data the repo already has (TerraClimate and CRU/ERA5 from 1958):

| Test | Fit (T1) | Climate for T1 | Test (T2) | Climate for T2 |
|---|---|---|---|---|
| BBS birds, United States and Canada | records 1966-1985 (20 years), species presence from routes pooled over the window | mean of the same 20 years, TerraClimate | records 2005-2024 (20 years) | mean 2005-2024, TerraClimate |
| EBBA1 to EBBA2 | EBBA1 atlas squares (mainly 1980s), climate 1975-1990 (covers atlas-field years plus preceding years) | 1975-1990, TerraClimate | EBBA2 (2013-2017), climate 2008-2017 | 2008-2017 |
| FIA trees, US | first complete FIA cycle per state (dates to be read from the PLOT table, not verified) | the 30 years ending at that cycle | latest cycle per state | the 30 years ending at that cycle |
| GBIF plants, birds, insects (temporal split) | records 1970-1999 | 1970-1999 | records 2000-2020 | 2000-2020 |

Note on FIA windows: the exact survey years differ by state; they are determined per state from the PLOT table (MEASYEAR) and a 30-year climate window ending at each measurement is used. I did not verify the cycle dates.

Rules for the climate:
- Use **one consistent source for both periods**, for example TerraClimate (1958-present) for all tests so that the T1 to T2 change is internally consistent. Do not mix CRU for T1 with ERA5 for T2; offsets between products can be as large as the signal. [K: dataset availability from 1958 as stated by the project lead; not re-verified here]
- Use windows of **at least 20 years**, because species respond to means and extremes, not individual years; windows are chosen **before** looking at results and are written into the config.
- Climate baseline for the production model (1991-2020, per site) is not the same as T1; the hindcast must fit the same algorithms and predictors as production but trained on T1 data only. Otherwise the test shows nothing about the production model.
- Predictors: only those with a time-varying climate component (temperature, precipitation, water deficit). Elevation, soils held fixed.

### 4.3 Recorder-effort bias

- **Prefer standardised surveys** (BBS, atlases, FIA) over opportunistic records: that is why they rank first.
- For atlas data (EBBA): restrict to squares with adequate coverage in both periods (EBBA2 provides coverage/effort information [K UNVERIFIED]); treat absence only where the number of species recorded in the square (the checklist completeness) exceeds a threshold, for example more than 50% of the species recorded in either atlas for that square [proposal].
- For BBS: use routes sampled in both windows (at least 10 years in each window), counts standardised per route-year, presence defined as at least one detection in at least 3 route-years in the window [proposal].
- For GBIF: one record per 0.5 degree cell per period, background points drawn from records of the same taxonomic group in the same period (target-group, Phillips et al. 2009). Compare only cells with at least N records of the target group in **both** periods (proposal N = 20), so that "absence" in a cell is credible. Hassall and Thompson (ref 4) show why this is needed.
- Always report results for the "well-sampled cells" subset **and** for all cells; the gap is a measure of the bias.
- **Never** compare raw record counts between periods.

### 4.4 Spatial CV within T1

Fit on T1 with spatial block cross-validation (blockCV, ref 7, blocks at least as wide as the spatial autocorrelation range of the predictors) and report cross-validated skill. This is the "skill gate" in roadmap 3.4. The hindcast is a separate, out-of-time test on top.

### 4.5 Metrics

For each species and test:

| Metric | Definition | Use |
|---|---|---|
| AUC and TSS | model fitted on T1, evaluated on T2 observed presence/absence in comparable cells | static transfer. TSS with a threshold chosen on T1 only (maximising TSS in T1 CV). AUC alone is misleading with prevalence change (ref 10). |
| Boyce index | continuous Boyce (Hirzel et al.) computed on T2 presences against the T2 prediction | static transfer for presence-only data (GBIF). Range -1 to 1. |
| Centroid shift error | distance between the modelled and observed shift of the **range centroid** (and of the leading and trailing 5% and 95% quantiles of latitude, which are the more sensitive indicators). Great-circle km. Observed shift from T2 minus T1 observed ranges in the standardised-survey cells; modelled shift = change of the suitability-weighted centroid using thresholded predictions in the **same cells**. | change test |
| Direction of shift | whether the sign of the observed and modelled shift along the main axis (latitude for most species; elevation where relevant) agree. Report the fraction correct across species with a binomial test against 50%, and bearing difference in degrees. | change test, the most easily communicated result |
| Area change error | (modelled area change - observed area change) relative to the observed range area, in the comparable cells; also the Pearson correlation between predicted and observed per-cell change in occupancy. | change test |
| Null comparisons | (i) "no change" model (T2 distribution = T1 distribution); (ii) optionally a simple "shift along the latitudinal temperature gradient" model, as the existing repo hindcast uses as its naive baseline; (iii) a model fitted on T2 data (an upper bound). The model must beat (i). | all tests |

### 4.6 Pass/fail thresholds (proposals, not standards)

These are judgement calls. They are grounded in the sources cited above, but no source I verified defines them as accepted cutoffs. The reviewer is asked to adjust them.

| Check | Threshold for pass | Reasoning |
|---|---|---|
| Spatial-block CV in T1: TSS | at least 0.4 | TSS 0.2-0.5 is a commonly used "poor to fair" band in the SDM literature [K UNVERIFIED]; below 0.4 the model is not distinguishing climate niche from noise. A gate per species. |
| Spatial-block CV in T1: AUC | at least 0.7 | common rule of thumb [K]; reported alongside TSS because of prevalence effects (Lobo et al.). |
| Static transfer T1 to T2 (AUC) | within 0.1 of the within-T1 spatial-CV AUC | transfer in time should not lose much skill, per Rapacciuolo (good transferability found). |
| Boyce index on T2 | at least 0.5 | positive and clearly above zero; arbitrary threshold [proposal]. |
| Direction of shift | at least 70% of species with an observed shift larger than the measurement noise (shift bigger than 2 SE from a bootstrap over routes or squares) agree in sign; binomial p below 0.05 against 50% | direction is the weakest claim we can defensibly make on the site. |
| Centroid shift magnitude | median ratio of modelled to observed shift between 0.5 and 2 (not necessarily 1: species lag behind climate, see Devictor et al., Zhu et al.) and absolute error smaller than the shift of the no-change null | lag means models should **over**-predict shift for trees; we report the ratio, we do not require 1. |
| Area change | sign agreement and correlation of per-cell change above 0.3 | weak requirement, because per-cell change is noisy |
| Beats null | model better than "no change" in TSS on T2 for at least 60% of species | the model must add information beyond persistence. |

Interpretation rules (so a "fail" is useful, not just a red light):
- **Static pass, change fail**: publish only the current suitability, hide future projections for that group (this is the Rapacciuolo outcome).
- **Both fail** for a group (e.g. trees with lag): publish with a bold caveat "suitability not realised range", or do not publish.
- Results per group (birds, trees, insects) decide group-level publication; per-species skill gate decides species-level publication.

### 4.7 Minimum number of species for each test

Needed so that a group-level pass is not a few lucky species. Derived from a binomial test on direction (with p = 0.5 null, 20 species with 75% correct gives p about 0.02 one-sided, 12 species with 83% gives p about 0.04) [arithmetic, my own calculation]:

| Test | Minimum species | Notes |
|---|---|---|
| BBS direction/centroid test | 30 species with at least 100 route-presences in each window | BBS has hundreds of species; choose widespread species with enough routes |
| EBBA1-EBBA2 | 30 species widespread across at least 100 squares in either atlas | |
| FIA trees | 20 species with at least 500 plots in each cycle | trees shift slowly; larger n compensates |
| GBIF temporal split | 40 species per group | noisier data, more species needed |
| Pilot-species spot checks (sugar maple, robins, etc.) | not a statistical test | illustrative only; can be reported but do not count towards pass/fail |

If a group has fewer species than the minimum, the result is **not** a test and is reported as "insufficient data for validation", not as a pass.

### 4.8 Reusing the existing hindcast in this repo

What exists (read from `ctw/hindcast.py` and `config.toml`): `[hindcast] windows = [[1961,1990],[1991,2020]]`, `n_places = 100`, `seed = 20260929`. It tests the **analog-matching method** (place twin) using ERA5 on a 0.5 degree land grid, with "persistence" and "naive" baselines, and writes `data/hindcast.json`. It is a different question from species validation (it tests whether the projected climate of a place is a better analog than "nothing changes").

What can be reused:
- The **window structure** (1961-90 against 1991-2020) and the **null-model idea** (persistence baseline plus naive latitudinal shift). I recommend the species hindcast uses the same style of baselines. Note that the fit windows proposed above (1966-85, 2005-24) differ from 1961-90/1991-2020 because BBS starts in 1966; a second variant using 1961-90 climate with 1991-2020 observations should still be run for the atlas and GBIF tests to align with the site's baseline period.
- The **0.5 degree land grid**, the `_box_mean` land-weighted aggregation, the seeded diverse sampling and the `C.config()` pattern, so the species tests use the same grid and reproducible seeds.
- The **Mahalanobis sigma niche distance** in `C.ShrinkSigmaModel`: the species niche model can be run in T1 and T2 as one of the ensemble members; its change between periods gives a model-free "climate novelty" measure.
- The pattern of writing a small committed `data/hindcast_species.json` and feeding it into the methods page.

Limits: the existing routine uses ERA5 only and has no occurrence data or species; it samples places, not species; and ERA5 has no PET or solar radiation, so water-deficit predictors from TerraClimate would need a new path. I have not run or modified it.

## 5. Ranked recommendation: which hindcast tests to run first

| Rank | Test | Why | Blockers |
|---|---|---|---|
| 1 | **BBS 1966-85 to 2005-24, birds of US and Canada** | CC0, standardised effort, plain CSV, no registration, verified [A]. Directly tests American robin from the pilot list. 50+ widespread species available. | none; needs the climate grid for 1966+ (available) |
| 2 | **EBBA1 to EBBA2, European breeding birds** | Cleanest two-period, two-atlas design; tests European robin. | Licence and data-request step unverified; request 50 km occurrence data now (the request can take weeks) |
| 3 | **FIA trees, first cycle to latest cycle** | Open (US federal), reachable [A], tests sugar maple; but trees lag, so a failure is expected and is informative. Run as a **change** test, with the lag caveat. | Plot coordinates are fuzzed; table handling is heavy (state CSVs up to hundreds of MB) |
| 4 | **Compare with USFS DISTRIB-II / RDS-2024-0020 projections** | Verified downloads; US government licence; not a hindcast but a published comparison, required by roadmap 3.4 item 3. | species presence in each file to check |
| 5 | **GBIF temporal split (1970-99 against 2000-20)** | Covers every group, but weakest (effort bias). Run only with target-group background and the well-sampled-cells subset; good for plants and insects where nothing else exists. | Download DOIs, cleaning |
| 6 | **Compare with Audubon projections** (1 km rasters) | American robin, birds; licence unclear; a private comparison is fine, redistribution needs a check. | licence unverified |
| 7 | **UKBMS / eBMS butterflies** | Small region; eBMS needs a signed licence. Skip until a butterfly project is actually needed. | access |
| - | **CBC and eBird Status and Trends** | Restricted terms; do not use in the public pipeline. Optional private sanity checks. | terms |

Monarch, blacklegged tick and wine grape have **no verified hindcast dataset**: monarch (migratory, breeding generations; only eBMS-type data), tick (county presence records, CDC/others [K UNVERIFIED]) and wine grape (a crop whose range is management-driven). The protocol should state that these are **excluded from the formal validation** and shown with a "not validated" label until a dataset is found.

## 6. Open items (what remains unverified)

1. EBBA2 data licence variant and request procedure.
2. FIA coordinate fuzzing rules, DataMart licence text, and table layout.
3. Audubon climate-model licence (databasin page lists a citation, no licence in the extracted text).
4. Whether sugar maple, American robin and European robin are in the listed projection datasets.
5. GBIF per-species counts for the seven pilot species (taxon keys matched [A], counts not run).
6. The numbers attributed to Devictor et al., MESS thresholds, and the TSS/AUC rule-of-thumb bands are from memory.
7. eBMS data access policy text; PECBMS public indices.
8. The probe scripts and workflow (`.github/workflows/spike-c-probe.yml`, trigger file `.github/run/spike-c`) can be deleted after review.
