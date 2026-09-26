"""Assemble the deployable site: web/ templates -> site/ (index.html, methods.html; data files are already there).
The data version is stamped into index.html so browsers fetch new data after each release, and the methods
page's release numbers are filled from the build summary."""
from __future__ import annotations
import json, re
from . import common as C


def run(cfg=None):
    cfg = cfg or C.config()
    S = json.load(open(C.SITE / "data" / "summary.json"))
    na = json.load(open(C.DATA / "feature_calibration.json"))
    web = C.ROOT / "web"
    idx = (web / "index.html").read_text()
    assert "__DATA_VERSION__" in idx
    (C.SITE / "index.html").write_text(idx.replace("__DATA_VERSION__", S["data_version"]))
    (C.SITE / "world.dat").unlink(missing_ok=True)              # v9 kept world data beside index.html
    m = (web / "methods.html").read_text()
    fills = {"DATA_VERSION": S["data_version"], "RELEASE": S["method_version"], "RECENT_FIRST": str(S["recent_years"][0]),
             "RECENT_LAST": str(S["recent_years"][1]), "N_MODELS": str(S["n_models"]),
             "HZ_R2": f"{na['hardiness']['r2']:.2f}", "HZ_ERR": f"{na['hardiness']['median_abs_err_c']:.1f}",
             "HZ_SAME": f"{na['hardiness']['same_half_zone']:.0%}", "HZ_ONE": f"{na['hardiness']['within_one_half_zone']:.0%}",
             "FFP_R2": f"{na['ffp']['r2']:.2f}", "FFP_ERR": f"{na['ffp']['median_abs_err_days']:.0f}",
             "SELFCHK": f"{S['selfchk_median']:.2f}", "SL_N": str(S["sealevel_places"]),
             "REPO_LINK": (f'<a href="{cfg["release"]["repo_url"]}">{cfg["release"]["repo_url"]}</a>' if cfg["release"].get("repo_url") else "source code in the project repository")}
    for k, v in fills.items():
        m = m.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_0-9]+\}\}", m)
    assert not left, f"unfilled methods placeholders: {left}"
    (C.SITE / "methods.html").write_text(m)
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
