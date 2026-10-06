"""Spike B probe 2: CHELSA layout discovery (S3 listing), TerraClimate chunking and regional range-read timing,
WorldClim / CHELSA GeoTIFF range reads (GDAL vsicurl) of a 20 x 20 degree window."""
import re, sys, time, resource
import numpy as np
sys.path.insert(0, "ctw/species")
from spike_b_probe import head, get_text, gb, sec, throughput

sec("CHELSA S3 listing")
HOST = "https://os.unil.cloud.switch.ch/chelsa02"
for pre in ["chelsa/global/climatologies/", "chelsa/global/climatologies/1981-2010/", "chelsa/global/climatologies/2041-2070/",
            "chelsa/global/climatologies/2041-2070/GFDL-ESM4/", "chelsa/global/climatologies/2041-2070/GFDL-ESM4/ssp370/",
            "chelsa/global/climatologies/2041-2070/GFDL-ESM4/ssp370/bio/"]:
    t = get_text(f"{HOST}?prefix={pre}&delimiter=/&max-keys=60")
    keys = re.findall(r"<(?:Prefix|Key)>([^<]+)</(?:Prefix|Key)>", t)
    print(pre, "->", len(keys), [k[len(pre):] for k in keys if k != pre][:40], t[:150].replace("\n", " ") if not keys else "")
B = HOST + "/chelsa/global/climatologies"
for u in [f"{B}/1981-2010/bio/CHELSA_bio1_1981-2010_V.2.1.tif", f"{B}/bio/1981-2010/CHELSA_bio1_1981-2010_V.2.1.tif",
          f"{B}/tasmax/1981-2010/CHELSA_tasmax_07_1981-2010_V.2.1.tif", f"{B}/1981-2010/tasmax/CHELSA_tasmax_07_1981-2010_V.2.1.tif",
          f"{B}/2041-2070/GFDL-ESM4/ssp370/bio/CHELSA_bio1_2041-2070_gfdl-esm4_ssp370_V.2.1.tif",
          f"{B}/GFDL-ESM4/ssp370/2041-2070/bio/CHELSA_bio1_2041-2070_gfdl-esm4_ssp370_V.2.1.tif"]:
    print(head(u), u.replace(B, ""))

sec("TerraClimate: chunking and regional range read")
import fsspec, h5py
TC = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA/TerraClimate_{v}_{y}.nc"
t0 = time.time()
f = fsspec.open(TC.format(v="tmax", y=2019), block_size=16 << 20).open()
h = h5py.File(f, "r")
d = h["tmax"]
print("open", round(time.time() - t0, 1), "s;", d.shape, d.dtype, "chunks", d.chunks, "compression", d.compression, "scale", dict(d.attrs).get("scale_factor"), "fill", dict(d.attrs).get("_FillValue"), dict(d.attrs).get("missing_value"))
print("lat/lon vars:", [k for k in h.keys()])
t0 = time.time()
# 20 x 20 deg box lat 40-60, lon 0-20: rows 720.., cols 4320..
a = d[:, 720:1200, 4320:4800]
print("regional read 12 months:", a.shape, round(time.time() - t0, 1), "s", "MB-ish transferred:", "see cache")
print("sample raw", a[0, 100, 100], "dtype", a.dtype)
t0 = time.time()
full = d[0]
print("one global month read", round(time.time() - t0, 1), "s", full.shape, "mem MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
raw = np.asarray(full)
fv = dict(d.attrs).get("_FillValue")
land = (raw != fv) if fv is not None else np.isfinite(raw)
if np.issubdtype(raw.dtype, np.floating):
    land = np.isfinite(raw) & (raw > -1e5)
print("global land cells (tmax month 0):", int(land.sum()), "of", land.size)
rows = land.sum(1)
lat = 89.979166667 - np.arange(4320) / 24
area = (6371.0088 * np.radians(1 / 24)) ** 2 * np.cos(np.radians(lat))
print("land area km2:", float((rows * area).sum()), "south of -60:", int(rows[lat < -60].sum()), "north of 60:", int(rows[lat > 60].sum()))
np.save("/tmp/land_rows.npy", rows)
h.close(); f.close()

sec("GDAL range reads of GeoTIFFs (WorldClim 2.5m future, CHELSA)")
import subprocess
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "rasterio"], check=False)
import rasterio
from rasterio.windows import from_bounds
for u in ["/vsicurl/https://geodata.ucdavis.edu/cmip6/2.5m/ACCESS-CM2/ssp245/wc2.1_2.5m_tmax_ACCESS-CM2_ssp245_2041-2060.tif",
          "/vsicurl/https://geodata.ucdavis.edu/cmip6/30s/ACCESS-CM2/ssp245/wc2.1_30s_tmax_ACCESS-CM2_ssp245_2041-2060.tif",
          f"/vsicurl/{B}/tasmax/1981-2010/CHELSA_tasmax_07_1981-2010_V.2.1.tif"]:
    try:
        t0 = time.time()
        with rasterio.open(u) as ds:
            print(u[-70:], ds.shape, ds.count, ds.dtypes[0], ds.block_shapes[0], ds.compression if hasattr(ds, "compression") else "", ds.res)
            w = from_bounds(7, 45, 8, 46, ds.transform)
            x = ds.read(1, window=w)
            print("  1 degree window", x.shape, round(time.time() - t0, 1), "s")
            t0 = time.time()
            w = from_bounds(0, 40, 20, 60, ds.transform)
            x = ds.read(1, window=w)
            print("  20x20 window", x.shape, round(time.time() - t0, 1), "s")
    except Exception as e:  # noqa: BLE001
        print(u[-70:], "FAILED", str(e)[:200])
print("done")
