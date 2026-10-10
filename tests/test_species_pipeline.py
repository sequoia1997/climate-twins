"""Unit tests for the W3 production pipeline (ctw/species/{grid,pipeline,project,gates,summary,cts,run_pilot}.py).
All on a small synthetic world; deterministic; whole file runs in well under a minute. Run: pytest tests/test_species_pipeline.py"""
import json
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw.species import grid, pipeline as PL, project as PR, gates as G, summary as SM, cts, synthetic as SY, run_pilot as RP  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC = grid.GridSpec(120, 240)          # 1.5 degree cells


@pytest.fixture(scope="module")
def world():
    src = grid.SyntheticClimate(SPEC, n_models=3)
    v = SY.Virtual("t_broad", (("bio1", 12.0, 2.0), ("bio12", 700.0, 200.0)), 0.35, 500)
    d = SY.make(src, v)
    return src, v, d


@pytest.fixture(scope="module")
def fitted(world):
    src, v, d = world
    fit = PL.fit_species(v.name, SPEC, src, d["occ"], land=d["land"], native=d["native"], density=d["density"], cfg=PL.FitConfig(n_jobs=1))
    proj = PR.project_species(fit, src, grid.SSPS, grid.PERIODS, group="tree", cfg=PR.ProjConfig(band_rows=32))
    return fit, proj


# --------------------------------------------------------------------------- grid
def test_gridspec_geometry():
    s = grid.GridSpec()
    assert (s.H, s.W) == (4320, 8640)
    assert abs(s.lat(0) - (90 - 1 / 48)) < 1e-9 and abs(s.lon(0) - (-180 + 1 / 48)) < 1e-9
    assert abs(s.row_area_km2().astype(float).sum() * s.W - 4 * np.pi * grid.R_EARTH ** 2) < 1e3       # cells tile the sphere
    assert s.row_of(89.99) == 0 and s.row_of(-89.99) == 4319 and s.col_of(-179.99) == 0 and s.col_of(179.99) == 8639


def test_within_km_distance_and_buffer():
    s = grid.GridSpec(180, 360)                                    # 1 degree = ~111 km
    m = np.zeros((180, 360), bool)
    m[90, 180] = True
    near = grid.within_km(m, s, 250.0, factor=1)
    r, c = np.nonzero(near)
    assert near[m].all() and 11 <= near.sum() <= 25                 # a disc of radius ~2.2 cells (about 13 cells), always includes the cell
    d = grid.nearest_km(np.array([[90, 180]]), s, r, c)
    assert d.max() <= 250.0 + 1e-6
    assert not grid.within_km(m, s, 250.0, factor=1)[90, 190]       # 10 degrees away
    far = np.zeros((180, 360), bool)
    far[10, 5] = True
    assert grid.within_km(far, s, 0.0).sum() == 1 and grid.within_km(np.zeros((180, 360), bool), s, 500).sum() == 0


def test_grid_at_resamples_coarse_arrays():
    s = grid.GridSpec(8, 16)
    coarse = np.arange(4 * 8).reshape(4, 8)
    r, c = np.array([0, 1, 7]), np.array([0, 3, 15])
    assert list(PL.grid_at(coarse, s, r, c)) == [coarse[0, 0], coarse[0, 1], coarse[3, 7]]


def test_baseline_points_match_bands(world):
    src = world[0]
    rows, cols = np.array([10, 60, 61, 118]), np.array([5, 100, 3, 200])
    P = src.baseline_points(rows, cols, ("bio1", "bio12"), band_rows=50)
    full = src.baseline_band(0, SPEC.H, ("bio1", "bio12"))
    assert np.allclose(P, full[:, rows, cols].T, equal_nan=True)


# --------------------------------------------------------------------------- predictor selection
def test_select_predictors_prunes_correlated_in_priority_order():
    rng = np.random.default_rng(0)
    a = rng.normal(size=3000)
    X = np.stack([a, a * 2 + rng.normal(0, 0.1, 3000), rng.normal(size=3000), -a + rng.normal(0, 0.5, 3000)], 1)
    kept, dropped = PL.select_predictors(X, ["bio1", "bio5", "bio12", "bio6"], ("bio1", "bio6", "bio5", "bio12"), 0.7, 5)
    assert kept == ["bio1", "bio12"]                                # bio6 correlates with bio1 (|r| about 0.9), bio5 too
    assert dropped["bio6"]["with_"] == "bio1" and dropped["bio5"]["reason"] == "correlated"
    kept2, d2 = PL.select_predictors(X, ["bio1", "bio5", "bio12", "bio6"], ("bio12", "bio5", "bio1", "bio6"), 0.7, 5)
    assert kept2 == ["bio12", "bio5"]                               # order decides which of a correlated pair survives
    kept3, d3 = PL.select_predictors(X, ["bio1", "bio5", "bio12", "bio6"], ("bio1", "bio12", "bio6", "bio5"), 0.7, 1)
    assert kept3 == ["bio1"] and d3["bio12"]["reason"] == "cap"


# --------------------------------------------------------------------------- background and domains
def test_target_group_background_follows_density_and_stays_in_domain():
    dom = np.zeros((40, 80), bool)
    dom[10:30, 20:60] = True
    dens = np.zeros((40, 80))
    dens[:, 40:] = 9.0
    dens[:, :40] = 1.0
    rng = np.random.default_rng(1)
    r, c = PL.sample_cells(dom, lambda rr, cc: dens[rr, cc], 20000, rng, floor=0.0)
    assert dom[r, c].all()
    east = (c >= 40).mean()
    assert abs(east - 0.9) < 0.02                                   # 9:1 density -> 90% of the background in the east half
    r2, c2 = PL.sample_cells(dom, None, 20000, rng)
    assert abs((c2 >= 40).mean() - 0.5) < 0.02
    r3, c3 = PL.sample_cells(dom, lambda rr, cc: dens[rr, cc] * (cc >= 40), 20000, rng, floor=0.1)
    assert 0.03 < (c3 < 40).mean() < 0.07                           # the uniform floor keeps the west reachable


def test_domains_native_plus_buffer_excludes_other_continents(world):
    src, v, d = world
    rc = d["occ"].unique_cells()
    train, proj = PL.domains(SPEC, d["land"], rc, d["native"], PL.FitConfig())
    rec = np.zeros_like(train)
    rec[rc[:, 0], rc[:, 1]] = True
    assert not (train & ~d["land"] & ~rec).any() and not (proj & ~d["land"] & ~rec).any()          # land only
    assert (train >= (d["native"] & d["land"])).all() and (proj >= train).all()
    cfg = PL.FitConfig()
    assert not (train & ~rec & ~grid.within_km(d["native"], SPEC, cfg.train_buffer_km + 120)).any()   # nothing beyond native + buffer
    assert not (proj & ~rec & ~grid.within_km(d["native"], SPEC, cfg.proj_buffer_km + 120)).any()
    assert (proj & ~train).any()
    # without a native mask the record cells stand in for the range
    t2, p2 = PL.domains(SPEC, d["land"], rc, None, PL.FitConfig())
    assert t2.sum() > 0 and p2.sum() >= t2.sum()


def test_prepare_records_flags_and_gate_cells():
    occ = grid.Occurrences([4, 4, 5, 7, 40], [4, 4, 5, 9, 40], flags=[0, 0, 0, 1, 0])
    cfg = PL.FitConfig(gate_cell_deg=3.0)                           # 1.5 degree grid -> 2 x 2 blocks
    rec = PL.prepare_records(occ, SPEC, cfg)
    assert rec["n_raw"] == 5 and rec["n_flagged"] == 1 and rec["n_cells"] == 3
    assert rec["n_gate"] == 2                                       # (4,4) and (5,5) share a 2x2 block; (40,40) is another
    assert len(PL.prepare_records(occ, SPEC, PL.FitConfig(allow_flags=1))["rc"]) == 4


# --------------------------------------------------------------------------- fit
def test_fit_is_deterministic_and_reports_skill(world, fitted):
    src, v, d = world
    fit, _ = fitted
    fit2 = PL.fit_species(v.name, SPEC, src, d["occ"], land=d["land"], native=d["native"], density=d["density"], cfg=PL.FitConfig(n_jobs=1))
    assert fit.pred == fit2.pred and np.isclose(fit.thr, fit2.thr)
    m = fit.cv["metrics"]["gbm"]
    assert 0.6 < m["auc"] <= 1.0 and m["boyce"] > 0.5 and fit.cv["folds_used"] >= 3
    assert "gam" in fit.cv["metrics"] and fit.check_thr is not None
    assert len(fit.pred) <= 5 and "bio1" in fit.pred
    assert fit.thr_all["minpres"] <= fit.thr_all["p05"] <= fit.thr_all["p10"]
    assert fit.note["threshold_source"] == "out-of-fold"


def test_fit_recovers_truth_roughly(world, fitted):
    src, v, d = world
    fit, proj = fitted
    pred = proj.now & fit.proj
    truth = d["truth"]
    a = np.outer(SPEC.row_area_km2(), np.ones(SPEC.W))
    from ctw.species import sdm
    r = sdm.range_agreement(pred, truth, a)
    assert r["sens"] > 0.85 and r["sorensen"] > 0.8                  # synthetic world, coarse cells: a loose bound, not an accuracy claim


def test_uniform_background_option_runs(world):
    src, v, d = world
    fit = PL.fit_species(v.name, SPEC, src, d["occ"], land=d["land"], native=d["native"], density=None, cfg=PL.FitConfig(bias="uniform", check_model=False))
    assert fit.check is None and np.isfinite(fit.cv["metrics"]["gbm"]["auc"])


def test_too_few_records_do_not_crash():
    src = grid.SyntheticClimate(SPEC, n_models=2)
    occ = grid.Occurrences([60, 61, 62], [100, 101, 102])
    fit = PL.fit_species("tiny", SPEC, src, occ, cfg=PL.FitConfig(check_model=False))
    assert np.isnan(fit.cv["metrics"]["gbm"]["auc"]) and fit.records["n_gate"] <= 3


# --------------------------------------------------------------------------- projection
def test_quantise_threshold_maps_to_44_and_is_monotone():
    s = np.linspace(0, 1, 5001)
    for thr in (0.05, 0.3, 0.77):
        q = PR.quantise(s, thr)
        assert ((q >= PR.THR7) == (s >= thr)).all() and q.max() == 127 and (np.diff(q.astype(int)) >= 0).all()
    assert PR.quantise(np.array([np.nan]), 0.3)[0] == 0


def test_projection_outputs_and_dispersal_nesting(fitted):
    fit, proj = fitted
    assert proj.S0.dtype == np.uint8 and proj.S0.shape == (SPEC.H, SPEC.W)
    assert not proj.S0[~fit.proj].any()                                # nothing outside the projection domain
    for (ssp, per), sc in proj.scen.items():
        assert sc.n_models == 3 and sc.S.shape == proj.S0.shape and sc.A.max() <= 15 and set(np.unique(sc.N)) <= {0, 1}
        un, li, no = (proj.binary((ssp, per), m) for m in PR.MODES)
        assert (no <= li).all() and (li <= un).all()                   # none within limited within unlimited
        assert not (no & ~proj.now).any()
        assert not (sc.S[~fit.proj]).any()
    assert proj.reach_km["2081-2100"] > proj.reach_km["2041-2060"] > 0
    assert (proj.reach["2041-2060"] <= proj.reach["2081-2100"]).all() and (proj.now <= proj.reach["2041-2060"]).all()
    # warmer scenario/period -> more novel cells and a larger centroid move for this warm-limited species is not guaranteed, but novelty grows
    n1 = proj.scen[("SSP2-4.5", "2041-2060")].N.sum()
    n2 = proj.scen[("SSP5-8.5", "2081-2100")].N.sum()
    assert n2 >= n1


def test_projection_streaming_is_band_size_independent(world, fitted):
    src, v, d = world
    fit, proj = fitted
    p2 = PR.project_species(fit, src, ("SSP5-8.5",), ("2081-2100",), group="tree", cfg=PR.ProjConfig(band_rows=17))
    a, b = proj.scen[("SSP5-8.5", "2081-2100")], p2.scen[("SSP5-8.5", "2081-2100")]
    assert (a.S == b.S).all() and (a.A == b.A).all() and (a.N == b.N).all() and (proj.S0 == p2.S0).all()


def test_projection_agrees_with_direct_scoring(world, fitted):
    """The streamed median over models equals scoring all models at once for a few cells."""
    src, v, d = world
    fit, proj = fitted
    sc = proj.scen[("SSP2-4.5", "2041-2060")]
    r, c = np.nonzero(fit.proj)
    pick = np.linspace(0, len(r) - 1, 50).astype(int)
    scores = []
    for m in src.future_models("SSP2-4.5", "2041-2060"):
        X = np.array([src.future_band("SSP2-4.5", "2041-2060", m, int(rr), int(rr) + 1, fit.pred)[:, 0, cc] for rr, cc in zip(r[pick], c[pick])], float)
        scores.append(np.where(np.isfinite(X).all(1), fit.score(np.nan_to_num(X)), 0.0))
    med = np.median(np.array(scores), 0)
    assert (PR.quantise(med, fit.thr) == sc.S[r[pick], c[pick]]).all()


def test_dispersal_rule_is_marked_uncalibrated():
    v, note = PR.dispersal_rule("tree")
    assert v == 15.0 and "uncalibrated" in note
    v2, note2 = PR.dispersal_rule("bird", 77.0)
    assert v2 == 77.0 and "uncalibrated" in note2
    assert PR.dispersal_rule("nonsense")[0] == PR.DISPERSAL_DEFAULT


# --------------------------------------------------------------------------- gates
def _ev(**kw):
    base = dict(n_gate=600, n_used=600, cv_auc=0.8, area_now=1e6, novel_shares={"a|b": 0.05}, check_change={"a|b": 5.0}, main_change={"a|b": 8.0},
                rng_check=dict(status="pass", unrecorded_share=0.1), validation=None)
    base.update(kw)
    return G.evaluate(**base)


def test_gate_tiers():
    assert _ev()["tier"] == "B" and _ev()["confidence"] == "standard" and _ev()["published"]
    assert _ev(validation=dict(kind="bbs", passed=True))["tier"] == "A"
    assert _ev(validation=dict(kind="bbs", passed=False))["tier"] == "B"
    assert _ev(validation=dict(kind="gbif_before_after", passed=True))["tier"] == "B"          # not in tierA_kinds by default
    e = _ev(n_gate=99)
    assert e["tier"] == "C" and not e["published"] and "fewer than 100" in e["hard_failures"][0]
    e = _ev(cv_auc=0.65)                                                                     # lower discrimination: tier kept, confidence low
    assert e["tier"] == "B" and e["confidence"] == "low" and "lower discrimination" in e["soft_flags"][0]
    assert _ev(cv_auc=0.52)["tier"] == "B" and _ev(cv_auc=0.52)["confidence"] == "low" and _ev(cv_auc=0.45)["tier"] == "C" and _ev(cv_auc=float("nan"))["tier"] == "C"
    assert _ev(n_gate=250)["confidence"] == "low"
    assert _ev(area_now=5e4, n_gate=400)["confidence"] == "low"                              # narrow range needs about 500
    assert _ev(area_now=5e4, n_gate=600)["confidence"] == "standard"
    assert _ev(rng_check=dict(status="missing"))["tier"] == "C"                                # the range check is mandatory
    assert _ev(rng_check=dict(status="fail", omission=0.5, commission=0.1))["tier"] == "C"
    assert _ev(check_change={"a|b": -40.0})["confidence"] == "low"


def test_novelty_gate_withholds_per_scenario():
    e = _ev(novel_shares={"x": 0.16, "y": 0.15, "z": 0.0})
    assert e["withheld"] == {"x": True, "y": False, "z": False} and e["tier"] == "B"


def test_range_check_flags_non_climatic_limits(world):
    src, v, d = world
    rc = d["occ"].unique_cells()
    now = d["truth"].copy()
    ok = G.range_check(now, SPEC, rc, d["native"])
    assert ok["status"] == "pass" and ok["omission"] < 0.05 and ok["commission"] == 0.0 or ok["commission"] < 0.3
    over = now | grid.within_km(now, SPEC, 4000.0)                  # a model that spills far outside the native range
    bad = G.range_check(over & d["land"], SPEC, rc, d["native"])
    assert bad["status"] == "fail" and bad["commission"] > 0.3
    assert G.range_check(now, SPEC, rc, None)["status"] == "missing"
    assert G.range_check(now, SPEC, rc, None)["unrecorded_share"] is not None


# --------------------------------------------------------------------------- summary
def test_summary_content_and_json(world, fitted):
    src, v, d = world
    fit, proj = fitted
    meta = dict(scientific_name=v.name, common_name="Virtual", group="tree", gbif_taxon_key="1", validation_plan="spatial CV only")
    s = SM.build_summary(fit, proj, meta, expert=d["native"], dois=["10.15468/dl.example"])
    s2 = json.loads(SM.dumps(s))
    assert s2["schema"] == SM.SCHEMA and s2["tier"] in ("A", "B", "C") and s2["data_dois"] == ["10.15468/dl.example"]
    assert s2["gates"]["range_check"]["kind"] == "native_range" and s2["gate_config"]["min_records"] == 100
    k = "SSP5-8.5|2081-2100"
    sc = s2["scenarios"][k]
    assert set(sc["modes"]) == {"unlimited", "limited", "none"} or sc.get("withheld")
    if not sc.get("withheld"):
        u, n = sc["modes"]["unlimited"], sc["modes"]["none"]
        assert abs(u["area_now"] - s2["area_now_km2"]) < 1.0
        assert abs(u["gain"] + u["stable"] - u["area_fut"]) < 1.0 and abs(u["loss"] + u["stable"] - u["area_now"]) < 1.0
        assert n["gain"] == 0 and n["area_fut"] <= u["area_fut"] + 1e-6
        assert 0 <= u["agree_share"] <= 1 and (u["shift_km"] is None or u["shift_km"] >= 0)
    assert s2["dispersal"]["calibrated"] is False and s2["predictors"]["kept"] == fit.pred
    assert s2["records"]["gate_cells"] == fit.records["n_gate"] and "audit_withheld" in s2


def test_summary_withholds_numbers_when_novel_above_limit(world, fitted):
    src, v, d = world
    fit, proj = fitted
    strict = G.GateConfig(novel_max=-1.0)                            # everything counts as too novel
    s = SM.build_summary(fit, proj, dict(scientific_name=v.name, group="tree"), expert=d["native"], gate_cfg=strict)
    for k, sc in s["scenarios"].items():
        assert sc["withheld"] and all(m.get("withheld") for m in sc["modes"].values())
        assert "shift_km" not in sc["modes"]["unlimited"] and k in s["audit_withheld"]
        assert "withheld" in sc["withheld_reason"] or "novel" in sc["withheld_reason"]


# --------------------------------------------------------------------------- CTS
def _rand_bands(rng, h=300, w=520):
    S = (rng.random((h, w)) * 4).astype(np.uint8)
    S[:, :200] = 0                                                   # empty blocks cost nothing
    S[40:120, 300:420] |= 128
    A = (rng.integers(0, 16, (h, w)) * 16 + rng.integers(0, 16, (h, w))).astype(np.uint8)
    return S, A


def test_cts_roundtrip_all_levels():
    rng = np.random.default_rng(0)
    S, A = _rand_bands(rng)
    N = (rng.random(S.shape) < 0.1).astype(np.uint8)
    data = cts.encode({"S1": S, "A": A, "N": N}, ["S1", "A", "N"])
    out = cts.decode(data)
    assert (out["S1"] == S).all() and (out["A"] == A).all() and (out["N"] == N).all()
    o2 = cts.decode(data, 2)
    assert (o2["S1"] == cts.pool(S, "S", 2)).all() and (o2["A"] == cts.pool(A, "A", 2)).all() and (o2["N"] == cts.pool(N, "N", 2)).all()
    hdr = json.loads(data[8:8 + int.from_bytes(data[4:8], "little")])
    assert hdr["bands"] == ["S1", "A", "N"] and hdr["lon0"] == -180 and hdr["lat0"] == 90 and hdr["levels"][0]["w"] == 520
    empty = cts.encode({"S0": np.zeros((300, 520), np.uint8)}, ["S0"])
    assert len(empty) < 600                                           # header and an all-zero index only


def test_cts_is_byte_identical_to_the_prototype_encoder():
    f = ROOT / "prototypes" / "species" / "data" / "s01_base.cts"
    if not f.exists():
        pytest.skip("prototype data not present")
    raw = f.read_bytes()
    dec = cts.decode(raw)
    assert cts.encode(dec, ["S0"]) == raw
    f2 = ROOT / "prototypes" / "species" / "data" / "s01_ssp245.cts"
    d2 = cts.decode(f2.read_bytes())
    assert cts.encode(d2, ["S1", "S2", "A"]) == f2.read_bytes()


def test_species_files_and_prototype_stats(world, fitted):
    src, v, d = world
    fit, proj = fitted
    files = cts.species_files(proj, "tbroad")
    assert set(files) == {"tbroad_base.cts", "tbroad_ssp245.cts", "tbroad_ssp585.cts"}
    base = cts.decode(files["tbroad_base.cts"])["S0"]
    assert ((base > 0) == proj.now).all() and base.max() <= 3
    sc = cts.decode(files["tbroad_ssp585.cts"])
    near, late = proj.scen[("SSP5-8.5", "2041-2060")], proj.scen[("SSP5-8.5", "2081-2100")]
    assert ((sc["S1"] & 127) > 0).tolist() == (near.S >= PR.THR7).tolist()
    assert ((sc["S2"] >> 7).astype(bool) == proj.reach["2081-2100"]).all()
    assert (sc["A"] >> 4 == near.A).all() and (sc["A"] & 15 == late.A).all()
    assert (sc["N"] & 1 == near.N).all() and (sc["N"] >> 1 == late.N).all()
    full = cts.decode(cts.species_files(proj, "tbroad", "full")["tbroad_base.cts"])["S0"]
    assert (full == proj.S0).all()
    s = SM.build_summary(fit, proj, dict(scientific_name=v.name, group="tree"), expert=d["native"])
    e = cts.prototype_stats_entry(s)
    assert e["tier"] == s["tier"] and e["area_now_km2"] == s["area_now_km2"]
    if not s["scenarios"]["SSP2-4.5|2081-2100"].get("withheld"):
        m = e["by"]["ssp245|2100|limited"]
        assert set(m) >= {"now", "fut", "lost", "kept", "gained", "c0", "c1", "shift_km", "bearing", "agree_share"}


# --------------------------------------------------------------------------- orchestration
def test_run_species_resumes_and_writes_everything(tmp_path, world):
    src, v, d = world
    meta = dict(id="t_broad", scientific_name=v.name, group="tree")
    cfg = PL.FitConfig(check_model=False)
    s1 = RP.run_species(meta, src, SPEC, d["occ"], d["native"], d["density"], tmp_path, land=d["land"], cfg=cfg, pcfg=PR.ProjConfig(band_rows=40),
                        log=lambda *a: None)
    out = tmp_path / "t_broad"
    assert (out / "DONE").exists() and (out / "summary.json").exists() and (out / "fit.pkl").exists()
    assert s1["provenance"]["grid"] == [120, 240]
    if s1["published"]:
        assert (out / "cts" / "t_broad_base.cts").exists() and (out / "cts" / "stats_entry.json").exists()
    mt = (out / "summary.json").stat().st_mtime_ns
    RP.run_species(meta, None, SPEC, None, None, None, tmp_path, log=lambda *a: None)          # DONE: nothing is recomputed, no inputs touched
    assert (out / "summary.json").stat().st_mtime_ns == mt
    (out / "DONE").unlink()
    (out / "summary.json").unlink()
    s3 = RP.run_species(meta, src, SPEC, None, d["native"], None, tmp_path, cfg=cfg, pcfg=PR.ProjConfig(band_rows=40), log=lambda *a: None)   # resumes from fit.pkl
    assert s3["tier"] == s1["tier"] and s3["skill"]["cv_auc"] == s1["skill"]["cv_auc"]
    md = RP.report(tmp_path)
    assert "| t_broad |" in md and "CV AUC" in md


def test_pilot_table_reads():
    rows = RP.read_table()
    assert len(rows) == 25 and rows[0]["id"] == "turdus_migratorius" and rows[0]["group"] == "bird"


def test_window_years_and_score_cells_for_hindcast(world):
    src, v, d = world
    base = PL.fit_species(v.name, SPEC, src, d["occ"], land=d["land"], native=d["native"], density=d["density"], cfg=PL.FitConfig(check_model=False))
    early = PL.fit_species(v.name, SPEC, src, d["occ"], land=d["land"], native=d["native"], density=d["density"],
                           cfg=PL.FitConfig(check_model=False, years=(1990, 2002), window="1966-1985"))
    assert 0 < early.records["n_used"] < base.records["n_used"]
    r, c = np.nonzero(d["truth"])
    a = early.score_cells(src, r, c, "1966-1985")
    b = early.score_cells(src, r, c, "2005-2024")
    assert np.isfinite(a).all() and np.isfinite(b).all() and not np.allclose(a, b)        # the climate window changes the score
    assert np.isnan(early.score_cells(src, np.array([0]), np.array([0]), "2005-2024")).all()      # no data -> NaN


def test_tiles_for_continents():
    from ctw.species import inputs
    assert "r1c1" in inputs.tiles_for("NORTH_AMERICA") and "r0c2" in inputs.tiles_for("EUROPE;ASIA(W)")
    assert len(inputs.tiles_for("")) == 16


def test_range_shift_status_is_recorded_separately_and_never_changes_tier():
    base = _ev()
    assert base["range_shifts_tested"] == "untested" and base["cv_kind"] == "presence_background"
    fail = _ev(validation=dict(kind="bbs", passed=True), range_shift_test=dict(status="fail"), cv_kind="presence_absence")
    assert fail["tier"] == "A" and fail["range_shifts_tested"] == "fail" and fail["cv_kind"] == "presence_absence"
    assert _ev(range_shift_test=dict(passed=True))["range_shifts_tested"] == "pass"
    assert "expected range" in base["wording"] and "projected climate suitability" in base["wording"]


def test_absences_make_the_cv_presence_absence(world):
    src, v, d = world
    ab = grid.Occurrences(*np.nonzero(d["land"] & ~d["truth"]))
    fit = PL.fit_species(v.name, SPEC, src, d["occ"], land=d["land"], native=d["native"], absences=ab, cfg=PL.FitConfig(check_model=False))
    assert fit.cv["kind"] == "presence_absence" and fit.records["n_bg"] > 100
    s = SM.build_summary(fit, PR.project_species(fit, src, ("SSP5-8.5",), ("2081-2100",), group="tree"), dict(scientific_name=v.name, group="tree"),
                         expert=d["native"], validation=dict(kind="bbs", passed=True), range_shift_test=dict(status="fail"))
    assert s["skill"]["cv_kind"] == "presence_absence" and s["range_shifts_tested"] == "fail" and s["cv_kind"] == "presence_absence"


def test_cts_meta_in_header(world, fitted):
    fit, proj = fitted
    f = cts.species_files(proj, "x", meta=dict(tier="B", range_shifts_tested="untested", cv_kind="presence_background"))
    data = f["x_base.cts"]
    hdr = json.loads(data[8:8 + int.from_bytes(data[4:8], "little")])
    assert hdr["meta"]["tier"] == "B" and hdr["meta"]["range_shifts_tested"] == "untested"
    assert (cts.decode(data)["S0"] > 0).sum() == proj.now.sum()
