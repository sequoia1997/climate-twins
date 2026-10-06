"""Spike B probe (run from GitHub Actions): reachability, sizes, ranges and throughput of the climate-stack data sources.
No secrets. Prints a plain report. Stdlib only."""
import re, sys, time, urllib.request, urllib.error

UA = {"User-Agent": "climate-twins-spike-b/1.0"}


def head(url, timeout=40):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=timeout)
        return r.status, int(r.headers.get("Content-Length") or -1), r.headers.get("Accept-Ranges", "-")
    except urllib.error.HTTPError as e:
        return e.code, -1, "-"
    except Exception as e:  # noqa: BLE001
        return type(e).__name__ + ":" + str(e)[:60], -1, "-"


def get_text(url, timeout=60):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf8", "replace")
    except Exception as e:  # noqa: BLE001
        return "ERR " + str(e)[:100]


def throughput(url, seconds=20, rng=None):
    h = dict(UA)
    if rng:
        h["Range"] = rng
    t0 = time.time(); n = 0
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60)
        while time.time() - t0 < seconds:
            b = r.read(1 << 20)
            if not b:
                break
            n += len(b)
        return r.status, n / 1e6 / max(time.time() - t0, 1e-6)
    except Exception as e:  # noqa: BLE001
        return str(e)[:80], 0


def sec(t):
    print("\n=== " + t, flush=True)


def gb(n):
    return f"{n / 1e9:.2f} GB" if n > 0 else "n/a"


# ---------------------------------------------------------------- TerraClimate
sec("TerraClimate: per-variable yearly file size (HEAD)")
TC = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA/TerraClimate_{v}_{y}.nc"
tot = 0
for v in ["tmax", "tmin", "ppt", "def", "aet", "soil", "pet", "vpd", "srad", "vap", "ws", "q", "swe", "PDSI"]:
    s, n, ar = head(TC.format(v=v, y=2019))
    print(f"{v:5s} 2019 status={s} size={gb(n)} ranges={ar}")
    tot += max(n, 0)
print("sum of the 14 variables for one year:", gb(tot))
sec("TerraClimate: range GET and full-file throughput")
u = TC.format(v="tmax", y=2019)
print("range 1MB..2MB:", throughput(u, 10, "bytes=1000000-1999999"))
print("full GET 25 s:", throughput(u, 25))
for p in ["http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_terraclimate_tmax_1958_CurrentYear_GLOBE.nc.dds",
          "https://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_terraclimate_tmax_1958_CurrentYear_GLOBE.nc.dds"]:
    print(p, head(p), get_text(p)[:200].replace("\n", " "))

# ---------------------------------------------------------------- WorldClim
sec("WorldClim 2.1 base (1970-2000) zip sizes")
for res in ["30s", "2.5m", "5m", "10m"]:
    for v in ["tmax", "tmin", "prec", "bio"]:
        s, n, ar = head(f"https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_{res}_{v}.zip")
        print(f"{res:5s} {v:5s} status={s} size={gb(n)} ranges={ar}")
sec("WorldClim CMIP6 index")
for res in ["2.5m", "30s"]:
    idx = get_text(f"https://geodata.ucdavis.edu/cmip6/{res}/")
    gcms = sorted(set(re.findall(r'href="([A-Za-z0-9\-_.]+)/"', idx)))
    print(res, "index models:", len(gcms), gcms)
    if res == "2.5m" and gcms:
        tot_files = 0
        allssp = {}
        for g in gcms:
            t = get_text(f"https://geodata.ucdavis.edu/cmip6/{res}/{g}/")
            ssps = sorted(set(re.findall(r'href="(ssp\d+)/"', t)))
            allssp[g] = ssps
        print("ssps per model:", allssp)
        g = "MIROC6" if "MIROC6" in gcms else gcms[0]
        for ssp in (allssp[g] or [])[:1]:
            t = get_text(f"https://geodata.ucdavis.edu/cmip6/{res}/{g}/{ssp}/")
            fs = re.findall(r'href="(wc2[^"]+\.tif)"', t)
            print(g, ssp, "files:", len(fs), fs)
            for f in fs[:6]:
                s, n, ar = head(f"https://geodata.ucdavis.edu/cmip6/{res}/{g}/{ssp}/{f}")
                print("  ", f, s, gb(n), ar)
for res, g, ssp, per in [("30s", "MIROC6", "ssp245", "2041-2060"), ("2.5m", "MIROC6", "ssp245", "2041-2060")]:
    for v in ["tmax", "prec", "bioc"]:
        f = f"https://geodata.ucdavis.edu/cmip6/{res}/{g}/{ssp}/wc2.1_{res}_{v}_{g}_{ssp}_{per}.tif"
        print(res, v, head(f))
sec("WorldClim throughput (2.5m tmax base zip, 20 s)")
print(throughput("https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_2.5m_tmax.zip", 20))

# ---------------------------------------------------------------- CHELSA
sec("CHELSA v2.1")
B = "https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies"
for var, per in [("tasmax", "1981-2010"), ("tasmin", "1981-2010"), ("pr", "1981-2010")]:
    print(var, head(f"{B}/{per}/{var}/CHELSA_{var}_07_{per}_V.2.1.tif"))
print("bio1 base", head(f"{B}/1981-2010/bio/CHELSA_bio1_1981-2010_V.2.1.tif"))
n_ok = 0; n_all = 0; sizes = []
for per in ["2011-2040", "2041-2070", "2071-2100"]:
    for m in ["gfdl-esm4", "ipsl-cm6a-lr", "mpi-esm1-2-hr", "mri-esm2-0", "ukesm1-0-ll"]:
        for ssp in ["ssp126", "ssp370", "ssp585"]:
            u = f"{B}/{per}/{m.upper()}/{ssp}/bio/CHELSA_bio1_{per}_{m}_{ssp}_V.2.1.tif"
            s, n, ar = head(u, 30); n_all += 1
            if s == 200:
                n_ok += 1; sizes.append(n)
            if per == "2041-2070" and ssp == "ssp126":
                print("  ", m, ssp, per, s, gb(n), ar)
print(f"future bio1 files reachable: {n_ok}/{n_all}; size min/max {min(sizes, default=0)/1e6:.0f}/{max(sizes, default=0)/1e6:.0f} MB")
for v in ["tasmax", "tasmin", "pr"]:
    print("future", v, head(f"{B}/2041-2070/GFDL-ESM4/ssp370/{v}/CHELSA_gfdl-esm4_r1i1p1f1_w5e5_ssp370_{v}_07_2041_2070_norm.tif"))
sec("CHELSA throughput (bio1 baseline, 20 s) and range read")
u = f"{B}/1981-2010/bio/CHELSA_bio1_1981-2010_V.2.1.tif"
print("range 1-2 MB:", throughput(u, 10, "bytes=1000000-1999999"))
print("full 20 s:", throughput(u, 20))

# ---------------------------------------------------------------- terrain and soil
sec("Copernicus DEM on AWS and SoilGrids")
for p in ["https://copernicus-dem-90m.s3.amazonaws.com/Copernicus_DSM_COG_30_N46_00_E007_00_DEM/Copernicus_DSM_COG_30_N46_00_E007_00_DEM.tif",
          "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N46_00_E007_00_DEM/Copernicus_DSM_COG_10_N46_00_E007_00_DEM.tif"]:
    print(p.split("/")[-1], head(p))
for p in ["https://files.isric.org/soilgrids/latest/data/phh2o/phh2o_0-5cm_mean.vrt",
          "https://files.isric.org/soilgrids/latest/data/phh2o/phh2o_0-5cm_mean/tileSG-001-002/tileSG-001-002_1-1.tif",
          "https://files.isric.org/soilgrids/latest/data_aggregated/5000m/phh2o/phh2o_0-5cm_mean_5000.tif",
          "https://files.isric.org/soilgrids/latest/data_aggregated/1000m/phh2o/phh2o_0-5cm_mean_1000.tif",
          "https://files.isric.org/soilgrids/latest/data_aggregated/5000m/",
          "https://zenodo.org/api/records/5914710"]:
    print(p, head(p))
print(get_text("https://files.isric.org/soilgrids/latest/data_aggregated/")[:600])
print("done")
