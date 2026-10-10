# Spike F: SDM engine tested on virtual species

Status: PARTIAL, updated as experiments finish (E1 records and E6 novelty done; E2-E5, E7 running). Unit tests: 13 pass in about 6 s.
Code: `ctw/species/sdm.py`, `virtual.py`; tests `tests/test_species_sdm.py`; runner `docs/spikes/F-experiments.py`; analysis `docs/spikes/F-analysis.py`; raw results `docs/spikes/data/F/*.csv`.
The first attempt's E1 and E6 result files were recovered and are used as is; the rest were re-run.

## Setup (what was built)
- Seven virtual species on the shipped 15 km North America grid (real baseline climate; future = same ensemble deltas, SSP2-4.5 2050 and SSP5-8.5 2100): broad, narrow, cold_limited, drought_limited, heat_limited, region_excluded (absent from western 35%, non-climatic), patchy (30% of 150 km blocks unsuitable, non-climatic).
- True suitability is a product of Gaussian / logistic response curves on 2 drivers; "present" is a threshold on it. Records: probability proportional to suitability times sampling effort (a population-weighted surface, a stand-in for road/city bias), 3% false positives, 10% coordinate jitter, thinned to one per cell.
- Pipeline: ensemble of GAM, Maxent-like (L1 logistic with hinge features), LightGBM and random forest (GLM and Mahalanobis niche also available), target-group background (10 000 cells), spatial-block CV (400 km, 5 folds), p05 threshold, MESS plus Mahalanobis novelty flags, dispersal-bounded projection, area / centroid / bearing / gain-loss summaries.
- Scored against truth: Sorensen overlap of predicted vs true range, TSS, area ratio, error in % area change, centroid error (km) and bearing error, agreement of the gain/loss/stable class.
- Caveat on the climate: the future grids are baseline plus deltas interpolated from a few hundred places, so spatial detail of change is smoother than in a real GCM; the truth uses the identical climate, so the test measures the statistical engine, not climate-model error.

## Results so far
### E1 by number of records (median and quartiles over 6 species x 3 seeds)

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

### gate analysis: 84 runs with default settings

| gate | published | unacceptable among published | median 2100 Sorensen | 90th pct |area-change error| pp |
|---|---|---|---|---|
| no gate | 100% | 37% | 0.92 | 12 |
| n >= 50 | 99% | 36% | 0.92 | 13 |
| n >= 100 | 74% | 32% | 0.94 | 5 |
| CV AUC >= 0.7 | 61% | 20% | 0.94 | 15 |
| CV AUC >= 0.75 | 57% | 15% | 0.95 | 17 |
| CV Boyce >= 0.6 | 79% | 32% | 0.94 | 7 |
| CV Boyce >= 0.7 | 75% | 30% | 0.94 | 7 |
| CV Boyce >= 0.8 | 43% | 31% | 0.94 | 5 |
| n >= 100 & Boyce >= 0.7 | 61% | 31% | 0.94 | 5 |
| n >= 100 & Boyce >= 0.7 & AUC >= 0.6 | 60% | 32% | 0.95 | 5 |
| n >= 100 & Boyce >= 0.7 & novel <= 15% | 61% | 31% | 0.94 | 5 | 

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

