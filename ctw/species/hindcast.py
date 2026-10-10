"""Species hindcast: metrics, null baselines, thresholds, minimum-species rules, verdicts and the report (workstream W4).

Protocol: docs/spikes/C-validation.md section 4, restated and extended in docs/pilot/W4-hindcast.md. The thresholds below
are PROPOSALS (Spike C), not accepted standards; they live in one dataclass so a reviewer can change them in one place.

Input per species and test is a `CellSet`: the comparable cells (cells that are adequately sampled in BOTH windows), with
observed presence in window 1 and window 2 and the model's score in both windows (the model is fitted on window 1 only, scores in
window 2 use window 2 climate). Everything here is plain numpy and needs no model library, so it is tested on synthetic data.

Two tests, never mixed (Rapacciuolo et al. 2012): static transfer (AUC, TSS, Boyce on window 2) and the change test (do the
modelled differences between windows match the observed differences: centroid vector, edges, area, per-cell change).
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import math
import numpy as np
from scipy import stats

from . import sdm
from .. import common as C

KM_PER_DEG = 111.195


# --------------------------------------------------------------------------- thresholds (proposals)
@dataclass(frozen=True)
class Thresholds:
    """Pass marks from docs/spikes/C-validation.md 4.6 and minimum species from 4.7. PROPOSALS, adjustable by the reviewer."""
    cv_tss: float = 0.4                # spatial-block CV TSS in window 1 (skill gate, per species)
    cv_auc: float = 0.7                # spatial-block CV AUC in window 1 (skill gate, per species)
    transfer_auc_drop: float = 0.1     # window-2 AUC must be within this of the window-1 CV AUC
    boyce: float = 0.5                 # Boyce index on window 2
    direction_frac: float = 0.7        # share of species with a detectable observed shift whose sign agrees
    direction_alpha: float = 0.05      # one-sided binomial test against 0.5
    noise_se: float = 2.0              # an observed shift counts as detectable when larger than this many bootstrap SE
    ratio_lo: float = 0.5              # median modelled / observed shift magnitude must lie in [lo, hi] (lag: not required to be 1)
    ratio_hi: float = 2.0
    area_corr: float = 0.3             # correlation of modelled and observed per-cell change
    beat_null_frac: float = 0.6        # share of species where the model beats the no-change null in TSS on window 2
    min_species: dict = field(default_factory=lambda: {"bbs": 30, "fia": 20, "gbif": 40})
    min_presence: dict = field(default_factory=lambda: {"bbs": 100, "fia": 500, "gbif": 20})   # per window: route-presences, plots, records


TH = Thresholds()


# --------------------------------------------------------------------------- geometry
def range_stats(lat, lon, area, occ) -> dict:
    """Area-weighted centroid and occupied area of the cells in `occ`; poleward and equatorward latitude edges are the 95th / 5th
    weighted percentile of latitude for northern-hemisphere cells (reversed for the south), as in C-validation 4.5."""
    lat, lon, area, occ = map(np.asarray, (lat, lon, area, occ))
    occ = occ.astype(bool)
    if not occ.any():
        return dict(clat=math.nan, clon=math.nan, area=0.0, n=0, edge_hi=math.nan, edge_lo=math.nan)
    cl = sdm.centroid(lat, lon, area, occ)
    w = area[occ]; la = lat[occ]
    o = np.argsort(la); cw = np.cumsum(w[o]) / w.sum()
    q = lambda p: float(la[o][min(np.searchsorted(cw, p), len(o) - 1)])
    return dict(clat=cl[0], clon=cl[1], area=float(w.sum()), n=int(occ.sum()), edge_hi=q(0.95), edge_lo=q(0.05))


def shift_vector(a: dict, b: dict) -> dict:
    """Centroid shift a -> b: distance km, bearing deg (clockwise from north) and north / east components in km."""
    if not (np.isfinite(a["clat"]) and np.isfinite(b["clat"])):
        return dict(km=math.nan, bearing=math.nan, north=math.nan, east=math.nan)
    d = float(C.haversine_km(a["clat"], a["clon"], b["clat"], b["clon"]))
    br = sdm.bearing(a["clat"], a["clon"], b["clat"], b["clon"]) if d > 1e-9 else math.nan
    if d <= 1e-9:
        return dict(km=0.0, bearing=math.nan, north=0.0, east=0.0)
    return dict(km=d, bearing=br, north=d * math.cos(math.radians(br)), east=d * math.sin(math.radians(br)))


def range_change(lat, lon, area, occ1, occ2) -> dict:
    """Change of a range between two occupancy maps over the same cells: centroid shift (km, bearing, components), leading
    (poleward, 95th percentile) and trailing (5th percentile) latitude edge shifts in km (positive = northward), area change as a
    fraction of the window-1 area."""
    s1, s2 = range_stats(lat, lon, area, occ1), range_stats(lat, lon, area, occ2)
    out = shift_vector(s1, s2)
    out.update(edge_hi_km=(s2["edge_hi"] - s1["edge_hi"]) * KM_PER_DEG, edge_lo_km=(s2["edge_lo"] - s1["edge_lo"]) * KM_PER_DEG,
               area1=s1["area"], area2=s2["area"], n1=s1["n"], n2=s2["n"],
               area_change=(s2["area"] - s1["area"]) / s1["area"] if s1["area"] > 0 else math.nan,
               lat_shift_km=(s2["clat"] - s1["clat"]) * KM_PER_DEG if np.isfinite(s1["clat"]) and np.isfinite(s2["clat"]) else math.nan)
    return out


def vec_error(a: dict, b: dict) -> float:
    """Length (km) of the difference between two shift vectors (north / east components)."""
    if not all(np.isfinite([a["north"], a["east"], b["north"], b["east"]])):
        return math.nan
    return float(math.hypot(a["north"] - b["north"], a["east"] - b["east"]))


# --------------------------------------------------------------------------- observed change with bootstrap
@dataclass
class CellSet:
    """Comparable cells of one species in one test. obs1 / obs2 bool, score1 / score2 in [0, 1] (None for observed-only analyses)."""
    lat: np.ndarray
    lon: np.ndarray
    area: np.ndarray
    obs1: np.ndarray
    obs2: np.ndarray
    score1: np.ndarray | None = None
    score2: np.ndarray | None = None
    thr: float | None = None            # presence threshold chosen on window 1 only
    cluster: np.ndarray | None = None   # resampling unit (e.g. route id); default = the cell

    def __post_init__(self):
        for k in ("lat", "lon", "area"):
            setattr(self, k, np.asarray(getattr(self, k), float))
        self.obs1, self.obs2 = np.asarray(self.obs1, bool), np.asarray(self.obs2, bool)

    def take(self, idx):
        f = lambda x: None if x is None else np.asarray(x)[idx]
        return CellSet(self.lat[idx], self.lon[idx], self.area[idx], self.obs1[idx], self.obs2[idx], f(self.score1), f(self.score2), self.thr,
                       f(self.cluster))


def observed_change(cs: CellSet, n_boot: int = 500, seed: int = 0, noise_se: float = TH.noise_se) -> dict:
    """Observed change metrics with bootstrap uncertainty (cells, or clusters, resampled with replacement; the same resample
    is used in both windows). Reports the point estimate, bootstrap SE and 95% interval for centroid shift km, northward
    component, leading and trailing edge shifts, occupancy change; `detectable` = shift km > noise_se x SE of the shift under
    a null that keeps the bootstrap SE as noise level (a shift smaller than 2 SE is treated as noise)."""
    est = range_change(cs.lat, cs.lon, cs.area, cs.obs1, cs.obs2)
    rng = np.random.default_rng(seed)
    n = len(cs.lat)
    keys = ["km", "north", "east", "edge_hi_km", "edge_lo_km", "area_change", "bearing"]
    draws = {k: [] for k in keys}
    if cs.cluster is not None:
        u, inv = np.unique(cs.cluster, return_inverse=True)
        members = [np.flatnonzero(inv == i) for i in range(len(u))]
    for _ in range(n_boot):
        if cs.cluster is None:
            idx = rng.integers(0, n, n)
        else:
            pick = rng.integers(0, len(members), len(members))
            idx = np.concatenate([members[i] for i in pick])
        b = range_change(cs.lat[idx], cs.lon[idx], cs.area[idx], cs.obs1[idx], cs.obs2[idx])
        for k in keys:
            draws[k].append(b[k])
    out = dict(est)
    for k in keys:
        d = np.array(draws[k], float); d = d[np.isfinite(d)]
        out[k + "_se"] = float(d.std(ddof=1)) if len(d) > 2 else math.nan
        out[k + "_lo"], out[k + "_hi"] = (float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))) if len(d) > 2 else (math.nan, math.nan)
    # detectable: the northward (main-axis) component differs from zero by more than noise_se x SE
    se = out["north_se"]
    out["detectable"] = bool(np.isfinite(se) and np.isfinite(out["north"]) and abs(out["north"]) > noise_se * se)
    out["detectable_km"] = bool(np.isfinite(out["km_se"]) and np.isfinite(out["km"]) and out["km"] > noise_se * out["km_se"])
    return out


# --------------------------------------------------------------------------- null baselines
def permutation_p(cs: "CellSet", n: int = 500, seed: int = 0) -> float:
    """Label-swap null for the OBSERVED shift: for every cell, swap its window-1 and window-2 presence with probability 0.5 (no true
    change, same cells and prevalence structure) and recompute the centroid shift. Returns the share of null shifts at least as large
    as the observed one (one-sided). Clusters (e.g. routes) are swapped together."""
    obs = range_change(cs.lat, cs.lon, cs.area, cs.obs1, cs.obs2)["km"]
    if not np.isfinite(obs):
        return math.nan
    rng = np.random.default_rng(seed)
    if cs.cluster is not None:
        u, inv = np.unique(cs.cluster, return_inverse=True)
    cnt = 0
    for _ in range(n):
        flip = rng.random(len(u) if cs.cluster is not None else len(cs.lat)) < 0.5
        f = flip[inv] if cs.cluster is not None else flip
        a, b = np.where(f, cs.obs2, cs.obs1), np.where(f, cs.obs1, cs.obs2)
        k = range_change(cs.lat, cs.lon, cs.area, a, b)["km"]
        cnt += bool(np.isfinite(k) and k >= obs)
    return (cnt + 1) / (n + 1)


def random_shift_errors(obs_km: float, n: int = 2000, seed: int = 0) -> np.ndarray:
    """Vector error (km) of a prediction that has the observed shift magnitude but a random bearing: 2 s |sin(d/2)| with d
    uniform on the circle. Its median is the benchmark a model with the right magnitude but no directional skill reaches."""
    d = np.random.default_rng(seed).uniform(0, 2 * math.pi, n)
    return 2 * abs(obs_km) * np.abs(np.sin(d / 2))


def tss_binary(pred: np.ndarray, truth: np.ndarray, weights: np.ndarray | None = None) -> float:
    """True skill statistic of a binary prediction against binary truth (optionally area weighted)."""
    pred, truth = np.asarray(pred, bool), np.asarray(truth, bool)
    w = np.ones(len(pred)) if weights is None else np.asarray(weights, float)
    P, N = w[truth].sum(), w[~truth].sum()
    if P == 0 or N == 0:
        return math.nan
    return float(w[pred & truth].sum() / P + w[~pred & ~truth].sum() / N - 1)


# --------------------------------------------------------------------------- per species evaluation
def evaluate_species(cs: CellSet, thr: float | None = None, th: Thresholds = TH, obs: dict | None = None, n_boot: int = 300, seed: int = 0,
                     cv: dict | None = None) -> dict:
    """All metrics for one species. cs needs score1, score2 and a window-1 threshold. cv = dict(tss=, auc=) from the
    window-1 spatial-block CV (from the W3 pipeline); without it the skill gate is reported as not assessed."""
    thr = cs.thr if thr is None else thr
    assert cs.score1 is not None and cs.score2 is not None and thr is not None, "scores and a window-1 threshold are required"
    obs = obs or observed_change(cs, n_boot=n_boot, seed=seed, noise_se=th.noise_se)
    p1, p2 = np.asarray(cs.score1) >= thr, np.asarray(cs.score2) >= thr
    mod = range_change(cs.lat, cs.lon, cs.area, p1, p2)
    r = dict(n_cells=len(cs.lat), n_obs1=int(cs.obs1.sum()), n_obs2=int(cs.obs2.sum()), obs=obs, mod=mod)
    # static transfer on window 2
    pos, neg = np.asarray(cs.score2)[cs.obs2], np.asarray(cs.score2)[~cs.obs2]
    r["auc2"] = sdm.auc(pos, neg)
    r["tss2"] = tss_binary(p2, cs.obs2, cs.area)
    r["boyce2"] = sdm.boyce(pos, np.asarray(cs.score2))
    # nulls: (A) the model with window-1 climate (no climate update) ; (B) persistence of the observed window-1 map
    r["tss2_null_model_t1"] = tss_binary(p1, cs.obs2, cs.area)
    r["tss2_null_persist"] = tss_binary(cs.obs1, cs.obs2, cs.area)
    r["beats_null"] = bool(np.isfinite(r["tss2"]) and np.isfinite(r["tss2_null_model_t1"]) and r["tss2"] > r["tss2_null_model_t1"])
    r["beats_persistence"] = bool(np.isfinite(r["tss2"]) and np.isfinite(r["tss2_null_persist"]) and r["tss2"] > r["tss2_null_persist"])
    # change test
    err = vec_error(mod, obs)
    null_err = float(obs["km"]) if np.isfinite(obs["km"]) else math.nan          # no-change null predicts zero shift
    rnd = random_shift_errors(obs["km"], seed=seed) if np.isfinite(obs["km"]) else np.array([])
    r["shift_error_km"], r["shift_error_nochange_km"] = err, null_err
    r["shift_error_random_median_km"] = float(np.median(rnd)) if len(rnd) else math.nan
    r["shift_error_pctile_vs_random"] = float((rnd >= err).mean()) if len(rnd) and np.isfinite(err) else math.nan
    r["beats_nochange_shift"] = bool(np.isfinite(err) and np.isfinite(null_err) and err < null_err)
    r["shift_ratio"] = float(mod["km"] / obs["km"]) if np.isfinite(obs["km"]) and obs["km"] > 0 and np.isfinite(mod["km"]) else math.nan
    r["bearing_error"] = sdm.angle_diff(mod["bearing"], obs["bearing"]) if np.isfinite(mod["bearing"]) and np.isfinite(obs["bearing"]) else math.nan
    r["direction_agree"] = (bool(np.sign(mod["north"]) == np.sign(obs["north"])) if np.isfinite(mod["north"]) and np.isfinite(obs["north"]) and obs["detectable"] else None)
    r["edge_hi_error_km"] = mod["edge_hi_km"] - obs["edge_hi_km"]
    r["edge_lo_error_km"] = mod["edge_lo_km"] - obs["edge_lo_km"]
    r["area_change_error"] = mod["area_change"] - obs["area_change"] if np.isfinite(mod["area_change"]) and np.isfinite(obs["area_change"]) else math.nan
    r["area_sign_agree"] = (bool(np.sign(mod["area_change"]) == np.sign(obs["area_change"])) if np.isfinite(mod["area_change"]) and np.isfinite(obs["area_change"])
                            and obs["area_change"] != 0 else None)
    dobs, dmod = cs.obs2.astype(float) - cs.obs1.astype(float), np.asarray(cs.score2) - np.asarray(cs.score1)
    r["cell_change_corr"] = float(np.corrcoef(dobs, dmod)[0, 1]) if dobs.std() > 0 and dmod.std() > 0 else math.nan
    r["cv"] = cv
    r["cv_gate"] = (None if not cv else bool(cv.get("tss", -1) >= th.cv_tss and cv.get("auc", -1) >= th.cv_auc))
    r["transfer_ok"] = (None if not cv or not np.isfinite(r["auc2"]) else bool(r["auc2"] >= cv["auc"] - th.transfer_auc_drop))
    return r


# --------------------------------------------------------------------------- group level
def binom_p_one_sided(k: int, n: int, p: float = 0.5) -> float:
    return float(stats.binomtest(k, n, p, alternative="greater").pvalue) if n > 0 else math.nan


def eligible(n_pres1: int, n_pres2: int, test: str, th: Thresholds = TH) -> bool:
    """Species counts towards the minimum-species rule only with enough presences (route-presences, plots, records) in BOTH windows."""
    m = th.min_presence[test]
    return n_pres1 >= m and n_pres2 >= m


def group_verdict(results: dict, test: str, th: Thresholds = TH, n_eligible: int | None = None) -> dict:
    """Group-level verdict from per-species `evaluate_species` outputs ({species: result}).
    status: 'insufficient data' when fewer than th.min_species[test] species are eligible (this is not a pass and not a fail),
    otherwise 'pass' or 'fail'. `checks` lists each group check with its value, threshold and outcome."""
    n_el = len(results) if n_eligible is None else n_eligible
    need = th.min_species[test]
    sp = list(results.values())
    dirs = [r["direction_agree"] for r in sp if r["direction_agree"] is not None]
    k = int(sum(dirs)); n = len(dirs)
    ratios = np.array([r["shift_ratio"] for r in sp if r["shift_ratio"] is not None and np.isfinite(r["shift_ratio"])])
    corr = np.array([r["cell_change_corr"] for r in sp if np.isfinite(r["cell_change_corr"])])
    errs = [(r["shift_error_km"], r["shift_error_nochange_km"]) for r in sp if np.isfinite(r["shift_error_km"]) and np.isfinite(r["shift_error_nochange_km"])]
    beats = [r["beats_null"] for r in sp]
    areas = [r["area_sign_agree"] for r in sp if r["area_sign_agree"] is not None]
    p = binom_p_one_sided(k, n)
    checks = [
        dict(name="direction of shift", value=f"{k}/{n} agree" + (f" (p={p:.3f})" if n else ""), need=f">= {th.direction_frac:.0%} and p < {th.direction_alpha}",
             ok=bool(n >= 1 and k / n >= th.direction_frac and p < th.direction_alpha)),
        dict(name="median shift ratio (model / observed)", value=f"{np.median(ratios):.2f}" if len(ratios) else "n/a", need=f"{th.ratio_lo} to {th.ratio_hi}",
             ok=bool(len(ratios) and th.ratio_lo <= np.median(ratios) <= th.ratio_hi)),
        dict(name="shift error below no-change error", value=(f"median {np.median([a for a, _ in errs]):.0f} km vs {np.median([b for _, b in errs]):.0f} km" if errs else "n/a"),
             need="model error < no-change error (median)", ok=bool(errs and np.median([a for a, _ in errs]) < np.median([b for _, b in errs]))),
        dict(name="area change sign and per-cell correlation", value=(f"sign {sum(areas)}/{len(areas)}, median r {np.median(corr):.2f}" if len(areas) and len(corr) else "n/a"),
             need=f"sign majority and r >= {th.area_corr}", ok=bool(len(areas) and len(corr) and sum(areas) / len(areas) > 0.5 and np.median(corr) >= th.area_corr)),
        dict(name="beats no-change null in TSS (window 2)", value=f"{sum(beats)}/{len(beats)}", need=f">= {th.beat_null_frac:.0%} of species",
             ok=bool(beats and sum(beats) / len(beats) >= th.beat_null_frac)),
    ]
    if n_el < need:
        status = "insufficient data"
    else:
        status = "pass" if all(c["ok"] for c in checks) else "fail"
    return dict(test=test, status=status, n_species=len(results), n_eligible=n_el, need=need, checks=checks,
                static_pass=bool(all(r["transfer_ok"] is not False and (r["boyce2"] is None or not np.isfinite(r["boyce2"]) or r["boyce2"] >= th.boyce) for r in sp) if sp else False),
                interpretation=interpretation(status, checks))


def interpretation(status: str, checks: list) -> str:
    """Plain-language outcome following C-validation 4.6 interpretation rules."""
    if status == "insufficient data":
        return "Not a test: too few species. Results are illustrative and do not count towards a pass."
    change_ok = all(c["ok"] for c in checks if c["name"] in ("direction of shift", "shift error below no-change error", "median shift ratio (model / observed)"))
    if status == "pass":
        return "Static transfer and change test both pass: Tier 1 can be earned for species that also pass their own gates."
    if change_ok:
        return "Change test passes but other checks fail: publish current suitability, review the failing checks before projections."
    return "Change test fails: publish current suitability only, hide future projections for this group, or label as suitable climate not expected range."


def species_verdict(res: dict, group: dict, th: Thresholds = TH) -> dict:
    """Tier 1 earned or not for one species. Tier 1 needs (a) a conclusive group test that passed, (b) the species' own skill gate,
    (c) window-2 transfer, (d) beating the no-change null, (e) no detectable wrong-direction shift. Reasons are listed."""
    why = []
    if group["status"] == "insufficient data":
        why.append("group test has insufficient data")
    elif group["status"] == "fail":
        why.append("group change test failed")
    if res["cv_gate"] is None:
        why.append("spatial CV skill not supplied")
    elif not res["cv_gate"]:
        why.append("below skill gate")
    if res["transfer_ok"] is False:
        why.append("AUC lost more than %.1f in window 2" % th.transfer_auc_drop)
    if np.isfinite(res["boyce2"]) and res["boyce2"] < th.boyce:
        why.append("Boyce below %.1f" % th.boyce)
    if not res["beats_null"]:
        why.append("does not beat no-change null")
    if res["direction_agree"] is False:
        why.append("wrong direction of shift")
    tier1 = not why
    fallback = "Tier 1" if tier1 else ("Tier 3" if res["cv_gate"] is False else "Tier 2")
    return dict(tier1=tier1, tier=fallback, reasons=why)


# --------------------------------------------------------------------------- report
def _f(x, nd=2, unit=""):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    return f"{x:.{nd}f}{unit}"


def observed_table(obs_by_species: dict, names: dict | None = None) -> str:
    """Markdown table of observed change per species (no model needed)."""
    lines = ["| species | cells | shift km (95% CI) | bearing | north km (SE) | leading edge km | trailing edge km | occupancy change | detectable |",
             "|---|---|---|---|---|---|---|---|---|"]
    for sp, o in obs_by_species.items():
        lines.append(f"| {(names or {}).get(sp, sp)} | {o.get('n_cells', '')} | {_f(o['km'], 0)} ({_f(o['km_lo'], 0)} to {_f(o['km_hi'], 0)}) | {_f(o['bearing'], 0, ' deg')} | "
                     f"{_f(o['north'], 0)} ({_f(o['north_se'], 0)}) | {_f(o['edge_hi_km'], 0)} | {_f(o['edge_lo_km'], 0)} | {_f(o['area_change'] * 100 if np.isfinite(o['area_change']) else math.nan, 0, '%')} | "
                     f"{'yes' if o['detectable'] else 'no'} |")
    return "\n".join(lines)


def report(test: str, title: str, results: dict, group: dict, verdicts: dict, th: Thresholds = TH, names: dict | None = None) -> str:
    """Markdown report for one test: group verdict, check table, species table, tier verdicts."""
    nm = lambda s: (names or {}).get(s, s)
    out = [f"## {title}", "", f"**Group verdict: {group['status'].upper()}** ({group['n_eligible']} eligible species, minimum {group['need']}). {group['interpretation']}", "",
           "| group check | value | needed | result |", "|---|---|---|---|"]
    out += [f"| {c['name']} | {c['value']} | {c['need']} | {'ok' if c['ok'] else 'not met'} |" for c in group["checks"]]
    out += ["", "| species | AUC w2 | TSS w2 | Boyce w2 | TSS no-change (model, w1 climate) | TSS persistence | obs shift km / bearing | model shift km / bearing | ratio | bearing err | direction | edge err hi / lo km | area change obs / model | cell corr |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sp, r in results.items():
        o, m = r["obs"], r["mod"]
        d = {True: "agree", False: "WRONG", None: "not detectable"}[r["direction_agree"]]
        out.append(f"| {nm(sp)} | {_f(r['auc2'])} | {_f(r['tss2'])} | {_f(r['boyce2'])} | {_f(r['tss2_null_model_t1'])} | {_f(r['tss2_null_persist'])} | "
                   f"{_f(o['km'], 0)} / {_f(o['bearing'], 0)} | {_f(m['km'], 0)} / {_f(m['bearing'], 0)} | {_f(r['shift_ratio'])} | {_f(r['bearing_error'], 0)} | {d} | "
                   f"{_f(r['edge_hi_error_km'], 0)} / {_f(r['edge_lo_error_km'], 0)} | {_f(o['area_change'], 2)} / {_f(m['area_change'], 2)} | {_f(r['cell_change_corr'])} |")
    out += ["", "| species | tier | Tier 1 earned | reasons if not |", "|---|---|---|---|"]
    out += [f"| {nm(sp)} | {v['tier']} | {'yes' if v['tier1'] else 'no'} | {'; '.join(v['reasons']) or '-'} |" for sp, v in verdicts.items()]
    return "\n".join(out)


def run_test(cellsets: dict, test: str, cv: dict | None = None, th: Thresholds = TH, n_eligible: int | None = None, n_boot: int = 300, seed: int = 0):
    """Evaluate every species, then the group and the species verdicts. cellsets: {species: CellSet}, cv: {species: dict(tss, auc)}."""
    results = {sp: evaluate_species(cs, th=th, cv=(cv or {}).get(sp), n_boot=n_boot, seed=seed) for sp, cs in cellsets.items()}
    ne = n_eligible if n_eligible is not None else sum(eligible(r["n_obs1"], r["n_obs2"], test, th) for r in results.values())
    g = group_verdict(results, test, th, n_eligible=ne)
    return results, g, {sp: species_verdict(r, g, th) for sp, r in results.items()}
