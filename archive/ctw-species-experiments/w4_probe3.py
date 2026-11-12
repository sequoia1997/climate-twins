"""W4 probe 3: which pilot trees are in USFS RDS-2019-0029 and RDS-2024-0020; raster format; FIA user-guide links and fuzzing statement."""
import io, re, sys, zipfile, urllib.request, os, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from w4_probe2 import Ranged, UA, text
SP = {318: "Acer saccharum", 316: "Acer rubrum", 129: "Pinus strobus", 746: "Populus tremuloides", 802: "Quercus alba"}
for rid, pat in (("RDS-2019-0029", "sp%d_"), ("RDS-2024-0020", "_sp%d.")):
    u = "https://www.fs.usda.gov/rds/archive/products/%s/%s.zip" % (rid, rid)
    z = zipfile.ZipFile(io.BufferedReader(Ranged(u), 1 << 16)); names = z.namelist()
    print("\n==", rid, len(names), "entries; top-level", sorted({n.split("/")[0] for n in names}))
    print("  non-data entries:", [n for n in names if not n.startswith("Data/")][:30])
    for spcd, nm in SP.items():
        hit = [n for n in names if (pat % spcd) in n]
        print("  ", spcd, nm, "files:", len(hit), [h.split("/")[-1] for h in hit][:14])
    if rid.endswith("0029"):
        print("  distinct file stems sample:", sorted({re.sub(r"sp\d+", "spN", n.split("/")[-1]) for n in names})[:40])
# download the 0020 zip and read the 5 species' current rasters
u = "https://www.fs.usda.gov/rds/archive/products/RDS-2024-0020/RDS-2024-0020.zip"
b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=900).read()
z = zipfile.ZipFile(io.BytesIO(b)); os.makedirs("rds20", exist_ok=True)
for spcd in SP:
    for n in z.namelist():
        if ("_sp%d." % spcd) in n and n.endswith((".tif", ".tfw", ".tif.xml")) and ("Predicted_Consensus" in n or "Actual" in n or "HQCL" in n):
            z.extract(n, "rds20")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "rasterio"], check=False)
try:
    import rasterio, numpy as np
    for root, _, fs in os.walk("rds20"):
        for f in sorted(fs):
            if f.endswith(".tif") and ("Predicted_Consensus" in f or "Actual" in f):
                with rasterio.open(os.path.join(root, f)) as r:
                    a = r.read(1, masked=True)
                    print(f, "crs", r.crs, "shape", r.shape, "res", r.res, "bounds", tuple(round(x, 2) for x in r.bounds), "dtype", r.dtypes[0], "min/max", float(a.min()), float(a.max()), "valid", int((~a.mask).sum()) if hasattr(a, "mask") else "")
except Exception as e: print("rasterio FAIL", type(e).__name__, e)
for f in sorted(os.listdir("rds20/Data/Acer_saccharum")) if os.path.isdir("rds20/Data/Acer_saccharum") else []:
    if f.endswith(".tif.xml") and "Current" in f:
        t = text(open("rds20/Data/Acer_saccharum/" + f, encoding="utf8", errors="replace").read()); print("XML", f, t[:2500])
for u in ("https://research.fs.usda.gov/understory/forest-inventory-and-analysis-database-user-guide-nfi", "https://research.fs.usda.gov/products/dataandtools/fia-datamart"):
    h = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read().decode("utf8", "replace")
    print("\n==", u); print(text(h)[:1500]); print("LINKS", sorted(set(re.findall(r'href="([^"]+)"', h)))[:80])
