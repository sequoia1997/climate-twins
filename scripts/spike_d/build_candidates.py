"""SPIKE D: build the ranked species candidate list from public popularity signals.

Run from GitHub Actions only (needs iNaturalist, GBIF, Wikipedia, Wikimedia APIs).
No credentials are used or printed. Output: data/species/*.csv and a stats json.
Usage: python scripts/spike_d/build_candidates.py [--outdir data/species] [--work work-spike-d] [--limit-test]
"""
import argparse, csv, json, math, os, random, sys, time, urllib.parse, collections
from concurrent.futures import ThreadPoolExecutor
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seeds as S

UA = "ClimateTwinsSpikeD/0.1 (education project; https://github.com/sequoia1997/climate-twins)"
INAT = "https://api.inaturalist.org/v1"
GBIF = "https://api.gbif.org/v1"
WIKI = "https://en.wikipedia.org/w/api.php"
PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
PV_START, PV_END = "20250901", "20260831"   # 12 full months

REGIONS = ["AFRICA", "ASIA", "EUROPE", "NORTH_AMERICA", "SOUTH_AMERICA", "OCEANIA"]
SHARES = {"AFRICA": .15, "ASIA": .22, "EUROPE": .15, "NORTH_AMERICA": .18, "SOUTH_AMERICA": .17, "OCEANIA": .13}
BOXES = {  # swlat, swlng, nelat, nelng  (rough; final region comes from GBIF record shares)
    "AFRICA": (-35, -18, 37, 52), "ASIA": (-8, 52, 70, 150), "EUROPE": (35, -11, 71, 40),
    "NORTH_AMERICA": (7, -168, 72, -52), "SOUTH_AMERICA": (-56, -82, 12.5, -34), "OCEANIA": (-48, 110, -10, 180)}
# group -> (iNat taxon ids, pages of 200 per region, candidate quota, shortlist quota)
GROUPS = {
    "tree": ([47126], 8, 180, 90), "wild_plant": ([47126], 8, 80, 40), "crop": ([], 0, 80, 40),
    "bird": ([3], 3, 180, 90), "mammal": ([40151], 3, 80, 40), "herp": ([26036, 20978], 2, 40, 20),
    "insect_arachnid": ([47158, 47119], 3, 60, 30), "fish": ([], 0, 20, 10)}
POOL_FACTOR = 1.8   # enrich top POOL_FACTOR x quota per group (per region share) by iNat count

sess = requests.Session()
sess.headers.update({"User-Agent": UA, "Accept": "application/json"})
CACHE = {}

def get(url, params=None, tries=5, pause=0.0):
    key = url + "?" + urllib.parse.urlencode(sorted((params or {}).items()))
    if key in CACHE: return CACHE[key]
    for i in range(tries):
        try:
            r = sess.get(url, params=params, timeout=60)
            if r.status_code == 200:
                j = r.json(); CACHE[key] = j
                if pause: time.sleep(pause)
                return j
            if r.status_code in (404, 400, 422): return None
            time.sleep(2 ** i + 1)
        except Exception:
            time.sleep(2 ** i + 1)
    return None

def save_cache(path):
    try:
        snap = dict(CACHE)
        with open(path, "w") as fh: json.dump(snap, fh)
    except Exception as ex:
        print("cache save failed", repr(ex), flush=True)

def log(*a): print(*a, flush=True)

# ---------------- iNaturalist pools ----------------
def inat_pool(group):
    taxa, pages, _, _ = GROUPS[group]
    out = {}
    for region, (swlat, swlng, nelat, nelng) in BOXES.items():
        for tid in taxa:
            for page in range(1, pages + 1):
                j = get(INAT + "/observations/species_counts", dict(
                    taxon_id=tid, swlat=swlat, swlng=swlng, nelat=nelat, nelng=nelng,
                    quality_grade="research", per_page=200, page=page, locale="en"), pause=1.1)
                if not j or not j.get("results"): break
                for r in j["results"]:
                    t = r["taxon"]
                    if t.get("rank") != "species": continue
                    e = out.setdefault(t["name"], dict(inat_id=t["id"], name=t["name"], common=t.get("preferred_common_name"),
                                                        inat_obs=t.get("observations_count"), regional=0, qregion=region))
                    if r["count"] > e["regional"]: e["regional"] = r["count"]; e["qregion"] = region
        log(f"  pool {group} {region}: {len(out)} species so far")
    return out

def inat_lookup(name):
    j = get(INAT + "/taxa", dict(q=name, rank="species", per_page=5, locale="en"), pause=1.1)
    for t in (j or {}).get("results", []):
        if t["name"].lower() == name.lower():
            return dict(inat_id=t["id"], name=t["name"], common=t.get("preferred_common_name"), inat_obs=t.get("observations_count"))
    return None

# ---------------- GBIF ----------------
def gbif_match(name):
    j = get(GBIF + "/species/match", dict(name=name, strict="false", verbose="false"))
    if not j or j.get("matchType") in (None, "NONE"): return None
    return j

def gbif_enrich(key):
    d = {}
    j = get(f"{GBIF}/species/{key}/iucnRedListCategory")
    d["iucn"] = (j or {}).get("category") or "NE"
    base = dict(taxonKey=key, hasCoordinate="true", hasGeospatialIssue="false", occurrenceStatus="PRESENT")
    j = get(GBIF + "/occurrence/search", dict(base, limit=0, facet=["continent", "country"], facetLimit=60))
    d["gbif_records"] = (j or {}).get("count", 0)
    d["continents"] = {}; d["countries"] = {}
    for f in (j or {}).get("facets", []):
        tgt = d["continents"] if f["field"] == "CONTINENT" else d["countries"]
        for c in f["counts"]: tgt[c["name"]] = c["count"]
    n = d["gbif_records"]
    if n >= 20:
        off = random.Random(key).randint(0, max(0, min(n - 300, 90000)))
        j = get(GBIF + "/occurrence/search", dict(base, limit=300, offset=off))
        pts = [(r["decimalLatitude"], r["decimalLongitude"]) for r in (j or {}).get("results", [])
               if "decimalLatitude" in r and "decimalLongitude" in r]
        if len(pts) >= 20:
            la = sorted(p[0] for p in pts); lo = sorted(p[1] for p in pts)
            q = lambda v, f: v[min(len(v) - 1, int(f * len(v)))]
            d.update(lat_p5=q(la, .05), lat_p95=q(la, .95), lon_p5=q(lo, .05), lon_p95=q(lo, .95),
                     cells05=len({(math.floor(a * 2), math.floor(b * 2)) for a, b in pts}), sample_n=len(pts))
    pr = get(f"{GBIF}/species/{key}/speciesProfiles")
    prof = (pr or {}).get("results", [])
    d["marine_profile"] = any(p.get("marine") for p in prof) and not any(p.get("terrestrial") for p in prof)
    return d

# ---------------- Wikipedia ----------------
def wiki_titles(names):
    """name -> (title, wikidata id) via redirects of the scientific name."""
    res = {}
    names = list(names)
    for i in range(0, len(names), 40):
        chunk = names[i:i + 40]
        j = get(WIKI, dict(action="query", format="json", titles="|".join(chunk), redirects=1, prop="pageprops",
                           ppprop="wikibase_item", formatversion=2), pause=0.3)
        if not j: continue
        q = j.get("query", {})
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
        pages = {p["title"]: p for p in q.get("pages", []) if not p.get("missing")}
        for n in chunk:
            t = norm.get(n, n); t = redir.get(t, t)
            p = pages.get(t)
            if p: res[n] = (p["title"], p.get("pageprops", {}).get("wikibase_item"))
    return res

def pageviews(title):
    u = f"{PV}/{urllib.parse.quote(title.replace(' ', '_'), safe='')}/monthly/{PV_START}/{PV_END}"
    j = get(u)
    return sum(i["views"] for i in (j or {}).get("items", [])) if j else None

# ---------------- build ----------------
def pct_rank(vals):
    """vals: list of numbers or None -> percentile (0..1) of log10(1+v); None -> 0."""
    xs = sorted(math.log10(1 + v) for v in vals if v is not None)
    out = []
    for v in vals:
        if v is None or not xs: out.append(0.0); continue
        lv = math.log10(1 + v)
        lo = sum(1 for x in xs if x < lv); hi = sum(1 for x in xs if x <= lv)
        out.append((lo + hi) / 2 / len(xs))
    return out

def top_continent(cont):
    tot = sum(cont.values())
    if not tot: return None, 0
    k = max(cont, key=cont.get)
    return k, cont[k] / tot

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data/species"); ap.add_argument("--work", default="work-spike-d")
    ap.add_argument("--limit-test", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True); os.makedirs(a.work, exist_ok=True)
    cpath = os.path.join(a.work, "cache.json")
    if os.path.exists(cpath):
        CACHE.update(json.load(open(cpath)))
    t0 = time.time()

    # 1. gather raw candidates: name -> dict(group, source, seed region, note, must)
    raw = {}
    def add(name, group, source, region=None, note="", must=False, inat=None):
        if name in S.DOMESTIC_OR_ODD: raw.setdefault(name, dict(group=group, source=source, region=region, note=note,
                                                                 must=must, inat=inat, domestic=True)); return
        if name in raw: 
            if source != "inat_pool": raw[name].update(source=source, region=region or raw[name]["region"], note=note or raw[name]["note"], must=must or raw[name]["must"], group=group)
            return
        raw[name] = dict(group=group, source=source, region=region, note=note, must=must, inat=inat, domestic=False)
    for n, r, note in S.CROPS: add(n, "crop", "seed", r, note, False)
    for n, r, note in S.TREES: add(n, "tree", "seed", r, note, False)
    for n, r, note in S.FISH: add(n, "fish", "seed", r, note, False)
    for n, r, note in S.INSECTS: add(n, "insect_arachnid", "seed", r, note, True)
    seedset = set(raw)
    lim = a.limit_test
    for g in ["bird", "mammal", "herp", "insect_arachnid", "wild_plant"]:
        if lim and g not in ("bird",): continue
        log("iNat pool", g)
        pool = inat_pool(g) if not lim else {}
        for n, e in pool.items():
            genus = n.split()[0]
            grp = g
            if g == "wild_plant":
                if n in seedset: continue
                grp = "tree" if genus in S.TREE_GENERA else "wild_plant"
            add(n, grp, "inat_pool", None, "", False, e)
    if lim:
        for k in list(raw)[:30]: pass
    # per group/region pre-cut by iNat regional popularity for pool species
    log("raw candidates", len(raw), collections.Counter(v["group"] for v in raw.values()))
    keep = {}
    bygr = collections.defaultdict(list)
    for n, v in raw.items():
        if v["source"] == "seed" or v["domestic"]: keep[n] = v
        else: bygr[(v["group"], v["inat"]["qregion"])].append((v["inat"]["regional"], n))
    for (g, reg), lst in bygr.items():
        k = int(math.ceil(GROUPS[g][2] * POOL_FACTOR * SHARES[reg]))
        for _, n in sorted(lst, reverse=True)[:k]: keep[n] = raw[n]
    log("to enrich", len(keep))

    # 2. enrich
    def work(item):
        n, v = item
        rec = dict(name=n, **{k: v[k] for k in ("group", "source", "region", "note", "must", "domestic")})
        try:
            inat = v["inat"] or inat_lookup(n)
            if inat: rec.update(inat_id=inat["inat_id"], common=inat.get("common"), inat_obs=inat.get("inat_obs"))
            m = gbif_match(n)
            if not m or m.get("rank") not in ("SPECIES", "SUBSPECIES", "VARIETY"):
                rec["error"] = "no GBIF species match"; return rec
            key = m.get("usageKey")
            rec.update(gbif_key=key, gbif_name=m.get("scientificName"), canonical=m.get("canonicalName"), rank=m.get("rank").lower(),
                       family=m.get("family"), order=m.get("order"), klass=m.get("class"), status=m.get("status"),
                       kingdom=m.get("kingdom"))
            rec.update(gbif_enrich(key))
        except Exception as ex:
            rec["error"] = repr(ex)[:120]
        return rec
    items = list(keep.items())
    out = []
    with ThreadPoolExecutor(12) as ex:
        for i, r in enumerate(ex.map(work, items)):
            out.append(r)
            if i % 100 == 0:
                log(f"  enriched {i}/{len(items)} {time.time()-t0:.0f}s")
                save_cache(cpath)
    save_cache(cpath)
    # 3. wikipedia
    log("wikipedia titles")
    nm = [r["name"] for r in out if "gbif_key" in r]
    wt = wiki_titles(nm)
    miss = [r for r in out if "gbif_key" in r and r["name"] not in wt and r.get("common")]
    wt2 = wiki_titles([r["common"] for r in miss])
    for r in miss:
        if r["common"] in wt2: wt[r["name"]] = wt2[r["common"]]
    titles = {n: t for n, t in wt.items()}
    def pv(n): return n, pageviews(titles[n][0])
    with ThreadPoolExecutor(4) as ex:
        pvs = dict(ex.map(pv, list(titles)))
    for r in out:
        t = titles.get(r["name"])
        r["wiki_title"], r["wikidata"] = (t if t else (None, None))
        r["pageviews"] = pvs.get(r["name"])
    # 4. flags, region, scores
    rows = []
    for r in out:
        if "gbif_key" not in r: continue
        if r.get("rank") != "species": r["subspecies_note"] = True
        top, share = top_continent(r.get("continents", {}))
        region = r["region"] or top
        # when GBIF says ANTARCTICA etc, fall back
        if region not in REGIONS: region = None
        r["region_final"] = region
        r["top_continent"], r["top_share"] = top, share
        iucn = r.get("iucn", "NE")
        fl = dict(
            threatened=iucn in ("VU", "EN", "CR", "EW", "EX"), dd=iucn == "DD",
            marine=bool(r.get("marine_profile")) and r["group"] != "fish" or (r.get("family") in S.MARINE_FAMILIES),
            domestic=r["domestic"] or r["name"] in S.DOMESTIC_OR_ODD or r.get("canonical") in S.DOMESTIC_OR_ODD,
            invasive=r["name"] in S.INVASIVE_CURATED or "invasive" in r["note"] or "introduced" in r["note"])
        narrow = None
        if "lat_p5" in r:
            narrow = (r["lat_p95"] - r["lat_p5"] < 4 and r["lon_p95"] - r["lon_p5"] < 4)
        fl["narrow"] = bool(narrow) if narrow is not None else (r.get("gbif_records", 0) < 20)
        r["flags"] = fl
        rows.append(r)
    for g in GROUPS:
        gr = [r for r in rows if r["group"] == g]
        a1 = pct_rank([r.get("inat_obs") for r in gr]); a2 = pct_rank([r.get("gbif_records") for r in gr]); a3 = pct_rank([r.get("pageviews") for r in gr])
        for r, x, y, z in zip(gr, a1, a2, a3):
            r["score"] = round(0.35 * x + 0.35 * y + 0.30 * z, 4)
    def reason(r):
        f = r["flags"]; rs = []
        if f["threatened"]: rs.append("threatened_" + r.get("iucn", ""))
        for k in ("dd", "marine", "domestic", "narrow"):
            if f[k]: rs.append(k)
        if not r["region_final"]: rs.append("no_region")
        if not r.get("gbif_records"): rs.append("no_records")
        return rs
    for r in rows:
        r["excl"] = reason(r)
        r["override"] = r["must"] and r["group"] == "insect_arachnid" and r["excl"] == ["threatened_" + r.get("iucn", "")]
    elig = [r for r in rows if not r["excl"] or r["override"]]
    excluded = [r for r in rows if r["excl"] and not r["override"]]
    # de-dupe by gbif key
    seen = set(); e2 = []
    for r in sorted(elig, key=lambda r: -r["score"]):
        if r["gbif_key"] in seen: continue
        seen.add(r["gbif_key"]); e2.append(r)
    elig = e2

    def select(pool, quota_idx):
        chosen = []; report = {}
        for g, spec in GROUPS.items():
            Q = spec[quota_idx]; gp = [r for r in pool if r["group"] == g]
            sel = [r for r in gp if r["must"] and (g in ("crop",) or r["source"] == "seed" and g == "insect_arachnid")]
            if quota_idx == 3 and len(sel) > Q:   # shortlist: must-include cannot exceed quota
                sel = sorted(sel, key=lambda r: (r["name"] not in S.CORE, -r["score"]))[:Q]
            selset = {r["gbif_key"] for r in sel}
            target = {rg: round(Q * SHARES[rg]) for rg in REGIONS}
            for r in sel:
                if r["region_final"] in target: target[r["region_final"]] -= 1
            for rg in REGIONS:
                cand = sorted([r for r in gp if r["region_final"] == rg and r["gbif_key"] not in selset], key=lambda r: -r["score"])
                for r in cand[:max(0, target[rg])]: sel.append(r); selset.add(r["gbif_key"])
            # fill shortfall by score with a cap of 1.4x regional share
            cnt = collections.Counter(r["region_final"] for r in sel)
            rest = sorted([r for r in gp if r["gbif_key"] not in selset], key=lambda r: -r["score"])
            for r in rest:
                if len(sel) >= Q: break
                if cnt[r["region_final"]] + 1 > math.ceil(1.4 * Q * SHARES[r["region_final"]]): continue
                sel.append(r); selset.add(r["gbif_key"]); cnt[r["region_final"]] += 1
            for r in rest:   # still short: relax cap
                if len(sel) >= Q: break
                if r["gbif_key"] in selset: continue
                sel.append(r); selset.add(r["gbif_key"])
            report[g] = dict(quota=Q, got=len(sel), by_region=dict(collections.Counter(r["region_final"] for r in sel)))
            chosen += sel
        return chosen, report
    cand, rep1 = select(elig, 2)
    short, rep2 = select(cand, 3)

    cols = ["rank_overall", "group", "gbif_taxon_key", "scientific_name", "common_name", "rank", "family", "region_assigned",
            "region_basis", "occ_continent_shares", "inat_taxon_id", "inat_obs_count", "gbif_records", "wikipedia_title",
            "wikidata_id", "pageviews_12m", "popularity_score", "iucn_category", "flag_threatened", "flag_data_deficient",
            "flag_narrow_range", "flag_marine", "flag_domestic_or_oddity", "flag_invasive_or_introduced", "cultivated_or_note",
            "must_include", "source", "lat_p5", "lat_p95", "lon_p5", "lon_p95", "gbif_sample_cells05", "exclusion_reasons"]
    def row(r, i):
        cont = r.get("continents", {}); tot = sum(cont.values()) or 1
        shares = ";".join(f"{k}:{v/tot:.2f}" for k, v in sorted(cont.items(), key=lambda kv: -kv[1]) if v / tot >= .03)
        f = r["flags"]; b = lambda x: "Y" if x else ""
        note = r["note"]
        if r["group"] == "crop": note = ("cultivated; " + note).strip("; ")
        if r["override"]: note = (note + "; threatened-list override (explicitly requested)").strip("; ")
        sg = lambda k: "" if r.get(k) is None else round(r[k], 2)
        return [i, r["group"], r["gbif_key"], r.get("canonical") or r["name"], r.get("common") or "", r.get("rank"), r.get("family") or "",
                r["region_final"] or "", "manual (native/origin)" if r["region"] else "gbif majority records", shares, r.get("inat_id", ""),
                r.get("inat_obs") if r.get("inat_obs") is not None else "", r.get("gbif_records", ""), r.get("wiki_title") or "",
                r.get("wikidata") or "", r.get("pageviews") if r.get("pageviews") is not None else "", r["score"], r.get("iucn", ""),
                b(f["threatened"]), b(f["dd"]), b(f["narrow"]), b(f["marine"]), b(f["domestic"]), b(f["invasive"]), note,
                b(r["must"]), r["source"], sg("lat_p5"), sg("lat_p95"), sg("lon_p5"), sg("lon_p95"), r.get("cells05", ""), ";".join(r["excl"])]
    def write(path, rs):
        rs = sorted(rs, key=lambda r: (-r["score"]))
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(cols)
            for i, r in enumerate(rs, 1): w.writerow(row(r, i))
    write(os.path.join(a.outdir, "candidates.csv"), cand)
    write(os.path.join(a.outdir, "shortlist_v1.csv"), short)
    write(os.path.join(a.outdir, "excluded_pool.csv"), excluded)
    stats = dict(candidates=len(cand), shortlist=len(short), excluded=len(excluded), enriched=len(rows),
                 errors=[(r["name"], r.get("error")) for r in out if "gbif_key" not in r][:200],
                 candidate_report=rep1, shortlist_report=rep2,
                 excluded_reasons=dict(collections.Counter(x for r in excluded for x in r["excl"])),
                 coverage=dict(pageviews=sum(1 for r in rows if r.get("pageviews") is not None), rows=len(rows)),
                 seconds=round(time.time() - t0))
    json.dump(stats, open(os.path.join(a.outdir, "build_stats.json"), "w"), indent=1)
    log(json.dumps(stats, indent=1)[:6000])

if __name__ == "__main__":
    main()
