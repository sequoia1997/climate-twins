# W1: global climate predictor stack (species pilot)

Status log (newest last). Tags: [V: ...] verified by a command or Actions run named; [U] unverified.

- 2026-10-10 17:50 UTC: code written and tested on a 100 x 100 cell window with real TerraClimate data [V: local run, 14 var-years in 93 s]
  and on NEX-GDDP for one model [V: local run in progress]. Release `species-pilot-data` is created by the first workflow run (the sandbox may not create
  releases). No stage has run in Actions yet.
- 2026-10-10 17:55 UTC: stage 1 launched by pushing the marker `.github/run/pilot-w1` = `tc:priority nex` (commit 6d71c1f): TerraClimate priority tiles
  (run 38073242901, 6 jobs) and NEX deltas for 20 models (run 38073242908). The `species-pilot-data` release exists (created by a workflow or another agent).
  Expected: tile jobs 1-3 h, NEX jobs about 1 h (est. from local timings, [U]).

## 1. What is built

A global predictor stack on TerraClimate's native 1/24 degree grid (2.5 arc-minutes, 4320 rows x 8640 columns, row 0 = north), land cells only.
Everything is cut into 16 tiles of 1080 x 2160 cells (45 degrees latitude x 90 degrees longitude), named `r<i>c<j>` (i = 0..3 from 90N, j = 0..3 from 180W).
Priority tiles (North America and Europe): r0c0, r0c1, r0c2, r1c0, r1c1, r1c2 (everything north of the equator and west of 90E).

Predictors (float32, in this order): `bio1, bio4, bio5, bio6, bio12, bio15, bio17, gdd, cwd, aet`.

| name | units and definition |
|---|---|
| bio1 | deg C, annual mean of monthly (tmax+tmin)/2 |
| bio4 | deg C x 100, SD of the 12 monthly mean temperatures x 100 (WorldClim convention) |
| bio5 | deg C, monthly mean daily maximum of the warmest month |
| bio6 | deg C, monthly mean daily minimum of the coldest month |
| bio12 | mm per year |
| bio15 | percent, coefficient of variation of the 12 monthly precipitation totals (0 where annual precipitation is 0) |
| bio17 | mm, precipitation of the driest 3 consecutive months (wrapping the year) |
| gdd | deg C days per year above 5 C (`climategrid.gdd`, sine method on a daily curve, sw = 3 C weather term, calibrated on NEX-GDDP daily data) |
| cwd | mm per year, TerraClimate's own `def` (sum of the 12 monthly climatology values) |
| aet | mm per year, TerraClimate's own `aet` (sum of the 12 monthly climatology values) |

Products (each one file per tile, `pred_<product>_<tile>.npz`):

| product | content |
|---|---|
| `base_1991-2020` | baseline climatology of TerraClimate monthly values, then predictors |
| `hind_1966-1985`, `hind_2005-2024` | same method for the hindcast windows (TerraClimate last full year is 2025, so 2005-2024 is complete) |
| `fut_<ssp245,ssp585>_<2041-2060,2081-2100>_ensmedian` | baseline plus ensemble-median NEX-GDDP change factors (4 products) |

Predictors are computed from the window's monthly climatology (mean of each calendar month over the years), not year by year.

Futures are coarse change factors plus an on-demand function:
`deltas_<model>.npz` (per climate model, 0.25 degree NEX-GDDP grid, monthly, scenarios ssp245 and ssp585, periods 2041-2060 and 2081-2100:
`dtx`, `dtn` additive deg C for monthly mean daily max and min, `rp` precipitation ratio) and `deltas_ensemble_median.npz`.
`basem_<tile>.npz` holds the baseline monthly climatology (tmax, tmin, ppt, pet, def, aet, soil as scaled integers) that `apply_deltas` needs.

Ensemble: median, per cell and month, of the changes of the models whose TCR is in the likely range 1.4-2.2 (config.toml `[models] tcr_likely`),
the same default ensemble as the site. The ensemble-median product is the fine-grid climate under the median change, not the median of per-model predictors.

## 2. Loading (exact)

```python
from ctw.species import climstack as S
# download (public release, no token; each file is checked against manifest.json). Needs only numpy.
S.download(["manifest.json", "landmask.npz", "pred_base_1991-2020_r1c1.npz", "basem_r1c1.npz", "deltas_MIROC6.npz"], "clim")
vals = S.sample_points("clim", "base_1991-2020", lat=[40.0, 35.0], lon=[-105.3, -100.0])    # (10, n_points), order S.NAMES, NaN on sea
grids, lat, lon = S.read_box("clim", "base_1991-2020", (30, 45, -110, -90))                  # dict name -> (ny, nx) float32, NaN on sea (needs the tiles covering the box)
# one climate model on demand (basem_<tile>.npz and deltas_<model>.npz in the directory):
st = S.load_baseline("clim", bbox=(35, 45, -110, -100))                                      # BaselineStack: land cells, st.lat, st.lon, st.row, st.col
fut = S.apply_deltas(st, S.DeltaLibrary("clim"), "MIROC6", "ssp585", "2081-2100")            # dict name -> (n,) float32 for the cells of st
```
Land mask: `landmask.npz` (`land_packed` = np.packbits of the (4320, 8640) boolean grid, row 0 = north; 12,532,612 land cells).
Each `pred_*` file also carries its tile's mask. Tile `r<i>c<j>` covers rows 1080i..1080i+1079 and columns 2160j..2160j+2159.

## 3. Release inventory [V: manifest.json built 2026-10-10 19:24 UTC, 149 files, 4.75 GB; no expected file missing]

- Tiles: all 16 (r0c0 .. r3c3), including all-ocean tiles (tiny files).
- 7 products x 16 tiles = 112 `pred_*` files: `base_1991-2020`, `hind_1966-1985`, `hind_2005-2024`, and `fut_{ssp245,ssp585}_{2041-2060,2081-2100}_ensmedian`.
- 16 `basem_<tile>.npz` (baseline monthly climatology for `apply_deltas`).
- 21 delta files: ACCESS-CM2, BCC-CSM2-MR, CNRM-CM6-1, CNRM-ESM2-1, CanESM5, EC-Earth3, EC-Earth3-Veg-LR, FGOALS-g3, GFDL-ESM4, GISS-E2-1-G, INM-CM4-8, INM-CM5-0, IPSL-CM6A-LR, KACE-1-0-G, MIROC-ES2L, MIROC6, MPI-ESM1-2-HR, MPI-ESM1-2-LR, MRI-ESM2-0, UKESM1-0-LL (the 20 models of data/nexdeltas.npz; each about 66 MB) and `deltas_ensemble_median.npz` (median of the likely-TCR models, listed in its meta and in `meta_ens.json`).
- `landmask.npz`, `manifest.json` (grid definition, predictor list and units, products, per-file sha256 and bytes), `qa_report.json`, `meta_*.json` (per job), plus intermediate `nexclim_*` files (coarse per-model monthly climatologies) kept for reuse.
- Missing: nothing in the contract. Not built: other hindcast windows, 4 other SSPs (the NEX files exist; deltas could be extended), per-model fine grids (by design).

## 4. QA [V: qa_report.json from the assemble/QA run, commit 6e6bd87 workflow; numbers below copied from it]

**Spike B box (lat 40-60, lon 0-20) vs a direct TerraClimate read with the spike's own function**: 152,100 land cells in both; every predictor identical (max abs difference 0.0007, gdd; bio15 differences zero). Means match the spike document (bio1 9.85, bio12 822 mm, gdd 2299 deg C days; cwd 200 and aet 533 mm are TerraClimate's own values, which equal the spike's TerraClimate-based numbers).

**Stack vs the site's present climate at its 2,386 places** (nearest 2.5' cell, all places on a land cell; site seasonal tmax/tmin/precipitation; ours minus site):

| group | annual mean temp bias / MAE (C) | annual precip bias / MAE (mm), ratio | seasonal tmax bias | seasonal precip r |
|---|---|---|---|---|
| all (2386) | +0.28 / 0.33 (r 0.9986) | -17 / 46, ratio 0.999 | +0.25..+0.35 | 0.991-0.994 |
| North America (790) | +0.39 / 0.47 | -57 / 90, ratio 0.92 | +0.37..+0.62 | 0.96-0.98 |
| world (1596) | +0.22 / 0.26 | +2.7 / 24, ratio 1.005 | +0.18..+0.22 | 0.996-0.998 |
| site source PRISM (635, US) | +0.40 / 0.45 | -77 / 84, ratio 0.91 | +0.41..+0.66 | 0.98 |
| site source TerraClimate (1751) | +0.23 / 0.28 | +4.9 / 32, ratio 1.006 | +0.20..+0.24 | 0.99 |

Reading [U, explanation not tested]: the world places use TerraClimate on a coarser grid, so the +0.2 C is the 2.5' cell versus the site's coarser average (the stack is warmer because cells keep their own, often lower-lying, character) and tmin +0.2 likewise. In the US the site uses PRISM, which is wetter (by 8-9%) and cooler than TerraClimate at the 4 km cell; this is a product difference and applies to every place in the US, so US species models fitted on this stack see slightly drier and warmer conditions than the site's maps.

**Hindcast plausibility** (area-weighted land means; ours, difference between windows):

| change | bio1 C | bio5 C | bio6 C | bio12 mm | gdd | cwd mm |
|---|---|---|---|---|---|---|
| 1991-2020 minus 1966-1985 | +0.87 | +0.78 | +1.04 | -10 (ratio 0.986) | +192 | +37 |
| 2005-2024 minus 1966-1985 | +1.22 | +1.19 | +1.23 | -13 (ratio 0.982) | +275 | +59 |

Warming by latitude band (2005-2024 minus 1966-1985, bio1): 90-66.5N +2.13, 66.5-45N +1.56, 45-23.5N +1.38, 23.5N-0 +1.08, 0-23.5S +0.89, 23.5-45S +0.70, south of 45S +0.74. Plausible: about 1.2 C global land warming over about 40 years with Arctic amplification (the mid-1970s to mid-2010s window shift is 40 years). The drying (-13 mm) is TerraClimate's own signal (it includes the Sahel/Amazon/Australia pattern); treat the precipitation trend as uncertain.

**Futures (ensemble-median, area-weighted global land, change from the 1991-2020 baseline)**:

| product | bio1 C | bio6 C | bio12 mm | gdd | cwd mm |
|---|---|---|---|---|---|
| ssp245 2041-2060 | +1.51 | +1.63 | +12 | +364 | +35 |
| ssp245 2081-2100 | +2.40 | +2.65 | +19 | +581 | +57 |
| ssp585 2041-2060 | +2.02 | +2.21 | +12 | +491 | +46 |
| ssp585 2081-2100 | +4.63 | +5.13 | +24 | +1150 | +112 |

**Our coarse deltas vs the repo's own `data/nexdeltas.npz` at the 2,386 places** (20 models; annual mean of monthly (dtx+dtn)/2): ssp245 2041-2060 mean bias +0.002 C, RMSE 0.14 C, r 0.953; ssp585 2081-2100 bias +0.03 C, RMSE 0.15 C, r 0.989. Differences come from 20 vs 10 sampled years per window and bilinear interpolation vs nearest NEX cell. The annual mean of monthly precipitation ratios agrees poorly (r 0.2-0.37, bias -0.12/-0.17) because that statistic is dominated by dry-month ratios, where we set the ratio to 1 below 0.05 mm/day of model baseline precipitation and the repo only when the baseline is zero; compare annual totals instead (bio12 changes are in the table above).

## 5. Known limits

- Seasonality predictors (bio4, bio15, bio17) derive from a smooth 25 km change field applied to monthly values; Spike B found r 0.67-0.94 against WorldClim futures for bio15/bio17. Use them with a sensitivity run.
- cwd and aet baselines are TerraClimate's own; futures use baseline plus the change in our simplified bucket model (own balance biases the deficit about 25% low, so the change, not the level, is modelled) [spike B].
- Futures are change factors from NEX-GDDP (bias-corrected statistical downscaling at 25 km) on a 4 km baseline; terrain-scale change differences are not represented. The 1991-2020 baseline for the NEX models is historical to 2014 plus SSP2-4.5 for 2015-2020.
- Hindcast windows use TerraClimate before 1980 when station coverage is thinner; trends in precipitation there are less certain. 1986-1990 are not used.
- Predictors come from window climatologies (monthly means), not annual extremes; bio5 and bio6 are monthly mean daily maxima/minima, not absolute extremes.
- bio15 is set to 0 where annual precipitation is 0. The ensemble median product is the climate under the median change (no per-model spread; use `apply_deltas` for any model).
- Resolution 2.5 arc-minutes (about 4.5 km at the equator); mountain cells hide up to 5-8 C of within-cell range (Spike B).
- TerraClimate land mask: Antarctica and small islands are absent where TerraClimate has no data; land cells are 12,532,612.
- Not covered: the ocean, and latitudes south of 60S for the NEX deltas (nearest fill; no land of interest).

## 6. Progress log (stages)

- 18:20 UTC: first tiles done in Actions [V: run 38073242901]: r1c2 (Europe, 0-45N, 0-90E) in about 30 min, r0c0 done; other priority tiles still running. NEX: 12 of 20 models finished in about 25 min each [V: run 38073242908]. Stage 2 launched: `tc:rest` (marker commit).
- 18:55 UTC: priority set complete on the release [V: meta_tc_r0c0..r1c2, meta_fut_r0c0..r1c2, 20 `deltas_<model>.npz`, `deltas_ensemble_median.npz`, `meta_ens.json`]. That is
  baseline, both hindcast windows and the four ensemble-median futures for tiles r0c0, r0c1, r0c2, r1c0, r1c1, r1c2 (north of the equator, 180W-90E), plus basem for apply_deltas.
  `tc:rest` run 38075334199 in progress for the other 10 tiles; tile r2c0 failed after 2 min because TerraClimate returned 404 for the 1966 files (transient, files exist; HEAD 200 afterwards) [V: job 114281056421]. Fix: 8 retries with backoff; r2c0 relaunched alone.
