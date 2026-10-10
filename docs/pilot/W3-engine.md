# W3: production modelling pipeline (species pilot)

Status (updated as work proceeds): **in progress.** Last update: 10 October 2026, start of W3.

Owner workstream: W3. Inputs come from W1 (global climate stack, `docs/pilot/W1-climate.md`) and W2 (occurrences,
`docs/pilot/W2-occurrences.md`). Neither doc existed when W3 started; interfaces below are coded against an abstract
`ClimateSource` / `OccurrenceSet` and tested on synthetic stand-ins. Everything marked **unverified** has not been run on real data.

## 1. What is being built (all in `ctw/species/`)

| file | job |
|---|---|
| `pipeline.py` | predictor selection (priority + correlation pruning), accessible area, target-group-weighted background, spatial-block CV, LightGBM main model + GAM check model, metrics, threshold |
| `gates.py` | gates from F section 6 and the tier assignment |
| `project.py` | streamed projection over latitude bands and the climate-model ensemble, novelty, three dispersal bounds |
| `summary.py` | per-species JSON summary (areas, change, gain/loss/stable, centroid shift, gates, tier, skill) |
| `cts.py` | writer and reader for the CTS delivery format of spike G (lite product), plus the prototype `stats.json` entry |
| `run_pilot.py` | CLI: one species end to end, resumable; `report` sub-command makes the markdown gate table |
| `.github/workflows/pilot-w3-fit.yml` | matrix over species, resumable, summary job |

## 2. Waiting on others

- W1 climate stack and `apply_deltas(...)`: not yet published (release tag `species-pilot-data` empty at start). **Waiting.**
- W2 thinned occurrences, native-range masks, target-group density grids: **Waiting.**

(Updated below when they land.)
