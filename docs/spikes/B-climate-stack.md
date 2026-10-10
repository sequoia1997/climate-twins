# Spike B: global high-resolution climate predictor stack

Status: COMPLETE for Tier A numbers (2026-10-10). Tags: [V: run/job] verified from a logged Actions run; [U] unverified.
Runs referenced (all branch claude/eloquent-ritchie-r7jjby, 2026-10-06): probe 37524881904 (job 112479246196), probe 2 37524882136 (112479247383), probe 3 37525967067 (112482929526), terrain 37526243706 (112483860084), Tier A 37528509108 (112491548144, sha 5d04674).

## Recommendation: GO-WITH-CHANGES
Build Tier A (2.5', TerraClimate 1991-2020 native + NEX change factors) as the main global stack. Changes required: (a) read the globe per variable in latitude bands (naive global read peaked at 7.9 GB RSS); (b) use TerraClimate's own def and aet for the baseline, our water balance only for future deltas; (c) fix the roadmap's cell counts (12.5 M land cells at 2.5', about 313 M at 30", not 6 M / 150 M); (d) treat 1 km (CHELSA, tiles of 10x10 degrees) as a later regional sensitivity tier with the TerraClimate bridge below; (e) precipitation and bio15/bio17 future change from NEX ratios differ from WorldClim's, so report as uncertainty. Reruns: Tier A rerun after fixes, run 38055514572 (job 114223029119, sha ccbd04d), succeeded; it supplies sections 3b and 4.

## 1. Tier A feasibility (test region lat 40-60, lon 0-20, 480x480 cells = 230,400 cells, 152,100 land)
- TerraClimate yearly files on climate.northwestknowledge.net: HTTP range GET works; one variable-year is 0.04-0.17 GB; 14 variables x 1 year = 1.55 GB [V: probe 112479246196]. Layout int16, shape (12,4320,8640) = 2.5 arc-minute (1/24 deg), chunks (2,1080,2160), gzip, scale 0.01 [V: probe2 112479247383]. Full-file GET 33 MB/s; 1-2 MB range GET 1.1 MB/s-ish [V: probe].
- Native regional read incl. water balance: 333 files (tmax,tmin,ppt,def,aet,soil,pet,vpd,srad for 1991-2020 plus tmax/tmin/ppt 1970-1990) in 687 s with 4 processes; 8.1 s mean, 28.7 s max per file; peak RSS 823 MB [V: Tier A tc stage]. (TC.VARS is the 9-variable set.)
- Output sizes: 9 vars x 12 months float32 = 99.5 MB for the region; npz compressed 44.7 MB; int16 land-only 32.9 MB [V]. 11 predictor layers: 5.4 MB npz [V].
- Predictor computation: 10.2 s for 230,400 cells (about 44 us/cell; global 37.3M cells approx 27 min single core, extrapolated [U]).
- Single global file read (tmax 2019): 15.3 s but 7.9 GB peak RSS; i.e. a naive whole-globe read exceeds the 7 GB runner. Must read in latitude bands or per variable with int16 [V: tc_global_one_file_tmax].
- Global land cells at 2.5': 12,532,612 of 37,324,800 (33.6%); land area 149.2 million km2 [V: probe2]. The roadmap's "about 6 million" is wrong by 2x.
- Global estimate [U, extrapolated]: about 270 yearly files (9 vars x 30 y) = about 30 GB transferred, at 33 MB/s about 15-30 min transfer, in practice 1-2 h with decode; fits one 6 h job if processed one variable at a time (1.8 GB float32 accumulator per variable) and written as int16 land-only (3.0 GB for 9 vars x 12 months at 12.5M land cells).

## 2. Predictors (ctw/species/climategrid.py)
Bioclim bio1/4/5/6/12/15/17, GDD5 (sine method on monthly-to-daily interpolation, calibrated against NEX daily in commit 8cf91e3), frost days (Gaussian proxy), CWD and AET from an own bucket water balance. Region means (p5-p95) [V: Tier A]: bio1 9.8 (5.5-14.9) C, bio12 822 mm, gdd5 2299, frost days 82, cwd 200 mm, aet 533 mm.
Method errors vs TerraClimate's own def/aet [V: wb_check, region 40-60N 0-20E]:
| capacity | CWD bias mm | CWD RMSE | CWD r | AET bias | AET r |
| max monthly TC soil | -51 | 54 | 0.993 | +51 | 0.990 |
| 100 mm | -55 | 60 | 0.985 | +55 | 0.958 |
| 150 mm | -73 | 79 | 0.980 | +73 | 0.951 |
Own water balance underestimates deficit by about 25% (mean 200 mm) with high rank correlation. Recommendation: use TerraClimate's own def and aet directly for the baseline (they are native); use the own balance only for futures, bias-corrected by the baseline offset (our baseline minus TC baseline), or as ratios.
Frost-day and GDD error quoted in the unit-test file; see tests/test_species_climategrid.py.

## 3. Future predictors (NEX change factors on the fine grid)
Method (code: coarse_changes, regrid_bilinear, apply_changes, future_predictors): from the repo's NEX-GDDP ACCESS-CM2 monthly file for the box (docs/spikes/data/B_nex_ACCESS-CM2.npz): temperature as additive deltas, precipitation as log-ratios with a dry-month guard (0.5 mm) and ratio clamp 0.2-5, bilinear interpolation from 0.25 deg to 2.5' (no wrap, nearest fill at coasts), applied to TerraClimate 1991-2020 monthly fields; PET carried by Hargreaves future/baseline ratio clipped 0.5-3 on TC's PET; CWD/AET from the own water balance. Runtime 11-12 s per scenario for 230,400 cells [V: 38055514572]. First run crashed (pandas missing), fixed.
Comparison with WorldClim 2.1 ACCESS-CM2 (same model, 2.5' native, [V: 38055514572]), absolute predictors on land cells, ours minus WorldClim:
| | ssp245 2041-60 bias / RMSE / r | ssp585 2081-2100 bias / RMSE / r |
| bio1 C | +0.38 / 0.41 / 0.998 | +0.11 / 0.22 / 0.998 |
| bio5 C | +0.27 / 0.48 / 0.995 | -0.41 / 0.57 / 0.995 |
| bio6 C | +0.60 / 0.89 / 0.975 | +0.08 / 0.95 / 0.93 |
| bio12 mm | -1.8 / 57 / 0.986 | -4.7 / 65 / 0.985 |
| bio15 | +5.7 / 8.4 / 0.76 | +8.4 / 12.7 / 0.67 |
| bio17 mm | -12.7 / 23 / 0.94 | -14.7 / 28 / 0.90 |
| gdd5 | +98 / 114 / 0.998 | +31 / 69 / 0.998 |
| frost days | -6.1 / 9.1 / 0.99 | -1.4 / 4.9 / 0.98 |
Precipitation as ratios: mean bio12 ratio future/base ours 1.023 vs WorldClim 1.032 (245); 0.963 vs 0.978 (585). Our own CWD rises from 200 to 266 mm (245) and 427 mm (585); AET 533 to 543 / 506. CWD/AET have no WorldClim counterpart, so they are unvalidated against an independent future product [V values, U interpretation].
Caution: "change" (future minus each product's own baseline) differs by about -0.5 C bio1 because WorldClim's baseline is 1970-2000 and ours is 1991-2020; absolute values agree better and are the right comparison. bio15/bio17 (seasonality) agree poorly (r 0.67-0.94): monthly ratio fields are smooth at 25 km; do not use them as sharp predictors without a sensitivity run. One GCM and the AdaptWest comparison were not done (AdaptWest not tested here; [U]).

## 4. 1 km options (from Actions)
WorldClim 2.1 [V: probe]: base 1970-2000 zips: 30s tmax 4.38 GB, tmin 4.39 GB, prec 1.03 GB, bio 10.4 GB; 2.5m tmax 0.44, tmin 0.45, prec 0.07, bio 0.66 GB. CMIP6 future: 26 models (list in log), SSP 126/245/370/585 (FIO-ESM-2-0 and HadGEM3-GC31-LL lack 370; GFDL-ESM4 lacks 245), periods 2021-40, 41-60, 61-80, 81-2100, variables tmin/tmax/prec/bioc. One 30s future file: tmax 5.1 GB, prec 22.4 GB, bioc 9.1 GB (all 12 months in one multiband tif); 2.5m tmax 255 MB, prec 130 MB, bioc 456 MB. Throughput 3.7 MB/s on the 2.5m base zip (geodata.ucdavis.edu, slow). GDAL /vsicurl range read of a 30s future tif: 1-degree window 20 s, 20x20 degree window 334 s (poor: LZW stripes of full-width rows) [V: probe2]; the 2.5m file 20x20 window 19 s. Licence: WorldClim terms are non-commercial/attribution [U, check site].
CHELSA v2.1 [V: probe3, probe2]: host https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/ (S3 listing works); the old chelsa-climate.org/envicloud paths 404. climatologies/{tas,tasmax,tasmin,pr,rsds,hurs,sfcWind,vpd,pet,cmi,clt}/<period>/ and bioclim/bio01..19 etc. Baseline 1981-2010 has 12 monthly files per variable (tasmax 0.15 GB each, pr 0.35 GB, pet 0.40 GB). Futures 2011-2040, 2041-2070, 2071-2100: only 5 models (GFDL-ESM4, IPSL-CM6A-LR, MPI-ESM1-2-HR, MRI-ESM2-0, UKESM1-0-LL; ISIMIP3b set) x ssp126/370/585. Totals listed: tasmax 93 GB, pr 204 GB, tas 91 GB. Cloud-optimised: 512x512 tiles, a 20x20 degree (2400x2400) window reads in 0.9 s [V: probe2]: far better than WorldClim for tiling. Licence CC BY 4.0 [U].

### Baseline period mismatch (Tier A run, region 40-60N 0-20E, 2.5')
WorldClim 1970-2000 vs TerraClimate 1991-2020 [V: Tier A compare]: bio1 -0.87 C, bio5 -1.11, bio6 -0.72, bio12 -3.9 mm (MAE 24.5), gdd5 -222 degree-days, frost days +12.7. The same WorldClim vs TerraClimate computed for 1970-2000 agrees closely [V]: bio1 -0.04 C, bio12 -2 mm, gdd5 -8.5, r >= 0.997: so the two datasets are mutually consistent at 2.5' and the difference is the period (climate change), not the product.
CHELSA v2.1 1981-2010 (30" averaged to 2.5') vs TerraClimate 1991-2020, corrected-window rerun [V: 38055514572]: bio1 bias -0.73 C (r 0.978, RMSE 1.0), bio5 -1.58, bio6 -0.72, bio12 +119 mm (r 0.87, RMSE 249; CHELSA is much wetter, probably mountain precipitation correction), bio17 +27 mm, gdd5 -160 (r 0.985), frost days +8.8. Against TerraClimate for the SAME 1981-2010 period: bio1 -0.26, bio5 -1.07, bio6 -0.15, bio12 +123 mm, gdd5 -52, fd +0.7. So of CHELSA's -0.73 C offset, about 0.47 C is the period, the rest product difference; precipitation difference is a product difference and is not removed by period bridging. (An earlier run gave r=0.37: a window bug, fixed in ccbd04d.)
Within-2.5'-cell spread seen at 30" (CHELSA) [V]: bio1 mean range 1.0 C (p95 4.8, p99 7.8), bio5 1.2 C, bio12 mean range 85 mm (p95 337), gdd5 226 (p95 902), frost days 15 (p95 74). Meaning: Tier A smooths away typical 1 C but up to 5-8 C inside a cell in mountains.
Bridge proposal: fine = CHELSA(1981-2010) + [TC(1991-2020) - TC(1981-2010)] (deltas for temperature, ratios for precipitation, at 2.5' bilinear), for precipitation use CHELSA x [TC1991-2020/TC1981-2010] ratio; validated only by construction (the rerun shows the period term is +0.47 C, so correcting to TC removes about a third to two thirds of the offset; the remaining offset is product difference, so also consider rescaling to TC at 2.5' per tile). Correction size (TC 1991-2020 minus 1981-2010) [V]: bio1 +0.47 C (p5-p95 0.35-0.64), bio5 +0.50, bio6 +0.57, gdd5 +108, frost -8 days.

## 5. Terrain and soil [V: terrain run 112483860084]
Copernicus DEM on AWS (copernicus-dem-90m / 30m public S3 buckets, COG, 1 degree tiles, no auth): 4 tiles 90 m (2400x2400 total, 0.000833 deg) read in 7.4 s; averaged to 2.5' 7.6 s; within-2.5' elevation range mean 984 m, p95 1882 m in the Alps test box. Single 1-degree tile sizes: 5.2 MB (90 m), 41.8 MB (30 m).
SoilGrids 2.0 via https://files.isric.org/soilgrids/latest/data/<var>/<var>_<depth>_mean.vrt (Goode homolosine, 250 m, int16, shape 58034x159246): open 5-9 s, 2.5' average of the test box 7-9 s per layer (phh2o, clay, soc). Pre-aggregated data_aggregated/ 1000m and 5000m files exist (phh2o 1 km 79 MB) but the aggregated listing URL used in the terrain run returned 404 [V]. Licence CC BY 4.0 [U].

## 6. Global cell counts and storage
2.5': 37,324,800 grid, 12,532,612 land (V). int16 layer, land only: 25.1 MB; 11 predictors 276 MB; per future scenario/period/model 276 MB (ensemble mean + spread: about 0.8 GB).
30": 933.1 M grid cells; land by the same fraction (33.6%) about 313 M cells (area-weighted figure is smaller but grid count is what is stored) [U, derived]. int16 layer 627 MB; 11 predictors 6.9 GB. The roadmap's "150 million" is low by 2x.
Tiling plan: 20x20 degree tiles (162 tiles of 480x480 at 2.5'; 2400x2400 at 30"), ocean tiles skipped; one job per band of tiles; peak RSS for 480x480 region 0.8 GB, 2400x2400 CHELSA read RSS 7.5 GB with 36 files in memory: too high, use 10x10 degree tiles at 30" [V: chelsa_read rss 7537 MB].

## 7. Risks
- Memory on whole-globe read (7.9 GB measured). - WorldClim slowness (3.7 MB/s) and 30s window reads. - CHELSA only 5 GCMs. - Own water balance biased -25% CWD. - Period mismatch ~0.5-0.9 C and ~110-220 GDD. - UNVERIFIED: licence texts, global run time, AdaptWest comparison, SoilGrids aggregated URL path. Tier A rerun peak RSS 10 GB in the compare stage (above the 7 GB nominal runner; it passed, but a 30" run must be tiled).
