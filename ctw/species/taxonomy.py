"""Build data/species/taxonomy.csv (kingdom, phylum, class, order, family) for every organism in the pilot and batch tables, from the GBIF backbone
species-match API. Run: python -m ctw.species.taxonomy  (needs network access to api.gbif.org)."""
import csv, json, sys, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = ["data/species/pilot_v1.csv", "data/species/batch1.csv", "data/species/batch2.csv"]
OUT = ROOT / "data/species/taxonomy.csv"
COLS = ["scientific_name", "kingdom", "phylum", "class", "order", "family", "match"]


def names() -> list[str]:
    seen = []
    for t in TABLES:
        p = ROOT / t
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                n = r.get("scientific_name", "").strip()
                if n and n not in seen:
                    seen.append(n)
    return seen


def lookup(name: str) -> dict:
    url = "https://api.gbif.org/v1/species/match?name=" + urllib.parse.quote(name)
    for _ in range(3):
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "climate-twins-taxonomy"}), timeout=30))
            return {"scientific_name": name, "kingdom": d.get("kingdom", ""), "phylum": d.get("phylum", ""), "class": d.get("class", ""),
                    "order": d.get("order", ""), "family": d.get("family", ""), "match": d.get("matchType", "")}
        except Exception:
            pass
    return {"scientific_name": name, "match": "ERROR"}


def main() -> int:
    ns = names()
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(lookup, ns))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    bad = [r["scientific_name"] for r in rows if r.get("match") not in ("EXACT", "FUZZY", "HIGHERRANK") or not r.get("family")]
    print(f"{len(rows)} organisms; without a family: {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
