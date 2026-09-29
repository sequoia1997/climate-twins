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


def extra_section(cfg, S) -> tuple[str, str]:
    """(contents entry, section) for the optional extra matched variables; both empty while [matching] extra = []."""
    names = C.extra_names(cfg)
    if not names:
        return "", ""
    seas = ["Dec–Feb", "Mar–May", "Jun–Aug", "Sep–Nov"]
    used = " and ".join(seas[int(i)] for i in cfg["matching"].get("extra_seasons", [0, 2]))
    K = len(C.match_idx(cfg))
    paras = [f"<p>In addition to temperature, precipitation and dewpoint, {K} measures in all are matched. The extra measures are taken for {used}, "
             "with the same year-to-year variability scaling, shrinkage and degrees of freedom as the others; like humidity, present-day values come "
             "from TerraClimate everywhere, including North America, because the North American temperature and precipitation dataset does not include them.</p>"]
    if "pet" in names:
        paras.append("<p><strong>Potential evapotranspiration</strong> (TerraClimate, Penman–Monteith; log(mm + 1)) is the atmosphere's thirst. Together with "
                     "precipitation it separates places that are dry because little rain falls from places that are dry because the air demands a lot, which "
                     "temperature alone does not. Future values scale the observed PET by the ratio of Hargreaves–Samani PET (Hargreaves &amp; Samani 1985) computed from "
                     "each model's projected and baseline monthly highs and lows, limited to 0.5–3. This captures warming and changes in daily range but not "
                     "humidity, wind, radiation or plant water-use responses, and temperature-based PET is known to overstate future increases "
                     "(Milly &amp; Dunne 2016), so this measure is best read as an upper bound on drying.</p>")
    if "srad" in names:
        paras.append("<p><strong>Solar radiation</strong> (TerraClimate srad, W/m², matched in units of 10 W/m²) separates sunny from cloudy climates that share "
                     "the same temperature and rainfall. Future values scale the observed radiation by each model's change in downwelling shortwave radiation "
                     "(rsds), limited to 0.8–1.25; models without rsds contribute no change. Cloud changes are among the least certain model outputs, so this "
                     "measure mostly anchors the present-day climate.</p>")
    paras.append("<p>Near-surface wind was considered and left out: reanalysis-derived TerraClimate winds are coarse, model wind speeds are poorly constrained "
                 "by observations, and the change is small relative to its uncertainty.</p>")
    x = S.get("extra")
    if x:
        paras.append(f"<p>Effect of these measures in this release: the best match moved by more than {x['moved_km']} km in {x['moved_share']:.0%} of "
                     f"place–period–scenario combinations, and the best-match σ changed by a median of {x['median_abs_dsigma']:.2f}.</p>")
    return '<li><a href="#extra">Extra variables</a></li>', '<section id="extra">\n    <h2>Extra variables</h2>\n    ' + "\n    ".join(paras) + "\n  </section>\n"


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
    fills["EXTRA_TOC"], fills["EXTRA_SECTION"] = extra_section(cfg, S)
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
