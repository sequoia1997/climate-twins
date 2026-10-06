"""Spike C: reachability / metadata probe for validation data sources (run from GitHub Actions).
Prints status, content-type, size and (for pages) a text excerpt so licences can be read from the log."""
import json, re, sys, urllib.request

UA = {"User-Agent": "climate-twins-spike-c/0.1 (research probe)"}
SB = ["691cfb53d4be021d1d89b482", "6a39284a1ba49b4f9d9e0e99", "692f0fa7d4be026ff273a98e"]
HEAD = [
    "https://www.sciencebase.gov/catalog/item/%s?format=json" % s for s in SB
] + [
    "https://www.usgs.gov/data/2025-release-north-american-breeding-bird-survey-dataset-1966-2024",
    "https://www.usgs.gov/data/north-american-breeding-bird-survey-mapping-products-1966-2022",
    "https://data.usgs.gov/datacatalog/data/USGS:5d00efafe4b0573a18f5e03a",
    "https://www.usgs.gov/centers/eesc/science/north-american-breeding-bird-survey",
    "https://www.pwrc.usgs.gov/bbs/RawData/",
    "https://api.gbif.org/v1/occurrence/count?taxonKey=3189815&year=1970,1989",
    "https://api.gbif.org/v1/occurrence/count?taxonKey=3189815&year=1990,2020",
    "https://api.gbif.org/v1/occurrence/search?taxonKey=3189815&limit=0&facet=basisOfRecord&facetLimit=10",
    "https://www.gbif.org/terms/data-user",
    "https://science.ebird.org/en/status-and-trends/faqs",
    "https://science.ebird.org/en/status-and-trends/products-access/terms-of-use",
    "https://www.ebird.org/data/download",
    "https://ebird.org/science/use-ebird-data/ebird-data-terms-of-use",
    "https://www.ebba2.info/",
    "https://www.ebba2.info/about-the-atlas/data-use/",
    "https://www.ebba2.info/data-access/",
    "https://www.ebcc.info/index.php?ID=720",
    "https://www.audubon.org/climate/survivalbydegrees",
    "https://www.audubon.org/news/audubon-climate-model-data",
    "https://www.fs.usda.gov/nrs/atlas/",
    "https://www.nrs.fs.usda.gov/atlas/tree/",
    "https://www.fs.usda.gov/rds/archive/Catalog/RDS-2014-0010",
    "https://www.fs.usda.gov/rds/archive/Catalog/RDS-2014-0009",
    "https://research.fs.usda.gov/products/dataandtools/datasets",
    "https://apps.fs.usda.gov/fia/datamart/datamart.html",
    "https://apps.fs.usda.gov/fia/datamart/CSV/CSV_FILE_LIST.html",
    "https://apps.fs.usda.gov/fia/datamart/CSV/AK_TREE.csv",
    "https://apps.fs.usda.gov/fia/datamart/CSV/DE_TREE.csv",
    "https://netapp.cals.cornell.edu/neotrop/s_and_t/",
    "https://www.audubon.org/conservation/science/christmas-bird-count",
    "https://www.christmasbirdcount.org/",
    "https://gis.audubon.org/christmasbirdcount/",
    "https://www.butterfly-monitoring.net/",
    "https://butterfly-monitoring.net/ebms",
    "https://butterfly-monitoring.net/data-policy",
    "https://www.butterfly-monitoring.net/data",
    "https://zenodo.org/api/records?q=butterfly%20monitoring%20scheme&size=5",
    "https://zenodo.org/api/records?q=%22range%20shift%22%20species%20distribution%20hindcast&size=5",
    "https://www.pnas.org/doi/10.1073/pnas.1816094116",
    "https://api.crossref.org/works/10.1111/j.0906-7590.2008.5203.x",
    "https://api.crossref.org/works/10.1111/ecog.01881",
    "https://api.crossref.org/works/10.1111/j.1466-8238.2011.00683.x",
    "https://api.crossref.org/works/10.1111/2041-210X.12261",
    "https://api.crossref.org/works/10.1111/ecog.02881",
    "https://api.crossref.org/works/10.1111/j.1600-0587.2012.07348.x",
    "https://api.crossref.org/works/10.1111/j.1600-0587.2013.07872.x",
    "https://api.crossref.org/works/10.1111/j.1461-0248.2005.00792.x",
    "https://api.crossref.org/works/10.1111/j.1365-2699.2006.01594.x",
    "https://api.crossref.org/works/10.1126/science.1206432",
    "https://api.crossref.org/works/10.1111/ecog.00845",
    "https://api.crossref.org/works/10.1016/j.ecolmodel.2005.03.026",
    "https://api.crossref.org/works/10.1111/j.1472-4642.2010.00725.x",
    "https://api.crossref.org/works/10.1038/nature01286",
    "https://api.crossref.org/works/10.1111/j.1600-0587.2008.05742.x",
    "https://api.crossref.org/works/10.1111/geb.12268",
    "https://api.crossref.org/works/10.1111/ddi.12012",
    "https://api.crossref.org/works/10.1002/ecy.1738",
    "https://api.crossref.org/works/10.1111/j.1365-2486.2012.02779.x",
    "https://api.crossref.org/works/10.1111/1365-2664.12482",
    "https://api.crossref.org/works/10.1016/j.tree.2006.11.014",
    "https://api.crossref.org/works/10.1111/j.2006.0906-7590.04596.x",
    "https://api.crossref.org/works/10.1111/ecog.01132",
    "https://api.crossref.org/works/10.1038/nclimate1347",
    "https://api.crossref.org/works/10.1126/science.1210173",
    "https://api.crossref.org/works/10.1073/pnas.1114911109",
    "https://powo.science.kew.org/",
    "https://www.worldfloraonline.org/downloadData",
    "https://www.gbif.org/dataset/search?q=breeding%20bird%20atlas",
    "https://api.gbif.org/v1/dataset/search?q=breeding%20bird%20survey&limit=10",
    "https://api.gbif.org/v1/dataset/search?q=christmas%20bird%20count&limit=5",
    "https://api.gbif.org/v1/dataset/search?q=butterfly%20monitoring&limit=10",
    "https://api.gbif.org/v1/dataset/search?q=forest%20inventory&limit=5",
    "https://www.fs.usda.gov/rm/boise/AWAE/projects/NationalForestClimateChangeMaps.html",
    "https://www.nrs.fs.usda.gov/atlas/tree/",
    "https://www.fs.usda.gov/nrs/atlas/tree/",
    "https://doi.org/10.2737/RDS-2016-0035",
    "https://doi.org/10.2737/NRS-GTR-12",
    "https://doi.org/10.5066/P14SNUV4",
]
def strip(h):
    h = re.sub(r"(?s)<(script|style).*?</\1>", " ", h)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()

def probe(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={**UA, "Range": "bytes=0-60000"}), timeout=40)
        b = r.read(60000)
        ct = r.headers.get("content-type", ""); cl = r.headers.get("content-range") or r.headers.get("content-length")
        print("\n=== %s\nHTTP %s | %s | size/range: %s | final: %s" % (u, r.status, ct, cl, r.url))
        t = b.decode("utf8", "replace")
        if "json" in ct and "sciencebase" in u:
            j = json.loads(t) if len(b) < 60000 else {}
            print("TITLE", j.get("title")); print("LICENSE/RIGHTS", j.get("rights"), "|", j.get("purpose", "")[:200])
            for f in j.get("files", []):
                print("  FILE", f.get("name"), f.get("size"), f.get("contentType"), f.get("url"))
            for l in j.get("webLinks", [])[:8]:
                print("  LINK", l.get("title"), l.get("uri"))
            print("DATES", [(d.get("type"), d.get("dateString")) for d in j.get("dates", [])])
            print("BODY", strip(j.get("body", ""))[:1500])
        elif "json" in ct:
            print(t[:1200] if "crossref" not in u else json.dumps({k: (j := json.loads(t)).get("message", {}).get(k) for k in ("title", "container-title", "issued", "author")})[:600] if False else _cr(t))
        elif "text" in ct or "html" in ct or "xml" in ct:
            print(strip(t)[:1800])
        else:
            print("(binary) first bytes", b[:80])
    except Exception as e:
        print("\n=== %s\nFAIL %s %s" % (u, type(e).__name__, str(e)[:200]))

def _cr(t):
    try:
        m = json.loads(t)["message"]
        a = ", ".join("%s %s" % (x.get("family", ""), x.get("given", "")[:1]) for x in m.get("author", [])[:4])
        return "CROSSREF OK: %s | %s | %s | %s" % (a, (m.get("title") or [""])[0], (m.get("container-title") or [""])[0], m.get("issued", {}).get("date-parts"))
    except Exception:
        return t[:600]

if __name__ == "__main__":
    for u in (sys.argv[1:] or HEAD):
        probe(u)
