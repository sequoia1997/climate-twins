"""Batch 3 species selection (no birds: the balance rule). Builds data/species/batch3.csv and data/species/native/curated_native_v3.csv from the
shortlist plus the curated animal ranges below, with the same rules as batch 2 (ctw.species.s3select). Run: python -m ctw.species.batch3select
Animals: OUR curated native range (continent grammar of ctw.species.native; deliberately generous, the range check tests commission). Plants: native range
from WCVP (data); the spec only picks climate tiles. Crops: modelled where recorded. Introduced populations fall outside the native mask and are excluded."""
from __future__ import annotations
import csv
from collections import Counter
from .s3select import ROOT, EU, AS, AF, NA, SA, OC, slug_id, shares, outside, pack

ANIMALS = {
    # mammals
    "Sus scrofa": ("", f"{EU};{AS};{AF}(N)", None, "native Eurasia and North Africa; introduced in the Americas, Australia and elsewhere (excluded)"),
    "Sciurus carolinensis": ("", NA, None, "native eastern North America; introduced Britain, Ireland, Italy, South Africa (excluded)"),
    "Panthera onca": ("", f"{SA};{NA}", None, "native Mexico to Argentina, formerly south-western US"),
    "Equus quagga": ("", AF, None, "native eastern and southern Africa"),
    "Syncerus caffer": ("", AF, None, "native sub-Saharan Africa"),
    "Crocuta crocuta": ("", AF, None, "native sub-Saharan Africa"),
    "Procavia capensis": ("", f"{AF};{AS}(W)", None, "native Africa and the Levant / Arabia"),
    "Didelphis marsupialis": ("", f"{SA};{NA}", None, "native Mexico to northern South America"),
    "Lycalopex culpaeus": ("", SA, None, "native Andes and Patagonia"),
    "Eutamias sibiricus": ("", AS, None, "native northern Asia; pet-trade populations in western Europe (excluded)"),
    "Capreolus pygargus": ("", AS, None, "native Siberia, Russian Far East, Korea, north-east China"),
    "Pteropus medius": ("", AS, None, "native Indian subcontinent"),
    "Axis axis": ("", AS, None, "native Indian subcontinent; introduced Hawaii, Australia, Americas (excluded)"),
    "Callosciurus finlaysonii": ("", AS, None, "native mainland south-east Asia; small introduced populations in Italy (excluded)"),
    # reptiles, amphibians
    "Lithobates catesbeianus": ("amphibian", NA, None, "native eastern North America; introduced western US, Europe, Asia, South America (excluded)"),
    "Varanus salvator": ("reptile", AS, None, "native south and south-east Asia"),
    "Gekko gecko": ("reptile", AS, None, "native south and south-east Asia; introduced Florida, Hawaii (excluded)"),
    "Varanus varius": ("reptile", f"{OC}(AU)", None, "native eastern Australia"),
    "Duttaphrynus melanostictus": ("amphibian", AS, None, "native south and south-east Asia; introduced Madagascar and Wallacea (excluded)"),
    "Crocodylus niloticus": ("reptile", AF, None, "native sub-Saharan Africa and Madagascar"),
    "Varanus niloticus": ("reptile", AF, None, "native sub-Saharan Africa; introduced Florida (excluded)"),
    "Boa constrictor": ("reptile", f"{SA};{NA}", None, "native Mexico to Argentina"),
    "Ameiva ameiva": ("reptile", SA, None, "native South America east of the Andes; introduced Florida (excluded)"),
    # insects, arachnids
    "Nephila pilipes": ("", f"{AS};{OC}(N)", None, "native south-east Asia to northern Australia"),
    "Vespula vulgaris": ("", f"{EU};{AS}", None, "native Eurasia; introduced Australia, New Zealand, the Americas, South Africa (excluded)"),
    "Leptinotarsa decemlineata": ("", NA, None, "native Mexico and the southern US plains, spread across North America; introduced Europe and Asia (excluded)"),
    "Dermacentor variabilis": ("", NA, None, "native eastern and central North America"),
    "Bombus lucorum": ("", f"{EU};{AS}", None, "native Europe to Siberia"),
    "Apis cerana": ("", AS, None, "native Asia; introduced New Guinea and Australia locally (excluded)"),
    "Papilio demoleus": ("", f"{AS};{AF};{OC}(AU)", None, "native Africa, Asia, Australia; introduced Caribbean (excluded)"),
    "Eurema hecabe": ("", f"{AS};{AF};{OC}", None, "native Africa, Asia, Australasia; local movements"),
    "Belenois aurota": ("", f"{AF};{AS}(W)", None, "native Africa and Arabia; migratory swarms inside the mask"),
    "Anartia amathea": ("", f"{SA};{NA}", None, "native Central and South America"),
    "Tetragonisca angustula": ("", f"{SA};{NA}", None, "native Neotropics, Mexico to Argentina"),
    "Trigona spinipes": ("", SA, None, "native South America"),
    "Lymantria dispar": ("", f"{EU};{AS};{AF}(N)", None, "native Europe, Asia, North Africa; introduced North America 1869 (excluded)"),
}
PLANTS = {
    "Fraxinus excelsior": (f"{EU};{AS}(W)", "tree"), "Acer platanoides": (f"{EU};{AS}(W)", "tree"), "Robinia pseudoacacia": (NA, "tree"),
    "Prunus serotina": (NA, "tree"), "Gleditsia triacanthos": (NA, "tree"), "Prunus virginiana": (NA, "tree"), "Acer palmatum": (AS, "tree"),
    "Morus alba": (AS, "tree"), "Cryptomeria japonica": (AS, "tree"), "Cedrus deodara": (AS, "tree"), "Eucalyptus globulus": (f"{OC}(AU)", "tree"),
    "Casuarina equisetifolia": (f"{AS};{OC}", "tree"), "Grevillea robusta": (f"{OC}(AU)", "tree"), "Anacardium occidentale": (SA, "tree"),
    "Tabebuia rosea": (f"{SA};{NA}", "tree"), "Ochroma pyramidale": (f"{SA};{NA}", "tree"), "Ficus sycomorus": (f"{AF};{AS}(W)", "tree"),
    "Vachellia erioloba": (AF, "tree"), "Alnus acuminata": (f"{SA};{NA}", "tree"), "Salix humboldtiana": (f"{SA};{NA}", "tree"),
    "Cordyline australis": (f"{OC}", "tree"), "Acacia mearnsii": (f"{OC}(AU)", "tree"),
    "Rosa multiflora": (AS, "wild_plant"), "Euphorbia hirta": (f"{SA};{NA}", "wild_plant"), "Chromolaena odorata": (f"{SA};{NA}", "wild_plant"),
    "Tridax procumbens": (f"{SA};{NA}", "wild_plant"), "Clitoria ternatea": (AS, "wild_plant"), "Celosia argentea": (f"{AF};{AS}", "wild_plant"),
    "Pittosporum undulatum": (f"{OC}(AU)", "wild_plant"), "Thunbergia alata": (AF, "wild_plant"), "Solanum mauritianum": (SA, "wild_plant"),
    "Cyanthillium cinereum": (f"{AS};{AF}", "wild_plant"), "Impatiens walleriana": (AF, "wild_plant"), "Tecomaria capensis": (AF, "wild_plant"),
    "Heliconia psittacorum": (f"{SA};{NA}", "wild_plant"), "Oxalis purpurea": (AF, "wild_plant"), "Baccharis latifolia": (SA, "wild_plant"),
    "Protea repens": (AF, "wild_plant"), "Leucadendron salignum": (AF, "wild_plant"), "Sphagneticola trilobata": (f"{SA};{NA}", "wild_plant"),
}
CROPS = {   # origin continent only for information; crops are modelled where recorded, no native mask
    "Cocos nucifera": OC, "Daucus carota": EU, "Prunus avium": EU, "Trifolium repens": EU, "Colocasia esculenta": AS, "Humulus lupulus": EU, "Rubus idaeus": EU,
    "Fagopyrum esculentum": AS, "Ribes nigrum": EU, "Capsicum annuum": NA, "Linum usitatissimum": AS, "Ananas comosus": SA, "Citrullus lanatus": AF,
    "Arachis hypogaea": SA, "Cucumis melo": AF, "Vaccinium corymbosum": NA, "Cucurbita pepo": NA, "Chenopodium quinoa": SA, "Vigna unguiculata": AF,
    "Pennisetum glaucum": AF, "Saccharum officinarum": OC,
}


def build():
    sl = {r["scientific_name"]: r for r in csv.DictReader(open(ROOT / "data/species/shortlist_v1.csv", encoding="utf-8"))}
    rows, native = [], []
    for sci in list(ANIMALS) + list(PLANTS) + list(CROPS):
        s = sl[sci]
        crop = sci in CROPS
        if sci in ANIMALS:
            go, spec, season, note = ANIMALS[sci]; group = go or s["group"]; source = "curated"
        elif sci in PLANTS:
            spec, group = PLANTS[sci]; note, season, source = "WCVP native range (data)", None, "wcvp"
        else:
            spec, group = CROPS[sci], "crop"; note, season, source = "crop: modelled where recorded", None, "none"
        sh = shares(s["occ_continent_shares"]); out_share, out_c = outside(spec, sh)
        rec = int(float(s["gbif_records"]))
        why = f"{s['common_name']}: rank {s['rank_overall']}, " + (f"{rec/1e6:.1f} M records" if rec >= 1e6 else f"{rec/1e3:.0f} k records") + f"; {note}"
        rows.append({"id": slug_id(sci), "scientific_name": sci, "common_name": s["common_name"], "group": group, "kind": "crop" if crop else "wild",
                     "native_continents_curated": "" if crop else spec, "native_source": source, "gbif_taxon_key": s["gbif_taxon_key"], "shortlist_rank": s["rank_overall"],
                     "region_assigned": s["region_assigned"], "gbif_records_unfiltered": rec, "sample_cells05": int(float(s["gbif_sample_cells05"] or 0)), "iucn": s["iucn_category"],
                     "season": "", "dl_batch": "", "status": "selected", "reason": why})
        if sci in ANIMALS:
            native.append({"scientific_name": sci, "group": group, "native_spec": spec, "season_scheme": "", "breeding_native_spec": "", "winter_native_spec": "",
                           "gbif_continent_shares": s["occ_continent_shares"], "share_outside_mask": out_share, "outside_continents": out_c, "introduced_or_migration_note": note,
                           "second_pass": "consistent: record shares by continent all inside the curated continents" if out_share < 0.03 else f"outside share {out_share}: {out_c}"})
    pack(rows)
    return rows, native


if __name__ == "__main__":
    rows, native = build()
    with open(ROOT / "data/species/batch3.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(ROOT / "data/species/native/curated_native_v3.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(native[0])); w.writeheader(); w.writerows(native)
    print(len(rows), Counter(r["group"] for r in rows))
    print({k: round(sum(r["gbif_records_unfiltered"] for r in rows if r["dl_batch"] == k) / 1e6, 1) for k in sorted({r["dl_batch"] for r in rows})})
    for r in native:
        if float(r["share_outside_mask"]) >= 0.03: print("CHECK", r["scientific_name"], r["share_outside_mask"], r["outside_continents"])
