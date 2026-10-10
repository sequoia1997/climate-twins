"""Command line and orchestration of the W3 pilot fit (one species end to end, resumable, plus the gate-table report).

  python -m ctw.species.run_pilot list   [--table data/species/pilot_v1.csv]            # JSON list of species slugs (workflow matrix)
  python -m ctw.species.run_pilot fit    --species "Acer saccharum" --out work/w3 [--synthetic] [--force]
  python -m ctw.species.run_pilot report --out work/w3 [--md work/w3/REPORT.md]

Per species the output directory <out>/<slug>/ holds:  fit.pkl + domain.npz (stage 1), summary.json + cts/*.cts (stage 2), DONE.
A rerun skips finished stages (resume after a cut-off job) unless --force. Real inputs come from ctw.species.inputs (W1 climate,
W2 occurrences); --synthetic uses virtual species on the synthetic climate for a dry run of the whole chain.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import pickle
import platform
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

from . import grid, pipeline as PL, project as PR, summary as SM, cts, gates as G
from .grid import SSPS, PERIODS

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "data" / "species" / "pilot_v1.csv"


def slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")


def read_table(path: Path = TABLE) -> list:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["id"] = slug(r["scientific_name"])
    return rows


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def save_fit(fit: PL.Fit, d: Path):
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "domain.npz", train=fit.train, proj=fit.proj, pres_rc=fit.pres_rc)
    tr, pr, rc = fit.train, fit.proj, fit.pres_rc
    fit.train = fit.proj = fit.pres_rc = None
    try:
        with open(d / "fit.pkl", "wb") as f:
            pickle.dump(fit, f, protocol=4)
    finally:
        fit.train, fit.proj, fit.pres_rc = tr, pr, rc


def load_fit(d: Path) -> PL.Fit:
    with open(d / "fit.pkl", "rb") as f:
        fit = pickle.load(f)
    z = np.load(d / "domain.npz")
    fit.train, fit.proj, fit.pres_rc = z["train"], z["proj"], z["pres_rc"]
    return fit


def run_species(meta: dict, src, spec, occ, native, density, outdir: Path, *, land=None, ssps=SSPS, periods=PERIODS, cfg: PL.FitConfig = None,
                pcfg: PR.ProjConfig = None, gate_cfg: G.GateConfig = None, validation: dict = None, expert_kind: str = "native_range",
                dois: list = None, range_shift_test: dict = None, force: bool = False, product: str = "lite", log=print) -> dict:
    """Fit, project, summarise and write one species. Returns the summary dict."""
    cfg = cfg or PL.FitConfig()
    pcfg = pcfg or PR.ProjConfig()
    gate_cfg = gate_cfg or G.GateConfig()
    sid = meta["id"]
    d = Path(outdir) / sid
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if (d / "DONE").exists() and not force:
        log(f"{sid}: already done")
        return json.loads((d / "summary.json").read_text())
    if (d / "fit.pkl").exists() and not force:
        fit = load_fit(d)
        log(f"{sid}: resumed from fit.pkl")
    else:
        fit = PL.fit_species(meta["scientific_name"], spec, src, occ, land=land, native=native, density=density, group=meta.get("group"),
                             cfg=cfg, log=log)
        save_fit(fit, d)
    t1 = time.time()
    proj = PR.project_species(fit, src, ssps, periods, group=meta.get("group"), cfg=pcfg, log=log)
    t2 = time.time()
    summ = SM.build_summary(fit, proj, meta, expert=native, expert_kind=expert_kind, validation=validation, range_shift_test=range_shift_test, gate_cfg=gate_cfg, dois=dois)
    summ["provenance"] = dict(code=_git_sha(), python=platform.python_version(), seconds=dict(fit=round(t1 - t0, 1), project=round(t2 - t1, 1)),
                              made=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), grid=[spec.H, spec.W],
                              product=product, climate_models={f"{s}|{p}": proj.scen[(s, p)].n_models for (s, p) in proj.scen})
    (d / "summary.json").write_text(SM.dumps(summ))
    if summ["published"]:
        (d / "cts").mkdir(exist_ok=True)
        for name, data in cts.species_files(proj, sid, product, meta=dict(kind=summ["species_kind"], tier=summ["tier"], range_shifts_tested=summ["range_shifts_tested"], cv_kind=summ["cv_kind"], confidence=summ["confidence"])).items():
            (d / "cts" / name).write_bytes(data)
        info = cts.prototype_stats_entry(summ)
        (d / "cts" / "stats_entry.json").write_text(json.dumps(info, separators=(",", ":")))
    (d / "DONE").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    log(f"{sid}: tier {summ['tier']} shifts {summ['range_shifts_tested']} ({summ['confidence']}), AUC {summ['skill']['cv_auc']}, {time.time() - t0:.0f} s")
    return summ


# --------------------------------------------------------------------------- report
def _f(x, nd=2):
    return "" if x is None else (f"{x:.{nd}f}" if isinstance(x, (int, float)) else str(x))


def report(out: Path, key: str = "SSP2-4.5|2081-2100") -> str:
    """Markdown gate table from every summary.json under `out`."""
    rows = []
    for p in sorted(Path(out).glob("*/summary.json")):
        rows.append(json.loads(p.read_text()))
    lines = ["# W3 fit report: gate table", "",
             f"Species fitted: {len(rows)}. Tier A = static skill validated against an independent survey, Tier B = spatial-block CV skill only, Tier C = below a hard gate (not shown); 'shifts' = range-shift test pass/fail/untested. "
             f"Change columns are the unlimited-dispersal area change for {key}; 'withheld' means more than 15% novel climate.", "",
             "| species | group | tier | shifts | CV kind | conf. | thinned cells | CV AUC | CV TSS | Boyce | check GAM AUC | range check | novel % | area now (1000 km2) | change % | shift km | reasons |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in rows:
        sp, sk, g = s["species"], s["skill"], s["gates"]
        sc = s["scenarios"].get(key, {})
        m = sc.get("modes", {}).get("unlimited", {})
        gam = (sk.get("check_model") or {}).get("auc")
        rc = g["range_check"]
        why = "; ".join(s["hard_failures"] + s["soft_flags"])
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            sp["scientific_name"], sp.get("group") or "", s["tier"], s.get("range_shifts_tested"), s.get("cv_kind"), s["confidence"], s["records"]["gate_cells"], _f(sk["cv_auc"]), _f(sk["cv_tss"]),
            _f(sk["cv_boyce"]), _f(gam), rc["status"], "" if sc.get("novel_share") is None else f"{100 * sc['novel_share']:.0f}",
            _f(s["area_now_km2"] / 1000, 0), "withheld" if sc.get("withheld") else _f(m.get("change_pct"), 1),
            "withheld" if sc.get("withheld") else _f(m.get("shift_km"), 0), why))
    lines += ["", "Thresholds: 100 thinned records (per 0.125 degree cell), CV AUC 0.7 (floor 0.6 uncalibrated), novel climate 15%, range check omission <= 0.40 and "
              "commission <= 0.30 (uncalibrated). Dispersal rule and gate limits are listed in each summary.json."]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- W4 evidence
def make_evidence(w4_json: Path, table: Path, out: Path) -> int:
    """W4's BBS hindcast (blocked presence-absence variant) -> per-species evidence files for --validation-dir / --shift-dir.
      validation/<id>.json  {kind: 'bbs', passed, static metrics}   passed = presence-absence blocked-CV skill gate AND window-2 transfer
      shift/<id>.json       {status: group change verdict ('fail' for the birds), group checks, species numbers}
    Species are matched to the pilot table by common name (case-insensitive). Species without BBS evidence get no file (untested)."""
    d = json.loads(Path(w4_json).read_text())["blocked"]
    names = {r["common_name"].strip().lower(): r for r in read_table(table)}
    (out / "validation").mkdir(parents=True, exist_ok=True)
    (out / "shift").mkdir(parents=True, exist_ok=True)
    n = 0
    for bbs_name, res in d["species"].items():
        r = names.get(bbs_name.strip().lower())
        if r is None:
            continue
        cv = res.get("cv") or {}
        passed = bool(res.get("cv_gate")) and bool(res.get("transfer_ok"))
        val = dict(kind="bbs", passed=passed, source=cv.get("source"), cv_auc=cv.get("auc"), cv_tss=cv.get("tss"), cv_boyce=cv.get("boyce"),
                   n_presence_routes=cv.get("n_pres"), n_absence_routes=cv.get("n_abs"), window2_auc=res.get("auc2"), window2_tss=res.get("tss2"),
                   window2_boyce=res.get("boyce2"), w3_background_cv=cv.get("w3_background_cv"), cv_gate=res.get("cv_gate"), transfer_ok=res.get("transfer_ok"),
                   from_file="data/species/w4/bbs_hindcast_results.json")
        g = d["group"]
        sh = dict(status="fail" if g["status"] == "fail" else ("pass" if g["status"] == "pass" else "untested"), group_status=g["status"],
                  group_checks=g["checks"], species_direction_agree=res.get("direction_agree"), species_shift_error_km=res.get("shift_error_km"),
                  species_nochange_error_km=res.get("shift_error_nochange_km"), interpretation=g.get("interpretation"),
                  from_file="data/species/w4/bbs_hindcast_results.json")
        (out / "validation" / f"{r['id']}.json").write_text(json.dumps(val, indent=1))
        (out / "shift" / f"{r['id']}.json").write_text(json.dumps(sh, indent=1))
        n += 1
    return n


# --------------------------------------------------------------------------- main
def _synthetic_inputs(name: str):
    from . import synthetic as SY
    src = grid.SyntheticClimate(grid.GridSpec(180, 360), n_models=4)
    cat = {v.name: v for v in SY.CATALOGUE}
    v = cat[name]
    d = SY.make(src, v)
    return src, src.spec, d["occ"], d["native"], d["density"], d["land"], v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list")
    a.add_argument("--table", default=str(TABLE))
    a.add_argument("--synthetic", action="store_true")
    e = sub.add_parser("evidence")
    e.add_argument("--w4", default=str(ROOT / "data" / "species" / "w4" / "bbs_hindcast_results.json"))
    e.add_argument("--table", default=str(TABLE))
    e.add_argument("--out", default=str(ROOT / "data" / "species" / "w3" / "evidence"))
    sub.add_parser("models")
    t = sub.add_parser("tiles")
    t.add_argument("--species", required=True)
    t.add_argument("--table", default=str(TABLE))
    b = sub.add_parser("fit")
    b.add_argument("--species", required=True, help="scientific name (or slug)")
    b.add_argument("--table", default=str(TABLE))
    b.add_argument("--out", default="work/w3")
    b.add_argument("--synthetic", action="store_true")
    b.add_argument("--force", action="store_true")
    b.add_argument("--jobs", type=int, default=int(os.environ.get("W3_JOBS", os.cpu_count() or 1)))
    b.add_argument("--product", default="lite", choices=["lite", "full"])
    b.add_argument("--shift-dir", default=None, help="directory of <slug>.json range-shift test results (W4)")
    b.add_argument("--validation-dir", default=None, help="directory of <slug>.json external change-test evidence (e.g. BBS hindcast)")
    c = sub.add_parser("report")
    c.add_argument("--out", default="work/w3")
    c.add_argument("--md", default=None)
    c.add_argument("--key", default="SSP2-4.5|2081-2100")
    args = ap.parse_args(argv)
    if args.cmd == "list":
        if args.synthetic:
            from . import synthetic as SY
            print(json.dumps([v.name for v in SY.CATALOGUE]))
        else:
            print(json.dumps([r["id"] for r in read_table(Path(args.table))]))
        return 0
    if args.cmd == "evidence":
        n = make_evidence(Path(args.w4), Path(args.table), Path(args.out))
        print(f"wrote evidence for {n} species to {args.out}")
        return 0
    if args.cmd == "models":
        from . import inputs
        print(" ".join(inputs.tcr_likely_models()))
        return 0
    if args.cmd == "tiles":
        from . import inputs
        rows = {r["id"]: r for r in read_table(Path(args.table))}
        print(" ".join(inputs.tiles_for(rows[args.species]["native_continents_curated"])))
        return 0
    if args.cmd == "report":
        md = report(Path(args.out), args.key)
        if args.md:
            Path(args.md).write_text(md)
        print(md)
        return 0
    out = Path(args.out)
    cfg = PL.FitConfig(n_jobs=args.jobs)
    pcfg = PR.ProjConfig(n_jobs=args.jobs)
    validation = None
    if args.synthetic:
        src, spec, occ, native, density, land, v = _synthetic_inputs(args.species)
        meta = dict(id=slug(v.name), scientific_name=v.name, group=v.group, common_name=v.name + " (virtual)")
        run_species(meta, src, spec, occ, native, density, out, land=land, cfg=cfg, pcfg=pcfg, force=args.force, product=args.product)
        return 0
    from . import inputs                                             # real W1 / W2 data (see docs/pilot/W3-engine.md)
    rows = {r["id"]: r for r in read_table(Path(args.table))}
    rows.update({r["scientific_name"]: r for r in rows.values()})
    meta = rows[args.species]
    if args.validation_dir:
        p = Path(args.validation_dir) / f"{meta['id']}.json"
        validation = json.loads(p.read_text()) if p.exists() else None
    shift = None
    if args.shift_dir:
        p = Path(args.shift_dir) / f"{meta['id']}.json"
        shift = json.loads(p.read_text()) if p.exists() else None
    src, spec = inputs.climate_source()
    occ, native, density, dois = inputs.species_inputs(meta, spec)
    run_species(meta, src, spec, occ, native, density, out, cfg=cfg, pcfg=pcfg, validation=validation, range_shift_test=shift, dois=dois, force=args.force,
                product=args.product)
    return 0


if __name__ == "__main__":
    sys.exit(main())
