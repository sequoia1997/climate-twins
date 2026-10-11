# S1 batch 1: data scale-up of the species feature

Owner: S1 (data scale-up agent). Branch `claude/eloquent-ritchie-r7jjby`. Species list and reasons: `data/species/batch1.csv` (35 selected, 6 reserves that are not run).
Marking: [V] verified by a command or run named here, [U] unverified (judgement or design).

## 1. Status (updated as stages finish)

| stage | state | evidence |
|---|---|---|
| species selection (35 + 6 reserves) | done | [V] `tests/test_species_s1.py` (35 rows, GBIF exact accepted species match and key equal to the shortlist key for all 35, IUCN LC or NE, no pilot species, 4 download batches below 25 M records) |
| code: `ctw/species/s1run.py` (multi-species download, split by `specieskey`, native masks, `s1_*` assets), `s1report.py`, workflows `s1-w2.yml`, `s1-w3-fit.yml` | written, unit-tested | [V] 5 new tests plus the 51 existing W2/inputs/pipeline tests pass (pytest, local) |
| GBIF acquisition (4 downloads) | not started | |
| native inputs (WCVP, GRIIS) | not started | |
| assemble (masks, flags, `s1_*` assets) | not started | |
| fits, tiers, CTS (35 jobs) | not started | |

## 2. How the 35 were chosen

Source: `data/species/shortlist_v1.csv` (381 species; the 19 already in the pilot are excluded). Rules applied, in this order:
1. **Exclude**: IUCN other than LC or NE (threatened, near threatened: jaguar, plains zebra, African buffalo, American bumble bee, European ash, sugi), any `exclusion_reasons`, narrow-range or rare species, and species whose popularity comes mainly from an introduced population (house sparrow, starling, house finch) because their native mask would remove most of the records.
2. **Migratory and partial-migrant birds are left out** (mallard, Canada goose, American crow, red-tailed hawk, great blue heron, turkey vulture, Eurasian blackbird, chaffinch, buzzard and so on). Batch 1 birds are sedentary, so the all-year records are valid without the breeding-season handling that only the 11 pilot migrants have. [U] some of the 9 may have local movements.
3. **Low curation cost**: plants use WCVP (no curation); animals have a whole-continent region (or Australia only, new qualifier `OCEANIA(AU)` so New Zealand introductions are not counted as native), written in the pilot's grammar in the `native_continents_curated` column. The mask is deliberately generous, so the range check tests commission (predicted range outside the mask), the gate that matters.
4. **Strongest data first** (thinned cells expected from GBIF records and 0.5 degree sampled cells), then shortlist rank (popularity).
5. **Balance** by group (shortlist quotas tree 90, bird 90, mammal 40, wild plant 40, crop 40, insect 30 scaled to 35 with the pilot already holding 12 birds, 7 trees, 3 insects, 2 mammals, 1 crop) and by continent (shares Africa 15, Asia 22, Europe 15, North America 18, South America 17, Oceania 13 percent; the pilot is heavy on North America, so batch 1 has few North American animals).
6. **Crops: 3** (apple, maize, tomato), all worded "climate like where X is recorded" because the pilot grape showed that GBIF holds almost no records flagged cultivated or managed. [U] the same will hold; the W2 report states `cultivated_managed_records.kept` per crop and the engine switches the wording only if it is above zero.
7. **Not in batch 1 by design**: herps (20 in the shortlist) and fish (11) need two new target-group downloads and curated ranges; they wait for batch 2. Honest consequence: the 60 shown will have no reptile, amphibian or fish.

Counts by group: tree 9, bird 9, wild plant 5, mammal 5, insect 4, crop 3. By shortlist region: Europe 8, North America 8, Oceania 5, Africa 5, South America 5, Asia 4. Reserves (used only if a species cannot be processed for a data reason; a gate failure is never replaced): Betula pendula, Liriodendron tulipifera, Cyanistes caeruleus, Bombus terrestris, Alliaria petiolata, Papilio machaon.


| # | species | common name | group | rank | region | native range source | GBIF records (unfiltered, thousands) | download | reason |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Parus major | Great Tit | bird | 31 | EUROPE | curated: EUROPE;ASIA;AFRICA(N) | 14,046 | b1 | Great tit: rank 31, 14 M records; sedentary Eurasian resident, whole-continent range |
| 2 | Corvus corax | Common Raven | bird | 39 | NORTH_AMERICA | curated: NORTH_AMERICA;EUROPE;ASIA;AFRICA(N) | 12,308 | b2 | Common raven: rank 39, 12 M records; sedentary Holarctic, adds North America west and north |
| 3 | Pica pica | Eurasian Magpie | bird | 65 | EUROPE | curated: EUROPE;ASIA;AFRICA(N) | 8,193 | b1 | Eurasian magpie: rank 65, 8.2 M records; sedentary, Eurasia and NW Africa |
| 4 | Gymnorhina tibicen | Australian Magpie | bird | 135 | OCEANIA | curated: OCEANIA(AU) | 2,923 | b2 | Australian magpie: rank 135, 2.9 M records; resident, Australia (NZ introduction excluded by the OCEANIA(AU) region) |
| 5 | Malurus cyaneus | Superb Fairywren | bird | 184 | OCEANIA | curated: OCEANIA(AU) | 1,551 | b3 | Superb fairywren: rank 184, 1.6 M records; sedentary, south-eastern Australia |
| 6 | Copsychus saularis | Oriental Magpie-Robin | bird | 218 | ASIA | curated: ASIA | 1,185 | b3 | Oriental magpie-robin: rank 218, 1.2 M records; resident across tropical Asia |
| 7 | Furnarius rufus | Rufous Hornero | bird | 291 | SOUTH_AMERICA | curated: SOUTH_AMERICA | 649 | b3 | Rufous hornero: rank 291, 649 k records; sedentary, southern South America |
| 8 | Bostrychia hagedash | Hadada Ibis | bird | 300 | AFRICA | curated: AFRICA | 656 | b3 | Hadada ibis: rank 300, 657 k records; sedentary, sub-Saharan Africa |
| 9 | Pycnonotus barbatus | Common Bulbul | bird | 344 | AFRICA | curated: AFRICA | 381 | b3 | Common bulbul: rank 344, 381 k records; sedentary, Africa |
| 10 | Malus domestica | apple | crop | 25 | ASIA | none (crop) | 157 | b4 | Apple: rank 25, 158 k records, 217 sampled cells; wording 'climate like where apples are recorded' |
| 11 | Solanum lycopersicum | tomato | crop | 78 | SOUTH_AMERICA | none (crop) | 58 | b4 | Tomato: rank 78, 59 k records, 184 sampled cells; wording 'climate like where tomatoes are recorded' |
| 12 | Zea mays | Maize | crop | 99 | NORTH_AMERICA | none (crop) | 153 | b4 | Maize: rank 99, 153 k records; wording 'climate like where maize is recorded' |
| 13 | Pieris rapae | Small White | insect_arachnid | 12 | EUROPE | curated: EUROPE;ASIA;AFRICA(N) | 3,650 | b2 | Small white: rank 12, 3.7 M records; native Palearctic, introduced North America/Australasia excluded |
| 14 | Bombus impatiens | Common Eastern Bumble Bee | insect_arachnid | 94 | NORTH_AMERICA | curated: NORTH_AMERICA | 324 | b4 | Common eastern bumble bee: rank 94, 325 k records; eastern North America; LC |
| 15 | Heliconius erato | Red Postman | insect_arachnid | 322 | SOUTH_AMERICA | curated: SOUTH_AMERICA;NORTH_AMERICA | 13 | b4 | Red postman: rank 322, 13 k records; Neotropics, adds South America for insects |
| 16 | Papilio demodocus | Citrus Swallowtail | insect_arachnid | 342 | AFRICA | curated: AFRICA | 13 | b4 | Citrus swallowtail: rank 342, 14 k records; Africa south of the Sahara; resident, adds Africa |
| 17 | Procyon lotor | Common Raccoon | mammal | 50 | NORTH_AMERICA | curated: NORTH_AMERICA | 191 | b4 | Raccoon: rank 50, 191 k records, 181 cells; native North America to Panama; European/Japanese introductions excluded |
| 18 | Capreolus capreolus | Western Roe Deer | mammal | 69 | EUROPE | curated: EUROPE;ASIA(W) | 2,816 | b2 | Western roe deer: rank 69, 2.8 M records; Europe and Anatolia |
| 19 | Macropus giganteus | Eastern Grey Kangaroo | mammal | 152 | OCEANIA | curated: OCEANIA(AU) | 242 | b4 | Eastern grey kangaroo: rank 152, 242 k records; eastern Australia |
| 20 | Hydrochoerus hydrochaeris | Capybara | mammal | 156 | SOUTH_AMERICA | curated: SOUTH_AMERICA | 26 | b4 | Capybara: rank 156, 27 k records; South America (east of the Andes) |
| 21 | Aepyceros melampus | Impala | mammal | 239 | AFRICA | curated: AFRICA | 20 | b4 | Impala: rank 239, 21 k records, 95 cells; Africa (savanna) |
| 22 | Pinus sylvestris | Scots pine | tree | 15 | EUROPE | WCVP | 1,162 | b3 | Scots pine: rank 15, 1.2 M records, Eurasian range from WCVP; Europe forestry anchor |
| 23 | Fagus sylvatica | European beech | tree | 37 | EUROPE | WCVP | 1,522 | b3 | European beech: rank 37, 1.5 M records, 172 sampled cells; strongest European broadleaf data |
| 24 | Picea abies | Norway spruce | tree | 38 | EUROPE | WCVP | 989 | b3 | Norway spruce: rank 38, 1.0 M records, WCVP native range; boreal/montane Europe |
| 25 | Pseudotsuga menziesii | Douglas-fir | tree | 41 | NORTH_AMERICA | WCVP | 162 | b4 | Douglas-fir: rank 41, 163 k records; western North America complements the eastern pilot trees |
| 26 | Quercus rubra | northern red oak | tree | 64 | NORTH_AMERICA | WCVP | 227 | b4 | Northern red oak: rank 64, 228 k records; eastern North America (FIA covers it later); introduced Europe removed by WCVP mask |
| 27 | Azadirachta indica | Neem | tree | 110 | ASIA | WCVP | 62 | b4 | Neem: rank 110, 62 k records; South Asia (WCVP); tropical Asia coverage; many records are planted trees inside the native area |
| 28 | Eucalyptus camaldulensis | River Red Gum | tree | 153 | OCEANIA | WCVP | 82 | b4 | River red gum: rank 153, 83 k records; Australia; planted trees abroad removed by WCVP mask |
| 29 | Tamarindus indica | Tamarind | tree | 294 | AFRICA | WCVP | 49 | b4 | Tamarind: rank 294, 50 k records; native tropical Africa (WCVP) - cultivated pantropically, mask removes introduced area |
| 30 | Cecropia peltata | trumpet tree | tree | 334 | SOUTH_AMERICA | WCVP | 25 | b4 | Trumpet tree: rank 334, 25 k records; Neotropics; WCVP mask removes African and Asian introductions |
| 31 | Urtica dioica | great stinging nettle | wild_plant | 11 | EUROPE | WCVP | 2,174 | b3 | Stinging nettle: rank 11, 2.2 M records, 128 cells; widespread herb, WCVP native range |
| 32 | Asclepias syriaca | common milkweed | wild_plant | 95 | NORTH_AMERICA | WCVP | 149 | b4 | Common milkweed: rank 95, 150 k records; eastern North America; monarch host plant |
| 33 | Toxicodendron radicans | eastern poison ivy | wild_plant | 96 | NORTH_AMERICA | WCVP | 110 | b4 | Eastern poison ivy: rank 96, 111 k records; North America |
| 34 | Mimosa pudica | Sensitive Plant | wild_plant | 157 | ASIA | WCVP | 29 | b4 | Sensitive plant: rank 157, 29 k records; native Neotropics (WCVP), pantropical weed outside |
| 35 | Pteridium esculentum | Austral Bracken | wild_plant | 267 | OCEANIA | WCVP | 105 | b4 | Austral bracken: rank 267, 105 k records; Australasia (Oceania coverage for plants) |

## 3. Pipeline (same engine as the pilot; only the species list and asset names differ)

1. **Acquire** (`python -m ctw.species.s1run acquire`, workflow `s1-w2.yml`, push to `.github/run/s1-w2` with `[acquire]`): four GBIF downloads with the pilot's predicate but `TAXON_KEY in [...]` (SIMPLE_PARQUET): b1 two heavy birds (22 M records), b2 four (21.7 M), b3 nine (10.3 M), b4 twenty small species (2.2 M), instead of 35 single downloads (the pilot needed 29). Three at a time, state in `s1_state.json` on the release, resumable, 5.6 h limit. Rows are routed to one cleaner per species by `specieskey`, so the cleaning is identical to a single-species download [V: `test_split_download_equals_separate_cleaning` compares cells and step counts]. One DOI per download batch is cited for its species; whether GBIF accepts one DOI for a multi-species batch inside a derived dataset is still open (roadmap section 16) [U].
2. **Native inputs** (`s1run native`, `[native]`): WCVP native TDWG level 3 areas for the 14 trees and wild plants, GRIIS introduced-country flags for the 32 non-crops; stored as `s1_wcvp.json`, `s1_griis.json` on the release.
3. **Assemble** (`s1run assemble`, `[assemble]`): native masks (WCVP for plants, curated for animals, none for crops), GRIIS flags, well-sampled flags from the pilot's target-group grids (unchanged, `tg_density_<group>_v1.npz`), final assets `s1_occ_cells_v1.parquet`, `s1_occ_cells_crops_v1.parquet`, `s1_occ_cells_v1_excluded_non_native.parquet`, `s1_native_masks_v1.npz`, `s1_w2_report_v1.json`, `s1_manifest_w2_v1.json`. No pilot asset is touched.
4. **Fit** (`s1-w3-fit.yml`, push to `.github/run/s1-w3`): one job per species, `run_pilot fit --table data/species/batch1.csv` with `W3_PRODUCT=s1`; the gates, tiers, wording and the 15 percent novelty rule are the pilot's `gates.py` and `summary.py`, unchanged. Outputs `s1_w3_<id>_summary.json` and `s1_w3_<id>_cts.zip` on the release, plus `s1_manifest_cts_v1.json` (CTS file sizes, sha256 and the `stats_entry` of every shown species) and `data/species/batch1_results.csv`.
5. **Tiers expected** [U]: Tier A needs an independent survey. Only the common raven is in the Breeding Bird Survey validation set (`bbs_validation_species.csv`), so it gets the direct BBS check; every other batch 1 species can be at most Tier B (spatial-block CV only). Birds carry `range_shifts_tested = fail` from the W4 group verdict (stored per species in `data/species/batch1_evidence/shift/`, marked as a group statement); other groups are `untested`.

## 4. Code changes outside the new files (all additive)

`native.py` qualifier `OCEANIA(AU)`; `w2cells.read_batches(extra=...)`; `inputs.species_inputs` reads the `s1_*` product when `W3_PRODUCT=s1`; `project.py` dispersal rule and `tg.py` group map accept the group name `wild_plant` (15 km per decade, plant target group); the pilot behaviour is unchanged [V: the 51 existing tests above].

## 5. Issues and open points

- Plant specs in `native_continents_curated` are only used to choose the climate tiles to download and as a cross-check; WCVP decides the mask. [U] a plant without a WCVP entry falls back to the curated mask; the assemble report lists the source used per species.
- Species whose native-mask removal is large (planted trees, e.g. neem, tamarind, river red gum; invasive plants) can change the fit; the W2 report records cells removed per continent.
