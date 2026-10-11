"""Spike E probe: queries GloBI and probes dataset endpoints. Stdlib only. Prints compact results."""
import json, sys, urllib.request, urllib.parse, collections, csv, io, time
UA = {"User-Agent": "climate-twins-spike-e/0.1 (research probe)"}

def get(url, timeout=60, rng=None, method="GET"):
    h = dict(UA)
    if rng: h["Range"] = rng
    req = urllib.request.Request(url, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()

def probe(url, rng="bytes=0-399"):
    try:
        s, h, b = get(url, rng=rng, timeout=40)
        print(f"PROBE {url}\n  -> {s} type={h.get('Content-Type')} len={h.get('Content-Length')} range={h.get('Content-Range')}\n  head={b[:300]!r}")
    except Exception as e:
        print(f"PROBE {url}\n  -> ERROR {e}")

FIELDS = "source_taxon_name,source_taxon_external_id,interaction_type,target_taxon_name,target_taxon_external_id,study_citation"

def globi(params, cap=6000, page=1000):
    rows = []; skip = 0
    while skip < cap:
        q = dict(params); q.update(type="csv", limit=page, skip=skip, field=None)
        qs = urllib.parse.urlencode({k: v for k, v in q.items() if v is not None})
        qs += "".join("&field=" + f for f in FIELDS.split(","))
        try:
            s, h, b = get("https://api.globalbioticinteractions.org/interaction?" + qs, timeout=120)
        except Exception as e:
            print("  globi error", e); break
        recs = list(csv.DictReader(io.StringIO(b.decode("utf8", "replace"))))
        rows += recs
        if len(recs) < page: break
        skip += page
    return rows

print("=== GloBI interaction types")
try:
    s, h, b = get("https://api.globalbioticinteractions.org/interactionTypes")
    d = json.loads(b); print(str(d)[:600])
except Exception as e: print("ERR", e)

PILOT = {"sugar maple": "Acer saccharum", "English oak": "Quercus robur", "monarch": "Danaus plexippus",
 "American robin": "Turdus migratorius", "European robin": "Erithacus rubecula",
 "blacklegged tick": "Ixodes scapularis", "wine grape": "Vitis vinifera",
 "milkweed A": "Asclepias syriaca", "Asclepias curassavica": "Asclepias curassavica"}
CAP = 6000
for common, sci in PILOT.items():
    print(f"=== GloBI {common} ({sci})")
    for role, key in (("as source", "sourceTaxon"), ("as target", "targetTaxon")):
        rows = globi({key: sci}, cap=CAP)
        n = len(rows)
        print(f"  {role}: {n} rows fetched (cap {CAP}{', TRUNCATED' if n >= CAP else ''})")
        by_type = collections.Counter(r["interaction_type"] for r in rows)
        print("   types:", dict(by_type.most_common(8)))
        other = "target_taxon_name" if role == "as source" else "source_taxon_name"
        c = collections.Counter((r["interaction_type"], r[other]) for r in rows)
        print("   distinct partners:", len({r[other] for r in rows}))
        print("   top:", [(k[0], k[1], v) for k, v in c.most_common(10)])
        cites = collections.Counter(r["study_citation"][:70] for r in rows)
        print("   n sources(citations):", len(cites), "top:", cites.most_common(3))
        ids = sum(1 for r in rows if r["source_taxon_external_id"] or r["target_taxon_external_id"])
        print("   rows with any external id:", ids, "sample ids:", [(r["source_taxon_external_id"], r["target_taxon_external_id"]) for r in rows[:2]])

print("=== Monarch eats vs milkweed names")
rows = globi({"sourceTaxon": "Danaus plexippus", "interactionType": "eats"}, cap=CAP)
c = collections.Counter(r["target_taxon_name"] for r in rows)
print(len(rows), "monarch eats rows;", c.most_common(25))
print("=== Oak specialists: Quercus robur targets, eatenBy")
rows = globi({"targetTaxon": "Quercus robur", "interactionType": "eatenBy"}, cap=CAP)
c = collections.Counter(r["source_taxon_name"] for r in rows)
print(len(rows), "rows; distinct consumers", len(c), c.most_common(15))
print("=== Ixodes scapularis hosts")
for t in ("hasHost", "interactsWith", "parasiteOf", "ectoparasiteOf"):
    rows = globi({"sourceTaxon": "Ixodes scapularis", "interactionType": t}, cap=CAP)
    c = collections.Counter(r["target_taxon_name"] for r in rows)
    print(t, len(rows), "distinct", len(c), c.most_common(12))

print("=== Snapshot probes")
for u in ["https://depot.globalbioticinteractions.org/snapshot/target/data/tsv/interactions.tsv.gz",
          "https://depot.globalbioticinteractions.org/snapshot/target/data/tsv/",
          "https://github.com/globalbioticinteractions/globalbioticinteractions/releases",
          "https://zenodo.org/api/records?q=%22Global%20Biotic%20Interactions%22&size=3&sort=mostrecent",
          "https://api.globalbioticinteractions.org/info",
          "https://www.nhm.ac.uk/our-science/data/hostplants/search/index.dsml",
          "https://data.nhm.ac.uk/api/3/action/package_search?q=host%20plants&rows=5",
          "https://api.gbif.org/v1/dataset?q=FungalRoot&limit=5",
          "https://api.gbif.org/v1/dataset?q=HOSTS%20database&limit=5",
          "https://www.fungalroot.org/",
          "https://www.web-of-life.es/",
          "https://www.web-of-life.es/get_networks.php",
          "https://mangal.io/api/v2/dataset?count=3",
          "https://figshare.com/ndownloader/articles/16586228/versions/5",
          "https://api.figshare.com/v2/articles/16586228",
          "https://api.figshare.com/v2/articles/3563475",
          "https://api.figshare.com/v2/articles/13000121",
          "https://ecocrop.fao.org/ecocrop/srv/en/home",
          "https://reptile-database.reptarium.cz/advanced_search?taxon=Squamata&submit=Search",
          "https://www.try-db.org/TryWeb/Home.php",
          "https://raw.githubusercontent.com/cropmodels/Recocrop/master/inst/ecocrop/ecocropDB.csv"]:
    probe(u)
