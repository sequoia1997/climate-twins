# W3: production modelling pipeline (species pilot)

Status (newest last): **pipeline, gates, projection, summary, CTS writer, workflow and tests are done and pass on synthetic data and on a fake
real-size tile set; no real species has been fitted yet** (waiting for W2's occurrence products, see section 9).
Tags: **[V: how]** verified by the named command or Actions run, **[U]** unverified.

- 10 Oct 2026 (start): doc skeleton; W1, W2 had not published.
- 10 Oct 2026: modules `grid, pipeline, project, gates, summary, cts, run_pilot, inputs, synthetic` written. `pytest tests/test_species_pipeline.py tests/test_species_inputs.py
  tests/test_species_sdm.py`: 45 pass in about 50 s [V: local run].
- 10 Oct 2026: W1's tile/`apply_deltas` interface read (`docs/pilot/W1-climate.md`, `ctw/species/climstack.py`) and adapted (`inputs.W1Source`) [V: tested on a fake tile directory
  made with W1's own writers; not on W1's real files].
- Workflow `pilot-w3-fit.yml` written; first dry run on virtual species: see section 8.

## 1. What is built (all in `ctw/species/`, tests in `tests/`)

| file | job |
|---|---|
| `grid.py` | `GridSpec` (4320 x 8640, row 0 north, any size for tests), the interfaces `ClimateSource`, `Occurrences`, distance helpers (`within_km`), `SyntheticClimate` stand-in |
| `pipeline.py` | predictor selection, accessible area, target-group background, spatial-block CV (LightGBM + GAM check), threshold, `Fit` |
| `project.py` | streamed projection over bands and climate models, novelty, three dispersal bounds, `Projection` |
| `gates.py` | the gates of F section 6, range check, tier assignment |
| `summary.py` | per-species JSON summary |
| `cts.py` | writer and reader of the CTS delivery format of spike G, species files, the prototype `stats.json` record |
| `run_pilot.py` | CLI `list`, `tiles`, `fit` (resumable), `report` (markdown gate table) |
| `inputs.py` | adapters for the real data: `W1Source` (done), `species_inputs` for W2 (waiting) |
| `synthetic.py` | virtual species on the synthetic climate (tests and workflow dry run) |
| `.github/workflows/pilot-w3-fit.yml` | matrix over species, resumable, report job |

Reused unchanged from the spike: `sdm.py` (metrics `auc, tss, boyce, best_threshold, threshold`, `block_folds`, the `GBM` and `GAM` wrappers, `summarise`); `sdm.py`
and `virtual.py` were not modified.

## 2. Design, and the evidence behind each choice

Everything numeric below comes from `docs/spikes/F-sdm-engine.md` (virtual species on a 15 km North America grid; an upper bound on real accuracy, **[U]** for real data).

1. **Predictors.** Candidates are W1's ten (`bio1, bio4, bio5, bio6, bio12, bio15, bio17, gdd, cwd, aet`). They are taken in a biological priority order
   (default `bio1, bio6, bio5, cwd, bio12, bio17, bio15, bio4, aet, gdd`; trees start with `bio6`, crops with `gdd`, insects/ticks with `bio6, bio1`) and a variable is dropped when
   its absolute Spearman correlation with an already kept one exceeds 0.7 (computed on uniformly drawn cells of the accessible area), with a maximum of 5 kept. F (E3): all raw variables
   degrade the 2100 range (area-change error 2.0 to 4.7-5.3 points) and blind pruning is the worst case when it drops a true driver (9 points), so the order is by ecology and **every drop is
   recorded with the variable that caused it** (`predictors.dropped` in the summary) so a reviewer can see when a proxy replaced a driver.
2. **Main model.** LightGBM with the spike's settings (8 leaves, 150 rounds, learning rate 0.05, bagging, balanced classes). F (E4): a single GBM matched the four-model ensemble
   (2100 Sorensen 0.96 vs 0.94, area error 1.8 vs 2.0 points). **Check model:** the spike's penalised-spline GAM (smooth additive response curves, cannot form interactions).
   It is projected under 5 evenly spaced climate models; if its area change differs from the main model's by more than 25 points the species is flagged low confidence. It never votes.
3. **Background.** Cells are drawn in proportion to the target-group record density inside the training area, mixed with 5% uniform draws so no cell has zero probability.
   Size: 3 per presence, between 10,000 and 50,000. F (E2): under moderate sampling bias this cut the 2100 area-change error from 10.4 to 2.0 points; under strong bias it helps but
   does not remove the damage. F did not test a target group whose bias differs from the focal species' (that is the real case), so the correction will be partial **[U]**.
4. **Accessible area.** Training area = native range (W2 mask) plus 300 km, restricted to land with data. Projection area = native range plus 1000 km. Records outside the training area
   are dropped and counted. Without a native mask the record cells stand in for the range with a 500 km training buffer. The buffers are great-circle distances computed on a 0.25 degree
   coarse grid, so the edge is accurate to about 14 km. **Limitation [U]:** a buffer is not continent-aware; a 1000 km buffer can cross a narrow strait (for example Gibraltar). The native
   masks from W2 are what keeps most species off other continents; check the maps of the Mediterranean, Bering and Central American species before publishing.
5. **Validation.** Spatial-block CV, 5 folds, blocks of 100 to 400 km (one sixth of the extent of the records, F used 400 km). Per fold: AUC of held-out presences against held-out
   background, TSS (threshold fitted on the training fold), continuous Boyce index (presences against the evaluation cells of the held-out blocks, percentile scale), domain AUC. The
   reported **CV AUC is against the target-group background, as in F**. F's warning is built in: AUC measures niche specificity, so broad-niche species score low with good ranges
   (virtual `cold_limited` AUC 0.62, Sorensen 0.95); Boyce is reported but never gated (F: it does not discriminate).
6. **Threshold.** p05 of the out-of-fold presence scores (5th percentile). F: TSS 0.94 and 2100 area error 1.9 points, equal to max-TSS; `minpres` is unusable (TSS 0.09). The other
   thresholds are stored in the summary (`skill.thresholds_all`). Suitability is rescaled per species so that its threshold maps to 44 of 127 (the prototype's constant), so the page
   needs no per-species threshold.
7. **Projection** (memory rule: no per-model fine grid for the globe). `project_species` walks the projection area in bands of 128 rows. For each climate model (outer loop) and each
   scenario/period it asks the climate source for that model's predictors on the band, scores them, and keeps **one uint8 quantised score per model and domain cell** (24 models x 5 million
   cells = 120 MB). After all models: median suitability, agreement (share of models above the threshold, 0 to 15), novelty vote. Novelty is the MESS rule (a cell is novel for a model when
   any predictor lies outside the range of the training data; MESS < 0 is exactly that) and a cell is flagged when at least half of the models flag it; the Mahalanobis share is reported
   but does not gate. A model-outer loop is used because W1's `apply_deltas` needs one large per-model file (about 250 MB) that should be read once per model, not once per band.
8. **Dispersal bounds.** unlimited = suitable; limited = suitable and (in the present range or within reach of it); none = suitable and in the present range. Reach = km per decade x
   decades since the baseline mid-year (2006 to 2050.5 is 4.45 decades, to 2090.5 is 8.45). **The km per decade comes from a trait rule by group (tree 15, crop 10, bird 100, mammal 50,
   insect/arachnid 40, reptile 10, default 20) and is marked `calibrated: false` in every summary: about 10 times uncertain until W4's hindcast calibrates it.** A species table
   column can override it (`ProjConfig.km_per_decade`).
9. **Records and the 100-record gate.** The pilot grid cell is 4.6 km; F's 15 km cell and its 100/300/500 record counts do not transfer by number. Records are therefore counted per
   0.125 degree cell (`records.gate_cells`, about 14 km, close to F's 15 km); the narrow-range limit F states as "about 300 cells" is converted to area (300 x 225 km2 = 67,500 km2).
   Both raw and gate counts are in the summary.

## 3. Gates and tiers (`gates.py`, F section 6)

**Tiers changed on 10 Oct 2026 (owner, after W4's BBS hindcast: static skill good, range-change prediction fails).** Tier A = static skill validated against an independent survey
(`validation` JSON, kind `bbs` or `fia`, passed); Tier B = spatial-block CV skill only; Tier C = below a hard gate, not shown. Whether range shifts were tested is recorded separately as
`range_shifts_tested` = pass / fail / untested (`--shift-dir <slug>.json`, `{"status": ...}`; birds: fail) and never changes the tier. The future map is worded "projected climate suitability",
never an expected range. **CV kind:** presence-vs-background blocked CV is not a usable gate for survey-trained fits (W4), so `fit_species(absences=...)` uses true absences as the negatives and
runs presence-absence blocked CV; without absences it uses target-group background CV. The summary (`cv_kind`, `skill.cv_kind`), the report table and the CTS header `meta` all say which.
Tier, `range_shifts_tested`, `cv_kind` and `confidence` are written into the CTS header (`meta`, ignored by readers that do not know it) and into `stats_entry.json`
[V: tests `test_range_shift_status_is_recorded_separately_and_never_changes_tier`, `test_absences_make_the_cv_presence_absence`, `test_cts_meta_in_header`]. In the table below read
"Tier 3" as C, "Tier 2" as B, "Tier 1" as A.

| gate | rule | effect |
|---|---|---|
| records | at least 100 thinned records (per 0.125 degree cell) | below: Tier 3, reason recorded. Below 300, or a range under 67,500 km2 with under 500 records: low confidence ("range-shift numbers uncertain") |
| skill | CV AUC (target-group background) at least 0.7 | 0.5 to 0.7: kept, **low confidence** ("lower discrimination", F: drops 40% of good broad-niche species if used as a hard gate). Below 0.5 or not computable: Tier 3 |
| extrapolation | share of the (present or unlimited-future) area flagged novel above 15% for a scenario and period | the shift and area-change numbers are withheld for that scenario/period (kept only under `audit_withheld`); map and flag still produced |
| range check (mandatory) | omission (share of the native/expert range called unsuitable) at most 0.40 and commission (share of the predicted range outside it) at most 0.30; always reports `unrecorded_share` (predicted area more than 500 km from any record, warning above 50%) | missing or failed: Tier 3. The limits 0.40 and 0.30 are **uncalibrated first values** [U] |
| check model | area-change gap to the GAM above 25 points | low confidence. Limit uncalibrated [U] |
| tier | Tier 1 if an external change test (`validation` JSON with `kind` in `bbs`, `fia`, `passed: true`, from W4) is supplied; otherwise Tier 2; Tier 3 if a hard gate failed | `tier1_kinds` is configurable |

The wording field of every summary says "climatically suitable area (a model of climate suitability, not a forecast of the range)". The range check uses W2's native-range mask as the
expert range; a stronger atlas/hindcast check can be passed in `expert=` and `validation=`. Two things the gates cannot do (F): detect non-climatic limits that the native mask also
misses, and tell a good broad-niche model from a bad one by AUC alone.

## 4. Outputs

Per species in `<out>/<slug>/`: `fit.pkl`, `domain.npz`, `summary.json`, `cts/<slug>_base.cts`, `cts/<slug>_ssp245.cts`, `cts/<slug>_ssp585.cts`, `cts/stats_entry.json`, `DONE`.

`summary.json` (schema `ctw-species-summary/1`): species, tier, confidence, hard failures and soft flags, `area_now_km2`, records (raw, flagged, thinned cells, gate cells, used, background),
skill (CV AUC, TSS, Boyce, domain AUC, GAM check metrics, folds, block size, threshold and its source, all thresholds), predictors (kept, dropped with reason), domain, dispersal
(km per decade, reach per period, `calibrated: false`), `scenarios["SSP|period"]` with `modes.unlimited|limited|none` each holding `area_now, area_fut, change_pct, centroid_now/fut,
shift_km, bearing, gain, loss, stable, agree_share, novel_share`, `gates`, `gate_config`, `validation`, `data_dois` (passed in by the caller; W2 supplies them), provenance.

**CTS** (`cts.py`; layout in `docs/spikes/G-delivery-ui.md`): lite product, one base file and one file per scenario, names as in `prototypes/species/data/`. Bands: `S0` present
(classes 0 to 3), `S1`/`S2` near/late period (class plus reach bit 7), `A` agreement (high nibble near, low nibble late), and **`N` novel climate for this species (bit 0 near, bit 1 late), a
fourth band the prototype does not read yet**. The writer is byte-identical to the prototype's encoder [V: `test_cts_is_byte_identical_to_the_prototype_encoder`, decode and re-encode of
`s01_base.cts` and `s01_ssp245.cts`]. `stats_entry.json` is the prototype's `stats.json` species record (without the `place` table). Whether the unmodified prototype page displays W3 files
was **not** tested [U]; the loader needed is only the file names plus that record.

## 5. How to run

```
pip install lightgbm scikit-learn            # in addition to requirements.txt
python -m ctw.species.run_pilot list                                      # species ids of data/species/pilot_v1.csv
python -m ctw.species.run_pilot fit --species acer_saccharum --out work/w3 --jobs 4   # real data: W3_CLIM=work/clim (W1 files), W3_OCC=work/occ (W2 files)
python -m ctw.species.run_pilot fit --synthetic --species moderate --out work/w3      # dry run on virtual species
python -m ctw.species.run_pilot report --out work/w3 --md work/w3/REPORT.md           # gate table
```
Resume: rerun the same command; finished stages are skipped (`--force` refits). Hindcast hooks for W4: `FitConfig(window="1966-1985", years=(1966, 1985))` fits on an early window and
`Fit.score_cells(src, rows, cols, "2005-2024")` scores cells under the later climate. External change-test evidence is passed as `--validation-dir` with one `<slug>.json` per species.

Actions: push to `.github/run/pilot-w3` (content `all`, `synthetic`, or species ids; add `force`) or dispatch `Pilot W3 fit`. One job per species (timeout 345 min), working directory kept in the Actions cache
for resume, outputs uploaded to the release `species-pilot-data` as `w3_<slug>_summary.json` and `w3_<slug>_cts.zip`, and a report job commits `docs/pilot/W3-fit-report.md` and
`data/species/w3/*_summary.json`.

## 6. What is verified

- Unit tests (45 in the three species files, about 50 s) [V: `pytest tests/test_species_pipeline.py tests/test_species_inputs.py tests/test_species_sdm.py`]: grid geometry; buffer distances; predictor
  pruning order and recording; background follows target-group density and stays in the domain; domains exclude everything beyond native + buffer; fits are deterministic; CV metrics
  and the thresholds' order; recovery of a virtual species' range (sensitivity above 0.85, Sorensen above 0.8 on the coarse synthetic world, a loose bound); dispersal nesting
  (none within limited within unlimited); streamed projection independent of band size; streamed median equals direct scoring; gates (every tier path, AUC 0.5 to 0.7 low confidence, novelty withholds per
  scenario); range check flags spill outside the native range; summary arithmetic (gain + stable = future, loss + stable = now); CTS round trip, byte identity with the prototype, species files;
  resume from `fit.pkl`; hindcast hooks; W1 adapter bands and per-model deltas against W1's writers; a full fit and projection on the real 4320 x 8640 geometry.
- What these do **not** show: accuracy on real species, real-data timing, behaviour with W2's real products, or that the thresholds are right. All accuracy numbers remain F's
  virtual-species numbers.

## 7. Known limits and honest caveats

- **Synthetic checks only.** On the synthetic world, a species whose range is a large part of its accessible area gets a low CV AUC (about 0.5) although its range is recovered (as F found).
  Such species are low confidence, not removed.
- The over-prediction seen on coarse synthetic grids (area ratio 1.1 to 1.5 with a p05 threshold) comes from the threshold rule and the coarse cells; F's 15 km test gave 1.0. With 4.6 km cells and
  real records this is unmeasured **[U]**.
- Predictor pruning at 0.7 can keep a proxy instead of a true driver (on the synthetic world `bio6` replaced `bio1` at |r| 0.95). F's result stands: the future range is the sensitive part.
- No hindcast is run here; W4 supplies change tests, and Tier 1 depends on them. The uncalibrated numbers are listed in `gate_config` of each summary.
- Resolution rule of F (fit cell at most one tenth of the linear range extent) is not enforced: the grid is fixed at 4.6 km, which satisfies it for all but very small ranges.
- The hindcast needs records with years and the 1966-1985 / 2005-2024 climate; both are supported by `FitConfig` but not exercised on real data.
- Run time and memory on real data are unmeasured **[U]** (design target: a species in under 2 hours on a 4 core, 16 GB runner; the estimate rests on LightGBM scoring about 5 million cells per
  second per model and on W1's `apply_deltas` speed, which is the open question).

## 8. Actions dry run

Run 38075334221 (push to `.github/run/pilot-w3`, `synthetic`): plan, five fit jobs (broad, moderate, cold_limited, narrow, region_excluded) and the report job all succeeded
[V: Actions API job conclusions]. The first attempt (run 38073703854) failed only in the report job because it installed numpy and scipy but `ctw.common` needs pandas and requests; fixed by installing
requirements.txt. Job logs cannot be read from the sandbox (log downloads redirect to a blocked host), so the content of the synthetic gate table was not inspected.

## 8b. Real-data status (10 Oct, later)

- W1 on the release so far: tiles r0c0 and r1c2 (baseline and both hindcast windows), 11 of the climate models' `deltas_*`. Sugar maple etc. need r0c0, r0c1, r1c0, r1c1; not all there yet.
- W2 on the release so far: `w2-cells-<Genus_species>.parquet` for Acer saccharum, Danaus plexippus, Ixodes scapularis (columns row, col, lat, lon, year_min, year_max, n_records, n_events, n_1970_1999,
  n_2000_2020, n_2021_plus) and `w2-report-*.json` (with the GBIF DOI). `inputs.species_inputs` reads these [V: columns read from the real sugar maple file, 3,741 cells]. The cells are **not yet
  native-masked** (sugar maple has cells in Latvia, Japan) and no native-range or target-group density grids are published, so a real fit would be Tier 3 (range check missing) and unweighted. **Waiting on W2.**
- Speed finding [V: local timing]: W1's `apply_deltas` costs about 140 microseconds per cell (200,000 cells: 27.6 s). A 3 million cell domain, 11 or more models and 4 scenario-periods would take
  hours. `W1Source` therefore evaluates the deltas on a lattice of representative cells (spacing 4 cells, plus any cell farther than 8 cells from one) and adds the change to each cell's own fine
  baseline from the pred files (cost / 16; env `W3_DECIMATE=1` disables). Decimation check on real W1 data [V: local run, tile r1c1, 120 x 8640 band, 46,436 land cells, climate model MIROC6, SSP5-8.5 2081-2100]: decimated (spacing 4) against every-cell evaluation
differ by a mean absolute 0.014 C (99th percentile 0.11 C) for bio1, 0.018 C (0.12) for bio6, 1.9 mm (17.5) for bio12 and 3.7 mm (28) for cwd, i.e. 0.3 to 0.6% of the spread of the field, and the band
takes 0.64 s instead of 15.7 s (25 times faster). The effect on a fitted range was not measured separately; an error of 0.02 C is far below the threshold uncertainty.

## 8c. First real fit (sugar maple, interim data) [V: local run, 10 Oct]

Acer saccharum from W2's interim cell table (3,741 cells, 3,674 used; not yet native-masked), a continent-level native mask I built with `native.curated_mask("NORTH_AMERICA")` (W2's final masks were not
published), no target-group density (W2's interim `w2-tg-*` grids are all zero, so a uniform background), W1 tiles r0c0-r1c1 and **3 climate models** (CanESM5, GFDL-ESM4, MIROC6). Result: predictors bio6, bio12,
bio15 (bio1 dropped, |r| 0.96 with bio6); CV AUC 0.83, TSS 0.53, Boyce 0.94 (presence-background blocked CV); present suitable area 3.9 million km2; SSP5-8.5 2081-2100 +3.1% area, centroid shift 827 km at
bearing 29 degrees (the area change is small and the shift sign depends on the 3-model sample; not a result). Time 336 s (fit 8 s, projection 324 s for 3 models x 4 scenario-periods) on this 4 core sandbox,
peak memory about 2.4 GB at last look. Extrapolating: 24 models would take about 45 minutes. **First attempt gave Tier C** because the range check compared omission with a whole-continent mask (omission 0.85);
fixed: omission now only gates against a true expert/atlas range, a native mask gates on commission (predicted area outside the native range) alone. This is a real-data finding about the check, not about the maple.
These numbers are an engine test with interim inputs, not the pilot result.

## 8d. Review item: the omission-versus-commission gate change (made after seeing a result)

**What changed.** The mandatory range check first required omission <= 0.40 and commission <= 0.30 against the native-range mask. After the first real fit it requires **commission <= 0.30 only** when the
reference is a native-range mask (kind `native_range`); omission is still computed, stored (`omission`, `omission_gates: false`) and shown, and it still gates when the reference is a true expert or atlas
range (kind `expert_range`). Crops: see 8e.

**Why.** Before/after on the one real fit so far (sugar maple, 4 trial inputs listed in 8c; reference = my continent-level North America mask, area 25.8 million km2):

| | omission | commission | verdict before | verdict after |
|---|---|---|---|---|
| Acer saccharum, 3,674 records, CV AUC 0.83, Boyce 0.94 | 0.850 (predicted range covers 15% of North America) | 0.019 | fail, Tier C | pass, Tier B |

Omission asks "how much of the reference does the model call suitable". A native range (continent or botanical-country polygons) is the area where the species can occur, not where its climate is suitable
today, so every species with a climate niche narrower than its continent has high omission. It measures the coarseness of the mask, not the quality of the fit. Commission asks the question the check exists
for (F section 6, item 4): does the model put the species where it is not native, i.e. is there a non-climatic limit the climate model cannot see.

**Why it cannot hide a bad fit.** Removing omission from the gate opens one hole: a model that predicts almost nothing has commission near 0. Two things close it, both in `gates.evaluate` and tested:
(1) `record_recall`: at least 80% of the training records must lie inside the predicted present range (the p05 threshold gives about 95% by construction, so a fit failing this is broken), and an empty
present range is a hard failure; (2) the skill gates (CV AUC floor, record counts) and the novelty withholding are unchanged. A model that spills outside the native range still fails on commission
(`test_range_check_flags_non_climatic_limits`, `test_crop_kind_exempts_native_commission_but_not_recall`), a nearly empty model fails on recall
(`test_range_check_cannot_be_passed_by_predicting_nothing`), and the same coarse-mask numbers fail when the reference is declared an expert range
(`test_native_omission_reported_not_gated_but_commission_gates`) [V: local pytest, 35 pass]. What the change does not catch: an over-prediction that stays inside the (large) native mask, for example a
species restricted to one region of a continent. That case is the same blind spot F documented; the unrecorded-area warning (predicted area more than 500 km from any record) is the only flag for it, and a
finer mask (W2's WCVP botanical countries for plants) narrows it. Reviewers should decide whether to add an expert-range or atlas check for the species where this matters.

## 8e. Crops (owner decision, wording revised)

`species.kind` is `crop` when the pilot table `group` is `crop` (a `kind` column overrides), else `wild`; it is in the summary (`species.kind`, `species_kind`, `species.cultivated_verified`), the report, the CTS header
`meta` (`kind`, `wording`) and `stats_entry.json`. The native-range commission check is skipped for crops (status `exempt_crop`; the commission against the native mask is still stored). Recall, empty-range, records,
skill, novelty and check-model gates still apply. Licences stay CC0 and CC-BY.

**Wording.** Only when the source flags the kept records as cultivated or managed (W2 report `cultivated_managed_records.kept > 0`, stored as `cultivated_verified`) may the summary say "where the climate suits growing it".
Otherwise it says **"climate like where grapevines are recorded"** (label from `LABELS` or the common name), and adds that the records are not verified as cultivated, so it is not a statement about where the crop can be grown.
[V: `test_crop_kind_exempts_native_commission_but_not_recall` checks both wordings.]

**What the grape model represents, exactly [V: W2 report `w2_report_pilot_v1.json`].** Vitis vinifera: GBIF download 0013410 (doi 10.15468/dl.wk7m62), 88,968 records (CC0 and CC-BY), 15,348 cells after cleaning. W2 kept
cultivated and managed records for crops (`keep_cultivated: true`) but the download contained **zero** records flagged cultivated or managed; 1,106 records are flagged INTRODUCED (kept). The records are therefore
mostly ordinary GBIF observations of grape plants, with 68% in Portugal (60,783 of 88,968), then France, Germany, Italy, Spain: wild, escaped, garden and vineyard vines are not separated. The model is a presence-versus-
target-group-background model of where those recorded vines are: "climate like where grapevines are recorded", dominated by western Europe. It is not a vineyard suitability map, it has no native-range reference, and a
position in the Americas or Australia comes only from the few records there.

## 10. First real fit (run 38094754614, 10 Oct 2026) [V: Actions run; summaries on the release as `w3_<slug>_summary.json`]

Inputs: W1 baseline tiles and deltas of the 14 available TCR-likely models, W2 final cells, native masks and target-group grids (real), W4 evidence for the birds. 21 of 25 species were done when this was written; **Hirundo rustica, Vulpes vulpes and Danaus chrysippus
were still running and Vitis vinifera failed** (domain reached a tile not downloaded; crops now download all 16 tiles; rerun queued). Full tables: `docs/pilot/W3-fit-report.md` (generated by `run_pilot report --full`; the version in the repo is a snapshot of
the 21 done species and is overwritten by the Actions report job without the `--full` extras, so regenerate it from the release summaries).

**Gate results.** Tier A (9 birds: robin, cardinal, mourning dove, blue jay, red-winged blackbird, song sparrow, Carolina wren, bluebird, goldfinch), all with `range_shifts_tested = fail`; Tier B: 5 trees, deer, monarch, tick, kookaburra, baobab;
Tier C: European robin (range check: commission 0.44, so it spills outside Europe; 25% novel climate so its shift numbers are withheld). Low confidence (CV AUC under 0.7): red maple, sugar maple, white oak, English oak (0.58), tick, kookaburra, mourning dove, plus Carolina wren (check model
disagrees by 29 points). CV AUC (presence vs target-group background) 0.58 to 0.85, Boyce 0.62 to 0.96. As W4 found, background CV AUC is a weak gate for the widespread birds (0.70 to 0.79 here while W4's presence-absence AUC for the same fits is 0.90 to 0.98); the Tier A label for birds rests on W4's presence-absence evidence, not on these numbers.

**Trees against the USFS benchmark** (RDS-2024-0020 via W4; centroid shift, bearing, area change; ours = suitable area, unlimited dispersal, 2081-2100; different models, threshold, domain and climate source, so only the order of magnitude and direction are comparable):
sugar maple SSP2-4.5 ours 448 km at 25 degrees / +15.6% vs DISTRIB 575 km at 360 / +14.3% (threshold 5; 538 km at 340 / +42% at threshold 1); SSP5-8.5 875 km vs 894 km. White pine 549 km at 10 degrees vs 493-503 km. Red maple 326 km vs 407-458 km. Aspen 327 km at 350 degrees vs 487-630 km at 335-348 (direction agrees, size is
about half, and the area change is +5% against +35 to +59%). White oak 270 km vs 240-302 km. Our shifts are the same order and mostly the same direction (north to north-north-east) but systematically tilt about 25 degrees east of DISTRIB's for sugar maple and are smaller for aspen; area changes differ widely.
No tree has been tested against observed change (FIA is insufficient data), so these are agreements between two models, not validation.

**Caveats handled.**
1. *Barn swallow native list.* W2's curated list has no South America, so 17,148 of 519,754 cells (12,935 in South America) were removed; the mask removes the wintering range there. Its record pool is therefore breeding plus Old World winter records, and it also failed W4's BBS gate (no Tier A). **[summary pending: run still going]**
2. *Migratory birds.* The cell table has years but no months, so breeding and non-breeding records are pooled. Judged affected (not measured): barn swallow (long-distance), robin, red-winged blackbird, mourning dove, goldfinch, bluebird, blue jay and song sparrow (partial migrants), European robin (partial), monarch and plain tiger. Carolina wren, cardinal and kookaburra are resident. A breeding-season restriction needs W2 to keep the month of each record, aggregate records by season (northern May to July, southern November to January, tropical residents unrestricted), build target-group density for the same months, and mask native range by season; the climate predictors can stay annual (a documented choice). W4's BBS evidence is a breeding-season survey (conducted in June, from memory [U]), so the Tier A birds were validated on breeding-season presence while fitted on year-round records.
3. *Grape* (wording now "climate like where grapevines are recorded", section 8e). W2's report shows `keep_cultivated: true` but **zero** cultivated/managed-flagged records for Vitis vinifera (88,968 records, 15,348 cells; 1,106 records flagged INTRODUCED kept; mostly Portugal, France, Germany). So the crop model describes where the vine is recorded in GBIF (observations of grape plants, wild, escaped and planted, mostly Europe), not vineyard area; it can be read as "where the climate suits the vine being found", and "where the climate suits growing it" is an interpretation that the data do not prove. **[fit pending]**
4. *Precipitation change factors* (W1 QA: r 0.2 to 0.37 with the site's own). Test: pine (bio6, cwd, bio17) and white oak (bio6, bio12), 3 models, default factors against precipitation change forced to zero [V: local runs]. SSP5-8.5 2081-2100 area change: pine +31.2% vs +23.9%, oak +27.5% vs +10.6%; SSP2-4.5 2081-2100: pine +31.9% vs +18.3%, oak +17.2% vs +13.5%; centroid shift changes by 10 to 50 km and the bearing by 10 degrees. So the precipitation factors move the area change by up to 17 points for a rainfall-sensitive species and the shift little. Because the factors are poorly validated, area-change numbers for species with rain or water-deficit predictors (all 21 done species keep bio12, cwd or bio17) should carry that caveat; the direction and size of the centroid shift are robust to it. This is a bound on sensitivity, not a correction: I did not replace the factors with the site's own.

**Not done / open.** Comparison of the three remaining runs; the crop fit; checking that the Mediterranean and Bering buffers do not leak across continents (maps not inspected); the apply_deltas decimation was not rerun on real ranges; 14 models are used (the site's TCR-likely list has 15 names; AWI-CM-1-1-MR has no deltas file), not the site's 24.

## 9. Waiting on others

- W1: tile files and `apply_deltas` are on the code side; the release has no climate assets yet [as of this entry]. When they appear: run one species end to end and record time and memory.
- W2: occurrence cell tables, native-range masks and target-group density grids. `inputs.species_inputs` is a stub until `docs/pilot/W2-occurrences.md` states the file format.
- W4: change-test evidence JSON per species (`--validation-dir`) to award Tier 1; the 40 validation-only species need fits through the same pipeline.
