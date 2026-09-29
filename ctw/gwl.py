"""Global warming levels (GWL): when does a model's global mean surface air temperature reach +1.5, +2, +3, +4 degC?

Convention (IPCC AR6 WGI Chapter 4 and the Interactive Atlas): warming is measured against the 1850-1900 mean of the
same model's global annual mean tas, and a level is "reached" in the first year whose 20-year running mean
(the 10 years before and the 9 years after it, so the window is centred on the crossing year) is at or above it.
The regional change at that level is the model's own change over that 20-year window. Pure numpy, no data access,
so the logic can be unit-tested with synthetic series."""
from __future__ import annotations
import numpy as np

BEFORE, AFTER = 10, 9                     # window = [year - 10, year + 9]: 20 years


def running_mean(tas, n: int = BEFORE + AFTER + 1):
    """Centred n-year running mean of an annual series. Entry i is the mean of tas[i-BEFORE : i+AFTER+1];
    NaN where the window is incomplete or holds a missing year."""
    a = np.asarray(tas, "float64")
    out = np.full(len(a), np.nan)
    if len(a) < n:
        return out
    c = np.concatenate([[0.0], np.cumsum(np.where(np.isfinite(a), a, 0.0))])
    k = np.concatenate([[0], np.cumsum(np.isfinite(a))])
    for i in range(BEFORE, len(a) - AFTER):
        lo, hi = i - BEFORE, i + AFTER + 1
        if k[hi] - k[lo] == n:
            out[i] = (c[hi] - c[lo]) / n
    return out


def reference(years, tas, ref=(1850, 1900)) -> float:
    """Mean of the annual series over the reference years (NaN unless every year is present)."""
    y = np.asarray(years); a = np.asarray(tas, "float64")
    sel = (y >= ref[0]) & (y <= ref[1])
    if sel.sum() < ref[1] - ref[0] + 1 or not np.isfinite(a[sel]).all():
        return float("nan")
    return float(a[sel].mean())


def crossing_years(years, tas, levels, ref=(1850, 1900)) -> np.ndarray:
    """First centre year at which the 20-year running mean is >= reference + level, for each level; 0 when never.
    `years` must be consecutive. The window [y-10, y+9] always lies inside the series."""
    y = np.asarray(years)
    r0 = reference(y, tas, ref)
    out = np.zeros(len(levels), int)
    if not np.isfinite(r0):
        return out
    rm = running_mean(tas) - r0
    for i, L in enumerate(levels):
        hit = np.nonzero(np.nan_to_num(rm, nan=-np.inf) >= L)[0]
        if len(hit):
            out[i] = int(y[hit[0]])
    return out


def window(year: int) -> tuple[int, int]:
    """Inclusive 20-year window centred on the crossing year."""
    return int(year) - BEFORE, int(year) + AFTER


def pool_deltas(deltas):
    """Pool per-scenario changes for one model and one level. deltas: (n_scenarios, ...) with NaN for scenarios
    that do not reach the level. Each scenario that reaches it counts equally; NaN if none does."""
    d = np.asarray(deltas, "float64")
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        return np.nanmean(d, axis=0)
