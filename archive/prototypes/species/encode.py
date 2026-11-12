"""Encoders for the Spike G delivery experiment. Reads the arrays made by synth.py and writes one species/scenario
in each candidate format:  png (Web Mercator XYZ value-encoded PNG tiles), webp (same, lossless WebP), pmtiles
(the PNG tiles in a PMTiles v3 archive), cog (Cloud-Optimized GeoTIFF, EPSG:4326), cts (custom binary, below).

CTS1 layout (little endian):  'CTS1' | u32 n | JSON header (n bytes) | per level: u32 offset,u32 length per block
| block payloads. A block is BS x BS cells (256), planar bands, each band delta-coded along the row (mod 256) and
raw-deflated, so the browser can inflate it with DecompressionStream('deflate-raw'). Level f is the grid pooled by f
(1, 2, 4, 8): max of the 7 bit value, OR of the reach bit, max of each agreement nibble. Empty blocks have length 0.
Usage: python encode.py WORKDIR OUTDIR ssp245 s01 [s02 ...]"""
from __future__ import annotations
import io, json, struct, sys, zlib
from pathlib import Path
import numpy as np
from PIL import Image

NX, NY, BS = 8640, 4320, 256
LEVELS = (1, 2, 4, 8)


def pool(band, kind, f):
    if f == 1:
        return band
    h, w = band.shape[0] // f, band.shape[1] // f
    b = band[:h * f, :w * f].reshape(h, f, w, f)
    if kind == "S":
        return (b & 127).max((1, 3)) | ((b >> 7).max((1, 3)) << 7)
    if kind == "A":
        return ((b >> 4).max((1, 3)) << 4) | (b & 15).max((1, 3))
    return np.bitwise_or.reduce(b, axis=(1, 3))


KINDS = {"S0": "S", "S1": "S", "S2": "S", "A": "A", "N": "N"}


THR = 44


def lite(bands: dict):
    """classified product: suitability above the threshold in 3 classes (1..3) + reach bit, instead of 7 bit values"""
    out = {}
    for k, v in bands.items():
        if k in ("S0", "S1", "S2"):
            s = (v & 127).astype(np.int16)
            cls = np.where(s < THR, 0, 1 + np.minimum(2, (s - THR) * 3 // (128 - THR))).astype(np.uint8)
            out[k] = cls | (v & 128)
        else:
            out[k] = v
    return out


def lite_sizes(base, sc):
    r = {}
    for tag, bands, names in (("base", lite(base), ["S0"]), ("scen", lite(sc), ["S1", "S2", "A"])):
        webp = sum(len(enc_webp(t)) for _, _, _, t in tile_set(bands, names))
        png = sum(len(enc_png(t)) for _, _, _, t in tile_set(bands, names))
        r[tag] = dict(cts=len(enc_cts(bands, names)), png=png, webp=webp)
    return r


def load(work: Path, sid, ssp):
    if sid == "base":
        return {}
    z = np.load(work / f"sp_{sid}_{ssp}.npz")
    return {k: z[k] for k in ("S1", "S2", "A")}


def load_base(work: Path, sid):
    z = np.load(work / f"sp_{sid}_base.npz")
    return {"S0": z["S0"]}


def pyramid(bands: dict):
    return {f: {k: pool(v, KINDS[k], f) for k, v in bands.items()} for f in LEVELS}


# ---------- custom binary ----------
def enc_cts(bands: dict, names):
    pyr = pyramid(bands)
    levels, blobs, off_cursor = [], [], 0
    payloads = []
    for f in LEVELS:
        arrs = [pyr[f][n] for n in names]
        h, w = arrs[0].shape
        bx, by = -(-w // BS), -(-h // BS)
        entries = []
        for j in range(by):
            for i in range(bx):
                parts = []
                nz = False
                for a in arrs:
                    blk = np.zeros((BS, BS), np.uint8)
                    s = a[j * BS:(j + 1) * BS, i * BS:(i + 1) * BS]
                    blk[:s.shape[0], :s.shape[1]] = s
                    nz |= bool(blk.any())
                    d = blk.copy()
                    d[:, 1:] = blk[:, 1:] - blk[:, :-1]
                    parts.append(d.tobytes())
                if not nz:
                    entries.append(b"")
                    continue
                c = zlib.compressobj(9, zlib.DEFLATED, -15)
                entries.append(c.compress(b"".join(parts)) + c.flush())
        levels.append(dict(f=f, w=w, h=h, bx=bx, by=by))
        payloads.append(entries)
    hdr = dict(v=1, bs=BS, bands=list(names), levels=levels, lon0=-180, lat0=90, dlon=360 / NX, dlat=-180 / NY)
    nidx = sum(l["bx"] * l["by"] for l in levels)
    # header length must be fixed before offsets: iterate once
    hj = json.dumps(hdr, separators=(",", ":")).encode()
    base = 8 + len(hj) + 8 * nidx
    out_idx, out_data, pos = [], [], base
    offs = {}
    for li in range(len(payloads) - 1, -1, -1):          # payloads are stored coarsest level first (progressive reads)
        for ei, e in enumerate(payloads[li]):
            offs[(li, ei)] = pos if e else 0
            out_data.append(e)
            pos += len(e)
    for li, entries in enumerate(payloads):
        for ei, e in enumerate(entries):
            out_idx.append(struct.pack("<II", offs[(li, ei)], len(e)))
    return b"CTS1" + struct.pack("<I", len(hj)) + hj + b"".join(out_idx) + b"".join(out_data)
# NOTE: out_data is in coarsest-first order while out_idx is in level order


# ---------- Web Mercator tiles ----------
def merc_rows(size):
    y = (np.arange(size) + 0.5) / size
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * y))))
    return lat


def tile_set(bands: dict, names):
    """yield (z, x, y, array HxWxC) for non-empty tiles, z 0..5 (z5 ~4.9 km at the equator)"""
    pyr = pyramid(bands)
    for z in range(0, 6):
        f = {5: 1, 4: 2, 3: 4}.get(z, 8)
        size = 256 * 2 ** z
        lat = merc_rows(size)
        arrs = [pyr[f][n] for n in names]
        h, w = arrs[0].shape
        r = np.clip(((90 - lat) / 180 * h).astype(int), 0, h - 1)
        c = np.clip(((np.arange(size) + 0.5) / size * w).astype(int), 0, w - 1)
        img = np.stack([a[r][:, c] for a in arrs], -1)
        for ty in range(2 ** z):
            for tx in range(2 ** z):
                t = img[ty * 256:(ty + 1) * 256, tx * 256:(tx + 1) * 256]
                if t.any():
                    yield z, tx, ty, t


def enc_png(t):
    b = io.BytesIO()
    Image.fromarray(t[:, :, 0] if t.shape[2] == 1 else t).save(b, "PNG", optimize=True)
    return b.getvalue()


def enc_webp(t):
    b = io.BytesIO()
    Image.fromarray(t[:, :, 0] if t.shape[2] == 1 else t).save(b, "WEBP", lossless=True, method=6, exact=True)
    return b.getvalue()


def write_tiles(outdir: Path, bands, names, ext, fn):
    n = tot = 0
    idx = []
    for z, x, y, t in tile_set(bands, names):
        p = outdir / str(z) / str(x)
        p.mkdir(parents=True, exist_ok=True)
        data = fn(t)
        (p / f"{y}.{ext}").write_bytes(data)
        n += 1; tot += len(data); idx.append((z, x, y))
    (outdir / "index.json").write_text(json.dumps(idx, separators=(",", ":")))
    return n, tot


def write_pmtiles(path: Path, bands, names):
    from pmtiles.writer import write
    from pmtiles.tile import zxy_to_tileid, TileType, Compression
    tiles = sorted(((zxy_to_tileid(z, x, y), t) for z, x, y, t in tile_set(bands, names)), key=lambda a: a[0])
    with write(str(path)) as w:
        for tid, t in tiles:
            w.write_tile(tid, enc_png(t))
        w.finalize(dict(tile_type=TileType.PNG, tile_compression=Compression.NONE, min_lon_e7=-1800000000, min_lat_e7=-850000000,
                        max_lon_e7=1800000000, max_lat_e7=850000000, center_zoom=2, center_lon_e7=0, center_lat_e7=300000000),
                   {"name": "synthetic", "bands": list(names)})
    return len(tiles)


def write_cog(path: Path, bands, names, sparse=False):
    import rasterio
    from rasterio.shutil import copy
    from rasterio.transform import from_origin
    arr = np.stack([bands[n] for n in names])
    prof = dict(driver="MEM", width=NX, height=NY, count=len(names), dtype="uint8", crs="EPSG:4326",
                transform=from_origin(-180, 90, 360 / NX, 180 / NY))
    with rasterio.open("/vsimem/src.tif", "w", **{**prof, "driver": "GTiff"}) as d:
        d.write(arr)
    copy("/vsimem/src.tif", str(path), driver="COG", compress="DEFLATE", predictor=2, blocksize=256, overview_resampling="NEAREST",
         level=9, **({"sparse_ok": "TRUE"} if sparse else {}))


def du(p: Path):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and f.name != "index.json") if p.is_dir() else p.stat().st_size


def run(work, out, ssp, ids):
    res = {}
    for sid in ids:
        base = load_base(work, sid)
        sc = load(work, sid, ssp)
        r = {}
        for tag, bands, names in (("base", base, ["S0"]), ("scen", sc, ["S1", "S2", "A"])):
            o = out / sid / tag
            o.mkdir(parents=True, exist_ok=True)
            cts = enc_cts(bands, names)
            (o / "x.cts").write_bytes(cts)
            n, tot = write_tiles(o / "png", bands, names, "png", enc_png)
            n2, tot2 = write_tiles(o / "webp", bands, names, "webp", enc_webp)
            write_pmtiles(o / "x.pmtiles", bands, names)
            write_cog(o / "x.tif", bands, names)
            r[tag] = dict(cts=len(cts), png=tot, png_n=n, webp=tot2, pmtiles=(o / "x.pmtiles").stat().st_size,
                          cog=(o / "x.tif").stat().st_size)
            print(sid, tag, r[tag], flush=True)
        res[sid] = r
    return res


if __name__ == "__main__":
    work, out, ssp, ids = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4:]
    res = run(work, out, ssp, ids)
    (out / "sizes.json").write_text(json.dumps(res, indent=1))
