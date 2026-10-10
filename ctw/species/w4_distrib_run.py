"""W4: summarise USFS RDS-2024-0020 (North American tree models) for the five pilot trees: where the published model puts each species now
(1991-2020) and under SSP2-4.5 / SSP5-8.5 (2070-2100): centroid, edges, area, shift. Reference for the 'compare with published projections' check."""
import io, os, sys, zipfile, urllib.request, json
import numpy as np, pandas as pd
import rasterio
from pyproj import Transformer
from ctw.species import hindcast as H

URL = "https://www.fs.usda.gov/rds/archive/products/RDS-2024-0020/RDS-2024-0020.zip"
SP = {318: ("Acer_saccharum", "Acer saccharum"), 316: ("Acer_rubrum", "Acer rubrum"), 129: ("Pinus_strobus", "Pinus strobus"),
      746: ("Populus_tremuloides", "Populus tremuloides"), 802: ("Quercus_alba", "Quercus alba")}
b = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "climate-twins-w4/0.1"}), timeout=900).read()
z = zipfile.ZipFile(io.BytesIO(b)); os.makedirs("rds20", exist_ok=True)
rows = []
def load(folder, stem, spcd):
    n = f"Data/{folder}/{stem}_sp{spcd}.tif"; z.extract(n, "rds20")
    with rasterio.open(os.path.join("rds20", n)) as r:
        a = r.read(1, masked=True)
        rr, cc = np.meshgrid(np.arange(r.height), np.arange(r.width), indexing="ij")
        x, y = rasterio.transform.xy(r.transform, rr.ravel(), cc.ravel())
        lon, lat = Transformer.from_crs(r.crs, "EPSG:4326", always_xy=True).transform(np.array(x), np.array(y))
    return lat, lon, np.ma.filled(a.astype(float), 0.0).ravel()
for spcd, (folder, sci) in SP.items():
    lat, lon, cur = load(folder, "CurrentPredicted_Consensus", spcd)
    area = np.ones(len(lat))
    for scen in ("SSP2-45", "SSP5-85"):
        _, _, fut = load(folder, f"{scen}_Predicted_Consensus", spcd)
        for thr in (1.0, 5.0):
            rc = H.range_change(lat, lon, area, cur >= thr, fut >= thr)
            rows.append(dict(spcd=spcd, species=sci, scenario=scen, threshold=thr, cells_now=int((cur >= thr).sum()), cells_future=int((fut >= thr).sum()),
                             **{k: rc[k] for k in ("km", "bearing", "north", "east", "edge_hi_km", "edge_lo_km", "area_change")},
                             centroid_now_lat=H.range_stats(lat, lon, area, cur >= thr)["clat"], centroid_now_lon=H.range_stats(lat, lon, area, cur >= thr)["clon"],
                             centroid_future_lat=H.range_stats(lat, lon, area, fut >= thr)["clat"], centroid_future_lon=H.range_stats(lat, lon, area, fut >= thr)["clon"]))
d = pd.DataFrame(rows); os.makedirs("w4-out", exist_ok=True); d.to_csv("w4-out/distrib2024_summary.csv", index=False)
pd.set_option("display.width", 250, "display.max_columns", 30); print(d.round(1).to_string())
