# Climate Twins

Where on Earth does today's climate look like your town's future? An interactive map for 1,612 places:
789 across the US, Canada and Mexico and 823 world cities, for 2050 and 2100 under four emissions scenarios.

Live site: https://climate-twins.forest4science.workers.dev · How it works: [methods page](site/methods.html)

This repository holds everything: the data pipeline, the page, and the automation that keeps the data current.

## How updating works

| What | When | What you do |
|---|---|---|
| **Rebuild data** (`.github/workflows/rebuild.yml`) | Every March 15, or by hand | Nothing until it opens a pull request. Read the report in the pull request, then merge. |
| **Deploy site** (`deploy.yml`) | Whenever `site/` changes on `main` | Nothing: merging a rebuild publishes it. |
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

The first push deploys the current site (release 9.6) unchanged. The first rebuild produces release 10.

## Running locally

```
pip install -r requirements.txt
python -m ctw plan                          # models, latest TerraClimate year
CTW_SMOKE=1 python -m ctw all               # quick end-to-end test: 2 models, 12 places, a few years
python -m ctw validate --previous old_summary.json
python tests/test_page.py site              # browser test (pip install playwright; playwright install chromium)
```
Steps write to `work/` (set `CTW_WORK` to move it). A full local build needs about 25 GB of downloads.

## Layout

```
config.toml            every setting: periods, scenarios, models, matching, grids, review gates
ctw/                   the pipeline, one module per step (python -m ctw <step>)
  cmip6.py             model projections at every place (per model, in parallel on GitHub)
  terraclimate.py      world climate, humidity, recent years (per variable, in parallel)
  adaptwest.py prism.py gazetteer.py sealevel.py
  analogs.py           the matching; features.py (climate type, hardiness zone, growing season)
  export.py validate.py site.py watch.py
data/                  fixed inputs: place lists, outlines, calibration, sea-level projections
web/                   page and methods templates
site/                  what is published (built by the pipeline; do not edit by hand)
tests/test_page.py     browser test run by every rebuild
```

## Changing things

- **The page's look or text:** edit `web/index.html` or `web/methods.html`, then run `python -m ctw site`
  (or the next rebuild does it). Pushing `site/` deploys.
- **The method** (models, periods, measures): edit `config.toml`, bump `method_version`, run *Rebuild data*.
- **New baseline normals (2001–2030):** set `[baseline] years` once AdaptWest and PRISM publish them.
