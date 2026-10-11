"""S3 batch 2 species selection (documented, reproducible): builds data/species/batch2.csv and data/species/native/curated_native_v2.csv from
data/species/shortlist_v1.csv plus the curated animal ranges below. Run: python -m ctw.species.s3select

Rules are in docs/species/S3-batch2.md. Native ranges of animals are OUR curation (continent grammar of ctw.species.native, deliberately generous:
the range check tests commission); migratory birds carry a breeding / winter spec for the seasonal cells (breeding-only fits).
Tuple: scientific name -> (group override or '', native spec, (breeding spec, winter spec) or None, introduced / migration note)
"""
from __future__ import annotations
import csv, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAP_RECORDS = 24_000_000          # per multi-species download (the S1 cap was 25 M)

EU, AS, AF, NA, SA, OC = "EUROPE", "ASIA", "AFRICA", "NORTH_AMERICA", "SOUTH_AMERICA", "OCEANIA"
# ---- animals: curated native range (group override for herps), season specs for migrants, note on introduced populations / movements
ANIMALS = {
    # birds, migrants and partial migrants (breeding-only fits)
    "Cathartes aura": ("", f"{NA};{SA}", (f"{NA};{SA}", f"{NA};{SA}"), "partial migrant: northern birds winter in the southern US and Mexico, southern populations resident; no known introduced population"),
    "Buteo jamaicensis": ("", NA, (NA, NA), "partial migrant: northern breeders winter in the southern US and Mexico; resident in the south"),
    "Ardea herodias": ("", NA, (NA, f"{NA};{SA}"), "partial migrant: northern breeders winter to Central America and northern South America"),
    "Corvus brachyrhynchos": ("", NA, (NA, NA), "partial migrant: northern birds winter in the central and southern US"),
    "Turdus merula": ("", f"{EU};{AS};{AF}(N)", (f"{EU};{AS};{AF}(N)", f"{EU};{AS};{AF}(N)"), "partial migrant (northern and eastern birds winter south and west); introduced in Australia and New Zealand, excluded by the mask"),
    "Fringilla coelebs": ("", f"{EU};{AS}(W);{AF}(N)", (f"{EU};{AS}(W);{AF}(N)", f"{EU};{AS}(W);{AF}(N)"), "partial migrant: northern and eastern birds winter in western Europe, the Mediterranean and North Africa; introduced New Zealand (excluded)"),
    "Motacilla alba": ("", f"{EU};{AS};{AF}(N)", (f"{EU};{AS};{AF}(N)", f"{EU};{AS};{AF}"), "migrant: Eurasian breeders winter in sub-Saharan Africa and south Asia, so the breeding mask is Eurasia and N Africa only"),
    "Buteo buteo": ("", f"{EU};{AS}", (f"{EU};{AS}", f"{EU};{AS};{AF}"), "partial migrant: Fennoscandian and Russian breeders winter in southern Europe, Africa and south Asia"),
    # birds, residents (all-year fits)
    "Cyanistes caeruleus": ("", f"{EU};{AS}(W);{AF}(N)", None, "resident"),
    "Corvus cornix": ("", f"{EU};{AS}(W)", None, "resident, a little altitudinal and northern movement; hybridises with the carrion crow"),
    "Trichoglossus moluccanus": ("", f"{OC}(AU)", None, "resident / nomadic, eastern Australia; Perth population is introduced (inside the mask)"),
    "Cacatua galerita": ("", f"{OC}(AU)", None, "resident, eastern and northern Australia (also New Guinea, not in the mask); introduced New Zealand (excluded)"),
    "Vanellus miles": ("", f"{OC}(AU)", None, "resident, northern and eastern Australia (also New Guinea and, self-colonised, New Zealand)"),
    "Manorina melanocephala": ("", f"{OC}(AU)", None, "sedentary, eastern Australia"),
    "Halcyon smyrnensis": ("", AS, None, "resident, some local movement"),
    "Dicrurus macrocercus": ("", AS, None, "resident with partial winter movement in the north"),
    "Centropus sinensis": ("", AS, None, "resident"),
    "Vanellus chilensis": ("", f"{SA};{NA}", None, "resident; northern edge reaches Panama and Costa Rica"),
    "Turdus rufiventris": ("", SA, None, "resident, partial southern winter movement"),
    "Rupornis magnirostris": ("", f"{SA};{NA}", None, "resident, Mexico to Argentina"),
    "Corvus albus": ("", AF, None, "resident (also Madagascar)"),
    "Dicrurus adsimilis": ("", AF, None, "resident, sub-Saharan Africa"),
    "Streptopelia capicola": ("", AF, None, "resident, eastern and southern Africa"),
    # mammals
    "Sciurus vulgaris": ("", f"{EU};{AS}", None, "native Europe to Siberia; introduced Italy locally (inside the mask)"),
    "Alces alces": ("", f"{EU};{AS};{NA}", None, "Holarctic; seasonal movements within the range; New Zealand introduction failed"),
    "Canis latrans": ("", NA, None, "native North America, range expanded east and south by itself (inside the mask)"),
    "Odocoileus hemionus": ("", NA, None, "native western North America; altitudinal migration"),
    "Lynx rufus": ("", NA, None, "native North America"),
    "Ursus americanus": ("", NA, None, "native North America"),
    "Trichosurus vulpecula": ("", f"{OC}(AU)", None, "native Australia; introduced New Zealand (excluded by the AU qualifier)"),
    "Wallabia bicolor": ("", f"{OC}(AU)", None, "native eastern Australia"),
    "Lama guanicoe": ("", SA, None, "native Andes and Patagonia"),
    "Phacochoerus africanus": ("", AF, None, "native sub-Saharan Africa"),
    "Macaca mulatta": ("", AS, None, "native south and east Asia; feral population in Florida (excluded)"),
    "Cerdocyon thous": ("", SA, None, "native South America east of the Andes"),
    # insects, arachnids
    "Coccinella septempunctata": ("", f"{EU};{AS};{AF}(N)", None, "native Palearctic; introduced North America (excluded); seasonal dispersal"),
    "Vespa crabro": ("", f"{EU};{AS}", None, "native Europe and Asia; introduced eastern North America (excluded)"),
    "Bombus terrestris": ("", f"{EU};{AS}(W);{AF}(N)", None, "native western Palearctic; introduced Tasmania, Chile, Japan (excluded)"),
    "Bombus pascuorum": ("", f"{EU};{AS}", None, "native Europe to Siberia"),
    "Papilio machaon": ("", f"{EU};{AS};{NA};{AF}(N)", None, "Holarctic; local movements only"),
    "Bombus bimaculatus": ("", NA, None, "native eastern North America"),
    "Amblyomma americanum": ("", NA, None, "native south-eastern US, range expanding north (inside the mask)"),
    "Heteronympha merope": ("", f"{OC}(AU)", None, "native south-eastern Australia"),
    "Papilio aegeus": ("", f"{OC}(AU)", None, "native Australia (and New Guinea region, not in the mask)"),
    "Oecophylla smaragdina": ("", f"{AS};{OC}(N)", None, "native south-east Asia to northern Australia"),
    "Argiope argentata": ("", f"{SA};{NA}", None, "native southern US to Argentina"),
    "Trithemis arteriosa": ("", f"{AF};{AS}(W)", None, "native Africa, Arabia and the Levant (second pass: 10 percent of records are in Asia, added W Asia); local movements"),
    # herps, fish
    "Thamnophis sirtalis": ("reptile", NA, None, "native North America"),
    "Chrysemys picta": ("reptile", NA, None, "native North America; introduced Europe and western Asia locally (excluded)"),
    "Anaxyrus americanus": ("amphibian", NA, None, "native eastern North America"),
    "Bufo bufo": ("amphibian", f"{EU};{AS};{AF}(N)", None, "native Europe, Asia, north-west Africa"),
    "Rana temporaria": ("amphibian", f"{EU};{AS}", None, "native Europe and north Asia"),
    "Anguis fragilis": ("reptile", f"{EU};{AS}(W)", None, "native Europe and western Asia"),
    "Tiliqua rugosa": ("reptile", f"{OC}(AU)", None, "native southern Australia"),
    "Limnodynastes peronii": ("amphibian", f"{OC}(AU)", None, "native eastern Australia"),
    "Stigmochelys pardalis": ("reptile", AF, None, "native eastern and southern Africa"),
    "Salvator merianae": ("reptile", SA, None, "native South America; feral in Florida (excluded)"),
    "Esox lucius": ("fish", f"{EU};{AS};{NA}", None, "Holarctic freshwater fish; stocked outside its native range locally (Italy, Iberia, Ireland, Alaska south)"),
    "Salmo trutta": ("fish", f"{EU};{AS}(W);{AF}(N)", None, "native Europe, west Asia, north-west Africa; stocked worldwide (the introduced part is outside the mask); anadromous forms"),
    "Hoplias malabaricus": ("fish", f"{SA};{NA}", None, "native Neotropical freshwater fish (Costa Rica to Argentina)"),
    "Macquaria ambigua": ("fish", f"{OC}(AU)", None, "native Murray-Darling and inland eastern Australia, stocked elsewhere in Australia"),
    "Clarias gariepinus": ("fish", f"{AF};{AS}(W)", None, "native Africa and the Levant; aquaculture escapes in Asia and Europe (excluded)"),
}
# ---- plants: native range comes from WCVP; this spec only chooses climate tiles and is the fall-back
PLANTS = {
    "Acer pseudoplatanus": (f"{EU};{AS}(W)", "tree"), "Sorbus aucuparia": (f"{EU};{AS}", "tree"), "Prunus spinosa": (f"{EU};{AS}(W);{AF}(N)", "tree"),
    "Crataegus monogyna": (f"{EU};{AS}(W);{AF}(N)", "tree"), "Sambucus nigra": (f"{EU};{AS}(W);{AF}(N)", "tree"), "Betula pendula": (f"{EU};{AS}", "tree"),
    "Liquidambar styraciflua": (NA, "tree"), "Liriodendron tulipifera": (NA, "tree"), "Cercis canadensis": (NA, "tree"), "Juniperus virginiana": (NA, "tree"),
    "Platanus occidentalis": (NA, "tree"), "Ficus religiosa": (AS, "tree"), "Bombax ceiba": (f"{AS};{OC}(N)", "tree"), "Syzygium cumini": (f"{AS};{OC}(N)", "tree"),
    "Sclerocarya birrea": (AF, "tree"), "Vachellia tortilis": (f"{AF};{AS}(W)", "tree"), "Vachellia caven": (SA, "tree"), "Euterpe oleracea": (SA, "tree"),
    "Guazuma ulmifolia": (f"{SA};{NA}", "tree"), "Acacia pycnantha": (f"{OC}(AU)", "tree"),
    "Achillea millefolium": (f"{EU};{AS};{NA}", "wild_plant"), "Glechoma hederacea": (f"{EU};{AS}", "wild_plant"), "Trifolium pratense": (f"{EU};{AS};{AF}(N)", "wild_plant"),
    "Alliaria petiolata": (f"{EU};{AS};{AF}(N)", "wild_plant"), "Cichorium intybus": (f"{EU};{AS};{AF}(N)", "wild_plant"), "Impatiens capensis": (NA, "wild_plant"),
    "Monotropa uniflora": (f"{NA};{AS};{EU};{SA}", "wild_plant"), "Ageratina altissima": (NA, "wild_plant"), "Phytolacca americana": (NA, "wild_plant"),
    "Aloe ferox": (AF, "wild_plant"), "Mauritia flexuosa": (SA, "wild_plant"),
}
CROPS = {   # origin continent only for information; crops are modelled where recorded, no native mask
    "Solanum tuberosum": SA, "Sorghum bicolor": AF, "Hordeum vulgare": AS, "Helianthus annuus": NA, "Brassica napus": EU, "Prunus persica": AS,
    "Persea americana": NA, "Ficus carica": AS, "Avena sativa": EU, "Phaseolus vulgaris": NA, "Punica granatum": AS,
}
RESERVES = {   # not run; used only when a species cannot be processed for a DATA reason (never for a gate failure)
    "Corvus corone": "carrion crow: resident Europe, as Eurasian blue tit", "Zonotrichia capensis": "rufous-collared sparrow: resident SA, 15 percent of records in North America",
    "Coracias caudatus": "lilac-breasted roller: resident Africa", "Streptopelia semitorquata": "red-eyed dove: resident Africa", "Milvus migrans": "black kite: migrant, mixed subspecies, curation not done",
    "Sylvilagus floridanus": "eastern cottontail: introduced Italy", "Tachyglossus aculeatus": "short-beaked echidna", "Pseudocheirus peregrinus": "ring-tailed possum",
    "Funambulus palmarum": "palm squirrel", "Xylocopa violacea": "violet carpenter bee", "Ixodes ricinus": "castor bean tick", "Bombus lapidarius": "red-tailed bumble bee",
    "Leptospermum scoparium": "manuka", "Ziziphus mucronata": "buffalo-thorn", "Ceiba pentandra": "kapok: pantropical", "Trema micranthum": "nettletree",
    "Juglans nigra": "black walnut", "Sassafras albidum": "sassafras", "Dodonaea viscosa": "pantropical, native range unclear",
}


def slug_id(sci: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", sci.lower()).strip("_")


def shares(s: str) -> dict:
    return {k: float(v) for k, v in (x.split(":") for x in (s or "").split(";") if ":" in x)}


def outside(spec: str, sh: dict) -> tuple[float, str]:
    cont = {t.split("(")[0].strip() for t in spec.split(";") if t.strip()}
    out = {k: v for k, v in sh.items() if k not in cont}
    return round(sum(out.values()), 3), ";".join(f"{k}:{v}" for k, v in out.items())


def pack(rows: list[dict]) -> None:
    """First-fit decreasing by unfiltered GBIF records, cap CAP_RECORDS per download; sets dl_batch b1..bn (heavy first)."""
    bins: list[list] = []
    for r in sorted(rows, key=lambda r: -int(r["gbif_records_unfiltered"])):
        n = int(r["gbif_records_unfiltered"])
        for b in bins:
            if b[0] + n <= CAP_RECORDS:
                b[0] += n; b[1].append(r); break
        else:
            bins.append([n, [r]])
    for i, (_, rs) in enumerate(bins, 1):
        for r in rs:
            r["dl_batch"] = f"b{i}"


SECOND_PASS = {   # animals with GBIF record share outside the curated continents (>= 3 percent): verdict of the self-check
    "Turdus merula": "outside share is the Australian and New Zealand introduction (well known, 19th century): correctly outside the mask",
    "Macaca mulatta": "outside share is the feral Florida / Puerto Rico population: correctly outside the mask",
    "Coccinella septempunctata": "outside share is the North American introduction (and spread): correctly outside the mask",
    "Vespa crabro": "outside share is the North American introduction (1800s): correctly outside the mask",
    "Trithemis arteriosa": "first pass said Africa only; 10 percent of records are in Asia (Arabia, Levant, Iran), which are native: mask widened to W Asia",
    "Salvator merianae": "outside share is the Florida feral population: correctly outside the mask",
    "Salmo trutta": "outside share is the North American stocking: correctly outside the mask (stocked fish elsewhere in Asia, Oceania and South America are not in the GBIF shares shown)",
}


def build():
    sl = {r["scientific_name"]: r for r in csv.DictReader(open(ROOT / "data/species/shortlist_v1.csv", encoding="utf-8"))}
    b1 = list(csv.DictReader(open(ROOT / "data/species/batch1.csv", encoding="utf-8")))
    reserves1 = [r["scientific_name"] for r in b1 if r["status"] == "reserve"]
    rows, native = [], []
    names = list(ANIMALS) + list(PLANTS) + list(CROPS)
    for sci in names:
        s = sl[sci]
        crop = sci in CROPS
        if sci in ANIMALS:
            go, spec, season, note = ANIMALS[sci]
            group = go or s["group"]
            source = "curated"
        elif sci in PLANTS:
            spec, group = PLANTS[sci]; note, season, source = "WCVP native range (data)", None, "wcvp"
        else:
            spec, group = CROPS[sci], "crop"; note, season, source = "crop: modelled where recorded", None, "none"
        sh = shares(s["occ_continent_shares"])
        out_share, out_c = outside(spec, sh)
        rec = int(float(s["gbif_records"]))
        why = f"{s['common_name']}: rank {s['rank_overall']}, {rec/1e6:.1f} M records" if rec >= 1e6 else f"{s['common_name']}: rank {s['rank_overall']}, {rec/1e3:.0f} k records"
        why += f"; {note}" + ("; one of the six batch-1 reserves" if sci in reserves1 else "")
        rows.append({"id": slug_id(sci), "scientific_name": sci, "common_name": s["common_name"], "group": group, "kind": "crop" if crop else "wild",
                     "native_continents_curated": "" if crop else spec, "native_source": source, "gbif_taxon_key": s["gbif_taxon_key"], "shortlist_rank": s["rank_overall"],
                     "region_assigned": s["region_assigned"], "gbif_records_unfiltered": rec, "sample_cells05": int(float(s["gbif_sample_cells05"] or 0)), "iucn": s["iucn_category"],
                     "season": "breeding" if season else "", "dl_batch": "", "status": "selected", "reason": why})
        if sci in ANIMALS:
            native.append({"scientific_name": sci, "group": group, "native_spec": spec, "season_scheme": "N" if season else "",
                           "breeding_native_spec": season[0] if season else "", "winter_native_spec": season[1] if season else "",
                           "gbif_continent_shares": s["occ_continent_shares"], "share_outside_mask": out_share, "outside_continents": out_c,
                           "introduced_or_migration_note": note,
                           "second_pass": SECOND_PASS.get(sci) or ("consistent: GBIF record shares by continent all inside the curated continents" if out_share < 0.03 else "CHECK")})
    pack(rows)
    for sci, why in {**{r: "batch-1 reserve" for r in []}, **RESERVES}.items():
        s = sl[sci]
        rows.append({"id": slug_id(sci), "scientific_name": sci, "common_name": s["common_name"], "group": s["group"], "kind": "wild", "native_continents_curated": "",
                     "native_source": "", "gbif_taxon_key": s["gbif_taxon_key"], "shortlist_rank": s["rank_overall"], "region_assigned": s["region_assigned"],
                     "gbif_records_unfiltered": int(float(s["gbif_records"])), "sample_cells05": int(float(s["gbif_sample_cells05"] or 0)), "iucn": s["iucn_category"],
                     "season": "", "dl_batch": "", "status": "reserve", "reason": f"reserve, not run: {why}"})
    missing = [x for x in reserves1 if x not in names]
    assert not missing, f"batch-1 reserves not selected: {missing}"
    return rows, native


if __name__ == "__main__":
    rows, native = build()
    cols = list(rows[0])
    with open(ROOT / "data/species/batch2.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    with open(ROOT / "data/species/native/curated_native_v2.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(native[0])); w.writeheader(); w.writerows(native)
    sel = [r for r in rows if r["status"] == "selected"]
    import json
    d = ROOT / "data/species/batch2_evidence/shift"; d.mkdir(parents=True, exist_ok=True)
    tmpl = json.loads((ROOT / "data/species/batch1_evidence/shift/pica_pica.json").read_text())
    tmpl["note"] = "S3: the W4 group verdict for birds (range-change hindcast failed) applied to a species W4 did not test; it is a group statement, not a test of this species"
    for r in sel:
        if r["group"] == "bird":
            (d / f"{r['id']}.json").write_text(json.dumps(tmpl, indent=1))
    from collections import Counter
    print(len(sel), Counter(r["group"] for r in sel))
    bt = {}
    for r in sel:
        bt[r["dl_batch"]] = bt.get(r["dl_batch"], 0) + r["gbif_records_unfiltered"]
    print({k: round(v / 1e6, 1) for k, v in bt.items()})
