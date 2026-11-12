"""W4 probe: structure of BBS (ScienceBase), FIA DataMart and Forest Service RDS tree-projection datasets. Run in Actions; prints evidence."""
import io, json, re, sys, urllib.request, zipfile, csv, collections
UA = {"User-Agent": "climate-twins-w4/0.1 (mailto:forest4science@gmail.com)"}
def get(u, n=None, rng=None, timeout=90):
    h = dict(UA)
    if rng: h["Range"] = "bytes=0-%d" % rng
    r = urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=timeout)
    return r.url, r.read(n) if n else r.read()
def sect(t): print("\n" + "=" * 10, t, flush=True)

sect("BBS ScienceBase item")
try:
    _, b = get("https://www.sciencebase.gov/catalog/item/691cfb53d4be021d1d89b482?format=json")
    it = json.loads(b)
    print("title:", it.get("title"), "| rights:", it.get("rights"), "| lastUpdated:", it.get("provenance", {}).get("lastUpdated"))
    files = it.get("files", [])
    for f in files: print("  FILE", f.get("name"), f.get("size"), f.get("contentType"), f.get("url"))
    print("  child items:", it.get("hasChildren"))
    for k, v in (it.get("facets") or [{}])[0].items() if it.get("facets") else []: print("  facet", k, str(v)[:200])
except Exception as e:
    files = []; print("FAIL", type(e).__name__, e)
byname = {f["name"]: f["url"] for f in files}
def peek_csv(name, url, nrows=4):
    try:
        _, b = get(url, rng=300000)
        txt = b.decode("latin-1")
        lines = txt.splitlines()[:nrows + 1]
        print("--", name); [print("   ", l[:300]) for l in lines]
    except Exception as e: print("--", name, "FAIL", type(e).__name__, e)
for nm in ("Routes.csv", "SpeciesList.csv", "routes.csv", "SpeciesList.txt"):
    if nm in byname: peek_csv(nm, byname[nm], 6)
# state zip: download the smallest one and show its member headers
zips = [f for f in files if f["name"].lower().endswith(".zip")]
print("zip files:", [(f["name"], f.get("size")) for f in zips][:80])
if zips:
    z = sorted(zips, key=lambda f: f.get("size") or 0)
    for f in z[:1] + [x for x in z if x["name"].lower().startswith(("50-stop", "fifty"))][:1]:
        try:
            _, b = get(f["url"], timeout=300)
            zf = zipfile.ZipFile(io.BytesIO(b))
            print("ZIP", f["name"], zf.namelist()[:20])
            for m in zf.namelist()[:2]:
                with zf.open(m) as fh:
                    head = fh.read(1500).decode("latin-1").splitlines()[:4]
                print("  member", m); [print("     ", l[:300]) for l in head]
        except Exception as e: print("ZIP FAIL", f["name"], type(e).__name__, e)

sect("FIA DataMart")
BASE = "https://apps.fs.usda.gov/fia/datamart/CSV/"
for nm in ("DE_PLOT.csv", "DE_TREE.csv", "DE_SEEDLING.csv", "DE_COND.csv", "REF_SPECIES.csv", "REF_STATE_ELEV.csv", "DE_SURVEY.csv"):
    try:
        u, b = get(BASE + nm, rng=4000)
        lines = b.decode("latin-1").splitlines()[:3]
        print("--", nm, "OK"); [print("    ", l[:900]) for l in lines]
    except Exception as e: print("--", nm, "FAIL", type(e).__name__, e)
try:
    u, b = get(BASE + "DE_PLOT.csv", timeout=300)
    rows = list(csv.DictReader(io.StringIO(b.decode("latin-1"))))
    print("DE_PLOT rows", len(rows), "cols", list(rows[0].keys()))
    for col in ("MEASYEAR", "INVYR", "PLOT_STATUS_CD", "DESIGNCD", "KINDCD", "CYCLE", "SUBCYCLE", "ECOSUBCD"):
        if col in rows[0]: print("  ", col, sorted(collections.Counter(r[col] for r in rows).items())[:40])
    print("  sample", {k: rows[len(rows)//2][k] for k in ("LAT", "LON", "MEASYEAR", "INVYR", "CYCLE", "SUBCYCLE", "ELEV", "PREV_PLT_CN", "CN") if k in rows[0]})
except Exception as e: print("DE_PLOT full FAIL", type(e).__name__, e)

sect("Forest Service RDS pages")
for rid in ("RDS-2019-0029", "RDS-2024-0020"):
    for u in ("https://www.fs.usda.gov/rds/archive/Catalog/%s" % rid, "https://doi.org/10.2737/%s" % rid):
        try:
            fu, b = get(u, 3_000_000)
            h = b.decode("utf8", "replace")
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", h)))
            print("--", u, "->", fu, len(t), "chars")
            print("   TEXT:", t[:2500])
            links = sorted(set(re.findall(r'href="([^"]+\.(?:zip|tif|csv|xlsx|pdf|xml|txt))"', h, re.I)))
            print("   LINKS:", links[:60])
            for k in ("sugar maple", "Acer saccharum", "Quercus alba", "Pinus strobus", "Populus tremuloides"):
                print("   mentions", k, h.lower().count(k.lower()))
            break
        except Exception as e: print("--", u, "FAIL", type(e).__name__, e)
