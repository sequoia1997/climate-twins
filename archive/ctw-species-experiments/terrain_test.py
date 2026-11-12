"""Spike B: terrain and soil access test (run in Actions). Copernicus GLO-90 on AWS open data and SoilGrids 2.0 (ISRIC),
resampled to the 2.5 arc-minute grid over a 2 x 2 degree window of the Alps (lat 45-47, lon 7-9)."""
import json, os, sys, time, math, resource
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import reproject, calculate_default_transform
from rasterio.vrt import WarpedVRT

def result(tag, **kw):
    print("RESULT", json.dumps({"tag": tag, **kw}, default=float), flush=True)

RES = 1 / 24
LAT_MAX, LAT_MIN, LON_MIN, LON_MAX = 47.0, 45.0, 7.0, 9.0
NY, NX = int(round((LAT_MAX - LAT_MIN) / RES)), int(round((LON_MAX - LON_MIN) / RES))
DST = from_origin(LON_MIN, LAT_MAX, RES, RES)

# ---------------------------------------------------------------- Copernicus DEM
t0 = time.time(); nbytes = 0; tiles = []
for lat in (45, 46):
    for lon in (7, 8):
        name = f"Copernicus_DSM_COG_30_N{lat:02d}_00_E{lon:03d}_00_DEM"
        tiles.append(f"https://copernicus-dem-90m.s3.amazonaws.com/{name}/{name}.tif")
srcs = [rasterio.open(u) for u in tiles]
mos, tr = merge(srcs)
dt_read = time.time() - t0
dem = mos[0]
result("dem_read", tiles=len(tiles), shape=dem.shape, seconds=dt_read, res_deg=srcs[0].res[0], dtype=str(dem.dtype))
out = {}
for nm, rs in (("mean", Resampling.average), ("min", Resampling.min), ("max", Resampling.max), ("rms", Resampling.rms)):
    arr = np.full((NY, NX), np.nan, "float32")
    reproject(dem.astype("float32"), arr, src_transform=tr, src_crs="EPSG:4326", dst_transform=DST, dst_crs="EPSG:4326", resampling=rs, src_nodata=-32767, dst_nodata=np.nan)
    out[nm] = arr
result("dem_2p5min", seconds=time.time() - t0, mean_elev_m=float(np.nanmean(out["mean"])), max_range_m_p95=float(np.nanpercentile(out["max"] - out["min"], 95)),
       mean_range_m=float(np.nanmean(out["max"] - out["min"])), cells=int(NY * NX))
slope = np.hypot(*np.gradient(out["mean"], 4600.0))
result("dem_note", terrain_roughness_sd_mean_m=float(np.nanmean(out["rms"])))
# size estimate for global: 90 m tiles listing count
import urllib.request, re
for pre in ["Copernicus_DSM_COG_30_N46_00_E00"]:
    t = urllib.request.urlopen(f"https://copernicus-dem-90m.s3.amazonaws.com/?list-type=2&max-keys=3&prefix={pre}", timeout=60).read().decode()
    print(re.findall(r"<Key>([^<]+)</Key><LastModified>[^<]+</LastModified><ETag>[^<]*</ETag><Size>(\d+)", t))
tile_sizes = [int(s.headers.get("Content-Length", 0)) if hasattr(s, "headers") else 0 for s in []]

# ---------------------------------------------------------------- SoilGrids
base = "https://files.isric.org/soilgrids/latest/data"
for layer in ("phh2o/phh2o_0-5cm_mean", "clay/clay_0-5cm_mean", "soc/soc_0-5cm_mean"):
    u = f"/vsicurl/{base}/{layer}.vrt"
    t0 = time.time()
    try:
        with rasterio.open(u) as ds:
            result("soil_vrt_open", layer=layer, shape=ds.shape, crs=str(ds.crs)[:60], res=ds.res, dtype=ds.dtypes[0], scale=ds.scales[0], nodata=ds.nodata, seconds=time.time() - t0)
            with WarpedVRT(ds, crs="EPSG:4326", transform=DST, width=NX, height=NY, resampling=Resampling.average, nodata=ds.nodata) as v:
                t1 = time.time()
                a = v.read(1, masked=True).astype("float32").filled(np.nan) * ds.scales[0]
            result("soil_2p5min_250m_average", layer=layer, seconds=time.time() - t1, mean=float(np.nanmean(a)), valid_frac=float(np.isfinite(a).mean()))
    except Exception as e:
        result("soil_vrt_fail", layer=layer, err=str(e)[:200])
# aggregated 1 km product (global single file)
for u in (f"{base[:-5]}data_aggregated/1000m/phh2o/phh2o_0-5cm_mean_1000.tif",):
    try:
        with rasterio.open(f"/vsicurl/{u}") as ds:
            result("soil_agg_1km", shape=ds.shape, crs=str(ds.crs)[:50], res=ds.res, dtype=ds.dtypes[0], tiled=ds.profile.get("tiled"), blocks=ds.block_shapes[0])
    except Exception as e:
        result("soil_agg_fail", err=str(e)[:200])
result("done", rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
