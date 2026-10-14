"""Batch 6 selection: the last organisms to reach 300, chosen for taxonomic AND geographic spread (Africa, Asia, Eurasia, Oceania, South America; ferns, grasses, palms, bats-to-elephants, dragonflies, resident birds).
Every organism is fitted from ALL its observed records (W3_RANGE=all), so the curated "native" spec is every continent (it only decides which climate tiles are loaded).
Run: python -m ctw.species.batch6select  (needs api.gbif.org; cached in data/species/batch6_resolved.json)."""
from __future__ import annotations
import csv, json, urllib.parse, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from .s3select import ROOT, slug_id, pack

ALL = "EUROPE;ASIA;AFRICA;NORTH_AMERICA;SOUTH_AMERICA;OCEANIA"
G = "https://api.gbif.org/v1"
A = {  # scientific name -> group
    # mammals
    **{n: "mammal" for n in ["Loxodonta africana", "Panthera leo", "Giraffa camelopardalis", "Papio ursinus", "Hippopotamus amphibius", "Connochaetes taurinus", "Elephas maximus",
                              "Panthera tigris", "Rusa unicolor", "Muntiacus muntjak", "Tapirus terrestris", "Kobus ellipsiprymnus", "Ursus arctos", "Lynx lynx", "Ovis aries musimon"]},
    # reptiles
    **{n: "reptile" for n in ["Hemidactylus frenatus", "Calotes versicolor", "Naja naja", "Python bivittatus", "Chamaeleo chamaeleon", "Agama agama", "Varanus niloticus",
                               "Lacerta viridis", "Hemidactylus turcicus", "Testudo hermanni"]},
    # amphibians
    **{n: "amphibian" for n in ["Pelophylax ridibundus", "Xenopus laevis", "Hoplobatrachus tigerinus", "Sclerophrys regularis", "Kassina senegalensis", "Hyla arborea"]},
    # birds (residents)
    **{n: "bird" for n in ["Corvus macrorhynchos", "Passer montanus", "Streptopelia senegalensis", "Pycnonotus jocosus", "Acridotheres tristis", "Struthio camelus", "Garrulus glandarius",
                            "Dendrocopos major", "Copsychus saularis", "Cinnyris asiaticus", "Ploceus cucullatus", "Lamprotornis superbus", "Bubo bubo", "Strix aluco", "Turdoides striata"]},
    # insects and arachnids
    **{n: "insect_arachnid" for n in ["Sympetrum striolatum", "Aeshna cyanea", "Mantis religiosa", "Locusta migratoria", "Schistocerca gregaria", "Lucanus cervus", "Cetonia aurata", "Apis cerana",
                                       "Papilio demoleus", "Hypolimnas misippus", "Catopsilia pomona", "Gryllus bimaculatus", "Anopheles gambiae", "Aedes aegypti"]},
    # plants
    **{n: "wild_plant" for n in ["Pteridium aquilinum", "Phragmites australis", "Typha latifolia", "Ricinus communis", "Lantana camara", "Calotropis procera", "Rhododendron ponticum",
                                  "Dryopteris filix-mas", "Cyperus papyrus", "Imperata cylindrica", "Themeda triandra", "Cynodon dactylon", "Protea cynaroides", "Banksia serrata"]},
    **{n: "tree" for n in ["Vachellia tortilis", "Larix decidua", "Tectona grandis", "Phoenix dactylifera", "Elaeis guineensis", "Nothofagus pumilio", "Araucaria araucana", "Bambusa vulgaris", "Ceiba pentandra", "Adansonia digitata"]},
}


def _get(u):
    for _ in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "ct-batch6"}), timeout=60))
        except Exception:
            pass


def resolve(names, cache_name="batch6_resolved.json"):
    cache_f = ROOT / "data/species" / cache_name
    cache = json.load(open(cache_f)) if cache_f.exists() else {}

    def one(n):
        if n in cache:
            return n, cache[n]
        m = _get(f"{G}/species/match?name={urllib.parse.quote(n)}&kingdom={'Plantae' if n in PL else 'Animalia'}") or {}
        k = m.get("speciesKey") or m.get("usageKey")
        if not k or m.get("rank") not in ("SPECIES",) or m.get("matchType") == "NONE":
            return n, None
        v = _get(f"{G}/species/{k}/vernacularNames?limit=60") or {}
        eng = [x["vernacularName"] for x in v.get("results", []) if x.get("language") == "eng"]
        f = _get(f"{G}/occurrence/search?speciesKey={k}&facet=continent&facetLimit=10&limit=0&hasCoordinate=true&hasGeospatialIssue=false&occurrenceStatus=PRESENT") or {}
        cnt = {x["name"]: x["count"] for x in (f.get("facets") or [{}])[0].get("counts", [])}
        tot = sum(cnt.values())
        sh = ";".join(f"{a}:{round(b / (tot or 1), 3)}" for a, b in cnt.items())
        return n, dict(key=k, n=tot, common=(eng[0] if eng else n), shares=sh, canon=m.get("canonicalName"))
    with ThreadPoolExecutor(6) as ex:
        out = dict(ex.map(one, names))
    json.dump(out, open(cache_f, "w"), indent=0)
    return out


PL = {n for n, g in A.items() if g in ("wild_plant", "tree")}


def build():
    have = set()
    for t in ("pilot_v1", "batch1", "batch2", "batch3", "batch4", "batch5"):
        have |= {r["scientific_name"] for r in csv.DictReader(open(ROOT / f"data/species/{t}.csv", encoding="utf-8"))}
    names = [n for n in A if n not in have]
    R = resolve(names)
    rows, native = [], []
    for sci in names:
        r = R[sci]
        if not r or r["n"] < 4000 or r.get("canon") != sci:
            print("SKIP", sci, r and (r["n"], r.get("canon")))
            continue
        group = A[sci]
        rows.append({"id": slug_id(sci), "scientific_name": sci, "common_name": r["common"], "group": group, "kind": "wild", "native_continents_curated": ALL, "native_source": "curated",
                     "gbif_taxon_key": r["key"], "shortlist_rank": "", "region_assigned": "", "gbif_records_unfiltered": r["n"], "sample_cells05": 0, "iucn": "", "season": "",
                     "dl_batch": "", "status": "selected", "reason": f"{r['common']}: {r['n'] / 1e3:.0f} k GBIF records; chosen for taxonomic and geographic spread; fitted from all observed records"})
        native.append({"scientific_name": sci, "group": group, "native_spec": ALL, "season_scheme": "", "breeding_native_spec": "", "winter_native_spec": "", "gbif_continent_shares": r["shares"],
                       "share_outside_mask": 0.0, "outside_continents": "", "introduced_or_migration_note": "all-records fit: no native-range restriction",
                       "second_pass": "not applicable: all-records fit"})
    pack(rows)
    return rows, native


if __name__ == "__main__":
    rows, native = build()
    with open(ROOT / "data/species/batch6.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(ROOT / "data/species/native/curated_native_v6.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(native[0])); w.writeheader(); w.writerows(native)
    print(len(rows), Counter(r["group"] for r in rows), {k: round(sum(r["gbif_records_unfiltered"] for r in rows if r["dl_batch"] == k) / 1e6, 1) for k in sorted({r["dl_batch"] for r in rows})})
