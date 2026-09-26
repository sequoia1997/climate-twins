"""Pack work/results.npz for the page: site/data/na.dat and site/data/world.dat, plus site/data/summary.json.

File format (both files), gzip-compressed:
  "CTW2" | uint32 header length | JSON header | binary arrays, 4-byte aligned, referenced in the header as
  {"$b": [offset, nbytes, dtype]}. int16 arrays that compress better split into low/high byte planes are
  marked dtype "i16p". Everything the page shows is in these two files; index.html holds no data."""
from __future__ import annotations
import datetime as dt, gzip, json
import numpy as np
from scipy.spatial import cKDTree
from . import common as C
from . import features as F


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
    common = dict(
        nv=C.NV, midx=midx.tolist(), K=K, models=[m["name"] for m in ms], tcr=[m["tcr"] if m["tcr"] > 0 else None for m in ms],
        ens={e: ens[e] for e in ("tcr_likely", "all")}, ssps=cfg["scenarios"]["labels"],
        periods=[{"key": k, "label": k, "years": f"{a}–{b}"} for k, (a, b) in zip(cfg["periods"]["keys"], cfg["periods"]["years"])],
        baseline=cfg["baseline"]["years"], data_version=version, method_version=cfg["release"]["method_version"],
        kg=F.KG, kg_name=[F.KG_NAME[c] for c in F.KG], recent_years=R["rec_years"].tolist(), humidity=bool(cfg["matching"]["humidity"]),
        calibration={"hardiness": {k: v for k, v in cal["hardiness"].items() if k != "coef"}, "ffp": {k: v for k, v in cal["ffp"].items() if k != "coef"}},
    )
    Dg = np.arange(0, 60.0001, 0.02)
    sig_tab = np.stack([C.chi_to_sigma(Dg, k) for k in range(1, C.NV + 1)]).astype("float32")
    E = len(EN)
    eord = [EN.index("all"), EN.index("tcr_likely")]             # page order (v9 convention): all = 0, tcr_likely = 1
    summary = {"data_version": version, "method_version": cfg["release"]["method_version"], "places": {}}

    def target_block(pk, idx, g):
        pk_rows = []
        for k in idx:
            rec = dict(n=T.label[k] if g else _na_label(T, k), lat=round(float(T.lat[k]), 4), lon=round(float(T.lon[k]), 4),
                       pop=int(T["pop"][k]), c=T.country[k], icv=str(R["icv_src"][k]), k=int(R["kdef"][k]), g=g)
            if sl and T.label[k] in sl["places"]:
                r = sl["places"][T.label[k]]
                if all(isinstance(x, (int, float)) and np.isfinite(x) for v in r["v"].values() for a in v.values() for x in a):
                    rec["sl"] = r
            pk_rows.append(rec)
        sel = np.array(idx)
        base16 = C.enc(R["base"][sel])
        fut16 = C.enc(R["fut"][sel])
        blk = dict(
            targets=pk_rows, base=pk.add(base16), fut_d=pk.planes(fut16.astype("int32") - base16[:, None, None, None, :]),
            Msh=pk.add(R["Msh"][sel]), Mtr=pk.add(R["Mtr"][sel]), icvsd=pk.add(R["icvsd"][sel].astype("float32")),
            best_idx=pk.add(R["best_idx"][sel][:, :, :, eord].astype("int32")), best_sig=pk.add(R["best_sig"][sel][:, :, :, eord].astype("float32")),
            area2=pk.add(R["area2"][sel][:, :, :, eord].astype("float32")),
            kg_now=pk.add(R["f_now_kg"][sel]), zone_now=pk.add(R["f_now_zone"][sel]), ffp_now=pk.add(R["f_now_ffp"][sel]),
            kg_fut=pk.add(R["f_fut_kg"][sel][:, :, :, eord]), zone_fut=pk.add(R["f_fut_zone"][sel][:, :, :, eord]),
            ffp_fut=pk.add(R["f_fut_ffp"][sel][:, :, :, eord]),
            recent=pk.add(np.round(np.nan_to_num(R["recent"][sel]) * 100).astype("int16")),        # °C x100, log ratio x100
            rec_sig=pk.add(np.nan_to_num(R["rec_sig"][sel]).astype("float32")),
        )
        for j, k in enumerate(idx):
            summary["places"][T.label[k]] = {
                "g": g, "sig": np.round(R["best_sig"][k][:, :, eord, 0], 3).tolist(),
                "ll": np.round(np.stack([(R["na_lat"] if g == 0 else R["w_lat"])[R["best_idx"][k][:, :, eord, 0]],
                                         (R["na_lon"] if g == 0 else R["w_lon"])[R["best_idx"][k][:, :, eord, 0]]], -1), 3).tolist(),
                "selfchk": round(float(R["selfchk"][k]), 3), "rec_sig": round(float(R["rec_sig"][k]), 3)}
        return blk

    # ------------------------------------------------------------ North America
    g = cfg["grids"]
    pk = Pack()
    na_idx = [k for k in np.where((T.g.values == 0) & ~bad)[0]]
    near, big, places = labels_for(R["na_lat"], R["na_lon"], gz["na"])
    mask = np.zeros(g["na_ny"] * g["na_nx"], bool); mask[R["na_cells"]] = True
    na = dict(common, nx=g["na_nx"], ny=g["na_ny"], x0=g["na_x0"], y0=g["na_y0"], cell_m=g["na_cell_m"], block_km=g["na_cell_m"] / 1000,
              NP=int(len(R["na_cells"])), mask=pk.add(np.packbits(mask)), pool=pk.planes(C.enc(R["na_raw"]).T.copy()),
              plat=pk.add(R["na_lat"].astype("float32")), plon=pk.add(R["na_lon"].astype("float32")),
              cell_place=pk.add(near), cell_city=pk.add(big), places=places,
              kg=F.KG, kg_pool=pk.add(R["na_kg"]), zone_pool=pk.add(R["na_zone"]), ffp_pool=pk.add(R["na_ffp"]),
              sig_tab=pk.add(sig_tab), sig_dstep=0.02, sig_n=len(Dg), fallback=json.load(open(C.DATA / "fallback.json")))
    na.update(target_block(pk, na_idx, 0))
    # worldwide matches for North American places: sites carry their climate and features for the page
    pos = {k: n for n, k in enumerate(na_idx)}
    wplaces = gz["world"]
    wpl = np.array([[p[1], p[2]] for p in wplaces])
    wtree = cKDTree(C.unit_xyz(wpl[:, 0], wpl[:, 1]))
    glob = {}
    for row, key in enumerate(R["glob_keys"]):
        k, p, s, e = (int(x) for x in key)
        if k not in pos:
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
        glob[f"{p}|{pos[k]}|{s}|{eord.index(e)}"] = dict(s=round(float(R["glob_s"][row]), 2), a=int(R["glob_a"][row]), n=int(R["glob_n"][row]), sites=sites)
    na["glob"] = glob
    raw, gzs = pk.write(na, C.SITE / "data" / "na.dat")
    C.log.info("na.dat: %d places, %d cells, %.1f MB raw, %.2f MB gzip", len(na_idx), na["NP"], raw / 1e6, gzs / 1e6)

    # ------------------------------------------------------------ world
    pk = Pack()
    w_idx = [k for k in np.where((T.g.values == 1) & ~bad)[0]]
    near, big, places = labels_for(R["w_lat"], R["w_lon"], wplaces)
    NGY, NGX = int(round(180 / g["world_res"])), int(round(360 / g["world_res"]))
    mask = np.zeros(NGY * NGX, bool); mask[R["w_cells"]] = True
    w = dict(common, ny=NGY, nx=NGX, res=g["world_res"], NP=int(len(R["w_cells"])), mask=pk.add(np.packbits(mask)),
             pool_p=pk.planes(C.enc(R["w_raw"]).T.copy()), land=pk.add(np.round(R["w_land"] * 255).astype("uint8")),
             cell_place=pk.add(near), cell_city=pk.add(big), places=places,
             kg_pool=pk.add(R["w_kg"]), zone_pool=pk.add(R["w_zone"]), ffp_pool=pk.add(R["w_ffp"]),
             fallback=json.load(open(C.DATA / "fallback_world.json")))
    w.update(target_block(pk, w_idx, 1))
    raw, gzs = pk.write(w, C.SITE / "data" / "world.dat")
    C.log.info("world.dat: %d places, %d cells, %.1f MB raw, %.2f MB gzip", len(w_idx), w["NP"], raw / 1e6, gzs / 1e6)

    summary.update(selfchk_median=round(float(np.nanmedian(R["selfchk"])), 3), tc_check_median=round(float(np.nanmedian(R["tc_check"])), 3),
                   unusable=T.label[bad].tolist(), floored=R["floored"].tolist(), cc_fill=R["cc_fill"].tolist(),
                   recent_years=R["rec_years"].tolist(), n_models=len(ms), sealevel_places=len(sl["places"]) if sl else 0)
    json.dump(summary, open(C.SITE / "data" / "summary.json", "w"), separators=(",", ":"))


def _na_label(T, k):
    from .names import label
    return label(T.label[k].split(",")[0], T.country[k], T.admin1[k])
