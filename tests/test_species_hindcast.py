"""Unit tests for ctw/species/hindcast.py on synthetic data (no model library needed)."""
import math
import numpy as np
from ctw.species import hindcast as H


def world(shift_deg=2.0, noise=0.0, seed=0, lo=35.0, hi=45.0):
    """Grid of 1-degree cells; species occupies lat lo..hi in window 1 and lo+shift..hi+shift in window 2.
    Score is a smooth bump on latitude, so the model can reproduce (or miss) the shift."""
    la, lo_ = np.meshgrid(np.arange(25.5, 60.5, 1.0), np.arange(-100.5, -80.5, 1.0), indexing="ij")
    lat, lon = la.ravel(), lo_.ravel()
    area = np.cos(np.radians(lat)) * 1.0
    rng = np.random.default_rng(seed)
    def occ(l0, h0): return (lat >= l0) & (lat <= h0)
    def score(l0, h0): return np.clip(1 - np.abs(lat - (l0 + h0) / 2) / ((h0 - l0) / 2 + 3), 0, 1) + rng.normal(0, noise, len(lat)) * 0.01
    return lat, lon, area, occ, score


def cellset(model_shift, obs_shift, noise=0.0, seed=0):
    lat, lon, area, occ, score = world(seed=seed, noise=noise)
    return H.CellSet(lat, lon, area, occ(35, 45), occ(35 + obs_shift, 45 + obs_shift), np.clip(score(35, 45), 0, 1), np.clip(score(35 + model_shift, 45 + model_shift), 0, 1), thr=0.5)


def test_range_change_north_shift():
    lat, lon, area, occ, _ = world()
    r = H.range_change(lat, lon, area, occ(35, 45), occ(37, 47))
    assert 200 < r["km"] < 240 and abs(r["bearing"]) < 3 or abs(r["bearing"] - 360) < 3
    assert abs(r["edge_hi_km"] - 2 * H.KM_PER_DEG) < 40 and abs(r["edge_lo_km"] - 2 * H.KM_PER_DEG) < 40
    assert abs(r["area_change"]) < 0.05
    assert r["north"] > 190 and abs(r["east"]) < 5


def test_range_change_no_change_and_empty():
    lat, lon, area, occ, _ = world()
    r = H.range_change(lat, lon, area, occ(35, 45), occ(35, 45))
    assert r["km"] == 0.0 and r["area_change"] == 0.0
    e = H.range_change(lat, lon, area, occ(35, 45), occ(80, 90))
    assert math.isnan(e["km"]) and e["area2"] == 0


def test_vec_error_perfect_and_opposite():
    a = dict(north=100.0, east=0.0); b = dict(north=-100.0, east=0.0)
    assert H.vec_error(a, a) == 0 and H.vec_error(a, b) == 200


def test_random_null_median():
    e = H.random_shift_errors(100.0, n=20000)
    assert 100 * 1.25 < np.median(e) < 100 * 1.45     # median of 2s|sin(d/2)| is s*sqrt(2) = 141 km
    assert e.max() <= 200.0 + 1e-9


def test_observed_change_detectable_and_bootstrap():
    cs = cellset(2, 3)
    o = H.observed_change(cs, n_boot=60, seed=1)
    assert o["detectable"] and o["north_lo"] > 0 and o["km_se"] >= 0
    # no change: not detectable
    z = H.observed_change(cellset(0, 0), n_boot=60)
    assert not z["detectable"]


def test_cluster_bootstrap_runs():
    cs = cellset(0, 2)
    cs.cluster = np.arange(len(cs.lat)) // 7
    o = H.observed_change(cs, n_boot=30)
    assert np.isfinite(o["km_se"])


def test_evaluate_good_model_beats_null():
    cs = cellset(model_shift=2, obs_shift=2)
    r = H.evaluate_species(cs, n_boot=60, cv=dict(tss=0.6, auc=0.85))
    assert r["direction_agree"] is True and r["beats_null"] and r["beats_nochange_shift"]
    assert 0.6 < r["shift_ratio"] < 1.6 and r["bearing_error"] < 20
    assert r["cv_gate"] and r["transfer_ok"] and r["auc2"] > 0.9
    assert r["shift_error_km"] < r["shift_error_nochange_km"]


def test_evaluate_static_model_fails_change():
    cs = cellset(model_shift=0, obs_shift=3)
    r = H.evaluate_species(cs, n_boot=60, cv=dict(tss=0.6, auc=0.85))
    assert not r["beats_null"] and r["shift_ratio"] < 0.1
    assert r["direction_agree"] is False       # zero modelled north component vs observed northward shift: sign 0 != 1


def test_evaluate_wrong_direction():
    cs = cellset(model_shift=-3, obs_shift=3)
    r = H.evaluate_species(cs, n_boot=60)
    assert r["direction_agree"] is False and r["bearing_error"] > 150 and not r["beats_nochange_shift"]


def test_skill_gate_flags():
    cs = cellset(2, 2)
    assert H.evaluate_species(cs, n_boot=20, cv=dict(tss=0.3, auc=0.9))["cv_gate"] is False
    assert H.evaluate_species(cs, n_boot=20)["cv_gate"] is None


def _many(n, model_shift, obs_shift=2.0):
    return {f"sp{i}": cellset(model_shift, obs_shift + 0.0 * i, seed=i) for i in range(n)}


def test_insufficient_data_is_not_a_pass():
    res, g, v = H.run_test(_many(10, 2), "bbs", cv={f"sp{i}": dict(tss=0.7, auc=0.9) for i in range(10)}, n_boot=30, n_eligible=10)
    assert g["status"] == "insufficient data" and g["n_eligible"] == 10 and g["need"] == 30
    assert all(not x["tier1"] for x in v.values()) and "insufficient" in " ".join(v["sp0"]["reasons"])
    assert "Not a test" in g["interpretation"]


def test_group_pass_and_tier1():
    n = 32
    cv = {f"sp{i}": dict(tss=0.7, auc=0.9) for i in range(n)}
    res, g, v = H.run_test(_many(n, 2), "bbs", cv=cv, n_boot=20, n_eligible=n)
    assert g["status"] == "pass", g["checks"]
    assert all(x["tier1"] for x in v.values())


def test_group_fail_static_model():
    n = 32
    cv = {f"sp{i}": dict(tss=0.7, auc=0.9) for i in range(n)}
    res, g, v = H.run_test(_many(n, 0), "bbs", cv=cv, n_boot=20, n_eligible=n)
    assert g["status"] == "fail" and not any(x["tier1"] for x in v.values())
    assert "hide future projections" in g["interpretation"] or "label" in g["interpretation"]


def test_direction_binomial_threshold():
    # 12 of 12 correct passes p<0.05; 8 of 12 does not reach 70% with significance
    assert H.binom_p_one_sided(12, 12) < 0.001
    assert H.binom_p_one_sided(8, 12) > 0.05
    assert abs(H.binom_p_one_sided(15, 20) - 0.0207) < 0.002       # 20 species, 75%: p about 0.02 (C-validation 4.7)


def test_eligibility_rule():
    assert H.eligible(100, 100, "bbs") and not H.eligible(99, 500, "bbs") and H.eligible(500, 500, "fia")


def test_skill_gate_failure_gives_tier3():
    cs = cellset(2, 2)
    res, g, v = H.run_test({"a": cs}, "bbs", cv={"a": dict(tss=0.1, auc=0.5)}, n_boot=20, n_eligible=1)
    assert v["a"]["tier"] == "Tier 3"


def test_report_renders():
    res, g, v = H.run_test(_many(3, 2), "fia", cv={f"sp{i}": dict(tss=0.7, auc=0.9) for i in range(3)}, n_boot=20, n_eligible=3)
    md = H.report("fia", "Test", res, g, v)
    assert "INSUFFICIENT DATA" in md and "| sp0 |" in md and "Tier 1 earned" in md
    obs = {k: dict(r["obs"], n_cells=r["n_cells"]) for k, r in res.items()}
    assert "| sp1 |" in H.observed_table(obs)


def test_permutation_null():
    cs = cellset(0, 4)
    assert H.permutation_p(cs, n=100) < 0.05          # a 4 degree shift is far outside label-swap noise
    z = cellset(0, 0)
    assert H.permutation_p(z, n=50) in (1.0,) or H.permutation_p(z, n=50) > 0.5
