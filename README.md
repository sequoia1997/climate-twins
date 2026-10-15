# Climate Twins

**Will your town feel like somewhere else one day?** Climate Twins is a free, non-commercial educational site with two halves:

- **Places** ([climatetwins.org](https://climatetwins.org)): pick a town in North America or one of 800 major cities worldwide, and an arrow
  points to the place whose climate *today* best matches the climate yours is projected to have around 2050 or 2100, under four emissions
  scenarios. Similarity is measured as sigma dissimilarity (Mahony et al. 2017), the method behind Fitzpatrick & Dunn's 2019 map of 540
  North American cities.
- **Organisms** ([climatetwins.org/species](https://climatetwins.org/species)): pick one of about 380 plants, animals and fungi from a
  tree of life, and see where its suitable climate is projected to be lost, kept or gained by 2050 or 2100. Each map comes from a
  statistical model (LightGBM, with a smooth additive model as a cross-check) fitted to real recorded locations, projected with 14 CMIP6 climate
  models.

Everything is *projections, not forecasts*: organism maps show where the climate may suit a species, never where it will live.
Both halves are built for a curious non-specialist first (a plain answer, one tap for the reasons) with the method, data and
limitations one layer down on the [methods page](https://climatetwins.org/methods).

This repository holds everything: the data pipelines, the pages, the Cloudflare Worker and the automation that keeps the data current.

## What is where

| Part | Source | Data lives |
|---|---|---|
| Places page | `web/index.html` | `site/data/` (committed, built by *Rebuild data*) |
| Organisms page | `web/species.html`, `web/species/app.js` | Cloudflare R2 bucket, served at `species.climatetwins.org` (built by *Publish organisms to R2*) |
| Methods page (both halves) | `web/methods.html` | rendered into `site/` |
| Worker (feedback, place requests, security headers) | `worker/index.js`, `web/assets/_headers` | deployed with `wrangler.jsonc` |

The Places pipeline is `ctw/*.py` (one module per step). The Organisms pipeline is `ctw/species/` (occurrence records from GBIF,
climate stack, model fitting, publication gates) plus `ctw/species_site.py`, which turns fitted models into the files the page loads.
The long-form design notes are in `docs/SPECIES_ROADMAP.md`.

### How an organism gets on the map

1. **Pick and fetch.** Species are chosen in batches (`data/species/batch*.csv`) and their occurrence records downloaded from GBIF. Records
   under CC0, CC BY and CC BY-NC are used (the site is non-commercial); each organism's page lists the GBIF download DOIs.
2. **Fit.** A model is fitted to *all* recorded locations (gardens, farms and stocked populations are left out), checked by spatial-block
   cross-validation, with a second simpler model as a sanity check. Where an independent survey exists (Breeding Bird Survey, US Forest
   Inventory) the model is also tested against it.
3. **Gate.** An organism is published only if it clears the skill thresholds (`ctw/species/gates.py`); the rest are not shown.
4. **Project.** Suitability is projected with 14 climate models and four scenarios. Numbers are withheld where most of the future area has
   a climate unlike anything in the organism's records.
5. **Publish.** *Publish organisms to R2* (`species-publish.yml`) builds the files and syncs them to R2. Photos come from Wikimedia Commons
   (public domain, CC0, CC BY and CC BY-SA only) and are credited on each page.

Fitting runs as staged GitHub Actions workflows (`s*-w2.yml`, `s*-w3-fit.yml`, `refit.yml`, `nc.yml`, `intro.yml`, `images.yml`),
started by pushing a file under `.github/run/`.

## How updating works

| What | When | What you do |
|---|---|---|
| **Rebuild data** (`.github/workflows/rebuild.yml`) | Every March 15, or by hand | Nothing until it opens a pull request. Read the report in the pull request, then merge. |
| **Extreme days** (`.github/workflows/extremes.yml`) | Every April 20, or by hand | Separate from the rebuild. Downloads NEX-GDDP-CMIP6 daily data (one job per model x baseline/scenario, ~100 jobs; about 93 GB per model, 20 models, all four scenarios) and opens a pull request that changes only `site/data/extremes.json` and `data/nexdeltas.npz`. Merging it also changes the main answer at the next rebuild: `config.toml [deltas] source = "nex"` makes each model's projected change come from these 25 km, bias-corrected data where they exist (native-grid CMIP6 otherwise; `"cmip6"` switches back). The rebuild report says which source each model used and how far matches moved. |
| **Deploy site** (`deploy.yml`) | Whenever `site/`, `web/` or `worker/` change on `main` | Nothing: merging publishes it. |
| **Publish organisms** (`species-publish.yml`) | When organism data changes, or by hand | Nothing routine. It needs the R2 secrets below. |
| **Watch upstream data** (`watch.yml`) | The 1st of each month | Read the issue it opens, if any (a new TerraClimate year, a corrected climate-model dataset, CMIP7 arriving). |

The rebuild downloads every source again (TerraClimate, AdaptWest, PRISM, 24 CMIP6 models), recomputes all
matches, checks the result and opens a pull request labelled **routine** or **needs review**:

- **routine**: counts are right, today's climate finds itself, and matches moved little from the last release.
- **needs review**: more than 10% of best matches moved over 500 km, typical σ changed by more than 0.25, or
  the method version changed. Read `site/data/report.md` in the pull request before merging.
- If the build breaks, you get an issue instead and the live site is untouched.

Nothing reaches the live site until you merge.

## One-time setup

1. **Create the repository.** On GitHub: *New repository* → name `climate-twins` → **Public** (public
   repositories get unlimited free Actions minutes and faster machines) → *Create*. Do not add a README.
2. **Upload these files.** Easiest from a terminal in this folder:
   ```
   git init -b main
   git add .
   git commit -m "Climate Twins pipeline and site"
   git remote add origin https://github.com/YOUR-NAME/climate-twins.git
   git push -u origin main
   ```
   (Or use *Add file → Upload files* on GitHub and drag the folder contents in.)
3. **Add the Cloudflare secrets.** In the repository: *Settings → Secrets and variables → Actions →
   New repository secret*. Add two:
   - `CLOUDFLARE_API_TOKEN`: your Cloudflare API token. It needs the **Workers Scripts: Edit** permission
     (the *Edit Cloudflare Workers* template in Cloudflare → *My Profile → API Tokens* creates one).
   - `CLOUDFLARE_ACCOUNT_ID`: in the Cloudflare dashboard, *Workers & Pages*, shown in the right-hand column.

   Paste the token only into GitHub's secret box. Never put it in a file, a commit, an issue or a chat.
4. **Let the rebuild open pull requests.** *Settings → Actions → General → Workflow permissions*: choose
   *Read and write permissions* and tick *Allow GitHub Actions to create and approve pull requests*. Save.
5. **Optional safety catch.** *Settings → Environments → production → Required reviewers → add yourself.*
   Every deployment then waits for your click.
6. **Say where the code lives.** Edit `config.toml`: set `repo_url = "https://github.com/YOUR-NAME/climate-twins"`.
   The methods page links to it.
7. **Run the first rebuild.** *Actions → Rebuild data → Run workflow*. It takes 2–3 hours. When the pull
   request appears, read the report, open the `site` artifact from the run to try the new page if you like,
   then merge.

The first push deploys the current site unchanged. Organisms need extra one-time setup: an R2 bucket with a custom domain
(`species.climatetwins.org`) and the repository secrets `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` and `R2_BUCKET`.

## Place requests

Visitors can ask for a place that isn't on the map ("Don't see your place?" under the search box).

1. The form posts to the Worker (`worker/index.js`), which passes the request to GitHub. Spam guards: a hidden
   field bots fill in, a minimum time on the form, 5 requests per minute per visitor, length limits.
2. **Place request** (`city-request.yml`) looks the place up in GeoNames, checks whether it is already on the map
   and whether the data cover it, and opens an issue labelled `city-request`. You get the usual GitHub notification.
3. Comment **`/add`** on the issue (or `/add 2` for the second candidate) and **Add requested place**
   (`add-place.yml`) adds it to the place list, starts **Rebuild data** and closes the issue. Merge the rebuild's
   pull request and the place is live. To decline, close the issue.

One-time setup: the Worker needs a GitHub token to pass requests on.
*GitHub → your photo → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new
token*: repository access **Only select repositories → climate-twins**; repository permission **Contents: Read and
write** (GitHub requires this for dispatch events); the longest expiry offered. Save it as the repository secret
`DISPATCH_TOKEN`. Every deploy hands it to the Worker. When it expires, requests fail politely until you make a new one.

## Feedback

"Send feedback" (bottom of the panel on both the Places and Organisms pages, under each place's comparison, and on the methods page via `/#feedback`)
opens a short form: what it's about, the note, an optional reply email, and an optional summary of what the visitor
was looking at (place or organism, period, scenario, screen type, data version; shown to them before sending).
The Worker (`worker/index.js`, `/api/feedback`) emails it privately to you through Cloudflare Email Routing,
from `feedback@climatetwins.org`, with Reply-To set to the visitor's address if they gave one. Nothing is published
or stored. Each email has a link that opens a public GitHub issue with the note (without their email) if you want
to track it. Spam guards as for place requests. Tests: `node worker/test_feedback.mjs`.

One-time setup (in this order):
1. Cloudflare dashboard → **climatetwins.org → Email → Email Routing → Enable**. Accept the DNS records it adds.
2. **Destination addresses → Add** your personal email, then click the link in the verification email.
3. Optional: add a routing rule `feedback@climatetwins.org` → your email, so replies to that address reach you.
4. GitHub repository secret **`FEEDBACK_TO`** = that verified address. It is never stored in the repository.
5. Upload the files and let **Deploy site** run. It hands `FEEDBACK_TO` to the Worker.

## Changelog

`CHANGELOG.md` is the public "What's new" page (`/changelog.html`, linked from the panel and the methods page).
Add entries in plain language under a `## date` heading, newest first, just below the `<!-- entries -->` line.
Each data rebuild adds its own dated entry automatically (once per data version) and includes it in its pull request.

## Running locally

```
pip install -r requirements.txt
python -m ctw plan                          # models, latest TerraClimate year
CTW_SMOKE=1 python -m ctw all               # quick end-to-end test: 2 models, 12 places, a few years
python -m ctw validate --previous old_summary.json
python tests/test_page.py site              # Places browser test (pip install playwright; playwright install chromium)
python tests/test_species_page.py           # Organisms browser test, on real fixture outputs
python -m pytest                            # the rest of the Python tests
node worker/test_redirect.mjs               # Worker: redirects, security headers and the policy in web/assets/_headers
```
Browser tests use `PW_CHROMIUM` (browser binary) and `PW_MAPLIBRE_DIR` (a local MapLibre 5.24.0 `dist` folder) to run offline.
Steps write to `work/` (set `CTW_WORK` to move it). A full local build needs about 25 GB of downloads.

## Layout

```
config.toml            every setting: periods, scenarios, models, matching, grids, review gates
ctw/                   the pipeline, one module per step (python -m ctw <step>)
  cmip6.py             model projections at every place (per model, in parallel on GitHub)
  terraclimate.py      world climate, humidity, recent years (per variable, in parallel)
  adaptwest.py prism.py gazetteer.py sealevel.py
  analogs.py           the matching; features.py (climate type, hardiness zone, growing season)
  extremes.py          NEX-GDDP-CMIP6 daily data: extreme-day counts and data/nexdeltas.npz (the downscaled monthly changes)
  nexcheck.py          uses those changes in the projection ([deltas]) and checks sensitivity to model resolution
  export.py            packs results for the page: index.json, two core pools, per-place shards (site/data/p/)
  validate.py site.py watch.py
  expand.py regions.py reshard.py  one-off tools (not in the workflow): grow the world place list, region table, convert old data files
data/                  fixed inputs: place lists, outlines, calibration, sea-level projections
  species/             the organisms pipeline: GBIF records, climate stack, model fitting, gates, publication
  species_site.py      turns fitted models into the files the Organisms page loads
web/                   page and methods templates (index.html, species.html, species/app.js, methods.html, assets/)
site/                  what is published (built by the pipeline; do not edit by hand)
worker/                the Cloudflare Worker: place requests, feedback email, redirects, security headers
docs/                  design notes: SPECIES_ROADMAP.md and the earlier handoff
tests/                 test_page.py and test_species_page.py (browser), plus unit tests for each module
```

## Changing things

- **The page's look or text:** edit `web/index.html`, `web/species.html`, `web/species/app.js` or `web/methods.html`, then run
  `python -m ctw site` (or the next rebuild does it). Pushing to `main` deploys. The security headers live in
  `web/assets/_headers` and must match the policy in `worker/index.js` (a test checks this).
- **An organism:** add it to a batch CSV, run the staged fit workflows, then *Publish organisms to R2*.
- **The world place list:** `python -m ctw.expand` prints a proposed expansion of `data/world_targets.csv` from the committed
  GeoNames snapshot (`--write` appends it); review the diff, commit, run *Rebuild data*.
- **Page weight:** the page downloads `site/data/index.json` (all places) and the two pool files first, then one
  small shard from `site/data/p/` (about `[export] shard_places` places) when a place is picked, so it does not grow
  with the number of places.
- **The method** (models, periods, measures): edit `config.toml`, bump `method_version`, run *Rebuild data*.
- **New baseline normals (2001–2030):** set `[baseline] years` once AdaptWest and PRISM publish them.
