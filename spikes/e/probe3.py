"""Spike E probe 2: quantify GloBI noise for pilot taxa, probe HOSTS/FungalRoot/trait datasets. Stdlib (+openpyxl for AVONET)."""
import json, sys, urllib.request, urllib.parse, collections, csv, io, re, zipfile, time
UA = {"User-Agent": "climate-twins-spike-e/0.1 (research probe)"}
def get(url, timeout=90, rng=None):
    h = dict(UA)
    if rng: h["Range"] = rng
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()
def J(url, **kw):
    try: return json.loads(get(url, **kw)[2])
    except Exception as e: print("  ERR", url[:100], e); return None

F = ["source_taxon_name","source_taxon_path","source_taxon_path_ranks","source_taxon_external_id","interaction_type",
     "target_taxon_name","target_taxon_path","target_taxon_path_ranks","target_taxon_external_id","study_title","study_source_citation"]
def globi(params, cap=40000, page=2000):
    rows, skip = [], 0
    while skip < cap:
        qs = urllib.parse.urlencode(dict(params, type="csv", limit=page, skip=skip)) + "".join("&field="+f for f in F)
        try: b = get("https://api.globalbioticinteractions.org/interaction?"+qs, timeout=180)[2]
        except Exception as e: print("  globi err", e); break
        recs = [{k:(v or "") for k,v in d.items()} for d in csv.DictReader(io.StringIO(b.decode("utf8","replace")))]
        rows += recs
        if len(recs) < page: break
        skip += page
    return rows
def rank(row, side, rk):
    p = (row.get(side+"_taxon_path") or "").split(" | "); r = (row.get(side+"_taxon_path_ranks") or "").split(" | ")
    for a, b in zip(p, r):
        if b == rk: return a
    return ""
def top(c, n=10): return c.most_common(n)

try:
    print("=== E. HOSTS (NHM Data Portal CKAN)")
    d = J("https://data.nhm.ac.uk/api/3/action/package_show?id=hosts")
    if d and d.get("success"):
        r = d["result"]; print("  title:", r.get("title"), "| license:", r.get("license_id"), r.get("license_title"), "| modified:", r.get("metadata_modified"))
        for x in r.get("resources", []): print("  resource:", x.get("id"), x.get("name"), x.get("format"), x.get("size"), x.get("url","")[:100])
        rid = r["resources"][0]["id"] if r.get("resources") else None
    else: rid = None; print("  package_show failed", str(d)[:200])
    if rid:
        for q in ("Danaus plexippus", "Quercus", "Asclepias syriaca"):
            dd = J("https://data.nhm.ac.uk/api/3/action/datastore_search?resource_id="+rid+"&q="+urllib.parse.quote(q)+"&limit=3")
            if dd and dd.get("success"):
                print(f"  q='{q}': total={dd['result'].get('total')} fields={[f['id'] for f in dd['result']['fields']][:14]}")
                for rec in dd["result"]["records"][:3]: print("    ", {k:v for k,v in rec.items() if k!='_id'})

except Exception as _e:
    import traceback; print('SECTION FAILED', repr(_e)); traceback.print_exc(limit=2)

try:
    print("=== F. FungalRoot in GBIF")
    d = J("https://api.gbif.org/v1/dataset/744edc21-8dd2-474e-8a0b-b8c3d56a3c2d")
    if d: print("  title:", d.get("title"), "| license:", d.get("license"), "| doi:", d.get("doi"), "| modified:", d.get("modified"))
    c = J("https://api.gbif.org/v1/occurrence/count?datasetKey=744edc21-8dd2-474e-8a0b-b8c3d56a3c2d"); print("  occurrence records:", c)
    for sp in ("Acer saccharum","Quercus robur","Vitis vinifera","Asclepias syriaca"):
        dd = J("https://api.gbif.org/v1/occurrence/search?datasetKey=744edc21-8dd2-474e-8a0b-b8c3d56a3c2d&scientificName="+urllib.parse.quote(sp)+"&limit=3")
        if dd:
            print(f"  {sp}: n={dd.get('count')}", [ (x.get('scientificName'), x.get('occurrenceRemarks'), x.get('verbatimScientificName')) for x in dd.get('results',[])[:2]])
            if dd.get('results'): print("    keys:", [k for k in dd['results'][0].keys() if k not in ('key','gbifID')][:40])

except Exception as _e:
    import traceback; print('SECTION FAILED', repr(_e)); traceback.print_exc(limit=2)

try:
    print("=== G. GloBI snapshot / Zenodo")
    d = J("https://zenodo.org/api/records?q=%22Global%20Biotic%20Interactions%22&size=5&sort=mostrecent")
    if d:
        for h in d["hits"]["hits"]:
            m = h["metadata"]; print("  ", h["id"], m.get("title","")[:90], "|", m.get("license",{}).get("id"), "|", m.get("publication_date"), "|", [(f["key"], f["size"]) for f in h.get("files",[])][:4])
    d = J("https://api.github.com/repos/globalbioticinteractions/globalbioticinteractions/releases/latest")
    if d: print("  github latest release:", d.get("tag_name"), d.get("published_at"))

except Exception as _e:
    import traceback; print('SECTION FAILED', repr(_e)); traceback.print_exc(limit=2)

try:
    print("=== H. Plant-pollinator networks (Web of Life / Mangal)")
    try:
        b = get("https://www.web-of-life.es/get_networks.php", timeout=120)[2]; recs = json.loads(b)
        nets = collections.Counter(r["network_name"].rsplit("_",1)[0] for r in recs)
        print("  Web of Life rows:", len(recs), "network types (prefix):", top(nets, 12), "n networks:", len({r['network_name'] for r in recs}))
        pl = [r for r in recs if r["network_name"].startswith("M_PL")]
        print("  plant-pollinator networks:", len({r['network_name'] for r in pl}), "rows", len(pl))
        sp = {r["species1"] for r in pl} | {r["species2"] for r in pl}
        for k in ("Danaus plexippus","Asclepias syriaca","Apis mellifera","Bombus","Quercus"):
            print("   ", k, sum(1 for s in sp if k in s))
    except Exception as e: print("  WoL ERR", e)
    d = J("https://mangal.io/api/v2/dataset?count=1", timeout=60)

except Exception as _e:
    import traceback; print('SECTION FAILED', repr(_e)); traceback.print_exc(limit=2)

try:
    print("=== I. Traits: licence/size via figshare + others")
    for aid, nm in ((16586228,"AVONET"), (4644424,"AmphiBIO")):
        d = J("https://api.figshare.com/v2/articles/%d" % aid)
        if d: print(f"  {nm}: title={d.get('title','')[:70]} license={d.get('license',{}).get('name')} files={[(f['name'], f['size']) for f in d.get('files',[])][:6]}")
    for u in ("https://esapubs.org/archive/ecol/E095/178/", "https://esapubs.org/archive/ecol/E095/045/", "https://esapubs.org/archive/ecol/E095/045/suppl-1.php",
              "https://api.github.com/repos/cropmodels/Recocrop/contents/", "https://api.github.com/repos/cropmodels/Recocrop/contents/inst"):
        try:
            s,h,b = get(u, timeout=60); t = re.sub(r"<[^>]+>", " ", b.decode("utf8","replace")); t = re.sub(r"\s+"," ",t)
            print("  ", u, s, t[:700] if "api.github" not in u else b[:900].decode())
        except Exception as e: print("  ", u, "ERR", e)
    d = J("https://api.crossref.org/works?query.bibliographic=COMBINE+coalesced+mammal+database+Soria&rows=2&select=DOI,title,link")
    if d: print("  crossref COMBINE:", [(i.get("DOI"), i.get("title")) for i in d["message"]["items"]])

except Exception as _e:
    import traceback; print('SECTION FAILED', repr(_e)); traceback.print_exc(limit=2)

try:
    print("=== J. AVONET rows for pilot birds")
    import subprocess, os
    os.makedirs("av", exist_ok=True)
    subprocess.run(["pip","install","-q","openpyxl"], check=False)
    try:
        b = get("https://ndownloader.figshare.com/files/34480856", timeout=300)[2]
        open("av/avonet.xlsx","wb").write(b)
        import openpyxl
        wb = openpyxl.load_workbook("av/avonet.xlsx", read_only=True)
        print("  sheets:", wb.sheetnames)
        for sn in wb.sheetnames:
            ws = wb[sn]; it = ws.iter_rows(values_only=True); hdr = next(it)
            print("  sheet", sn, "cols:", hdr[:40])
            if "AVONET1" in sn or "eBird" in sn:
                idx = {h:i for i,h in enumerate(hdr)}; n=0
                for row in it:
                    n += 1
                    if row[idx["Species1"]] in ("Turdus migratorius","Erithacus rubecula"):
                        print("   ", {k: row[idx[k]] for k in hdr if k in ("Species1","Mass","Hand-Wing.Index","Habitat","Migration","Trophic.Level","Primary.Lifestyle","Range.Size")})
                print("   rows:", n)
    except Exception as e: print("  AVONET ERR", e)

except Exception as _e:
    import traceback; print('SECTION FAILED', repr(_e)); traceback.print_exc(limit=2)
