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
- Side-by-side layouts (desktop, sideways phones): a caret on the middle of the panel edge hides the panel
  (map goes full width); a floating mini bar at top centre (place, period/scenario pickers, caret) restores it.
  Hidden panels stay hidden when places are tapped. Upright phones keep the bottom sheet and its own caret.
- Search: custom combobox (COMBO) replaces the datalist: focus selects the text and opens an alphabetical list
  (current place highlighted); typing filters (word-start matches first, 120 max); arrows/Enter/Esc; no-match row.
- Framing: every pick runs focusOn(): centres on the arrow's midpoint in Mercator space (place -> best, short way round),
  min ~90 km context; other matches join only if within 1.8x the arrow frame around that centre; balanced padding with
  room above the key. Phones may zoom out to 0.8 so very long arrows fit. Scenario/period changes don't move the map.
- toScr() wraps longitudes to the copy nearest the map centre, so views across the date line show both sides.
- Sharing: description, Open Graph/Twitter card (og-image.png 1200x630: dark map of 2100 SSP2-4.5 arrows, site fonts)
  and icons (favicon.svg, favicon-32.png, apple-touch-icon.png) live in web/assets/ and are copied by `ctw site`.
  The public address is config.toml [release] site_url; site.py fills __SITE_URL__. Change it there for a new domain.
- Tropics: panel note (tropNote) under the badge when best σ >= 2 and |lat| < 30; methods section #tropics with a
  latitude table filled by site.py (tropics_rows, ~2100 SSP2-4.5 likely range) and refs Mora 2013, King & Harrington 2018.
- Basemap: stateLines() restyles positron's boundary_3 to admin_level 4 only (states/provinces/territories) from zoom 2,
  dashed, lighter than national borders (#98a1ab light, #6f7c89 dark); runs after style load and every theme switch.
- Changelog: CHANGELOG.md -> site/changelog.html (ctw/changelog.py renders a small Markdown subset; template
  web/changelog.html). rebuild.yml runs `ctw changelog` (adds a data-update entry once per data version) and commits it.
- Preview card and Instagram images re-shot on real tiles (labels hidden) with state lines, 2026-09-28.
- Map view buttons: Home (start over: clear selection, starting view; also Esc) and World, 29 px icon buttons styled
  like the MapLibre +/- group directly beneath it. The old "US" button was dropped (Home covers it).
- Worker redirects page loads to https://climatetwins.org (http, www and the old workers.dev address); var CANONICAL_HOST.
  Tests: node worker/test_redirect.mjs.
- Preview titles: og/twitter title is "Where is your city's future climate today?" (Messages trims a leading site name).
- Map: US/World/Reset as one grouped control; best-match arrow stops outside the match dot; key has no loading line.
- deploy.yml rebuilds site/ from web/ once site/data/summary.json exists, so page edits go live on upload.

## Place requests (added after 10.0 went live)
- Page: "Don't see your place? Request it" under the search; a search with no match offers it too. Form posts to
  /api/request (place, region, note, honeypot `website`, `elapsed` ms).
- worker/index.js (Cloudflare Worker, assets binding ASSETS, rate limit binding REQUEST_LIMIT 5/min/IP, var
  GITHUB_REPO, secret DISPATCH_TOKEN) -> GitHub repository_dispatch "city-request". Tests: node worker/test.mjs.
- city-request.yml -> python -m ctw request (ctw/request.py triage: GeoNames candidates, already-covered check within
  20 km, grid coverage) -> issue labelled city-request with candidates in a hidden JSON comment.
- add-place.yml on an OWNER comment "/add [N]" -> python -m ctw add-place -> appends to data/targets.csv or
  data/world_targets.csv, commits to main, runs rebuild.yml, closes the issue.
- deploy.yml installs only requirements-site.txt (numpy, scipy, pandas, requests) with retries before `ctw site`.
- deploy.yml runs `wrangler secret put DISPATCH_TOKEN` when the repository secret exists.

## Feedback
- Page: fbdlg dialog (kind chips wrong/bug/idea/other, note, optional email, context preview via fbContext()); entry points:
  panel footer, "Something look off for this place?" under the comparison (kind=wrong), /#feedback (methods footer).
- Worker /api/feedback: validation (3–3000 chars, strict email regex, no header injection), honeypot, >= 3 s on form,
  rate limit; builds a UTF-8 text email (buildFeedbackEmail) and sends via send_email binding FEEDBACK_MAIL from
  var FEEDBACK_FROM to secret FEEDBACK_TO; 503 with a GitHub issues link if not configured.
- deploy.yml puts FEEDBACK_TO when the repository secret exists. Requires Email Routing on climatetwins.org with the
  address verified.

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
- Steps: `python -m ctw plan|cmip6 --model M|terraclimate --var V|era5 --var V (ERA5 cross-check, about 10 min per variable)|hindcast (needs the four era5 files)|adaptwest|prism|gazetteer|sealevel|analogs|export|validate|site|watch`.
  `CTW_WORK` = scratch dir, `CTW_SMOKE=1` = quick run.
- `web/` holds page templates; `site/` is build output (deployed). Page edits go in `web/`, then `python -m ctw site`.
- Gazetteer falls back to data/places_snapshot.json.gz when GeoNames is unreachable.
- Sandbox: 1 CPU / 3 GB. Running two TerraClimate passes plus CMIP6 at once crashed the VM; run one heavy job at a time.
  Background jobs stop when a turn ends; all steps checkpoint and resume.
