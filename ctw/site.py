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
# BEGIN era5-agreement / hindcast blocks for methods.html
def era5_html(S) -> str:
    e = S.get("era5")
    if not e:
        return "<p>Results for this build are not available.</p>"
    names = {"tmax": "Highs (°C)", "tmin": "Lows (°C)", "ppt": "Precipitation (mm per season)", "dew": "Dewpoint (°C)"}
    rows = ""
    for reg, b in e["bias"].items():
        for v, lab in names.items():
            rows += f"<tr><td>{reg}</td><td>{lab}</td>" + "".join(f'<td class="n">{x:+.1f}</td>' if x is not None else "<td>-</td>" for x in b[v]) + "</tr>"
    cell = e.get("match") == "cell"
    nolc = (f" {e['no_land_cell']:,} places have no ERA5 land cell within reach and are not checked against ERA5." if cell and e.get("no_land_cell") else "")
    what = "ERA5 (each place's land cell) minus baseline averaged over the same cell" if cell else "ERA5 minus baseline"
    return (f"<p>In this release the median disagreement is {e['median']:.2f}σ across {e['n']:,} places (90th percentile {e['p90']:.1f}σ); "
            f"{e['over_fair']:.0%} of places are above {e['thr'][0]:g}σ and {e['over_poor']:.0%} above {e['thr'][1]:g}σ.{nolc}</p>"
            '<div class="tw"><table class="res"><thead><tr><th>Places</th><th>Measure</th><th class="n">Winter</th><th class="n">Spring</th>'
            '<th class="n">Summer</th><th class="n">Autumn</th></tr></thead><tbody>' + rows +
            f"</tbody><caption>Median {what} (TerraClimate, or AdaptWest in North America), 1991–2020, by season "
            "(December–February, and so on; the same months in both hemispheres). These are the offsets removed before the agreement is computed. North American temperature and precipitation are compared with AdaptWest, dewpoint and all other places with TerraClimate.</caption></table></div>")


def agreement_html(S) -> str:
    """Per-source table and the CHIRPS / CHELSA offsets for methods.html (block AGREE_BLOCK)."""
    a = S.get("agree")
    if not a or not a.get("sources"):
        return "<p>Results for this build are not available.</p>"
    from .baselines import LABEL
    what = {"era5": "All sixteen measures", "chirps": "Precipitation (four seasons)", "chelsa": "Highs, lows, precipitation (twelve measures)"}
    rows = "".join(f'<tr><td>{LABEL[n]}</td><td>{what[n]}</td><td class="n">{e["n"]:,}</td><td class="n">{e["median"]:.2f}</td><td class="n">{e["p90"]:.1f}</td>'
                   f'<td class="n">{e["over_fair"]:.0%}</td><td class="n">{e["over_poor"]:.0%}</td></tr>' for n, e in a["sources"].items())
    cb = a.get("combined")
    if cb:
        rows += (f'<tr><td><strong>Worst of the sources</strong></td><td>Used for the confidence level</td><td class="n">{cb["n"]:,}</td><td class="n">{cb["median"]:.2f}</td>'
                 f'<td class="n">&ndash;</td><td class="n">{cb["over_fair"]:.0%}</td><td class="n">{cb["over_poor"]:.0%}</td></tr>')
    out = ('<div class="tw"><table class="res"><thead><tr><th>Source</th><th>Covers</th><th class="n">Places</th><th class="n">Median &sigma;</th>'
           f'<th class="n">90th percentile</th><th class="n">Above {a["thr"][0]:g}&sigma;</th><th class="n">Above {a["thr"][1]:g}&sigma;</th></tr></thead><tbody>{rows}</tbody>'
           "<caption>Baseline agreement in this release, after removing each source's typical offset.</caption></table></div>")
    names = {"tmax": "Highs (&deg;C)", "tmin": "Lows (&deg;C)", "ppt": "Precipitation (mm per season)"}
    brows = ""
    for src, tab in a.get("bias", {}).items():
        for reg, b in tab.items():
            for v, lab in names.items():
                if v in b:
                    brows += f"<tr><td>{LABEL[src]}</td><td>{reg}</td><td>{lab}</td>" + "".join(f'<td class="n">{x:+.1f}</td>' if x is not None else "<td>-</td>" for x in b[v]) + "</tr>"
    if brows:
        out += ('<div class="tw"><table class="res"><thead><tr><th>Source</th><th>Places</th><th>Measure</th><th class="n">Winter</th><th class="n">Spring</th>'
                '<th class="n">Summer</th><th class="n">Autumn</th></tr></thead><tbody>' + brows +
                "</tbody><caption>Median source minus baseline (TerraClimate, or AdaptWest in North America). CHELSA covers 1981&ndash;2010, so its offsets include the change between the two periods.</caption></table></div>")
    if a.get("chirps_icv_ratio"):
        r = a["chirps_icv_ratio"]
        out += (f"<p>Year-to-year variability of precipitation is also compared: the detrended standard deviation of log seasonal totals in CHIRPS, divided by the value in each place's "
                f"own variability model, has a median of {r[0]:.2f} (winter), {r[1]:.2f} (spring), {r[2]:.2f} (summer) and {r[3]:.2f} (autumn) across places. Values near 1 mean the two agree "
                "on how much the rain varies; this comparison is reported only and does not change any confidence level.</p>")
    return out


def hindcast_html() -> str:
    f = C.DATA / "hindcast.json"
    if not f.exists():
        return "<p>The hindcast has not been run for this build.</p>"
    H = json.load(open(f))
    a, d = H["all"], H["largest_change_third"]
    (a0, a1), (b0, b1) = H["windows"]

    def row(lab, x):
        return (f'<tr><td>{lab}</td><td class="n">{x["n"]}</td><td class="n">{x["persistence_d"]:.2f}</td><td class="n">{x["projection_d"]:.2f}</td>'
                f'<td class="n">{x["at_predicted_analog_d"]:.2f}</td><td class="n">{x["oracle_d"]:.2f}</td>'
                f'<td class="n">{x["own_cell_d"]:.2f}</td><td class="n">{x["naive_lat_shift_d"]:.2f}</td><td class="n">{x["share_beats_naive"]:.0%}</td></tr>')
    z = a["at_predicted_analog"]
    return (f"<p>{a['n']} places sampled from {H['n_candidates']:,} (half farthest-point in climate space, half random). "
            f"Median warming of the annual mean between the windows was {a['median_warming_C']:.2f}&nbsp;&deg;C.</p>"
            '<div class="tw"><table class="res"><thead><tr><th>Subset</th><th class="n">Places</th><th class="n">No change</th><th class="n">Projection</th>'
            '<th class="n">Predicted analog</th><th class="n">Best possible analog</th><th class="n">Own 0.5&deg; cell</th>'
            '<th class="n">Latitude shift</th><th class="n">Analog beats latitude shift</th></tr></thead><tbody>'
            + row("All sampled places", a) + row("Third with the largest change", d) +
            f"</tbody><caption>Table H. Median distance from the climate that actually occurred in {b0}&ndash;{b1}, as the root-mean-square difference in units of the "
            "place's own year-to-year standard deviation (0 = identical; two random years of the same place differ by about 1.4). "
            "The last column is the share of places where the predicted analog was closer to the truth than the latitude-shifted cell.</caption></table></div>"
            f"<p>In the method's own units, the actual {b0}&ndash;{b1} climate lay a median of {z['median']:.2f}&sigma; from the predicted analog "
            f"({z['share_under_1']:.0%} of places under 1&sigma;, {z['share_under_2']:.0%} under 2&sigma;, 90th percentile {z['p90']:.1f}&sigma;). "
            f"The predicted analog was within 500&nbsp;km of the best possible analog for {a['share_predicted_within_500km_of_oracle']:.0%} of places "
            f"(median {a['km_predicted_to_oracle_median']:,.0f}&nbsp;km apart), and the projection was closer to the truth than &ldquo;nothing changes&rdquo; "
            f"at {a['share_projection_beats_persistence']:.0%} of places. Predicted analogs lay a median of {a['median_move_km']:,.0f}&nbsp;km from the place, "
            f"equatorward for {a['share_equatorward']:.0%} of them. Skill against the latitude-shift baseline (1 minus the ratio of median distances) was {a['skill_vs_naive']:.0%}, "
            f"and against the place's own 0.5&deg; cell {a['skill_vs_own_cell']:.0%}. The predicted analog was only "
            f"{1 - a['at_predicted_analog_d'] / a['persistence_d']:.0%} closer to the truth than the place's own 1961&ndash;{a1} climate (Table H, &ldquo;No change&rdquo;), "
            "which is what a small change against large year-to-year swings implies: the test shows that the search finds essentially the best place there is, "
            "not that moving to it is warranted.</p>")


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
             "SELFCHK": f"{S['selfchk_median']:.2f}", "GWL_NOW": f"{S.get('gwl_now', 0.9):.1f}", "MEMBERS_MAX": str(cfg["models"].get("members_max", 1)), "SL_N": str(S["sealevel_places"]),
             "REPO_LINK": (f'<a href="{cfg["release"]["repo_url"]}">{cfg["release"]["repo_url"]}</a>' if cfg["release"].get("repo_url") else "source code in the project repository")}
    fills["TROPICS_TABLE"] = tropics_rows(S)
    fills["EXTRA_TOC"], fills["EXTRA_SECTION"] = extra_section(cfg, S)
    fills["ERA5_BLOCK"] = era5_html(S)                                  # era5-agreement
    fills["AGREE_BLOCK"] = agreement_html(S)                            # baseline-agreement
    fills["HINDCAST_BLOCK"] = hindcast_html()                           # hindcast
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
        vers, mems = {}, {}
        for mm in C.models(cfg):
            z = C.load(C.work("cmip6", f"{mm['name']}.npz"))
            vers.update(json.loads(str(z["versions"])))
            if "members" in z:                                     # ensemble members averaged for this model
                mems[mm["name"]] = json.loads(str(z["members"]))["used"]
        if vers:
            manifest["cmip6_versions"] = vers
        if mems:
            manifest["cmip6_members"] = mems
    except Exception:  # noqa: BLE001
        pass
    json.dump(manifest, open(C.SITE / "data" / "manifest.json", "w"), indent=1)
    C.log.info("site assembled: %s", sorted(p.name for p in C.SITE.rglob("*") if p.is_file()))
