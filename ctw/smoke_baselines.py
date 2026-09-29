"""Smoke check for the CHIRPS and CHELSA extraction (run by .github/workflows/smoke-*.yml after `python -m ctw chirps|chelsa`).
Prints a compact per-place table of what was extracted and checks a few well-known places. Exit code 1 if a check fails.
    python -m ctw.smoke_baselines chirps|chelsa"""
from __future__ import annotations
import sys
import numpy as np
from . import common as C
from .baselines import CHELSA_VARS, load_chirps, seasonal_ppt


def main(kind: str) -> int:
    T = C.targets()
    labels = list(T.label)
    bad = []

    def val(arr, place):
        return arr[labels.index(place)] if place in labels else None

    def check(place, ok, msg):
        if place in labels and not ok:
            bad.append(f"{place}: {msg}")

    if kind == "chirps":
        ch = load_chirps(T)
        if ch is None:
            print("no CHIRPS output")
            return 1
        years, s = ch
        print(f"CHIRPS years {years.min()}-{years.max()}, series {s.shape}")
        print(f"{'place':38s} {'lat':>6s} {'lon':>7s} {'months':>6s} {'annual mm':>9s}  DJF MAM JJA SON of the last year (mm)")
        sp = seasonal_ppt(s, years, [int(years[-1])])[:, 0]
        for k in range(min(len(T), 24)):
            n = int(np.isfinite(s[k]).sum())
            ann = float(np.nanmean(np.nansum(s[k], 1))) if n else float("nan")
            print(f"{T.label[k][:38]:38s} {T.lat[k]:6.1f} {T.lon[k]:7.1f} {n:6d} {ann:9.0f}  " + " ".join(f"{x:6.0f}" for x in sp[k]))
        inband = np.abs(T.lat.values) < 49
        cov = np.isfinite(s).any((1, 2))
        print(f"places with data: {int(cov.sum())} of {len(T)}; inside 49S-49N: {int((cov & inband).sum())} of {int(inband.sum())}")
        ann = np.nansum(s, 2).mean(1)
        a = val(ann, "Singapore, Singapore"); check("Singapore, Singapore", a is not None and 1500 < a < 3500, f"annual {a}")
        a = val(ann, "Sydney, Australia"); check("Sydney, Australia", a is not None and 500 < a < 2000, f"annual {a}")
        a = val(cov, "Reykjavík, Iceland"); check("Reykjavík, Iceland", a is not None and not a, "should be outside CHIRPS coverage")
        if inband.sum() and (cov & inband).sum() < 0.9 * inband.sum():
            bad.append("fewer than 90% of places inside the CHIRPS band have data")
    else:
        d = {cv: C.load(f) for cv in CHELSA_VARS if (f := C.work("chelsa", f"{cv}.npz")).exists()}
        if not d:
            print("no CHELSA output")
            return 1
        months = sorted({int(m) for z in d.values() for m in z["months"]})
        print(f"CHELSA variables {sorted(d)} months {months}")
        head = " ".join(f"{cv}{m:02d}".rjust(9) for cv in d for m in months)
        print(f"{'place':38s} {'lat':>6s} {'lon':>7s} {head}")
        for k in range(min(len(T), 24)):
            print(f"{T.label[k][:38]:38s} {T.lat[k]:6.1f} {T.lon[k]:7.1f} " + " ".join(f"{d[cv]['normal'][k, m - 1]:9.1f}" for cv in d for m in months))
        if "tasmax" in d:
            tx = d["tasmax"]["normal"]
            a = val(tx[:, 0], "Singapore, Singapore"); check("Singapore, Singapore", a is not None and 26 < a < 36, f"Jan tasmax {a}")
            a = val(tx[:, 0], "Reykjavík, Iceland"); check("Reykjavík, Iceland", a is not None and -8 < a < 9, f"Jan tasmax {a}")
            a = val(tx[:, 6], "Sydney, Australia"); check("Sydney, Australia", a is not None and 10 < a < 21, f"Jul tasmax {a}")
        if "pr" in d:
            a = val(d["pr"]["normal"][:, 0], "Singapore, Singapore"); check("Singapore, Singapore", a is not None and 100 < a < 600, f"Jan pr {a}")
        cov = np.isfinite(next(iter(d.values()))["normal"]).any(1)
        print(f"places with data: {int(cov.sum())} of {len(T)}")
        if cov.mean() < 0.9:
            bad.append("fewer than 90% of places have CHELSA data")
    for b in bad:
        print("CHECK FAILED", b)
    print("smoke table:", "FAILED" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
