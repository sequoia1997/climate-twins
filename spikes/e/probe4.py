"""Spike E probe 4: GloBI per-dataset licences, full HOSTS analysis, AVONET metadata, EcoCrop mirror, Tamme supplement. Stdlib + openpyxl."""
import json, urllib.request, urllib.parse, collections, csv, io, re, gzip, subprocess, os, zipfile
UA = {"User-Agent": "climate-twins-spike-e/0.1 (research probe)"}
def get(url, timeout=180):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r: return r.read()
def J(url): return json.loads(get(url))
def S(name, fn):
    print("=== " + name)
    try: fn()
    except Exception as e:
        import traceback; print("FAILED", repr(e)); traceback.print_exc(limit=2)

def globi_datasets():
    d = J("https://zenodo.org/api/records/22691479")
    for f in d["files"]:
        if f["key"] == "datasets.tsv":
            url = f["links"]["self"]; b = get(url).decode("utf8", "replace")
    rows = list(csv.DictReader(io.StringIO(b), delimiter="\t"))
    print("datasets.tsv rows:", len(rows), "columns:", list(rows[0].keys())[:30])
    for k in rows[0].keys():
        if "licen" in k.lower() or "rights" in k.lower():
            c = collections.Counter(r[k] for r in rows); print(" ", k, c.most_common(12))
    print(" sample:", {k: v[:80] for k, v in rows[0].items()})
S("A. GloBI per-dataset licences (Zenodo interpreted data products)", globi_datasets)

def hosts():
    r = J("https://data.nhm.ac.uk/api/3/action/package_show?id=hosts")["result"]
    url = [x["url"] for x in r["resources"] if x["format"] == "CSV"][0]
    b = get(url, timeout=300).decode("utf8", "replace")
    rows = list(csv.DictReader(io.StringIO(b)))
    print("rows:", len(rows), "cols:", list(rows[0].keys()))
    sp = lambda r: (r["Insect Genus"] + " " + r["Insect Species"]).strip()
    ins = {sp(r) for r in rows}; fam = {r["Insect Family"] for r in rows}
    print("distinct insect names:", len(ins), "insect families:", len(fam), "distinct host genera:", len({r['Hostplant Genus'] for r in rows}))
    print("insect families top:", collections.Counter(r["Insect Family"] for r in rows).most_common(8))
    # Danaus plexippus exact
    d = [r for r in rows if sp(r) == "Danaus plexippus"]
    print("Danaus plexippus rows:", len(d), "host families:", collections.Counter(r["Hostplant Family"] for r in d).most_common(8), "host genera:", collections.Counter(r["Hostplant Genus"] for r in d).most_common(8))
    print("  distinct Asclepias spp.:", len({r['Hostplant Species'] for r in d if r['Hostplant Genus']=='Asclepias'}), "locations:", collections.Counter(r["Location"] for r in d).most_common(8))
    # oak specialists
    byins = collections.defaultdict(list)
    for r in rows: byins[sp(r)].append(r)
    oak = {k for k, v in byins.items() if any(x["Hostplant Genus"] == "Quercus" for x in v)}
    print("insect spp. with >=1 Quercus record:", len(oak), "of which Lepidoptera in HOSTS (all):", len(ins))
    spec = collections.Counter()
    for k in oak:
        v = byins[k]; hg = {x["Hostplant Genus"] for x in v}; hf = {x["Hostplant Family"] for x in v}
        n = len(v)
        spec["records>=3"] += n >= 3
        if n >= 3:
            spec["  only Quercus genus"] += hg == {"Quercus"}
            spec["  only Fagaceae"] += hf == {"Fagaceae"}
            spec["  <=3 host genera"] += len(hg) <= 3
            spec["  >=10 host genera"] += len(hg) >= 10
    print("oak users:", dict(spec))
    print("records per insect species: median", sorted(len(v) for v in byins.values())[len(byins)//2], "share with exactly 1 record:", sum(1 for v in byins.values() if len(v)==1)/len(byins))
    for nm in ("Hyphantria cunea", "Operophtera brumata", "Tortrix viridana", "Aglais io", "Papilio machaon", "Vanessa atalanta", "Pieris rapae", "Battus philenor"):
        v = byins.get(nm, []); print(f"  {nm}: rows={len(v)} host families={collections.Counter(x['Hostplant Family'] for x in v).most_common(4)}")
S("B. HOSTS full CSV analysis", hosts)

def avonet():
    subprocess.run(["pip", "install", "-q", "openpyxl"], check=False)
    import openpyxl
    b = get("https://ndownloader.figshare.com/files/34480856", timeout=300); os.makedirs("av", exist_ok=True); open("av/a.xlsx", "wb").write(b)
    wb = openpyxl.load_workbook("av/a.xlsx", read_only=True); ws = wb["Metadata"]
    for row in ws.iter_rows(values_only=True):
        if row[0] in ("Hand-Wing.Index", "Migration", "Mass", "Range.Size", "Habitat", "Primary.Lifestyle", "Trophic.Niche"): print(" ", {k: (str(v)[:230] if v else v) for k, v in zip(("var", "desc", "type", "units", "src"), row)})
    ws = wb["AVONET1_BirdLife"]; it = ws.iter_rows(values_only=True); h = next(it); ix = {k: i for i, k in enumerate(h)}
    mig = collections.Counter(); hwi = []
    for r in it:
        mig[r[ix["Migration"]]] += 1
        if r[ix["Hand-Wing.Index"]] is not None: hwi.append(float(r[ix["Hand-Wing.Index"]]))
    hwi.sort(); print("Migration code counts:", dict(mig), "HWI n=%d min=%.1f p10=%.1f median=%.1f p90=%.1f max=%.1f" % (len(hwi), hwi[0], hwi[len(hwi)//10], hwi[len(hwi)//2], hwi[9*len(hwi)//10], hwi[-1]))
S("C. AVONET metadata and distributions", avonet)

def ecocrop():
    for u in ("https://api.github.com/repos/cropmodels/Recocrop/contents/inst/parameters", "https://api.github.com/repos/cropmodels/Recocrop/contents/data", "https://api.github.com/repos/cropmodels/Recocrop/license", "https://gaez.fao.org/pages/ecocrop-search"):
        try:
            b = get(u, timeout=60); t = b.decode("utf8", "replace")
            if "api.github" in u: print(u, "->", t[:700].replace("\n", " "))
            else: print(u, "-> OK len", len(b), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:300])
        except Exception as e: print(u, "ERR", e)
S("D. EcoCrop mirrors", ecocrop)

def tamme():
    t = get("https://esapubs.org/archive/ecol/E095/045/suppl-1.php").decode("utf8", "replace")
    print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[600:1800]); print(re.findall(r'href="([^"]+\.(?:csv|txt|zip|xlsx?|R|pdf))"', t))
S("E. Tamme 2014 supplement", tamme)
