# Spike F: SDM engine tested on virtual species

**Recommendation: GO-WITH-CHANGES.** The engine recovers a *climate-driven* present range (median Sorensen overlap 0.94 at 500 records) and its 2100 range shift (median area-change error 2 percentage points, centroid error 54 km) on the shipped 15 km North America climate. It does **not** recover non-climatic range limits, and its own skill metrics cannot tell it has missed them. The changes needed before species go to users are in section 6.

Code: `ctw/species/sdm.py`, `virtual.py`; tests `tests/test_species_sdm.py` (13 pass in about 6 s; needs scikit-learn and lightgbm in the venv); runner `docs/spikes/F-experiments.py`; analysis `docs/spikes/F-analysis.py`; raw per-run results `docs/spikes/data/F/E1..E7.csv`; figures `docs/spikes/img/F-*.png`. A previous agent was cut off; its E1 and E6 result files were recovered from the scratchpad and used unchanged, E2-E5 and E7 were re-run (about 70 min on 4 cores). No existing core file was touched (`ctw/analogs.py` unmodified).

## 1. What was built and tested
- **Seven virtual species** on the real 15 km North America grid (baseline climate plus the shard-ensemble deltas for SSP2-4.5 2050 and SSP5-8.5 2100): `broad`, `narrow` (small range), `cold_limited` (needs mild winters), `drought_limited` (needs positive water balance), `heat_limited` (cool optimum, hard summer-heat limit), `region_excluded` (broad niche but absent from the western 35%, a non-climatic constraint) and `patchy` (30% of 150 km blocks unsuitable for soil/land-cover reasons). Each depends on two climate drivers; truth is a Gaussian/logistic response, "present" is a suitability threshold.
- **Records**: probability proportional to suitability times a population-based effort surface (stand-in for road/city bias), plus 3% false positives and 10% coordinate jitter, thinned to one per cell.
- **Pipeline**: ensemble of GAM, Maxent-like (L1 logistic with hinge features), LightGBM and random forest (GLM and the Mahalanobis niche model available but not in the default), target-group background (10 000 cells), 5-fold spatial-block CV (400 km), p05 threshold (5th percentile of presence scores), MESS plus Mahalanobis novelty flags, dispersal-bounded projection (unlimited / 100 km per decade / 20 km per decade / none), and area, centroid shift, bearing and gain/loss/stable summaries.
- **Scoring** against truth: Sorensen overlap, TSS, area ratio, error in percent area change, centroid error in km, bearing error, agreement of the gain/loss/stable class. "Unacceptable" run = present or future Sorensen below 0.8, or 2100 area-change error above 20 points.
- **Limits of the test**: (a) future climate in the grid is baseline plus deltas interpolated from a few hundred places, so truth and model share the same smooth climate; this measures the statistical engine, not GCM error. (b) The target group shares exactly the records' effort surface (best case for bias correction). (c) Truth is a smooth two-variable niche, which is easy for every algorithm. (d) 7 species x 3 seeds per cell; cell medians have wide quartile ranges, and the seven species differ more than the seeds do. Treat differences under about 0.02 Sorensen as noise.

## 2. Headline results
E1, records (median and quartiles over 7 species x 3 seeds; figure `img/F-records.png`):

| records | present Sorensen | 2050 Sorensen | 2100 Sorensen | 2100 area-change error (pp) | 2100 centroid error (km) | bearing error (deg) |
|---|---|---|---|---|---|---|
| 50 | 0.85 | 0.86 | 0.87 | 4.3 (2.3-12.7) | 135 (78-431) | 7.1 |
| 100 | 0.93 | 0.92 | 0.94 | 2.9 (1.2-5.4) | 123 (65-187) | 3.8 |
| 500 | 0.94 | 0.94 | 0.94 | 2.0 (0.8-2.8) | 54 (25-89) | 2.3 |
| 5000 | 0.95 | 0.95 | 0.95 | 1.7 (0.9-2.7) | 74 (34-185) | 1.7 |

Gain: 50 to 500 records halves the shift errors, and beyond 500 nothing improves, because the remaining error is not sampling noise. Per species at 500 records (mean of 3 seeds):

| species | present Sorensen | 2100 Sorensen | true / predicted 2100 area change (%) | centroid error (km) |
|---|---|---|---|---|
| broad | 0.98 | 0.97 | -7.5 / -8.6 | 38 |
| cold_limited | 0.95 | 0.95 | +58.0 / +58.5 | 92 |
| drought_limited | 0.96 | 0.98 | -13.3 / -10.4 | 40 |
| heat_limited | 0.99 | 0.98 | -43.2 / -44.2 | 24 |
| narrow | 0.93 | 0.93 | +59.9 / +57.1 | 88 |
| patchy | 0.79 | 0.78 | -8.1 / -5.3 | 61 |
| region_excluded | 0.79 | 0.70 | -11.4 / -8.2 | **861** (bearing error 24 deg) |

**Where it fails.**
1. *Non-climatic limits.* `patchy` and `region_excluded` plateau at Sorensen 0.7-0.8 at any record count (area ratio 1.36-1.38: the model over-predicts into unoccupied but climatically suitable cells). For `region_excluded` the model puts the species in the west too, so the future gain is placed in the wrong place: centroid error 861 km and bearing error 24 degrees even with 500 records, although area change is only 3 points off. These two species account for most of the 33% "unacceptable" runs in the gate table.
2. *Narrow-niche species with few records.* `narrow` at 50 records: present Sorensen 0.52, area ratio 2.7, 2100 area-change error 41 points, centroid error 528 km. At 100 records 0.68. It recovers at 500 (0.93) but, surprisingly, falls back to 0.77 at 5000 records: the fixed 3% false-positive rate then puts about 150 random records outside a range of a few hundred cells, which the flexible models fit. Noise rate, not record count, limits a narrow species. This is an artefact of how noise was simulated, but real GBIF data do contain misidentified and mislocated points, so cleaning matters more as records grow.
3. *Dispersal assumptions* are tracked correctly (E1, 500 records, 2100: Sorensen 0.90 unlimited, 0.90 fast, 0.89 slow, 0.84 none) since both truth and prediction use the same rule; this checks the code, not the ecology.
4. *Threshold*: `minpres` (lowest presence score) is unusable (TSS 0.09, area ratio 2.0, 2100 area-change error 13 points). `p05` (TSS 0.94, 2100 error 1.9 points) and `maxtss` (0.92, 2.0) are equivalent; `p10` slightly under-predicts (area ratio 0.95). Default stays `p05`.

## 3. Sampling bias and background (E2, 500 records)

| treatment | present Sorensen | 2100 Sorensen | 2100 area-change error (pp) | centroid error (km) | CV AUC |
|---|---|---|---|---|---|
| no bias, uniform background | 0.97 | 0.97 | 2.2 | 59 | 0.70 |
| bias, **target-group** background | 0.94 | 0.94 | 2.0 | 54 | 0.76 |
| bias, uniform background (no correction) | 0.86 | 0.90 | 10.4 | 193 | 0.80 |
| strong bias (effort squared), target-group | 0.90 | 0.92 | 5.0 | 90 | 0.73 |
| strong bias, uniform background | 0.68 | 0.80 | 29.1 | 442 | 0.86 |

Target-group background removes nearly all the damage of moderate bias (area-change error 10.4 to 2.0 points). Under strong bias it halves-to-quarters the damage but does not remove it. Note the warning in the last row: **uncorrected, more-biased data give a higher CV AUC (0.86) while the range is worse**: AUC rewards recovering the sampling effort, not the niche. `narrow` under strong bias with correction collapses to 0.47 (present). Not tested: a target group whose bias differs from the focal species' (real life), which will make the correction partial.

## 4. Predictors, algorithm, resolution
E3, predictor sets (500 records, median):

| set | present Sorensen | 2100 Sorensen | 2100 area-change error (pp) | centroid error (km) |
|---|---|---|---|---|
| true drivers only (oracle) | 0.94 | 0.94 | 2.0 | 54 |
| all 10 derived variables | 0.93 | 0.86 | 4.7 | 101 |
| 16 raw seasonal variables | 0.93 | 0.76 | 5.3 | 169 |
| correlation-pruned (|r|<0.7, priority list) | 0.91 | 0.85 | 9.1 | 86 |
| all 10 with the two true drivers removed (only correlated proxies left) | 0.93 | 0.79 | 10.6 | 200 |
| pruned set with the true drivers removed | 0.72 | 0.65 | 11.4 | 618 |

Collinearity costs little for the *present* range (proxies reproduce today's pattern) but costs a lot for the *future*: with 16 raw variables, `drought_limited` falls from 0.98 to 0.71 and `narrow` from 0.93 to 0.65 at 2100, because the correlations among predictors change under warming and the model may have latched onto a proxy. Blind correlation pruning is no cure: if the pruning drops a true driver, it is the worst case. Predictor choice should be biological, not statistical.

E4, algorithms (500 records, median; 2100 Sorensen / area-change error pp / centroid km):

| algorithm | present Sorensen | 2100 Sorensen | 2100 error pp | centroid km |
|---|---|---|---|---|
| gbm (LightGBM) | 0.95 | 0.96 | 1.8 | 51 |
| **default ensemble (gam, maxent, gbm, rf)** | 0.94 | 0.94 | 2.0 | 54 |
| rf | 0.93 | 0.93 | 5.4 | 113 |
| gam | 0.89 | 0.92 | 2.6 | 111 |
| glm, maxent | 0.90 | 0.91 | 2.2-2.4 | 77-81 |
| ensemble of glm, gam, maxent | 0.90 | 0.92 | 3.0 | 111 |
| ensemble of all six incl. Mahalanobis | 0.93 | 0.94 | 3.7 | 61 |
| Mahalanobis niche alone | 0.78 | 0.71 | 13.4 | 324 |

The smooth parametric models (glm, gam, maxent) fail on `narrow` (0.76-0.79 present) because a hard threshold on a Gaussian needs the tail; the tree models do better. The Mahalanobis niche model on its own is a poor range model (symmetric ellipsoid, over-predicts, area ratio 1.3, and cannot represent one-sided limits such as `cold_limited`) and adding it to the ensemble makes things slightly worse; keep it as the transparent "how typical is this climate" display and the novelty flag, not as a range model. In this test a single GBM is as good as the ensemble; the ensemble's justification is robustness and an algorithm-spread uncertainty band, not accuracy.

E5, grid resolution (records are thinned to the coarse cell, truth scored on the 15 km grid):

| fit grid | records left | present Sorensen | 2100 Sorensen | 2100 error pp | centroid km | `narrow` present / 2100 |
|---|---|---|---|---|---|---|
| 15 km (E1) | 499 | 0.94 | 0.94 | 2.0 | 54 | 0.93 / 0.93 |
| 30 km | 488 | 0.92 | 0.93 | 2.5 | 68 | 0.63 / 0.64 |
| 60 km | 443 | 0.89 | 0.89 | 7.7 | 128 | 0.38 / 0.44 |
| 120 km | 333 | 0.82 | 0.73 | 11.4 | 269 | 0.28 / 0.33 |

Wide-ranging species tolerate 30-60 km, a species with a small range does not (it fills a cell or two). E7, the 0.5 degree world grid (about 55 km) with 100 / 500 records: present Sorensen 0.90 / 0.96, 2100 0.93 / 0.97, area-change error 3.1 / 2.4 points, but centroid error 297 / 223 km (large because a world domain amplifies distance errors; the species there span many more cells than at 55 km in NA, so resolution relative to range size is what matters). Resolution needs a rule relative to the species' range, see gates.

## 5. Extrapolation into novel climate (E6) and the MESS flag
Trained on the cooler half of the domain only, projected everywhere (7 species x 3 seeds; figure `img/F-novelty.png`):

| species | present Sorensen | 2100 Sorensen | share flagged novel | error inside flagged cells | error outside | 2100 centroid error (km) |
|---|---|---|---|---|---|---|
| broad | 0.88 | 0.83 | 74% | 19% | 7% | 506 |
| cold_limited | 0.78 | 0.76 | 42% | 61% | 6% | 774 |
| drought_limited | 0.91 | 0.95 | 45% | 5% | 3% | 104 |
| heat_limited | 0.94 | 0.92 | 74% | 5% | 4% | 147 |
| narrow | 0.50 | 0.46 | 74% | 26% | 1% | 1586 |
| patchy | 0.72 | 0.66 | 74% | 48% | 31% | 665 |
| region_excluded | 0.73 | 0.59 | 74% | 51% | 38% | 871 |

The flag works as a warning: averaged over species, 31% of flagged cells are misclassified versus 13% of unflagged cells, and about 80% of all misclassified area lies inside the flagged area. But it is conservative and blunt: it flags a lot of cells that are fine (`heat_limited`, `drought_limited`: 5% error inside flagged cells), and it cannot see failures that are not about novel climate (patchy, region_excluded: error also high outside the flag). In the realistic setting (all of North America as training area, E1), the flag fires on only 0.2% of cells at 2050 and 1-3% at SSP5-8.5 2100; the real exposure comes when the training area is a narrow accessible area, as in E6.

## 6. Proposed defaults and quality gates
Gate analysis over 168 default-setting runs (E1-E4; figure `img/F-gates.png`; "unacceptable" as defined in section 1):

| gate | runs published | unacceptable among published | median 2100 Sorensen | 90th pct 2100 area-change error (pp) |
|---|---|---|---|---|
| none | 100% | 33% | 0.93 | 10 |
| n >= 100 | 87% | 31% | 0.94 | 9 |
| CV AUC >= 0.7 | 59% | 11% | 0.97 | 12 |
| CV AUC >= 0.75 | 57% | 8% | 0.97 | 12 |
| CV Boyce >= 0.7 | 80% | 33% | 0.94 | 9 |
| n >= 100 and Boyce >= 0.7 | 73% | 33% | 0.94 | 7 |

What this says. (a) Record count removes the worst area-change errors (90th percentile 10 to 7 points) but not the poor runs. (b) **CV Boyce does not discriminate at all** (33% unacceptable with or without it) and is anti-correlated with CV AUC (Spearman -0.58): it is lowest for `narrow` (0.46) and highest for `cold_limited` (0.91), the opposite order to AUC. It cannot be used as the sole gate. (c) CV AUC with target-group background is the only metric that separates, cutting unacceptable runs from 33% to 11%, but at a price: it rejects 41% of all runs, including good ones, because AUC measures niche *specificity*, not model quality (`cold_limited`: AUC 0.62, yet Sorensen 0.95; `narrow`: AUC 0.94 but Sorensen 0.84). And the species it correctly rejects (`patchy` 0.68, `region_excluded` 0.66) sit within 0.05 of the good species it rejects wrongly. (d) Spatial-CV metrics cannot detect a non-climatic constraint such as a missing region; that needs a different check.

**Recommended defaults**
- Algorithms: ensemble of GAM, Maxent-like, LightGBM, random forest (`Settings.algos`); the Mahalanobis model only as a display and novelty layer; per-algorithm and per-climate-model spread reported as uncertainty.
- Background: target-group, 10 000 cells, same accessible area as the records. Thin to one record per cell (15 km); 400 km spatial blocks, 5 folds.
- Threshold `p05` (not `minpres`). Dispersal: report unlimited and a trait-based limited scenario, plus none.
- Predictors: a small, biologically chosen set (2-4 per species from mean temperature, coldest-month minimum, warmest-month maximum, water balance, annual rain, with the correlation check as a warning, not as an automatic dropper); never feed all 16 raw variables.
- Resolution: fit cell no larger than about one tenth of the species' linear range extent; 15-30 km regional, about 55 km only for species spanning a continent.

**Recommended gates** (tiers rather than a single yes/no, because no single CV metric is reliable)
1. *Minimum records*: at least 100 thinned records to publish; below 300 or for a species occupying fewer than about 300 cells, label "low confidence: range-shift numbers uncertain" (virtual `narrow`: 0.68 at 100, 0.93 at 500).
2. *Skill*: CV AUC at least 0.7 (target-group background) for the top tier, with the explicit knowledge that this also drops about 40% of good broad-niche species; those go to a "lower discrimination" tier shown with shaded uncertainty instead of being dropped. Do not use Boyce as a gate (report it only). Do not trust CV AUC computed with uniform background under biased records.
3. *Extrapolation*: draw the MESS and Mahalanobis novelty mask on every future map; withhold the numeric shift and area-change summary when more than 15% of the projected-suitable (or the species' present) area is flagged; E6 shows that a 40-75% flagged share goes with centroid errors of 500-1600 km.
4. *Non-climatic limits (the blind spot)*: require a check against expert or atlas range (the accessible-area definition of roadmap section 3.1, plus hindcast against Breeding Bird Survey or similar). This cannot be replaced by CV, as `region_excluded` and `patchy` show. Predicted present range far outside the records' convex area, or presence-predicted cells with no record within a stated distance, should be flagged.
5. *Wording*: the site should say "climatically suitable area", never "range", and show it as a model of climate suitability.

## 7. Open items and honesty notes
- Everything is on simulated truth with one noise setting; real data add taxonomic error, record clustering, absence of true background information and non-stationary niches. Results are an upper bound on real accuracy.
- Gate thresholds (0.7 AUC, 100 records, 15% novel) rest on 7 species and 3 seeds and should be re-checked with a bigger virtual-species set (a few dozen random niches) before being frozen.
- The 5000-record narrow-species degradation comes from the false-positive setting; worth a dedicated experiment on record cleaning.
- Coarse-grid, world-grid runs were not repeated for bias and predictor sensitivity.
- Test of the target group with a *different* bias from the species' is not done.

## Appendix: full tables
Generated by `python docs/spikes/F-analysis.py docs/spikes/data/F maps`; "7 species x 3 seeds" in some headings of the generated tables is a typo for 7 species (84 runs in E1).

### E1 by number of records (median and quartiles over 7 species x 3 seeds)

| n_req | records used | CV AUC | CV TSS | CV Boyce | present Sorensen | present TSS | area ratio | 2050 Sorensen | 2100 Sorensen | 2100 area-change error (pp) | 2100 centroid error (km) | bearing error (deg) | change-class agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 50 | 50.00 (50.00-50.00) | 0.76 (0.68-0.88) | 0.30 (0.18-0.38) | 0.74 (0.55-0.78) | 0.85 (0.72-0.93) | 0.81 (0.44-0.88) | 1.18 (0.98-1.64) | 0.86 (0.71-0.94) | 0.87 (0.71-0.92) | 4.30 (2.29-12.69) | 134.55 (77.73-430.86) | 7.13 (2.10-11.24) | 0.82 (0.62-0.88) |
| 100 | 100.00 (100.00-100.00) | 0.77 (0.67-0.86) | 0.30 (0.17-0.51) | 0.77 (0.69-0.82) | 0.93 (0.77-0.95) | 0.86 (0.55-0.92) | 1.07 (0.98-1.47) | 0.92 (0.76-0.95) | 0.94 (0.76-0.94) | 2.88 (1.16-5.44) | 122.86 (64.85-187.13) | 3.81 (1.24-6.65) | 0.87 (0.68-0.92) |
| 500 | 499.00 (498.00-500.00) | 0.76 (0.65-0.87) | 0.38 (0.21-0.68) | 0.85 (0.81-0.88) | 0.94 (0.80-0.98) | 0.94 (0.60-0.97) | 0.99 (0.96-1.30) | 0.94 (0.79-0.98) | 0.94 (0.79-0.98) | 1.95 (0.82-2.75) | 53.55 (24.70-88.96) | 2.25 (1.12-3.38) | 0.95 (0.72-0.97) |
| 5000 | 4910.00 (4888.00-4922.00) | 0.78 (0.69-0.90) | 0.49 (0.30-0.78) | 0.83 (0.79-0.94) | 0.95 (0.80-0.98) | 0.93 (0.64-0.97) | 1.00 (0.96-1.37) | 0.95 (0.79-0.98) | 0.95 (0.78-0.98) | 1.72 (0.94-2.71) | 73.94 (33.58-184.95) | 1.74 (0.92-5.92) | 0.94 (0.72-0.96) | 

### E1 per species at 500 records (mean of 3 seeds)

| species | cv_auc | cv_boyce | now_sorensen | now_tss | now_area_ratio | 2-4_2050_sorensen | 5-8_2100_sorensen | 5-8_2100_abs_change_err | 5-8_2100_shift_err_km | 5-8_2100_bearing_err | 5-8_2100_class_agree | 5-8_2100_true_change | 5-8_2100_pred_change |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| broad | 0.77 | 0.88 | 0.98 | 0.95 | 0.98 | 0.98 | 0.97 | 1.1 | 37.72 | 1.41 | 0.95 | -7.49 | -8.59 |
| cold_limited | 0.61 | 0.93 | 0.95 | 0.9 | 0.9 | 0.95 | 0.95 | 1.01 | 92.11 | 1.45 | 0.89 | 57.99 | 58.45 |
| drought_limited | 0.77 | 0.84 | 0.96 | 0.92 | 0.93 | 0.95 | 0.98 | 2.86 | 40.07 | 1.19 | 0.95 | -13.25 | -10.4 |
| heat_limited | 0.89 | 0.8 | 0.99 | 0.98 | 0.99 | 0.98 | 0.98 | 0.93 | 23.83 | 1.53 | 0.98 | -43.24 | -44.17 |
| narrow | 0.94 | 0.42 | 0.93 | 0.97 | 1.11 | 0.94 | 0.93 | 2.8 | 88.12 | 3.1 | 0.98 | 59.94 | 57.14 |
| patchy | 0.68 | 0.85 | 0.79 | 0.54 | 1.36 | 0.78 | 0.78 | 2.76 | 61.08 | 3.23 | 0.7 | -8.09 | -5.33 |
| region_excluded | 0.64 | 0.85 | 0.79 | 0.6 | 1.38 | 0.76 | 0.7 | 3.18 | 860.77 | 23.96 | 0.68 | -11.39 | -8.21 | 

### E1 per species at 50 records

| species | cv_auc | cv_boyce | now_sorensen | now_tss | now_area_ratio | 2-4_2050_sorensen | 5-8_2100_sorensen | 5-8_2100_abs_change_err | 5-8_2100_shift_err_km | 5-8_2100_bearing_err | 5-8_2100_class_agree |
|---|---|---|---|---|---|---|---|---|---|---|---|
| broad | 0.77 | 0.73 | 0.91 | 0.75 | 1.16 | 0.91 | 0.92 | 2.4 | 93.56 | 4.69 | 0.83 |
| cold_limited | 0.63 | 0.8 | 0.92 | 0.86 | 0.87 | 0.93 | 0.92 | 1.82 | 58.5 | 3.68 | 0.85 |
| drought_limited | 0.78 | 0.78 | 0.88 | 0.79 | 1.09 | 0.87 | 0.9 | 11.3 | 155.4 | 7.81 | 0.84 |
| heat_limited | 0.89 | 0.65 | 0.94 | 0.89 | 1.1 | 0.93 | 0.89 | 5.24 | 128.72 | 7.62 | 0.88 |
| narrow | 0.95 | 0.54 | 0.52 | 0.85 | 2.72 | 0.54 | 0.61 | 41.01 | 528.32 | 8.28 | 0.81 |
| patchy | 0.66 | 0.48 | 0.74 | 0.39 | 1.6 | 0.74 | 0.74 | 1.6 | 137.54 | 3.62 | 0.61 |
| region_excluded | 0.67 | 0.64 | 0.71 | 0.41 | 1.41 | 0.7 | 0.67 | 14.33 | 848.12 | 12.36 | 0.56 | 

### E1 dispersal assumptions (500 records, 2100): Sorensen of limited projection vs the same assumption applied to truth; area ratio

|  | Sorensen | area ratio (median) |
|---|---|---|
| unlimited | 0.9 | 0.97 |
| fast | 0.9 | 0.98 |
| slow | 0.89 | 0.98 |
| none | 0.84 | 0.97 | 

### thresholds (E1, 500 records)

|  | present TSS | present area ratio | 2100 Sorensen | |area-change error| pp |
|---|---|---|---|---|
| maxtss | 0.92 | 1.01 | 0.92 | 2.0 |
| p10 | 0.86 | 0.95 | 0.94 | 2.3 |
| p05 | 0.94 | 0.99 | 0.94 | 1.9 |
| minpres | 0.09 | 2.02 | 0.59 | 13.3 | 

### gate analysis: 168 runs with default settings

| gate | published | unacceptable among published | median 2100 Sorensen | 90th pct |area-change error| pp |
|---|---|---|---|---|
| no gate | 100% | 33% | 0.93 | 10 |
| n >= 50 | 99% | 33% | 0.93 | 10 |
| n >= 100 | 87% | 31% | 0.94 | 9 |
| CV AUC >= 0.7 | 59% | 11% | 0.97 | 12 |
| CV AUC >= 0.75 | 57% | 8% | 0.97 | 12 |
| CV Boyce >= 0.6 | 82% | 33% | 0.94 | 9 |
| CV Boyce >= 0.7 | 80% | 33% | 0.94 | 9 |
| CV Boyce >= 0.8 | 60% | 36% | 0.93 | 9 |
| n >= 100 & Boyce >= 0.7 | 73% | 33% | 0.94 | 7 |
| n >= 100 & Boyce >= 0.7 & AUC >= 0.6 | 70% | 35% | 0.94 | 6 |
| n >= 100 & Boyce >= 0.7 & novel <= 15% | 73% | 33% | 0.94 | 7 | 

### E2 (median and quartiles; 7 species x 3 seeds)

| label | records | CV AUC | CV Boyce | present Sorensen | present TSS | area ratio | 2050 Sorensen | 2100 Sorensen | 2100 area-change error (pp) | 2100 centroid error (km) | bearing error (deg) | change-class agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bias/target | 499.00 (498.00-500.00) | 0.76 (0.65-0.87) | 0.85 (0.81-0.88) | 0.94 (0.80-0.98) | 0.94 (0.60-0.97) | 0.99 (0.96-1.30) | 0.94 (0.79-0.98) | 0.94 (0.79-0.98) | 1.95 (0.82-2.75) | 53.55 (24.70-88.96) | 2.25 (1.12-3.38) | 0.95 (0.72-0.97) |
| bias/uniform | 499.00 (498.00-500.00) | 0.80 (0.76-0.84) | 0.92 (0.89-0.95) | 0.86 (0.73-0.92) | 0.76 (0.49-0.90) | 0.98 (0.90-1.24) | 0.89 (0.73-0.92) | 0.90 (0.74-0.92) | 10.40 (5.56-17.05) | 193.10 (148.59-314.94) | 3.65 (2.06-6.33) | 0.80 (0.58-0.91) |
| none/uniform | 499.00 (499.00-500.00) | 0.70 (0.66-0.77) | 0.87 (0.83-0.88) | 0.97 (0.80-0.98) | 0.94 (0.61-0.96) | 0.99 (0.97-1.41) | 0.95 (0.79-0.97) | 0.97 (0.78-0.98) | 2.15 (0.91-3.34) | 58.99 (17.46-164.34) | 1.77 (0.74-2.60) | 0.94 (0.73-0.97) |
| strong/target | 497.00 (496.00-499.00) | 0.73 (0.69-0.92) | 0.83 (0.61-0.89) | 0.90 (0.77-0.93) | 0.85 (0.57-0.87) | 1.14 (1.02-1.40) | 0.90 (0.75-0.93) | 0.92 (0.72-0.97) | 4.99 (1.81-10.52) | 90.39 (33.33-341.99) | 3.33 (1.18-5.85) | 0.85 (0.72-0.92) |
| strong/uniform | 497.00 (496.00-499.00) | 0.86 (0.82-0.88) | 0.88 (0.82-0.92) | 0.68 (0.63-0.85) | 0.49 (0.38-0.80) | 0.85 (0.77-0.89) | 0.72 (0.64-0.83) | 0.80 (0.70-0.83) | 29.14 (11.09-39.51) | 442.15 (268.61-470.03) | 7.61 (2.07-12.73) | 0.65 (0.52-0.80) | 

### E2 per species, present Sorensen / 2100 Sorensen (mean of 3 seeds)

| label | broad | cold_limited | drought_limited | heat_limited | narrow | patchy | region_excluded |
|---|---|---|---|---|---|---|---|
| bias/target | 0.98 / 0.97 | 0.95 / 0.95 | 0.96 / 0.98 | 0.99 / 0.98 | 0.93 / 0.93 | 0.79 / 0.78 | 0.79 / 0.7 |
| bias/uniform | 0.88 / 0.91 | 0.93 / 0.92 | 0.85 / 0.88 | 0.95 / 0.94 | 0.88 / 0.88 | 0.7 / 0.73 | 0.72 / 0.66 |
| none/uniform | 0.98 / 0.98 | 0.96 / 0.97 | 0.98 / 0.98 | 0.98 / 0.97 | 0.83 / 0.83 | 0.8 / 0.78 | 0.79 / 0.71 |
| strong/target | 0.96 / 0.97 | 0.91 / 0.93 | 0.9 / 0.98 | 0.93 / 0.96 | 0.47 / 0.67 | 0.79 / 0.78 | 0.77 / 0.69 |
| strong/uniform | 0.67 / 0.82 | 0.92 / 0.91 | 0.67 / 0.77 | 0.85 / 0.82 | 0.81 / 0.8 | 0.6 / 0.69 | 0.62 / 0.64 | 

### E3 (median and quartiles; 7 species x 3 seeds)

| label | records | CV AUC | CV Boyce | present Sorensen | present TSS | area ratio | 2050 Sorensen | 2100 Sorensen | 2100 area-change error (pp) | 2100 centroid error (km) | bearing error (deg) | change-class agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all10 | 499.00 (498.00-500.00) | 0.75 (0.67-0.87) | 0.85 (0.79-0.89) | 0.93 (0.84-0.97) | 0.93 (0.78-0.96) | 1.00 (0.96-1.28) | 0.92 (0.82-0.97) | 0.86 (0.78-0.96) | 4.68 (1.36-15.09) | 101.28 (45.31-182.21) | 3.25 (1.74-5.96) | 0.92 (0.72-0.94) |
| all10_minus_drivers | 499.00 (498.00-500.00) | 0.75 (0.66-0.86) | 0.86 (0.80-0.90) | 0.93 (0.78-0.94) | 0.89 (0.73-0.91) | 1.11 (0.99-1.36) | 0.87 (0.78-0.93) | 0.79 (0.73-0.91) | 10.56 (5.20-19.44) | 200.35 (117.51-310.97) | 7.40 (5.28-11.15) | 0.82 (0.70-0.85) |
| drivers | 499.00 (498.00-500.00) | 0.76 (0.65-0.87) | 0.85 (0.81-0.88) | 0.94 (0.80-0.98) | 0.94 (0.60-0.97) | 0.99 (0.96-1.30) | 0.94 (0.79-0.98) | 0.94 (0.79-0.98) | 1.95 (0.82-2.75) | 53.55 (24.70-88.96) | 2.25 (1.12-3.38) | 0.95 (0.72-0.97) |
| raw16 | 499.00 (498.00-500.00) | 0.75 (0.67-0.87) | 0.87 (0.79-0.91) | 0.93 (0.78-0.96) | 0.91 (0.85-0.93) | 1.02 (0.99-1.33) | 0.86 (0.77-0.96) | 0.76 (0.74-0.94) | 5.34 (1.65-18.18) | 168.93 (73.20-479.37) | 4.34 (1.38-22.85) | 0.86 (0.74-0.90) |
| uncorr | 499.00 (498.00-500.00) | 0.76 (0.66-0.86) | 0.85 (0.82-0.87) | 0.91 (0.82-0.95) | 0.90 (0.66-0.94) | 1.06 (0.97-1.29) | 0.91 (0.79-0.92) | 0.85 (0.77-0.92) | 9.06 (5.65-10.57) | 86.01 (61.63-331.33) | 1.54 (0.88-12.66) | 0.86 (0.70-0.94) |
| uncorr_minus_drivers | 499.00 (498.00-500.00) | 0.60 (0.55-0.73) | 0.70 (0.48-0.81) | 0.72 (0.62-0.87) | 0.41 (0.10-0.78) | 1.60 (1.11-1.97) | 0.72 (0.61-0.80) | 0.65 (0.59-0.70) | 11.35 (7.98-24.22) | 618.03 (493.28-706.34) | 16.37 (8.08-43.39) | 0.49 (0.40-0.70) | 

### E3 per species, present Sorensen / 2100 Sorensen (mean of 3 seeds)

| label | broad | cold_limited | drought_limited | heat_limited | narrow | patchy | region_excluded |
|---|---|---|---|---|---|---|---|
| all10 | 0.97 / 0.95 | 0.96 / 0.95 | 0.95 / 0.87 | 0.99 / 0.97 | 0.85 / 0.79 | 0.78 / 0.77 | 0.85 / 0.73 |
| all10_minus_drivers | 0.96 / 0.92 | 0.95 / 0.92 | 0.93 / 0.79 | 0.94 / 0.84 | 0.61 / 0.54 | 0.78 / 0.76 | 0.84 / 0.72 |
| drivers | 0.98 / 0.97 | 0.95 / 0.95 | 0.96 / 0.98 | 0.99 / 0.98 | 0.93 / 0.93 | 0.79 / 0.78 | 0.79 / 0.7 |
| raw16 | 0.96 / 0.92 | 0.97 / 0.97 | 0.93 / 0.71 | 0.99 / 0.96 | 0.7 / 0.65 | 0.77 / 0.75 | 0.9 / 0.76 |
| uncorr | 0.97 / 0.97 | 0.92 / 0.93 | 0.95 / 0.85 | 0.95 / 0.84 | 0.89 / 0.89 | 0.78 / 0.77 | 0.81 / 0.73 |
| uncorr_minus_drivers | 0.72 / 0.7 | 0.9 / 0.9 | 0.88 / 0.69 | 0.83 / 0.65 | 0.17 / 0.24 | 0.64 / 0.62 | 0.62 / 0.58 | 

### E4 (median and quartiles; 7 species x 3 seeds)

| label | records | CV AUC | CV Boyce | present Sorensen | present TSS | area ratio | 2050 Sorensen | 2100 Sorensen | 2100 area-change error (pp) | 2100 centroid error (km) | bearing error (deg) | change-class agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ens4 | 499.00 (498.00-500.00) | 0.76 (0.65-0.87) | 0.85 (0.81-0.88) | 0.94 (0.80-0.98) | 0.94 (0.60-0.97) | 0.99 (0.96-1.30) | 0.94 (0.79-0.98) | 0.94 (0.79-0.98) | 1.95 (0.82-2.75) | 53.55 (24.70-88.96) | 2.25 (1.12-3.38) | 0.95 (0.72-0.97) |
| ens6 | 499.00 (498.00-500.00) | 0.76 (0.65-0.87) | 0.88 (0.83-0.91) | 0.93 (0.75-0.96) | 0.88 (0.48-0.95) | 0.98 (0.96-1.26) | 0.94 (0.76-0.96) | 0.94 (0.76-0.96) | 3.66 (1.09-10.18) | 61.10 (41.13-121.88) | 2.22 (0.78-3.17) | 0.91 (0.64-0.95) |
| ens_glm_gam_maxent | 499.00 (498.00-500.00) | 0.76 (0.65-0.87) | 0.81 (0.75-0.86) | 0.90 (0.78-0.97) | 0.88 (0.54-0.95) | 1.04 (0.95-1.35) | 0.87 (0.78-0.96) | 0.92 (0.78-0.96) | 2.98 (1.10-5.98) | 110.59 (52.02-209.86) | 3.88 (3.00-7.88) | 0.88 (0.69-0.94) |
| gam | 499.00 (498.00-500.00) | 0.75 (0.65-0.87) | 0.82 (0.77-0.88) | 0.89 (0.78-0.97) | 0.89 (0.57-0.95) | 1.05 (1.00-1.37) | 0.86 (0.78-0.96) | 0.92 (0.78-0.95) | 2.57 (1.49-5.40) | 110.59 (42.09-239.94) | 3.71 (2.09-7.71) | 0.87 (0.70-0.94) |
| gbm | 499.00 (498.00-500.00) | 0.76 (0.64-0.87) | 0.86 (0.84-0.90) | 0.95 (0.80-0.97) | 0.94 (0.58-0.96) | 1.02 (0.96-1.32) | 0.94 (0.79-0.97) | 0.96 (0.79-0.97) | 1.82 (1.13-3.14) | 50.68 (25.24-85.18) | 2.72 (1.71-4.32) | 0.94 (0.72-0.97) |
| glm | 499.00 (498.00-500.00) | 0.76 (0.65-0.87) | 0.80 (0.73-0.84) | 0.90 (0.78-0.97) | 0.87 (0.54-0.94) | 1.04 (0.94-1.34) | 0.86 (0.78-0.97) | 0.91 (0.78-0.97) | 2.37 (1.64-6.07) | 77.40 (59.69-207.10) | 4.01 (3.00-7.80) | 0.88 (0.69-0.94) |
| mahal | 499.00 (498.00-500.00) | 0.72 (0.65-0.81) | 0.90 (0.81-0.93) | 0.78 (0.68-0.83) | 0.61 (0.38-0.80) | 1.30 (1.05-1.37) | 0.77 (0.70-0.85) | 0.71 (0.64-0.86) | 13.43 (11.96-22.27) | 324.14 (274.74-697.36) | 4.23 (1.73-11.91) | 0.57 (0.50-0.83) |
| maxent | 499.00 (498.00-500.00) | 0.76 (0.65-0.87) | 0.78 (0.73-0.84) | 0.90 (0.77-0.97) | 0.88 (0.54-0.94) | 1.05 (0.94-1.34) | 0.86 (0.78-0.97) | 0.91 (0.78-0.97) | 2.17 (0.78-6.83) | 80.85 (59.61-211.22) | 4.49 (2.78-7.99) | 0.88 (0.69-0.94) |
| rf | 499.00 (498.00-500.00) | 0.75 (0.63-0.87) | 0.77 (0.71-0.86) | 0.93 (0.77-0.96) | 0.87 (0.50-0.96) | 1.10 (0.99-1.43) | 0.93 (0.77-0.96) | 0.93 (0.76-0.97) | 5.36 (1.37-8.03) | 112.52 (44.31-196.70) | 1.96 (0.40-3.29) | 0.89 (0.65-0.97) | 

### E4 per species, present Sorensen / 2100 Sorensen (mean of 3 seeds)

| label | broad | cold_limited | drought_limited | heat_limited | narrow | patchy | region_excluded |
|---|---|---|---|---|---|---|---|
| ens4 | 0.98 / 0.97 | 0.95 / 0.95 | 0.96 / 0.98 | 0.99 / 0.98 | 0.93 / 0.93 | 0.79 / 0.78 | 0.79 / 0.7 |
| ens6 | 0.95 / 0.96 | 0.95 / 0.95 | 0.94 / 0.96 | 0.98 / 0.98 | 0.94 / 0.95 | 0.73 / 0.74 | 0.68 / 0.64 |
| ens_glm_gam_maxent | 0.97 / 0.96 | 0.94 / 0.95 | 0.9 / 0.9 | 0.97 / 0.97 | 0.81 / 0.82 | 0.78 / 0.77 | 0.76 / 0.69 |
| gam | 0.97 / 0.96 | 0.95 / 0.95 | 0.89 / 0.91 | 0.98 / 0.95 | 0.78 / 0.82 | 0.78 / 0.77 | 0.77 / 0.69 |
| gbm | 0.97 / 0.97 | 0.96 / 0.96 | 0.96 / 0.97 | 0.98 / 0.98 | 0.92 / 0.93 | 0.79 / 0.78 | 0.78 / 0.71 |
| glm | 0.97 / 0.97 | 0.94 / 0.94 | 0.9 / 0.89 | 0.97 / 0.98 | 0.79 / 0.79 | 0.78 / 0.78 | 0.76 / 0.7 |
| mahal | 0.83 / 0.87 | 0.9 / 0.92 | 0.74 / 0.61 | 0.81 / 0.69 | 0.77 / 0.8 | 0.68 / 0.71 | 0.68 / 0.64 |
| maxent | 0.97 / 0.97 | 0.94 / 0.94 | 0.9 / 0.89 | 0.97 / 0.98 | 0.76 / 0.78 | 0.78 / 0.78 | 0.76 / 0.69 |
| rf | 0.94 / 0.92 | 0.85 / 0.94 | 0.94 / 0.96 | 0.98 / 0.98 | 0.92 / 0.92 | 0.77 / 0.75 | 0.75 / 0.69 | 

### E5 (median and quartiles; 7 species x 3 seeds)

| label | records | CV AUC | CV Boyce | present Sorensen | present TSS | area ratio | 2050 Sorensen | 2100 Sorensen | 2100 area-change error (pp) | 2100 centroid error (km) | bearing error (deg) | change-class agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 120 km | 333.00 (294.00-341.00) | 0.73 (0.71-0.76) | 0.88 (0.83-0.94) | 0.82 (0.72-0.90) | 0.70 (0.51-0.81) | 1.34 (1.13-1.46) | 0.77 (0.71-0.89) | 0.73 (0.65-0.88) | 11.36 (5.52-27.20) | 269.07 (190.31-791.44) | 10.23 (2.55-15.63) | 0.64 (0.53-0.79) |
| 30 km | 488.00 (483.00-489.00) | 0.74 (0.67-0.82) | 0.91 (0.83-0.92) | 0.92 (0.78-0.96) | 0.90 (0.59-0.91) | 1.02 (0.96-1.39) | 0.91 (0.76-0.96) | 0.93 (0.70-0.95) | 2.50 (1.20-5.45) | 67.58 (39.32-269.46) | 3.14 (1.60-9.37) | 0.86 (0.69-0.92) |
| 60 km | 443.00 (434.00-453.00) | 0.74 (0.69-0.82) | 0.90 (0.84-0.94) | 0.89 (0.75-0.93) | 0.82 (0.54-0.86) | 1.09 (0.97-1.35) | 0.87 (0.73-0.94) | 0.89 (0.68-0.92) | 7.70 (5.12-13.78) | 127.97 (95.21-606.91) | 4.08 (2.36-10.55) | 0.83 (0.62-0.88) | 

### E5 per species, present Sorensen / 2100 Sorensen (mean of 3 seeds)

| label | broad | cold_limited | drought_limited | heat_limited | narrow | patchy | region_excluded |
|---|---|---|---|---|---|---|---|
| 120 km | 0.89 / 0.88 | 0.93 / 0.93 | 0.82 / 0.7 | 0.91 / 0.84 | 0.28 / 0.33 | 0.71 / 0.71 | 0.74 / 0.65 |
| 30 km | 0.96 / 0.96 | 0.93 / 0.93 | 0.93 / 0.94 | 0.98 / 0.96 | 0.63 / 0.64 | 0.77 / 0.77 | 0.79 / 0.7 |
| 60 km | 0.92 / 0.93 | 0.94 / 0.94 | 0.9 / 0.87 | 0.96 / 0.92 | 0.38 / 0.44 | 0.74 / 0.75 | 0.76 / 0.68 | 

### E6 trained on the cooler half only, projected everywhere (mean of 3 seeds)

| species | now_sorensen | now_area_ratio | 2-4_2050_sorensen | 5-8_2100_sorensen | 5-8_2100_novel_share | 5-8_2100_novel_err | 5-8_2100_other_err | 5-8_2100_shift_err_km |
|---|---|---|---|---|---|---|---|---|
| broad | 0.88 | 0.89 | 0.86 | 0.83 | 0.74 | 0.19 | 0.07 | 506.32 |
| cold_limited | 0.78 | 0.72 | 0.78 | 0.76 | 0.42 | 0.61 | 0.06 | 774.34 |
| drought_limited | 0.91 | 0.84 | 0.91 | 0.95 | 0.45 | 0.05 | 0.03 | 104.41 |
| heat_limited | 0.94 | 0.98 | 0.92 | 0.92 | 0.74 | 0.05 | 0.04 | 146.67 |
| narrow | 0.5 | 2.91 | 0.49 | 0.46 | 0.74 | 0.26 | 0.01 | 1586.43 |
| patchy | 0.72 | 1.66 | 0.7 | 0.66 | 0.74 | 0.48 | 0.31 | 664.65 |
| region_excluded | 0.73 | 1.59 | 0.68 | 0.59 | 0.74 | 0.51 | 0.38 | 871.11 | 

### E7 world 0.5 degree grid

| n_req | records | CV AUC | CV Boyce | present Sorensen | present TSS | area ratio | 2050 Sorensen | 2100 Sorensen | 2100 area-change error (pp) | 2100 centroid error (km) | bearing error (deg) | change-class agreement |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 100.00 (100.00-100.00) | 0.74 (0.68-0.82) | 0.80 (0.73-0.85) | 0.90 (0.78-0.97) | 0.92 (0.53-0.95) | 1.09 (0.97-1.42) | 0.91 (0.77-0.97) | 0.93 (0.77-0.95) | 3.08 (1.03-7.31) | 297.02 (208.10-598.47) | 6.46 (1.98-14.57) | 0.93 (0.71-0.94) |
| 500 | 498.00 (496.00-499.00) | 0.69 (0.60-0.80) | 0.86 (0.82-0.90) | 0.96 (0.79-0.98) | 0.96 (0.55-0.97) | 0.99 (0.98-1.34) | 0.96 (0.79-0.98) | 0.97 (0.80-0.97) | 2.43 (0.90-6.31) | 222.77 (57.44-287.87) | 2.15 (0.82-5.75) | 0.95 (0.73-0.96) | 

