"""Writer and reader for the CTS delivery format chosen in spike G (docs/spikes/G-delivery-ui.md, prototypes/species/encode.py).

CTS1 layout (little endian):  'CTS1' | u32 n | JSON header (n bytes) | per level: (u32 offset, u32 length) per block | block payloads.
A block is BS x BS cells (256), planar bands, each band delta-coded along the row (mod 256) and raw-deflated, so a browser can inflate
it with DecompressionStream('deflate-raw'). Level f is the grid pooled by f (1, 2, 4, 8): max of the 7 bit value (class for the lite
product) and OR of the reach bit ('S' bands), max of each agreement nibble ('A' bands), bitwise OR ('N' bands). Empty blocks have
length 0. Payloads are stored coarsest level first. The writer here produces byte-identical files to the prototype's encoder for the
same bands (checked in tests/test_species_pipeline.py against prototypes/species/data when present).

Files per species (names as the prototype expects):
  <id>_base.cts        band S0: present suitability (lite classes 0..3; full product: 7 bit)
  <id>_<ssp>.cts       bands S1, S2 (near / late period: class | reach bit 7), A (agreement, high nibble near period, low nibble late),
                       N (novel climate for this species: bit 0 near period, bit 1 late period; an addition to the prototype's three bands)
with ssp as 'ssp245' / 'ssp585'. `prototype_stats_entry` maps a summary JSON to the prototype's stats.json species record.
"""
from __future__ import annotations
import json
import struct
import zlib
import numpy as np

from .project import Projection, THR7, MODES
from .grid import GridSpec

BS = 256
LEVELS = (1, 2, 4, 8)
KINDS = {"S0": "S", "S1": "S", "S2": "S", "A": "A", "N": "N"}
SSP_KEY = {"SSP1-2.6": "ssp126", "SSP2-4.5": "ssp245", "SSP3-7.0": "ssp370", "SSP5-8.5": "ssp585"}
PERIOD_KEY = {"2041-2060": "2050", "2081-2100": "2100"}


def pool(band: np.ndarray, kind: str, f: int) -> np.ndarray:
    if f == 1:
        return band
    h, w = band.shape[0] // f, band.shape[1] // f
    b = band[:h * f, :w * f].reshape(h, f, w, f)
    if kind == "S":
        return (b & 127).max((1, 3)) | ((b >> 7).max((1, 3)) << 7)
    if kind == "A":
        return ((b >> 4).max((1, 3)) << 4) | (b & 15).max((1, 3))
    return np.bitwise_or.reduce(b, axis=(1, 3))


def lite(v: np.ndarray) -> np.ndarray:
    """7 bit suitability (+ reach bit) -> class 0 (below threshold), 1..3 (thirds of the range above it) + reach bit."""
    s = (v & 127).astype(np.int16)
    cls = np.where(s < THR7, 0, 1 + np.minimum(2, (s - THR7) * 3 // (128 - THR7))).astype(np.uint8)
    return cls | (v & 128)


def encode(bands: dict, names, kinds: dict = None, meta: dict = None) -> bytes:
    """bands: name -> uint8 (H, W) arrays of equal shape. Returns the CTS1 file."""
    kinds = {**KINDS, **(kinds or {})}
    H, W = bands[names[0]].shape
    pyr = {f: {k: pool(bands[k], kinds[k], f) for k in names} for f in LEVELS}
    levels, payloads = [], []
    for f in LEVELS:
        arrs = [pyr[f][n] for n in names]
        h, w = arrs[0].shape
        bx, by = -(-w // BS), -(-h // BS)
        entries = []
        for j in range(by):
            for i in range(bx):
                parts, nz = [], False
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
    hdr = dict(v=1, bs=BS, bands=list(names), levels=levels, lon0=-180, lat0=90, dlon=360 / W, dlat=-180 / H)
    if meta:
        hdr["meta"] = meta                                         # tier, range_shifts_tested, cv_kind: ignored by readers that do not know it
    nidx = sum(l["bx"] * l["by"] for l in levels)
    hj = json.dumps(hdr, separators=(",", ":")).encode()
    pos = 8 + len(hj) + 8 * nidx
    offs, out_data = {}, []
    for li in range(len(payloads) - 1, -1, -1):                      # coarsest level first (progressive reads)
        for ei, e in enumerate(payloads[li]):
            offs[(li, ei)] = pos if e else 0
            out_data.append(e)
            pos += len(e)
    idx = [struct.pack("<II", offs[(li, ei)], len(e)) for li, entries in enumerate(payloads) for ei, e in enumerate(entries)]
    return b"CTS1" + struct.pack("<I", len(hj)) + hj + b"".join(idx) + b"".join(out_data)


def decode(data: bytes, level: int = 1) -> dict:
    """CTS1 file -> {band name: uint8 array} at pooling level `level` (1 = full resolution)."""
    assert data[:4] == b"CTS1"
    n = struct.unpack_from("<I", data, 4)[0]
    hdr = json.loads(data[8:8 + n])
    pos = 8 + n
    index = []
    for lv in hdr["levels"]:
        e = []
        for _ in range(lv["bx"] * lv["by"]):
            e.append(struct.unpack_from("<II", data, pos))
            pos += 8
        index.append(e)
    li = [l["f"] for l in hdr["levels"]].index(level)
    lv = hdr["levels"][li]
    nb, bs = len(hdr["bands"]), hdr["bs"]
    out = {b: np.zeros((lv["by"] * bs, lv["bx"] * bs), np.uint8) for b in hdr["bands"]}
    for k, (off, ln) in enumerate(index[li]):
        if not ln:
            continue
        j, i = divmod(k, lv["bx"])
        raw = zlib.decompressobj(-15).decompress(data[off:off + ln])
        arr = np.frombuffer(raw, np.uint8).reshape(nb, bs, bs)
        for bi, b in enumerate(hdr["bands"]):
            out[b][j * bs:(j + 1) * bs, i * bs:(i + 1) * bs] = np.cumsum(arr[bi], axis=1, dtype=np.uint8)
    return {b: a[:lv["h"], :lv["w"]] for b, a in out.items()}


def species_files(proj: Projection, sid: str, product: str = "lite", meta: dict = None) -> dict:
    """{file name: bytes} for one species. product 'lite' (classes, the prototype's product) or 'full' (7 bit values)."""
    conv = lite if product == "lite" else (lambda v: v)
    files = {f"{sid}_base.cts": encode({"S0": conv(proj.S0)}, ["S0"], meta=meta)}
    periods = sorted({p for (_, p) in proj.scen})
    for ssp in sorted({s for (s, _) in proj.scen}):
        ps = [p for p in periods if (ssp, p) in proj.scen]
        if len(ps) < 2:
            ps = ps + ps[-1:]                                       # a single period fills both slots
        sc = [proj.scen[(ssp, p)] for p in ps[:2]]
        S = [conv(s.S) | (proj.reach[p].astype(np.uint8) << 7) for s, p in zip(sc, ps[:2])]
        A = ((sc[0].A << 4) | sc[1].A).astype(np.uint8)
        N = (sc[0].N | (sc[1].N << 1)).astype(np.uint8)
        files[f"{sid}_{SSP_KEY.get(ssp, ssp)}.cts"] = encode({"S1": S[0], "S2": S[1], "A": A, "N": N}, ["S1", "S2", "A", "N"], meta=meta)
    return files


def prototype_stats_entry(summary: dict, bbox: list = None) -> dict:
    """Record in the shape of prototypes/species/data/stats.json['species'][id] built from a summary JSON (areas in km2). The
    'place' table is not produced here (it needs the place list); scenario / period combinations that were withheld are omitted."""
    sp = summary["species"]
    info = dict(id=sp["id"], name=sp.get("common_name") or sp["scientific_name"], sci=sp["scientific_name"], group=sp.get("group"),
                deps=[], by={}, place={}, area_now_km2=summary["area_now_km2"], tier=summary["tier"], confidence=summary["confidence"], range_shifts_tested=summary.get("range_shifts_tested"), kind=summary.get("species_kind"), cv_kind=summary.get("cv_kind"),
                bbox=bbox or [-180, -60, 180, 80])
    for k, sc in summary["scenarios"].items():
        if sc.get("withheld"):
            continue
        for mode, m in sc["modes"].items():
            info["by"][f"{SSP_KEY.get(sc['ssp'], sc['ssp'])}|{PERIOD_KEY.get(sc['period'], sc['period'])}|{mode}"] = dict(
                now=m["area_now"], fut=m["area_fut"], lost=m["loss"], kept=m["stable"], gained=m["gain"], c0=m["centroid_now"],
                c1=m["centroid_fut"], shift_km=m["shift_km"], bearing=m["bearing"], agree_share=m["agree_share"])
    return info
