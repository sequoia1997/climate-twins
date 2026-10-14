# Batch 3 (no birds): 97 organisms toward 250

Selection: `ctw/species/batch3select.py` -> `data/species/batch3.csv`, `data/species/native/curated_native_v3.csv`. 22 trees, 21 crops, 18 wild plants, 14 mammals, 13 insects and arachnids, 7 reptiles, 2 amphibians. No birds (35% of the first 124) and no fish (the fish target-group download came back empty in batch 2).

Dropped on a data check: brown marmorated stink bug and Asian lady beetle (96 to 97 percent of GBIF records are from introduced ranges, so very few native-range records), plus invasive or human-spread species whose native range is unclear (honey bee, Aedes mosquitoes, cabbage-moth pests, painted lady, Hemidactylus frenatus).

Pipeline: copies of the batch 2 stages (`ctw/species/s3run.py`, `.github/workflows/s3-w2.yml`, `s3-w3-fit.yml`, product `s3`). Everything batch 3 writes goes to the release `species-data-batch3` (the old release hit GitHub's 1000-asset limit); shared inputs (climate stack, target-group grids) are read from `species-pilot-data` (`W2_EXTRA_TAGS`). Publication to R2 uses the same rule as before (`ctw.species_site.defensible`).

Stages: push to `.github/run/s3-w2` with `[acquire]` and `[native]` in the commit message, then `[assemble]` in a separate push, then `all` to `.github/run/s3-w3`.

## Batch 4 (89 organisms; no birds, no fish)

`ctw/species/batch4select.py` -> `data/species/batch4.csv`, `native/curated_native_v4.csv`. Candidates are the most-recorded not-yet-used species per group in GBIF (`data/species/batch4_candidates.json`), so each is data-rich: 24 wild plants, 5 trees, 14 mammals, 14 reptiles, 12 amphibians, 20 insects and arachnids. Caveat: GBIF is strongly European-weighted, so this batch is too; a later round should add North American, Asian, African and South American species (the sandbox can reach GBIF but not iNaturalist, so those need a different source). Own pipeline copy (`s4run`, `s4-w2.yml`, `s4-w3-fit.yml`, release `species-data-batch4`). Start native-range inputs any time; start `[acquire]` only after batch 3's acquire has finished (GBIF allows three concurrent downloads per account).

## Batch 5 (23 organisms)

After batch 4 the live count was 239 (batch 3: 66 of 95 published; batch 4: 67 of 87). Batch 5 closes the gap to 250 with 8 amphibians, 8 reptiles, 3 bats and goats, 4 dragonflies and grasshoppers, all dense-record species from `batch4_candidates.json` (`ctw/species/batch5select.py`, release `species-data-batch5`, pipeline `s5run`, `s5-w2.yml`, `s5-w3-fit.yml`). Pass rate so far: 77 percent in batch 4, 69 percent in batch 3. Widespread European species such as hazel, cock's-foot, badger and the large white often fall just below the AUC floor of 0.60 even with a Boyce index above 0.9; the rule is unchanged.
