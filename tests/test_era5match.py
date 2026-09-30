"""Unit tests for the matched-resolution ERA5 check (ctw/era5.py: land cells, TerraClimate boxes, footprint, matched())
on synthetic arrays. Run: pytest tests/test_era5match.py"""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw import common as C, era5 as ERA5  # noqa: E402

RNG = np.random.default_rng(11)
MIDX = np.r_[np.arange(12), [12, 14]]
MON = ("tmax", "tmin", "ppt", "vap")


def cell_centre(i, j):
    return 90.0 - 0.25 * i, 0.25 * j


def empty_lsm():
    return np.zeros((ERA5.NLAT, ERA5.NLON), "float32")


# ------------------------------------------------------------------------------------------ land cells
def test_land_cell_prefers_own_cell_then_nearest_land():
    lsm = empty_lsm()
    lsm[300, 400] = 1.0                                   # a land cell
    lsm[300, 401] = 0.6
    la, lo = cell_centre(300, 400)
    i, j, d = ERA5.land_cell([la, la + 0.01, la], [lo, lo + 0.26, lo + 0.13], lsm)
    assert (i[0], j[0]) == (300, 400) and d[0] < 1
    assert (i[1], j[1]) == (300, 401)                     # nearest land centre, not the containing sea cell
    assert i[2] == 300 and j[2] in (400, 401)


def test_land_cell_threshold_and_distance():
    lsm = empty_lsm()
    lsm[300, 400] = 0.4                                   # below land_frac_min
    lsm[300, 404] = 1.0                                   # one degree east
    la, lo = cell_centre(300, 400)
    i, j, d = ERA5.land_cell([la], [lo], lsm, 0.5, 50.0)
    assert i[0] == -1 and j[0] == -1 and np.isnan(d[0])  # 1 degree at 15N is > 50 km: no land cell
    i, j, d = ERA5.land_cell([la], [lo], lsm, 0.5, 150.0)
    assert (i[0], j[0]) == (300, 404) and 90 < d[0] < 120
    i, j, d = ERA5.land_cell([la], [lo], lsm, 0.3, 50.0)
    assert (i[0], j[0]) == (300, 400)


def test_land_cell_wraps_the_date_line():
    lsm = empty_lsm()
    lsm[400, 0] = 1.0                                     # longitude 0
    lsm[410, 1439] = 1.0                                  # longitude 359.75
    i, j, _ = ERA5.land_cell([90 - 0.25 * 400, 90 - 0.25 * 410], [-0.05, 0.05], lsm)
    assert (i[0], j[0]) == (400, 0) and (i[1], j[1]) == (410, 1439)


def test_cells_within_is_complete_at_high_latitude():
    la, lo = 69.65, 18.95
    ii, jj, d = ERA5.cells_within([la], [lo], 50.0)[0]
    # brute force over a generous window
    I, J = np.mgrid[70:90, 0:1440]
    D = C.haversine_km(la, lo, 90 - 0.25 * I, 0.25 * J)
    want = set(zip(I[D <= 50].tolist(), J[D <= 50].tolist()))
    assert set(zip(ii.tolist(), jj.tolist())) == want


def test_candidate_cells_cover_every_land_cell():
    lat = RNG.uniform(-60, 75, 40); lon = RNG.uniform(-180, 180, 40)
    lsm = (RNG.random((ERA5.NLAT, ERA5.NLON)) > 0.97).astype("float32")
    i, j, _ = ERA5.land_cell(lat, lon, lsm, 0.5, 50.0)
    cand = ERA5.candidate_cells(lat, lon, 50.0)
    got = i >= 0
    assert got.sum() > 10
    assert np.isin(i[got].astype(np.int64) * ERA5.NLON + j[got], cand).all()
    assert (np.diff(cand) > 0).all()


# ------------------------------------------------------------------------------------------ TerraClimate boxes
def test_box_pixels_are_exactly_the_cell_footprint():
    tc_lat = 90 - (np.arange(4320) + 0.5) / 24
    tc_lon = -180 + (np.arange(8640) + 0.5) / 24
    for i, j in ((300, 0), (300, 719), (300, 720), (361, 1439), (100, 5)):
        R, Cc = ERA5.box_pixels([i * ERA5.NLON + j])
        assert R.shape == (1, 36)
        la, lo = cell_centre(i, j)
        assert np.all(np.abs(tc_lat[R[0]] - la) < 0.125)
        dlon = (tc_lon[Cc[0]] - lo + 180) % 360 - 180
        assert np.all(np.abs(dlon) < 0.125)
        assert len(set(zip(R[0].tolist(), Cc[0].tolist()))) == 36


def test_box_means_land_only():
    a = np.full((20, 30), np.nan)
    a[0:6, 0:6] = 2.0
    a[0:3, 0:6] = np.nan                                  # half the box is sea
    a[0, 0] = np.nan
    R = np.repeat(np.arange(6), 6)[None]
    Cc = np.tile(np.arange(6), 6)[None]
    m, n = ERA5.box_means(a, R, Cc)
    assert m[0] == 2.0 and n[0] == 18
    m, n = ERA5.box_means(np.full((20, 30), np.nan), R, Cc)
    assert np.isnan(m[0]) and n[0] == 0


# ------------------------------------------------------------------------------------------ footprint and matched()
def make_mon(n):
    tx = RNG.uniform(5, 30, (n, 1)) + 5 * np.sin(np.arange(12) / 12 * 2 * np.pi)[None]
    return {"tmax": tx, "tmin": tx - 9, "ppt": RNG.uniform(10, 200, (n, 12)), "vap": np.full((n, 12), 1.2)}


def vec(mon):
    return C.seasonalize({v: m.T for v, m in mon.items()}).T


def test_footprint_world_place_is_the_box_and_shifts_are_applied():
    C.use_extras([])
    p, b = vec(make_mon(5)), vec(make_mon(5))
    assert np.allclose(ERA5.footprint(p, p, b), b)
    base = p.copy(); base[:, 0:8] += 1.0; base[:, 8:12] *= 1.5          # AdaptWest-like: differs from the TerraClimate point
    fp = ERA5.footprint(base, p, b)
    assert np.allclose(fp[:, 0:8], base[:, 0:8] + b[:, 0:8] - p[:, 0:8])
    assert np.allclose((fp[:, 8:12] + 1), (base[:, 8:12] + 1) * (b[:, 8:12] + 1) / (p[:, 8:12] + 1))
    assert np.allclose(fp[:, 12:], base[:, 12:] + b[:, 12:] - p[:, 12:])


def fake_inputs(n, years=np.arange(1990, 2021)):
    """ERA5 (d) and TerraClimate (tc) dicts for n places: TerraClimate box = ERA5 cell + a common offset (+ small noise);
    the 10 km point is very different (an island whose point climate is not the cell's). Place 0 has no land cell."""
    ny = len(years)
    cellm = make_mon(n)
    d, tc = {}, {}
    ci = np.arange(n) + 200; cj = np.arange(n) * 3 + 10
    ci[0] = cj[0] = -1
    flat = (ci.astype(np.int64) * ERA5.NLON + cj)[1:]
    order = np.argsort(flat)
    for v in MON:
        c = np.repeat(cellm[v][:, None, :], ny, 1)
        c[0] = np.nan
        d[v] = {"years": years, "series": np.repeat(cellm[v][:, None, :] * 0.5, ny, 1), "cell": c,
                "cell_i": ci, "cell_j": cj}
        off = {"tmax": 0.6, "tmin": -1.2, "ppt": 0.0, "vap": 0.0}[v]
        box = cellm[v][1:] + off + RNG.normal(0, 0.05, (n - 1, 12))
        if v == "ppt":
            box = cellm[v][1:] * 0.9
        tc[v] = {"box_cells": flat[order], "box_normals": box[order].T}
    return d, tc


def test_matched_uses_cell_and_footprint():
    C.use_extras([])
    n = 30
    d, tc = fake_inputs(n)
    point = vec(make_mon(n))                             # unrelated point climate
    ref, era, nocell, mode = ERA5.matched(d, tc, point, point, 1991, 2020, MON, "cell")
    assert mode == "cell" and nocell[0] and not nocell[1:].any()
    assert np.isnan(ref[0]).all() and np.isnan(era[0]).all()
    # the box mean is recovered from the lookup (sorted cells): ref equals the TerraClimate box vector
    box = {v: np.asarray(tc[v]["box_normals"]).T for v in MON}
    flat = (d["tmax"]["cell_i"].astype(np.int64) * ERA5.NLON + d["tmax"]["cell_j"])[1:]
    pos = np.searchsorted(tc["tmax"]["box_cells"], flat)
    assert np.allclose(ref[1:], vec({v: box[v][pos] for v in MON}))
    # agreement: matched comparison is small, the point comparison large
    SH = []
    for k in range(n):
        t = C.transform(point[k])[MIDX]
        sd = np.r_[np.full(8, 0.8), np.full(4, 0.25), np.full(2, 0.7)]
        SH.append(C.ShrinkSigmaModel(t + RNG.normal(0, 1, (30, len(MIDX))) * sd))
    G = np.ones(n, int)
    ok = np.isfinite(ref[:, MIDX]).all(1)
    off = ERA5.offsets(ref[ok], era[ok], G[ok])
    sig = np.array([ERA5.agreement(SH[k], MIDX, ref[k], era[k], off[1]) for k in np.where(ok)[0]])
    offp = ERA5.offsets(point[ok], era[ok], G[ok])
    sigp = np.array([ERA5.agreement(SH[k], MIDX, point[k], era[k], offp[1]) for k in np.where(ok)[0]])
    assert np.median(sig) < 0.8 and np.median(sigp) > 2 * np.median(sig)


def test_matched_falls_back_to_point_without_cell_output():
    C.use_extras([])
    n = 6
    d, tc = fake_inputs(n)
    point = vec(make_mon(n))
    for v in MON:
        del tc[v]["box_cells"]
    ref, era, nocell, mode = ERA5.matched(d, tc, point, point, 1991, 2020, MON, "cell")
    assert mode == "point" and not nocell.any() and np.allclose(ref, point)
    ref, era, nocell, mode = ERA5.matched(d, tc, point, point, 1991, 2020, MON, "point")
    assert mode == "point"


def test_untransform_inverts_transform():
    C.use_extras([])
    x = vec(make_mon(4))
    assert np.allclose(ERA5.untransform(C.transform(x)), x)
