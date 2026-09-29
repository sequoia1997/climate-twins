"""Write a synthetic work/results.npz and work/gazetteer.json for the current place lists, so export -> site -> validate
-> tests/test_page.py can be run without downloading any climate data (the numbers are random but shaped exactly like
the real ones; pools are the size of the real ones). Use it in a scratch copy of the repository or with a scratch site:

    CTW_WORK=/tmp/ctw_fixture python tests/make_fixture.py
    CTW_WORK=/tmp/ctw_fixture python -m ctw export && python -m ctw site && python -m ctw validate
    python tests/test_page.py site

It writes site/data/*, so run it in a copy of the repository if site/ holds a real build."""
import gzip, json, os, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw import common as C, features as F                                           # noqa: E402


def main(seed=1):
    rng = np.random.default_rng(seed)
    cfg = C.config()
    T = C.targets()
    NT, NM, NV = len(T), len(C.models(cfg)), C.NV
    P, S, E = len(cfg["periods"]["keys"]), len(cfg["scenarios"]["ids"]), 2
    midx = C.match_idx(cfg); K = len(midx)
    g = cfg["grids"]
    lat, lon = T.lat.values, T.lon.values

    def climate(la, n_extra=0):
        """(n, 16) raw seasonal vectors: warm in the tropics, cold poleward, rain 20-400 mm per season."""
        t = 30 - 0.55 * np.abs(la)[:, None] + rng.normal(0, 1.5, (len(la), 1))
        x = np.zeros((len(la), NV))
        x[:, 0:4] = t + np.array([-6, 0, 6, 0]) * (np.abs(la)[:, None] / 60) + 4
        x[:, 4:8] = x[:, 0:4] - 9
        x[:, 8:12] = rng.uniform(20, 400, (len(la), 4))
        x[:, 12:16] = x[:, 4:8] - 3
        return x

    base = climate(lat)
    scale = (np.arange(P)[:, None] + 1) * (np.arange(S)[None, :] + 1) * 0.5
    fut = (base[:, None, None, None, :] + rng.normal(1.0, 0.5, (NT, P, S, NM, NV)) * scale[None, :, :, None, None]).astype("float32")
    # match pools: as many cells as the real grids
    nna, nw = 97488, 64958
    na_cells = np.sort(rng.choice(g["na_nx"] * g["na_ny"], nna, replace=False))
    na_lat, na_lon = rng.uniform(14, 72, nna), rng.uniform(-168, -55, nna)
    w_cells = np.sort(rng.choice(360 * 720, nw, replace=False))
    w_lat, w_lon = 90 - (w_cells // 720 + .5) * 0.5, -180 + (w_cells % 720 + .5) * 0.5
    kdef = rng.integers(8, 12, NT)
    eye = np.tile(np.eye(K, dtype="float32") * 0.5, (NT, 1, 1))
    best_idx = np.zeros((NT, P, S, E, 2), "int32")
    for k in range(NT):
        best_idx[k] = rng.integers(0, nna if T.g[k] == 0 else nw, (P, S, E, 2))
    best_sig = rng.gamma(2.0, 1.2, (NT, P, S, E, 2)).astype("float32")
    keys = [(k, p, s, e) for k in np.where(T.g.values == 0)[0][::7] for p in range(P) for s in range(S) for e in range(E)]
    nk = len(keys)
    fk = lambda *s: rng.integers(1, 30, s).astype("uint8")                            # noqa: E731
    R = dict(midx=midx, bad=np.zeros(NT, bool), icv_src=np.where(T.domain.values == "conus", "PRISM", "TerraClimate"),
             base=base.astype("float32"), fut=fut, icvsd=rng.uniform(.3, 2, (NT, NV)).astype("float32"), Msh=eye, Mtr=eye.copy(), kdef=kdef,
             best_idx=best_idx, best_sig=best_sig, area2=rng.uniform(0, 1e6, (NT, P, S, E)).astype("float32"),
             selfchk=rng.uniform(0, .1, NT).astype("float32"), tc_check=rng.uniform(0, .5, NT).astype("float32"),
             recent=rng.normal(0, .3, (NT, NV)).astype("float32"), rec_sig=rng.uniform(0, 2, NT).astype("float32"),
             rec_years=np.array([2016, 2025]), floored=np.array([], str), cc_fill=np.array([], str),
             f_now_kg=fk(NT), f_now_zone=fk(NT), f_now_ffp=rng.integers(30, 365, NT).astype("uint16"),
             f_fut_kg=fk(NT, P, S, E), f_fut_zone=fk(NT, P, S, E), f_fut_ffp=rng.integers(30, 365, (NT, P, S, E)).astype("uint16"),
             na_cells=na_cells, na_lat=na_lat, na_lon=na_lon, na_raw=climate(na_lat).astype("float32"),
             na_kg=fk(nna), na_zone=fk(nna), na_ffp=rng.integers(30, 365, nna).astype("uint16"),
             w_cells=w_cells, w_lat=w_lat, w_lon=w_lon, w_raw=climate(w_lat).astype("float32"), w_land=rng.uniform(.25, 1, nw).astype("float32"),
             w_iso=np.array([""] * nw), w_kg=fk(nw), w_zone=fk(nw), w_ffp=rng.integers(30, 365, nw).astype("uint16"),
             glob_keys=np.array(keys, "int32").reshape(-1, 4), glob_s=rng.uniform(2, 6, nk).astype("float32"),
             glob_a=rng.integers(0, 24, nk).astype("int32"), glob_n=np.full(nk, 14, "int32"),
             glob_cells=rng.integers(0, nw, (nk, cfg["matching"]["sites"])).astype("int32"),
             glob_sig=rng.uniform(2, 6, (nk, cfg["matching"]["sites"])).astype("float32"))
    C.save(C.work("results.npz"), **R)
    snap = json.load(gzip.open(C.DATA / "places_snapshot.json.gz", "rt"))
    json.dump({"na": snap["na"], "world": snap["world"], "source": "fixture", "countries": {}}, open(C.work("gazetteer.json"), "w"))
    print(f"fixture: {NT} places ({int((T.g == 0).sum())} North America, {int((T.g == 1).sum())} world) in {C.WORK}")


if __name__ == "__main__":
    main()
