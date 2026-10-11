# W3 fit report: gate table

Species fitted: 1. Tier A = static skill validated against an independent survey, Tier B = spatial-block CV skill only, Tier C = below a hard gate (not shown); 'shifts' = range-shift test pass/fail/untested. Change columns are the unlimited-dispersal area change for SSP2-4.5|2081-2100; 'withheld' means more than 15% novel climate.

| species | group | tier | shifts | CV kind | conf. | thinned cells | CV AUC | CV TSS | Boyce | check GAM AUC | range check | novel % | area now (1000 km2) | change % | shift km | reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Danaus chrysippus [breeding] | insect_arachnid | B | untested | presence_background | low | 646 | 0.68 | 0.24 | 0.70 | 0.69 | pass | 7 | 53435 | 5.7 | 103 | lower discrimination: CV AUC 0.68 < 0.7 |

Thresholds: 100 thinned records (per 0.125 degree cell), CV AUC 0.7 for standard confidence (Tier C below 0.5), novel climate 15%, native-range commission <= 0.30 (uncalibrated; omission is reported, not gated, against a native mask), at least 80% of records inside the predicted range. Dispersal rule and gate limits are listed in each summary.json.

## Area now and future, shift, novelty (unlimited dispersal; limited and none for 2081-2100)

| species | tier | scenario | period | area now (1000 km2) | area future (1000 km2) | change % | shift km | bearing | novel % | models agree % | change % limited | change % none |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Danaus chrysippus [breeding] | B | SSP2-4.5 | 2041-2060 | 53435 | 55536 | 3.9 | 61 | 34 | 3.9 | 98 | 3.9 | -0.8 |
| Danaus chrysippus [breeding] | B | SSP2-4.5 | 2081-2100 | 53435 | 56465 | 5.7 | 103 | 20 | 6.6 | 98 | 5.7 | -0.8 |
| Danaus chrysippus [breeding] | B | SSP5-8.5 | 2041-2060 | 53435 | 56252 | 5.3 | 93 | 22 | 5.4 | 98 | 5.2 | -0.8 |
| Danaus chrysippus [breeding] | B | SSP5-8.5 | 2081-2100 | 53435 | 58313 | 9.1 | 238 | 17 | 13.3 | 98 | 9.0 | -0.4 |

## Migratory birds and mixed seasons

The W2 cell table has years but no months, so breeding and non-breeding records are pooled. Pilot species where this matters (judgement, not measured):


A breeding-season restriction needs W2 to keep `month` (eventDate) in the cell aggregation, to write per-season record counts (for example May to July in the northern hemisphere, the reverse in the southern, none for tropical residents), to build target-group density grids for the same months, and the native mask for the breeding range only. Climate predictors would then need to be breeding-season variables or stay annual (a documented choice). Not done in this run.

## Crops

