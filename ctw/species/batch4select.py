"""Batch 4 selection (no birds, no fish). Candidates are the most-recorded species per group in GBIF that are not already in the shortlist or batches
(data/species/batch4_candidates.json, from GBIF occurrence facets on speciesKey), so every candidate is data-rich. Caveat: GBIF is strongly European
weighted, so this batch is too; regional balance is a later round. Animals: OUR curated native range (continent grammar of ctw.species.native); plants:
WCVP decides the native range. Run: python -m ctw.species.batch4select  (needs network access to api.gbif.org the first time; results are cached in
data/species/batch4_resolved.json)."""
from __future__ import annotations
import csv, json, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from .s3select import ROOT, EU, AS, AF, NA, SA, OC, slug_id, shares, outside, pack

G = "https://api.gbif.org/v1"
A = {  # name: (group, native spec, note)
    "Lepus europaeus": ("mammal", f"{EU};{AS}(W)", "native Europe and west Asia; introduced Americas, Australia, New Zealand (excluded)"),
    "Erinaceus europaeus": ("mammal", EU, "native western and central Europe; introduced New Zealand (excluded)"),
    "Cervus elaphus": ("mammal", f"{EU};{AS}(W);{AF}(N)", "native Europe, west Asia, North Africa; introduced elsewhere (excluded)"),
    "Meles meles": ("mammal", f"{EU};{AS}", "native Europe and Asia"),
    "Rupicapra rupicapra": ("mammal", f"{EU};{AS}(W)", "native European mountains and Turkey; introduced New Zealand (excluded)"),
    "Castor fiber": ("mammal", f"{EU};{AS}", "native Europe and Asia; reintroduced widely inside the mask"),
    "Talpa europaea": ("mammal", f"{EU};{AS}", "native Europe to Siberia"),
    "Lutra lutra": ("mammal", f"{EU};{AS};{AF}(N)", "native Eurasia and North Africa"),
    "Apodemus sylvaticus": ("mammal", f"{EU};{AF}(N)", "native Europe and north-west Africa"),
    "Myodes glareolus": ("mammal", f"{EU};{AS}", "native Europe to Siberia"),
    "Pipistrellus pipistrellus": ("mammal", f"{EU};{AS}(W);{AF}(N)", "native Europe, west Asia, North Africa; partial migrant, local movements"),
    "Peromyscus maniculatus": ("mammal", NA, "native North America"),
    "Phascolarctos cinereus": ("mammal", f"{OC}(AU)", "native eastern Australia"),
    "Martes foina": ("mammal", f"{EU};{AS}", "native Europe and central Asia"),
    "Lissotriton vulgaris": ("amphibian", f"{EU};{AS}", "native Europe to western Siberia"),
    "Crinia signifera": ("amphibian", f"{OC}(AU)", "native south-eastern Australia"),
    "Ichthyosaura alpestris": ("amphibian", EU, "native central Europe; introduced Britain, New Zealand (excluded)"),
    "Salamandra salamandra": ("amphibian", f"{EU};{AS}(W)", "native Europe and Turkey"),
    "Triturus cristatus": ("amphibian", f"{EU};{AS}", "native north-west Europe to Russia"),
    "Plethodon cinereus": ("amphibian", NA, "native north-eastern North America"),
    "Epidalea calamita": ("amphibian", EU, "native western and central Europe"),
    "Hyla arborea": ("amphibian", f"{EU};{AS}(W)", "native Europe and Turkey"),
    "Lithobates clamitans": ("amphibian", NA, "native eastern North America"),
    "Rana dalmatina": ("amphibian", f"{EU};{AS}(W)", "native southern and central Europe, Turkey"),
    "Limnodynastes tasmaniensis": ("amphibian", f"{OC}(AU)", "native south-eastern Australia"),
    "Pseudacris crucifer": ("amphibian", NA, "native eastern North America"),
    "Podarcis muralis": ("reptile", f"{EU};{AS}(W)", "native southern and central Europe; introduced Britain, North America (excluded)"),
    "Zootoca vivipara": ("reptile", f"{EU};{AS}", "native Europe and northern Asia"),
    "Lacerta agilis": ("reptile", f"{EU};{AS}", "native Europe and western Asia"),
    "Sceloporus occidentalis": ("reptile", NA, "native western North America"),
    "Natrix natrix": ("reptile", f"{EU};{AS};{AF}(N)", "native Eurasia and North Africa"),
    "Vipera berus": ("reptile", f"{EU};{AS}", "native Europe and northern Asia"),
    "Anolis carolinensis": ("reptile", NA, "native south-eastern US; introduced Hawaii, Pacific (excluded)"),
    "Coronella austriaca": ("reptile", f"{EU};{AS}(W)", "native Europe and west Asia"),
    "Tiliqua scincoides": ("reptile", f"{OC}(AU)", "native Australia"),
    "Thamnophis elegans": ("reptile", NA, "native western North America"),
    "Hierophis viridiflavus": ("reptile", EU, "native southern and western Europe"),
    "Pituophis catenifer": ("reptile", NA, "native western North America"),
    "Intellagama lesueurii": ("reptile", f"{OC}(AU)", "native eastern Australia"),
    "Pseudechis porphyriacus": ("reptile", f"{OC}(AU)", "native eastern Australia"),
    "Maniola jurtina": ("insect_arachnid", f"{EU};{AS}(W);{AF}(N)", "native Europe, west Asia, North Africa"),
    "Pararge aegeria": ("insect_arachnid", f"{EU};{AS}(W);{AF}(N)", "native Europe, west Asia, North Africa"),
    "Aglais io": ("insect_arachnid", f"{EU};{AS}", "native Europe and Asia"),
    "Pieris napi": ("insect_arachnid", f"{EU};{AS};{NA};{AF}(N)", "native Holarctic"),
    "Aglais urticae": ("insect_arachnid", f"{EU};{AS}", "native Europe and Asia; some migration inside the mask"),
    "Pieris brassicae": ("insect_arachnid", f"{EU};{AS};{AF}(N)", "native Europe, Asia, North Africa; introduced Chile, New Zealand (excluded)"),
    "Polyommatus icarus": ("insect_arachnid", f"{EU};{AS};{AF}(N)", "native Eurasia and North Africa"),
    "Gonepteryx rhamni": ("insect_arachnid", f"{EU};{AS};{AF}(N)", "native Eurasia and North Africa"),
    "Coenonympha pamphilus": ("insect_arachnid", f"{EU};{AS};{AF}(N)", "native Eurasia and North Africa"),
    "Aphantopus hyperantus": ("insect_arachnid", f"{EU};{AS}", "native Europe and Asia"),
    "Anthocharis cardamines": ("insect_arachnid", f"{EU};{AS}", "native Europe and Asia"),
    "Lycaena phlaeas": ("insect_arachnid", f"{EU};{AS};{NA};{AF}", "native Holarctic and east Africa"),
    "Ischnura elegans": ("insect_arachnid", f"{EU};{AS}(W);{AF}(N)", "native Europe, west Asia, North Africa"),
    "Anax imperator": ("insect_arachnid", f"{EU};{AS};{AF}", "native Europe, Asia, Africa"),
    "Araneus diadematus": ("insect_arachnid", f"{EU};{AS}", "native Europe and Asia; introduced North America (excluded)"),
    "Argiope bruennichi": ("insect_arachnid", f"{EU};{AS};{AF}(N)", "native Eurasia and North Africa; range expanding north inside the mask"),
    "Pisaura mirabilis": ("insect_arachnid", f"{EU};{AS}", "native Europe and Asia"),
    "Phidippus audax": ("insect_arachnid", NA, "native North America"),
    "Argiope aurantia": ("insect_arachnid", f"{NA};{SA}", "native North America to Central America"),
    "Phalangium opilio": ("insect_arachnid", f"{EU};{AS};{NA};{AF}(N)", "native Holarctic"),
}
P = {  # plants: native range from WCVP; spec picks tiles only
    "Plantago lanceolata": ("wild_plant", f"{EU};{AS};{AF}(N)"), "Dactylis glomerata": ("wild_plant", f"{EU};{AS};{AF}(N)"), "Hedera helix": ("wild_plant", f"{EU};{AS}(W);{AF}(N)"),
    "Calluna vulgaris": ("wild_plant", f"{EU};{AS}(W);{AF}(N)"), "Vaccinium myrtillus": ("wild_plant", f"{EU};{AS};{NA}"), "Hypericum perforatum": ("wild_plant", f"{EU};{AS};{AF}(N)"),
    "Lythrum salicaria": ("wild_plant", f"{EU};{AS};{AF}(N);{NA}"), "Chamaenerion angustifolium": ("wild_plant", f"{EU};{AS};{NA}"), "Juniperus communis": ("wild_plant", f"{EU};{AS};{NA}"),
    "Anemone nemorosa": ("wild_plant", f"{EU};{AS}(W)"), "Oxalis acetosella": ("wild_plant", f"{EU};{AS};{NA}"), "Dryopteris filix-mas": ("wild_plant", f"{EU};{AS};{NA};{AF}(N)"),
    "Equisetum arvense": ("wild_plant", f"{EU};{AS};{NA}"), "Iris pseudacorus": ("wild_plant", f"{EU};{AS}(W);{AF}(N)"), "Leucanthemum vulgare": ("wild_plant", f"{EU};{AS}"),
    "Epilobium hirsutum": ("wild_plant", f"{EU};{AS};{AF}"), "Tussilago farfara": ("wild_plant", f"{EU};{AS};{AF}(N)"), "Primula veris": ("wild_plant", f"{EU};{AS}"),
    "Lonicera periclymenum": ("wild_plant", f"{EU};{AF}(N)"), "Ilex aquifolium": ("wild_plant", f"{EU};{AS}(W);{AF}(N)"), "Cornus sanguinea": ("wild_plant", f"{EU};{AS}(W)"),
    "Silene dioica": ("wild_plant", EU), "Filipendula ulmaria": ("wild_plant", f"{EU};{AS}"), "Hypochaeris radicata": ("wild_plant", f"{EU};{AS}(W);{AF}(N)"),
    "Corylus avellana": ("tree", f"{EU};{AS}(W)"), "Quercus rotundifolia": ("tree", f"{EU};{AF}(N)"), "Alnus glutinosa": ("tree", f"{EU};{AS}(W);{AF}(N)"),
    "Populus tremula": ("tree", f"{EU};{AS}"), "Quercus suber": ("tree", f"{EU};{AF}(N)"),
}


def _get(u):
    for _ in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "ct-batch4"}), timeout=60))
        except Exception:
            pass


def resolve(names, cache_name="batch4_resolved.json"):
    cand = {c["sci"]: c for c in json.load(open(ROOT / "data/species/batch4_candidates.json"))}
    cache_f = ROOT / "data/species" / cache_name
    cache = json.load(open(cache_f)) if cache_f.exists() else {}

    def one(n):
        if n in cache:
            return n, cache[n]
        c = cand[n]; k = c["key"]
        v = _get(f"{G}/species/{k}/vernacularNames?limit=60") or {}
        eng = [x["vernacularName"] for x in v.get("results", []) if x.get("language") == "eng"]
        f = _get(f"{G}/occurrence/search?speciesKey={k}&facet=continent&facetLimit=10&limit=0&hasCoordinate=true&hasGeospatialIssue=false&occurrenceStatus=PRESENT") or {}
        cnt = {x["name"]: x["count"] for x in (f.get("facets") or [{}])[0].get("counts", [])}
        tot = sum(cnt.values()) or 1
        sh = ";".join(f"{a}:{round(b / tot, 3)}" for a, b in cnt.items())
        return n, dict(key=k, n=c["n"], fam=c["fam"], common=(eng[0] if eng else n), shares=sh)
    with ThreadPoolExecutor(6) as ex:
        out = dict(ex.map(one, names))
    json.dump(out, open(cache_f, "w"), indent=0)
    return out


def build():
    names = list(A) + list(P)
    R = resolve(names)
    rows, native = [], []
    for sci in names:
        r = R[sci]
        if sci in A:
            group, spec, note = A[sci]; source = "curated"
        else:
            group, spec = P[sci]; note, source = "WCVP native range (data)", "wcvp"
        sh = shares(r["shares"].replace("EUROPE", "EUROPE").replace("NORTH_AMERICA", "NORTH_AMERICA"))
        out_share, out_c = outside(spec, sh)
        common = r["common"]
        why = f"{common}: {r['n'] / 1e3:.0f} k GBIF records (most-recorded unused species of its group); {note}"
        rows.append({"id": slug_id(sci), "scientific_name": sci, "common_name": common, "group": group, "kind": "wild", "native_continents_curated": spec, "native_source": source,
                     "gbif_taxon_key": r["key"], "shortlist_rank": "", "region_assigned": "", "gbif_records_unfiltered": r["n"], "sample_cells05": 0, "iucn": "",
                     "season": "", "dl_batch": "", "status": "selected", "reason": why})
        if sci in A:
            native.append({"scientific_name": sci, "group": group, "native_spec": spec, "season_scheme": "", "breeding_native_spec": "", "winter_native_spec": "",
                           "gbif_continent_shares": r["shares"], "share_outside_mask": out_share, "outside_continents": out_c, "introduced_or_migration_note": note,
                           "second_pass": "consistent: record shares by continent all inside the curated continents" if out_share < 0.03 else f"outside share {out_share}: {out_c}"})
    pack(rows)
    return rows, native


if __name__ == "__main__":
    rows, native = build()
    with open(ROOT / "data/species/batch4.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(ROOT / "data/species/native/curated_native_v4.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(native[0])); w.writeheader(); w.writerows(native)
    print(len(rows), Counter(r["group"] for r in rows))
    print({k: round(sum(r["gbif_records_unfiltered"] for r in rows if r["dl_batch"] == k) / 1e6, 1) for k in sorted({r["dl_batch"] for r in rows})})
    for r in native:
        if float(r["share_outside_mask"]) >= 0.03: print("CHECK", r["scientific_name"], r["share_outside_mask"], r["outside_continents"])
