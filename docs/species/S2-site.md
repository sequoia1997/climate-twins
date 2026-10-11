# S2: species pages on the static site (first release)

Status: **page, data builder, methods page and tests are done on branch `claude/eloquent-ritchie-r7jjby`; pull request opened, not merged.**
Tags: **[V: how]** verified by the named run, **[U]** unverified.

## 1. What is in it

| Path | What |
|---|---|
| `web/species.html`, `web/species/app.js` | the species page (one HTML file, one JS file; MapLibre from the same CDN version as the main page; custom WebGL layer for the CTS maps) |
| `web/species/land.cts` | land mask used only when the online base map cannot load (copy of the prototype's) |
| `web/species-methods.html` | methods, tiers, plain-words range-shift explanation, limitations, credits and the GBIF DOI of every species (table filled from the data index) |
| `ctw/species_site.py` | builds `site/species/data/` from the release assets (new file; no existing `ctw` file other than `site.py` is touched) |
| `ctw/site.py` | +15 lines: `species_pages()` copies the two pages and `web/species/*` into `site/` (no-op when `web/species.html` is absent) |
| `web/index.html` | +1 line: link "New: plants and animals under future climate" under the title in the panel |
| `site/species*.html`, `site/species/app.js`, `site/species/land.cts`, `site/index.html` | build output of `python -m ctw site`, committed like the rest of `site/` |
| `site/species/data/` | the species data (separate last commit, see section 3) |
| `tests/test_species_page.py`, `tests/test_species_site.py`, `tests/fixtures/species/` | browser test and builder test on real pilot outputs (3 species, 3.0 MB; the grape summary alone for the crop wording) |

Not touched: `deploy.yml`, `wrangler.jsonc`, `ctw/analogs.py` (unmodified, checked with `git status`), `data/species/batch1*`, `ctw/species/*`.

## 2. How the page works

- **Start:** `species/data/index.json` (13 kB for 25 species: id, name, scientific name, group, tier, confidence, range-shift status, season, bounding box, DOIs, file names and sizes). One species is selected (URL hash `#<id>`, default sugar maple) and only then are its `info.<hash>.json` (5 kB) and CTS files fetched.
- **Species file:** one base file (now) and one file per scenario (SSP2-4.5, SSP5-8.5: these are the only two the pilot produced; the page shows whatever scenarios the index lists). Files are fetched whole (no Range requests, so any static host works), kept in memory, cut into 256 x 256 blocks and drawn by one fragment shader. Period, dispersal bound, view, agreement and novelty overlays are uniform changes (no refetch); a scenario change fetches one file.
- **Controls:** Now / Future / Change, scenario, period (2041-2060, 2081-2100), dispersal (unlimited / limited / none, with the real reach in km and "uncalibrated, about 10 times uncertain"), agreement shading (dotted where fewer than 3 in 4 of the 14 models agree), novelty shading (diagonal lines, read from the species' own novelty band in the scenario file).
- **Summary:** area now / future / change, centre shift with arrow, lost / kept / gained, agreement, novel share. One chart view at a time with a Values / Change toggle; taps on rows do nothing (tested).
- **Trust cues on every species:** tier badge (A / B, symbol plus word), "Low confidence" with the reason, range-shift badge (pass / fail / untested, with plain-words explanation), cross-validation kind, records, DOIs, the exact `wording` field of the summary (crops get their own), "Climate suitability, not a forecast.", breeding-season note for migratory birds, link to methods.
- **Withheld numbers:** when a scenario and period is flagged (novel climate above 15%) the summary shows "Withheld" plus the reason from the summary; the map is drawn and the novelty overlay is forced on and its checkbox disabled. The place list shows those species as "not shown", never as a number.
- **Place list** ("which species lose or gain climate where you are", closed by default, loaded only when opened): 49 cities, read from the map cells around each city centre at build time for every scenario, period and dispersal bound. **Cheap, so included.** It is a list of cities, not an arbitrary click on the map.
- **Dependency card:** skipped, as instructed (no curated pairs exist).
- **Layout and access:** bottom sheet on phones (same pattern as the main page), side panel on desktop; light and dark (system, plus a button, shared `ct-theme` key); keyboard: combobox search with arrows and Enter, all controls are buttons, inputs or selects with visible focus; legend uses hatch / dots / lines, so no colour-only encoding; live region and a text description of the map; reduced motion respected.
- **Base map:** the same OpenFreeMap styles as the main page, species colours inserted below the label layer; if the style cannot load, a plain background plus `land.cts` is used (this is what the offline test sees).
- **Colours (dataviz validator run) [V]:** lost `#b84a00`, gained `#1769c9` pass lightness band, CVD separation (worst adjacent pair delta E 15.3 protan, 9.9 tritan), normal-vision floor and contrast; kept is a deliberate neutral grey `#55606b` that fails only the chroma floor (by design) and is told apart from the others by hatch and dots. Dark mode uses its own steps (`#e0692a`, `#3d8fe6`, `#b9c3cb`) with the same result (separation passes; the grey fails band and chroma by design).

## 3. Hosting and how files get into `site/`

**Sizes [V: built from the real release assets, `python -m ctw.species_site build`]:** 25 pilot species = **51.1 MB** (average 2.0 MB per species; range 0.7 MB to 5.9 MB: barn swallow 5.9, red fox 5.6, wine grape 5.3, plain tiger 3.2). The roadmap's "about 30 MB for 60 species" is **too low by a factor of about 4**: 60 species at the pilot average is about **120 MB** (50 to 150 MB depending on how many wide-ranging species are added). `site/` is 27 MB today, so the deployed site would be about 150 MB. The cause is real, patchy ranges (the prototype's 226 KB per species was synthetic). The CTS files are already deflated, so the host's compression does not shrink them.

**Cloudflare limits [U: from documentation as recalled, not verified from this sandbox]:** Workers static assets allow 25 MiB per file (largest file here is 3.0 MB) and about 20,000 files per version on the free plan (we have about 130 species files plus 75 site files); no total-size limit was recalled. Cloudflare's own documentation should be checked before the deploy of the 60-species build (`wrangler deploy` will fail loudly if a limit is hit; the live site is unchanged on failure).

**Base URL:** `<meta name="species-data-base" content="species/data/">` in `species.html` and `species-methods.html` (relative to the page, or an absolute URL). Moving to R2 later = upload `site/species/data/` to the bucket (same layout, hashed immutable files; `index.json` last) and change the two meta tags. No code change. The R2 bucket would need CORS for the site origin (GET, HEAD) [U].

**Getting files into `site/` (decision):** a builder, not hand-copying. `python -m ctw.species_site build --src <folder with w3_*/s1_* assets> --out site/species/data` reads `<prefix>_<slug>_summary.json` and `<prefix>_<slug>_cts.zip`, applies the selection rule (birds use the `_breeding` run when it exists, everything else the all-year run; tier C, unpublished or zip-less species are left out and listed in the log), and writes hashed files (`<id>/base.<hash>.cts`, `<id>/ssp245.<hash>.cts`, `<id>/info.<hash>.json`, `places.<hash>.json`, `index.json`). **Adding species is only a data change:** put the new `s1_*` assets in the folder and rebuild (about 1 s per species plus 30 s for the place table; the 25-species build took 62 s). Nothing in the page or the builder names a species.

Steps today (no workflow needed):
```
gh release download species-pilot-data --dir work/species-assets --pattern 'w3_*_summary.json' --pattern 'w3_*_cts.zip' --pattern 's1_*_summary.json' --pattern 's1_*_cts.zip'
python -m ctw.species_site build --src work/species-assets --out site/species/data
git add site/species && git commit && git push      # deploy.yml publishes on main (its paths filter already includes site/**)
```

**Repo growth:** committing the files puts about 51 MB (25 species) and later about 120 MB in git history, and every rebuild that changes a species adds a new copy of that species' files (names carry the content hash; unchanged species cost nothing). Git cannot shrink them (already compressed). The data is committed as **one separate last commit** in the pull request so you can drop it and decide.

### Proposals that need your approval (nothing below is in the branch)

1. **A publish workflow** `species-site-data.yml` (manual dispatch) that downloads the release assets, runs the builder, commits `site/species/data/` and starts `deploy.yml` (a push made with `GITHUB_TOKEN` does not start other workflows, so it dispatches it). I wrote it, but the tool policy blocked me from creating a workflow that pushes commits and dispatches a deploy, so I stopped there. Full text of the proposal:
```yaml
name: Species site data
on: { workflow_dispatch: { inputs: { tag: { default: "species-pilot-data" } } } }
permissions: { contents: write, actions: write }
concurrency: species-site-data
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with: { python-version: "3.12" }
      - run: pip install numpy
      - env: { GH_TOKEN: "${{ github.token }}" }
        run: gh release download "${{ inputs.tag }}" --dir work/species-assets --pattern 'w3_*_summary.json' --pattern 'w3_*_cts.zip' --pattern 's1_*_summary.json' --pattern 's1_*_cts.zip'
      - run: python -m ctw.species_site build --src work/species-assets --out site/species/data
      - env: { GH_TOKEN: "${{ github.token }}" }
        run: |
          git config user.name github-actions; git config user.email actions@users.noreply.github.com
          git add -A site/species/data; git diff --cached --quiet && exit 0
          git commit -m "Species site data: rebuild from ${{ inputs.tag }}"
          git pull --rebase origin "$GITHUB_REF_NAME" && git push origin "HEAD:$GITHUB_REF_NAME"
          [ "$GITHUB_REF_NAME" = main ] && gh workflow run deploy.yml --ref main || true
```
2. **Alternative with no repo growth: change `deploy.yml`.** Add a step before `wrangler-action` that downloads the release assets and runs the builder into `site/species/data/` (the folder would then be git-ignored). Same builder, no committed data; the deploy takes about 1.5 minutes longer and depends on the release assets staying available. Proposed step:
```yaml
      - name: Species data from the release
        env: { GH_TOKEN: "${{ github.token }}" }
        run: |
          pip install numpy
          gh release download species-pilot-data --dir work/species-assets --pattern 'w3_*_summary.json' --pattern 'w3_*_cts.zip' --pattern 's1_*_summary.json' --pattern 's1_*_cts.zip'
          python -m ctw.species_site build --src work/species-assets --out site/species/data
```
   plus `species/**`-independent paths filter additions only if the release is changed without a repo change (a `workflow_dispatch` already exists). I recommend this for the 60-species and larger releases; I did not make it because `deploy.yml` needs your approval.
3. **R2** (later): see "Base URL".

## 4. Page-load numbers (headless Chromium, localhost, software WebGL, no throttling) [V: tests/test_species_page.py and a 25-species local site]

| | bytes | time |
|---|---|---|
| Startup, sugar maple (default): index 1.6 kB (13 kB with all 25 species) + info 5.2 kB + base 49 kB + SSP2-4.5 file 371 kB | **427 kB** of data (+ 200 kB land mask only in the offline fallback) | index 30-50 ms, info 20-340 ms, first full map 470-910 ms |
| Widest species (barn swallow): base + one scenario | 3.0 MB | scene 184 ms (localhost) |
| Scenario switch | one file (0.37 MB for sugar maple, up to 2.7 MB) | one fetch |
| Period, dispersal, view, overlays | 0 | one frame |
| Place table (opened on demand) | 25 kB for 25 species x 49 cities | |

Real network, real phones, Safari and Firefox were **not** tested [U]. The first-draw time on a slow link scales with the scenario file: a 2.7 MB file at 1.6 Mbit/s is about 13 s for the widest species; the world view cannot draw before the whole file is in. If that matters, ranges can be fetched (the CTS index supports it; the prototype did so) once the host's Range support is verified [U].

## 5. Tests [V]

- `python tests/test_species_page.py` (Playwright, offline; needs `PW_CHROMIUM`, `PW_MAPLIBRE_DIR`): builds the 3-species fixture with the real builder, serves it as `site/`, runs at 1440 x 900 and 390 x 844, light and dark (4 runs). Checks: no JS error; map shows range colours; no horizontal overflow (page and panel, species page and methods page); no unnamed control; startup fetches only the index and one species; tier, low confidence, range-shift status, "not a forecast" and the wording on the header; scenario, period, dispersal and overlay clicks; the limited-dispersal text has a distance; exactly one chart view in the flow, a row tap never switches it, the toggle does; keyboard search selects ("robin" gives the Tier A, breeding-season, range shifts fail robin); the kookaburra shows withheld numbers with the novel-climate reason; the place list text; phone sheet collapses; methods page lists the DOI table and the required sections.
- `pytest tests/test_species_site.py` (8 s): selection rule, hashed files, index, withheld reasons, place table (Sydney keeps kookaburra climate), crop wording kept verbatim.
- `python tests/test_page.py site` (the existing main-page test) passes with the link and the rebuilt `site/` [V: local run, 8 places, 2 viewports].
- Not covered: pixel correctness (a human looks at the screenshots in `docs/species/img/`), screen readers, colour-blind simulation, real GPUs.

## 6. Open points for the owner

- Hosting choice in section 3 (committed data, or the deploy-time download), and the Cloudflare limits to confirm.
- The 25 pilot species are all there is until S1's `s1_*` assets exist; the builder will take them unchanged if they follow the `<prefix>_<slug>_summary.json` / `_cts.zip` naming. **If S1 uses different names or adds scenarios, tell me or adjust `pick_runs`.**
- DOIs for TerraClimate (10.1038/sdata.2017.191) and the NEX-GDDP-CMIP6 paper (10.1038/s41597-022-01393-4) on the methods page are from memory [U]; the GBIF, BBS, WCVP and USFS DOIs come from the project's own notes (`W2-occurrences.md`, `C-validation.md`).
- Methods statements about the birds' range-shift test describe the result as "direction of change no better than chance" (roadmap section 16); the early test period is not named on the page.
- The 49-city list in `ctw/species_site.py` (`PLACES`) is a table: replace or extend it freely.
- Species with tier C or `published: false` are left out, e.g. the all-year European robin; its breeding fit (tier B, low confidence) is shown.
- The page default (sugar maple) is a placeholder choice.
