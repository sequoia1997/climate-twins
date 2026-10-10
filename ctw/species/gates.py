"""Quality gates and tier assignment for the species pilot (W3), from docs/spikes/F-sdm-engine.md section 6.

Tiers (owner decision after W4's BBS hindcast; the future map is always "projected climate suitability", never an expected range):
  Tier A  static skill validated against an independent survey (external evidence with kind in GateConfig.tierA_kinds, passed; birds: BBS)
  Tier B  spatial-block cross-validation skill only (all hard gates pass)
  Tier C  below a hard gate: not shown. The reasons are recorded; nothing is silently dropped.
Range-shift prediction is recorded separately as `range_shifts_tested`: 'pass' | 'fail' | 'untested' (W4: birds fail, direction at chance),
from an external `range_shift_test` record. It never changes the tier; the site must not present shifts as predictions where it is 'fail'.
CV kind: presence-vs-background blocked CV is not a usable gate for survey-trained fits (W4), so when true absences are supplied the CV is
presence-absence blocked CV; otherwise background CV. The summary says which (`skill.cv_kind`).
`confidence` is separate: 'low' marks lower discrimination (CV AUC < 0.7), few records, a narrow range with fewer than 500 records, or
a check-model disagreement. A low-confidence species stays Tier A or B and is shown with the warning (F: AUC 0.7 also rejects about
40% of good broad-niche species, so it demotes confidence rather than removing the species).

Hard gates (any failure -> Tier C): fewer than `min_records` thinned records (counted per 0.125 degree cell, about F's 15 km cell);
CV AUC below `auc_floor` (0.5: no better than chance; F showed AUC 0.6-0.7 for good broad-niche ranges, so 0.5 to 0.7 is low confidence, not rejection); no range check recorded; range check failed. Novelty is handled per scenario/period: when more than
`novel_max` of the area is flagged novel climate the shift and area-change numbers are withheld for that scenario (the map and the
flag are still produced).

All numeric thresholds except the three F recommended (100 records, AUC 0.7, 15% novel) are first values: auc_floor (chance level), the
range-check limits, the narrow-range area and the check-model limit. They are recorded in every summary so they can be changed and rerun.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np

from .grid import GridSpec, within_km


@dataclass(frozen=True)
class GateConfig:
    min_records: int = 100               # F: at least 100 thinned records to publish
    low_conf_records: int = 300          # F: below 300 -> low confidence
    narrow_records: int = 500            # F: narrow-range species need about 500
    narrow_area_km2: float = 67500.0     # F: fewer than ~300 cells of 15 km (225 km2 each)
    auc_ok: float = 0.7                  # F: CV AUC (target-group background) >= 0.7 for standard confidence
    auc_floor: float = 0.5               # below this (no better than chance) the species is Tier C; between 0.5 and 0.7 it is kept as low confidence
    novel_max: float = 0.15              # F: withhold shift numbers above 15% novel area
    omission_max: float = 0.40           # UNCALIBRATED: share of the expert / native range the model calls unsuitable
    commission_max: float = 0.30         # UNCALIBRATED: share of the predicted range outside the expert / native range
    unrecorded_km: float = 500.0         # predicted-suitable area farther than this from any record is reported (warning only)
    unrecorded_warn: float = 0.5
    gam_disagree_pp: float = 25.0        # UNCALIBRATED: |area change main - check| above this percentage points -> low confidence
    tierA_kinds: tuple = ("bbs", "fia")  # kinds of independent-survey evidence that count as validated static skill


def area(mask: np.ndarray, spec: GridSpec) -> float:
    return float((mask.sum(1).astype(np.float64) * spec.row_area_km2()).sum())


def range_check(now: np.ndarray, spec: GridSpec, rec_rc: np.ndarray, expert: np.ndarray = None, kind: str = "native_range",
                cfg: GateConfig = GateConfig()) -> dict:
    """Mandatory check against an expert / native range (bool global grid, may be coarser). Always also reports `unrecorded_share`,
    the share of the present predicted area farther than cfg.unrecorded_km from any record (F: non-climatic limits are the blind spot).
    status: 'pass' | 'fail' | 'missing' (no expert range supplied)."""
    out = dict(kind=kind if expert is not None else "none", status="missing")
    a_now = area(now, spec)
    if len(rec_rc) and a_now > 0:
        rec = np.zeros((spec.H, spec.W), bool)
        rec[rec_rc[:, 0], rec_rc[:, 1]] = True
        near = within_km(rec, spec, cfg.unrecorded_km)
        out["unrecorded_share"] = round(area(now & ~near, spec) / a_now, 4)
    else:
        out["unrecorded_share"] = None
    if expert is None:
        return out
    from .grid import resample
    ex = expert if expert.shape == (spec.H, spec.W) else resample(expert.astype(np.uint8), spec).astype(bool)
    a_ex = area(ex, spec)
    out["omission"] = round(area(ex & ~now, spec) / a_ex, 4) if a_ex else None
    out["commission"] = round(area(now & ~ex, spec) / a_now, 4) if a_now else None
    out["expert_area_km2"] = a_ex
    if out["omission"] is None or out["commission"] is None:
        out["status"] = "fail"
    else:
        # A native-range mask (continent or botanical-country polygons) is far larger than the area a species occupies, so omission against it is
        # reported but only gates when the reference is a true expert / atlas range (found on real data: sugar maple vs North America, omission 0.85).
        om_ok = out["omission"] <= cfg.omission_max or kind == "native_range"
        out["status"] = "pass" if (om_ok and out["commission"] <= cfg.commission_max) else "fail"
        out["omission_gates"] = kind != "native_range"
    out["limits"] = dict(omission_max=cfg.omission_max, commission_max=cfg.commission_max, uncalibrated=True)
    return out


def evaluate(*, n_gate: int, n_used: int, cv_auc: float, area_now: float, novel_shares: dict, check_change: dict, main_change: dict,
             rng_check: dict, validation: dict = None, range_shift_test: dict = None, cv_kind: str = "presence_background", cfg: GateConfig = GateConfig()) -> dict:
    """Apply the gates. novel_shares: {'ssp|period': share of the (present or unlimited-future) area flagged novel};
    check_change / main_change: {'ssp|period': percent area change under the GAM check / the main model}.
    validation: None or {'kind': 'bbs'|'fia'|..., 'passed': bool, ...}: static skill against an independent survey (W4).
    range_shift_test: None or {'status': 'pass'|'fail'} or {'passed': bool}: W4's change test; recorded, never changes the tier."""
    hard, soft = [], []
    g = {}
    # 1 records
    narrow = area_now < cfg.narrow_area_km2
    g["records"] = dict(value=n_gate, used=n_used, threshold=cfg.min_records, passed=n_gate >= cfg.min_records, narrow_range=bool(narrow),
                        narrow_threshold=cfg.narrow_records)
    if n_gate < cfg.min_records:
        hard.append(f"fewer than {cfg.min_records} thinned records ({n_gate})")
    elif n_gate < cfg.low_conf_records:
        soft.append(f"only {n_gate} thinned records (< {cfg.low_conf_records}): range-shift numbers uncertain")
    if narrow and n_gate < cfg.narrow_records and n_gate >= cfg.min_records:
        soft.append(f"narrow range ({area_now:,.0f} km2) with {n_gate} records (< {cfg.narrow_records})")
    # 2 skill
    auc = cv_auc
    g["skill"] = dict(cv_auc=None if auc is None or not np.isfinite(auc) else round(float(auc), 4), threshold=cfg.auc_ok, floor=cfg.auc_floor,
                      passed=bool(np.isfinite(auc) and auc >= cfg.auc_ok))
    if not (auc is not None and np.isfinite(auc)):
        hard.append("cross-validation could not be computed")
    elif auc < cfg.auc_floor:
        hard.append(f"CV AUC {auc:.2f} below the floor {cfg.auc_floor}")
    elif auc < cfg.auc_ok:
        soft.append(f"lower discrimination: CV AUC {auc:.2f} < {cfg.auc_ok}")
    # 3 novelty (per scenario / period, withholds numbers, does not change the tier)
    withheld = {k: bool(v > cfg.novel_max) for k, v in novel_shares.items()}
    g["novelty"] = dict(threshold=cfg.novel_max, shares={k: round(float(v), 4) for k, v in novel_shares.items()}, withheld=withheld)
    # 4 range check
    g["range_check"] = rng_check
    st = rng_check.get("status")
    if st == "missing":
        hard.append("no expert-range or hindcast check recorded (mandatory)")
    elif st == "fail":
        hard.append(f"range check failed (omission {rng_check.get('omission')}, commission {rng_check.get('commission')})")
    if rng_check.get("unrecorded_share") is not None and rng_check["unrecorded_share"] > cfg.unrecorded_warn:
        soft.append(f"{rng_check['unrecorded_share']:.0%} of the predicted area is more than {cfg.unrecorded_km:.0f} km from any record")
    # 5 transparent check model
    diffs = {k: abs(main_change[k] - check_change[k]) for k in check_change if k in main_change
             and np.isfinite(main_change[k]) and np.isfinite(check_change[k])}
    worst = max(diffs.values()) if diffs else None
    g["check_model"] = dict(area_change_gap_pp=None if worst is None else round(float(worst), 1), limit_pp=cfg.gam_disagree_pp,
                            passed=(worst is None or worst <= cfg.gam_disagree_pp), uncalibrated=True)
    if worst is not None and worst > cfg.gam_disagree_pp:
        soft.append(f"transparent check model disagrees on area change by up to {worst:.0f} points")
    # tier
    v = validation or {}
    ev_ok = bool(v.get("passed")) and v.get("kind") in cfg.tierA_kinds
    g["validation"] = dict(evidence=v or None, tierA_kinds=list(cfg.tierA_kinds), counts_as_tierA=ev_ok)
    rs = range_shift_test or {}
    rs_status = rs.get("status") or ({True: "pass", False: "fail"}.get(rs.get("passed")) if "passed" in rs else "untested")
    g["range_shifts"] = dict(status=rs_status, evidence=range_shift_test or None)
    g["cv_kind"] = cv_kind
    tier = "C" if hard else ("A" if ev_ok else "B")
    return dict(gates=g, tier=tier, confidence="low" if (soft and tier != "C") else "standard", published=tier != "C", hard_failures=hard,
                soft_flags=soft, withheld=withheld, config=asdict(cfg), range_shifts_tested=rs_status, cv_kind=cv_kind,
                wording="projected climate suitability (a model of climate suitability, not a forecast or an expected range)")
