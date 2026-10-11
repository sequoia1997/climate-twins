# W3 fit report: gate table

Species fitted: 20. Tier A = static skill validated against an independent survey, Tier B = spatial-block CV skill only, Tier C = below a hard gate (not shown); 'shifts' = range-shift test pass/fail/untested. Change columns are the unlimited-dispersal area change for SSP2-4.5|2081-2100; 'withheld' means more than 15% novel climate.

| species | group | tier | shifts | CV kind | conf. | thinned cells | CV AUC | CV TSS | Boyce | check GAM AUC | range check | novel % | area now (1000 km2) | change % | shift km | reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agelaius phoeniceus | bird | B | fail | presence_background | standard | 59047 | 0.71 | 0.28 | 0.94 | 0.68 | pass | 2 | 15224 | 20.2 | 235 |  |
| Agelaius phoeniceus | bird | B | fail | presence_background | standard | 54744 | 0.71 | 0.30 | 0.93 | 0.68 | pass | 1 | 14604 | 21.4 | 213 |  |
| Cardinalis cardinalis | bird | A | fail | presence_background | standard | 32541 | 0.75 | 0.37 | 0.91 | 0.70 | pass | 1 | 6352 | 38.1 | 311 |  |
| Cyanocitta cristata | bird | A | fail | presence_background | standard | 39382 | 0.75 | 0.39 | 0.93 | 0.71 | pass | 0 | 8662 | 30.0 | 416 |  |
| Cyanocitta cristata | bird | A | fail | presence_background | standard | 34317 | 0.77 | 0.40 | 0.91 | 0.73 | pass | 0 | 8202 | 31.1 | 423 |  |
| Danaus plexippus | insect_arachnid | B | untested | presence_background | standard | 3101 | 0.75 | 0.40 | 0.95 | 0.72 | pass | 2 | 13956 | 23.1 | 408 |  |
| Erithacus rubecula | bird | B | untested | presence_background | low | 33268 | 0.63 | 0.17 | 0.96 | 0.60 | pass | 6 | 9811 | 11.3 | 408 | lower discrimination: CV AUC 0.63 < 0.7 |
| Hirundo rustica | bird | B | fail | presence_background | low | 143827 | 0.60 | 0.15 | 0.76 | 0.56 | pass | 4 | 88725 | 7.3 | 378 | lower discrimination: CV AUC 0.60 < 0.7 |
| Hirundo rustica | bird | B | fail | presence_background | low | 106514 | 0.64 | 0.21 | 0.91 | 0.62 | pass | 0 | 48251 | 6.2 | 369 | lower discrimination: CV AUC 0.64 < 0.7 |
| Melospiza melodia | bird | B | fail | presence_background | standard | 53773 | 0.72 | 0.31 | 0.93 | 0.70 | pass | 0 | 13802 | 16.4 | 336 |  |
| Melospiza melodia | bird | A | fail | presence_background | standard | 41212 | 0.78 | 0.40 | 0.93 | 0.76 | pass | 0 | 12034 | 10.3 | 428 |  |
| Sialia sialis | bird | A | fail | presence_background | standard | 31913 | 0.76 | 0.39 | 0.96 | 0.71 | pass | 0 | 7070 | 32.8 | 485 |  |
| Sialia sialis | bird | A | fail | presence_background | standard | 27548 | 0.75 | 0.40 | 0.94 | 0.71 | pass | 0 | 6513 | 33.2 | 476 |  |
| Spinus tristis | bird | B | fail | presence_background | standard | 48668 | 0.70 | 0.28 | 0.92 | 0.67 | pass | 0 | 11513 | 21.1 | 373 |  |
| Spinus tristis | bird | A | fail | presence_background | standard | 39884 | 0.74 | 0.36 | 0.88 | 0.72 | pass | 0 | 10319 | 18.4 | 459 |  |
| Thryothorus ludovicianus | bird | A | fail | presence_background | low | 22470 | 0.79 | 0.42 | 0.92 | 0.78 | pass | 0 | 3904 | 26.0 | 225 | transparent check model disagrees on area change by up to 29 points |
| Turdus migratorius | bird | A | fail | presence_background | standard | 68291 | 0.73 | 0.31 | 0.62 | 0.71 | pass | 0 | 17569 | 9.7 | 228 |  |
| Turdus migratorius | bird | A | fail | presence_background | standard | 59804 | 0.75 | 0.34 | 0.67 | 0.74 | pass | 0 | 17863 | 3.6 | 291 |  |
| Zenaida macroura | bird | B | fail | presence_background | low | 61235 | 0.69 | 0.25 | 0.88 | 0.66 | pass | 2 | 13583 | 23.7 | 320 | lower discrimination: CV AUC 0.69 < 0.7 |
| Zenaida macroura | bird | B | fail | presence_background | low | 55478 | 0.70 | 0.28 | 0.93 | 0.67 | pass | 0 | 12144 | 24.1 | 371 | lower discrimination: CV AUC 0.70 < 0.7 |

Thresholds: 100 thinned records (per 0.125 degree cell), CV AUC 0.7 for standard confidence (Tier C below 0.5), novel climate 15%, native-range commission <= 0.30 (uncalibrated; omission is reported, not gated, against a native mask), at least 80% of records inside the predicted range. Dispersal rule and gate limits are listed in each summary.json.

## Area now and future, shift, novelty (unlimited dispersal; limited and none for 2081-2100)

| species | tier | scenario | period | area now (1000 km2) | area future (1000 km2) | change % | shift km | bearing | novel % | models agree % | change % limited | change % none |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agelaius phoeniceus | B | SSP2-4.5 | 2041-2060 | 15224 | 17210 | 13.0 | 136 | 8 | 1.3 | 97 | 13.0 | -0.4 |
| Agelaius phoeniceus | B | SSP2-4.5 | 2081-2100 | 15224 | 18298 | 20.2 | 235 | 8 | 2.0 | 97 | 20.1 | -0.5 |
| Agelaius phoeniceus | B | SSP5-8.5 | 2041-2060 | 15224 | 17844 | 17.2 | 182 | 13 | 1.8 | 96 | 17.1 | -0.5 |
| Agelaius phoeniceus | B | SSP5-8.5 | 2081-2100 | 15224 | 20785 | 36.5 | 353 | 12 | 5.2 | 95 | 35.9 | -0.8 |
| Agelaius phoeniceus | B | SSP2-4.5 | 2041-2060 | 14604 | 16547 | 13.3 | 124 | 2 | 0.6 | 97 | 13.3 | -0.2 |
| Agelaius phoeniceus | B | SSP2-4.5 | 2081-2100 | 14604 | 17733 | 21.4 | 213 | 4 | 1.1 | 97 | 21.4 | -0.2 |
| Agelaius phoeniceus | B | SSP5-8.5 | 2041-2060 | 14604 | 17199 | 17.8 | 174 | 6 | 0.9 | 97 | 17.7 | -0.2 |
| Agelaius phoeniceus | B | SSP5-8.5 | 2081-2100 | 14604 | 20037 | 37.2 | 324 | 9 | 3.8 | 95 | 36.6 | -0.4 |
| Cardinalis cardinalis | A | SSP2-4.5 | 2041-2060 | 6352 | 7736 | 21.8 | 158 | 345 | 0.1 | 94 | 21.7 | -0.3 |
| Cardinalis cardinalis | A | SSP2-4.5 | 2081-2100 | 6352 | 8771 | 38.1 | 311 | 342 | 0.7 | 93 | 37.8 | -0.3 |
| Cardinalis cardinalis | A | SSP5-8.5 | 2041-2060 | 6352 | 8193 | 29.0 | 218 | 343 | 0.4 | 94 | 28.4 | -0.3 |
| Cardinalis cardinalis | A | SSP5-8.5 | 2081-2100 | 6352 | 11890 | 87.2 | 696 | 342 | 3.9 | 90 | 81.6 | -0.1 |
| Cyanocitta cristata | A | SSP2-4.5 | 2041-2060 | 8662 | 10309 | 19.0 | 248 | 343 | 0.0 | 95 | 19.0 | -1.5 |
| Cyanocitta cristata | A | SSP2-4.5 | 2081-2100 | 8662 | 11257 | 30.0 | 416 | 344 | 0.0 | 95 | 30.0 | -2.6 |
| Cyanocitta cristata | A | SSP5-8.5 | 2041-2060 | 8662 | 10804 | 24.7 | 343 | 345 | 0.0 | 94 | 24.6 | -2.5 |
| Cyanocitta cristata | A | SSP5-8.5 | 2081-2100 | 8662 | 13122 | 51.5 | 703 | 346 | 0.0 | 94 | 49.8 | -5.5 |
| Cyanocitta cristata | A | SSP2-4.5 | 2041-2060 | 8202 | 9822 | 19.7 | 260 | 341 | 0.0 | 95 | 19.7 | -1.7 |
| Cyanocitta cristata | A | SSP2-4.5 | 2081-2100 | 8202 | 10749 | 31.1 | 423 | 343 | 0.0 | 94 | 31.0 | -2.6 |
| Cyanocitta cristata | A | SSP5-8.5 | 2041-2060 | 8202 | 10281 | 25.3 | 347 | 344 | 0.0 | 94 | 25.2 | -2.6 |
| Cyanocitta cristata | A | SSP5-8.5 | 2081-2100 | 8202 | 12395 | 51.1 | 695 | 345 | 0.0 | 93 | 49.9 | -5.2 |
| Danaus plexippus | B | SSP2-4.5 | 2041-2060 | 13956 | 16010 | 14.7 | 248 | 6 | 1.2 | 94 | 13.8 | -2.5 |
| Danaus plexippus | B | SSP2-4.5 | 2081-2100 | 13956 | 17184 | 23.1 | 408 | 7 | 2.2 | 94 | 23.0 | -3.3 |
| Danaus plexippus | B | SSP5-8.5 | 2041-2060 | 13956 | 16719 | 19.8 | 330 | 8 | 2.1 | 93 | 17.7 | -3.2 |
| Danaus plexippus | B | SSP5-8.5 | 2081-2100 | 13956 | 19555 | 40.1 | 716 | 357 | 3.2 | 94 | 37.4 | -5.7 |
| Erithacus rubecula | B | SSP2-4.5 | 2041-2060 | 9811 | 10526 | 7.3 | 258 | 34 | 6.4 | 94 | 7.3 | -5.5 |
| Erithacus rubecula | B | SSP2-4.5 | 2081-2100 | 9811 | 10921 | 11.3 | 408 | 34 | 6.0 | 94 | 11.3 | -8.5 |
| Erithacus rubecula | B | SSP5-8.5 | 2041-2060 | 9811 | 10461 | 6.6 | 313 | 29 | 6.3 | 94 | 6.6 | -7.6 |
| Erithacus rubecula | B | SSP5-8.5 | 2081-2100 | 9811 | 10158 | 3.5 | 695 | 24 | 5.6 | 90 | 3.2 | -21.2 |
| Hirundo rustica | B | SSP2-4.5 | 2041-2060 | 88725 | 92891 | 4.7 | 232 | 4 | 1.8 | 98 | 4.7 | -2.3 |
| Hirundo rustica | B | SSP2-4.5 | 2081-2100 | 88725 | 95160 | 7.3 | 378 | 3 | 4.2 | 98 | 7.3 | -3.1 |
| Hirundo rustica | B | SSP5-8.5 | 2041-2060 | 88725 | 94140 | 6.1 | 313 | 3 | 3.3 | 98 | 6.1 | -2.9 |
| Hirundo rustica | B | SSP5-8.5 | 2081-2100 | 88725 | 100493 | 13.3 | 680 | 10 | 13.7 | 96 | 13.1 | -5.1 |
| Hirundo rustica | B | SSP2-4.5 | 2041-2060 | 48251 | 50130 | 3.9 | 253 | 29 | 0.0 | 96 | 3.9 | -6.1 |
| Hirundo rustica | B | SSP2-4.5 | 2081-2100 | 48251 | 51261 | 6.2 | 369 | 28 | 0.0 | 95 | 6.2 | -8.7 |
| Hirundo rustica | B | SSP5-8.5 | 2041-2060 | 48251 | 50723 | 5.1 | 315 | 31 | 0.0 | 95 | 5.1 | -7.5 |
| Hirundo rustica | B | SSP5-8.5 | 2081-2100 | 48251 | 52937 | 9.7 | 636 | 37 | 0.7 | 92 | 9.5 | -16.3 |
| Melospiza melodia | B | SSP2-4.5 | 2041-2060 | 13802 | 15139 | 9.7 | 204 | 352 | 0.0 | 97 | 9.7 | -1.8 |
| Melospiza melodia | B | SSP2-4.5 | 2081-2100 | 13802 | 16066 | 16.4 | 336 | 357 | 0.0 | 97 | 16.4 | -2.5 |
| Melospiza melodia | B | SSP5-8.5 | 2041-2060 | 13802 | 15589 | 12.9 | 267 | 356 | 0.0 | 97 | 12.9 | -2.2 |
| Melospiza melodia | B | SSP5-8.5 | 2081-2100 | 13802 | 16973 | 23.0 | 637 | 353 | 0.0 | 95 | 22.9 | -7.8 |
| Melospiza melodia | A | SSP2-4.5 | 2041-2060 | 12034 | 12725 | 5.7 | 278 | 348 | 0.1 | 96 | 5.7 | -6.2 |
| Melospiza melodia | A | SSP2-4.5 | 2081-2100 | 12034 | 13276 | 10.3 | 428 | 353 | 0.1 | 96 | 10.3 | -9.3 |
| Melospiza melodia | A | SSP5-8.5 | 2041-2060 | 12034 | 12967 | 7.8 | 354 | 352 | 0.1 | 97 | 7.8 | -7.9 |
| Melospiza melodia | A | SSP5-8.5 | 2081-2100 | 12034 | 13526 | 12.4 | 779 | 351 | 0.1 | 94 | 12.4 | -19.5 |
| Sialia sialis | A | SSP2-4.5 | 2041-2060 | 7070 | 8607 | 21.7 | 320 | 344 | 0.0 | 94 | 21.7 | -2.8 |
| Sialia sialis | A | SSP2-4.5 | 2081-2100 | 7070 | 9386 | 32.8 | 485 | 346 | 0.0 | 94 | 32.8 | -3.8 |
| Sialia sialis | A | SSP5-8.5 | 2041-2060 | 7070 | 8931 | 26.3 | 396 | 346 | 0.0 | 94 | 26.3 | -3.5 |
| Sialia sialis | A | SSP5-8.5 | 2081-2100 | 7070 | 10954 | 54.9 | 818 | 344 | 0.0 | 92 | 54.6 | -7.2 |
| Sialia sialis | A | SSP2-4.5 | 2041-2060 | 6513 | 7990 | 22.7 | 316 | 343 | 0.0 | 94 | 22.7 | -2.5 |
| Sialia sialis | A | SSP2-4.5 | 2081-2100 | 6513 | 8677 | 33.2 | 476 | 347 | 0.0 | 93 | 33.2 | -4.2 |
| Sialia sialis | A | SSP5-8.5 | 2041-2060 | 6513 | 8261 | 26.8 | 390 | 347 | 0.0 | 93 | 26.8 | -3.9 |
| Sialia sialis | A | SSP5-8.5 | 2081-2100 | 6513 | 9678 | 48.6 | 814 | 349 | 0.0 | 91 | 48.2 | -11.1 |
| Spinus tristis | B | SSP2-4.5 | 2041-2060 | 11513 | 13056 | 13.4 | 229 | 355 | 0.0 | 97 | 13.4 | -1.7 |
| Spinus tristis | B | SSP2-4.5 | 2081-2100 | 11513 | 13940 | 21.1 | 373 | 355 | 0.0 | 97 | 21.1 | -3.0 |
| Spinus tristis | B | SSP5-8.5 | 2041-2060 | 11513 | 13585 | 18.0 | 314 | 355 | 0.0 | 97 | 17.9 | -2.4 |
| Spinus tristis | B | SSP5-8.5 | 2081-2100 | 11513 | 15756 | 36.8 | 743 | 354 | 0.0 | 95 | 35.3 | -8.0 |
| Spinus tristis | A | SSP2-4.5 | 2041-2060 | 10319 | 11479 | 11.2 | 287 | 351 | 0.0 | 97 | 11.2 | -5.5 |
| Spinus tristis | A | SSP2-4.5 | 2081-2100 | 10319 | 12214 | 18.4 | 459 | 350 | 0.0 | 96 | 18.4 | -8.5 |
| Spinus tristis | A | SSP5-8.5 | 2041-2060 | 10319 | 11942 | 15.7 | 385 | 351 | 0.0 | 96 | 15.6 | -7.0 |
| Spinus tristis | A | SSP5-8.5 | 2081-2100 | 10319 | 13762 | 33.4 | 852 | 350 | 0.0 | 95 | 31.9 | -16.0 |
| Thryothorus ludovicianus | A | SSP2-4.5 | 2041-2060 | 3904 | 4500 | 15.3 | 154 | 32 | 0.0 | 95 | 15.3 | -1.5 |
| Thryothorus ludovicianus | A | SSP2-4.5 | 2081-2100 | 3904 | 4919 | 26.0 | 225 | 26 | 0.5 | 94 | 26.0 | -1.4 |
| Thryothorus ludovicianus | A | SSP5-8.5 | 2041-2060 | 3904 | 4735 | 21.3 | 179 | 30 | 0.3 | 95 | 21.3 | -1.0 |
| Thryothorus ludovicianus | A | SSP5-8.5 | 2081-2100 | 3904 | 5743 | 47.1 | 428 | 16 | 3.2 | 91 | 46.9 | -2.5 |
| Turdus migratorius | A | SSP2-4.5 | 2041-2060 | 17569 | 18573 | 5.7 | 128 | 6 | 0.0 | 99 | 5.7 | -1.2 |
| Turdus migratorius | A | SSP2-4.5 | 2081-2100 | 17569 | 19278 | 9.7 | 228 | 8 | 0.0 | 97 | 9.7 | -1.7 |
| Turdus migratorius | A | SSP5-8.5 | 2041-2060 | 17569 | 18870 | 7.4 | 168 | 7 | 0.0 | 98 | 7.4 | -1.4 |
| Turdus migratorius | A | SSP5-8.5 | 2081-2100 | 17569 | 19501 | 11.0 | 423 | 8 | 0.0 | 97 | 11.0 | -5.4 |
| Turdus migratorius | A | SSP2-4.5 | 2041-2060 | 17863 | 18387 | 2.9 | 199 | 7 | 0.0 | 98 | 2.9 | -3.8 |
| Turdus migratorius | A | SSP2-4.5 | 2081-2100 | 17863 | 18507 | 3.6 | 291 | 6 | 0.0 | 98 | 3.6 | -5.4 |
| Turdus migratorius | A | SSP5-8.5 | 2041-2060 | 17863 | 18401 | 3.0 | 243 | 6 | 0.0 | 99 | 3.0 | -4.7 |
| Turdus migratorius | A | SSP5-8.5 | 2081-2100 | 17863 | 18121 | 1.4 | 447 | 4 | 0.0 | 98 | 1.4 | -9.7 |
| Zenaida macroura | B | SSP2-4.5 | 2041-2060 | 13583 | 15645 | 15.2 | 189 | 3 | 1.2 | 97 | 15.2 | -0.5 |
| Zenaida macroura | B | SSP2-4.5 | 2081-2100 | 13583 | 16801 | 23.7 | 320 | 359 | 2.1 | 97 | 23.7 | -0.4 |
| Zenaida macroura | B | SSP5-8.5 | 2041-2060 | 13583 | 16346 | 20.3 | 248 | 2 | 2.0 | 97 | 20.3 | -0.4 |
| Zenaida macroura | B | SSP5-8.5 | 2081-2100 | 13583 | 19701 | 45.0 | 500 | 7 | 7.0 | 96 | 45.0 | -0.5 |
| Zenaida macroura | B | SSP2-4.5 | 2041-2060 | 12144 | 14007 | 15.3 | 229 | 359 | 0.0 | 97 | 15.3 | -1.1 |
| Zenaida macroura | B | SSP2-4.5 | 2081-2100 | 12144 | 15073 | 24.1 | 371 | 356 | 0.1 | 97 | 24.0 | -1.2 |
| Zenaida macroura | B | SSP5-8.5 | 2041-2060 | 12144 | 14567 | 20.0 | 316 | 356 | 0.1 | 97 | 19.8 | -1.3 |
| Zenaida macroura | B | SSP5-8.5 | 2081-2100 | 12144 | 17359 | 42.9 | 664 | 355 | 0.5 | 97 | 42.8 | -1.9 |

## Migratory birds and mixed seasons

The W2 cell table has years but no months, so breeding and non-breeding records are pooled. Pilot species where this matters (judgement, not measured):

- Agelaius phoeniceus: partial migrant, large winter flocks in the south
- Cyanocitta cristata: partial migrant (irregular)
- Hirundo rustica: long-distance migrant: breeds in the north, winters in Africa, South America and southern Asia; the curated native list has no South America
- Melospiza melodia: partial migrant (northern populations)
- Sialia sialis: partial migrant
- Spinus tristis: nomadic partial migrant, winter range far south of the breeding range
- Turdus migratorius: partial migrant: northern breeders winter in the southern US and Mexico, so winter records extend the range south
- Zenaida macroura: partial migrant, northern birds winter in the south

A breeding-season restriction needs W2 to keep `month` (eventDate) in the cell aggregation, to write per-season record counts (for example May to July in the northern hemisphere, the reverse in the southern, none for tropical residents), to build target-group density grids for the same months, and the native mask for the breeding range only. Climate predictors would then need to be breeding-season variables or stay annual (a documented choice). Not done in this run.

## Crops

