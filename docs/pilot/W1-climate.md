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
S0 = None  # download once (any machine, no token needed; files are checked against manifest.json):
# from ctw.species import climstack as S; S.download(["manifest.json", "pred_base_1991-2020_r1c1.npz", "basem_r1c1.npz"], "clim")
from ctw.species import climstack as S
vals = S.sample_points("clim", "base_1991-2020", lat=[45.5, 40.0], lon=[-122.7, -105.3])      # (10, n_points), order S.NAMES, NaN on sea
grids, lat, lon = S.read_box("clim", "hind_2005-2024", (35, 60, -10, 30))                       # dict name -> (ny, nx) float32, NaN on sea
# one climate model on demand (needs basem_<tile>.npz and deltas_<model>.npz in the directory):
st = S.load_baseline("clim", bbox=(40, 50, -10, 10))                                             # BaselineStack of land cells
lib = S.DeltaLibrary("clim")
fut = S.apply_deltas(st, lib, "MIROC6", "ssp585", "2081-2100")                                  # dict name -> (n,) float32, same cells as st (st.row, st.col)
```

Pending: final file inventory, QA numbers, known limits (sections 3 to 6 are filled as stages finish).

## 3. Progress

- 18:20 UTC: first tiles done in Actions [V: run 38073242901]: r1c2 (Europe, 0-45N, 0-90E) in about 30 min, r0c0 done; other priority tiles still running. NEX: 12 of 20 models finished in about 25 min each [V: run 38073242908]. Stage 2 launched: `tc:rest` (marker commit).
