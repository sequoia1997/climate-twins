# Reviewer brief: Climate Twins species extension (one page)

**Who we are asking.** A practising species-distribution-modelling (SDM) ecologist, plus, separately, a botanist or ornithologist for the species lists. About 3-4 hours. We want you to find what is wrong, not to endorse it.

**What we are building.** Climate Twins is a free public website that shows where in the world a place's climate is heading, by matching it to places that already have that climate. The new extension adds about 350 familiar species (trees, birds, crops, insects and others). For each species a page says: where the climate is suitable now, where it is projected to be suitable around 2050 and later under several warming levels, and how reliable that is. The site is for the general public, so plain-language claims matter as much as the maths.

**What the model does, in brief.**
- Occurrence records from GBIF (CC0 and CC-BY only), cleaned, thinned to one per grid cell (0.5 degrees, about 50 km).
- Climate predictors: temperature, precipitation, water balance and a few others from TerraClimate, held uncorrelated.
- An ensemble of several algorithms plus our own "climate typicality" distance, spatial block cross-validation, a skill gate per species, flags where predictions go outside the training climate.
- Projections using the same climate-model ensemble and warming levels as the rest of the site.
- It shows **climate suitability**, not where the species will actually be (dispersal, land use and biotic interactions are not modelled, except an optional dispersal limit).

**How we test it (details in docs/spikes/C-validation.md, section 4).** Fit on an early period, predict a later period from the later climate, and compare with what really changed. Planned tests, in order: North American Breeding Bird Survey (1966-85 to 2005-24); European Breeding Bird Atlases 1 and 2; USFS Forest Inventory trees; then a GBIF split by date. Metrics: AUC, TSS, Boyce index, direction of shift, centroid shift error, area change error, always against a "nothing changes" baseline. Proposed pass marks and minimum species counts are in section 4.6 and 4.7. These are our own proposals, not accepted standards.

## Please check these, in this order

1. **Is the hindcast a fair test?** Windows, climate source for both periods, how we handle recorder effort (standardised surveys first; target-group background for GBIF; well-sampled cells only). Is anything leaking information from the later period into the fit?
2. **Are the pass/fail thresholds sensible?** TSS at least 0.4, AUC at least 0.7, direction correct for at least 70% of shifting species, shift-ratio between 0.5 and 2, minimum 20-40 species per test. Which would you change, and why?
3. **Does the change test mean what we say it means?** Trees lag behind climate. If a group fails, we plan to hide projections for it or label them "suitable climate, not expected range". Is that the right response?
4. **Is the cleaning and thinning adequate?** Coordinates, cultivated and escaped records, taxonomy, the "accessible area" for each species, and the 50-100 record minimum.
5. **Predictors and extrapolation.** Is the predictor set reasonable for plants, birds and insects? Is our flagging of out-of-range climates (MESS-type) enough for the far-future and warm-end cases?
6. **Ensemble and spatial cross-validation.** Block size, choice of algorithms, how we combine them, and how we report disagreement between algorithms versus between climate models.
7. **Wording on species pages.** Read ten sample pages as a member of the public. Where could a claim be taken as "this species will be here by 2050"? Which caveats are missing?
8. **Species list review (botanist/ornithologist).** Names and synonyms, native versus cultivated ranges, any species where our method is clearly unsuitable (for example crops grown mainly under management, migratory insects such as the monarch, species with strong host dependence).

## What we already know is weak
- Some groups have **no usable validation data** (monarch, blacklegged tick, wine grape). They will be labelled "not validated".
- Atlas, survey and inventory data have their own biases (roadside sampling, uneven atlas effort, fuzzed forest plot coordinates).
- Tropical regions have far fewer records; reliability is labelled by region.
- Published projections available for comparison are mostly trees (US Forest Service) and North American birds (Audubon); we cannot compare every species.
- Some data terms are not yet confirmed (EBBA2, FIA coordinates, Audubon projections). We will not use eBird Status and Trends or Christmas Bird Count data in the public pipeline because their terms restrict redistribution.

## What we would like back
A short written note: (a) what must change before launch, (b) what should change but can wait, (c) what you would not claim, (d) whether you are willing to be named as a reviewer and how you would like it described. We will publish your comments, with your permission, alongside the methods page and record the changes we made in response.

**Key references to start from:** Araujo et al. 2005 (validation under climate change, doi:10.1111/j.1365-2486.2005.01000.x); Rapacciuolo et al. 2012 (transferability in time, doi:10.1371/journal.pone.0040212); Roberts et al. 2017 (cross-validation, doi:10.1111/ecog.02881); Zurell et al. 2020 (ODMAP reporting, doi:10.1111/ecog.04960). Full annotated list: section 3 of C-validation.md.
