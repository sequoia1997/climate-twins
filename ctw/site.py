"""Assemble the deployable site: web/ templates -> site/ (index.html, methods.html; data files are already there).
The data version is stamped into index.html so browsers fetch new data after each release, and the methods
page's release numbers are filled from the build summary."""
from __future__ import annotations
import json, re
from . import common as C


def tropics_rows(S) -> str:
    """How often places lack a match, by latitude (~2100, SSP2-4.5, likely-range models), for the methods page."""
    import numpy as np
    T = C.targets()
    lat = dict(zip(T.label, T.lat.abs()))
    pairs = [(lat[k], v["sig"][1][1][1]) for k, v in S["places"].items() if k in lat]
    rows = []
    for lo, hi, lab in [(0, 15, "0–15°"), (15, 25, "15–25°"), (25, 35, "25–35°"), (35, 45, "35–45°"), (45, 91, "45° and poleward")]:
        x = np.array([s for a, s in pairs if lo <= a < hi])
        if len(x):
            rows.append(f"<tr><td>{lab}</td><td>{len(x):,}</td><td>{np.mean(x >= 4):.0%}</td><td>{np.mean(x >= 2):.0%}</td></tr>")
    return "".join(rows)


def place_counts(S) -> dict:
    """Place counts for the methods page, from the places actually in the build (summary.json) and the place lists."""
    T = C.targets()
    T = T[T.label.isin(S["places"])]
    na, w = T[T.g == 0], T[T.g == 1]
    n = lambda x: f"{int(x):,}"                                                    # noqa: E731
    return {"N_PLACES": n(len(T)), "N_NA": n(len(na)), "N_WORLD": n(len(w)), "N_COUNTRIES": n(w.country.nunique()),
            "N_CONUS": n((na.domain == "conus").sum()), "N_AK": n(((na.country == "US") & (na.domain == "na")).sum()),
            "N_CA": n((na.country == "CA").sum()), "N_MX": n((na.country == "MX").sum())}


def run(cfg=None):
    cfg = cfg or C.config()
    S = json.load(open(C.SITE / "data" / "summary.json"))
    na = json.load(open(C.DATA / "feature_calibration.json"))
    web = C.ROOT / "web"
    idx = (web / "index.html").read_text()
    assert "__DATA_VERSION__" in idx
    url = cfg["release"].get("site_url", "").rstrip("/")
    (C.SITE / "index.html").write_text(idx.replace("__DATA_VERSION__", S["data_version"]).replace("__SITE_URL__", url))
    import shutil
    for f in (web / "assets").glob("*"):                              # preview image and icons
        shutil.copy2(f, C.SITE / f.name)
    (C.SITE / "world.dat").unlink(missing_ok=True)              # v9 kept world data beside index.html
    m = (web / "methods.html").read_text()
    fills = {"DATA_VERSION": S["data_version"], "RELEASE": S["method_version"], "RECENT_FIRST": str(S["recent_years"][0]),
             "RECENT_LAST": str(S["recent_years"][1]), "N_MODELS": str(S["n_models"]),
             "HZ_R2": f"{na['hardiness']['r2']:.2f}", "HZ_ERR": f"{na['hardiness']['median_abs_err_c']:.1f}",
             "HZ_SAME": f"{na['hardiness']['same_half_zone']:.0%}", "HZ_ONE": f"{na['hardiness']['within_one_half_zone']:.0%}",
             "FFP_R2": f"{na['ffp']['r2']:.2f}", "FFP_ERR": f"{na['ffp']['median_abs_err_days']:.0f}",
             "SELFCHK": f"{S['selfchk_median']:.2f}", "SL_N": str(S["sealevel_places"]),
             "REPO_LINK": (f'<a href="{cfg["release"]["repo_url"]}">{cfg["release"]["repo_url"]}</a>' if cfg["release"].get("repo_url") else "source code in the project repository")}
    fills["TROPICS_TABLE"] = tropics_rows(S)
    fills.update(place_counts(S))
    for k, v in fills.items():
        m = m.replace("{{" + k + "}}", v)
    m = m.replace("__SITE_URL__", url)
    left = re.findall(r"\{\{[A-Z_0-9]+\}\}", m)
    assert not left, f"unfilled methods placeholders: {left}"
    (C.SITE / "methods.html").write_text(m)
    from . import changelog                                            # the public changelog page
    md = changelog.PATH.read_text() if changelog.PATH.exists() else "# What's new\n\nNo entries yet.\n"
    page = (web / "changelog.html").read_text().replace("{{INTRO}}", changelog.intro(md)).replace("{{CHANGELOG}}", changelog.render(md))
    (C.SITE / "changelog.html").write_text(page.replace("__SITE_URL__", url))
    manifest = {"data_version": S["data_version"], "method_version": S["method_version"], "recent_years": S["recent_years"]}
    old = C.SITE / "data" / "manifest.json"
    if old.exists():                                               # a page-only rebuild keeps the recorded versions
        manifest = {**json.load(open(old)), **manifest}
    try:
        vers = {}
        for mm in C.models(cfg):
            z = C.load(C.work("cmip6", f"{mm['name']}.npz"))
            vers.update(json.loads(str(z["versions"])))
        if vers:
            manifest["cmip6_versions"] = vers
    except Exception:  # noqa: BLE001
        pass
    json.dump(manifest, open(C.SITE / "data" / "manifest.json", "w"), indent=1)
    C.log.info("site assembled: %s", sorted(p.name for p in C.SITE.rglob("*") if p.is_file()))
