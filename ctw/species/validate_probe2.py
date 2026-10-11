"""Spike C probe, round 3: (1) keyword extraction from terms/licence pages, (2) Crossref title lookups for the reference list.
Run from GitHub Actions; prints evidence to the job log."""
import json, re, sys, time, urllib.parse, urllib.request, http.cookiejar
urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())))
UA = {"User-Agent": "climate-twins-spike-c/0.1 (mailto:forest4science@gmail.com)"}
PAGES = [
    "https://ebird.org/about/products-access-terms-of-use",
    "https://www.audubon.org/content/policy-regarding-use-christmas-bird-count-data",
    "https://www.audubon.org/community-science/christmas-bird-count/access-christmas-bird-count-results",
    "https://ebba2.info/faq/",
    "https://butterfly-monitoring.net/ebms-data%20access",
    "https://adaptwest.databasin.org/pages/audubon-survival-by-degrees/",
    "https://research.fs.usda.gov/nrs/products/dataandtools/forest-ecosystem-atlas",
    "https://www.pwrc.usgs.gov/bbs/RawData/",
    "https://doi.org/10.2737/RDS-2019-0029",
    "https://doi.org/10.2737/RDS-2024-0020",
    "https://doi.org/10.2737/RDS-2024-0044",
]
KEY = re.compile(r"redistribut|commercial|attribut|licen[cs]e|cite|citation|permission|share|download|resolution|format|GeoTIFF|shapefile|raster|1 ?km|scenario|RCP|species|years|1966|1980|license|CC0|CC-BY|Creative Commons", re.I)
def get(u, n=3_000_000):
    r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40)
    return r.url, r.read(n).decode("utf8", "replace")
def text(h):
    h = re.sub(r"(?is)<(script|style|svg|noscript).*?</\1>", " ", h)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
for u in PAGES:
    try:
        fu, h = get(u)
        t = text(h)
        sents = re.split(r"(?<=[.!?]) ", t)
        hits = [s.strip()[:400] for s in sents if KEY.search(s) and 30 < len(s) < 600]
        print("\n=== %s -> %s (%d chars text)" % (u, fu, len(t)))
        for s in hits[:int(25)]:
            print("  *", s)
    except Exception as e:
        print("\n=== %s FAIL %s %s" % (u, type(e).__name__, str(e)[:150]))
REFS = [
 "Tingley Birds track their Grinnellian niche through a century of climate change",
 "Tingley Beissinger Detecting range shifts from historical species occurrences: new perspectives on old data",
 "Zhu Woodall Clark Failure to migrate: lack of tree range expansion in response to climate change",
 "Woodall Evidence of tree range shifts forest inventory seedlings",
 "Fei Divergence of species responses to climate change",
 "La Sorte Thompson Poleward shifts in winter ranges of North American birds",
 "Lenoir Species better track climate warming in the oceans than on land",
 "Lenoir A significant upward shift in plant species optimum elevation during the 20th century",
 "Hickling distributions of a wide range of taxonomic groups are expanding polewards",
 "Araujo Pearson Thuiller Erhard Validation of species-climate impact models under climate change",
 "Araujo Peterson Uses and misuses of bioclimatic envelope modeling",
 "Kramer-Schadt importance of correcting for sampling bias in MaxEnt species distribution models",
 "Fithian Bias correction in species distribution models: pooling survey and collection data for multiple species",
 "Beck Spatial bias in the GBIF database and its effect on modeling species geographic distributions",
 "Elith Leathwick Species distribution models: ecological explanation and prediction across space and time",
 "Zurell Benchmarking novel approaches for modelling species range dynamics",
 "Dormann Correlation and process in species distribution models: bridging a gap",
 "Bahn McGill Testing the predictive performance of distribution models",
 "Brun Model complexity affects species distribution projections under climate change",
 "Sofaer Development and delivery of species distribution models to inform decision-making",
 "Rapacciuolo Climatic associations of British species distributions show good transferability in time but low predictive accuracy for range change",
 "Dobrowski Modeling climate change velocity plants biodiversity",
 "Roberts Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure",
 "Brotons Bird species distribution models predict range changes hindcast Catalonia atlas",
 "Eskildsen Testing species distribution models across space and time: high latitude butterflies and recent warming",
 "Norberg A comprehensive evaluation of predictive performance of 33 species distribution models at species and community levels",
 "Webber Dormann Mesgaran novelty extrapolation species distribution models",
 "Kujala Not all data are equal: Influence of data type and amount in spatial conservation prioritisation hindcast",
 "Maguire Modeling species and community responses to past, present, and future episodes of climatic and ecological change",
 "Iverson Prasad Matthews Predicting potential changes in suitable habitat and distribution by 2100 for tree species of the eastern United States",
 "Prasad Iverson Liaw Newer classification and regression tree techniques: bagging and random forests for ecological prediction",
 "Hampe Petit Conserving biodiversity under climate change: the rear edge matters",
 "Langham Distribution shifts of North American birds Audubon climate change projections",
 "Stralberg Re-shuffling of species with climate disruption: a no-analog future for California birds",
 "Warren Increasing model complexity niche overlap equivalency tests ENMTools hindcast",
 "Warren Ecological niche modeling in Maxent: the importance of model complexity",
]
print("\n\n##### CROSSREF")
for q in REFS:
    try:
        url = "https://api.crossref.org/works?rows=2&select=DOI,title,author,issued,container-title&query.bibliographic=" + urllib.parse.quote(q)
        _, b = get(url, 200000)
        for it in json.loads(b)["message"]["items"][:2]:
            a = ", ".join(x.get("family", "") for x in it.get("author", [])[:3])
            print("Q:", q[:60], "|", a, "|", (it.get("title") or [""])[0][:110], "|", (it.get("container-title") or [""])[0], "|", it.get("issued", {}).get("date-parts", [[None]])[0][0], "|", it["DOI"])
    except Exception as e:
        print("Q:", q[:60], "FAIL", type(e).__name__, str(e)[:100])
    time.sleep(1.5)
