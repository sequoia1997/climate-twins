# Archive

Finished work kept for the record. Nothing here runs: GitHub only runs workflows in `.github/workflows/`, and nothing in
`ctw/` or `tests/` imports these files.

| Folder | What it is |
|---|---|
| `workflows/` | One-off GitHub Actions runs that are done: the species pilot (W1–W4), batches 1–5 (`s1`–`s5`), fit recovery, and the CHELSA, CHIRPS, downscaled-deltas and ERA5 smoke tests. Batch 6 (`s6-w2.yml`, `s6-w3-fit.yml`) stays active as the template for the next batch. |
| `run-triggers/` | The files that started those runs (and the earlier spikes) when pushed under `.github/run/`. |
| `ctw-species-experiments/` | Probes and spikes from building the organisms pipeline (GBIF access, climate stack, hindcast and validation probes, terrain and Tier A tests). The design notes they fed are in `docs/spikes/` and `docs/pilot/`. |
| `prototypes/species/` | The first synthetic organisms page (spike G) and its browser test; the CTS format in `ctw/species/cts.py` came from here. |
| `spikes/` | A small spike folder (`e`). |

To rerun an archived workflow, move it back to `.github/workflows/` and its trigger back to `.github/run/`. Paths inside these
files are as they were when they ran.
