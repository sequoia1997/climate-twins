"""One-off migration: convert an existing site/data/na.dat + world.dat (one file per region, every place inside,
"CTW2" format as built before sharding) into the sharded layout written by export.py (index.json, overview.dat,
core na.dat / world.dat, p/*.dat). No pipeline inputs are needed, so it works on any checkout that has the old files:

    python -m ctw.reshard              # rewrites site/data in place

The numbers are copied, not recomputed. (Data with warming levels: rebuild with export instead.) Run it once when the page that loads shards is deployed on top of data built
before sharding; every later "Rebuild data" writes the new layout directly. It refuses to run on already sharded data."""
from __future__ import annotations
import gzip, json, shutil
import numpy as np
from . import common as C
from .export import INDEX_COLS, SHARD_PLACES, Pack, plan_shards

DT = {"i16": "int16", "i32": "int32", "f32": "float32", "u8": "uint8", "u16": "uint16", "i16p": "int16"}
PER_PLACE = ("base", "fut_d", "Msh", "Mtr", "icvsd", "best_idx", "best_sig", "area2", "kg_now", "zone_now", "ffp_now",
             "kg_fut", "zone_fut", "ffp_fut", "recent", "rec_sig")


def read(path):
    raw = gzip.decompress(path.read_bytes())
    assert raw[:4] == b"CTW2"
    n = int.from_bytes(raw[4:8], "little")
    h = json.loads(raw[8:8 + n])
    bin0 = 8 + n

    def arr(ref):
        off, ln, dt = ref["$b"]
        u = np.frombuffer(raw[bin0 + off:bin0 + off + ln], np.uint8)
        if dt == "i16p":                                        # low bytes then high bytes
            h2 = len(u) // 2
            return np.stack([u[:h2], u[h2:]], 1).copy().view("<i2").ravel()
        return u.view(DT[dt]).copy()

    def rawbytes(ref):
        off, ln, dt = ref["$b"]
        return np.frombuffer(raw[bin0 + off:bin0 + off + ln], np.uint8), dt
    return h, arr, rawbytes


def run(size=None):
    out = C.SITE / "data"
    size = size or int(C.config().get("export", {}).get("shard_places", SHARD_PLACES))
    if (out / "index.json").exists():
        raise SystemExit("site/data is already sharded")
    na_h, na_a, na_raw = read(out / "na.dat")
    if "gfut_d" in na_h:
        raise SystemExit("this data has warming-level arrays, which reshard does not convert: run 'ctw export' instead")
    w_h, w_a, w_raw = read(out / "world.dat")
    P, S, E = 2, 4, 2
    NV = na_h["nv"]
    nna, nw = len(na_h["targets"]), len(w_h["targets"])
    version = na_h["data_version"]
    rows_in = [(t, 0, r) for t, r in enumerate(na_h["targets"])] + [(nna + j, 1, r) for j, r in enumerate(w_h["targets"])]
    shards, where = plan_shards([(t, g, r["c"], r["lat"], r["lon"]) for t, g, r in rows_in], size)

    # per-place arrays, page order (North America then world)
    def stack(key):
        a, b = na_a(na_h[key]), w_a(w_h[key])
        return np.concatenate([a.reshape(nna, -1), b.reshape(nw, -1)])
    A = {k: stack(k) for k in PER_PLACE}
    glob_by_t = {}
    for key, v in na_h["glob"].items():
        glob_by_t.setdefault(int(key.split("|")[1]), {})[key] = v
    shutil.rmtree(out / "p", ignore_errors=True)
    for sh in shards:
        sel = np.array(sh["ids"])
        pk = Pack()
        blk = dict(v=version, g=sh["g"], ids=sh["ids"])
        for k in PER_PLACE:
            a = A[k][sel]
            blk[k] = pk.planes(a.ravel()) if k == "fut_d" else pk.add(a.ravel())
        blk["sl"] = {str(j): rows_in[t][2]["sl"] for j, t in enumerate(sh["ids"]) if "sl" in rows_in[t][2]}
        blk["glob"] = {k: v for t in sh["ids"] for k, v in glob_by_t.get(t, {}).items()}
        _, sh["bytes"] = pk.write(blk, out / sh["f"])

    # overview: best-match position and sigma for every place
    plat, plon = na_a(na_h["plat"]), na_a(na_h["plon"])
    m = np.unpackbits(w_a(w_h["mask"]).view(np.uint8))[:w_h["nx"] * w_h["ny"]]
    cells = np.nonzero(m)[0]
    wlat, wlon = 90 - (cells // w_h["nx"] + .5) * w_h["res"], -180 + (cells % w_h["nx"] + .5) * w_h["res"]
    bi, bs = A["best_idx"].reshape(-1, P, S, E, 2), A["best_sig"].reshape(-1, P, S, E, 2)
    isna = (np.arange(nna + nw) < nna)[:, None, None, None, None]
    ii = np.maximum(bi, 0)
    la = np.where(isna, plat[np.minimum(ii, len(plat) - 1)], wlat[np.minimum(ii, len(wlat) - 1)])
    lo = np.where(isna, plon[np.minimum(ii, len(plon) - 1)], wlon[np.minimum(ii, len(wlon) - 1)])
    ok = (bi >= 0) & np.isfinite(bs)
    pk = Pack()
    pk.write(dict(v=version, n=nna + nw, sig=pk.add(np.where(ok, np.minimum(np.round(np.nan_to_num(bs) * 100), 65534), 65535).astype("uint16")),
                  pos=pk.add(np.stack([np.round(la * 100), np.round(lo * 100)], -1).astype("int16"))), out / "overview.dat")

    # index
    rows = [[r[c] for c in INDEX_COLS[:8]] + list(where[t]) for t, g, r in rows_in]
    for row, (t, g, r) in zip(rows, rows_in):
        row[7] = g
    json.dump(dict(v=version, cols=INDEX_COLS, na=nna, rows=rows, shards=[{"f": s["f"], "g": s["g"], "n": len(s["ids"]), "b": s["bytes"]} for s in shards]),
              open(out / "index.json", "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)

    # cores: everything that is not per-place, copied byte for byte
    for name, h, rb, nt in (("na.dat", na_h, na_raw, nna), ("world.dat", w_h, w_raw, nw)):
        pk = Pack()
        core = {}
        for k, v in h.items():
            if k in PER_PLACE or k in ("targets", "glob"):
                continue
            if isinstance(v, dict) and "$b" in v:
                b, dt = rb(v)
                core[k] = pk.add(b, dt)
            else:
                core[k] = v
        core.update(nt=nt, index=1)
        pk.write(core, out / name)
    print(f"resharded {nna} + {nw} places into {len(shards)} shards")


if __name__ == "__main__":
    run()
