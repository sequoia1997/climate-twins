# Build check: routine update

Data version 2026-09-30, method 10.0.

- ✅ North American places: 790 of 790
- ✅ World cities: 1596 of 1596
- ✅ Overview covers 2386 of 2386 places
- ✅ Place data files: 58 shards
- ✅ North American pool cells: 97,488
- ✅ World pool cells: 64,958
- ✅ Climate models: 24 of 24
- ✅ Self-check (today's climate finds itself): median 0.00 σ (expect < 0.5)
- ✅ TerraClimate vs AdaptWest at the same places: median 0.00 σ
- ⚠️ ERA5 baseline agreement: median 1.22σ over 2,331 places; 42% above 2.0σ, 32% above 3.5σ (confidence lowered there)
- ✅ CHIRPS baseline agreement: median 0.06σ over 2,219 places; 5% above 2.0σ, 2% above 3.5σ
- ⚠️ CHELSA baseline agreement: median 1.94σ over 2,386 places; 49% above 2.0σ, 36% above 3.5σ
- ℹ️ Combined agreement (two sources must agree): median 0.04σ; 4% above 2.0σ, 1% above 3.5σ (poor, by source: ERA5 9, CHIRPS 20)
- ✅ Best matches that moved more than 500 km: 3.7% (routine if ≤ 10%)
- ✅ Median change in best-match σ: 0.07 (routine if ≤ 0.25)

## Notes

- ERA5 disagrees with the baselines more than expected (median above 1σ or over 25% of places above the poor threshold): check the bias table in summary.json before trusting either dataset.
- Largest ERA5 disagreements: Jizan, Saudi Arabia (51.2σ); Tacna, Peru (48.6σ); Conakry, Guinea (47.2σ); Gisenyi, Rwanda (45.0σ); Monrovia, Liberia (44.2σ); Manokwari, Indonesia (43.6σ); Zamboanga, Philippines (41.4σ); Buchanan, Liberia (40.9σ)
- CHELSA disagrees with the baselines more than expected (median above 1σ or over 25% of its places above the poor threshold): check the bias table in summary.json.
- CHIRPS interannual precipitation variability relative to the place model (detrended SD of log seasonal totals, median, DJF MAM JJA SON): 0.82, 0.85, 0.79, 0.84
- Projected changes from NEX-GDDP-CMIP6 for 20 of 24 models (ACCESS-CM2, BCC-CSM2-MR, CNRM-CM6-1, CNRM-ESM2-1, CanESM5, EC-Earth3-Veg-LR, EC-Earth3, FGOALS-g3, GFDL-ESM4, GISS-E2-1-G, INM-CM4-8, INM-CM5-0, IPSL-CM6A-LR, KACE-1-0-G, MIROC-ES2L, MIROC6, MPI-ESM1-2-HR, MPI-ESM1-2-LR, MRI-ESM2-0, UKESM1-0-LL); native-grid CMIP6 for AWI-CM-1-1-MR, CNRM-CM6-1-HR, CanESM5-CanOE, EC-Earth3-Veg. Effect against the CMIP6-only projection of the same run: best match moved more than 500 km in 4.5% of place x period x scenario x ensemble combinations (24.8% of 2386 places in at least one period/scenario of the likely-range ensemble); median change in best-match sigma -0.00 (median |change| 0.09); median sigma distance between the two projected climates 0.00 (90th percentile 0.00); North America: moved 2.0%, median |dsigma| 0.02, distance 0.00; world: moved 5.8%, median |dsigma| 0.14, distance 0.00
- Sensitivity to model resolution (main projection from NEX-GDDP-CMIP6 changes vs the native-grid CMIP6 changes and other downscaled sources; WorldClim 2.1 (21 models) + AdaptWest (1 model mean) + native-grid CMIP6 (20 models); worst case over sources; 2386 places): 61% ok, 29% moderate (≥ 0.5σ or best match moved > 500 km), 9% high (≥ 1.0σ); median difference 0.0σ, 95th percentile 1.311σ; high by source: WorldClim 2.1 40%, AdaptWest 16%, native-grid CMIP6 7%
- Recent-climate years: 2016–2025
- Page downloads: index 174 kB, North America core 3.0 MB, world core 1.9 MB, then one of 58 place files (median 301 kB, largest 369 kB) per place picked.
- Coastal places with sea-level projections: 1013
- Largest σ changes: Georgetown, Guyana (4.34); Aden, Yemen (4.27); Santarém, Brazil (4.24); Paramaribo, Suriname (3.99); Mukalla, Yemen (3.48); Jeddah, Saudi Arabia (3.30); Chaguanas, Trinidad and Tobago (3.13); Monrovia, Liberia (3.03); São Luís, Brazil (3.03); Rasapūdipalem, India (2.98)
