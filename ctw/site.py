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
    return (f"<p>In this release the median disagreement is {e['median']:.2f}σ across {e['n']:,} places (90th percentile {e['p90']:.1f}σ); "
            f"{e['over_fair']:.0%} of places are above {e['thr'][0]:g}σ and {e['over_poor']:.0%} above {e['thr'][1]:g}σ.</p>"
            '<div class="tw"><table class="res"><thead><tr><th>Places</th><th>Measure</th><th class="n">Winter</th><th class="n">Spring</th>'
            '<th class="n">Summer</th><th class="n">Autumn</th></tr></thead><tbody>' + rows +
            "</tbody><caption>Median ERA5 minus baseline (TerraClimate, or AdaptWest in North America), 1991–2020, by season "
            "(December–February, and so on; seasons are the same in both hemispheres). North American precipitation and temperature come from AdaptWest; dewpoint from TerraClimate.</caption></table></div>")


def hindcast_html() -> str:
    f = C.DATA / "hindcast.json"
    if not f.exists():
        return "<p>The hindcast has not been run for this build.</p>"
    H = json.load(open(f))
    a, d = H["all"], H["detectable_change"]
    (a0, a1), (b0, b1) = H["windows"]

    def row(lab, x):
        if not x:
            return ""
        z = x["at_predicted_analog"]
        return (f'<tr><td>{lab}</td><td class="n">{x["n"]}</td><td class="n">{x["persistence_sigma_median"]:.2f}</td><td class="n">{x["projection_sigma_median"]:.2f}</td>'
                f'<td class="n">{z["median"]:.2f}</td><td class="n">{z["share_under_1"]:.0%}</td><td class="n">{x["oracle_median"]:.2f}</td>'
                f'<td class="n">{x["own_cell_median"]:.2f}</td><td class="n">{x["naive_lat_shift_median"]:.2f}</td><td class="n">{x["share_beats_naive"]:.0%}</td></tr>')
    return (f"<p>{a['n']} places sampled from all {H.get('n_candidates', 'the')} target places (half farthest-point in climate space, half random). "
            f"Median warming between the windows: {a['median_warming_C']:.2f} °C.</p>"
            '<div class="tw"><table class="res"><thead><tr><th>Subset</th><th class="n">Places</th><th class="n">No-change error (σ)</th><th class="n">Projection error (σ)</th>'
            '<th class="n">Truth to predicted analog (σ)</th><th class="n">Under 1σ</th><th class="n">Best possible (σ)</th><th class="n">Own cell (σ)</th>'
            '<th class="n">Latitude shift (σ)</th><th class="n">Beats latitude shift</th></tr></thead><tbody>'
            + row("All sampled places", a) + row("Places whose change exceeded 1σ", d) +
            f"</tbody><caption>Table H. Medians. Errors are σ distances to the climate that actually occurred in {b0}–{b1}.</caption></table></div>"
            f"<p>The predicted analog was {a['km_predicted_to_oracle_median']:,.0f} km (median) from the best possible analog, and "
            f"{a['share_predicted_within_500km_of_oracle']:.0%} of predicted analogs were within 500 km of it. "
            f"The predicted analog was equatorward of the place for {a['share_equatorward']:.0%} of places.</p>")


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
    fills["ERA5_BLOCK"] = era5_html(S)                                  # era5-agreement
    fills["HINDCAST_BLOCK"] = hindcast_html()                           # hindcast
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
