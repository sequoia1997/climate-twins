"""One photo per organism from Wikipedia / Wikimedia Commons, with author and licence, into data/species/images.json (only reusable licences: public domain, CC0, CC BY, CC BY-SA).
Run in an Actions job (the sandbox IP is rate-limited by Wikimedia): python -m ctw.species.images. Polite: one request at a time with a short pause and a descriptive User-Agent.
The page hot-links Wikimedia's own thumbnails (Special:FilePath) and credits the author, licence and Commons page under every photo."""
from __future__ import annotations
import csv, html, json, re, time, urllib.parse
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
UA = {"User-Agent": "ClimateTwins/1.0 (https://climatetwins.org; educational non-commercial site; contact via the site) python-requests"}
TABLES = ["pilot_v1", "batch1", "batch2", "batch3", "batch4", "batch5", "batch6"]
OK = re.compile(r"^(public domain|pd\b|cc0|cc[ -]by(?!-?(nc|nd))|cc[ -]by-sa|cc-by)", re.I)


def licence_ok(short: str, usage: str = "") -> bool:
    s = (short or "").strip()
    if re.search(r"\b(nc|nd)\b|non-?commercial|no ?deriv|fair use|all rights", s + " " + (usage or ""), re.I):
        return False
    return bool(OK.match(s)) or "public domain" in s.lower()


def clean(t: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t or ""))).strip()


def get(url, **params):
    for i in range(5):
        r = requests.get(url, params=params, headers=UA, timeout=40)
        if r.status_code == 429:
            time.sleep(10 * (i + 1)); continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    return None


def names():
    out = {}
    for t in TABLES:
        f = ROOT / "data/species" / f"{t}.csv"
        if f.exists():
            for r in csv.DictReader(open(f, encoding="utf-8")):
                out.setdefault(r["scientific_name"], r.get("common_name", ""))
    return out


def main() -> int:
    found = {}
    for i, (sci, common) in enumerate(names().items()):
        for title in (sci, common):
            if not title:
                continue
            d = get("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_")))
            time.sleep(0.4)
            src = ((d or {}).get("originalimage", {}).get("source") or (d or {}).get("thumbnail", {}).get("source") or "").split("?")[0]          # the API appends tracking parameters
            if src and (d or {}).get("type") == "standard":
                fn = urllib.parse.unquote(src.split("/")[-1] if "/thumb/" not in src else src.split("/thumb/")[1].split("/")[2])
                found[sci] = dict(file=fn, wiki=(d.get("content_urls") or {}).get("desktop", {}).get("page", ""))
                break
        if i % 40 == 0:
            print(i, len(found), flush=True)
    files = sorted({v["file"] for v in found.values()})
    meta = {}
    for k in range(0, len(files), 40):
        d = get("https://commons.wikimedia.org/w/api.php", action="query", prop="imageinfo", iiprop="extmetadata", format="json", titles="|".join("File:" + f for f in files[k:k + 40]))
        for p in ((d or {}).get("query", {}).get("pages") or {}).values():
            em = (p.get("imageinfo") or [{}])[0].get("extmetadata", {})
            meta[p.get("title", "")[5:].replace(" ", "_")] = em
        time.sleep(1)
    out, skipped = {}, 0
    for sci, v in found.items():
        em = meta.get(v["file"].replace(" ", "_"), {})
        lic = clean(em.get("LicenseShortName", {}).get("value", ""))
        if not em or not licence_ok(lic, clean(em.get("UsageTerms", {}).get("value", ""))):
            skipped += 1; continue
        out[sci] = dict(file=v["file"], page="https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(v["file"]), artist=clean(em.get("Artist", {}).get("value", ""))[:120] or "Wikimedia Commons",
                        licence=lic, licence_url=clean(em.get("LicenseUrl", {}).get("value", "")), article=v["wiki"])
    with open(ROOT / "data/species/images.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=0, ensure_ascii=False)
    print("photos", len(out), "of", len(names()), "(skipped for licence:", skipped, ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
