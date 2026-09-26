# Climate Twins handoff v6 (2026-09-25)

Live: https://climate-twins.forest4science.workers.dev (Worker `climate-twins`). Live release: 9.6.
This repository replaces the v9 script folder (climate_twins_pipeline_v9_5.zip) as the source of truth.

## Releases
- **9.6** (deployed from `site/` on first push): graphic map key (glyphs drawn like the map, context-dependent,
  collapses to the colour bar on phones), attribution shortened to "Methods & Sources · © OpenStreetMap"
  (full basemap credits on the methods page and in the link's hover text).
- **10.0** (produced by the first *Rebuild data* run): humidity in the matching, climate type, estimated
  hardiness zone and growing season, "already happening", sea level, page loads `data/na.dat` + `data/world.dat`.

## Page changes waiting for 10.0 (in web/index.html)
- Layout: intro folds into "About this map and σ" after a pick; period/scenario in a compact bar pinned while scrolling;
  checkboxes under Settings; key facts and matches 2-5 folded; comparison is an at-a-glance table (Temperature,
  Humidity, Precipitation, Climate type, Hardiness zone) whose rows open to charts. Open folds persist across re-renders.
- Phones (<=820px): full-screen map, panel as a bottom sheet (peek / half / full; drag or tap the grab bar).
  Picking a place opens half and scrolls to the answer; the search opens full; map padding follows the sheet.
- Phone sheet v2: sticky header (grab bar, place name, period/scenario pickers, caret) is the drag zone; content
  scrolls vertically only; page locked. States hidden (64px bar) / peek / half / full; the caret hides and restores;
  a hidden panel stays hidden when places are tapped (the bar's title updates). Bottom sheet is portrait-only.
- Sideways phones and short landscape screens: map beside a 340px panel, compact key, labels hidden, panel scrolls
  to the answer after a pick.
- Map: US/World/Reset as one grouped control; best-match arrow stops outside the match dot; key has no loading line.
- deploy.yml rebuilds site/ from web/ once site/data/summary.json exists, so page edits go live on upload.

## Method changes in 10.0
- 16 seasonal measures: tmax, tmin, ppt, dewpoint (DJF MAM JJA SON). Matched: 12 T/P + dewpoint DJF and JJA (K = 14).
  `config.toml [matching] humidity = false` returns to the v9 12-measure method.
- Dewpoint from TerraClimate vapour pressure (Magnus, Alduchov & Eskridge 1996), also on the NA 15 km grid
  (3 x 3 pixel mean). Future: obs vap x (huss_fut / huss_base), clipped 0.5-3; FGOALS-g3 SSP1-2.6 has no huss ->
  constant relative humidity.
- Features (features.py, data/feature_calibration.json): Köppen-Geiger (Beck et al. 2018 rules); hardiness from
  a regression on coldest-month low, annual range, log precip fitted to the PRISM/USDA 2023 grid
  (R² 0.956, same half-zone 56%, within one half-zone 95%); growing season fitted to ClimateNA FFP (R² 0.963,
  median error 7 days). Labelled "estimated, not the official USDA map" as the PHZM terms require.
- Snowfall deliberately not shown (monthly data cannot separate rain and snow; ClimateNA gives Denver 3%).
- Recent: latest 10 TerraClimate years vs 1991-2020 at each place (same dataset), σ departure.
- Sea level: IPCC AR6 medium confidence, places within 50 km of a projection site; runs once on GitHub
  (Zenodo is blocked from the Claude sandbox), result committed as data/sealevel.json. Untested; optional.
- Variability floor now applied to every place (v9: world cities only). Year handling tolerates missing years.

## Verification done in the sandbox
- Rebuilt NA pool 97,488 cells: 99.997% of int16 values identical to v9.5, max diff 0.01 °C.
- NA place baselines identical; MIROC6 projections within 0.01 °C.
- Regression, 12-measure mode, full data, 30 contiguous-US places x 16 combos: same best cell 480/480,
  max |Δσ| 0.002.
- Smoke run (12 places, 2 models, 9 years) through analogs -> export -> site -> validate -> browser test:
  passes at 1440 px light and 390 px dark. Screens reviewed.

## Not yet run at full scale
- `analogs` with humidity on all 1,612 places (first GitHub rebuild does it). Expect the "needs review" label:
  method version changed and there is no previous summary.
- Checks and results section of methods.html (Table 2) still quotes v9 numbers; regenerate from the first
  v10 summary.

## Deferred
- Heat days (days over 95 °F, NEX-GDDP daily data): terabyte-scale; would need a separate job design.

## Operating notes
- Steps: `python -m ctw plan|cmip6 --model M|terraclimate --var V|adaptwest|prism|gazetteer|sealevel|analogs|export|validate|site|watch`.
  `CTW_WORK` = scratch dir, `CTW_SMOKE=1` = quick run.
- `web/` holds page templates; `site/` is build output (deployed). Page edits go in `web/`, then `python -m ctw site`.
- Gazetteer falls back to data/places_snapshot.json.gz when GeoNames is unreachable.
- Sandbox: 1 CPU / 3 GB. Running two TerraClimate passes plus CMIP6 at once crashed the VM; run one heavy job at a time.
  Background jobs stop when a turn ends; all steps checkpoint and resume.
