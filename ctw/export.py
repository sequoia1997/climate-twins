"""Pack work/results.npz for the page. Output in site/data/:

  index.json        every place (name, position, population, country, variability source, PC count, group, shard, slot)
                    and the shard table. Small: the page builds the search list and map dots from it immediately.
  overview.dat      every place's best match (sigma, position) for each period/scenario/ensemble/method: the arrows the
                    map shows before a place is picked. About 100 bytes per place.
  na.dat, world.dat "core" files: the two search pools (climate of every candidate cell), grid, place labels for
                    cells, sigma table. Their size does not depend on the number of places.
  p/<group>-NN.dat  shards of per-place data (baseline, projections, metrics, best matches, features, sea level,
                    worldwide matches). About config [export] shard_places places each, grouped by region and
                    ordered along a Z-curve so neighbours share a file. The page fetches a shard when one of its
                    places is picked. The page's place index t is the row in index.json: North America first, then
                    the world, both in data/*.csv order (unusable places dropped), as in earlier releases.
  summary.json      per-place sigma and best-match position (validate.py, the methods page); the page does not load it.

File format (core files and shards), gzip-compressed:
  "CTW2" | uint32 header length | JSON header | binary arrays, 4-byte aligned, referenced in the header as
  {"$b": [offset, nbytes, dtype]}. int16 arrays that compress better split into low/high byte planes are
  marked dtype "i16p". index.html holds no data."""
from __future__ import annotations
import datetime as dt, gzip, json, shutil
import numpy as np
from scipy.spatial import cKDTree
from . import common as C
from . import features as F
from .regions import region as region_of

INDEX_COLS = ["n", "lat", "lon", "pop", "c", "icv", "k", "g", "s", "i"]     # index.json row layout
SHARD_PLACES = 48


class Pack:
    def __init__(self):
        self.blobs, self.off = [], 0

    def add(self, a, dtype=None):
        a = np.ascontiguousarray(a)
        dtype = dtype or {"int16": "i16", "int32": "i32", "float32": "f32", "uint8": "u8", "uint16": "u16"}[a.dtype.name]
        b = a.tobytes()
        ref = {"$b": [self.off, len(b), dtype]}
        b += b"\0" * (-len(b) % 4)
        self.blobs.append(b); self.off += len(b)
        return ref

    def planes(self, a):
        u = np.ascontiguousarray(a, "int16").view(np.uint8).reshape(-1, 2)
        return self.add(np.concatenate([u[:, 0], u[:, 1]]), "i16p")

    def write(self, header, path):
        bad = []

        def clean(x, where):
            if isinstance(x, float) and not np.isfinite(x):
                bad.append(where)
                return None
            if isinstance(x, dict):
                return {k: clean(v, f"{where}.{k}") for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [clean(v, f"{where}[{i}]") for i, v in enumerate(x)]
            return x
        header = clean(header, path.name)
        if bad:
            C.log.warning("%s: %d missing values written as null, e.g. %s", path.name, len(bad), bad[:8])
        h = json.dumps(header, separators=(",", ":"), allow_nan=False).encode()
        h += b" " * (-len(h) % 4)
        raw = b"CTW2" + len(h).to_bytes(4, "little") + h + b"".join(self.blobs)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(raw, 9))
        return len(raw), path.stat().st_size


def labels_for(lat, lon, plist, big_pop=100000):
    """Nearest place and nearest large city for each cell; returns (near, big, places) with compact indices."""
    pl = np.array([[p[1], p[2]] for p in plist]); pop = np.array([p[3] for p in plist])
    xyz = C.unit_xyz(lat, lon)
    _, near = cKDTree(C.unit_xyz(pl[:, 0], pl[:, 1])).query(xyz)
    bi = np.nonzero(pop >= big_pop)[0]
    _, nb = cKDTree(C.unit_xyz(pl[bi, 0], pl[bi, 1])).query(xyz)
    nb = bi[nb]
    used = np.unique(np.r_[near, nb])
    assert len(used) < 65535
    remap = -np.ones(len(plist), int); remap[used] = np.arange(len(used))
    return remap[near].astype("uint16"), remap[nb].astype("uint16"), [plist[i] for i in used]


# --------------------------------------------------------------------------- shards
def zkey(lat, lon, bits=10):
    """Z-order (Morton) key of a position on a 2^bits grid: nearby places get nearby keys."""
    x = min((1 << bits) - 1, max(0, int((lon + 180) / 360 * (1 << bits))))
    y = min((1 << bits) - 1, max(0, int((lat + 90) / 180 * (1 << bits))))
    z = 0
    for i in range(bits):
        z |= ((x >> i) & 1) << (2 * i) | ((y >> i) & 1) << (2 * i + 1)
    return z


def group_of(g, iso, lat):
    """Download group of a place: the country for US/Canada/Mexico, the world region otherwise."""
    if g == 0:
        return {"US": "us", "CA": "ca", "MX": "mx"}.get(iso, "na")
    return region_of(iso, lat).lower().replace(" ", "-")


def plan_shards(rows, size):
    """rows: [(t, g, iso, lat, lon)] in page order. Returns (shards, where): shards = [{"f", "g", "ids"}] with ids the
    page indices of the places in each file (slot order), where[t] = (shard number, slot). Deterministic."""
    groups = {}
    for t, g, iso, lat, lon in rows:
        groups.setdefault((g, group_of(g, iso, lat)), []).append((zkey(lat, lon), t))
    shards, where = [], {}
    for (g, name) in sorted(groups):
        rs = [t for _, t in sorted(groups[(g, name)])]
        n = len(rs)
        m = max(1, -(-n // max(1, size)))                                   # ceil: files as even as possible
        for i in range(m):
            ids = rs[i * n // m:(i + 1) * n // m]
            for slot, t in enumerate(ids):
                where[t] = (len(shards), slot)
            shards.append({"f": f"p/{'na' if g == 0 else 'w'}-{name}-{i:02d}.dat", "g": g, "ids": ids})
    return shards, where


def run(cfg=None):
    cfg = cfg or C.config()
    R = C.load(C.work("results.npz"))
    T = C.targets()
    gz = json.load(open(C.work("gazetteer.json")))
    sl = json.load(open(C.DATA / "sealevel.json")) if (C.DATA / "sealevel.json").exists() else None
    cal = F.calibration()
    ms = C.models(cfg); ens = C.ensembles(cfg); EN = list(ens)
    midx = R["midx"]; K = len(midx)
    bad = R["bad"]
    version = dt.date.today().isoformat()
    size = int(cfg.get("export", {}).get("shard_places", SHARD_PLACES))
    common = dict(
        nv=C.NV, midx=midx.tolist(), K=K, models=[m["name"] for m in ms], tcr=[m["tcr"] if m["tcr"] > 0 else None for m in ms],
        ens={e: ens[e] for e in ("tcr_likely", "all")}, ssps=cfg["scenarios"]["labels"],
        periods=[{"key": k, "label": k, "years": f"{a}–{b}"} for k, (a, b) in zip(cfg["periods"]["keys"], cfg["periods"]["years"])],
        baseline=cfg["baseline"]["years"], data_version=version, method_version=cfg["release"]["method_version"],
        kg=F.KG, kg_name=[F.KG_NAME[c] for c in F.KG], recent_years=R["rec_years"].tolist(), humidity=bool(cfg["matching"]["humidity"]),
        calibration={"hardiness": {k: v for k, v in cal["hardiness"].items() if k != "coef"}, "ffp": {k: v for k, v in cal["ffp"].items() if k != "coef"}},
    )
    # warming-level view (gwl.py): levels, how many models reach each, and the typical year it is reached per scenario
    eord0 = [EN.index("all"), EN.index("tcr_likely")]
    gy = R["gwl_year"]                                             # (levels, models, scenarios)
    when = []
    for e in eord0:
        rows = []
        for gi in range(gy.shape[0]):
            rows.append([int(np.median([gy[gi, mi, s] for mi in ens[EN[e]] if gy[gi, mi, s] > 0])) if sum(gy[gi, mi, s] > 0 for mi in ens[EN[e]]) >= cfg["gwl"]["min_models"] else 0
                         for s in range(gy.shape[2])])
        when.append(rows)
    common["gwl"] = dict(levels=[float(x) for x in R["gwl_levels"]], ref=cfg["gwl"]["reference"], window=20,
                         now=round(float(np.nanmedian(R["gwl_now"])), 2), n=R["gwl_n"][:, eord0].tolist(), ok=R["gwl_ok"][:, eord0].astype(int).tolist(),
                         when=when, reach=R["gwl_reach"].astype(int).tolist(), min_models=int(cfg["gwl"]["min_models"]))
    Dg = np.arange(0, 60.0001, 0.02)
    sig_tab = np.stack([C.chi_to_sigma(Dg, k) for k in range(1, C.NV + 1)]).astype("float32")
    E = len(EN)
    eord = [EN.index("all"), EN.index("tcr_likely")]             # page order (v9 convention): all = 0, tcr_likely = 1
    summary = {"data_version": version, "method_version": cfg["release"]["method_version"], "places": {}}

    # page order: North America (g = 0) then the world (g = 1), unusable places dropped
    na_idx = [int(k) for k in np.where((T.g.values == 0) & ~bad)[0]]
    w_idx = [int(k) for k in np.where((T.g.values == 1) & ~bad)[0]]
    order = na_idx + w_idx
    t_of = {k: t for t, k in enumerate(order)}
    shards, where = plan_shards([(t_of[k], int(T.g[k]), T.country[k], float(T.lat[k]), float(T.lon[k])) for k in order], size)

    def record(k):
        g = int(T.g[k])
        return dict(n=T.label[k] if g else _na_label(T, k), lat=round(float(T.lat[k]), 4), lon=round(float(T.lon[k]), 4),
                    pop=int(T["pop"][k]), c=T.country[k], icv=str(R["icv_src"][k]), k=int(R["kdef"][k]), g=g)

    def sea(k):
        if sl and T.label[k] in sl["places"]:
            r = sl["places"][T.label[k]]
            if all(isinstance(x, (int, float)) and np.isfinite(x) for v in r["v"].values() for a in v.values() for x in a):
                return r
        return None

    # ------------------------------------------------------------ worldwide matches of North American places
    wplaces = gz["world"]
    wpl = np.array([[p[1], p[2]] for p in wplaces])
    wtree = cKDTree(C.unit_xyz(wpl[:, 0], wpl[:, 1]))
    globs = {}                                              # page place index -> {"p|t|s|e": match record}
    for row, key in enumerate(R["glob_keys"]):
        k, p, s, e = (int(x) for x in key)
        if k not in t_of or T.g[k] != 0:
            continue
        sites = []
        for c, sg in zip(R["glob_cells"][row], R["glob_sig"][row]):
            if c < 0:
                continue
            j = int(c)                                          # position in the world pool
            la, lo = float(R["w_lat"][j]), float(R["w_lon"][j])
            _, ti = wtree.query(C.unit_xyz(np.array([la]), np.array([lo])))
            town = wplaces[int(ti[0])]
            sites.append([round(la, 3), round(lo, 3), round(float(sg), 2), town[0].rsplit(", ", 1)[0], town[0].rsplit(", ", 1)[-1],
                          int(round(float(C.haversine_km(la, lo, town[1], town[2])))), np.round(R["w_raw"][j].astype(float), 2).tolist(),
                          int(R["w_kg"][j]), int(R["w_zone"][j]), int(R["w_ffp"][j])])
        t = t_of[k]
        globs.setdefault(t, {})[f"{p}|{t}|{s}|{eord.index(e)}"] = dict(s=round(float(R["glob_s"][row]), 2), a=int(R["glob_a"][row]),
                                                                        n=int(R["glob_n"][row]), sites=sites)

    gglobs = {}                                             # warming-level worldwide matches: page place index -> {"g<level>|t|e": record}
    for row, key in enumerate(R["gglob_keys"]):
        k, gi, e = (int(x) for x in key)
        if k not in t_of or T.g[k] != 0:
            continue
        sites = []
        for c, sg in zip(R["gglob_cells"][row], R["gglob_sig"][row]):
            if c < 0:
                continue
            j = int(c)
            la, lo = float(R["w_lat"][j]), float(R["w_lon"][j])
            _, ti = wtree.query(C.unit_xyz(np.array([la]), np.array([lo])))
            town = wplaces[int(ti[0])]
            sites.append([round(la, 3), round(lo, 3), round(float(sg), 2), town[0].rsplit(", ", 1)[0], town[0].rsplit(", ", 1)[-1],
                          int(round(float(C.haversine_km(la, lo, town[1], town[2])))), np.round(R["w_raw"][j].astype(float), 2).tolist(),
                          int(R["w_kg"][j]), int(R["w_zone"][j]), int(R["w_ffp"][j])])
        t = t_of[k]
        gglobs.setdefault(t, {})[f"g{gi}|{t}|{eord.index(e)}"] = dict(s=round(float(R["gglob_s"][row]), 2), a=int(R["gglob_a"][row]),
                                                                       n=int(R["gglob_n"][row]), sites=sites)

    # ------------------------------------------------------------ shards of per-place data
    out = C.SITE / "data"
    shutil.rmtree(out / "p", ignore_errors=True)               # a shorter place list must not leave stale shards behind
    tot_raw = tot_gz = biggest = 0
    for sh in shards:
        ks = [order[t] for t in sh["ids"]]
        sel = np.array(ks)
        pk = Pack()
        base16 = C.enc(R["base"][sel])
        fut16 = C.enc(R["fut"][sel])
        blk = dict(
            v=version, g=sh["g"], ids=sh["ids"],
            base=pk.add(base16), fut_d=pk.planes(fut16.astype("int32") - base16[:, None, None, None, :]),
            Msh=pk.add(R["Msh"][sel]), Mtr=pk.add(R["Mtr"][sel]), icvsd=pk.add(R["icvsd"][sel].astype("float32")),
            best_idx=pk.add(R["best_idx"][sel][:, :, :, eord].astype("int32")), best_sig=pk.add(R["best_sig"][sel][:, :, :, eord].astype("float32")),
            area2=pk.add(R["area2"][sel][:, :, :, eord].astype("float32")),
            kg_now=pk.add(R["f_now_kg"][sel]), zone_now=pk.add(R["f_now_zone"][sel]), ffp_now=pk.add(R["f_now_ffp"][sel]),
            kg_fut=pk.add(R["f_fut_kg"][sel][:, :, :, eord]), zone_fut=pk.add(R["f_fut_zone"][sel][:, :, :, eord]),
            ffp_fut=pk.add(R["f_fut_ffp"][sel][:, :, :, eord]),
            recent=pk.add(np.round(np.nan_to_num(R["recent"][sel]) * 100).astype("int16")),        # °C x100, log ratio x100
            rec_sig=pk.add(np.nan_to_num(R["rec_sig"][sel]).astype("float32")),
            # warming levels (page toggle "Warming level"): futures as changes from base, per model (n, level, model, measure)
            gfut_d=pk.planes(C.enc(R["gwl_fut"][sel]).astype("int32") - base16[:, None, None, :]),
            gbest_idx=pk.add(R["gwl_best_idx"][sel][:, :, eord].astype("int32")), gbest_sig=pk.add(R["gwl_best_sig"][sel][:, :, eord].astype("float32")),
            garea2=pk.add(R["gwl_area2"][sel][:, :, eord].astype("float32")),
            gkg=pk.add(R["gf_kg"][sel][:, :, eord]), gzone=pk.add(R["gf_zone"][sel][:, :, eord]), gffp=pk.add(R["gf_ffp"][sel][:, :, eord]),
            gglob={key: v for t in sh["ids"] for key, v in gglobs.get(t, {}).items()},
            sl={str(j): sea(k) for j, k in enumerate(ks) if sea(k)},
            glob={key: v for t in sh["ids"] for key, v in globs.get(t, {}).items()},
        )
        raw, gzs = pk.write(blk, out / sh["f"])
        sh["bytes"] = gzs
        tot_raw += raw; tot_gz += gzs; biggest = max(biggest, gzs)
    for k in order:
        g = int(T.g[k])
        summary["places"][T.label[k]] = {
            "g": g, "sig": np.round(R["best_sig"][k][:, :, eord, 0], 3).tolist(),
            "ll": np.round(np.stack([(R["na_lat"] if g == 0 else R["w_lat"])[R["best_idx"][k][:, :, eord, 0]],
                                     (R["na_lon"] if g == 0 else R["w_lon"])[R["best_idx"][k][:, :, eord, 0]]], -1), 3).tolist(),
            "selfchk": round(float(R["selfchk"][k]), 3), "rec_sig": round(float(R["rec_sig"][k]), 3)}
    C.log.info("shards: %d files, %d places, %.1f MB gzip in all, largest %.0f kB", len(shards), len(order), tot_gz / 1e6, biggest / 1e3)

    # ------------------------------------------------------------ overview: every place's best match, for the map before a pick
    # Per place, in the page's best_idx order (period, scenario, ensemble, method): sigma x100 (uint16, 65535 = none) and the
    # match position in degrees x100 (int16 lat, lon). Positions instead of pool cells so the world pool need not be loaded.
    sel = np.array(order)
    bi = R["best_idx"][sel][:, :, :, eord]                                   # (n, P, S, 2, 2)
    bs = R["best_sig"][sel][:, :, :, eord]
    isna = (T.g.values[sel] == 0)[:, None, None, None, None]
    ok = (bi >= 0) & np.isfinite(bs)
    ii = np.maximum(bi, 0)
    la = np.where(isna, R["na_lat"][np.minimum(ii, len(R["na_lat"]) - 1)], R["w_lat"][np.minimum(ii, len(R["w_lat"]) - 1)])
    lo = np.where(isna, R["na_lon"][np.minimum(ii, len(R["na_lon"]) - 1)], R["w_lon"][np.minimum(ii, len(R["w_lon"]) - 1)])
    ov_sig = np.where(ok, np.minimum(np.round(np.nan_to_num(bs) * 100), 65534), 65535).astype("uint16")
    ov_pos = np.stack([np.round(la * 100), np.round(lo * 100)], -1).astype("int16")
    pk = Pack()
    ovh = dict(v=version, n=len(order), sig=pk.add(ov_sig), pos=pk.add(ov_pos))
    # warming-level view: same, per (level, ensemble, method)
    gi_ = R["gwl_best_idx"][sel][:, :, eord]                                 # (n, levels, 2, 2)
    gs_ = R["gwl_best_sig"][sel][:, :, eord]
    gok = (gi_ >= 0) & np.isfinite(gs_)
    gii = np.maximum(gi_, 0)
    isna4 = (T.g.values[sel] == 0)[:, None, None, None]
    gla = np.where(isna4, R["na_lat"][np.minimum(gii, len(R["na_lat"]) - 1)], R["w_lat"][np.minimum(gii, len(R["w_lat"]) - 1)])
    glo = np.where(isna4, R["na_lon"][np.minimum(gii, len(R["na_lon"]) - 1)], R["w_lon"][np.minimum(gii, len(R["w_lon"]) - 1)])
    ovh["gsig"] = pk.add(np.where(gok, np.minimum(np.round(np.nan_to_num(gs_) * 100), 65534), 65535).astype("uint16"))
    ovh["gpos"] = pk.add(np.stack([np.round(gla * 100), np.round(glo * 100)], -1).astype("int16"))
    raw, gzs = pk.write(ovh, out / "overview.dat")
    C.log.info("overview.dat: %d places, %.0f kB gzip", len(order), gzs / 1e3)

    # ------------------------------------------------------------ index: the search list and map dots
    rows = []
    for t, k in enumerate(order):
        r = record(k)
        rows.append([r[c] for c in INDEX_COLS[:8]] + list(where[t]))
    index = dict(v=version, cols=INDEX_COLS, na=len(na_idx), rows=rows, shards=[{"f": s["f"], "g": s["g"], "n": len(s["ids"]), "b": s["bytes"]} for s in shards])
    json.dump(index, open(out / "index.json", "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    C.log.info("index.json: %d places, %.0f kB", len(rows), (out / "index.json").stat().st_size / 1e3)

    # ------------------------------------------------------------ North America core
    g = cfg["grids"]
    pk = Pack()
    near, big, places = labels_for(R["na_lat"], R["na_lon"], gz["na"])
    mask = np.zeros(g["na_ny"] * g["na_nx"], bool); mask[R["na_cells"]] = True
    na = dict(common, nx=g["na_nx"], ny=g["na_ny"], x0=g["na_x0"], y0=g["na_y0"], cell_m=g["na_cell_m"], block_km=g["na_cell_m"] / 1000,
              NP=int(len(R["na_cells"])), mask=pk.add(np.packbits(mask)), pool=pk.planes(C.enc(R["na_raw"]).T.copy()),
              plat=pk.add(R["na_lat"].astype("float32")), plon=pk.add(R["na_lon"].astype("float32")),
              cell_place=pk.add(near), cell_city=pk.add(big), places=places,
              kg=F.KG, kg_pool=pk.add(R["na_kg"]), zone_pool=pk.add(R["na_zone"]), ffp_pool=pk.add(R["na_ffp"]),
              sig_tab=pk.add(sig_tab), sig_dstep=0.02, sig_n=len(Dg), fallback=json.load(open(C.DATA / "fallback.json")),
              nt=len(na_idx), index=1)
    raw, gzs = pk.write(na, out / "na.dat")
    C.log.info("na.dat (core): %d places, %d cells, %.1f MB raw, %.2f MB gzip", len(na_idx), na["NP"], raw / 1e6, gzs / 1e6)

    # ------------------------------------------------------------ world core
    pk = Pack()
    near, big, places = labels_for(R["w_lat"], R["w_lon"], wplaces)
    NGY, NGX = int(round(180 / g["world_res"])), int(round(360 / g["world_res"]))
    mask = np.zeros(NGY * NGX, bool); mask[R["w_cells"]] = True
    w = dict(common, ny=NGY, nx=NGX, res=g["world_res"], NP=int(len(R["w_cells"])), mask=pk.add(np.packbits(mask)),
             pool_p=pk.planes(C.enc(R["w_raw"]).T.copy()), land=pk.add(np.round(R["w_land"] * 255).astype("uint8")),
             cell_place=pk.add(near), cell_city=pk.add(big), places=places,
             kg_pool=pk.add(R["w_kg"]), zone_pool=pk.add(R["w_zone"]), ffp_pool=pk.add(R["w_ffp"]),
             fallback=json.load(open(C.DATA / "fallback_world.json")), nt=len(w_idx), index=1)
    raw, gzs = pk.write(w, out / "world.dat")
    C.log.info("world.dat (core): %d places, %d cells, %.1f MB raw, %.2f MB gzip", len(w_idx), w["NP"], raw / 1e6, gzs / 1e6)

    summary.update(selfchk_median=round(float(np.nanmedian(R["selfchk"])), 3), tc_check_median=round(float(np.nanmedian(R["tc_check"])), 3),
                   unusable=T.label[bad].tolist(), floored=R["floored"].tolist(), cc_fill=R["cc_fill"].tolist(),
                   recent_years=R["rec_years"].tolist(), n_models=len(ms), gwl_now=common["gwl"]["now"], sealevel_places=len(sl["places"]) if sl else 0)
    json.dump(summary, open(out / "summary.json", "w"), separators=(",", ":"))


def _na_label(T, k):
    from .names import label
    return label(T.label[k].split(",")[0], T.country[k], T.admin1[k])
