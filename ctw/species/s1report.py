"""S1 batch 1 results table from the W3 summaries (one summary.json per species).

  python -m ctw.species.s1report --summaries work/w3 --csv data/species/batch1_results.csv [--md docs/species/S1-fit-report.md]

Per species: tier, wording, confidence, range-shift status, area now, and for SSP2-4.5 2081-2100 the area change and centroid shift under the
three dispersal bounds (unlimited / limited / none) or 'withheld' when more than 15% of the area is novel climate. Counts at the end.
"""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

KEY = "SSP2-4.5|2081-2100"
COLS = ["id", "scientific_name", "common_name", "group", "kind", "tier", "confidence", "range_shifts_tested", "cv_kind", "wording", "published", "gate_cells", "cv_auc", "boyce",
        "range_check", "novel_share_pct", "withheld", "area_now_million_km2", "change_pct_unlimited", "shift_km_unlimited", "bearing_unlimited", "change_pct_limited", "shift_km_limited",
        "change_pct_none", "hard_failures", "soft_flags"]


def load(root: Path) -> list[dict]:
    out = []
    for p in sorted(Path(root).glob("*/summary.json")):
        out.append(json.loads(p.read_text()))
    return out


def row(s: dict) -> dict:
    sp, sk, g = s["species"], s["skill"], s["gates"]
    sc = s["scenarios"].get(KEY, {})
    m = sc.get("modes", {})
    w = bool(sc.get("withheld"))
    r = lambda x, n=1: "" if x is None else round(x, n)                       # noqa: E731
    v = lambda mode, k, n=1: "withheld" if w else r((m.get(mode) or {}).get(k), n)  # noqa: E731
    return {"id": sp["id"], "scientific_name": sp["scientific_name"], "common_name": sp.get("common_name"), "group": sp.get("group"), "kind": s.get("species_kind"),
            "tier": s["tier"], "confidence": s["confidence"], "range_shifts_tested": s.get("range_shifts_tested"), "cv_kind": s.get("cv_kind"), "wording": s.get("wording"),
            "published": s["published"], "gate_cells": s["records"]["gate_cells"], "cv_auc": r(sk.get("cv_auc"), 2), "boyce": r(sk.get("cv_boyce"), 2),
            "range_check": g["range_check"]["status"], "novel_share_pct": "" if sc.get("novel_share") is None else round(100 * sc["novel_share"], 1), "withheld": w,
            "area_now_million_km2": r(s["area_now_km2"] / 1e6, 1), "change_pct_unlimited": v("unlimited", "change_pct"), "shift_km_unlimited": v("unlimited", "shift_km", 0),
            "bearing_unlimited": v("unlimited", "bearing", 0), "change_pct_limited": v("limited", "change_pct"), "shift_km_limited": v("limited", "shift_km", 0),
            "change_pct_none": v("none", "change_pct"), "hard_failures": "; ".join(s["hard_failures"]), "soft_flags": "; ".join(s["soft_flags"])}


def counts(rows: list[dict]) -> dict:
    c = {"fitted": len(rows), "A": 0, "B": 0, "C": 0, "withheld_2081_2100_ssp245": 0, "low_confidence": 0, "shown": 0}
    for r in rows:
        c[r["tier"]] = c.get(r["tier"], 0) + 1
        c["withheld_2081_2100_ssp245"] += int(bool(r["withheld"]))
        c["low_confidence"] += int(r["confidence"] != "standard")
        c["shown"] += int(bool(r["published"]))
    return c


def markdown(rows: list[dict]) -> str:
    c = counts(rows)
    L = [f"Fitted {c['fitted']}: Tier A {c['A']}, Tier B {c['B']}, Tier C {c['C']} (not shown); shown {c['shown']}; low confidence {c['low_confidence']}; "
         f"shift and area numbers withheld (novel climate over 15%) for SSP2-4.5 2081-2100: {c['withheld_2081_2100_ssp245']}.", "",
         "| species | group | tier | conf. | shifts tested | wording | area now (M km2) | SSP2-4.5 2081-2100 area change %: unlimited / limited / none | shift km (unlimited / limited) | novel % |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["group"], r["scientific_name"])):
        wording = (r["wording"] or "").split(" (")[0].split(". ")[0]
        L.append(f"| {r['scientific_name']} | {r['group']} | {r['tier']} | {r['confidence']} | {r['range_shifts_tested']} | {wording} | {r['area_now_million_km2']} | "
                 f"{r['change_pct_unlimited']} / {r['change_pct_limited']} / {r['change_pct_none']} | {r['shift_km_unlimited']} / {r['shift_km_limited']} | {r['novel_share_pct']} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summaries", required=True)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--md", default=None)
    a = ap.parse_args(argv)
    rows = [row(s) for s in load(Path(a.summaries))]
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
    md = markdown(rows)
    if a.md:
        Path(a.md).write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
