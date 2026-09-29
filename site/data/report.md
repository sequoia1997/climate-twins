# Build check: routine update

Data version 2026-09-29, method 10.0.

- ✅ North American places: 790 of 790
- ✅ World cities: 1596 of 1596
- ✅ Overview covers 2386 of 2386 places
- ✅ Place data files: 58 shards
- ✅ North American pool cells: 97,488
- ✅ World pool cells: 64,958
- ✅ Climate models: 24 of 24
- ✅ Self-check (today's climate finds itself): median 0.00 σ (expect < 0.5)
- ✅ TerraClimate vs AdaptWest at the same places: median 0.00 σ
- ⚠️ ERA5 baseline agreement: median 1.39σ over 2,386 places; 43% above 2.0σ, 33% above 3.5σ (confidence lowered there)
- ✅ CHIRPS baseline agreement: median 0.06σ over 2,219 places; 5% above 2.0σ, 2% above 3.5σ
- ℹ️ Combined agreement (worst source per place): median 1.47σ; 44% above 2.0σ, 34% above 3.5σ (poor, by source: ERA5 789, CHIRPS 11)
- ✅ Best matches that moved more than 500 km: 1.0% (routine if ≤ 10%)
- ✅ Median change in best-match σ: 0.02 (routine if ≤ 0.25)

## Notes

- ERA5 disagrees with the baselines more than expected (median above 1σ or over 25% of places above the poor threshold): check the bias table in summary.json before trusting either dataset.
- Largest ERA5 disagreements: Zamboanga, Philippines (57.1σ); Jizan, Saudi Arabia (54.6σ); Koror, Palau (51.7σ); Porlamar, Venezuela (51.4σ); Tacna, Peru (49.6σ); Palikir, Micronesia (49.2σ); Moroni, Comoros (46.2σ); Roseau, Dominica (45.5σ)
- No CHELSA cross-check in this build (the job did not produce data); the panel line names the sources that ran.
- CHIRPS interannual precipitation variability relative to the place model (detrended SD of log seasonal totals, median, DJF MAM JJA SON): 0.82, 0.85, 0.79, 0.84
- Recent-climate years: 2016–2025
- Page downloads: index 174 kB, North America core 3.0 MB, world core 1.9 MB, then one of 58 place files (median 290 kB, largest 353 kB) per place picked.
- Coastal places with sea-level projections: 1013
- Largest σ changes: Kampala, Uganda (0.49); Khartoum, Sudan (0.42); Rangpur, Bangladesh (0.41); Kakamega, Kenya (0.40); Lomé, Togo (0.39); Multan, Pakistan (0.39); Port Sudan, Sudan (0.38); Mbandaka, DR Congo (0.38); Aden, Yemen (0.38); Prayagraj, India (0.37)
