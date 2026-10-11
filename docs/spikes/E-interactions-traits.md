# Spike E: species interactions (Layer 3) and trait data

Status: research spike, written 6 October 2026. Branch `claude/eloquent-ritchie-r7jjby`. Owner: Spike E.
Companion data: `data/species/dependencies_draft.csv` (115 candidate rows). Probe scripts: `spikes/e/probe*.py`, run by `.github/workflows/spike-e-probe*.yml` (trigger file `.github/run/spike-e`).

## 0. Summary and verdict

- **Raw interaction data cannot be used to claim dependencies.** GloBI gives breadth, not exclusivity. For the monarch, only 7% of the "eats" targets and 71% of the "hasHost" targets are milkweeds; for the blacklegged tick it lists about 200 different hosts and gives the white-tailed deer, the key adult host, two records. Curating from literature is the only workable route, as the roadmap already says.
- **A literature-curated Layer 3 is feasible, but only as a small set** (a few dozen shown pairs, not 100) at the planned rigour, and only if each shown row has a citation that a person has actually read. The draft file has 115 candidate rows; 84 cite a bibliographic record I located by web search (existence confirmed, claim support not read), 31 have none. Realistically **about 20 to 30 rows** will clear the "shown" bar after review (see section 7).
- **Exposure is defined** (section 4) with a worked toy example, edge cases, and the rule that it measures potential climatic co-occurrence, never an interaction.
- **Dispersal bound:** no trait dataset gives a range-expansion speed. A rule is proposed (section 5.3) but it is a scenario with about an order-of-magnitude uncertainty and is not validated. It needs the Phase 3 hindcast to calibrate.
- **Phenology:** nothing honest can be said from monthly climate (section 6).
- **Licence flag:** FungalRoot's GBIF copy is **CC BY-NC 4.0** (queried), which conflicts with the roadmap's CC0 / CC-BY filter if the site ever has revenue. HOSTS is CC0 (queried).

### Verification labels used in this document

| Label | Meaning |
|---|---|
| **Queried** | I ran the query from a GitHub Actions runner on 2026-10-06 and read the output. The script and the run are in the repo. |
| **Search** | A web search summary says so; I did not open the primary source. |
| **Recalled** | From memory; not checked in this spike. |
| **Cite located** | A web search returned the bibliographic record. It does **not** mean I read the paper or confirmed that it supports the specific claim. |

The sandbox could not reach GloBI, NHM, FungalRoot or most data hosts (egress proxy). WebFetch to those hosts was blocked as well. Everything labelled "queried" ran on Actions.

### Legend for `data/species/dependencies_draft.csv`

Columns: consumer, resource, interaction type, class, evidence citation, confidence, notes. The bracket tag in front of each citation: **[V]** cite located by web search (existence only, claim support not read); **[R]** recalled from memory, not located; **[G]** a GloBI API record seen in this spike (association only); **[N]** no citation verified. `class` is one of obligate, near-obligate, strong-preference, generalist (section 3). `confidence` is high, medium or low and combines the evidence strength with how sure I am of the species-level pairing. Of 115 rows: 38 obligate, 31 near-obligate, 31 strong-preference, 15 generalist (the last group are negative controls, including the pilot species). Among the 69 obligate and near-obligate rows, 11 are marked high and 36 medium. A row is a candidate, never a finding, until someone has read the cited source.

## 1. Interaction data sources

| Source | Content | Access route (queried unless noted) | Format and size | Licence | Names to GBIF | Verdict |
|---|---|---|---|---|---|---|
| **GloBI** (Poelen, Simons & Mungall 2014, Ecol Inform 24:148-159; cite located) | Aggregated interaction records from many studies: eats, hasHost, parasiteOf, pollinates, visitsFlowersOf, symbiontOf, mutualistOf, dispersalVectorOf, adjacentTo, interactsWith and inverses | (a) REST API `api.globalbioticinteractions.org/interaction` (CSV or JSON, paged); (b) bulk snapshot `depot.globalbioticinteractions.org/snapshot/target/data/tsv/interactions.tsv.gz`, HTTP 200, **2,556,638,016 bytes (2.4 GiB) gzip TSV**; (c) Zenodo archives: "Interpreted Data Products" (CC0): `dwca-by-study.zip` 471 MB, `citations.tsv.gz` 47 MB, `datasets.tsv` 16.6 KB; "Taxon Graph" (CC0): `taxonCache.tsv.gz` 139 MB; "GloBI associations resource": `globi_assoc.tar.gz` 889 MB, licence "not specified" on Zenodo; (d) GitHub releases (latest tag v0.30.0, 2026-10-02) | gzip TSV, Darwin Core Archive | Zenodo products are CC0 or CC BY 4.0; a search summary says data is CC BY 4.0 unless the source dataset says otherwise. Per-study licences are the real constraint and must be filtered (see 1.1) | Each row carries source identifiers from several catalogues, not GBIF (see 2.1) | Good for leads and for a breadth indicator; **not** evidence of dependence |
| **HOSTS** (NHM London; Robinson, Ackery, Kitching, Beccaloni, Hernandez) | Lepidoptera caterpillar hostplants. A search summary says about 180,000 records, about 22,000 Lepidoptera species, about 1,600 sources; now an archival resource, last modified 2023-03-28 (queried) | NHM Data Portal CKAN. `package_show` and `datastore_search` work from Actions; the direct CSV download URL returned HTTP 403 from Actions, so paging the datastore API is the working route | CSV, 14,884,296 bytes (queried); fields: HOSTS ID, insect family/genus/species, hostplant family/genus/species, location, damage, lab rearing | **CC0** (CKAN `license_id: cc-zero`, queried) | Names are NHM/HOSTS names, taxonomy dated; must be mapped to the GBIF backbone | Best source for butterfly and moth hosts; Lepidoptera only; records are literature records, not rates |
| **FungalRoot** (Soudzilovskaia et al. 2020, New Phytol 227:955-966; cite located) | Plant mycorrhizal type (AM, EcM, ericoid, orchid, non-mycorrhizal), 36,303 species-by-site observations for 14,870 plants (search) | GBIF dataset 744edc21-8dd2-474e-8a0b-b8c3d56a3c2d, DOI 10.15468/a7ujmj; 36,515 occurrence records (queried) | GBIF occurrence records with remarks | **CC BY-NC 4.0** (queried) | Already GBIF-keyed | Tells the mycorrhizal *type* of a plant, not obligate fungal partners; the non-commercial licence blocks use if revenue is ever possible |
| **Web of Life** (Bascompte lab) | Ecological networks: 321 network names, 71,596 interaction rows; 174 network names begin `M_PL` (plant-pollinator; sub-networks of one study are counted separately) | `www.web-of-life.es/get_networks.php` returns JSON | JSON, small | Not checked | Species names only | Useful to test generality of pollinator-plant structure; no use for single-species dependency (*Danaus plexippus* appears in 0 names, *Asclepias syriaca* in 1, *Quercus* in 1; *Bombus* in 72) |
| **Mangal** | 175 datasets (header read) | `mangal.io/api/v2/dataset` | JSON API | Not checked | Own taxonomy | Same as above; not pursued |
| **Interaction Web Database (IWDB)** | Web and network data (search) | iwdb.nceas.ucsb.edu | Mixed | Not checked | - | Not pursued |
| **Ticks and hosts** | No single curated global host dataset found. A search found a western Palearctic tick distribution compilation (10,280 records, host information on 61% of records) and national surveillance schemes; museum host records for Mexican *Ixodes* | Literature | - | - | - | GloBI is the only aggregated route; supplement by literature |
| **Mosquito blood meals** | Search found meta-analyses: Culex (109 publications, 29,990 blood meals, 70 species) and one covering six vector species (over 15,600 blood meals), a Dryad dataset ("Diversity and plasticity in mosquito feeding patterns"), and VectorBase/MapVEu host blood-meal source for about 470 species | Dryad, VectorBase | Tables | Dryad CC0 default (not confirmed per dataset) | Species names | Good enough for host-preference evidence; not a dependency dataset (most mosquitoes feed on many hosts) |
| **Specialist dependency lists** | No ready-made list of obligate pairs. Starting points: Ehrlich & Raven 1964 (Evolution 18:586-608), Wcislo & Cane 1996 (bee oligolecty), Pellmyr 2003 (yuccas), Janzen 1979 and Cruaud et al. 2012 (figs), Kawakita & Kato 2004 (leafflowers), Hembry & Althoff 2016 (brood pollination), Bronstein et al. 2006 (review) (all cite located) | Literature | - | - | - | The curated route |

### 1.1 Licence handling for GloBI (open task)

GloBI is an aggregator: each study keeps its licence, and the roadmap's rule is to keep only CC0 and CC BY content. The interpreted-data `datasets.tsv` (16.6 KB) lists 458 studies by namespace (queried) but has a single column and **no licence field**, so licences cannot be filtered from that file. Per-study licences would have to be read from the study metadata inside `dwca-by-study.zip` (471 MB) or from each source repository. This is an open task, and until it is done, no GloBI-derived row may be shown.

## 2. What the data gives for the pilot set

All counts are from the GloBI API on 2026-10-06 (queried). A query by source taxon returns each interaction in both directions (for example `hasHost` and `hostOf`), so row counts are about twice the number of distinct interactions. Study-level citation fields came back empty in my CSV queries; I do not know whether that is my field names or the data, so provenance quality is **not assessed**.

### 2.1 Volume and noise

| Pilot taxon | GloBI rows (both directions) | Distinct partner names | Main types |
|---|---|---|---|
| Sugar maple *Acer saccharum* | 4,469 | 2,984 | hostOf 1,927 (mostly fungi), interactsWith 911, symbiontOf 548, eatenBy 466, pollinatedBy 50 |
| English oak *Quercus robur* | 6,661 | ~4,970 | symbiontOf ~2,100, hostOf ~1,300, eatenBy ~1,300 |
| Monarch *Danaus plexippus* | 3,060 | 1,549 | visitsFlowersOf 1,077, interactsWith 704, eats 577, visits 349, hasHost 127 |
| American robin *Turdus migratorius* | 1,191 | 859 | eats 616, interactsWith 153, hostOf 124 (parasites), hasParasite 78, preysOn 49 |
| European robin *Erithacus rubecula* | 4,231 | 4,019 | eats 2,215, preysOn 1,685, dispersalVectorOf 54 |
| Blacklegged tick *Ixodes scapularis* | 351 | 268 | hasHost 212, parasiteOf 48, interactsWith 39 |
| Wine grape *Vitis vinifera* | 6,675 | 4,685 | symbiontOf ~2,700, hostOf ~1,550, hasPathogen 545, eatenBy 517 |

**Name matching.** The rows carry identifiers from several catalogues, not GBIF keys. Over the 26,638 rows for the seven taxa, the partner identifier prefixes were: COL (Catalogue of Life) about 10,500, EOL about 4,900, WD (Wikidata) about 5,900, NCBI about 2,100; **GBIF only 648 rows (2.4%)**, and "no:match" 1,034 rows (3.9%); 189 rows (0.7%) have no name at all. Mapping partner names to the GBIF backbone with the `species/match` API on a random sample of 300 distinct partner names gave **251 exact (84%), 3 fuzzy (1%), 24 matched only to a higher rank (8%) and 22 no match (7%)**. A GBIF-keyed dependency table therefore needs a name-matching step with a logged failure rate of roughly 15%.

### 2.2 Monarch and milkweed

| Measure | GloBI | HOSTS |
|---|---|---|
| Monarch rows by type | eats 577, hasHost 127, visitsFlowersOf 1,077 | 126 rows match a free-text query for 'Danaus plexippus' (datastore API, queried; free text can match other fields, so this is not an exact-name count) |
| Share of targets in Apocynaceae (the milkweed family) | eats 41 of 577 (**7%**); hasHost 90 of 127 (**71%**); visitsFlowersOf 41 of 1,077 (4%) | Not computed (see note below) |
| Distinct *Asclepias* species among eats/hasHost targets | **42** | Not computed (see note below) |
| Top target genera (eats + hasHost) | *Asclepias* 67, Asteraceae-family-level 65, unnamed 47, Apocynaceae-family-level 37, *Salvia* 16, *Cirsium* 12 | |

Reading: "eats" in GloBI is dominated by adult nectaring, so a naive count says the monarch is mostly a daisy and mint feeder. Only the "hasHost" subset, which is larval, points at milkweeds, and even there 29% of targets are other plants or coarse names. The obligate link is real (cited in the draft file) but a database cannot tell you that. It could only be recovered here because I already knew to look at the host column. Also visible: family-level and order-level targets ("Asteraceae", "Gentianales") mix with species names, which breaks any species-level pairing without extra cleaning.

### 2.3 Oaks and their specialist insects

| Measure | GloBI (consumers that *eat* any *Quercus*) |
|---|---|
| Rows | 14,196 |
| Distinct consumer names | 3,974 |
| Distinct oak taxa as target | 180 |
| Lepidoptera consumer species | 829, of which **325 (39%) have exactly one record**; the best-recorded has 22 |

For the 25 best-recorded Lepidoptera (by Quercus records), I counted how many of each species' own GloBI "eats" records were on *Quercus*. The share ranged from 1% to 89%: **8 species had 50% or more** (mostly East Asian hairstreaks from one regional source, e.g. *Favonius orientalis* 89%), **8 had under 10%** (e.g. *Hyphantria cunea* 1% of 394 records over 99 plant genera; *Celastrina argiolus* 2% of 385 records over 121 genera), and 8 were in between; one name returned no records. The pattern says more about which studies were ingested and how intensely each species was sampled than about specialisation: a species with 9 to 12 records, all from one study, looks specialist by construction.

**HOSTS for the same questions.** The NHM datastore holds 140,485 rows (queried; the portal text says about 180,000 records, so the two numbers differ and I did not resolve why). A free-text query for 'Quercus' matches 6,265 rows, and 'Asclepias syriaca' matches 12 rows, including *Danaus plexippus* and the Asian *Euploea core*. The first monarch records returned are all *Asclepias* hosts with the family recorded as **Asclepiadaceae**, the older family name that GloBI and current taxonomy file under **Apocynaceae**; any join between the two sources needs a synonym table. A full extraction (exact-name counts of oak users and their host breadth) was attempted with the datastore API, which throttles deep paging (HTTP 409); see section 8.

For context, two published sources (cites located, not read for the numbers) report ~284 insect species on British oak (Kennedy & Southwood 1984) and *Quercus* as the genus supporting most Lepidoptera in the mid-Atlantic US (Tallamy & Shropshire 2009). Oaks are resources for many insects but **depend on none of them**, so for oak the dependency direction is insect to oak, and the oak itself is a "generalist-resource" row in the draft file.

### 2.4 Ticks and hosts

| Measure | Value |
|---|---|
| Host-type rows (hasHost, parasiteOf, ectoparasiteOf, interactsWith) | 247 |
| Distinct host names | 204 |
| Host classes (where a class could be resolved) | Mammalia 79, Aves 16, Reptilia 7; 99 names with no class path |
| Recorded counts of the textbook hosts | white-tailed deer *Odocoileus virginianus* 2, white-footed mouse *Peromyscus leucopus* 2, American robin 1, raccoon 3, humans 4 |
| Most-recorded host names | domestic cat 5, humans 4, coyote 4, "Cervidae" 3, "Aves" 3 |

The record counts do not rank the hosts by importance. The tick is a clear generalist at the host level (about 200 host names) and is classed as such in the draft file. What host data can legitimately support is a statement about **abundance** (hosts affect how many ticks), not about presence.

### 2.5 Sugar maple, robins, grape

- **Sugar maple.** 50 `pollinatedBy` rows and no specialist; the 1,927 `hostOf` rows are fungi and arthropods living on the tree, not dependencies of the tree. FungalRoot (GBIF copy) has 13 records for *A. saccharum* (arbuscular mycorrhiza by general knowledge; the record type was not read). Verdict: no dependency to show.
- **American robin.** 616 "eats" rows across about 859 partner names: a generalist (omnivore in AVONET).
- **European robin.** 2,215 "eats" and 1,685 "preysOn" rows, including 54 dispersal-vector records for plants. Generalist (AVONET: `Primary.Lifestyle = Generalist`).
- **Wine grape.** Pathogen and pest links are the substantive ones (545 `hasPathogen` rows; phylloxera and downy mildew are in the draft file as obligate consumers of *Vitis*). The grape itself needs no specific partner. FungalRoot: 14 records.

### 2.6 FungalRoot noise example

The GBIF copy has 43 records for *Quercus robur*; one carries the remark "incorrect report (this genus is EcM)" (Leho Tedersoo) and another "confirmed ECM" (Laura Suz). Remarks like these are the curation signal; a bulk import that ignores the remark field would carry the incorrect report.


## 3. Dependency classes and evidence rules

### 3.1 Scheme

A dependency is a statement "consumer C needs resource R (one species, or a defined set of substitutable species) to persist at a place". The class says how strict the need is.

| Class | Definition | Minimum evidence to assign it | Shown in product? |
|---|---|---|---|
| **obligate** | C cannot complete its life cycle (or, for a mutualist, reproduce) without R; no documented alternative resource anywhere in its range | At least one peer-reviewed source stating exclusivity AND no contradicting record of use of alternatives in a peer-reviewed source; the need is for a life stage that is not substituted by a human (so not domesticated or managed lineages) | Yes, with citation |
| **near-obligate** | Documented alternatives exist but are rare, marginal or regionally limited, so that loss of R leads to local extinction of C in most of its range | Peer-reviewed source reporting that R accounts for essentially all use (state the number, e.g. share of observations) AND the partner set is small and named | Yes, with citation and the caveat |
| **strong-preference** | C uses R most of the time but persists on alternatives; R shapes abundance, not presence | Quantitative statement of preference only | No (kept in the data file for research) |
| **generalist** | C uses many resources with no single one or small set required | Any source showing breadth, or GloBI-style breadth with many partner taxa | No; also used as an explicit negative control |

Two refinements that matter for the metric:

1. **Substitutable sets.** "Milkweeds" is a set. The rule is ANY of the set (the monarch needs at least one milkweed), unless the evidence says both are needed (a pathogen that needs a vector AND a host, written ALL).
2. **Direction.** Mutualisms can be obligate in both directions (figs and fig wasps). Each direction is its own row, because the exposure is computed separately.

### 3.2 Evidence rules (what counts as proof)

1. A citation must be a peer-reviewed paper, a review, or a curated database whose curation is described. A web page, blog or press summary is not evidence for a class, only for finding a lead.
2. Occurrence of an interaction in GloBI or any aggregator is never sufficient. It shows an observation of an interaction, not exclusivity (see the monarch numbers above: only 7% of recorded "eats" targets are milkweeds because adults nectar on everything).
3. Absence of records is not evidence of absence: all aggregated datasets are biased toward well-studied taxa and regions.
4. Exclusivity claims must name the life stage. Monarch larvae need milkweed; adults do not.
5. Host-race and geographic variation must be stated: an obligate pair in one region can be a strong-preference pair elsewhere (large blue ants in Europe, Thomas et al. 2009, are reported as essentially one ant species in the study's sites).
6. Domesticated and managed partners are out (silkworm and mulberry, honey bees on crops).
7. Class is downgraded one step when the only support is a single study, a single region, or a review that does not give the exclusivity numbers. In the draft file this is the `confidence` column.
8. Two reviewers (one entomologist or botanist for the taxon, one for the method) sign off before a row is shown. No external reviewer has been identified yet (roadmap section 13), so until then rows are shown only at confidence "high" with a verified primary or review citation that has been read, and the rest stay in the data file.

### 3.3 Why only obligate and near-obligate links are shown

- The exposure metric is only meaningful if the partner is truly required. For a generalist, exposure is about 1 by construction wherever any of dozens of partners is suitable; the number would look reassuring and be uninformative.
- Strong-preference and generalist links are the great majority of what interaction databases contain (see the numbers in section 2), and the evidence for the exact preference strength is thin. Showing them would imply knowledge we do not have.
- Obligate links are where a climate-suitability model for the consumer alone is most wrong, so that is where Layer 3 adds information. For a generalist the single-species model is already close to the best available answer.
- A smaller, well-sourced set is defensible to a reviewer. A large, noisy set is not.
- The wording constraint in the roadmap (suitability, never "will live in") must be preserved: exposure says the climates of the two species may no longer overlap; it does not say the consumer will vanish.


## 4. The exposure metric

### 4.1 Definition

Work on one grid (the species grid; Tier A, 2.5 arc-minute, or the 0.5 degree display grid), one scenario and one future period T, with t0 = the baseline period (1991-2020). Terms:

- `S_s(c, t)`: binary climate suitability of species s in cell c at time t, from the species model (ensemble consensus, thresholded at a fixed rule such as max-TSS), restricted to the species' accessible area and with novel-climate cells flagged.
- `D_s`: the dispersal distance for s per decade (section 5) and `n = (T - t0) / 10` decades.
- Dispersal bound `b`:
  - **unlimited**: the reachable set `R_s^b(T)` is every cell in the accessible area.
  - **limited**: `R_s^b(T)` is every cell within `n * D_s` of any baseline-suitable cell `S_s(., t0) = 1` (distance on the sphere, same distance rule for all species).
  - **none**: `R_s^b(T) = {c : S_s(c, t0) = 1}`.
- Realisable future area `F_s^b(c, T) = S_s(c, T) AND (c in R_s^b(T))`. For the baseline `F_s(c, t0) = S_s(c, t0)`.
- Partner set `P = {p_1 ... p_k}` and a logic: `ANY` (substitutable partners) or `ALL` (jointly required). Availability of the partners:
  `Av_P^b(c, t) = OR_i F_{p_i}^b(c, t)` for ANY, `AND_i F_{p_i}^b(c, t)` for ALL. Each partner uses its own `D_p` and the same bound `b`.

For consumer C with partner set P:

```
A_C(t)        = sum_c F_C^b(c, t)                       consumer-alone suitable area
A_CP(t)       = sum_c F_C^b(c, t) * Av_P^b(c, t)         coupled area (consumer suitable AND a partner available)
O(t)          = A_CP(t) / A_C(t)                        overlap share (0 to 1), undefined if A_C(t) = 0
```

Reported quantities, per bound b, per scenario, per period:

1. `O(t0)` and `O(T)`: the roadmap's definition ("share of its future suitable area that also overlaps the partner area, compared with today").
2. `dO = O(T) - O(t0)` in percentage points.
3. **Coupled area ratio** `Q_CP = A_CP(T) / A_CP(t0)` and **consumer-alone area ratio** `Q_C = A_C(T) / A_C(t0)`. The **dependency penalty** is `Q_CP - Q_C` (negative when the partner makes things worse). The overlap share alone can rise while the coupled area collapses, because the denominator shrinks (see the toy example), so the area ratios are always shown beside it.
4. Uncertainty: the same numbers computed over all combinations of SDM algorithms and climate models; report the median and the 10th to 90th percentile range, and the share of members where `Q_CP < Q_C`.

Sanity check built into the metric: `O(t0)` should be close to 1. If `O(t0)` is well below 1 (for example 0.6), the consumer is found today where the partner's modelled suitability is absent, so either the dependency is not real at this resolution, the partner model misses something, or the partner is present through introductions. That row is not shown until it is understood.

### 4.2 Edge cases

| Case | Rule |
|---|---|
| Several substitutable partners | ANY: partner availability is the union. Weighting by importance is not done in v1 (no data). Partners must each meet the evidence rules; a partner with only anecdotal use is left out, not given a low weight. |
| Jointly required partners (host plus vector) | ALL: intersection. State it in the row. |
| A partner has no model (too few records, failed skill gate) | Exposure is **not computed** and the page says why. It is never shown as 0 or 1. |
| Partner is a generalist or widely planted/introduced | The pair does not qualify. If the partner set is so large that its union covers nearly all land where the consumer is suitable, the result is uninformative; shown only if the union is the stated obligate set (the genus). |
| Consumer's range includes areas where the partner is introduced (monarch on introduced milkweeds in Australia or Hawaii; `Ficus microcarpa` outside its native range) | Baseline `O(t0)` uses partner occurrences including introduced ones, so the check above is fair; the future run uses the accessible area of the consumer. State the introduced-range part. |
| Reciprocal obligate pair | Compute both directions, show both, do not average. |
| Different life stages (larval host, adult nectar) | Only the obligate stage's partner enters. |
| Partner disperses slower than the consumer (trees versus butterflies) | Each uses its own `D`. This is why the limited bound often shows the largest penalty. |
| Partner is a habitat finer than a grid cell (oyamel fir stands used by overwintering monarchs) | Not computed on the climate grid; shown as text only. |
| Thresholding | Sensitivity: repeat at three thresholds (for example max-TSS, 10th-percentile training presence, and a lenient one). If the sign of the penalty flips, flag the row. |
| Consumer area becomes zero at T | `O` is undefined; report `Q_C = 0` and `Q_CP = 0`. |
| Novel-climate cells | Count them separately, and compute the metric with and without them. |
| Climate lag, extinction debt, phenology | Not modelled. The metric measures **potential climatic co-occurrence**, an upper bound on interaction, not an interaction. |

### 4.3 Worked toy example (checked by script)

A south-to-north line of 12 cells (1 to 12), each 100 km. Climate warms, so suitable bands move north.

| | Today | Future (period T, three decades after t0) |
|---|---|---|
| Consumer C suitable | cells 3-8 (6 cells) | cells 6-11 (6 cells) |
| Partner P suitable | cells 2-7 (6 cells) | cells 5-10 (6 cells) |

Dispersal: `D_C = 100 km/decade` (so 3 cells by T), `D_P = 50 km/decade` (1.5 cells, rounded down to 1 cell for this toy).

Today: coupled area is cells 3-7 = 5, so `O(t0) = 5/6 = 0.83`, and `A_CP(t0) = 5`.

| Bound | `F_C(T)` | `F_P(T)` | Coupled cells | `O(T)` | `Q_CP` | `Q_C` | Penalty `Q_CP - Q_C` |
|---|---|---|---|---|---|---|---|
| unlimited | 6-11 (6) | 5-10 (6) | 6-10 (5) | 0.83 | 1.00 | 1.00 | 0.00 |
| limited | 6-11 (6) (reachable within 3 cells of 3-8) | 5-8 (4) (reachable within 1 cell of 2-7, so cells 1-8, intersect 5-10) | 6-8 (3) | 0.50 | 0.60 | 1.00 | -0.40 |
| none | 6-8 (3) (stays in cells 3-8) | 5-7 (3) (stays in cells 2-7) | 6-7 (2) | 0.67 | 0.40 | 0.50 | -0.10 |

Read-out: with unlimited dispersal nothing is lost to the dependency. With limited dispersal the slow partner lags behind the consumer, leaving only 3 of the consumer's 6 suitable cells with a partner (a 40-point penalty). With no dispersal, the overlap share (0.67) looks better than under limited dispersal (0.50) even though the coupled area is smaller (2 cells versus 3), which is exactly why the area ratios are reported next to the share.

Adding a second, substitutable partner (ANY) is the union of the partner sets before the intersection with the consumer; a second jointly required partner (ALL) is the intersection.

## 5. Traits: dispersal and tolerance

### 5.1 Datasets

Access checked from GitHub Actions on 2026-10-06 unless stated. "Verified" = I opened or queried it. "Search" = found by web search only.

| Dataset | What it holds | Access route | Format and size | Licence | Pilot coverage | Status |
|---|---|---|---|---|---|---|
| **AVONET** (Tobias et al. 2022, Ecol Lett 25:581-597) | 11,009 bird species: 11 morphological traits including Hand-Wing Index (HWI), mass, migration class, habitat, trophic niche, range size | figshare article 16586228 | xlsx 21.5 MB (a 67.5 MB zip) | CC BY 4.0 (figshare API) | American robin: HWI 29.0, mass 78.5 g, migration code 3. European robin: HWI 19.9, mass 17.7 g, migration code 3. Both present (read from the file). AVONET-wide: HWI median 21.0, 10th to 90th percentile 10.7 to 48.6, so the American robin is high and the European robin about median | Verified |
| **EltonTraits 1.0** (Wilman et al. 2014, Ecology 95:2027) | Diet, foraging stratum, body mass, activity for ~9,993 birds and ~5,400 mammals (counts from search) | Ecological Archives E095-178 | text files | Page says "Copyright Authors"; a CC BY claim came from a search summary only, so licence not confirmed | Diet and foraging attributes; no dispersal field known to me (not checked) | Page verified, licence unconfirmed |
| **COMBINE** (Soria et al. 2021, Ecology, DOI 10.1002/ecy.3344) | 54 traits for ~6,234 mammals (search), including dispersal and home range, with imputed gaps | Not located in this spike (Crossref confirms the paper; repository link not found) | - | Not checked | No pilot mammal | Paper verified, data not accessed |
| **AmphiBIO** (Oliveira et al. 2017, Sci Data 4:170123) | 17 traits for ~6,500 amphibians | figshare 4644424 | zip 1.4 MB | CC BY 4.0 (figshare API) | No pilot amphibian; I did not check whether it has a dispersal field | Verified |
| **Reptile Database** (Uetz et al.) and lizard traits (Meiri 2018, GEB) | Checklist and nomenclature; Meiri has body size, thermal biology for 6,657 lizards (search) | Reptile Database site reachable from Actions; Meiri data via the journal repository | csv | Reptile Database terms not checked | None in pilot | Search |
| **TRY** (Kattge et al. 2020, Glob Change Biol 26:119) | Plant traits including seed mass, height, dispersal syndrome | Request-based access through try-db.org (site reachable) | Per-request files | Per-dataset licences, many CC BY, some restricted | Not requested | Site verified, no data requested |
| **Tamme et al. 2014 seed dispersal** (Ecology 95:505-513) | Maximum dispersal distances and traits for 576 plant species, plus a prediction model (R function dispeRsal) | Ecological Archives E095-045, Supplement 1 | One file, `DispersalDistanceData.csv`: 576 species, 600 data points (supplement page, queried) | "Copyright Authors" | Neither maple nor oak confirmed present (file not downloaded) | Page verified, species coverage not checked |
| **Bullock et al. 2017 kernels** (J Ecol 105:6-19) | 168 empirical dispersal kernels for 144 plant species | Dryad (search) | tables | Dryad default (CC0) per search, not confirmed | Not checked | Search |
| **Vittoz & Engler 2007** (Bot Helv 117:109-124) | Seven dispersal-distance classes by syndrome and growth form | Paper | table | n/a | Rule-based, any plant | Citation verified by search |
| **FAO EcoCrop** | Crop temperature and rainfall requirements for ~2,568 species | The old site is discontinued; now in the FAO GAEZ platform (gaez.fao.org/pages/ecocrop-search); the original site returned HTTP 503 from Actions; the GAEZ page is reachable (queried); the R package Recocrop on GitHub carries `inst/parameters/ecocrop.rds` (77,086 bytes, queried) | Web search tool; package tables | "open access, no cost" per FAO page (search); licence text not verified | Wine grape: not checked | Partly verified |
| **Sutherland et al. 2000** natal dispersal scaling (Conserv Ecol 4:16) | Median and maximum natal dispersal distances against body mass for 77 birds, 68 mammals | Open journal | table | Open access | Mass-based prediction possible for any bird or mammal | Citation verified |
| **Sheard et al. 2020** (Nat Commun 11:2463) | HWI as dispersal proxy for 10,338 bird species | Paper (HWI also inside AVONET) | - | CC BY (open access) | Yes via AVONET | Citation verified |
| **Pollinator and insect traits** | Bee foraging distance against body size (Greenleaf et al. 2007, Oecologia 153:589-596); no global colonisation-speed dataset exists for insects as far as this spike found | Papers | - | - | Monarch, tick: no trait dataset used | Citation verified; coverage gap |

Two trait values for the pilot birds deserve a note. AVONET codes `Migration` as 1 = sedentary, 2 = partially migratory, 3 = migratory (metadata sheet, queried; counts over the 11,009 species: 8,804 / 1,196 / 986, and 23 missing). Both pilot robins carry code 3. The European robin is, from my own knowledge (not checked here), resident in much of western Europe and migratory in the north and east, so a single species-level code hides range-wide variation; a population-level rule would need regional migration data.

### 5.2 What the data cannot do

No dataset above gives a **range-expansion rate**. They give distances for single dispersal events (seeds, natal dispersal) or a morphological index (HWI). A climate-tracking speed depends on those distances, generation time, establishment success, habitat connectivity and barriers. Empirical rates (for example trees spreading after the last glaciation, or contemporary lags in forest inventories) are different in kind, and the literature reports both rapid post-glacial spread and little or no recent tree range expansion (Zhu et al. 2012, Glob Change Biol 18:1042-1052, found most of 92 eastern US tree species showing no northward seedling advantage; Corlett & Westcott 2013, TREE 28:482-488, compare plant movement with climate velocity; Loarie et al. 2009, Nature 462:1052-1055, give a global mean temperature velocity of about 0.42 km per year for A1B). Those three citations were verified to exist by search; I did not extract numbers beyond what the search summaries state.

### 5.3 Proposed rule for the "limited dispersal" bound (v0, uncalibrated)

The "limited" bound is a scenario, not a prediction. Give each species a distance per decade `D_s` by this rule, and show it on the species page with its stated uncertainty.

```
D_s [km / decade] = 10 * d_s / G_s
```

where `d_s` (km) is a high-end single-event dispersal distance and `G_s` (years) is a generation interval, both from traits, so that `D_s` is the rate at which a colonising front could advance if each generation reached `d_s` and filled in.

| Group | `d_s` taken from | `G_s` taken from | Fallback when no species trait | Notes |
|---|---|---|---|---|
| Plants (trees, shrubs, herbs) | Tamme et al. model `max distance ~ dispersal syndrome + growth form (+ terminal velocity)` (R function dispeRsal), or Vittoz & Engler class medians if only syndrome and growth form are known | Age to first reproduction: tree 20-40 y, shrub 5-10 y, herb 1-3 y (heuristic classes, not from a dataset) | Genus mean, then growth form mean | Tamme et al. predict *maximum* distances, with R2 of 0.53 to 0.60 on 576 species (search summary), so the error is large on the log scale. Seed-dispersing animals (jays, nutcrackers) can lift `d_s` by orders of magnitude; give such species their own entry |
| Birds | Natal dispersal distance from Sutherland et al. mass scaling, or HWI class (high HWI: not dispersal-limited at decadal scale) | 1-3 y | HWI class from AVONET | Most mobile birds are unlikely to be dispersal-limited at 30-80 year scale; "limited" and "unlimited" coincide for them unless sedentary and low HWI. The rule should flag this rather than compute a number |
| Mammals | COMBINE or Whitmee & Orme style (body size, home range) dispersal estimates; or Sutherland mass scaling | 2-10 y | Mass scaling | Barriers (cities, roads, water) not represented |
| Insects with flying adults (butterflies, bees) | Species-level mobility class from the literature (sedentary, intermediate, mobile) if available | 0.1-1 y | Family mean | Colonisation also needs the host plant; `D` is capped by the host partner's `D` for obligate pairs |
| Ticks, parasites, vectors | Mostly passive on hosts: use the host's `D` (birds), but with low confidence | - | - | Tick range spread follows bird and deer movement and is limited by habitat, not by its own mobility |
| Crops | Not applicable: distribution is managed; use EcoCrop-style climate requirements only | - | - | Suitability only; dispersal bound shown as "n/a" |

**Stated uncertainty.** No part of this rule has been validated against observed range expansion in this spike. Treat `D_s` as uncertain by about one order of magnitude either way (a factor of ~10 up or down) for plants, and by more for insects; show the limited bound as a **band** (D/5 to 5D) instead of a single line, and say it is an assumption, not a measurement. The proper calibration is the Phase 3 hindcast: fit `k` in `D_s = k * 10 d_s / G_s` on documented shifts (Breeding Bird Survey for birds, forest inventory seedling-versus-adult latitudes for trees) and compare against published projections.

A simple alternative if calibration fails is to drop kilometre values altogether and present only the three discrete bounds (unlimited, none, and "limited by the slowest partner"), which needs no `D_s`.

### 5.4 Tolerance data

Tolerance traits for the species are better taken from the occurrence-based niche (the SDM itself) than from trait tables: physiological tolerances (frost, drought, heat) are not available globally in comparable form. EcoCrop-style minimum and maximum temperature and rainfall tables are a cross-check for crops only (Ramirez-Villegas et al. 2013, Agric For Meteorol 170:67-78, report the EcoCrop model reproducing sorghum suitability fairly well; verified by search).

## 6. Phenology: what can be said from monthly climate

Honest answer: **nothing about timing mismatches yet.** A mismatch is a change in the *difference between event dates* of two species (flowering versus pollinator emergence, leaf-out versus caterpillar hatch). Monthly climate on a 0.5 degree or 4.5 km grid cannot yield event dates, and nothing in the project predicts a species' event date. At most we could say that the *thermal cue* (e.g. spring degree days) shifts earlier by so many days at a place, and that is a statement about climate, not about the species. Kharouba et al. 2018 (PNAS 115:5211-5216) and Thackeray et al. 2016 (Nature 535:241-245) show that species differ in how phenology tracks climate, and that interaction pairs can drift apart, which is why a generic "everything shifts together" assumption is unsafe. Both exist (verified by search); I did not read them for this document.

What would be needed to say something defensible:

1. **Event-date data per species**, for the partners: long-term phenology records (UK and Europe: national phenology networks; USA-NPN; monarch arrival from citizen science such as Journey North) with sufficient replication, at least 20-30 years, across many sites.
2. **Species-specific phenological models**: temperature response (degree-day thresholds, chilling requirements, photoperiod) fitted to those records, validated out of sample.
3. **Daily or at least weekly temperature** (we have monthly): the spring window matters at the scale of days to weeks, and monthly means smear it. CMIP6 daily data are available (NEX-GDDP is daily), but bias correction of the timing of spring warmth would be needed.
4. **The interaction's temporal structure**: which stage of the consumer needs which stage of the resource, and how long the window is.
5. **Hindcast validation** against observed mismatches (Kharouba-type compilations), because the sign of the trend is not the same across species.

Verdict: leave phenology as a documented research frontier. It stays out of v1 and out of the Layer 3 claims.

## 7. Is Layer 3 feasible at the planned rigour?

**Yes, as a small curated set; no, as a database-driven layer; and "100 pairs" is optimistic.**

What the evidence in this spike supports:

1. **Aggregators cannot supply the claim.** GloBI measures how much was recorded, not how exclusive an interaction is (monarch: 7% of "eats" targets are milkweeds; ticks: about 200 hosts and 2 records for deer). HOSTS is a literature compilation and is better for Lepidoptera, but it too only lists records (a species with one record is not evidence of specialisation).
2. **Every shown row needs a person-read citation and a named life stage.** The draft file holds 115 candidate rows. After applying the evidence rules in section 3, the realistic shown set is the rows that are (a) obligate or near-obligate, (b) at confidence `high`, or (c) `medium` and confirmed by someone who has read the source, (d) both partners inside the species scope (non-threatened, enough records, not narrow endemics, not domesticated). That is on the order of 20 to 30 rows, dominated by fig/yucca-type brood pollination, monarch and milkweed, host-specific pests of tree and vine crops, vector-parasite pairs (plasmodium and *Anopheles*; schistosomes and snails), and a few seed-disperser pairs.
3. **Several of the best-documented pairs are out of v1 scope** because the species are threatened, narrow-ranged or the partner is a group (large blue butterfly, Rafflesia, Joshua-tree yucca moths, Brazil nut and bees). They are still useful as method tests.
4. **The metric needs species models for both partners.** Exposure is only defined where both partners have a model that passes the skill gate, so it inherits the pilot's coverage limits (tropical records, insects with few GBIF records).
5. **The dispersal bound is the weakest input.** The metric's most informative output is the limited-dispersal penalty, and its input `D` is uncalibrated and uncertain by about an order of magnitude. The honest position is to show the bound as a band and label it a scenario.

### Recommendation

1. **Keep Layer 3 in Phase 6 but narrow the promise** from "about 100 hand-checked pairs" to "about 25 to 40 hand-checked pairs", chosen from `data/species/dependencies_draft.csv` after the first reviewer pass, and state in the product that the layer is a curated sample, not a census.
2. **Do not ingest GloBI as a dependency source.** Use it (and HOSTS, CC0) as lead generators and as the counter-example evidence for "generalist" classes. Use the GloBI interpreted CC0 products rather than the 2.4 GiB TSV unless a specific need arises.
3. **Do not use FungalRoot in the product** unless the non-commercial licence is acceptable; mycorrhizal type is not a dependency at species level anyway.
4. **Calibrate the dispersal rule in the Phase 3 hindcast** and publish it with its band. If calibration fails, drop kilometre values and show only unlimited, none and "limited by the slowest partner".
5. **Make the "shown" bar part of the pipeline:** a row is shown only if the CSV has `class` in {obligate, near-obligate}, `confidence = high` (or reviewer-confirmed), a read citation, and both partners pass the species gates; the page test checks that every displayed dependency has a citation string.
6. **Get a taxon specialist reviewer** (an entomologist or plant-insect ecologist) for the shown rows; the roadmap notes none is identified yet.

### Open items for the next session

- Read the cited papers for the 84 rows that cite a located record, and for each shown row confirm exclusivity in the text (page and quote). Upgrade or downgrade `confidence`.
- Resolve species-level pairs recalled from memory (fig wasp and yucca moth species; Lepidoptera host rows) against HOSTS and the primary literature. The HOSTS datastore was queryable from Actions; a complete extraction was not finished in this spike unless section 2 says so.
- Build the GloBI per-study licence filter (from the study metadata in `dwca-by-study.zip`) and decide which studies are admissible; `datasets.tsv` has no licence column.
- Locate the COMBINE data file and test Tamme et al.'s `DispersalDistanceData.csv` (576 species, 600 rows, queried: the supplement lists this single file) against the species list; check coverage for the first 25 pilot species.
- Check the EcoCrop parameter table: the R package Recocrop carries `inst/parameters/ecocrop.rds` (77,086 bytes, queried) under GPL-3 for the package code, but the data's own licence is not checked; GAEZ hosts the live tool (page reachable, queried).
- Write the mapping from HOSTS/GloBI names to GBIF backbone keys with a logged failure rate (about 15% unresolved or coarse in the GloBI sample).

## 8. Reproduction and honesty notes

- Scripts: `spikes/e/probe.py` (first GloBI sweep), `probe2.py` (monarch, oaks, ticks, name matching), `probe3.py` (HOSTS, FungalRoot, Zenodo, Web of Life, trait datasets), `probe4.py` (GloBI dataset licences, full HOSTS, AVONET metadata, EcoCrop mirrors). Trigger: edit `.github/run/spike-e`. They use only the standard library plus `openpyxl`.
- The first probe capped GloBI at 6,000 rows per query and the second at 8,000 to 40,000; for English oak and wine grape the first cap truncated, which is why section 2 uses the second run's counts.
- GloBI study-citation fields were empty in my CSV query; provenance per row was not examined.
- Web search summaries were used for dataset counts and for licences marked "search". The only licences I confirmed by querying are: HOSTS (CC0, CKAN), FungalRoot on GBIF (CC BY-NC 4.0), AVONET and AmphiBIO (CC BY 4.0, figshare API), GloBI Zenodo products (CC0 or CC BY 4.0 as listed).
- No claim here is a finding about a species' future; this spike does not run any model.
