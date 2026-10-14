"""Batch 5 selection: the last 23 organisms to close the gap to 250 (no birds, no fish; mostly amphibians, reptiles, bats and dragonflies, in groups below 20 percent).
Same method as batch 4 (ctw.species.batch4select): GBIF-facet candidates (data/species/batch4_candidates.json), curated native ranges, WCVP not needed (no plants).
Run: python -m ctw.species.batch5select  (network access to api.gbif.org the first time; cached in data/species/batch5_resolved.json)."""
from __future__ import annotations
import csv
from collections import Counter
from .s3select import ROOT, EU, AS, AF, NA, SA, OC, slug_id, shares, outside, pack
from .batch4select import resolve

A = {
    "Pseudacris regilla": ("amphibian", NA, "native western North America"),
    "Anaxyrus boreas": ("amphibian", NA, "native western North America"),
    "Dryophytes versicolor": ("amphibian", NA, "native eastern North America"),
    "Notophthalmus viridescens": ("amphibian", NA, "native eastern North America"),
    "Ambystoma maculatum": ("amphibian", NA, "native eastern North America"),
    "Litoria peronii": ("amphibian", f"{OC}(AU)", "native eastern Australia"),
    "Litoria ewingii": ("amphibian", f"{OC}(AU)", "native south-eastern Australia; introduced New Zealand (excluded)"),
    "Crinia parinsignifera": ("amphibian", f"{OC}(AU)", "native eastern Australia"),
    "Sceloporus undulatus": ("reptile", NA, "native eastern and central North America"),
    "Plestiodon fasciatus": ("reptile", NA, "native eastern North America"),
    "Pantherophis alleghaniensis": ("reptile", NA, "native eastern North America"),
    "Storeria dekayi": ("reptile", NA, "native eastern North America to Central America"),
    "Coluber constrictor": ("reptile", NA, "native North America"),
    "Lampropholis delicata": ("reptile", f"{OC}(AU)", "native eastern Australia; introduced New Zealand, Hawaii (excluded)"),
    "Pseudonaja textilis": ("reptile", f"{OC}(AU)", "native eastern Australia"),
    "Crotalus atrox": ("reptile", NA, "native south-western US and Mexico"),
    "Myotis daubentonii": ("mammal", f"{EU};{AS}", "native Europe and Asia"),
    "Nyctalus noctula": ("mammal", f"{EU};{AS}", "native Europe and Asia; migratory in part"),
    "Capra ibex": ("mammal", EU, "native Alps; reintroduced across the Alps inside the mask"),
    "Coenagrion puella": ("insect_arachnid", f"{EU};{AS}(W)", "native Europe and west Asia"),
    "Orthetrum cancellatum": ("insect_arachnid", f"{EU};{AS};{AF}(N)", "native Eurasia and North Africa"),
    "Libellula quadrimaculata": ("insect_arachnid", f"{EU};{AS};{NA}", "native Holarctic; some migration inside the mask"),
    "Tettigonia viridissima": ("insect_arachnid", f"{EU};{AS}", "native Europe and Asia"),
}


def build():
    names = list(A)
    R = resolve(names, "batch5_resolved.json")
    rows, native = [], []
    for sci in names:
        r = R[sci]; group, spec, note = A[sci]
        out_share, out_c = outside(spec, shares(r["shares"]))
        rows.append({"id": slug_id(sci), "scientific_name": sci, "common_name": r["common"], "group": group, "kind": "wild", "native_continents_curated": spec, "native_source": "curated",
                     "gbif_taxon_key": r["key"], "shortlist_rank": "", "region_assigned": "", "gbif_records_unfiltered": r["n"], "sample_cells05": 0, "iucn": "", "season": "",
                     "dl_batch": "", "status": "selected", "reason": f"{r['common']}: {r['n'] / 1e3:.0f} k GBIF records (most-recorded unused species of its group); {note}"})
        native.append({"scientific_name": sci, "group": group, "native_spec": spec, "season_scheme": "", "breeding_native_spec": "", "winter_native_spec": "", "gbif_continent_shares": r["shares"],
                       "share_outside_mask": out_share, "outside_continents": out_c, "introduced_or_migration_note": note,
                       "second_pass": "consistent: record shares by continent all inside the curated continents" if out_share < 0.03 else f"outside share {out_share}: {out_c}"})
    pack(rows)
    return rows, native


if __name__ == "__main__":
    rows, native = build()
    with open(ROOT / "data/species/batch5.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(ROOT / "data/species/native/curated_native_v5.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(native[0])); w.writeheader(); w.writerows(native)
    print(len(rows), Counter(r["group"] for r in rows), {k: round(sum(r["gbif_records_unfiltered"] for r in rows if r["dl_batch"] == k) / 1e6, 1) for k in sorted({r["dl_batch"] for r in rows})})
    for r in native:
        if float(r["share_outside_mask"]) >= 0.03: print("CHECK", r["scientific_name"], r["share_outside_mask"], r["outside_continents"])
