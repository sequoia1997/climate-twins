"""S1 batch 1 data runner (GitHub Actions): GBIF acquisition in multi-species downloads, native-range masks, final occurrence assets.

  python -m ctw.species.s1run acquire [--hours 5.5]   request the batch downloads (3 at a time), wait, fetch, split by species, clean, store
  python -m ctw.species.s1run native                  WCVP native areas (plants) and GRIIS introduced-country rows for the batch species
  python -m ctw.species.s1run assemble                masks, flags, target-group well-sampled flags, final assets s1_*, manifest

Species and download batches: data/species/batch1.csv (status 'selected'; column dl_batch). Everything is stored on the GitHub release
`species-pilot-data` under names that start with s1_, so no pilot asset is ever replaced; a rerun skips what is stored (resumable).
Cleaning is exactly the pilot's (ctw.species.w2cells.CellCleaner, one instance per species, rows routed by the download's `specieskey`).
Target-group grids are the pilot's (`tg_density_<group>_v1.npz` on the release): batch 1 has no herps or fish, so no new target-group
download is needed. GBIF credentials come from the environment (GBIF_USER, GBIF_PWD, GBIF_EMAIL) and are never printed.
Local tests: S1_NO_RELEASE=1 (state and assets then live under the work folder).
"""
from __future__ import annotations
import csv, json, os, shutil, sys, tempfile, threading, time, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests

from . import gbif, native as N, tg, w2cells, w2run as W

ROOT = Path(__file__).resolve().parents[2]
BATCH_CSV = ROOT / "data" / "species" / "batch1.csv"
WORK = Path(os.environ.get("S1_WORK", ROOT / "work" / "s1"))
VERSION = "v1"
NO_REL = os.environ.get("S1_NO_RELEASE") == "1"
W.NO_REL = NO_REL
W.WORK = WORK            # w2run's release helpers use this folder in no-release mode


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def slug(sci: str) -> str:
    return sci.replace(" ", "_")


def read_batch(status: str = "selected") -> list[dict]:
    with open(BATCH_CSV, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["status"] == status]


def batches(rows) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["dl_batch"], []).append(r)
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- state (mirrored to the release as s1_state.json)
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.f = WORK / "s1_state.json"
        self.d: dict = {}
        if W.rel_get("s1_state.json", self.f):
            self.d = json.load(open(self.f))

    def get(self, job):
        return self.d.get(job, {})

    def set(self, job, **kw):
        with self.lock:
            self.d.setdefault(job, {}).update(kw)
            self.f.parent.mkdir(parents=True, exist_ok=True)
            self.f.write_text(json.dumps(self.d, indent=1, default=str))
            try:
                W.rel_put(self.f)
            except Exception as e:
                log("state upload failed", type(e).__name__)


# --------------------------------------------------------------------------- GBIF multi-species download
def predicate_multi(keys: list[int]) -> dict:
    p = gbif.predicate(keys[0])
    p["predicates"][0] = {"type": "in", "key": "TAXON_KEY", "values": [str(k) for k in keys]}      # same filters as the pilot, several taxa
    return p


def request_multi(keys: list[int]) -> str:
    body = {"creator": os.environ["GBIF_USER"], "notificationAddresses": [os.environ["GBIF_EMAIL"]], "sendNotification": False,
            "format": "SIMPLE_PARQUET", "predicate": predicate_multi(keys)}
    r = requests.post(f"{gbif.API}/occurrence/download/request", json=body, auth=gbif.auth(), timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"download request refused: HTTP {r.status_code} {r.text[:400]}")      # never echo the body: it holds the address
    return r.text.strip().strip('"')


def stored(rows, have) -> bool:
    return all(f"s1_cells_{slug(r['scientific_name'])}.parquet" in have and f"s1_report_{slug(r['scientific_name'])}.json" in have
               and f"s1_datasets_{slug(r['scientific_name'])}.json" in have for r in rows)


def route_and_clean(folder, rows: list[dict], land=None, ref=None):
    """Read the unzipped multi-species SIMPLE_PARQUET and feed each species' rows (by `specieskey`) to its own CellCleaner (the pilot's cleaning,
    unchanged). Returns ({taxon key: cleaner}, number of rows that belong to none of the species)."""
    cleaners = {int(r["gbif_taxon_key"]): w2cells.CellCleaner(land=land, ref=ref, keep_cultivated=(r["group"] == "crop")) for r in rows}
    unmatched = 0
    for d in w2cells.read_batches(folder, extra=("specieskey",)):
        sk = pd.to_numeric(d["specieskey"], errors="coerce").to_numpy() if "specieskey" in d else np.full(len(d), -1.0)
        hit = np.zeros(len(d), bool)
        for k, cc in cleaners.items():
            m = sk == k
            if m.any():
                cc.feed(d[m])
                hit |= m
        unmatched += int((~hit).sum())
    return cleaners, unmatched


def process_batch(bid: str, key: str, rows: list[dict], state: State) -> bool:
    t0 = time.time()
    s = gbif.status(key)
    meta = W.download_meta(s, key)
    if s["status"] != "SUCCEEDED":
        state.set(f"batch:{bid}", **meta)
        return False
    tmp = Path(os.environ.get("S1_TMP", tempfile.gettempdir())) / f"s1-{bid}"
    shutil.rmtree(tmp, ignore_errors=True)
    z = W.fetch_zip(s["downloadLink"], tmp)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(tmp)
    z.unlink()
    ref, land = W.ref_set()
    cleaners, unmatched = route_and_clean(tmp, rows, land, ref)
    by_key = {int(r["gbif_taxon_key"]): r for r in rows}
    shutil.rmtree(tmp, ignore_errors=True)
    out = WORK / "cells"; out.mkdir(parents=True, exist_ok=True)
    for k, cc in cleaners.items():
        r = by_key[k]; sci = r["scientific_name"]
        cells, rep = cc.finish()
        rep.update({"group": r["group"], "treatment": "crop_cultivated" if r["group"] == "crop" else "wild_native", "species": sci, "download_key": key,
                    "download_batch": bid, "species_in_download": len(rows), "records_in_download_all_species": meta["records"],
                    "unmatched_records_in_download": unmatched, "process_s": round(time.time() - t0),
                    **{x: meta[x] for x in ("doi", "created", "citation", "licence")},
                    "records": rep["steps"][0]["left"]})
        cells.to_parquet(out / f"s1_cells_{slug(sci)}.parquet", compression="zstd", index=False)
        (out / f"s1_report_{slug(sci)}.json").write_text(json.dumps(rep, indent=1))
        (out / f"s1_datasets_{slug(sci)}.json").write_text(json.dumps(cc.datasets))
        for n in (f"s1_datasets_{slug(sci)}.json", f"s1_cells_{slug(sci)}.parquet", f"s1_report_{slug(sci)}.json"):
            W.rel_put(out / n)
        log("processed", sci, rep["n_cells"], "cells", rep["steps"][0]["left"], "records")
    state.set(f"batch:{bid}", **meta, processed=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), species=[r["scientific_name"] for r in rows],
              unmatched_records=unmatched)
    return True


def acquire(hours: float) -> int:
    W.ensure_release()
    state = State()
    have = W.rel_assets()
    bs = batches(read_batch())
    todo = {b: rs for b, rs in bs.items() if not stored(rs, have)}
    log(f"{len(bs) - len(todo)} of {len(bs)} download batches already stored, {len(todo)} to do")
    deadline = time.time() + hours * 3600
    pending: dict[str, str] = {}
    queue = list(todo)
    failed: dict = {}
    state.set("_run", started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    while queue or pending:
        for b in list(queue):
            known = state.get(f"batch:{b}").get("key")
            if known:
                st = gbif.status(known)
                if st["status"] in ("FAILED", "CANCELLED", "KILLED", "FILE_ERASED"):
                    log("download", b, "ended as", st["status"], "- requesting a new one")
                    known = None
            if known:
                queue.remove(b); pending[b] = known
                continue
            if len(pending) >= 3 or time.time() > deadline - 600:
                continue
            try:
                key = request_multi([int(r["gbif_taxon_key"]) for r in todo[b]])
            except RuntimeError as e:
                if "420" in str(e):
                    continue
                failed[b] = str(e)[:300]; queue.remove(b); log("request failed", b, failed[b]); continue
            state.set(f"batch:{b}", key=key, requested=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), species=[r["scientific_name"] for r in todo[b]])
            queue.remove(b); pending[b] = key
            log("requested batch", b, key)
        for b, key in list(pending.items()):
            st = gbif.status(key)
            if st["status"] in ("PREPARING", "RUNNING", "SUSPENDED"):
                continue
            del pending[b]
            if st["status"] != "SUCCEEDED":
                failed[b] = st["status"]; state.set(f"batch:{b}", **W.download_meta(st, key)); log("download", b, st["status"]); continue
            log("ready", b, key)
            try:
                process_batch(b, key, todo[b], state)         # sequential: one batch at a time keeps disk and memory inside the runner limits
            except Exception as e:
                failed[b] = f"{type(e).__name__}: {e}"[:300]; log("processing failed", b, failed[b])
        if time.time() > deadline:
            log("time limit reached; state saved, start the workflow again to continue")
            break
        time.sleep(30 if (pending or queue) else 5)
    have = W.rel_assets()
    left = [b for b, rs in bs.items() if not stored(rs, have)]
    log("failed:", failed, "| batches not stored:", left)
    (WORK / "acquire_summary.json").write_text(json.dumps({"failed": failed, "not_stored": left}, indent=1))
    return 0 if not failed and not left else 1


# --------------------------------------------------------------------------- native-range inputs
def native_inputs() -> int:
    """WCVP native areas for the plants (trees, wild plants) and GRIIS introduced-country rows for every species."""
    W.ensure_release()
    rows = read_batch()
    cache = WORK / "cache"; cache.mkdir(parents=True, exist_ok=True)
    plants = [r["scientific_name"] for r in rows if r["native_source"] == "wcvp"]
    wc = N.build_wcvp_pilot(plants, cache, cache / "s1_wcvp.json")
    missing = [n for n in plants if n not in wc]
    log("WCVP entries", len(plants) - len(missing), "of", len(plants), "missing:", missing)
    gr = N.build_griis_pilot([r["scientific_name"] for r in rows if r["kind"] != "crop"], cache / "s1_griis.json")
    log("GRIIS rows", {k: len(v) for k, v in gr.items() if not k.startswith("_")})
    W.rel_put(cache / "s1_wcvp.json"); W.rel_put(cache / "s1_griis.json")
    return 0


def sha256(p: Path) -> str:
    return W.sha256(p)


def assemble() -> int:
    W.ensure_release()
    rows = read_batch()
    cache = WORK / "cache"; cache.mkdir(parents=True, exist_ok=True)
    out = WORK / "final"; out.mkdir(parents=True, exist_ok=True)
    state = State()
    fe = N.subunits(cache); lab = N.label_raster(fe)
    td = N.tdwg_units(cache); labt = N.label_raster(td)
    unit_cont = np.array(["-"] + [f["properties"].get("CONTINENT") or "-" for f in fe])
    wp = W.rel_get("s1_wcvp.json", cache / "s1_wcvp.json") or (ROOT / "data/species/native/wcvp_s1.json")
    gp = W.rel_get("s1_griis.json", cache / "s1_griis.json") or (ROOT / "data/species/native/griis_s1.json")
    wcvp, griis = json.load(open(wp)), json.load(open(gp))
    groups = {}
    for gname in ("bird", "mammal", "insect_arachnid", "plant"):
        p = W.rel_get(f"tg_density_{gname}_v1.npz", WORK / "tg" / f"tg_density_{gname}_v1.npz")
        if not p:
            raise RuntimeError(f"pilot target-group grid {gname} missing from the release")
        z = np.load(p)
        groups[gname] = np.stack([z["all"], z["p1_1970_1999"], z["p2_2000_2020"]])
        log("target group", gname, "loaded")
    species_tables, excluded_tables, report, masks = [], [], {}, {}
    for r in rows:
        sci = r["scientific_name"]; tgname = tg.PILOT_GROUP_TO_TG[r["group"]]
        pc = W.rel_get(f"s1_cells_{slug(sci)}.parquet", WORK / "cells" / f"s1_cells_{slug(sci)}.parquet")
        pr = W.rel_get(f"s1_report_{slug(sci)}.json", WORK / "cells" / f"s1_report_{slug(sci)}.json")
        if not pc:
            log("MISSING cells for", sci); report[sci] = {"missing": True}; continue
        cells = pd.read_parquet(pc); rep = json.load(open(pr))
        cur = N.curated_mask(r["native_continents_curated"], fe, lab)
        has_w = sci in wcvp
        wm = N.tdwg_mask(wcvp[sci]["native"], td, labt) if has_w else None
        is_crop = r["group"] == "crop"
        final = np.ones((N.NROW, N.NCOL), bool) if is_crop else (wm if has_w else cur)
        gi = N.griis_units(griis.get(sci, []), fe)
        gm = np.zeros(len(fe) + 1, bool)
        for i in gi:
            gm[i + 1] = True
        gmask = gm[lab]
        ri, ci = cells["row"].to_numpy(), cells["col"].to_numpy()
        cells["native_curated"] = cur[ri, ci]
        cells["native_wcvp"] = (wm[ri, ci].astype(np.int8) if has_w else np.int8(-1))
        cells["griis_intro"] = gmask[ri, ci]
        keep = final[ri, ci]
        removed = cells[~keep]
        rm_cont = pd.Series(unit_cont[lab[removed["row"].to_numpy(), removed["col"].to_numpy()]]).value_counts().to_dict()
        ambiguous = [x for x in griis.get(sci, []) if not ((x.get("establishmentMeans") or "").upper().startswith("INTRODUCED"))]
        rep["native_mask"] = {
            "source": ("none: crop modelled where recorded (no wild native-range mask)" if is_crop else "WCVP (data, TDWG level 3)" if has_w else "curated (our judgement, Natural Earth subunits)"),
            "treatment": "crop_cultivated" if is_crop else "wild_native", "wanted_source": r["native_source"],
            "curated_spec": r["native_continents_curated"], "mask_cells_land_curated": int(cur.sum()), "mask_cells_final": int(final.sum()),
            "cells_in": int(len(cells)), "cells_kept": int(keep.sum()), "cells_removed": int((~keep).sum()),
            "records_in": int(cells["n_records"].sum()), "records_kept": int(cells.loc[keep, "n_records"].sum()),
            "removed_cells_by_continent": {str(k): int(v) for k, v in rm_cont.items()},
            "cells_kept_not_in_curated": int((keep & ~cells["native_curated"].to_numpy()).sum()),
            "cells_curated_but_removed": int((~keep & cells["native_curated"].to_numpy()).sum()),
            "cells_kept_in_griis_introduced_country": int((keep & cells["griis_intro"].to_numpy()).sum()),
            "griis_units": sorted({fe[i]["properties"]["NAME"] for i in gi}),
            "griis_rows_total": len(griis.get(sci, [])), "griis_rows_ambiguous_not_applied": len(ambiguous),
            "wcvp_native_areas": len(wcvp[sci]["native"]) if has_w else None}
        if not is_crop:
            masks[f"{slug(sci)}__final"] = np.packbits(final, axis=1)
        masks[f"{slug(sci)}__curated"] = np.packbits(cur, axis=1)
        for df, bucket in ((cells[keep], species_tables), (removed, excluded_tables)):
            df = df.copy()
            df.insert(0, "species", sci); df.insert(0, "species_key", int(r["gbif_taxon_key"]))
            df["group"] = r["group"]; df["tg_group"] = tgname
            df["treatment"] = "crop_cultivated" if is_crop else "wild_native"
            df["kind"] = "crop" if is_crop else "wild"
            bucket.append(df)
        report[sci] = rep
    main = pd.concat(species_tables, ignore_index=True)
    excl = pd.concat(excluded_tables, ignore_index=True) if excluded_tables else main.iloc[:0]
    for df in (main, excl):
        for c in ("tg_block_p1", "tg_block_p2"):
            df[c] = np.int64(-1)
        df["ws20"] = False; df["ws100"] = False
        df["tg_source"] = "none"
    for gname, grid in groups.items():
        for df in (main, excl):
            m = (df["tg_group"] == gname).to_numpy()
            if not m.any():
                continue
            lk = tg.lookup(grid, df.loc[m, "row"].to_numpy(), df.loc[m, "col"].to_numpy())
            for k, v in lk.items():
                df.loc[m, k] = v
            df.loc[m, "tg_source"] = "gbif sql download (pilot grid)"
    ordered = ["species_key", "species", "group", "kind", "treatment", "tg_group", "row", "col", "lat", "lon", "year_min", "year_max", "n_records", "n_events",
               "n_1970_1999", "n_2000_2020", "n_2021_plus", "native_curated", "native_wcvp", "griis_intro", "tg_block_p1", "tg_block_p2", "ws20", "ws100", "tg_source"]
    main, excl = main[ordered], (excl[ordered] if len(excl) else excl)
    files = {}

    def save(df, name):
        p = out / name; df.to_parquet(p, compression="zstd", index=False); files[name] = p
    save(main[main["treatment"] == "crop_cultivated"], f"s1_occ_cells_crops_{VERSION}.parquet")
    save(main[main["treatment"] == "wild_native"], f"s1_occ_cells_{VERSION}.parquet")
    save(excl, f"s1_occ_cells_{VERSION}_excluded_non_native.parquet")
    p = out / f"s1_native_masks_{VERSION}.npz"
    np.savez_compressed(p, **masks); files[p.name] = p
    for sci, rep in report.items():
        rep["download_state"] = {k: v for k, v in state.get(f"batch:{next((r['dl_batch'] for r in rows if r['scientific_name'] == sci), '')}").items() if k not in ("predicate", "sql")}
        dp = W.rel_get(f"s1_datasets_{slug(sci)}.json", WORK / "cells" / f"s1_datasets_{slug(sci)}.json")
        if dp:
            rep["dataset_counts"] = json.load(open(dp))
    summary = {"version": VERSION, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "species": report}
    p = out / f"s1_w2_report_{VERSION}.json"; p.write_text(json.dumps(summary, indent=1, default=str)); files[p.name] = p
    manifest = {"version": VERSION, "built": summary["built"], "batch": "S1 batch 1", "species_table": "data/species/batch1.csv",
                "grid": "TerraClimate native 1/24 degree, 4320 x 8640, row 0 = north, cell centre lat = 90 - (row + 0.5) / 24, lon = -180 + (col + 0.5) / 24",
                "licence_filter": "CC0 and CC-BY records only", "tg_grids": "pilot tg_density_<group>_v1.npz (unchanged)",
                "species_kind": {r["scientific_name"]: r["kind"] for r in rows},
                "files": {n: {"bytes": f.stat().st_size, "sha256": sha256(f)} for n, f in files.items()}}
    mp = out / f"s1_manifest_w2_{VERSION}.json"; mp.write_text(json.dumps(manifest, indent=1))
    for f in list(files.values()) + [mp]:
        W.rel_put(f)
    log("published", len(files) + 1, "assets;", "species with cells:", sum(1 for v in report.values() if not v.get("missing")))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "acquire":
        hrs = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 5.5
        sys.exit(acquire(hrs))
    sys.exit({"native": native_inputs, "assemble": assemble}[cmd]())
