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
            src, exp, var, *extra = key.split("|")            # a fourth part names an extra ensemble member
            m = next(x for x in C.models(cfg) if x["name"] == src)
            r = cat[(cat.source_id == src) & (cat.experiment_id == exp) & (cat.variable_id == var) & (cat.member_id == (extra[0] if extra else m["member"])) & (cat.grid_label == m["grid"])]
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
    items += hosts(cfg) + new_products()
    body = "\n\n".join(items) if items else "Nothing new upstream."
    open("watch_report.md", "w").write("# Upstream data check\n\n" + body + "\n")
    print(body)
    changes = any(i.startswith("**") for i in items)
    if os.environ.get("GITHUB_OUTPUT"):
        open(os.environ["GITHUB_OUTPUT"], "a").write(f"changes={'true' if changes else 'false'}\n")
    return 0


def _probe(url, timeout=60):
    """True when the first byte of url can be read (a ranged GET, so large files cost nothing)."""
    try:
        r = C.http().get(url, headers={"Range": "bytes=0-0"}, timeout=timeout, stream=True)
        r.close()
        return r.status_code in (200, 206)
    except Exception:  # noqa: BLE001
        return False


def hosts(cfg) -> list[str]:
    """Every data source the builds read, checked monthly, so a moved or retired host (as CHELSA's was in 2026) shows up
    as an issue before the yearly rebuild fails on it."""
    from .baselines import CHELSA_URL, CHIRPS_URL
    from .extremes import BUCKET
    from .era5 import STORE
    s = cfg["sources"]
    y = 2020
    urls = {
        "TerraClimate": s["terraclimate"].format(v="tmax", y=y),
        "AdaptWest normals": s["adaptwest"],
        "CMIP6 catalogue (Pangeo)": s["pangeo_catalog"],
        "GeoNames": s["geonames"],
        "Natural Earth": s["natural_earth"],
        "IPCC AR6 sea level (Zenodo)": s["sealevel_zip"],
        "CHIRPS": CHIRPS_URL.format(y=y, m=1),
        "CHELSA": CHELSA_URL.format(v="tasmax", m=1),
        "NEX-GDDP-CMIP6": BUCKET + "index.html",
        "ERA5 (WeatherBench2)": f"https://storage.googleapis.com/{STORE}/.zmetadata",
        "WorldClim": "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_tmax.zip",
    }
    bad = [n for n, u in urls.items() if not _probe(u)]
    return [f"**Data sources not answering:** {', '.join(bad)}. Check whether they moved before the next rebuild "
            f"(each one's address is in config.toml [sources] or at the top of its ctw module)."] if bad else []


def new_products() -> list[str]:
    """Newer versions of datasets the site could use. Each hit is a prompt for a decision, not an automatic change."""
    out = []
    if _probe("https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/tasmax/1991-2020/"
              "CHELSA_tasmax_01_1991-2020_V.2.1.tif"):
        out.append("**CHELSA 1991-2020 climatologies are published:** switch CHELSA_URL in ctw/baselines.py to 1991-2020 so "
                   "the cross-check uses the same period as the baseline.")
    try:
        r = C.http().get("https://storage.googleapis.com/storage/v1/b/gcp-public-data-arco-era5/o",
                         params={"prefix": "ar/", "delimiter": "/", "fields": "prefixes"}, timeout=60)
        land = [p for p in r.json().get("prefixes", []) if "land" in p.lower()]
        if land:
            out.append(f"**ERA5-Land is on the public ARCO bucket** ({', '.join(land[:3])}): it is land-only at 0.1 degree and "
                       f"would make the ERA5 baseline check far more reliable at coasts and islands (ctw/era5.py).")
    except Exception:  # noqa: BLE001
        pass
    try:
        r = C.http().get("https://nex-gddp-cmip6.s3-us-west-2.amazonaws.com/", params={"prefix": "NEX-GDDP-CMIP7/", "max-keys": 1},
                         timeout=60)
        if "<Key>" in r.text:
            out.append("**NEX-GDDP for CMIP7 has appeared** in NASA's bucket: plan the move of the downscaled changes to it.")
    except Exception:  # noqa: BLE001
        pass
    return out
