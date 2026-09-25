"""Monthly look at the upstream data. Writes watch_report.md; prints changes=true|false for the workflow,
which opens (or updates) a GitHub issue when something needs attention. Never changes the site itself."""
from __future__ import annotations
import json, os
import pandas as pd
from . import common as C
from .terraclimate import latest_year


def run(cfg=None) -> int:
    cfg = cfg or C.config()
    man = json.load(open(C.SITE / "data" / "manifest.json")) if (C.SITE / "data" / "manifest.json").exists() else {}
    items = []
    try:
        y = latest_year(dict(cfg, recent={"end": "auto", "years": cfg["recent"]["years"]}))
        have = man.get("recent_years", [0, 0])[1]
        if y > have:
            items.append(f"**New TerraClimate year:** {y} is available (site uses data through {have}). Run *Rebuild data* to update the "
                         f"“already happening” comparison.")
    except Exception as e:  # noqa: BLE001
        items.append(f"Could not check TerraClimate: {e}")
    try:
        cat = pd.read_csv(cfg["sources"]["pangeo_catalog"], usecols=["source_id", "experiment_id", "member_id", "table_id", "variable_id", "grid_label", "version"])
        cat = cat[cat.table_id == "Amon"]
        old = man.get("cmip6_versions", {})
        changed, gone = [], []
        for key, v in old.items():
            src, exp, var = key.split("|")
            m = next(x for x in C.models(cfg) if x["name"] == src)
            r = cat[(cat.source_id == src) & (cat.experiment_id == exp) & (cat.variable_id == var) & (cat.member_id == m["member"]) & (cat.grid_label == m["grid"])]
            if r.empty:
                gone.append(key)
            elif int(r.version.max()) != int(v):
                changed.append(f"{key} {v}→{int(r.version.max())}")
        if changed:
            items.append("**Corrected CMIP6 datasets** (new versions published): " + ", ".join(changed[:30]))
        if gone:
            items.append("**CMIP6 datasets no longer in the archive** (possibly retracted): " + ", ".join(gone[:30]))
    except Exception as e:  # noqa: BLE001
        items.append(f"Could not check the CMIP6 catalogue: {e}")
    try:
        r = C.http().get(cfg["sources"]["esgf_search"], params={"project": "CMIP7", "variable_id": "tasmax", "limit": 0,
                                                                   "format": "application/solr+json"}, timeout=60)
        n = r.json()["response"]["numFound"]
        if n:
            items.append(f"**CMIP7 is arriving:** {n} monthly maximum-temperature datasets are on ESGF. When scenario runs from "
                         f"enough models appear (the CMIP7 ScenarioMIP), plan a method update (models list and TCR screen).")
    except Exception as e:  # noqa: BLE001
        items.append(f"Could not check ESGF for CMIP7: {e}")
    body = "\n\n".join(items) if items else "Nothing new upstream."
    open("watch_report.md", "w").write("# Upstream data check\n\n" + body + "\n")
    print(body)
    changes = any(i.startswith("**") for i in items)
    if os.environ.get("GITHUB_OUTPUT"):
        open(os.environ["GITHUB_OUTPUT"], "a").write(f"changes={'true' if changes else 'false'}\n")
    return 0
