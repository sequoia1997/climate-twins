"""IPCC AR6 relative sea-level projections (Fox-Kemper et al. 2021; data: Garner et al. 2021, Zenodo 5914709),
medium confidence, relative to 1995-2014, including vertical land motion. For each place within 50 km of a
projection location (tide gauges and the 1° coastal grid), the 17th, 50th and 83rd percentiles (the AR6 likely
range) for 2050 and 2100 under each scenario.

The projections are fixed until the next IPCC assessment, so this runs once and its small output
(data/sealevel.json) is committed. Only the four files needed are read out of the multi-gigabyte archive,
using HTTP range requests. Any failure leaves the previous file (or none) in place: sea level is optional."""
from __future__ import annotations
import json, re
import numpy as np
from . import common as C

MAX_KM = 50.0
QUANTS = (0.17, 0.5, 0.83)


def _members(url):
    from remotezip import RemoteZip
    rz = RemoteZip(url, initial_buffer_size=1 << 20)
    return rz, rz.namelist()


def run(cfg=None):
    cfg = cfg or C.config()
    dest = C.DATA / "sealevel.json"
    try:
        _run(cfg, dest)
    except Exception as e:  # noqa: BLE001
        C.log.warning("sea level step failed, keeping the previous data (%s)", e)


def _run(cfg, dest):
    import xarray as xr
    T = C.targets()
    rz, names = _members(cfg["sources"]["sealevel_zip"])
    C.log.info("sea level archive: %d members", len(names))
    out = {}
    lat = lon = None
    for sid, slab in zip(cfg["scenarios"]["ids"], cfg["scenarios"]["labels"]):
        pat = re.compile(rf"(^|/)total_{sid}_medium_confidence_values\.nc$")
        cand = [n for n in names if pat.search(n) and "novlm" not in n.lower()]
        if not cand:
            C.log.warning("no medium-confidence total file for %s; members look like: %s", sid, names[:8])
            continue
        # prefer the regional (tide gauge + grid) file over a global-mean one
        cand.sort(key=lambda n: (0 if "regional" in n else 1, len(n)))
        local = C.work("downloads", "sealevel", cand[0].split("/")[-1])
        if not local.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            with rz.open(cand[0]) as src, open(local, "wb") as dst:
                while chunk := src.read(1 << 22):
                    dst.write(chunk)
        ds = xr.open_dataset(local)
        C.log.info("sea level %s: %s", sid, {k: dict(ds[k].sizes) for k in ds.data_vars})
        v = ds["sea_level_change"]
        qd = next(d for d in v.dims if d.startswith("quantile"))
        yd = next(d for d in v.dims if d.startswith("year"))
        ld = next(d for d in v.dims if d.startswith("location"))
        if lat is None:
            lat, lon = ds["lat"].values.astype(float), ds["lon"].values.astype(float)
            near = np.zeros(len(T), int); dist = np.zeros(len(T))
            for k in range(len(T)):                         # one place at a time keeps memory small
                dk = C.haversine_km(T.lat.values[k], T.lon.values[k], lat, lon)
                near[k] = int(dk.argmin()); dist[k] = float(dk[near[k]])
        scale = 0.001 if str(v.attrs.get("units", "mm")).lower().startswith("mm") else 1.0
        vals = v.sel({qd: list(QUANTS)}, method="nearest").sel({yd: [2050, 2100]}, method="nearest").transpose(qd, yd, ld).values * scale
        for k in np.where(dist <= MAX_KM)[0]:
            rec = out.setdefault(T.label[k], {"km": round(float(dist[k]), 1), "loc": [round(float(lat[near[k]]), 3), round(float(lon[near[k]]), 3)], "v": {}})
            rec["v"][slab] = {"2050": [round(float(x), 2) for x in vals[:, 0, near[k]]],
                              "2100": [round(float(x), 2) for x in vals[:, 1, near[k]]]}
    if not out:
        raise RuntimeError("no coastal places found; archive layout may have changed")
    json.dump({"source": "IPCC AR6 sea level projections (Garner et al. 2021), medium confidence, relative to 1995-2014",
               "quantiles": QUANTS, "units": "m", "places": out}, open(dest, "w"), separators=(",", ":"))
    C.log.info("sea level: %d coastal places written to %s", len(out), dest)
