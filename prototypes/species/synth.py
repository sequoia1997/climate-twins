"""SYNTHETIC species range data for the Spike G delivery experiment and prototype page.
NOTHING HERE IS REAL ECOLOGY. Species are invented; ranges come from a made-up temperature/precipitation niche on a
made-up climate field over the real 0.5 degree land mask of the site (site/data/world.dat), upsampled to 1/24 degree
(~4.6 km at the equator).

Layers per species (all uint8 on the equirectangular grid, rows north to south, columns from -180):
  S0   now suitability, 7 bit (0..127)
  S1   2050 suitability 7 bit | bit7 = reachable under limited dispersal (within `reach_km` of the now range)
  S2   2100 same
  A    model agreement: high nibble = members (of 8) above threshold in 2050, low nibble = 2100
and per scenario a global novel-climate layer N (bit0 = 2050, bit1 = 2100).

Usage: python synth.py WORKDIR    (writes WORKDIR/world.npz, WORKDIR/sp_<id>_<ssp>.npz, stats.json)
"""
from __future__ import annotations
import gzip, json, sys
from pathlib import Path
import numpy as np
from scipy.ndimage import zoom, distance_transform_edt, gaussian_filter

NX, NY = 8640, 4320
SSPS = ["ssp126", "ssp245", "ssp370", "ssp585"]
DT = {  # global-mean warming over land-ish, degrees C vs 1991-2020, invented but of the right size
    "ssp126": (1.3, 1.5), "ssp245": (1.6, 2.6), "ssp370": (1.8, 3.6), "ssp585": (2.2, 4.8)}
REACH_KM = (80.0, 220.0)          # limited dispersal: reach by 2050 / 2100 (assumption, not a species trait)
NMEM = 8
FLOOR = 0.05

# id, common name (synthetic), latin placeholder, group, T0, sT, P0 (mm/yr), sP, accessible-area blob (lon, lat, rx, ry deg), dependencies
SPECIES = [
    dict(id="s01", name="Northern maple", sci="Acer sp. S01", group="Trees", T=8, sT=4.0, P=1100, sP=450, box=(-85, 43, 28, 14), deps=[]),
    dict(id="s02", name="Boreal pine", sci="Pinus sp. S02", group="Trees", T=0, sT=4.5, P=650, sP=350, box=(60, 58, 120, 14), deps=[]),
    dict(id="s03", name="Mediterranean oak", sci="Quercus sp. S03", group="Trees", T=15, sT=3.5, P=650, sP=300, box=(10, 41, 40, 11), deps=[]),
    dict(id="s04", name="Rainforest fig", sci="Ficus sp. S04", group="Trees", T=25, sT=3.4, P=2300, sP=800, box=(30, 0, 150, 22), deps=[]),
    dict(id="s05", name="Winter wheat", sci="Triticum sp. S05", group="Crops", T=11, sT=4.0, P=550, sP=250, box=(40, 45, 150, 14), deps=["s11"]),
    dict(id="s06", name="Paddy rice", sci="Oryza sp. S06", group="Crops", T=24, sT=3.0, P=1700, sP=600, box=(105, 20, 50, 20), deps=[]),
    dict(id="s07", name="Highland coffee", sci="Coffea sp. S07", group="Crops", T=21, sT=3.2, P=1700, sP=900, box=(10, 2, 130, 22), deps=[]),
    dict(id="s08", name="Wood warbler", sci="Setophaga sp. S08", group="Birds", T=10, sT=4.0, P=1000, sP=450, box=(-80, 44, 26, 14), deps=["s01"]),
    dict(id="s09", name="Snow hare", sci="Lepus sp. S09", group="Mammals", T=-3, sT=4.0, P=500, sP=350, box=(40, 63, 150, 12), deps=["s02"]),
    dict(id="s10", name="Desert tortoise", sci="Gopherus sp. S10", group="Reptiles", T=21, sT=3.0, P=250, sP=170, box=(-112, 33, 14, 9), deps=[]),
    dict(id="s11", name="Forest tick", sci="Ixodes sp. S11", group="Pests and vectors", T=11, sT=3.8, P=1000, sP=420, box=(-20, 46, 100, 14), deps=["s09"]),
    dict(id="s12", name="Container mosquito", sci="Aedes sp. S12", group="Pests and vectors", T=24, sT=3.5, P=1500, sP=800, box=(20, 10, 160, 32), deps=[]),
]
PLACES_FROM_SITE = 24


def rng_noise(seed, shape, scales, amps):
    r = np.random.default_rng(seed)
    out = np.zeros(shape, np.float32)
    for (sx, sy), a in zip(scales, amps):
        g = r.standard_normal((sy, sx)).astype(np.float32)
        g = gaussian_filter(g, 0.8, mode="wrap")
        z = zoom(g, (shape[0] / sy, shape[1] / sx), order=1, mode="grid-wrap", grid_mode=True)
        out += a * z[:shape[0], :shape[1]]
    return out


def build_world(site_world_dat: Path, work: Path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ctw.reshard import read
    h, a, _ = read(site_world_dat)
    m = np.unpackbits(a(h["mask"]).view(np.uint8))[:h["nx"] * h["ny"]].reshape(h["ny"], h["nx"]).astype(np.float32)
    big = zoom(m, 12, order=1)[:NY, :NX]
    coast = rng_noise(1, (NY, NX), [(144, 72), (576, 288), (2160, 1080)], [0.18, 0.12, 0.08])
    land = (big + coast) > 0.5
    lat = (90 - (np.arange(NY) + 0.5) * 180 / NY).astype(np.float32)
    land &= (lat[:, None] > -60) & (lat[:, None] < 83)
    L = lat[:, None]
    rough = rng_noise(2, (NY, NX), [(36, 18), (144, 72), (576, 288), (2160, 1080)], [1.0, 0.8, 0.5, 0.25])
    T = 28 - 0.0085 * L ** 2 + 2.2 * rough
    T = T - 4 * np.maximum(rough - 0.8, 0)                           # high ground is colder
    wet = 1900 * np.exp(-(L / 9) ** 2) + 800 * np.exp(-((np.abs(L) - 50) / 14) ** 2) + 120
    P = wet * np.exp(0.35 * rng_noise(3, (NY, NX), [(36, 18), (144, 72), (576, 288)], [1.0, 0.8, 0.5]))
    P = P.astype(np.float32)
    T = T.astype(np.float32)
    np.savez(work / "world.npz", land=land, T=T, P=P, lat=lat)
    return land, T, P, lat


def dT_field(ssp, k, lat):
    base = DT[ssp][k]
    return (base * (1.0 + 0.9 * (np.abs(lat) / 90.0) ** 2))[:, None].astype(np.float32)


def suit(T, P, sp, dT=0.0, pf=1.0):
    t = (T + dT - sp["T"]) / sp["sT"]
    p = (np.log(P * pf) - np.log(sp["P"])) / (sp["sP"] / sp["P"])
    return np.exp(-0.5 * (t * t + p * p))


def blob(sp, lat, shape):
    lon0, lat0, rx, ry = sp["box"]
    lon = (np.arange(shape[1]) + 0.5) * 360 / shape[1] - 180
    dx = np.minimum(np.abs(lon - lon0), 360 - np.abs(lon - lon0)) / rx
    dy = (lat - lat0) / ry
    # a soft accessible area; the ocean-side edge is wobbly through the noise added by the caller
    return np.clip(1.6 - (dx[None, :] ** 2 + dy[:, None] ** 2) ** 0.5, 0, 1) ** 0.5


def make_species(sp, world, work, ssps=SSPS):
    land, T, P, lat = world
    r = np.random.default_rng(int(sp["id"][1:]))
    acc = blob(sp, lat, T.shape) * np.clip(1 + 0.25 * rng_noise(7 + int(sp["id"][1:]), T.shape, [(72, 36), (288, 144)], [1, 0.6]), 0, 1.4)
    acc = np.clip(acc, 0, 1)

    def q(s):                                        # suitability -> 7 bit, floor so most cells are empty
        s = np.where(land, s * acc, 0)
        s = np.where(s < FLOOR, 0, s)
        return np.clip(np.round(s * 127), 0, 127).astype(np.uint8)
    S0 = q(suit(T, P, sp))
    thr = int(0.35 * 127)
    now_bin = S0 >= thr
    out = {"S0": S0}
    # reach (limited dispersal) distances computed on a 1/4 grid, converted to km with the range's mean latitude
    sub = 4
    nb = now_bin[::sub, ::sub] if now_bin.any() else now_bin[::sub, ::sub]
    clat = float(lat[now_bin.any(1)].mean()) if now_bin.any() else 0.0
    km_y = 111.2 * sub / 24.0
    km_x = km_y * max(0.35, np.cos(np.radians(clat)))
    dist = distance_transform_edt(~nb, sampling=(km_y, km_x)) if nb.any() else np.full(nb.shape, 1e9)
    dist_full = np.repeat(np.repeat(dist, sub, 0), sub, 1)[:NY, :NX]
    cs = 3                                           # ensemble at 1/3 res then repeated
    Tc, Pc, accc = T[::cs, ::cs], P[::cs, ::cs], acc[::cs, ::cs]
    landc, latc = land[::cs, ::cs], lat[::cs]
    stats = {}
    for ssp in ssps:
        S = [S0]
        agree = []
        for k in (0, 1):
            dT = dT_field(ssp, k, lat)
            fut = q(suit(T, P * 1.0, sp, dT * 1.0, pf=1.0))
            fut_reach = (dist_full <= REACH_KM[k]).astype(np.uint8) << 7
            S.append((fut | fut_reach).astype(np.uint8))
            cnt = np.zeros(Tc.shape, np.uint8)
            for m in range(NMEM):
                rr = np.random.default_rng(1000 * k + 17 * m + int(sp["id"][1:]))
                f = 0.65 + 0.7 * (m / (NMEM - 1))                    # members run cool to hot
                pf = np.exp(0.18 * rng_noise(50 + m, Tc.shape, [(24, 12), (96, 48)], [1.0, 0.6]) * (1 + k))
                s = np.where(landc, suit(Tc, Pc, sp, dT_field(ssp, k, latc) * f, pf) * accc, 0)
                cnt += (s >= 0.35).astype(np.uint8)
            agree.append(np.repeat(np.repeat(cnt, cs, 0), cs, 1)[:NY, :NX])
        A = ((agree[0] << 4) | agree[1]).astype(np.uint8)
        np.savez_compressed(work / f"sp_{sp['id']}_{ssp}.npz", S1=S[1], S2=S[2], A=A)
    np.savez_compressed(work / f"sp_{sp['id']}_base.npz", S0=S0, thr=thr, reach=np.array(REACH_KM), clat=clat)
    return S0


def novel(world, work):
    land, T, P, lat = world
    """present-day (T,P) joint histogram; future cells in an empty bin are 'novel climate'"""
    tb = np.clip(((T + 25) / 1.0).astype(np.int32), 0, 79)
    pb = np.clip((np.log(P) - 3.5) / 0.15, 0, 59).astype(np.int32)
    H = np.zeros((80, 60), np.int64)
    np.add.at(H, (tb[land], pb[land]), 1)
    ok = H >= 20
    for ssp in SSPS:
        N = np.zeros(T.shape, np.uint8)
        for k in (0, 1):
            tf = np.clip(((T + dT_field(ssp, k, lat) + 25) / 1.0).astype(np.int32), 0, 79)
            nov = ~ok[tf, pb] & land
            N |= (nov.astype(np.uint8) << k)
        np.savez_compressed(work / f"novel_{ssp}.npz", N=N)


def cell_km2(lat):
    return (111.2 * 360 / NX) * (111.2 * 180 / NY) * np.cos(np.radians(lat))[:, None]


if __name__ == "__main__":
    work = Path(sys.argv[1]); work.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    if (work / "world.npz").exists():
        z = np.load(work / "world.npz"); world = (z["land"], z["T"], z["P"], z["lat"])
    else:
        world = build_world(root / "site/data/world.dat", work)
    print("land cells", int(world[0].sum()))
    novel(world, work)
    only = sys.argv[2:]
    for sp in SPECIES:
        if only and sp["id"] not in only:
            continue
        S0 = make_species(sp, world, work)
        print(sp["id"], sp["name"], "now cells", int((S0 >= 44).sum()), "nonzero", int((S0 > 0).sum()), flush=True)
